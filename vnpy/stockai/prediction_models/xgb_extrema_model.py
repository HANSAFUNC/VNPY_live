"""StockAI XGBoost 极值预测模型 - 完全复刻 FreqAI XGBoostRegressorQuickAdapterV3"""

import logging
import time
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import scipy as spy
import xgboost as xgb
from pandas import DataFrame

from vnpy.alpha.logger import logger

from ..base_models.base_regression_model import BaseRegressionModel
from ..data_kitchen import StockaiDataKitchen

import warnings
warnings.filterwarnings("ignore", category=FutureWarning)


class XGBoostExtremaModel(BaseRegressionModel):
    """
    XGBoost 极值预测模型 - 完全复刻 FreqAI XGBoostRegressorQuickAdapterV3

    特性:
    - 使用 XGBRegressor 进行回归预测
    - 支持早停
    - 支持样本权重训练
    - 支持动态阈值计算 (fit_live_predictions)
    """

    def fit(
        self,
        data_dictionary: dict[str, npt.NDArray],
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """
        训练 XGBoost 模型 - 复刻 QuickAdapterV3

        参数:
            data_dictionary: 包含训练/测试数据的字典
            dk: 数据厨房

        返回:
            训练好的 XGBRegressor 模型
        """
        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]

        # 处理评估集
        if self.data_split_parameters.get("test_size", 0.1) == 0:
            eval_set = None
            eval_weights = None
        else:
            eval_set = [(data_dictionary["test_features"], data_dictionary["test_labels"])]
            eval_weights = [data_dictionary.get("test_weights", None)]

        # 获取样本权重
        sample_weight = data_dictionary.get("train_weights", None)

        # 获取增量训练的初始模型
        xgb_model = self.get_init_model(dk.pair)

        # 获取模型参数
        params = self.model_training_parameters.copy()

        model = xgb.XGBRegressor(**params)

        start = time.time()
        model.fit(
            X=X,
            y=y,
            sample_weight=sample_weight,
            eval_set=eval_set,
            sample_weight_eval_set=eval_weights,
            xgb_model=xgb_model,
        )
        time_spent = time.time() - start
        self.dd.update_metric_tracker("fit_time", time_spent, dk.pair)

        return model

    def get_init_model(self, pair: str):
        """获取增量训练的初始模型"""
        # XGBoost 支持增量训练，尝试从模型缓存或磁盘加载
        if pair in self.dd.pair_dict:
            try:
                # 尝试加载已有模型用于继续训练
                model = self.dd.load_model(pair)
                logger.info(f"{pair}: 加载已有模型用于增量训练")
                return model
            except Exception as e:
                logger.debug(f"{pair}: 无法加载已有模型用于增量训练: {e}")
                return None
        return None

    def fit_live_predictions(self, dk: StockaiDataKitchen, pair: str) -> None:
        """
        拟合实时预测 - 计算动态阈值

        基于历史预测结果计算动态阈值
        """
        # 获取历史预测数据
        hist_preds = self.dd.historic_predictions.get(pair, pd.DataFrame())

        if hist_preds.empty:
            logger.warning(f"{pair}: 没有历史预测数据用于 fit_live_predictions")
            return

        # 计算标签均值和标准差
        dk.data["labels_mean"] = {}
        dk.data["labels_std"] = {}

        for label in dk.label_list:
            if label in hist_preds.columns:
                mean = hist_preds[label].mean()
                std = hist_preds[label].std()
                dk.data["labels_mean"][label] = mean
                dk.data["labels_std"][label] = std

        # 计算额外返回值
        dk.data["extra_returns_per_train"] = {}

        # 如果有 DI_values 列，计算 Weibull 分布参数
        if "DI_values" in hist_preds.columns:
            di_values = hist_preds["DI_values"].dropna().astype(float)
            if len(di_values) > 0:
                try:
                    # Weibull 分布拟合
                    c, loc, scale = spy.stats.weibull_min.fit(di_values)
                    cutoff = spy.stats.weibull_min.ppf(0.999, c, loc, scale)

                    dk.data["extra_returns_per_train"]["DI_value_param1"] = c
                    dk.data["extra_returns_per_train"]["DI_value_param2"] = loc
                    dk.data["extra_returns_per_train"]["DI_value_param3"] = scale
                    dk.data["extra_returns_per_train"]["DI_cutoff"] = cutoff
                    dk.data["DI_value_mean"] = di_values.mean()
                    dk.data["DI_value_std"] = di_values.std()
                except Exception as e:
                    logger.warning(f"{pair}: Weibull 拟合失败: {e}")
                    dk.data["extra_returns_per_train"]["DI_cutoff"] = 2.0

        logger.debug(f"{pair}: fit_live_predictions 完成")
