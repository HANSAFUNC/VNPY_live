"""StockAI 数据抽屉 - 全局持久化存储管理 (FreqAI 风格)"""

import re
import shutil
import threading
import warnings
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import joblib
import numpy as np
import pandas as pd

from vnpy.alpha.logger import logger

from .utils import get_timestamp, load_json, load_parquet, save_json, save_parquet


class StockaiDataDrawer:
    """
    全局数据存储管理器 - 完全复刻 FreqAI FreqaiDataDrawer

    职责:
    - 存储每只股票元数据（模型文件名、训练时间戳）
    - 缓存已加载的模型在内存中
    - 持久化预测历史到磁盘
    - 管理模型版本
    """

    def __init__(self, full_path: Path, config: dict):
        """
        初始化数据抽屉

        参数:
            full_path: 数据存储根目录
            config: 配置字典
        """
        self.config = config
        self.freqai_info = config.get("freqai", {})
        self.full_path = full_path
        self.full_path.mkdir(parents=True, exist_ok=True)

        # pair 元数据字典 {pair: pair_info}
        self.pair_dict: dict[str, dict] = {}
        # 模型内存缓存 {filename: model}
        self.model_dictionary: dict[str, Any] = {}
        # 额外元数据存储
        self.meta_data_dictionary: dict[str, dict[str, Any]] = {}
        # 模型返回值存储 {pair: DataFrame}
        self.model_return_values: dict[str, pd.DataFrame] = {}
        # 历史K线数据缓存 {pair: {tf: DataFrame}}
        self.historic_data: dict[str, dict[str, pd.DataFrame]] = {}
        # 历史预测 {pair: DataFrame}
        self.historic_predictions: dict[str, pd.DataFrame] = {}

        # 文件路径
        self.historic_predictions_path = Path(self.full_path / "historic_predictions.pkl")
        self.historic_predictions_bkp_path = Path(
            self.full_path / "historic_predictions.backup.pkl"
        )
        self.pair_dictionary_path = Path(self.full_path / "pair_dictionary.json")
        self.global_metadata_path = Path(self.full_path / "global_metadata.json")
        self.metric_tracker_path = Path(self.full_path / "metric_tracker.json")

        # 从磁盘加载
        self.load_drawer_from_disk()
        self.load_historic_predictions_from_disk()

        # 指标追踪器
        self.metric_tracker: dict[str, dict[str, dict[str, list]]] = {}
        self.load_metric_tracker_from_disk()

        # 训练队列
        self.training_queue: dict[str, int] = {}

        # 线程锁
        self.history_lock = threading.Lock()
        self.save_lock = threading.Lock()
        self.pair_dict_lock = threading.Lock()
        self.metric_tracker_lock = threading.Lock()

        # DBSCAN 参数跟踪
        self.old_DBSCAN_eps: dict[str, float] = {}

        # 空的 pair_dict 模板
        self.empty_pair_dict: dict = {
            "model_filename": "",
            "trained_timestamp": 0,
            "data_path": "",
            "extras": {},
        }

        self.model_type = self.freqai_info.get("model_save_type", "joblib")

        self.current_candle: datetime = datetime.fromtimestamp(0, tz=UTC)

        logger.info(f"StockAI DataDrawer 初始化完成，路径: {full_path}")

    def collect_metrics(self, time_spent: float, pair: str) -> None:
        self.update_metric_tracker("train_time", time_spent, pair)

    def load_drawer_from_disk(self) -> None:
        """从磁盘加载 pair_dict"""
        data = load_json(self.pair_dictionary_path)
        if data:
            self.pair_dict = data
            logger.info(f"已加载 {len(self.pair_dict)} 只股票的元数据")

    def load_historic_predictions_from_disk(self) -> None:
        """从磁盘加载历史预测"""
        if self.historic_predictions_path.exists():
            try:
                self.historic_predictions = joblib.load(self.historic_predictions_path)
                logger.info(
                    f"已加载 {len(self.historic_predictions)} 只股票的历史预测"
                )
            except Exception as e:
                logger.warning(f"加载历史预测失败: {e}")
                self.historic_predictions = {}

    def save_historic_predictions_to_disk(self) -> None:
        """保存历史预测到磁盘"""
        if not self.historic_predictions:
            return

        with self.save_lock:
            try:
                # 备份旧文件
                if self.historic_predictions_path.exists():
                    shutil.copy2(
                        self.historic_predictions_path,
                        self.historic_predictions_bkp_path
                    )
                # 保存新文件
                joblib.dump(self.historic_predictions, self.historic_predictions_path)
            except Exception as e:
                logger.error(f"保存历史预测失败: {e}")

    def load_metric_tracker_from_disk(self) -> None:
        """从磁盘加载指标追踪器"""
        data = load_json(self.metric_tracker_path)
        if data:
            self.metric_tracker = data

    def save_metric_tracker_to_disk(self) -> None:
        """保存指标追踪器到磁盘"""
        save_json(self.metric_tracker, self.metric_tracker_path)

    def load_global_metadata_from_disk(self) -> dict[str, Any]:
        """从磁盘加载全局元数据"""
        return load_json(self.global_metadata_path) or {}

    def save_global_metadata_to_disk(self, metadata: dict[str, Any]) -> None:
        """保存全局元数据到磁盘"""
        save_json(metadata, self.global_metadata_path)

    def get_pair_dict_info(self, pair: str) -> tuple[str, int]:
        """
        获取指定股票的模型信息，不存在则创建空条目

        参数:
            pair: 股票代码

        返回:
            (model_filename, trained_timestamp)
        """
        pair_dict = self.pair_dict.get(pair)

        if pair_dict:
            model_filename = pair_dict["model_filename"]
            trained_timestamp = pair_dict["trained_timestamp"]
        else:
            self.pair_dict[pair] = self.empty_pair_dict.copy()
            model_filename = ""
            trained_timestamp = 0

        return model_filename, trained_timestamp

    def set_pair_dict_info(self, metadata: dict) -> None:
        """
        设置股票元数据（如果不存在）

        参数:
            metadata: 包含 pair 键的字典
        """
        pair_in_dict = self.pair_dict.get(metadata["pair"])
        if pair_in_dict:
            return
        else:
            self.pair_dict[metadata["pair"]] = self.empty_pair_dict.copy()
            return

    def _generate_model_filename(self, pair: str, timestamp: int) -> str:
        """生成模型文件名"""
        safe_pair = pair.replace(".", "_")
        return f"sub-train-{safe_pair}_{timestamp}"

    def save_model(self, pair: str, model: Any, timestamp: int, dk: Any = None) -> str:
        """
        保存模型到磁盘

        参数:
            pair: 股票代码
            model: 模型对象
            timestamp: 时间戳
            dk: 数据厨房（可选）

        返回:
            模型文件名
        """
        filename = self._generate_model_filename(pair, timestamp)
        model_path = self.full_path / filename
        model_path.mkdir(parents=True, exist_ok=True)

        # 保存模型
        model_file = model_path / "model.pkl"
        joblib.dump(model, model_file)

        # 保存元数据
        metadata = {
            "model_filename": filename,
            "trained_timestamp": timestamp,
            "data_path": str(model_path),
            "pair": pair,
        }
        save_json(metadata, model_path / "metadata.json")

        # 缓存到内存
        self.model_dictionary[filename] = model

        # 更新 pair_dict
        with self.pair_dict_lock:
            self.pair_dict[pair] = self.empty_pair_dict.copy()
            self.pair_dict[pair].update(metadata)
            save_json(self.pair_dict, self.pair_dictionary_path)

        logger.info(f"模型已保存: {filename} ({pair})")
        return filename

    def load_model(self, pair: str) -> Any:
        """
        加载模型（优先从内存缓存）

        参数:
            pair: 股票代码

        返回:
            模型对象
        """
        if pair not in self.pair_dict:
            raise ValueError(f"未找到 {pair} 的模型")

        filename = self.pair_dict[pair]["model_filename"]

        # 检查内存缓存
        if filename in self.model_dictionary:
            return self.model_dictionary[filename]

        # 从磁盘加载
        model_path = self.full_path / filename / "model.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        model = joblib.load(model_path)
        self.model_dictionary[filename] = model
        logger.info(f"模型已加载: {filename} ({pair})")

        return model

    def append_model_predictions(
        self,
        pair: str,
        predictions: pd.DataFrame,
        do_preds: np.ndarray,
        dk: Any,
        strat_df: pd.DataFrame,
    ) -> None:
        """
        Append model predictions to historic predictions dataframe, then set the
        strategy return dataframe to the tail of the historic predictions.
        """
        len_df = len(strat_df)
        index = self.historic_predictions[pair].index[-1:]
        columns = self.historic_predictions[pair].columns

        zeros_df = pd.DataFrame(np.zeros((1, len(columns))), index=index, columns=columns)
        self.historic_predictions[pair] = pd.concat(
            [self.historic_predictions[pair], zeros_df], ignore_index=True, axis=0
        )
        df = self.historic_predictions[pair]

        for label in predictions.columns:
            label_loc = df.columns.get_loc(label)
            pred_label_loc = predictions.columns.get_loc(label)
            df.iloc[-1, label_loc] = predictions.iloc[-1, pred_label_loc]
            if df[label].dtype == object:
                continue
            label_mean_loc = df.columns.get_loc(f"{label}_mean")
            label_std_loc = df.columns.get_loc(f"{label}_std")
            df.iloc[-1, label_mean_loc] = dk.data["labels_mean"][label]
            df.iloc[-1, label_std_loc] = dk.data["labels_std"][label]

        do_predict_loc = df.columns.get_loc("do_predict")
        df.iloc[-1, do_predict_loc] = do_preds[-1]
        if self.freqai_info.get("feature_parameters", {}).get("DI_threshold", 0) > 0:
            DI_values_loc = df.columns.get_loc("DI_values")
            df.iloc[-1, DI_values_loc] = dk.DI_values[-1]

        if dk.data.get("extra_returns_per_train"):
            rets = dk.data["extra_returns_per_train"]
            for return_str in rets:
                return_loc = df.columns.get_loc(return_str)
                df.iloc[-1, return_loc] = rets[return_str]

        high_price_loc = df.columns.get_loc("high_price")
        high_loc = strat_df.columns.get_loc("high")
        df.iloc[-1, high_price_loc] = strat_df.iloc[-1, high_loc]
        low_price_loc = df.columns.get_loc("low_price")
        low_loc = strat_df.columns.get_loc("low")
        df.iloc[-1, low_price_loc] = strat_df.iloc[-1, low_loc]
        close_price_loc = df.columns.get_loc("close_price")
        close_loc = strat_df.columns.get_loc("close")
        df.iloc[-1, close_price_loc] = strat_df.iloc[-1, close_loc]
        date_pred_loc = df.columns.get_loc("date_pred")
        date_loc = strat_df.columns.get_loc("date")
        df.iloc[-1, date_pred_loc] = strat_df.iloc[-1, date_loc]

        self.model_return_values[pair] = df.tail(len_df).reset_index(drop=True)

    def get_historic_predictions(
        self,
        pair: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Optional[pd.DataFrame]:
        """
        获取历史预测

        参数:
            pair: 股票代码
            start: 开始时间（可选）
            end: 结束时间（可选）

        返回:
            预测历史 DataFrame
        """
        if pair not in self.historic_predictions:
            return None

        df = self.historic_predictions[pair].copy()

        if "datetime" in df.columns:
            if start:
                df = df[df["datetime"] >= start]
            if end:
                df = df[df["datetime"] <= end]
            df = df.sort_values("datetime")

        return df

    def should_retrain(self, pair: str, max_age_days: int = 30) -> bool:
        """
        检查是否需要重新训练

        参数:
            pair: 股票代码
            max_age_days: 模型最大年龄（天）

        返回:
            True 如果需要重新训练
        """
        if pair not in self.pair_dict:
            return True

        last_trained = self.pair_dict[pair].get("trained_timestamp", 0)
        age_days = (get_timestamp() - last_trained) / 86400

        return age_days > max_age_days

    def update_metric_tracker(self, metric: str, value: float, pair: str) -> None:
        """
        更新指标追踪器

        参数:
            metric: 指标名称
            value: 指标值
            pair: 股票代码
        """
        if pair not in self.metric_tracker:
            self.metric_tracker[pair] = {}
        if metric not in self.metric_tracker[pair]:
            self.metric_tracker[pair][metric] = {"values": [], "timestamps": []}

        self.metric_tracker[pair][metric]["values"].append(value)
        self.metric_tracker[pair][metric]["timestamps"].append(get_timestamp())

    def np_encoder(self, obj):
        """numpy 类型编码器，用于 JSON 序列化"""
        if isinstance(obj, np.generic):
            return obj.item()
        return obj

    def set_initial_return_values(
        self, pair: str, pred_df: pd.DataFrame, dataframe: pd.DataFrame
    ) -> None:
        """
        Set the initial return values to the historical predictions dataframe. This avoids needing
        to repredict on historical candles, and also stores historical predictions despite
        retrainings (so stored predictions are true predictions, not just inferencing on trained
        data).
        """
        new_pred = pred_df.copy()

        # 支持 date 或 datetime 列
        date_col = "date" if "date" in dataframe.columns else "datetime"
        new_pred["date_pred"] = dataframe[date_col]
        columns_to_nan = new_pred.columns.difference(["date_pred", date_col])
        new_pred[columns_to_nan] = None

        hist_preds = self.historic_predictions[pair].copy()

        new_pred["date_pred"] = pd.to_datetime(new_pred["date_pred"])
        hist_preds["date_pred"] = pd.to_datetime(hist_preds["date_pred"])

        common_dates = pd.merge(new_pred, hist_preds, on="date_pred", how="inner")
        if len(common_dates.index) > 0:
            new_pred = new_pred.iloc[len(common_dates):]
        else:
            logger.warning(
                "No common dates found between new predictions and historic "
                "predictions. You likely left your StockAI instance offline "
                f"for more than {len(dataframe.index)} candles."
            )

        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=FutureWarning)
            new_pred_reindexed = new_pred.reindex(columns=hist_preds.columns)
            df_concat = pd.concat([hist_preds, new_pred_reindexed], ignore_index=True)

        df_concat = df_concat.fillna(0)
        self.historic_predictions[pair] = df_concat
        self.model_return_values[pair] = df_concat.tail(len(dataframe.index)).reset_index(drop=True)

    def attach_return_values_to_return_dataframe(
        self, pair: str, dataframe: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Attach the return values to the strat dataframe
        """
        df = self.model_return_values[pair]
        to_keep = [col for col in dataframe.columns if not col.startswith("&")]
        dataframe = pd.concat([dataframe[to_keep], df], axis=1)
        return dataframe

    def return_null_values_to_strategy(
        self, dataframe: pd.DataFrame, dk: "StockaiDataKitchen"
    ) -> None:
        """
        Build 0 filled dataframe to return to strategy
        """
        dk.find_features(dataframe)
        dk.find_labels(dataframe)

        full_labels = dk.label_list + dk.unique_class_list

        for label in full_labels:
            dataframe[label] = 0
            dataframe[f"{label}_mean"] = 0
            dataframe[f"{label}_std"] = 0

        dataframe["do_predict"] = 0

        if self.freqai_info.get("feature_parameters", {}).get("DI_threshold", 0) > 0:
            dataframe["DI_values"] = 0

        if dk.data.get("extra_returns_per_train"):
            rets = dk.data["extra_returns_per_train"]
            for return_str in rets:
                dataframe[return_str] = 0

        dk.return_dataframe = dataframe

    def purge_old_models(self, num_keep: int = None) -> None:
        """
        清理旧模型，只保留最近 num_keep 个

        参数:
            num_keep: 保留的模型数量，None 或 0 表示不清理
        """
        if num_keep is None:
            num_keep = self.config.get("purge_old_models", 0)

        if not num_keep:
            return
        elif isinstance(num_keep, bool):
            num_keep = 2

        model_folders = [x for x in self.full_path.iterdir() if x.is_dir()]

        pattern = re.compile(r"^sub-train-(.+)_(\d{10})$")

        delete_dict: dict[str, dict] = {}

        for directory in model_folders:
            result = pattern.match(str(directory.name))
            if result is None:
                continue
            pair = result.group(1)
            timestamp = result.group(2)

            if pair not in delete_dict:
                delete_dict[pair] = {}
                delete_dict[pair]["num_folders"] = 1
                delete_dict[pair]["timestamps"] = {int(timestamp): directory}
            else:
                delete_dict[pair]["num_folders"] += 1
                delete_dict[pair]["timestamps"][int(timestamp)] = directory

        for pair in delete_dict:
            if delete_dict[pair]["num_folders"] > num_keep:
                sorted_dict = dict(sorted(delete_dict[pair]["timestamps"].items()))
                num_delete = len(sorted_dict) - num_keep
                deleted = 0
                for k, v in sorted_dict.items():
                    if deleted >= num_delete:
                        break
                    logger.info(f"StockAI 清理旧模型文件 {v}")
                    shutil.rmtree(v)
                    deleted += 1
