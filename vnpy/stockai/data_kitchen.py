"""StockAI 数据厨房 - 单只股票数据管理"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Type

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


class StockaiDataKitchen:
    """
    单只股票数据管理单元

    职责:
    - 加载和管理一只股票的数据
    - 过滤特征列（%-前缀）和标签列（&-前缀）
    - 分割训练集和测试集
    - 管理特征管道和标签管道

    对应 FreqAI 的 FreqaiDataKitchen 类
    """

    def __init__(self, config: dict, pair: str, lab: Any):
        """
        初始化数据厨房

        参数:
            config: 配置字典
            pair: 股票代码
            lab: AlphaLabV2 实例
        """
        self.config = config
        self.pair = pair
        self.lab = lab

        # 路径
        self.data_path = Path()

        # 数据存储
        self.data_dictionary: dict[str, Any] = {}
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

    def load_data(
        self,
        start: str,
        end: str,
        train_period_days: int = 300,
    ) -> pl.DataFrame:
        """
        从 lab 加载数据

        参数:
            start: 测试期开始日期
            end: 测试期结束日期
            train_period_days: 训练期天数（从start往前推）

        返回:
            加载的DataFrame
        """
        # 计算时间段
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        train_start_dt = start_dt - timedelta(days=train_period_days)
        train_start = train_start_dt.strftime("%Y-%m-%d")

        self.train_period = (train_start, start)
        self.test_period = (start, end)

        # 从 lab 加载数据
        df = self.lab.load_bars_df(
            symbols=[self.pair],
            interval=self.lab.config.get("interval", "d"),
            start=train_start,
            end=end,
        )

        if df is None or len(df) == 0:
            raise ValueError(f"{self.pair}: 未能加载数据")

        self.full_df = df
        logger.info(f"{self.pair}: 已加载 {len(df)} 行数据")

        return df

    def filter_features(
        self,
        df: pl.DataFrame,
        training_filter: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        过滤特征和标签

        特征列: %-前缀
        标签列: &-前缀

        参数:
            df: 输入DataFrame
            training_filter: 是否用于训练过滤

        返回:
            (特征DataFrame, 标签DataFrame)
        """
        # 识别列
        feature_cols = [c for c in df.columns if c.startswith("%-")]
        label_cols = [c for c in df.columns if c.startswith("&")]

        if not feature_cols:
            raise ValueError("未找到特征列（需要%-前缀）")
        if not label_cols:
            raise ValueError("未找到标签列（需要&-前缀）")

        self.training_features_list = feature_cols
        self.label_list = label_cols

        # 提取数据
        features_df = df.select(feature_cols)
        labels_df = df.select(label_cols)

        # 处理缺失值
        features_df = features_df.fill_null(0.0)
        labels_df = labels_df.fill_null(0.0)

        logger.info(f"{self.pair}: 特征 {len(feature_cols)} 列，标签 {len(label_cols)} 列")

        return features_df, labels_df

    def make_train_test_datasets(
        self,
        features: pl.DataFrame,
        labels: pl.DataFrame,
    ) -> dict[str, Any]:
        """
        分割训练集和测试集

        参数:
            features: 特征DataFrame
            labels: 标签DataFrame

        返回:
            包含训练/测试数据的字典
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
            X_test, y_test = np.array([]), np.array([])

        self.data_dictionary = {
            "train_features": X_train,
            "train_labels": y_train,
            "test_features": X_test,
            "test_labels": y_test,
        }

        logger.info(f"{self.pair}: 训练集 {len(X_train)}，测试集 {len(X_test)}")

        return self.data_dictionary
