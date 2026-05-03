"""StockAI 回归模型基类"""

import logging
from abc import abstractmethod
from typing import Any

import joblib
import numpy as np
import polars as pl
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.pipeline import Pipeline

from ..data_kitchen import StockaiDataKitchen
from ..stockai_interface import IStockaiModel
from ..utils import get_timestamp

logger = logging.getLogger(__name__)


class BaseRegressionModel(IStockaiModel):
    """
    回归模型基类

    实现了通用的训练和预测流程
    子类只需要实现 fit() 方法
    """

    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        通用训练流程

        步骤:
        1. 过滤特征和标签
        2. 分割训练/测试集
        3. 定义管道
        4. 拟合管道
        5. 转换数据
        6. 训练模型
        7. 保存模型
        """
        logger.info(f"开始训练: {pair}")

        # 1. 过滤特征
        features, labels = dk.filter_features(df, training_filter=True)

        # 2. 分割数据
        data_dict = dk.make_train_test_datasets(features, labels)

        # 3. 定义管道
        dk.feature_pipeline = self.define_feature_pipeline()
        dk.label_pipeline = self.define_label_pipeline()

        # 4. 拟合管道
        dk.feature_pipeline.fit(data_dict["train_features"])
        dk.label_pipeline.fit(data_dict["train_labels"].reshape(-1, 1))

        # 5. 转换数据
        X_train = dk.feature_pipeline.transform(data_dict["train_features"])
        y_train = dk.label_pipeline.transform(
            data_dict["train_labels"].reshape(-1, 1)
        ).ravel()

        data_dict["train_features"] = X_train
        data_dict["train_labels"] = y_train

        if len(data_dict["test_features"]) > 0:
            X_test = dk.feature_pipeline.transform(data_dict["test_features"])
            y_test = dk.label_pipeline.transform(
                data_dict["test_labels"].reshape(-1, 1)
            ).ravel()
            data_dict["test_features"] = X_test
            data_dict["test_labels"] = y_test

        # 6. 训练模型
        logger.info(f"训练: {len(X_train)} 样本, {X_train.shape[1]} 特征")
        model = self.fit(data_dict, dk)

        # 7. 保存模型
        timestamp = get_timestamp()
        self.dd.save_model(pair, model, timestamp)
        self._save_pipelines(pair, timestamp, dk)

        logger.info(f"训练完成: {pair}")

        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """
        通用预测流程

        步骤:
        1. 过滤特征
        2. 加载管道和模型
        3. 转换特征
        4. 预测
        5. 反向转换
        6. 构建结果
        """
        pair = dk.pair

        # 1. 过滤特征
        features, _ = dk.filter_features(df)

        # 2. 加载
        self._load_pipelines(pair, dk)
        model = self.dd.load_model(pair)

        # 3. 转换
        X = dk.feature_pipeline.transform(features.to_numpy())

        # 4. 预测
        predictions = model.predict(X)

        # 5. 反向转换
        predictions = dk.label_pipeline.inverse_transform(
            predictions.reshape(-1, 1)
        ).ravel()

        # 6. 构建结果
        result = pl.DataFrame({
            "datetime": df["datetime"],
            "pair": pair,
            "prediction": predictions,
        })

        logger.info(f"预测完成: {pair}, {len(result)} 样本")

        return result

    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        训练模型（子类必须实现）

        参数:
            data_dictionary: 包含训练/测试数据的字典
            dk: 数据厨房

        返回:
            训练好的模型
        """
        pass

    def define_feature_pipeline(self) -> Pipeline:
        """定义特征处理管道（可覆盖）"""
        return Pipeline([
            ("scaler", StandardScaler()),
        ])

    def define_label_pipeline(self) -> Pipeline:
        """定义标签处理管道（可覆盖）"""
        return Pipeline([
            ("scaler", MinMaxScaler(feature_range=(-1, 1))),
        ])

    def _save_pipelines(
        self,
        pair: str,
        timestamp: int,
        dk: StockaiDataKitchen,
    ) -> None:
        """保存管道"""
        filename = self.dd._generate_model_filename(pair, timestamp)
        model_path = self.dd.full_path / filename

        if dk.feature_pipeline:
            joblib.dump(dk.feature_pipeline, model_path / "feature_pipeline.pkl")
        if dk.label_pipeline:
            joblib.dump(dk.label_pipeline, model_path / "label_pipeline.pkl")

    def _load_pipelines(self, pair: str, dk: StockaiDataKitchen) -> None:
        """加载管道"""
        filename = self.dd.pair_dict[pair]["model_filename"]
        model_path = self.dd.full_path / filename

        fp_path = model_path / "feature_pipeline.pkl"
        lp_path = model_path / "label_pipeline.pkl"

        if fp_path.exists():
            dk.feature_pipeline = joblib.load(fp_path)
        if lp_path.exists():
            dk.label_pipeline = joblib.load(lp_path)
