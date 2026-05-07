"""XGBoost 回归模型 - FreqAI 风格实现"""

from typing import Any

import numpy as np
import numpy.typing as npt
import xgboost as xgb

from vnpy.alpha.logger import logger

from ..base_models.base_regression_model import BaseRegressionModel
from ..data_kitchen import StockaiDataKitchen


class XGBoostRegressor(BaseRegressionModel):
    """
    XGBoost 回归模型 - 完全复刻 FreqAI XGBoostRegressor

    使用 xgboost.XGBRegressor 进行训练
    """

    def fit(
        self,
        data_dictionary: dict[str, npt.NDArray],
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """
        训练 XGBoost 回归模型

        参数:
            data_dictionary: 包含训练/测试数据
            dk: 数据厨房

        返回:
            训练好的 XGBRegressor 模型
        """
        X_train = data_dictionary["train_features"]
        y_train = data_dictionary["train_labels"]
        X_test = data_dictionary.get("test_features", np.array([]))
        y_test = data_dictionary.get("test_labels", np.array([]))

        # 处理多标签情况
        if y_train.ndim > 1 and y_train.shape[1] == 1:
            y_train = y_train.ravel()
        if y_test.ndim > 1 and y_test.shape[1] == 1:
            y_test = y_test.ravel()

        # 获取模型参数
        params = self.model_training_parameters.copy()

        # 默认参数
        default_params = {
            "n_estimators": 100,
            "learning_rate": 0.1,
            "max_depth": 6,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "objective": "reg:squarederror",
            "random_state": 42,
            "n_jobs": dk.thread_count,
        }

        # 合并参数（用户参数覆盖默认参数）
        for key, value in default_params.items():
            params.setdefault(key, value)

        logger.info(
            f"训练 XGBoost 回归模型: "
            f"n_estimators={params['n_estimators']}, "
            f"learning_rate={params['learning_rate']}, "
            f"max_depth={params['max_depth']}"
        )

        # 创建和训练模型
        model = xgb.XGBRegressor(**params)

        # 训练模型 (不使用 early stopping 以避免版本兼容问题)
        model.fit(X_train, y_train)

        # 记录特征重要性（如果有）
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            top_indices = np.argsort(importances)[-10:][::-1]
            logger.info(f"Top 10 重要特征索引: {top_indices}")

        return model
