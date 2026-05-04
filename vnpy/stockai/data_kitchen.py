"""StockAI 数据厨房 - 完全复刻 FreqAI FreqaiDataKitchen"""

import logging
from pathlib import Path
from typing import Any, Optional

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


class StockaiDataKitchen:
    """
    单只股票数据管理单元 - 完全复刻 FreqAI FreqaiDataKitchen

    职责:
    - 识别特征列 (%-前缀) 和标签列 (&-前缀)
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

        # 训练/测试时间段
        self.train_period: tuple[str, str] = ("", "")
        self.test_period: tuple[str, str] = ("", "")

        # 模型文件名
        self.model_filename: str = ""

        # 额外数据存储
        self.data: dict[str, Any] = {"extra_returns_per_train": {}}

        logger.debug(f"数据厨房初始化: {pair}")

    def find_features(self, df: pl.DataFrame) -> None:
        """
        识别特征列 - 列名以 %- 开头

        参数:
            df: 已计算特征的 DataFrame
        """
        self.training_features_list = [c for c in df.columns if c.startswith("%-")]
        logger.info(f"{self.pair}: 识别到 {len(self.training_features_list)} 个特征")

    def find_labels(self, df: pl.DataFrame) -> None:
        """
        识别标签列 - 列名以 & 开头

        参数:
            df: 已计算标签的 DataFrame
        """
        self.label_list = [c for c in df.columns if c.startswith("&")]
        logger.info(f"{self.pair}: 识别到 {len(self.label_list)} 个标签")

    def filter_features(
        self,
        df: pl.DataFrame,
        training_filter: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        过滤特征和标签

        参数:
            df: 输入 DataFrame (必须已包含特征和标签)
            training_filter: 是否用于训练过滤 (保留用于 future 扩展)

        返回:
            (features_df, labels_df)
        """
        if not self.training_features_list:
            raise ValueError("未找到特征列（需要%-前缀），请先调用 find_features()")
        if not self.label_list:
            raise ValueError("未找到标签列（需要&-前缀），请先调用 find_labels()")

        # 提取特征 (包括 datetime 以便对齐)
        if "datetime" in df.columns:
            cols_to_select = ["datetime"] + self.training_features_list
        else:
            cols_to_select = self.training_features_list
        features_df = df.select(cols_to_select)

        # 提取标签 (取第一个标签列用于训练)
        if len(self.label_list) == 1:
            labels_df = df.select(self.label_list)
        else:
            # 多标签情况，取第一个
            labels_df = df.select([self.label_list[0]])
            logger.warning(f"{self.pair}: 多个标签列，仅使用 {self.label_list[0]}")

        # 处理缺失值
        features_df = features_df.fill_null(0.0)
        labels_df = labels_df.fill_null(0.0)

        # 移除包含 NaN/inf 的行
        features_np = features_df.to_numpy()
        labels_np = labels_df.to_numpy().ravel()

        valid_mask = np.isfinite(features_np).all(axis=1) & np.isfinite(labels_np)
        n_invalid = len(valid_mask) - valid_mask.sum()
        if n_invalid > 0:
            logger.warning(f"{self.pair}: 移除 {n_invalid} 行包含无效值的样本")

        features_df = features_df.filter(pl.Series(valid_mask))
        labels_df = labels_df.filter(pl.Series(valid_mask))

        return features_df, labels_df

    def make_train_test_datasets(
        self,
        features: pl.DataFrame,
        labels: pl.DataFrame,
    ) -> dict[str, Any]:
        """
        分割训练集和测试集

        参数:
            features: 特征 DataFrame
            labels: 标签 DataFrame

        返回:
            data_dictionary 包含:
                - train_features: 训练特征 (numpy)
                - train_labels: 训练标签 (numpy)
                - test_features: 测试特征 (numpy)
                - test_labels: 测试标签 (numpy)
        """
        # 转换为 numpy
        X = features.to_numpy()
        y = labels.to_numpy().ravel() if labels.shape[1] == 1 else labels.to_numpy()

        # 分割参数
        test_size = self.config.get("data_split_parameters", {}).get("test_size", 0.2)
        shuffle = self.config.get("data_split_parameters", {}).get("shuffle", False)

        # 分割数据
        if test_size > 0:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, shuffle=shuffle
            )
        else:
            X_train, y_train = X, y
            X_test, y_test = np.array([]).reshape(0, X.shape[1]), np.array([])

        self.data_dictionary = {
            "train_features": X_train,
            "train_labels": y_train,
            "test_features": X_test,
            "test_labels": y_test,
        }

        logger.info(
            f"{self.pair}: 训练集 {len(X_train)} 样本，测试集 {len(X_test)} 样本"
        )

        return self.data_dictionary

    def set_paths(self, pair: str, timestamp: int) -> None:
        """设置数据路径"""
        safe_pair = pair.replace(".", "_")
        self.model_filename = f"sub-train-{safe_pair}_{timestamp}"
        self.data_path = Path(self.config.get("path", "./stockai_data")) / self.model_filename
        self.data_path.mkdir(parents=True, exist_ok=True)

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
        features_df, labels_df = self.filter_features(df)

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
