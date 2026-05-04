"""StockAI 回归模型基类 - 完全复刻 FreqAI BaseRegressionModel"""

import logging
from abc import abstractmethod
from typing import Any, Tuple

import joblib
import numpy as np
import polars as pl
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.feature_selection import VarianceThreshold

from ..data_kitchen import StockaiDataKitchen
from ..stockai_interface import IStockaiModel

logger = logging.getLogger(__name__)


class BaseRegressionModel(IStockaiModel):
    """
    回归模型基类 - 完全复刻 FreqAI BaseRegressionModel

    实现了通用的训练和预测流程:
    1. 特征/标签过滤
    2. 数据分割
    3. 管道拟合和转换
    4. 模型训练/预测

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
        7. 保存模型和管道

        参数:
            df: 已包含特征 (%-前缀) 和标签 (&-前缀) 的 DataFrame
            pair: 股票代码
            dk: 数据厨房

        返回:
            训练好的模型
        """
        logger.info(f"开始训练: {pair}")

        # 1. 确保已识别特征和标签
        if not dk.training_features_list:
            dk.find_features(df)
        if not dk.label_list:
            dk.find_labels(df)

        # 2. 过滤特征和标签
        features_df, labels_df = dk.filter_features(df, training_filter=True)

        # 3. 分割数据
        data_dict = dk.make_train_test_datasets(features_df, labels_df)

        # 4. 定义管道
        dk.feature_pipeline = self.define_data_pipeline()
        dk.label_pipeline = self.define_label_pipeline()

        # 5. 拟合管道
        dk.feature_pipeline.fit(data_dict["train_features"])
        dk.label_pipeline.fit(data_dict["train_labels"].reshape(-1, 1))

        # 6. 转换数据
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

        # 7. 训练模型 (子类实现)
        logger.info(f"训练: {len(X_train)} 样本, {X_train.shape[1]} 特征")
        model = self.fit(data_dict, dk)

        # 8. 保存模型
        self._save_model_and_pipelines(pair, model, dk)

        logger.info(f"训练完成: {pair}")
        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> Tuple[pl.DataFrame, np.ndarray]:
        """
        通用预测流程

        步骤:
        1. 过滤特征
        2. 加载管道和模型
        3. 转换特征
        4. 预测
        5. 反向转换
        6. 构建结果

        参数:
            df: 已包含特征的 DataFrame
            dk: 数据厨房

        返回:
            (predictions_df, do_predict)
            - predictions_df: 预测结果 DataFrame (包含 datetime, prediction)
            - do_predict: numpy 数组 (1=可预测, 0=跳过)
        """
        pair = dk.pair

        # 1. 确保已识别特征
        if not dk.training_features_list:
            dk.find_features(df)

        # 2. 过滤特征
        features_df, _ = dk.filter_features(df)

        # 3. 加载管道和模型
        self._load_pipelines(pair, dk)
        model = self.dd.load_model(pair)

        # 4. 转换
        X = dk.feature_pipeline.transform(features_df.to_numpy())

        # 5. 预测
        predictions = model.predict(X)

        # 6. 反向转换
        predictions = dk.label_pipeline.inverse_transform(
            predictions.reshape(-1, 1)
        ).ravel()

        # 7. 构建结果
        result_df = pl.DataFrame({
            "datetime": df["datetime"],
            "prediction": predictions,
        })

        # 默认所有预测都有效
        do_predict = np.ones(len(predictions), dtype=np.int_)

        # 检查 NaN/inf
        valid_mask = np.isfinite(predictions)
        do_predict[~valid_mask] = 0

        logger.info(f"预测完成: {pair}, {len(result_df)} 样本")

        return result_df, do_predict

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
                - train_features: 训练特征 (numpy, 已管道转换)
                - train_labels: 训练标签 (numpy, 已管道转换)
                - test_features: 测试特征 (numpy, 已管道转换, 可能为空)
                - test_labels: 测试标签 (numpy, 已管道转换, 可能为空)
            dk: 数据厨房

        返回:
            训练好的模型
        """
        pass

    def define_data_pipeline(self) -> Pipeline:
        """
        定义特征处理管道（可覆盖）

        默认: VarianceThreshold -> MinMaxScaler
        """
        return Pipeline([
            ("variance_threshold", VarianceThreshold(threshold=0)),
            ("scaler", MinMaxScaler(feature_range=(-1, 1))),
        ])

    def define_label_pipeline(self) -> Pipeline:
        """
        定义标签处理管道（可覆盖）

        默认: MinMaxScaler
        """
        return Pipeline([
            ("scaler", MinMaxScaler(feature_range=(-1, 1))),
        ])

    def _save_model_and_pipelines(
        self,
        pair: str,
        model: Any,
        dk: StockaiDataKitchen,
    ) -> None:
        """保存模型和管道"""
        from ..utils import get_timestamp

        timestamp = get_timestamp()
        dk.set_paths(pair, timestamp)

        # 保存模型
        self.dd.save_model(pair, model, timestamp)

        # 保存管道
        if dk.feature_pipeline:
            joblib.dump(dk.feature_pipeline, dk.data_path / "feature_pipeline.pkl")
        if dk.label_pipeline:
            joblib.dump(dk.label_pipeline, dk.data_path / "label_pipeline.pkl")

        # 保存特征列表
        import json
        metadata = {
            "pair": pair,
            "timestamp": timestamp,
            "training_features_list": dk.training_features_list,
            "label_list": dk.label_list,
        }
        with open(dk.data_path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

    def _load_pipelines(self, pair: str, dk: StockaiDataKitchen) -> None:
        """加载管道"""
        if pair not in self.dd.pair_dict:
            raise ValueError(f"未找到 {pair} 的模型")

        filename = self.dd.pair_dict[pair]["model_filename"]
        model_path = self.dd.full_path / filename

        fp_path = model_path / "feature_pipeline.pkl"
        lp_path = model_path / "label_pipeline.pkl"

        if fp_path.exists():
            dk.feature_pipeline = joblib.load(fp_path)
        else:
            # 如果没有保存的管道，使用默认管道
            dk.feature_pipeline = self.define_data_pipeline()
            logger.warning(f"{pair}: 未找到特征管道，使用默认管道")

        if lp_path.exists():
            dk.label_pipeline = joblib.load(lp_path)
        else:
            dk.label_pipeline = self.define_label_pipeline()
            logger.warning(f"{pair}: 未找到标签管道，使用默认管道")
