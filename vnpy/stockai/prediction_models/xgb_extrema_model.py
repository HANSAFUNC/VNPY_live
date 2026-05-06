"""StockAI XGBoost 极值预测模型 - 完全复刻 FreqAI XGBoostRegressorQuickAdapterV3"""


import time
from typing import Any, Tuple
import numpy as np
import polars as pl
import scipy as spy
from xgboost import XGBRegressor
from vnpy.alpha.logger import logger
from ..base_models.base_regression_model import BaseRegressionModel
from ..data_kitchen import StockaiDataKitchen


class XGBoostExtremaModel(BaseRegressionModel):
    """
    XGBoost 极值预测模型 - 完全复刻 FreqAI XGBoostRegressorQuickAdapterV3

    特性:
    - 使用 XGBRegressor 进行回归预测
    - 支持早停
    - 支持样本权重训练
    - 支持动态阈值计算 (fit_live_predictions)
    - 支持 DI 值 Weibull 分布拟合
    """

    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> XGBRegressor:
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

        # 准备评估集
        if self.data_split_params.get("test_size", 0.1) == 0:
            eval_set = None
            eval_weights = None
        else:
            eval_set = [(data_dictionary["test_features"], data_dictionary["test_labels"])]
            eval_weights = [data_dictionary.get("test_weights", None)]

        # 获取样本权重
        sample_weight = data_dictionary.get("train_weights", None)

        # 获取增量训练模型（如果支持）
        xgb_model = self._get_init_model(dk.pair)

        # 模型参数
        model = XGBRegressor(**self.model_training_params)

        # 训练
        start = time.time()
        model.fit(
            X=X, y=y,
            sample_weight=sample_weight,
            eval_set=eval_set,
            sample_weight_eval_set=eval_weights,
            xgb_model=xgb_model,
            verbose=False,
        )
        time_spent = time.time() - start

        # 保存训练样本数用于 fit_live_predictions 预热计算
        # 注意：model_return_values 在 FreqAI 中是存储预测结果的，不是训练索引
        # 训练样本数直接存入 exchange_candles 属性
        self.exchange_candles = len(X)

        # 记录训练时间
        self.dd.update_metric_tracker("fit_time", time_spent, dk.pair)

        logger.info(f"XGBoost 训练完成: {len(X)} 样本, 耗时 {time_spent:.2f}s")
        if hasattr(model, 'best_iteration'):
            logger.info(f"  best_iteration={model.best_iteration}")

        return model

    def _get_init_model(self, pair: str):
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
        拟合实时预测 - 计算动态阈值和 DI 值分布

        基于历史预测结果计算：
        1. 极大值/极小值动态阈值
        2. DI 值的 Weibull 分布参数
        """
        warmed_up = True
        num_candles = self.config.get("fit_live_predictions_candles", 100)

        # 初始化 exchange_candles
        # 从 model_return_values 获取（FreqAI 风格）
        if not hasattr(self, 'exchange_candles'):
            if pair in self.dd.model_return_values:
                self.exchange_candles = len(self.dd.model_return_values[pair])
            else:
                self.exchange_candles = 0

        historic_df = self.dd.historic_predictions.get(pair)
        logger.info(f"{pair}: 进入实时预测预热流程")
        if historic_df is None or len(historic_df) == 0:
            logger.info(f"{pair}: 实时预测预热中，历史数据 0/{num_candles + self.exchange_candles}")
            warmed_up = False
        else:
            # FreqAI 风格：需要 num_candles + exchange_candles 条数据
            logger.info(f"{pair}: historic_df 行数: {len(historic_df)}, 期望数: {num_candles + self.exchange_candles} num_candles:{num_candles} exchange_candles:{self.exchange_candles}")
            candle_diff = len(historic_df) - (num_candles + self.exchange_candles)
            if candle_diff < 0:
                logger.info(f"{pair}: 实时预测预热中，还需 {abs(candle_diff)} 根K线 (当前 {len(historic_df)}/{num_candles + self.exchange_candles})")
                warmed_up = False
            else:
                logger.info(f"{pair}: 历史数据已满足预热要求。")

        if historic_df is not None and len(historic_df) > 0:
            pred_df_full = historic_df.tail(num_candles)
            logger.info(f"{pair}: pred_df_full shape: {pred_df_full.shape if hasattr(pred_df_full, 'shape') else len(pred_df_full)} (取尾部 {num_candles} 条用于后续阈值计算)")
     

            # 计算预测值的排序均值
            label_cols = [c for c in pred_df_full.columns if c.startswith("&")]
            max_pred = {}
            min_pred = {}

            for col in label_cols:
                if pred_df_full[col].dtype in [pl.Float32, pl.Float64]:
                    sorted_vals = pred_df_full[col].sort(descending=True)
                    frequency = num_candles / (self.ft_params.get("label_period_candles", 10) * 2)
                    freq_int = max(1, int(frequency))

                    if len(sorted_vals) >= freq_int * 2:
                        max_pred[col] = sorted_vals.head(freq_int).mean()
                        min_pred[col] = sorted_vals.tail(freq_int).mean()

            # 设置动态阈值
            if not warmed_up:
                dk.data["extra_returns_per_train"]["&s-maxima_sort_threshold"] = 2
                dk.data["extra_returns_per_train"]["&s-minima_sort_threshold"] = -2
            else:
                label_name = dk.label_list[0] if dk.label_list else "&s-extrema"
                dk.data["extra_returns_per_train"]["&s-maxima_sort_threshold"] = max_pred.get(label_name, 2)
                dk.data["extra_returns_per_train"]["&s-minima_sort_threshold"] = min_pred.get(label_name, -2)

            # 重置标签统计
            dk.data["labels_mean"], dk.data["labels_std"] = {}, {}
            for ft in dk.label_list:
                dk.data["labels_std"][ft] = 0
                dk.data["labels_mean"][ft] = 0

            # 拟合 DI 值的 Weibull 分布
            if "DI_values" in pred_df_full.columns and warmed_up:
                try:
                    di_values = pred_df_full["DI_values"].to_numpy().astype(float)
                    # Weibull 分布拟合
                    f = spy.stats.weibull_min.fit(di_values)
                    cutoff = spy.stats.weibull_min.ppf(0.999, *f)

                    dk.data["DI_value_mean"] = float(np.mean(di_values))
                    dk.data["DI_value_std"] = float(np.std(di_values))
                    dk.data["extra_returns_per_train"]["DI_value_param1"] = f[0]
                    dk.data["extra_returns_per_train"]["DI_value_param2"] = f[1]
                    dk.data["extra_returns_per_train"]["DI_value_param3"] = f[2]
                    dk.data["extra_returns_per_train"]["DI_cutoff"] = cutoff

                    logger.info(f"{pair}: DI Weibull 拟合完成, cutoff={cutoff:.4f}")
                except Exception as e:
                    logger.warning(f"{pair}: DI Weibull 拟合失败: {e}")
                    dk.data["extra_returns_per_train"]["DI_value_param1"] = 0
                    dk.data["extra_returns_per_train"]["DI_value_param2"] = 0
                    dk.data["extra_returns_per_train"]["DI_value_param3"] = 0
                    dk.data["extra_returns_per_train"]["DI_cutoff"] = 2
            else:
                # 未预热或没有 DI 值
                dk.data["extra_returns_per_train"]["DI_value_param1"] = 0
                dk.data["extra_returns_per_train"]["DI_value_param2"] = 0
                dk.data["extra_returns_per_train"]["DI_value_param3"] = 0
                dk.data["extra_returns_per_train"]["DI_cutoff"] = 2

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> Tuple[pl.DataFrame, np.ndarray]:
        """
        预测 - 继承基类流程，添加后处理

        参数:
            df: 已包含特征的 DataFrame
            dk: 数据厨房

        返回:
            (predictions_df, do_predict)
        """
 
        # 调用基类的通用预测流程
        predictions_df, do_predict = super().predict(df, dk)

        # 将 extra_returns_per_train 中的阈值和参数添加到预测结果
        extra_returns = dk.data.get("extra_returns_per_train", {})
        if extra_returns:
            n_rows = len(predictions_df)
            for col_name, value in extra_returns.items():
                # 为每一行添加相同的阈值/参数值
                predictions_df = predictions_df.with_columns([
                    pl.lit(float(value)).alias(col_name)
                ])
            logger.debug(f"{dk.pair}: 已添加 {len(extra_returns)} 个 extra_returns 列")
        else:
            # 添加默认阈值列
            default_thresholds = {
                "&s-maxima_sort_threshold": 2.0,
                "&s-minima_sort_threshold": -2.0,
                "DI_cutoff": 2.0,
                "DI_value_param1": 0.0,
                "DI_value_param2": 0.0,
                "DI_value_param3": 0.0,
            }
            for col_name, value in default_thresholds.items():
                predictions_df = predictions_df.with_columns([
                    pl.lit(float(value)).alias(col_name)
                ])
            logger.debug(f"{dk.pair}: 已添加默认阈值列")

        # 添加 DI_values (如果存在)
        if hasattr(dk, 'DI_values') and dk.DI_values is not None:
            if len(dk.DI_values) == len(predictions_df):
                predictions_df = predictions_df.with_columns([
                    pl.Series("DI_values", dk.DI_values)
                ])

        # 保存预测到历史 (用于 fit_live_predictions 累积数据)
        hist_df = predictions_df.clone()
        if "pair" not in hist_df.columns:
            hist_df = hist_df.with_columns([pl.lit(dk.pair).alias("pair")])
        self.dd.append_model_predictions(dk.pair, hist_df)

        return predictions_df, do_predict
