"""StockAI XGBoost 极值预测模型 - 完全复刻 FreqAI XGBoostRegressorQuickAdapterV3"""


from tabnanny import verbose
import time
from typing import Any

import numpy as np
import numpy.typing as npt
import pandas as pd
import scipy as spy
from xgboost import XGBRegressor
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
        User sets up the training and test data to fit their desired model here
        :param data_dictionary: the dictionary constructed by DataHandler to hold
                                all the training and test data/labels.
        """

        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]

        if self.freqai_info.get("data_split_parameters", {}).get("test_size", 0.1) == 0:
            eval_set = None
            eval_weights = None
        else:
            eval_set = [(data_dictionary["test_features"], data_dictionary["test_labels"])]
            eval_weights = [data_dictionary['test_weights']]

        sample_weight = data_dictionary["train_weights"]

        xgb_model = self.get_init_model(dk.pair)

        model = XGBRegressor(**self.model_training_parameters)

        start = time.time()
        model.fit(X=X, y=y, sample_weight=sample_weight, eval_set=eval_set,
                  sample_weight_eval_set=eval_weights, xgb_model=xgb_model,verbose=0)
        time_spent = (time.time() - start)
        self.dd.update_metric_tracker('fit_time', time_spent, dk.pair)

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

        warmed_up = True
        num_candles = self.freqai_info.get('fit_live_predictions_candles', 100)
        if not hasattr(self, 'exchange_candles'):
            self.exchange_candles = len(self.dd.model_return_values[pair].index)
        candle_diff = len(self.dd.historic_predictions[pair].index) - \
            (num_candles + self.exchange_candles)
        if candle_diff < 0:
            logger.warning(
                f'Fit live predictions not warmed up yet. Still {abs(candle_diff)} candles to go')
            warmed_up = False

        pred_df_full = self.dd.historic_predictions[pair].tail(num_candles).reset_index(drop=True)
        pred_df_sorted = pd.DataFrame()
        for label in pred_df_full.keys():
            if pred_df_full[label].dtype == object:
                continue
            pred_df_sorted[label] = pred_df_full[label]

        # pred_df_sorted = pred_df_sorted
        for col in pred_df_sorted:
            pred_df_sorted[col] = pred_df_sorted[col].sort_values(
                ascending=False, ignore_index=True)
        frequency = num_candles / (self.freqai_info['feature_parameters']['label_period_candles'] * 2)
        max_pred = pred_df_sorted.iloc[:int(frequency)].mean()
        min_pred = pred_df_sorted.iloc[-int(frequency):].mean()

        if not warmed_up:
            dk.data['extra_returns_per_train']['&s-maxima_sort_threshold'] = 2
            dk.data['extra_returns_per_train']['&s-minima_sort_threshold'] = -2
        else:
            dk.data['extra_returns_per_train']['&s-maxima_sort_threshold'] = max_pred['&s-extrema']
            dk.data['extra_returns_per_train']['&s-minima_sort_threshold'] = min_pred['&s-extrema']

        dk.data["labels_mean"], dk.data["labels_std"] = {}, {}
        for ft in dk.label_list:
            # f = spy.stats.norm.fit(pred_df_full[ft])
            dk.data['labels_std'][ft] = 0  # f[1]
            dk.data['labels_mean'][ft] = 0  # f[0]

        # fit the DI_threshold
        if not warmed_up:
            f = [0, 0, 0]
            cutoff = 2
        else:
            # 确保数值类型，防止 object dtype 导致 scipy 报错
            di_values = pred_df_full['DI_values'].astype(float)
            f = spy.stats.weibull_min.fit(di_values)
            cutoff = spy.stats.weibull_min.ppf(0.999, *f)

        dk.data["DI_value_mean"] = pred_df_full['DI_values'].mean()
        dk.data["DI_value_std"] = pred_df_full['DI_values'].std()
        dk.data['extra_returns_per_train']['DI_value_param1'] = f[0]
        dk.data['extra_returns_per_train']['DI_value_param2'] = f[1]
        dk.data['extra_returns_per_train']['DI_value_param3'] = f[2]
        dk.data['extra_returns_per_train']['DI_cutoff'] = cutoff



        
