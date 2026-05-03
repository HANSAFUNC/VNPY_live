"""StockAI XGBoost 极值预测模型"""

import logging
from typing import Any, Tuple

import numpy as np
import polars as pl
import scipy.stats
from xgboost import XGBRegressor

from ..base_models.base_regression_model import BaseRegressionModel
from ..data_kitchen import StockaiDataKitchen

logger = logging.getLogger(__name__)


class XGBoostExtremaModel(BaseRegressionModel):
    """
    XGBoost 极值预测模型

    特性:
    - 渐进式阈值预热
    - 动态阈值计算
    - DI异常检测
    """

    # 默认阈值
    DEFAULT_MAXIMA_THRESHOLD = 2.0
    DEFAULT_MINIMA_THRESHOLD = -2.0
    DEFAULT_DI_CUTOFF = 2.0
    MIN_CANDLES_FOR_DYNAMIC = 50

    def __init__(self, config: dict, lab: Any):
        super().__init__(config, lab)

        # 模型参数
        self.model_params = config.get("model_training_parameters", {})

        # 特征参数
        self.num_candles = self.ft_params.get("num_candles", 200)
        self.label_period_candles = self.ft_params.get("label_period_candles", 10)

    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> XGBRegressor:
        """训练 XGBoost 模型"""
        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]

        # 模型参数
        params = {
            "learning_rate": self.model_params.get("learning_rate", 0.05),
            "max_depth": self.model_params.get("max_depth", 6),
            "n_estimators": self.model_params.get("n_estimators", 100),
            "early_stopping_rounds": self.model_params.get("early_stopping_rounds", 50),
            "objective": "reg:squarederror",
            "random_state": 42,
        }

        model = XGBRegressor(**params)

        # 如果有测试集，使用早停
        if len(data_dictionary.get("test_features", [])) > 0:
            model.fit(
                X=X, y=y,
                eval_set=[(data_dictionary["test_features"], data_dictionary["test_labels"])],
                verbose=False,
            )
        else:
            model.fit(X=X, y=y)

        logger.info(f"XGBoost 训练完成: best_iteration={model.best_iteration}")

        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """
        预测（带动态阈值）

        步骤:
        1. 基础预测
        2. 计算动态阈值
        3. 添加阈值列
        """
        # 基础预测
        result = super().predict(df, dk)

        # 计算阈值
        self._compute_thresholds(dk, result)

        # 添加阈值列
        extra = dk.data.get("extra_returns_per_train", {})
        result = result.with_columns([
            pl.lit(extra.get("maxima_threshold", self.DEFAULT_MAXIMA_THRESHOLD))
            .alias("maxima_threshold"),
            pl.lit(extra.get("minima_threshold", self.DEFAULT_MINIMA_THRESHOLD))
            .alias("minima_threshold"),
            pl.lit(extra.get("di_cutoff", self.DEFAULT_DI_CUTOFF))
            .alias("di_cutoff"),
        ])

        return result

    def _compute_thresholds(
        self,
        dk: StockaiDataKitchen,
        predictions: pl.DataFrame,
    ) -> None:
        """计算动态阈值"""
        pair = dk.pair

        # 获取历史预测
        hist_df = self.dd.get_historic_predictions(pair)
        if hist_df is None:
            hist_df = predictions
        else:
            hist_df = pl.concat([hist_df, predictions])

        # 计算预热进度
        n_candles = len(hist_df)
        warmup_progress = min(1.0, n_candles / self.num_candles)

        # 获取近期预测用于阈值计算
        recent_df = hist_df.tail(self.num_candles)

        # 计算阈值
        maxima, minima = self._compute_progressive_thresholds(
            recent_df, warmup_progress
        )
        di_cutoff, di_params = self._compute_progressive_di_cutoff(
            recent_df, warmup_progress
        )

        # 存储到数据厨房
        dk.data["extra_returns_per_train"] = {
            "maxima_threshold": maxima,
            "minima_threshold": minima,
            "di_cutoff": di_cutoff,
            "di_param1": di_params[0],
            "di_param2": di_params[1],
            "di_param3": di_params[2],
        }

        logger.info(
            f"{pair}: 阈值计算完成 (maxima={maxima:.3f}, minima={minima:.3f}, "
            f"di_cutoff={di_cutoff:.3f}, 进度={warmup_progress:.1%})"
        )

    def _compute_progressive_thresholds(
        self,
        pred_df: pl.DataFrame,
        warmup_progress: float,
    ) -> Tuple[float, float]:
        """计算渐进式阈值（混合默认和动态）"""
        # 默认值
        default_max = self.DEFAULT_MAXIMA_THRESHOLD
        default_min = self.DEFAULT_MINIMA_THRESHOLD

        # 数据不足，使用默认值
        if len(pred_df) < self.MIN_CANDLES_FOR_DYNAMIC:
            return default_max, default_min

        # 计算动态阈值
        frequency = max(1, int(self.num_candles / (self.label_period_candles * 2)))
        frequency = min(frequency, len(pred_df))

        predictions = pred_df["prediction"].to_numpy()
        sorted_preds = np.sort(predictions)[::-1]

        dynamic_max = float(np.mean(sorted_preds[:frequency]))
        dynamic_min = float(np.mean(sorted_preds[-frequency:]))

        # 混合（根据预热进度）
        maxima = default_max * (1 - warmup_progress) + dynamic_max * warmup_progress
        minima = default_min * (1 - warmup_progress) + dynamic_min * warmup_progress

        return maxima, minima

    def _compute_progressive_di_cutoff(
        self,
        pred_df: pl.DataFrame,
        warmup_progress: float,
    ) -> Tuple[float, Tuple[float, float, float]]:
        """使用Weibull分布计算DI截止值"""
        default = self.DEFAULT_DI_CUTOFF
        default_params = (0.0, 0.0, 0.0)

        if len(pred_df) < self.MIN_CANDLES_FOR_DYNAMIC:
            return default, default_params

        if "di_values" not in pred_df.columns:
            return default, default_params

        try:
            di_values = pred_df["di_values"].to_numpy()
            di_values = di_values[~np.isnan(di_values)]

            if len(di_values) < 10:
                return default, default_params

            # 拟合Weibull分布
            params = scipy.stats.weibull_min.fit(di_values)
            dynamic = float(scipy.stats.weibull_min.ppf(0.999, *params))

            # 混合
            cutoff = default * (1 - warmup_progress) + dynamic * warmup_progress
            blended = tuple(
                default_params[i] * (1 - warmup_progress) + params[i] * warmup_progress
                for i in range(3)
            )

            return cutoff, blended

        except Exception as e:
            logger.warning(f"DI截止值计算失败: {e}")
            return default, default_params
