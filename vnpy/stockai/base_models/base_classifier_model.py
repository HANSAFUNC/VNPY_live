"""StockAI 分类模型基类 - 完全复刻 FreqAI BaseClassifierModel"""

from abc import abstractmethod
from time import time
from typing import Any

import numpy as np
import numpy.typing as npt
from pandas import DataFrame

from vnpy.alpha.logger import logger

from ..data_kitchen import StockaiDataKitchen
from ..stockai_interface import IFreqaiModel


class BaseClassifierModel(IFreqaiModel):
    """
    分类模型基类 - 完全复刻 FreqAI BaseClassifierModel

    与 BaseRegressionModel 的区别:
    1. 训练时调用 _set_unique_classes 提取唯一类别
    2. 标签管道为空（分类标签不需要标准化）
    3. 预测时不做 inverse_transform
    """

    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, npt.NDArray],
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """
        实际模型拟合 - 子类必须实现

        参数:
            data_dictionary: 包含 train_features, train_labels, test_features, test_labels
            dk: 数据厨房

        返回:
            拟合好的模型
        """
        pass

    def train(
        self,
        unfiltered_df: DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """
        分类模型训练流程 - 完全复刻 FreqAI

        参数:
            unfiltered_df: 完整 DataFrame
            pair: 股票代码
            dk: 数据厨房

        返回:
            训练好的模型
        """
        logger.info(f"-------------------- Starting training {pair} --------------------")

        start_time = time()

        # 1. 识别特征和标签
        dk.find_features(unfiltered_df)
        dk.find_labels(unfiltered_df)

        # 2. 过滤特征和标签
        features_filtered, labels_filtered = dk.filter_features(
            unfiltered_df,
            dk.training_features_list,
            dk.label_list,
            training_filter=True,
        )

        # 3. 分割训练/测试集
        dd = dk.make_train_test_datasets(features_filtered, labels_filtered)

        # 4. 设置唯一类别
        self._set_unique_classes(dk, dd)

        # 5. 拟合标签 (可选)
        if not self.freqai_info.get("fit_live_predictions_candles", 0) or not self.live:
            dk.fit_labels()

        # 6. 定义和拟合管道
        dk.feature_pipeline = self.define_data_pipeline(threads=dk.thread_count)
        dk.label_pipeline = self.define_label_pipeline(threads=dk.thread_count)

        # 拟合特征管道
        dd["train_features"], _, _ = dk.feature_pipeline.fit_transform(
            dd["train_features"], None, None
        )

        # 转换测试集
        if dd["test_features"].shape[0] > 0:
            dd["test_features"], _, _ = dk.feature_pipeline.transform(
                dd["test_features"], None, None
            )

        logger.info(
            f"Training model on {dd['train_features'].shape[1]} features, "
            f"{dd['train_features'].shape[0]} data points, "
            f"{len(dk.unique_class_list)} classes"
        )

        # 7. 训练模型
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
        分类模型预测流程 - 完全复刻 FreqAI

        参数:
            unfiltered_df: 预测数据
            dk: 数据厨房

        返回:
            (pred_df, do_predict)
        """
        # 1. 识别特征
        dk.find_features(unfiltered_df)

        # 2. 过滤特征
        dk.data_dictionary["prediction_features"], _ = dk.filter_features(
            unfiltered_df, dk.training_features_list, training_filter=False
        )

        # 3. 应用特征管道
        pred_features, outliers, _ = dk.feature_pipeline.transform(
            dk.data_dictionary["prediction_features"], outlier_check=True
        )

        # 4. 预测
        predictions = self.model.predict(pred_features)

        # 分类预测不需要 reshape，直接是类别标签
        if len(dk.label_list) == 1:
            predictions = predictions.reshape(-1, 1)

        # 5. 构建预测 DataFrame
        pred_df = DataFrame(predictions, columns=dk.label_list)

        # 6. 分类预测不做 inverse_transform

        # 7. 设置 do_predict
        dk.do_predict = outliers.astype(int)

        return pred_df, dk.do_predict

    def _set_unique_classes(
        self,
        dk: StockaiDataKitchen,
        data_dictionary: dict[str, npt.NDArray],
    ) -> None:
        """
        提取并设置唯一类别列表

        参数:
            dk: 数据厨房
            data_dictionary: 数据字典
        """
        train_labels = data_dictionary["train_labels"]

        # 处理多维标签
        if train_labels.ndim > 1:
            train_labels = train_labels.ravel()

        unique_vals = sorted(np.unique(train_labels).tolist())
        dk.unique_class_list = unique_vals

        if dk.label_list:
            dk.unique_classes = {label: unique_vals for label in dk.label_list}
        else:
            dk.unique_classes = {"&target": unique_vals}

        logger.info(f"{dk.pair}: 唯一类别: {unique_vals}")

    def define_label_pipeline(self, threads: int = -1) -> Any:
        """
        定义标签处理管道 - 分类模型为空管道

        参数:
            threads: 线程数

        返回:
            datasieve Pipeline (空)
        """
        from datasieve.pipeline import Pipeline

        return Pipeline([])
