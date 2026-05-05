"""StockAI 数据厨房 - 完全复刻 FreqAI FreqaiDataKitchen"""

from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

from vnpy.alpha.logger import logger


class StockaiDataKitchen:
    """
    单只股票数据管理单元 - 完全复刻 FreqAI FreqaiDataKitchen

    职责:
    - 识别特征列 (包含 %- 前缀)
    - 识别标签列 (包含 & 前缀)
    - 训练/测试数据分割
    - 特征/标签管道管理
    - 数据字典管理 (data_dictionary)

    注意: 数据加载由策略层完成，本类只负责管理已加载的数据
    """

    def __init__(self, config: dict, pair: str, lab: Any):
        """
        初始化数据厨房

        参数:
            config: 配置字典
            pair: 股票代码
            lab: AlphaLabV2 实例 (仅用于获取路径等元信息)
        """
        self.config = config
        self.pair = pair
        self.lab = lab

        # 路径
        self.data_path: Path = Path()

        # 数据字典 - 存储训练/测试数据
        self.data_dictionary: dict[str, Any] = {}

        # 完整数据 (由外部传入)
        self.full_df: pl.DataFrame = pl.DataFrame()

        # 管道对象
        self.feature_pipeline: Optional[Any] = None
        self.label_pipeline: Optional[Any] = None

        # 特征和标签列名列表
        self.training_features_list: list[str] = []
        self.label_list: list[str] = []

        # do_predict 数组 - 标记哪些预测是有效的
        self.do_predict: np.ndarray = np.array([])

        # 训练/测试时间段
        self.train_period: tuple[str, str] = ("", "")
        self.test_period: tuple[str, str] = ("", "")

        # 模型文件名
        self.model_filename: str = ""

        # 分类模型支持
        self.unique_classes: dict[str, list] = {}
        self.unique_class_list: list = []

        # 额外数据存储
        self.data: dict[str, Any] = {"extra_returns_per_train": {}}

        # 训练日期
        self.train_dates: pl.Series = pl.Series()

        logger.debug(f"数据厨房初始化: {pair}")

    def find_features(self, df: pl.DataFrame) -> None:
        """
        识别特征列 - 列名包含 % (FreqAI 标准)

        参数:
            df: 已计算特征的 DataFrame
        """
        # FreqAI 使用 "%" in c 而不是 startswith
        column_names = df.columns
        features = [c for c in column_names if "%" in c]

        if not features:
            raise ValueError(f"{self.pair}: 未找到特征列（需要包含 % 的列名）")

        self.training_features_list = features
        logger.info(f"{self.pair}: 识别到 {len(features)} 个特征")

    def find_labels(self, df: pl.DataFrame) -> None:
        """
        识别标签列 - 列名包含 & (FreqAI 标准)

        参数:
            df: 已计算标签的 DataFrame
        """
        column_names = df.columns
        labels = [c for c in column_names if "&" in c]

        self.label_list = labels
        logger.info(f"{self.pair}: 识别到 {len(labels)} 个标签")

    def filter_features(
        self,
        unfiltered_df: pl.DataFrame,
        training_feature_list: list[str],
        label_list: Optional[list[str]] = None,
        training_filter: bool = True,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        过滤特征和标签 - 完全复刻 FreqAI filter_features

        训练时: 删除包含 NaN/inf 的行
        预测时: 用 0 填充 NaN/inf，并设置 do_predict 标记无效行

        参数:
            unfiltered_df: 完整 DataFrame
            training_feature_list: 特征列名列表 (从 metadata 加载或重新识别)
            label_list: 标签列名列表
            training_filter: True=训练模式, False=预测模式

        返回:
            (filtered_df, labels_df) - 训练时 labels_df 包含数据，预测时为空 DataFrame
        """
        # 1. 检查必需的列是否存在
        missing_cols = [c for c in training_feature_list if c not in unfiltered_df.columns]
        if missing_cols:
            raise ValueError(
                f"{self.pair}: 预测数据缺少特征列: {missing_cols}. "
                f"期望 {len(training_feature_list)} 个特征，"
                f"实际列数: {len(unfiltered_df.columns)}"
            )

        # 2. 只选择指定的特征列
        filtered_df = unfiltered_df.select(training_feature_list)

        logger.debug(f"{self.pair}: filter_features - 选择 {len(training_feature_list)} 个特征, "
                     f"training_filter={training_filter}")

        # 3. 将 inf 替换为 NaN (FreqAI 风格)
        filtered_df = filtered_df.with_columns([
            pl.when(pl.col(c).is_infinite())
            .then(None)
            .otherwise(pl.col(c))
            .alias(c)
            for c in filtered_df.columns
        ])

        # 4. 检测 NaN 行 (FreqAI 风格: pd.isnull(filtered_df).any(axis=1))
        nan_mask = filtered_df.select([
            pl.col(c).is_null().alias(f"{c}_nan")
            for c in filtered_df.columns
        ])
        drop_index = nan_mask.to_numpy().any(axis=1)  # 哪些行有 NaN

        if training_filter:
            # === 训练模式 ===
            # 同时检查标签的 NaN
            if label_list:
                labels_df = unfiltered_df.select(label_list)
                # 同样将 inf 替换为 NaN
                labels_df = labels_df.with_columns([
                    pl.when(pl.col(c).is_infinite())
                    .then(None)
                    .otherwise(pl.col(c))
                    .alias(c)
                    for c in labels_df.columns
                ])
                label_nan_mask = labels_df.select([
                    pl.col(c).is_null().alias(f"{c}_nan")
                    for c in labels_df.columns
                ])
                drop_index_labels = label_nan_mask.to_numpy().any(axis=1)
                # 合并
                combined_drop = drop_index | drop_index_labels
            else:
                labels_df = pl.DataFrame()
                combined_drop = drop_index

            # 记录训练日期（可选，用于调试）
            if "datetime" in unfiltered_df.columns:
                try:
                    self.train_dates = unfiltered_df.filter(~pl.Series(combined_drop))["datetime"]
                except Exception:
                    self.train_dates = pl.Series()

            # 过滤 DataFrame (保留 combined_drop == False 的行)
            keep_mask = ~pl.Series(combined_drop)
            filtered_df = filtered_df.filter(keep_mask)
            if label_list:
                labels_df = labels_df.filter(keep_mask)

            n_dropped = drop_index.sum()
            if n_dropped > 0:
                logger.info(
                    f"{self.pair}: 训练时移除了 {n_dropped} 行包含 NaN/inf 的数据 "
                    f"(原始 {len(unfiltered_df)} 行)"
                )

            if len(filtered_df) == 0:
                raise ValueError(
                    f"{self.pair}: 所有训练数据都因 NaN/inf 被移除。请检查特征计算或增加训练数据。"
                )

            self.data["filter_drop_index_training"] = combined_drop.astype(int)

        else:
            # === 预测模式 ===
            # 用 0 填充 NaN/inf (Polars: fill_null 处理 null，nan 需要另外处理)
            filtered_df = filtered_df.with_columns([
                pl.col(c).fill_null(0.0).fill_nan(0.0).alias(c)
                for c in filtered_df.columns
            ])

            # 设置 do_predict - 标记哪些行原本是有效的 (无 NaN)
            self.do_predict = (~drop_index).astype(int)

            n_invalid = drop_index.sum()
            if n_invalid > 0:
                logger.info(
                    f"{self.pair}: 预测时填充了 {n_invalid} 行 NaN/inf 数据 (共 {len(filtered_df)} 行)"
                )

            self.data["filter_drop_index_prediction"] = drop_index.astype(int)
            # 预测时返回空 DataFrame 作为 labels
            labels_df = pl.DataFrame()

        return filtered_df, labels_df

    def set_weights_higher_recent(self, num_weights: int) -> np.ndarray:
        """计算指数衰减权重，使近期样本权重更高"""
        weight_factor = self.config.get("feature_parameters", {}).get("weight_factor", 1.0)
        indices = np.arange(num_weights)
        weights = np.exp(-indices / (weight_factor * num_weights))[::-1]
        return weights

    def make_train_test_datasets(
        self,
        features: pl.DataFrame,
        labels: pl.DataFrame,
        use_weights: bool = False,
    ) -> dict[str, Any]:
        """
        分割训练集和测试集 - 复刻 FreqAI make_train_test_datasets

        参数:
            features: 特征 DataFrame (已过滤 NaN)
            labels: 标签 DataFrame (已过滤 NaN)
            use_weights: 是否计算样本权重

        返回:
            data_dictionary 包含:
                - train_features: 训练特征 (numpy)
                - train_labels: 训练标签 (numpy)
                - test_features: 测试特征 (numpy)
                - test_labels: 测试标签 (numpy)
                - train_weights: 训练权重 (numpy, 仅 use_weights=True)
                - test_weights: 测试权重 (numpy, 仅 use_weights=True)
        """
        # 转换为 numpy
        X = features.to_numpy()
        y = labels.to_numpy().ravel() if labels.shape[1] == 1 else labels.to_numpy()

        # 最终检查 - 确保没有 NaN/inf
        if np.isnan(X).any() or np.isinf(X).any():
            logger.warning(f"{self.pair}: 特征中仍有 NaN/inf，将被替换为 0")
            X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        if np.isnan(y).any() or np.isinf(y).any():
            logger.warning(f"{self.pair}: 标签中仍有 NaN/inf，将被替换为 0")
            y = np.nan_to_num(y, nan=0.0, posinf=0.0, neginf=0.0)

        # 计算权重
        if use_weights:
            weights = self.set_weights_higher_recent(len(X))
        else:
            weights = None

        # 分割参数
        split_params = self.config.get("data_split_parameters", {})
        test_size = split_params.get("test_size", 0.2)
        shuffle = split_params.get("shuffle", False)

        # 分割数据
        if test_size > 0:
            if weights is not None:
                X_train, X_test, y_train, y_test, w_train, w_test = train_test_split(
                    X, y, weights, test_size=test_size, shuffle=shuffle
                )
            else:
                X_train, X_test, y_train, y_test = train_test_split(
                    X, y, test_size=test_size, shuffle=shuffle
                )
        else:
            X_train, y_train = X, y
            X_test, y_test = np.array([]).reshape(0, X.shape[1]), np.array([])
            if weights is not None:
                w_train, w_test = weights, np.array([])

        # 最终检查训练和测试集
        if np.isnan(X_train).any() or np.isinf(X_train).any():
            raise ValueError(f"{self.pair}: 训练特征中仍有 NaN/inf")
        if np.isnan(y_train).any() or np.isinf(y_train).any():
            raise ValueError(f"{self.pair}: 训练标签中仍有 NaN/inf")

        self.data_dictionary = {
            "train_features": X_train,
            "train_labels": y_train,
            "test_features": X_test,
            "test_labels": y_test,
        }

        if weights is not None:
            self.data_dictionary["train_weights"] = w_train
            self.data_dictionary["test_weights"] = w_test

        logger.info(
            f"{self.pair}: 训练集 {len(X_train)} 样本，测试集 {len(X_test)} 样本"
        )

        return self.data_dictionary

    def fit_labels(self) -> None:
        """
        拟合标签的高斯分布 - 计算均值和标准差
        用于后续的标准化和反标准化
        """
        self.data["labels_mean"] = {}
        self.data["labels_std"] = {}

        # 获取训练标签 (numpy 数组)
        train_labels = self.data_dictionary.get("train_labels", np.array([]))
        if len(train_labels) == 0:
            return

        # 处理不同维度的标签
        if train_labels.ndim == 1:
            # 单标签情况
            labels_to_use = self.label_list if self.label_list else ["&target"]
            label_name = labels_to_use[0] if labels_to_use else "&target"
            self.data["labels_mean"][label_name] = float(np.nanmean(train_labels))
            self.data["labels_std"][label_name] = float(np.nanstd(train_labels)) if len(train_labels) > 1 else 1.0
        else:
            # 多标签情况
            labels_to_use = self.label_list if self.label_list else [f"&target_{i}" for i in range(train_labels.shape[1])]
            for i, label in enumerate(labels_to_use[:train_labels.shape[1]]):
                self.data["labels_mean"][label] = float(np.nanmean(train_labels[:, i]))
                self.data["labels_std"][label] = float(np.nanstd(train_labels[:, i])) if len(train_labels) > 1 else 1.0

        logger.debug(f"{self.pair}: 标签均值/标准差已计算: {self.data['labels_mean']}")

    def set_paths(self, pair: str, timestamp: int) -> None:
        """设置数据路径"""
        safe_pair = pair.replace(".", "_")
        self.model_filename = f"sub-train-{safe_pair}_{timestamp}"
        self.data_path = Path(self.config.get("path", "./stockai_data")) / self.model_filename
        self.data_path.mkdir(parents=True, exist_ok=True)

    def split_timerange(
        self,
        start_date: str,
        end_date: str,
        train_period_days: int,
        backtest_period_days: int,
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """
        将完整时间范围分割为多个训练和回测窗口 (滑动窗口)

        参数:
            start_date: 起始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)
            train_period_days: 训练窗口天数
            backtest_period_days: 回测窗口天数

        返回:
            (training_ranges, backtesting_ranges) - 每个元素为 (start, end) 日期字符串
        """
        fmt = "%Y-%m-%d"
        start = datetime.strptime(start_date, fmt)
        end = datetime.strptime(end_date, fmt)

        training_ranges: list[tuple[str, str]] = []
        backtesting_ranges: list[tuple[str, str]] = []

        # 计算滑动步长：每次向前滑动 backtest_period_days
        step_days = backtest_period_days

        current_train_start = start
        while True:
            train_end = current_train_start + timedelta(days=train_period_days)
            bt_start = train_end
            bt_end = bt_start + timedelta(days=backtest_period_days)

            # 如果预测期超出数据范围，结束
            if bt_start >= end:
                break

            # 如果预测期部分超出，仍然保留（截断到 end）
            if bt_end > end:
                bt_end = end

            training_ranges.append((current_train_start.strftime(fmt), train_end.strftime(fmt)))
            backtesting_ranges.append((bt_start.strftime(fmt), bt_end.strftime(fmt)))

            # 滑动到下一个窗口
            current_train_start = current_train_start + timedelta(days=step_days)

        return training_ranges, backtesting_ranges

    def build_data_dictionary(
        self,
        df: pl.DataFrame,
        dk: "StockaiDataKitchen",
    ) -> dict[str, Any]:
        """
        构建数据字典 - 用于训练

        参数:
            df: 已包含特征和标签的 DataFrame
            dk: 数据厨房实例

        返回:
            data_dictionary
        """
        # 确保已识别特征和标签
        if not self.training_features_list:
            self.find_features(df)
        if not self.label_list:
            self.find_labels(df)

        # 过滤特征和标签
        features_df, labels_df = self.filter_features(
            df,
            training_feature_list=self.training_features_list,
            label_list=self.label_list,
            training_filter=True,
        )

        # 分割训练/测试集
        data_dict = self.make_train_test_datasets(features_df, labels_df)

        return data_dict

    def get_predictions_to_append(
        self,
        pred_df: pl.DataFrame,
        do_preds: np.ndarray,
        original_df: pl.DataFrame,
    ) -> pl.DataFrame:
        """
        构建要追加到历史预测的 DataFrame

        参数:
            pred_df: 预测结果
            do_preds: 预测有效性标记
            original_df: 原始数据

        返回:
            格式化后的预测 DataFrame
        """
        result = pred_df.with_columns([
            pl.Series("do_predict", do_preds),
            pl.lit(self.pair).alias("pair"),
        ])
        return result

    def append_predictions(self, predictions: pl.DataFrame) -> None:
        """追加预测到内部存储 (用于回测时累积预测)"""
        if "predictions" not in self.data:
            self.data["predictions"] = []
        self.data["predictions"].append(predictions)

    def get_full_predictions(self) -> Optional[pl.DataFrame]:
        """获取累积的所有预测"""
        if "predictions" not in self.data or not self.data["predictions"]:
            return None
        return pl.concat(self.data["predictions"])
