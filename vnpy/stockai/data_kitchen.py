"""StockAI 数据厨房 - 完全复刻 FreqAI FreqaiDataKitchen"""

import random
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import numpy.typing as npt
import pandas as pd
from datasieve.pipeline import Pipeline
from pandas import DataFrame
from sklearn.model_selection import train_test_split

from vnpy.alpha.logger import logger

SECONDS_IN_DAY = 86400
SECONDS_IN_HOUR = 3600


class StockaiDataKitchen:
    """
    单只股票数据管理单元 - 完全复刻 FreqAI FreqaiDataKitchen

    职责:
    - 识别特征列 (包含 %- 前缀)
    - 识别标签列 (包含 & 前缀)
    - 训练/测试数据分割
    - 特征/标签管道管理 (datasieve)
    - 数据字典管理
    """

    def __init__(
        self,
        config: dict,
        live: bool = False,
        pair: str = "",
    ):
        """
        初始化数据厨房

        参数:
            config: 配置字典
            live: 是否实时模式
            pair: 股票代码
        """
        self.config = config
        self.freqai_config: dict[str, Any] = config.get("freqai", {})
        self.data: dict[str, Any] = {}
        self.data_dictionary: dict[str, DataFrame] = {}
        self.pair = pair
        # FreqAI 风格别名: symbol 与 pair 同义
        self.symbol = pair
        self.live = live

        # 路径
        self.data_path = Path()
        self.backtesting_results_path = Path()
        self.backtest_predictions_folder: str = "backtesting_predictions"

        # 完整数据
        self.full_df: DataFrame = DataFrame()
        self.append_df: DataFrame = DataFrame()

        # 管道对象 - 使用 datasieve
        self.feature_pipeline: Pipeline = Pipeline()
        self.label_pipeline: Pipeline = Pipeline()

        # 特征和标签列名列表
        self.label_list: list[str] = []
        self.training_features_list: list[str] = []

        # 模型文件名
        self.model_filename: str = ""

        # DI 值和 do_predict
        self.DI_values: npt.NDArray = np.array([])
        self.do_predict: npt.NDArray = np.array([])

        # 分类模型支持
        self.unique_classes: dict[str, list] = {}
        self.unique_class_list: list = []

        # 返回值 DataFrame
        self.return_dataframe: DataFrame = DataFrame()

        # 线程计数 (用于并行处理)
        self.thread_count: int = max(int(self.freqai_config.get("n_jobs", -1)), 1)

        # 回测相关
        self.backtest_live_models = config.get("freqai_backtest_live_models", False)
        if not self.live:
            self.full_path = self.get_full_models_path(self.config)

            if not self.backtest_live_models:
                train_period = self.freqai_config.get("train_period_days", 30)
                self.full_timerange = self.create_fulltimerange(
                    self.config.get("timerange", ""), train_period
                )
                # 拆分 timerange 字符串
                if "-" in self.full_timerange:
                    start_date, end_date = self.full_timerange.split("-", 1)
                else:
                    start_date = self.full_timerange
                    end_date = datetime.now().strftime("%Y%m%d")
                (
                    self.training_timeranges,
                    self.backtesting_timeranges,
                ) = self.split_timerange(
                    start_date,
                    end_date,
                    self.freqai_config.get("train_period_days", 30),
                    self.freqai_config.get("backtest_period_days", 7),
                )

        self.data["extra_returns_per_train"] = self.freqai_config.get(
            "extra_returns_per_train", {}
        )
        self.train_dates: DataFrame = pd.DataFrame()
        self.backtest_live_models_data: dict[str, Any] = {}

        logger.debug(f"数据厨房初始化: {pair}")

    def get_full_models_path(self, config: dict) -> Path:
        """获取完整模型路径"""
        path = config.get("freqai", {}).get("path", "freqai_models")
        identifier = config.get("freqai", {}).get("identifier", "default")
        return Path(path) / identifier

    def create_fulltimerange(self, timerange: str, train_period_days: int) -> str:
        """创建完整时间范围字符串"""
        if not timerange:
            # 默认使用最近的数据
            end = datetime.now()
            start = end - timedelta(days=train_period_days + 30)
            return f"{start.strftime('%Y%m%d')}-{end.strftime('%Y%m%d')}"
        return timerange

    def find_features(self, df: DataFrame) -> None:
        """
        识别特征列 - 列名包含 % (FreqAI 标准)

        参数:
            df: 已计算特征的 DataFrame
        """
        features = [c for c in df.columns if "%" in c]

        if not features:
            raise ValueError(f"{self.pair}: 未找到特征列（需要包含 % 的列名）")

        self.training_features_list = features
        logger.info(f"{self.pair}: 识别到 {len(features)} 个特征")

    def find_labels(self, df: DataFrame) -> None:
        """
        识别标签列 - 列名包含 & (FreqAI 标准)

        参数:
            df: 已计算标签的 DataFrame
        """
        labels = [c for c in df.columns if "&" in c]

        self.label_list = labels
        logger.info(f"{self.pair}: 识别到 {len(labels)} 个标签")

    def filter_features(
        self,
        unfiltered_df: DataFrame,
        training_feature_list: list[str],
        label_list: Optional[list[str]] = None,
        training_filter: bool = True,
    ) -> tuple[DataFrame, DataFrame]:
        """
        过滤特征和标签 - 完全复刻 FreqAI filter_features

        训练时: 删除包含 NaN/inf 的行
        预测时: 用 0 填充 NaN/inf，并设置 do_predict 标记无效行

        参数:
            unfiltered_df: 完整 DataFrame
            training_feature_list: 特征列名列表
            label_list: 标签列名列表
            training_filter: True=训练模式, False=预测模式

        返回:
            (filtered_df, labels_df)
        """
        # 检查必需的列是否存在
        missing_cols = [c for c in training_feature_list if c not in unfiltered_df.columns]
        if missing_cols:
            raise ValueError(
                f"{self.pair}: 数据缺少特征列: {missing_cols}. "
                f"期望 {len(training_feature_list)} 个特征"
            )

        # 只选择指定的特征列
        filtered_df = unfiltered_df[training_feature_list].copy()

        # 将 inf 替换为 NaN
        filtered_df = filtered_df.replace([np.inf, -np.inf], np.nan)

        # 检测 NaN 行
        drop_index = pd.isnull(filtered_df).any(axis=1)
        drop_index = drop_index.replace(True, 1).replace(False, 0).infer_objects(copy=False)

        if training_filter:
            # === 训练模式 ===
            if label_list:
                labels_df = unfiltered_df.filter(label_list, axis=1)
                labels_df = labels_df.replace([np.inf, -np.inf], np.nan)
                label_drop_index = labels_df.isnull().any(axis=1)
                label_drop_index = (
                    label_drop_index.replace(True, 1)
                    .replace(False, 0)
                    .infer_objects(copy=False)
                )
            else:
                labels_df = DataFrame()
                label_drop_index = pd.Series(0, index=drop_index.index)

            dates = unfiltered_df["date"] if "date" in unfiltered_df.columns else None

            filtered_df = filtered_df[
                (drop_index == 0) & (label_drop_index == 0)
            ]
            if label_list:
                labels_df = labels_df[
                    (drop_index == 0) & (label_drop_index == 0)
                ]
            if dates is not None:
                self.train_dates = dates[
                    (drop_index == 0) & (label_drop_index == 0)
                ]

            n_dropped = len(unfiltered_df) - len(filtered_df)
            if n_dropped > 0:
                logger.info(
                    f"{self.pair}: dropped {n_dropped} training points"
                    f" due to NaNs in populated dataset {len(unfiltered_df)}."
                )

            if len(filtered_df) == 0:
                raise ValueError(
                    f"{self.pair}: 所有训练数据都因 NaN/inf 被移除"
                )

            self.data["filter_drop_index_training"] = drop_index

        else:
            # === 预测模式 ===
            drop_index_pred = pd.isnull(filtered_df).any(axis=1)
            self.data["filter_drop_index_prediction"] = drop_index_pred
            filtered_df.fillna(0, inplace=True)
            drop_index_pred = ~drop_index_pred
            self.do_predict = np.array(
                drop_index_pred.replace(True, 1).replace(False, 0)
            )
            if (len(self.do_predict) - self.do_predict.sum()) > 0:
                logger.info(
                    "dropped %s of %s prediction data points due to NaNs.",
                    len(self.do_predict) - self.do_predict.sum(),
                    len(filtered_df),
                )

            labels_df = DataFrame()

        return filtered_df, labels_df

    def make_train_test_datasets(
        self,
        filtered_dataframe: DataFrame,
        labels: DataFrame,
    ) -> dict[str, Any]:
        """
        分割训练集和测试集 - 完全复刻 FreqAI

        参数:
            filtered_dataframe: 特征 DataFrame
            labels: 标签 DataFrame

        返回:
            data_dictionary
        """
        feat_dict = self.freqai_config.get("feature_parameters", {})

        if "shuffle" not in self.freqai_config.get("data_split_parameters", {}):
            self.freqai_config.setdefault("data_split_parameters", {})["shuffle"] = False

        weights: npt.ArrayLike
        if feat_dict.get("weight_factor", 0) > 0:
            weights = self.set_weights_higher_recent(len(filtered_dataframe))
        else:
            weights = np.ones(len(filtered_dataframe))

        split_params = self.freqai_config.get("data_split_parameters", {})
        test_size = split_params.get("test_size", 0.1)

        if test_size != 0:
            (
                train_features,
                test_features,
                train_labels,
                test_labels,
                train_weights,
                test_weights,
            ) = train_test_split(
                filtered_dataframe[: filtered_dataframe.shape[0]],
                labels,
                weights,
                **split_params,
            )
        else:
            test_labels = np.zeros(2)
            test_features = pd.DataFrame()
            test_weights = np.zeros(2)
            train_features = filtered_dataframe
            train_labels = labels
            train_weights = weights

        if feat_dict.get("shuffle_after_split", False):
            rint1 = random.randint(0, 100)
            rint2 = random.randint(0, 100)
            train_features = train_features.sample(
                frac=1, random_state=rint1
            ).reset_index(drop=True)
            train_labels = train_labels.sample(
                frac=1, random_state=rint1
            ).reset_index(drop=True)
            train_weights = (
                pd.DataFrame(train_weights)
                .sample(frac=1, random_state=rint1)
                .reset_index(drop=True)
                .to_numpy()[:, 0]
            )
            test_features = test_features.sample(
                frac=1, random_state=rint2
            ).reset_index(drop=True)
            test_labels = test_labels.sample(
                frac=1, random_state=rint2
            ).reset_index(drop=True)
            test_weights = (
                pd.DataFrame(test_weights)
                .sample(frac=1, random_state=rint2)
                .reset_index(drop=True)
                .to_numpy()[:, 0]
            )

        if feat_dict.get("reverse_train_test_order", False):
            return self.build_data_dictionary(
                test_features, train_features,
                test_labels, train_labels,
                test_weights, train_weights,
            )
        else:
            return self.build_data_dictionary(
                train_features, test_features,
                train_labels, test_labels,
                train_weights, test_weights,
            )

    def build_data_dictionary(
        self,
        train_df: DataFrame,
        test_df: DataFrame,
        train_labels: DataFrame,
        test_labels: DataFrame,
        train_weights: Any,
        test_weights: Any,
    ) -> dict[str, Any]:
        """构建数据字典"""
        self.data_dictionary = {
            "train_features": train_df,
            "test_features": test_df,
            "train_labels": train_labels,
            "test_labels": test_labels,
            "train_weights": train_weights,
            "test_weights": test_weights,
            "train_dates": self.train_dates,
        }
        return self.data_dictionary

    def set_weights_higher_recent(self, num_weights: int) -> npt.ArrayLike:
        """设置权重使近期数据在训练中权重更高"""
        wfactor = self.freqai_config.get("feature_parameters", {}).get("weight_factor", 0)
        weights = np.exp(-np.arange(num_weights) / (wfactor * num_weights))[::-1]
        return weights

    def fit_labels(self) -> None:
        """
        拟合标签的高斯分布 - 计算均值和标准差
        用于后续的标准化和反标准化
        """
        self.data["labels_mean"] = {}
        self.data["labels_std"] = {}

        train_labels = self.data_dictionary.get("train_labels", np.array([]))
        if len(train_labels) == 0:
            return

        if train_labels.ndim == 1:
            labels_to_use = self.label_list if self.label_list else ["&target"]
            label_name = labels_to_use[0] if labels_to_use else "&target"
            self.data["labels_mean"][label_name] = float(np.nanmean(train_labels))
            self.data["labels_std"][label_name] = float(np.nanstd(train_labels)) if len(train_labels) > 1 else 1.0
        else:
            labels_to_use = self.label_list if self.label_list else [f"&target_{i}" for i in range(train_labels.shape[1])]
            for i, label in enumerate(labels_to_use[:train_labels.shape[1]]):
                self.data["labels_mean"][label] = float(np.nanmean(train_labels[:, i]))
                self.data["labels_std"][label] = float(np.nanstd(train_labels[:, i])) if len(train_labels) > 1 else 1.0

        logger.debug(f"{self.pair}: 标签均值/标准差已计算")

    def split_timerange(
        self,
        start_date: str,
        end_date: str,
        train_period_days: int,
        backtest_period_days: int,
    ) -> tuple[list, list]:
        """
        将时间范围分割为多个训练和回测窗口

        参数:
            start_date: 开始日期 (格式: YYYY-MM-DD 或 YYYYMMDD)
            end_date: 结束日期 (格式: YYYY-MM-DD 或 YYYYMMDD)
            train_period_days: 训练窗口天数
            backtest_period_days: 回测窗口天数

        返回:
            (training_timeranges, backtesting_timeranges)
        """
        # 支持两种日期格式
        fmt = "%Y%m%d"
        if "-" in start_date:
            start = datetime.strptime(start_date, "%Y-%m-%d")
        else:
            start = datetime.strptime(start_date, fmt)

        if "-" in end_date:
            end = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            end = datetime.strptime(end_date, fmt)

        training_timeranges = []
        backtesting_timeranges = []

        current = start
        while current < end:
            train_start = current
            train_end = train_start + timedelta(days=train_period_days)
            bt_start = train_end
            bt_end = bt_start + timedelta(days=backtest_period_days)

            if bt_start >= end:
                break

            if bt_end > end:
                bt_end = end

            training_timeranges.append((train_start.strftime(fmt), train_end.strftime(fmt)))
            backtesting_timeranges.append((bt_start.strftime(fmt), bt_end.strftime(fmt)))

            current = bt_start

        return training_timeranges, backtesting_timeranges

    def convert_to_dataframe(
        self, array: npt.NDArray, label_list: list[str]
    ) -> DataFrame:
        """
        将 numpy 数组转换为 DataFrame

        参数:
            array: numpy 数组
            label_list: 列名列表

        返回:
            DataFrame
        """
        if array.ndim == 1:
            array = array.reshape(-1, 1)
        return DataFrame(array, columns=label_list)

    def remove_features_from_df(self, dataframe: DataFrame) -> DataFrame:
        """从 DataFrame 中移除特征列 (保留 %% 前缀列、date列和非特征列)"""
        logger.debug(f"remove_features_from_df: 输入列 = {list(dataframe.columns)}")
        to_keep = [
            col for col in dataframe.columns if not col.startswith("%") or col.startswith("%%")
        ]
        logger.debug(f"remove_features_from_df: 保留列 = {to_keep}")
        return dataframe[to_keep]

    def get_predictions_to_append(
        self,
        predictions: DataFrame,
        do_predict: npt.ArrayLike,
        dataframe_backtest: DataFrame,
    ) -> DataFrame:
        """
        构建要追加到历史预测的 DataFrame - 完全复刻 FreqAI
        """
        append_dict: dict[str, Any] = {}

        for label in predictions.columns:
            append_dict[label] = predictions[label]
            if predictions[label].dtype == object:
                continue
            if "labels_mean" in self.data and label in self.data["labels_mean"]:
                append_dict[f"{label}_mean"] = self.data["labels_mean"][label]
            if "labels_std" in self.data and label in self.data["labels_std"]:
                append_dict[f"{label}_std"] = self.data["labels_std"][label]

        for extra_col in self.data.get("extra_returns_per_train", {}):
            append_dict[f"{extra_col}"] = self.data["extra_returns_per_train"][extra_col]

        append_dict["do_predict"] = do_predict
        if self.freqai_config.get("feature_parameters", {}).get("DI_threshold", 0) > 0:
            append_dict["DI_values"] = self.DI_values

        append_df = DataFrame(append_dict)

        user_cols = [col for col in dataframe_backtest.columns if col.startswith("%%")]
        cols = ["date"] if "date" in dataframe_backtest.columns else []
        cols.extend(user_cols)

        dataframe_backtest.reset_index(drop=True, inplace=True)
        merged_df = pd.concat([dataframe_backtest[cols], append_df], axis=1)
        return merged_df

    def set_paths(self, pair: str, trained_timestamp: int | None = None) -> None:
        """设置数据路径"""
        self.full_path = self.get_full_models_path(self.config)
        self.data_path = Path(
            self.full_path / f"sub-train-{pair.split('/')[0]}_{trained_timestamp}"
        )

    def set_new_model_names(self, pair: str, timestamp_id: int) -> None:
        """设置新模型文件名"""
        coin = pair.split("/")[0]
        self.data_path = Path(
            self.full_path / f"sub-train-{coin}_{timestamp_id}"
        )
        self.model_filename = f"cb_{coin.lower()}_{timestamp_id}"

    def check_if_new_training_required(
        self, trained_timestamp: int
    ) -> tuple[bool, Any, Any]:
        """检查是否需要重新训练"""
        time = datetime.now(tz=UTC).timestamp()

        trained_timerange = {"startts": 0, "stopts": 0}
        data_load_timerange = {"startts": 0, "stopts": 0}

        feat_params = self.freqai_config.get("feature_parameters", {})
        timeframes = feat_params.get("include_timeframes", [])

        max_tf_seconds = 0
        for tf in timeframes:
            secs = self._timeframe_to_seconds(tf)
            if secs > max_tf_seconds:
                max_tf_seconds = secs

        max_period = self.config.get("startup_candle_count", 20) * 2
        additional_seconds = max_period * max_tf_seconds

        if trained_timestamp != 0:
            elapsed_time = (time - trained_timestamp) / SECONDS_IN_HOUR
            retrain = elapsed_time > self.freqai_config.get("live_retrain_hours", 0)
            if retrain:
                trained_timerange["startts"] = int(
                    time - self.freqai_config.get("train_period_days", 0) * SECONDS_IN_DAY
                )
                trained_timerange["stopts"] = int(time)
                data_load_timerange["startts"] = int(
                    time
                    - self.freqai_config.get("train_period_days", 0) * SECONDS_IN_DAY
                    - additional_seconds
                )
                data_load_timerange["stopts"] = int(time)
        else:
            trained_timerange["startts"] = int(
                time - self.freqai_config.get("train_period_days", 0) * SECONDS_IN_DAY
            )
            trained_timerange["stopts"] = int(time)
            data_load_timerange["startts"] = int(
                time
                - self.freqai_config.get("train_period_days", 0) * SECONDS_IN_DAY
                - additional_seconds
            )
            data_load_timerange["stopts"] = int(time)
            retrain = True

        return retrain, trained_timerange, data_load_timerange

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        """将时间帧字符串转换为秒数 (如 '1h' -> 3600)"""
        amount = int(timeframe[:-1]) if len(timeframe) > 1 else 1
        unit = timeframe[-1].lower()
        multipliers = {"m": 60, "h": 3600, "d": 86400, "w": 604800}
        return amount * multipliers.get(unit, 60)

    def check_if_model_expired(self, trained_timestamp: int) -> bool:
        """检查模型是否过期"""
        time = datetime.now(tz=UTC).timestamp()
        elapsed_time = (time - trained_timestamp) / 3600
        max_time = self.freqai_config.get("expiration_hours", 0)
        if max_time > 0:
            return elapsed_time > max_time
        else:
            return False

    def slice_dataframe(self, timerange: tuple, df: DataFrame) -> DataFrame:
        """
        按时间范围切片 DataFrame

        参数:
            timerange: (start_date_str, end_date_str) 元组
            df: 包含 'date' 列的 DataFrame
        """
        if "date" not in df.columns:
            return df

        start_str, end_str = timerange
        fmt = "%Y-%m-%d" if "-" in start_str else "%Y%m%d"
        start_dt = pd.Timestamp(datetime.strptime(start_str, fmt))
        end_dt = pd.Timestamp(datetime.strptime(end_str, fmt))

        if not self.live:
            df = df.loc[(df["date"] >= start_dt) & (df["date"] < end_dt), :]
        else:
            df = df.loc[df["date"] >= start_dt, :]

        return df

    def buffer_timerange(self, timerange: tuple) -> tuple:
        """
        为训练数据添加缓冲期，裁剪时间范围的首尾

        参数:
            timerange: (start_date_str, end_date_str) 元组

        返回:
            裁剪后的 (start_date_str, end_date_str)
        """
        buffer = self.freqai_config.get("feature_parameters", {}).get(
            "buffer_train_data_candles", 0
        )
        if not buffer:
            return timerange

        start_str, end_str = timerange
        fmt = "%Y-%m-%d" if "-" in start_str else "%Y%m%d"
        start_dt = datetime.strptime(start_str, fmt)
        end_dt = datetime.strptime(end_str, fmt)

        tf = self.config.get("timeframe", "1d")
        tf_seconds = self._timeframe_to_seconds(tf)
        buffer_seconds = buffer * tf_seconds

        start_dt = start_dt + timedelta(seconds=buffer_seconds)
        end_dt = end_dt - timedelta(seconds=buffer_seconds)

        out_fmt = "%Y-%m-%d" if "-" in start_str else "%Y%m%d"
        return (start_dt.strftime(out_fmt), end_dt.strftime(out_fmt))

    def remove_special_chars_from_feature_names(
        self, dataframe: DataFrame
    ) -> DataFrame:
        """移除特征名中的特殊字符"""
        spec_chars = [":"]
        for c in spec_chars:
            dataframe.columns = dataframe.columns.str.replace(c, "")
        return dataframe

    def get_unique_classes_from_labels(self, dataframe: DataFrame) -> None:
        """从标签列中获取唯一分类"""
        self.find_labels(dataframe)
        for key in self.label_list:
            if dataframe[key].dtype == object:
                self.unique_classes[key] = dataframe[key].dropna().unique()

        if self.unique_classes:
            for label in self.unique_classes:
                self.unique_class_list += list(self.unique_classes[label])

    def append_predictions(self, append_df: DataFrame) -> None:
        """追加回测预测到完整 DataFrame"""
        if self.full_df.empty:
            self.full_df = append_df
        else:
            self.full_df = pd.concat(
                [self.full_df, append_df], axis=0, ignore_index=True
            )

    def fill_predictions(self, dataframe: DataFrame) -> None:
        """填充预测结果，回填缺失值以匹配原始 DataFrame 大小"""
        to_keep = [
            col for col in dataframe.columns
            if not col.startswith("&") and not col.startswith("%%")
        ]
        self.return_dataframe = pd.merge(
            dataframe[to_keep], self.full_df, how="left", on="date"
        )
        self.return_dataframe[self.full_df.columns] = self.return_dataframe[
            self.full_df.columns
        ].fillna(value=0)
        self.full_df = DataFrame()

    def check_if_backtest_prediction_is_valid(
        self, len_backtest_df: int
    ) -> bool:
        """检查回测预测文件是否有效"""
        path_to_predictionfile = Path(
            self.full_path
            / self.backtest_predictions_folder
            / f"{self.model_filename}_prediction.feather"
        )
        self.backtesting_results_path = path_to_predictionfile

        file_exists = path_to_predictionfile.is_file()

        if file_exists:
            append_df = self.get_backtesting_prediction()
            if len(append_df) == len_backtest_df and "date" in append_df:
                logger.info(
                    f"Found backtesting prediction file at {path_to_predictionfile}"
                )
                return True
            else:
                logger.info(
                    "A new backtesting prediction file is required. "
                    "(Number of predictions is different from dataframe length or "
                    "old prediction file version)."
                )
                return False
        else:
            logger.info(
                f"Could not find backtesting prediction file at {path_to_predictionfile}"
            )
            return False

    def get_backtesting_prediction(self) -> DataFrame:
        """从 feather 文件读取回测预测"""
        append_df = pd.read_feather(self.backtesting_results_path)
        return append_df

    def save_backtesting_prediction(self, append_df: DataFrame) -> None:
        """保存回测预测到 feather 文件"""
        full_predictions_folder = Path(
            self.full_path / self.backtest_predictions_folder
        )
        if not full_predictions_folder.is_dir():
            full_predictions_folder.mkdir(parents=True, exist_ok=True)

        append_df.to_feather(self.backtesting_results_path)
