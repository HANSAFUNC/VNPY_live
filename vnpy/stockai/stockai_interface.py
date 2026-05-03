"""StockAI 模型接口基类"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import polars as pl

from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen

logger = logging.getLogger(__name__)


class IStockaiModel(ABC):
    """
    所有StockAI模型的抽象基类

    对应 FreqAI 的 IFreqaiModel 类

    职责:
    - 定义训练和预测的抽象接口
    - 管理全局 DataDrawer（持久化存储）
    - 创建 DataKitchen（临时数据管理）
    """

    def __init__(self, config: dict, lab: Any):
        """
        初始化模型接口

        参数:
            config: 配置字典
            lab: AlphaLabV2 实例
        """
        self.config = config
        self.lab = lab

        # 设置路径
        self.full_path = Path(config.get("path", "./stockai_data"))
        self.full_path.mkdir(parents=True, exist_ok=True)

        # 初始化全局数据抽屉
        self.dd = StockaiDataDrawer(self.full_path, config)

        # 当前数据厨房（临时）
        self.dk: Optional[StockaiDataKitchen] = None

        # 模型引用
        self.model: Optional[Any] = None

        # 特征参数
        self.ft_params = config.get("feature_parameters", {})

        logger.info(f"模型接口初始化完成，路径: {self.full_path}")

    def get_data_kitchen(self, pair: str) -> StockaiDataKitchen:
        """获取或创建数据厨房"""
        return StockaiDataKitchen(self.config, pair, self.lab)

    @abstractmethod
    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        训练模型（子类必须实现）

        参数:
            df: 训练数据
            pair: 股票代码
            dk: 数据厨房

        返回:
            训练好的模型对象
        """
        pass

    @abstractmethod
    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """
        预测（子类必须实现）

        参数:
            df: 输入数据
            dk: 数据厨房

        返回:
            预测结果DataFrame
        """
        pass

    def start_training(
        self,
        pair: str,
        start: str,
        end: str,
    ) -> Any:
        """
        高层训练入口

        参数:
            pair: 股票代码
            start: 测试期开始
            end: 测试期结束

        返回:
            训练好的模型
        """
        # 创建数据厨房
        dk = self.get_data_kitchen(pair)
        self.dk = dk

        # 加载数据
        df = dk.load_data(
            start=start,
            end=end,
            train_period_days=self.config.get("train_period_days", 300),
        )

        # 训练
        model = self.train(df, pair, dk)
        self.model = model

        return model

    def start_prediction(
        self,
        pair: str,
        start: str,
        end: str,
    ) -> pl.DataFrame:
        """
        高层预测入口

        参数:
            pair: 股票代码
            start: 预测期开始
            end: 预测期结束

        返回:
            预测结果
        """
        # 创建数据厨房
        dk = self.get_data_kitchen(pair)
        self.dk = dk

        # 加载数据
        df = dk.load_data(
            start=start,
            end=end,
            train_period_days=0,  # 预测不需要训练数据
        )

        # 预测
        predictions = self.predict(df, dk)

        # 保存到历史
        self.dd.append_predictions(pair, predictions)

        return predictions
