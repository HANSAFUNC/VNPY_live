"""StockAI 分类模型基类 - 复刻 FreqAI BaseClassifierModel"""

from abc import abstractmethod
from typing import Any, Tuple

import joblib
import numpy as np
import polars as pl
import datasieve.transforms as ds
from datasieve.pipeline import Pipeline
from datasieve.transforms import SKLearnWrapper
from sklearn.preprocessing import MinMaxScaler

from vnpy.alpha.logger import logger

from ..data_kitchen import StockaiDataKitchen
from ..stockai_interface import IStockaiModel


class BaseClassifierModel(IStockaiModel):
    """
    分类模型基类 - 复刻 FreqAI BaseClassifierModel

    与 BaseRegressionModel 的区别:
    1. 训练时调用 _set_unique_classes 提取唯一类别
    2. 标签管道为空（分类标签不需要标准化）
    3. 预测时不做 inverse_transform
    """

    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        分类模型训练流程

        参数:
            df: 已包含特征 (%-前缀) 和标签 (&-前缀) 的 DataFrame
            pair: 股票代码
            dk: 数据厨房

        返回:
            训练好的模型
        """
        logger.info(f"开始训练 (分类): {pair}")

        dk.find_features(df)
        dk.find_labels(df)

        features_df, labels_df = dk.filter_features(
            unfiltered_df=df,
            training_feature_list=dk.training_features_list,
            label_list=dk.label_list,
            training_filter=True,
        )

        data_dict = dk.make_train_test_datasets(features_df, labels_df)

        self._set_unique_classes(dk, data_dict)

        if not self.config.get("fit_live_predictions_candles", 0) or not dk.config.get("live", False):
            dk.fit_labels()

        dk.feature_pipeline = self.define_data_pipeline()
        dk.label_pipeline = self.define_label_pipeline()

        logger.info(f"{pair}: 拟合特征管道...")
        dk.feature_pipeline.feature_list = dk.training_features_list
        dk.feature_pipeline.fit(data_dict["train_features"])
        dk.training_features_list = dk.feature_pipeline.feature_list

        X_train, _, _ = dk.feature_pipeline.transform(data_dict["train_features"], outlier_check=True)
        y_train = data_dict["train_labels"]

        data_dict["train_features"] = X_train
        data_dict["train_labels"] = y_train

        if len(data_dict["test_features"]) > 0:
            X_test, _, _ = dk.feature_pipeline.transform(data_dict["test_features"], outlier_check=True)
            data_dict["test_features"] = X_test

        logger.info(f"训练: {len(X_train)} 样本, {X_train.shape[1]} 特征, {len(dk.unique_class_list)} 类别")
        model = self.fit(data_dict, dk)

        # 保存模型和数据 (使用接口的save_data方法)
        self.save_data(model, pair, dk)

        logger.info(f"训练完成 (分类): {pair}")
        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> Tuple[pl.DataFrame, np.ndarray]:
        """
        分类模型预测流程

        参数:
            df: 已包含特征的 DataFrame
            dk: 数据厨房

        返回:
            (predictions_df, do_predict)
        """
        pair = dk.pair

        dk.find_features(df)
        self._load_pipelines(pair, dk)

        features_df, _ = dk.filter_features(
            unfiltered_df=df,
            training_feature_list=dk.training_features_list,
            label_list=None,
            training_filter=False,
        )

        filtered_datetime = df["datetime"] if "datetime" in df.columns else pl.Series(range(len(features_df)))

        dk.data_dictionary["prediction_features"] = features_df.to_numpy()

        X, _, _ = dk.feature_pipeline.transform(features_df.to_numpy())

        if self.model is None:
            raise ValueError(f"{pair}: 模型未加载，请先调用 start() 或加载模型")
        predictions = self.model.predict(X)

        label_name = dk.label_list[0] if dk.label_list else "&target"
        result_df = pl.DataFrame({
            "datetime": filtered_datetime,
            label_name: predictions,
        })

        do_predict = dk.do_predict

        valid_mask = np.isfinite(predictions.astype(float))
        do_predict = do_predict & valid_mask.astype(int)

        logger.info(f"预测完成 (分类): {pair}, {len(result_df)} 样本, {do_predict.sum()} 有效")

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
            dk: 数据厨房

        返回:
            训练好的模型
        """
        pass

    def _set_unique_classes(self, dk: StockaiDataKitchen, data_dict: dict) -> None:
        """
        提取并设置唯一类别列表

        参数:
            dk: 数据厨房
            data_dict: 数据字典（包含 train_labels）
        """
        labels = data_dict["train_labels"]
        unique_vals = sorted(np.unique(labels).tolist())
        dk.unique_class_list = unique_vals
        if dk.label_list:
            dk.unique_classes = {label: unique_vals for label in dk.label_list}
        else:
            dk.unique_classes = {"&target": unique_vals}

        logger.info(f"{dk.pair}: 唯一类别: {unique_vals}")

    def define_data_pipeline(self) -> Pipeline:
        """定义特征处理管道（可覆盖）"""
        return Pipeline([
            ("variance_threshold", ds.VarianceThreshold(threshold=0)),
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ])

    def define_label_pipeline(self) -> Pipeline:
        """分类模型不需要标签管道"""
        return Pipeline([])

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

        self.dd.save_model(pair, model, timestamp)

        if dk.feature_pipeline:
            joblib.dump(dk.feature_pipeline, dk.data_path / "feature_pipeline.pkl")
        if dk.label_pipeline:
            joblib.dump(dk.label_pipeline, dk.data_path / "label_pipeline.pkl")

        import json
        metadata = {
            "pair": pair,
            "timestamp": timestamp,
            "training_features_list": dk.training_features_list,
            "label_list": dk.label_list,
            "unique_classes": dk.unique_classes,
            "unique_class_list": dk.unique_class_list,
        }
        with open(dk.data_path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # 更新 meta_data_dictionary (FreqAI风格)
        if pair not in self.dd.meta_data_dictionary:
            self.dd.meta_data_dictionary[pair] = {}
        self.dd.meta_data_dictionary[pair]["metadata"] = metadata
        self.dd.meta_data_dictionary[pair]["feature_pipeline"] = dk.feature_pipeline
        self.dd.meta_data_dictionary[pair]["label_pipeline"] = dk.label_pipeline

    def _load_pipelines(self, pair: str, dk: StockaiDataKitchen) -> None:
        """加载管道和元数据"""
        if pair not in self.dd.pair_dict:
            raise ValueError(f"未找到 {pair} 的模型")

        filename = self.dd.pair_dict[pair]["model_filename"]
        model_path = self.dd.full_path / filename

        # 优先从内存中的 meta_data_dictionary 加载 (FreqAI风格)
        if pair in self.dd.meta_data_dictionary:
            meta_dict = self.dd.meta_data_dictionary[pair]
            if "metadata" in meta_dict:
                dk.training_features_list = meta_dict["metadata"].get("training_features_list", [])
                dk.label_list = meta_dict["metadata"].get("label_list", [])
                dk.unique_classes = meta_dict["metadata"].get("unique_classes", {})
                dk.unique_class_list = meta_dict["metadata"].get("unique_class_list", [])
                logger.info(
                    f"{pair}: 从内存加载特征列表 "
                    f"({len(dk.training_features_list)} 个特征): {dk.training_features_list[:5]}..."
                )
            if "feature_pipeline" in meta_dict:
                dk.feature_pipeline = meta_dict["feature_pipeline"]
            if "label_pipeline" in meta_dict:
                dk.label_pipeline = meta_dict["label_pipeline"]
            return

        metadata_path = model_path / "metadata.json"
        if metadata_path.exists():
            import json
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            dk.training_features_list = metadata.get("training_features_list", [])
            dk.label_list = metadata.get("label_list", [])
            dk.unique_classes = metadata.get("unique_classes", {})
            dk.unique_class_list = metadata.get("unique_class_list", [])
            logger.info(
                f"{pair}: 从 metadata 加载特征列表 "
                f"({len(dk.training_features_list)} 个特征): {dk.training_features_list[:5]}..."
            )
        else:
            raise ValueError(f"{pair}: 未找到 metadata.json，无法加载特征列表")

        fp_path = model_path / "feature_pipeline.pkl"
        lp_path = model_path / "label_pipeline.pkl"

        if fp_path.exists():
            dk.feature_pipeline = joblib.load(fp_path)
        else:
            raise ValueError(f"{pair}: 未找到 feature_pipeline.pkl")

        if lp_path.exists():
            dk.label_pipeline = joblib.load(lp_path)
        else:
            dk.label_pipeline = Pipeline([])
