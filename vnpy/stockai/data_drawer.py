"""StockAI 数据抽屉 - 全局持久化存储管理"""

from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import joblib
import polars as pl

from vnpy.alpha.logger import logger

from .utils import get_timestamp, load_json, load_parquet, save_json, save_parquet


class StockaiDataDrawer:
    """
    全局数据存储管理器

    职责:
    - 存储每只股票元数据（模型文件名、训练时间戳）
    - 缓存已加载的模型在内存中
    - 持久化预测历史到磁盘
    - 管理模型版本

    对应 FreqAI 的 FreqaiDataDrawer 类
    """

    def __init__(self, full_path: Path, config: dict):
        """
        初始化数据抽屉

        参数:
            full_path: 数据存储根目录
            config: 配置字典
        """
        self.config = config
        self.full_path = full_path
        self.full_path.mkdir(parents=True, exist_ok=True)

        # 内存存储结构
        self.pair_dict: dict[str, dict] = {}  # {股票代码: 元数据}
        self.model_dictionary: dict[str, Any] = {}  # {文件名: 模型对象}
        self.meta_data_dictionary: dict[str, dict[str, Any]] = {}  # 额外元数据存储
        self.model_return_values: dict[str, pl.DataFrame] = {}  # 模型预测返回值存储
        self.historic_data: dict[str, dict[str, pl.DataFrame]] = {}  # 历史K线数据缓存
        self.historic_predictions: dict[str, pl.DataFrame] = {}  # {股票代码: 预测历史}

        # 文件路径
        self.historic_predictions_path = full_path / "historic_predictions.parquet"
        self.pair_dictionary_path = full_path / "pair_dictionary.json"

        # 回测实时模型模式
        self.backtest_live_models = config.get("backtest_live_models", False)

        # 模型保存类型
        self.model_type = config.get("model_save_type", "joblib")

        # 训练队列和DBSCAN参数跟踪
        self.training_queue: dict[str, int] = {}
        self.old_DBSCAN_eps: dict[str, float] = {}

        # 空的pair_dict模板
        self.empty_pair_dict: dict = {
            "model_filename": "",
            "trained_timestamp": 0,
            "data_path": "",
            "extras": {},
        }

        # 指标追踪器
        self.metric_tracker: dict[str, dict] = {}

        # 从磁盘加载已有数据
        self._load_from_disk()

        logger.info(f"数据抽屉初始化完成，路径: {full_path}")

    def _load_from_disk(self) -> None:
        """从磁盘加载已有数据"""
        # 加载股票元数据
        data = load_json(self.pair_dictionary_path)
        if data:
            self.pair_dict = data
            logger.info(f"已加载 {len(self.pair_dict)} 只股票的元数据")

        # 加载预测历史
        df = load_parquet(self.historic_predictions_path)
        if df is not None:
            for pair in df["pair"].unique().to_list():
                self.historic_predictions[pair] = df.filter(pl.col("pair") == pair)
            logger.info(f"已加载 {len(self.historic_predictions)} 只股票的历史预测")

    def _generate_model_filename(self, pair: str, timestamp: int) -> str:
        """生成模型文件名"""
        safe_pair = pair.replace(".", "_")
        return f"sub-train-{safe_pair}_{timestamp}"

    def get_pair_dict_info(self, pair: str) -> tuple[str, int]:
        """
        获取指定股票的模型信息

        参数:
            pair: 股票代码

        返回:
            (model_filename, trained_timestamp)
        """
        pair_info = self.pair_dict.get(pair)
        if pair_info:
            return pair_info["model_filename"], pair_info["trained_timestamp"]
        else:
            # 初始化新的pair_dict项
            self.pair_dict[pair] = self.empty_pair_dict.copy()
            return "", 0

    def set_pair_dict_info(self, metadata: dict) -> None:
        """
        设置股票元数据（如果不存在）

        参数:
            metadata: 包含pair等信息的字典
        """
        pair = metadata.get("pair")
        if pair and pair not in self.pair_dict:
            self.pair_dict[pair] = self.empty_pair_dict.copy()

    def save_model(self, pair: str, model: Any, timestamp: int) -> None:
        """
        保存模型到磁盘

        参数:
            pair: 股票代码
            model: 模型对象
            timestamp: 时间戳
        """
        filename = self._generate_model_filename(pair, timestamp)
        model_path = self.full_path / filename
        model_path.mkdir(parents=True, exist_ok=True)

        # 使用 joblib 保存模型
        model_file = model_path / "model.pkl"
        joblib.dump(model, model_file)

        # 缓存到内存
        self.model_dictionary[filename] = model

        # 更新元数据（使用empty_pair_dict作为模板）
        self.pair_dict[pair] = self.empty_pair_dict.copy()
        self.pair_dict[pair].update({
            "model_filename": filename,
            "trained_timestamp": timestamp,
            "data_path": str(model_path),
        })
        save_json(self.pair_dict, self.pair_dictionary_path)

        logger.info(f"模型已保存: {filename} ({pair})")

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

    def append_model_predictions(self, pair: str, predictions: pl.DataFrame) -> None:
        """
        追加预测结果到历史 (FreqAI风格)

        参数:
            pair: 股票代码
            predictions: 预测结果DataFrame
        """
        if pair in self.historic_predictions:
            # 对齐列结构：确保两个DataFrame有相同的列
            existing_df = self.historic_predictions[pair]
            all_cols = set(existing_df.columns) | set(predictions.columns)

            # 为缺失的列补空值
            for col in all_cols:
                if col not in existing_df.columns:
                    existing_df = existing_df.with_columns([pl.lit(None).alias(col)])
                if col not in predictions.columns:
                    predictions = predictions.with_columns([pl.lit(None).alias(col)])

            # 确保列顺序一致
            predictions = predictions.select(existing_df.columns)

            self.historic_predictions[pair] = pl.concat(
                [existing_df, predictions]
            )
            # 按 datetime 去重，保留最新记录
            self.historic_predictions[pair] = (
                self.historic_predictions[pair]
                .sort("datetime", descending=True)
                .unique(subset=["datetime"], keep="first")
                .sort("datetime")
            )
        else:
            self.historic_predictions[pair] = predictions

        # 持久化到磁盘
        self.save_historic_predictions_to_disk()

    def save_historic_predictions_to_disk(self) -> None:
        """将所有预测历史保存到磁盘 (FreqAI风格)"""
        if not self.historic_predictions:
            return

        all_preds = pl.concat(list(self.historic_predictions.values()))
        save_parquet(all_preds, self.historic_predictions_path)

    def get_historic_predictions(
        self,
        pair: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Optional[pl.DataFrame]:
        """
        获取历史预测

        参数:
            pair: 股票代码
            start: 开始时间（可选）
            end: 结束时间（可选）

        返回:
            预测历史DataFrame
        """
        if pair not in self.historic_predictions:
            return None

        df = self.historic_predictions[pair]

        if start:
            df = df.filter(pl.col("datetime") >= start)
        if end:
            df = df.filter(pl.col("datetime") <= end)

        return df.sort("datetime")

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

        if self.backtest_live_models:
            logger.info(f"{pair}: 回测实时模型模式，跳过重新训练")
            return False

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
        self.metric_tracker[pair][metric] = value
        logger.debug(f"{pair}: 指标 {metric} = {value:.4f}")

    def np_encoder(self, obj):
        """numpy 类型编码器，用于 JSON 序列化"""
        if isinstance(obj, np.generic):
            return obj.item()
        return obj

    def set_initial_return_values(
        self, pair: str, pred_df: pl.DataFrame, dataframe: pl.DataFrame
    ) -> None:
        """
        设置初始返回值到历史预测DataFrame

        避免在历史K线上重新预测，同时存储历史预测（真实预测而非训练数据上的推理）
        """
        new_pred = pred_df.clone()

        # 设置 date_pred 列
        if "datetime" in dataframe.columns:
            new_pred = new_pred.with_columns([dataframe["datetime"].alias("date_pred")])

        # 除了date_pred，其他列设为null（表示停机期间无预测）
        for col in new_pred.columns:
            if col not in ["date_pred", "datetime"]:
                new_pred = new_pred.with_columns([pl.lit(None).alias(col)])

        hist_preds = self.historic_predictions.get(pair, pl.DataFrame()).clone()
        if len(hist_preds) == 0:
            self.model_return_values[pair] = new_pred
            return

        # 合并历史预测
        all_cols = set(new_pred.columns) | set(hist_preds.columns)
        for col in all_cols:
            if col not in new_pred.columns:
                new_pred = new_pred.with_columns([pl.lit(None).alias(col)])
            if col not in hist_preds.columns:
                hist_preds = hist_preds.with_columns([pl.lit(None).alias(col)])

        new_pred = new_pred.select(hist_preds.columns)
        df_concat = pl.concat([hist_preds, new_pred])

        # 用0填充缺失值
        df_concat = df_concat.fill_null(0).fill_nan(0)

        self.historic_predictions[pair] = df_concat
        self.model_return_values[pair] = df_concat.tail(len(dataframe))

    def attach_return_values_to_return_dataframe(
        self, pair: str, dataframe: pl.DataFrame
    ) -> pl.DataFrame:
        """
        将返回值附加到策略DataFrame

        参数:
            pair: 股票代码
            dataframe: 策略DataFrame

        返回:
            附加了返回值的DataFrame
        """
        if pair not in self.model_return_values:
            return dataframe

        df = self.model_return_values[pair]

        # 保留原始DataFrame中不以 & 开头的列
        to_keep = [col for col in dataframe.columns if not col.startswith("&")]
        result = dataframe.select(to_keep)

        # 水平合并
        result = pl.concat([result, df], how="horizontal")

        return result

    def return_null_values_to_strategy(self, dataframe: pl.DataFrame, dk: StockaiDataKitchen) -> None:
        """
        构建填充0的DataFrame返回给策略（当模型不可用时）
        """
        dk.find_features(dataframe)
        dk.find_labels(dataframe)

        full_labels = dk.label_list + dk.unique_class_list

        for label in full_labels:
            dataframe = dataframe.with_columns([
                pl.lit(0.0).alias(label),
                pl.lit(0.0).alias(f"{label}_mean"),
                pl.lit(0.0).alias(f"{label}_std"),
            ])

        dataframe = dataframe.with_columns([pl.lit(0).alias("do_predict")])

        # DI值
        ft_params = self.config.get("feature_parameters", {})
        if ft_params.get("DI_threshold", 0) > 0:
            dataframe = dataframe.with_columns([pl.lit(0.0).alias("DI_values")])

        # 额外的返回值
        extra_returns = dk.data.get("extra_returns_per_train", {})
        for return_str in extra_returns:
            dataframe = dataframe.with_columns([pl.lit(0.0).alias(return_str)])

        dk.return_dataframe = dataframe

    def purge_old_models(self, num_keep: int = None) -> None:
        """
        清理旧模型，只保留最近 num_keep 个

        参数:
            num_keep: 保留的模型数量，None 或 0 表示不清理
        """
        import re
        import shutil

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
            coin = result.group(1)
            timestamp = result.group(2)

            if coin not in delete_dict:
                delete_dict[coin] = {}
                delete_dict[coin]["num_folders"] = 1
                delete_dict[coin]["timestamps"] = {int(timestamp): directory}
            else:
                delete_dict[coin]["num_folders"] += 1
                delete_dict[coin]["timestamps"][int(timestamp)] = directory

        for coin in delete_dict:
            if delete_dict[coin]["num_folders"] > num_keep:
                import collections
                sorted_dict = collections.OrderedDict(
                    sorted(delete_dict[coin]["timestamps"].items())
                )
                num_delete = len(sorted_dict) - num_keep
                deleted = 0
                for k, v in sorted_dict.items():
                    if deleted >= num_delete:
                        break
                    logger.info(f"FreqAI 清理旧模型文件 {v}")
                    shutil.rmtree(v)
                    deleted += 1
