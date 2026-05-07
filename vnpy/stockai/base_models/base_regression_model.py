"""StockAI 回归模型基类 - 完全复刻 FreqAI BaseRegressionModel"""

from abc import abstractmethod
from time import time
from typing import Any

import numpy as np
import numpy.typing as npt
from pandas import DataFrame

from vnpy.alpha.logger import logger

from ..data_kitchen import StockaiDataKitchen
from ..stockai_interface import IFreqaiModel


class BaseRegressionModel(IFreqaiModel):
    """
    回归模型基类 - 完全复刻 FreqAI BaseRegressionModel

    子类只需要实现 fit() 方法
    """

    def train(
        self,
        unfiltered_df: DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """
        训练模型 - 完全复刻 FreqAI BaseRegressionModel.train
        """
        logger.info(f"-------------------- Starting training {pair} --------------------")

        start_time = time()

        features_filtered, labels_filtered = dk.filter_features(
            unfiltered_df,
            dk.training_features_list,
            dk.label_list,
            training_filter=True,
        )

        start_date = unfiltered_df["date"].iloc[0].strftime("%Y-%m-%d")
        end_date = unfiltered_df["date"].iloc[-1].strftime("%Y-%m-%d")
        logger.info(
            f"-------------------- Training on data from {start_date} to "
            f"{end_date} --------------------"
        )

        dd = dk.make_train_test_datasets(features_filtered, labels_filtered)
        if not self.freqai_info.get("fit_live_predictions_candles", 0) or not self.live:
            dk.fit_labels()
        dk.feature_pipeline = self.define_data_pipeline(threads=dk.thread_count)
        dk.label_pipeline = self.define_label_pipeline(threads=dk.thread_count)

        (dd["train_features"], dd["train_labels"], dd["train_weights"]) = (
            dk.feature_pipeline.fit_transform(
                dd["train_features"], dd["train_labels"], dd["train_weights"]
            )
        )
        dd["train_labels"], _, _ = dk.label_pipeline.fit_transform(dd["train_labels"])

        if self.freqai_info.get("data_split_parameters", {}).get("test_size", 0.1) != 0:
            if dd["test_labels"].shape[0] == 0:
                raise ValueError(
                    f"{pair}: test set is empty after filtering. "
                    f"This is usually caused by overly strict SVM thresholds or insufficient data. "
                    f"Try reducing 'test_size' or relaxing your SVM conditions."
                )
            else:
                (dd["test_features"], dd["test_labels"], dd["test_weights"]) = (
                    dk.feature_pipeline.transform(
                        dd["test_features"], dd["test_labels"], dd["test_weights"]
                    )
                )
                dd["test_labels"], _, _ = dk.label_pipeline.transform(dd["test_labels"])

        logger.info(
            f"Training model on {len(dk.data_dictionary['train_features'].columns)} features"
        )
        logger.info(f"Training model on {len(dd['train_features'])} data points")

        model = self.fit(dd, dk)

        end_time = time()

        logger.info(
            f"-------------------- Done training {pair} "
            f"({end_time - start_time:.2f} secs) --------------------"
        )

        return model

    def predict(
        self,
        unfiltered_df: DataFrame,
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> tuple[DataFrame, npt.NDArray[np.int_]]:
        """
        预测 - 完全复刻 FreqAI BaseRegressionModel.predict
        """
        dk.find_features(unfiltered_df)
        dk.data_dictionary["prediction_features"], _ = dk.filter_features(
            unfiltered_df, dk.training_features_list, training_filter=False
        )

        dk.data_dictionary["prediction_features"], outliers, _ = dk.feature_pipeline.transform(
            dk.data_dictionary["prediction_features"], outlier_check=True
        )

        predictions = self.model.predict(dk.data_dictionary["prediction_features"])
        if self.CONV_WIDTH == 1:
            predictions = np.reshape(predictions, (-1, len(dk.label_list)))

        pred_df = DataFrame(predictions, columns=dk.label_list)

        pred_df, _, _ = dk.label_pipeline.inverse_transform(pred_df)
        if dk.feature_pipeline["di"]:
            dk.DI_values = dk.feature_pipeline["di"].di_values
        else:
            dk.DI_values = np.zeros(outliers.shape[0])
        dk.do_predict = outliers

        return (pred_df, dk.do_predict)

    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """子类必须实现"""
        pass

    def define_data_pipeline(self, threads: int = -1) -> Any:
        """
        定义特征处理管道 - 完全复刻 FreqAI
        """
        import datasieve.transforms as ds
        from datasieve.pipeline import Pipeline
        from datasieve.transforms import SKLearnWrapper
        from sklearn.preprocessing import MinMaxScaler

        ft_params = self.freqai_info["feature_parameters"]
        pipe_steps = [
            ("const", ds.VarianceThreshold(threshold=0)),
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ]

        if ft_params.get("principal_component_analysis", False):
            pipe_steps.append(("pca", ds.PCA(n_components=0.999)))
            pipe_steps.append(
                ("post-pca-scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1))))
            )

        if ft_params.get("use_SVM_to_remove_outliers", False):
            svm_params = ft_params.get("svm_params", {"shuffle": False, "nu": 0.01})
            pipe_steps.append(("svm", ds.SVMOutlierExtractor(**svm_params)))

        di = ft_params.get("DI_threshold", 0)
        if di:
            pipe_steps.append(("di", ds.DissimilarityIndex(di_threshold=di, n_jobs=threads)))

        if ft_params.get("use_DBSCAN_to_remove_outliers", False):
            pipe_steps.append(("dbscan", ds.DBSCAN(n_jobs=threads)))

        sigma = self.freqai_info["feature_parameters"].get("noise_standard_deviation", 0)
        if sigma:
            pipe_steps.append(("noise", ds.Noise(sigma=sigma)))

        return Pipeline(pipe_steps)

    def define_label_pipeline(self, threads: int = -1) -> Any:
        """
        定义标签处理管道 - 完全复刻 FreqAI
        """
        from datasieve.pipeline import Pipeline
        from datasieve.transforms import SKLearnWrapper
        from sklearn.preprocessing import MinMaxScaler

        return Pipeline([
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ])
