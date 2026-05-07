"""LightGBM 回归模型 - FreqAI 风格实现"""

from typing import Any

import lightgbm as lgb
import numpy as np
import numpy.typing as npt

from vnpy.alpha.logger import logger

from ..base_models.base_regression_model import BaseRegressionModel
from ..data_kitchen import StockaiDataKitchen


class LightGBMRegressor(BaseRegressionModel):
    """
    LightGBM 回归模型 - 完全复刻 FreqAI LightGBMRegressor

    使用 lightgbm.LGBMRegressor 进行训练
    """

    def fit(
        self,
        data_dictionary: dict[str, npt.NDArray],
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """
        训练 LightGBM 回归模型

        参数:
            data_dictionary: 包含训练/测试数据
            dk: 数据厨房

        返回:
            训练好的 LGBMRegressor 模型
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
            "max_depth": -1,
            "num_leaves": 31,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "objective": "regression",
            "random_state": 42,
            "n_jobs": dk.thread_count,
            "verbose": -1,
        }

        # 合并参数
        for key, value in default_params.items():
            params.setdefault(key, value)

        logger.info(
            f"训练 LightGBM 回归模型: "
            f"n_estimators={params['n_estimators']}, "
            f"learning_rate={params['learning_rate']}"
        )

        # 创建和训练模型
        model = lgb.LGBMRegressor(**params)

        # 如果有测试集，使用 early stopping
        if X_test.shape[0] > 0 and y_test.shape[0] > 0:
            model.fit(
                X_train,
                y_train,
                eval_set=[(X_test, y_test)],
                callbacks=[lgb.early_stopping(10, verbose=False)],
            )
        else:
            model.fit(X_train, y_train)

        # 记录特征重要性
        if hasattr(model, "feature_importances_"):
            importances = model.feature_importances_
            top_indices = np.argsort(importances)[-10:][::-1]
            logger.info(f"Top 10 重要特征: {top_indices}")

        return model
