"""StockAI XGBoost 极值预测模型 - 完全复刻 FreqAI XGBoostRegressor"""

from typing import Any, Tuple

import numpy as np
import polars as pl
from xgboost import XGBRegressor

from vnpy.alpha.logger import logger

from ..base_models.base_regression_model import BaseRegressionModel
from ..data_kitchen import StockaiDataKitchen


class XGBoostExtremaModel(BaseRegressionModel):
    """
    XGBoost 极值预测模型 - 完全复刻 FreqAI XGBoostRegressor

    特性:
    - 使用 XGBRegressor 进行回归预测
    - 支持早停
    - 支持动态阈值计算
    """

    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> XGBRegressor:
        """
        训练 XGBoost 模型

        参数:
            data_dictionary: 包含训练/测试数据的字典
            dk: 数据厨房

        返回:
            训练好的 XGBRegressor 模型
        """
        X_train = data_dictionary["train_features"]
        y_train = data_dictionary["train_labels"]

        # 模型参数
        params = {
            "learning_rate": self.model_training_params.get("learning_rate", 0.05),
            "max_depth": self.model_training_params.get("max_depth", 6),
            "n_estimators": self.model_training_params.get("n_estimators", 100),
            "early_stopping_rounds": self.model_training_params.get("early_stopping_rounds", 50),
            "objective": "reg:squarederror",
            "random_state": 42,
            "n_jobs": -1,
        }

        model = XGBRegressor(**params)

        # 检查训练数据
        logger.info(f"XGBoost 训练数据: X_train shape={X_train.shape}, y_train range=[{np.min(y_train):.4f}, {np.max(y_train):.4f}]")
        if np.isnan(X_train).any() or np.isinf(X_train).any():
            logger.error(f"XGBoost 训练特征包含 NaN/inf: {np.isnan(X_train).sum()} NaN, {np.isinf(X_train).sum()} inf")
        if np.isnan(y_train).any() or np.isinf(y_train).any():
            logger.error(f"XGBoost 训练标签包含 NaN/inf: {np.isnan(y_train).sum()} NaN, {np.isinf(y_train).sum()} inf")

        # 如果有测试集，使用早停
        if len(data_dictionary.get("test_features", [])) > 0:
            X_test = data_dictionary["test_features"]
            y_test = data_dictionary["test_labels"]
            logger.info(f"XGBoost 测试数据: X_test shape={X_test.shape}")
            model.fit(
                X=X_train, y=y_train,
                eval_set=[(X_test, y_test)],
                verbose=False,
            )
            logger.info(f"XGBoost 训练完成: best_iteration={model.best_iteration}")
        else:
            model.fit(X=X_train, y=y_train)
            logger.info(f"XGBoost 训练完成: n_estimators={model.n_estimators}")

        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> Tuple[pl.DataFrame, np.ndarray]:
        """
        预测 - 继承基类流程，可添加后处理

        参数:
            df: 已包含特征的 DataFrame
            dk: 数据厨房

        返回:
            (predictions_df, do_predict)
        """
        # 调用基类的通用预测流程
        predictions_df, do_predict = super().predict(df, dk)

        # 添加额外信息 (可选)
        # 例如: 动态阈值、置信度等

        return predictions_df, do_predict
