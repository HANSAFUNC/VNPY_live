"""StockAI 回归模型基类 - 完全复刻 FreqAI BaseRegressionModel"""

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


class BaseRegressionModel(IStockaiModel):
    """
    回归模型基类 - 完全复刻 FreqAI BaseRegressionModel

    实现了通用的训练和预测流程:
    1. 特征/标签过滤
    2. 数据分割
    3. 管道拟合和转换
    4. 模型训练/预测

    子类只需要实现 fit() 方法
    """

    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        通用训练流程 - 完全复刻 FreqAI

        步骤:
        1. 识别特征和标签
        2. 过滤特征和标签 (删除 NaN 行)
        3. 分割训练/测试集
        4. 定义管道
        5. 拟合管道
        6. 转换数据
        7. 训练模型
        8. 保存模型和管道

        参数:
            df: 已包含特征 (%-前缀) 和标签 (&-前缀) 的 DataFrame
            pair: 股票代码
            dk: 数据厨房

        返回:
            训练好的模型
        """
        logger.info(f"开始训练: {pair}")

        # 1. 识别特征和标签
        dk.find_features(df)
        dk.find_labels(df)

        # 2. 过滤特征和标签 (训练模式 - 删除 NaN 行)
        features_df, labels_df = dk.filter_features(
            unfiltered_df=df,
            training_feature_list=dk.training_features_list,
            label_list=dk.label_list,
            training_filter=True,
        )

        # 3. 分割数据
        data_dict = dk.make_train_test_datasets(features_df, labels_df)

        # 4. 计算标签统计（FreqAI 风格）
        # 在非实时模式下调用 fit_labels
        if not self.config.get("fit_live_predictions_candles", 0) or not dk.config.get("live", False):
            dk.fit_labels()

        # 5. 定义管道
        dk.feature_pipeline = self.define_data_pipeline()
        dk.label_pipeline = self.define_label_pipeline()

        # 5. 拟合管道 (datasieve 需要设置 feature_list)
        logger.info(f"{pair}: 拟合特征管道...")
        dk.feature_pipeline.feature_list = dk.training_features_list
        dk.feature_pipeline.fit(data_dict["train_features"])
        # 更新特征列表（VarianceThreshold 可能移除了一些特征）
        dk.training_features_list = dk.feature_pipeline.feature_list

        # 检查标签数据
        train_labels_raw = data_dict["train_labels"]
        if np.isnan(train_labels_raw).any() or np.isinf(train_labels_raw).any():
            logger.error(f"{pair}: 训练标签包含 NaN/inf，将被替换为 0")
            train_labels_raw = np.nan_to_num(train_labels_raw, nan=0.0, posinf=0.0, neginf=0.0)
            data_dict["train_labels"] = train_labels_raw

        dk.label_pipeline.fit(train_labels_raw.reshape(-1, 1))

        # 6. 转换数据 (datasieve Pipeline 返回 (data, outliers, extra))
        X_train, _, _ = dk.feature_pipeline.transform(data_dict["train_features"], outlier_check=True)
        y_train, _, _ = dk.label_pipeline.transform(
            data_dict["train_labels"].reshape(-1, 1)
        )
        y_train = y_train.ravel()

        data_dict["train_features"] = X_train
        data_dict["train_labels"] = y_train

        if len(data_dict["test_features"]) > 0:
            X_test, _, _ = dk.feature_pipeline.transform(data_dict["test_features"], outlier_check=True)
            y_test, _, _ = dk.label_pipeline.transform(
                data_dict["test_labels"].reshape(-1, 1)
            )
            y_test = y_test.ravel()
            data_dict["test_features"] = X_test
            data_dict["test_labels"] = y_test

        # 7. 训练模型 (子类实现)
        logger.info(f"训练: {len(X_train)} 样本, {X_train.shape[1]} 特征")
        model = self.fit(data_dict, dk)

        # 8. 保存模型和数据
        self.save_data(model, pair, dk)

        logger.info(f"训练完成: {pair}")
        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> Tuple[pl.DataFrame, np.ndarray]:
        """
        通用预测流程 - 完全复刻 FreqAI

        步骤:
        1. 从 df 识别特征 (确保包含最新特征列)
        2. 加载管道和元数据
        3. 过滤特征 (预测模式 - 使用训练时的特征列表)
        4. 转换特征
        5. 预测
        6. 反向转换
        7. 构建结果

        参数:
            df: 已包含特征的 DataFrame
            dk: 数据厨房

        返回:
            (predictions_df, do_predict)
            - predictions_df: 预测结果 DataFrame (包含 datetime, prediction)
            - do_predict: numpy 数组 (1=可预测, 0=跳过)
        """
        pair = dk.pair

        # 1. 从当前数据识别特征 (FreqAI 风格)
        dk.find_features(df)

        # 2. 加载管道和元数据 (必须先加载，确保使用训练时的特征列表)
        self._load_pipelines(pair, dk)

        # 3. 过滤特征 (预测模式)
        # 关键: 使用从 metadata 加载的 training_features_list，而不是重新识别的
        features_df, _ = dk.filter_features(
            unfiltered_df=df,
            training_feature_list=dk.training_features_list,
            label_list=None,  # 预测时不需要标签
            training_filter=False,
        )

        # 保存 datetime 用于结果对齐
        filtered_datetime = df["datetime"] if "datetime" in df.columns else pl.Series(range(len(features_df)))

        # 存储到 data_dictionary（FreqAI 风格）
        dk.data_dictionary["prediction_features"] = features_df.to_numpy()

        # 4. 转换 (datasieve Pipeline 返回 (data, outliers, extra))
        X, _, _ = dk.feature_pipeline.transform(features_df.to_numpy())

        # 提取 DI 值（如果启用了 DI）
        if "di" in dk.feature_pipeline:
            dk.DI_values = dk.feature_pipeline["di"].di_values
        else:
            dk.DI_values = np.zeros(len(X))

        # 5. 预测 (使用 self.model，在 start 方法中已加载)
        if self.model is None:
            raise ValueError(f"{pair}: 模型未加载，请先调用 start() 或加载模型")
        predictions = self.model.predict(X)

        # 6. 反向转换 (datasieve Pipeline 返回 (data, outliers, extra))
        try:
            predictions_reshaped = predictions.reshape(-1, 1)
            predictions_inverse, _, _ = dk.label_pipeline.inverse_transform(predictions_reshaped)
            predictions = predictions_inverse.ravel()
        except Exception as e:
            logger.error(f"{pair}: 标签管道 inverse_transform 失败: {e}")
            raise

        # 7. 构建结果 - 列名使用标签列名（FreqAI 风格）
        label_name = dk.label_list[0] if dk.label_list else "&target"
        result_df = pl.DataFrame({
            "datetime": filtered_datetime,
            label_name: predictions,
        })

        # 使用 dk.do_predict (由 filter_features 设置)
        do_predict = dk.do_predict

        # 检查预测结果中的 NaN/inf
        valid_mask = np.isfinite(predictions)
        do_predict = do_predict & valid_mask.astype(int)

        logger.info(f"预测完成: {pair}, {len(result_df)} 样本, {do_predict.sum()} 有效")

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
                - train_features: 训练特征 (numpy, 已管道转换)
                - train_labels: 训练标签 (numpy, 已管道转换)
                - test_features: 测试特征 (numpy, 已管道转换, 可能为空)
                - test_labels: 测试标签 (numpy, 已管道转换, 可能为空)
            dk: 数据厨房

        返回:
            训练好的模型
        """
        pass

    def define_data_pipeline(self) -> Pipeline:
        """
        定义特征处理管道（可覆盖）

        使用 datasieve Pipeline - 完全复刻 FreqAI
        支持通过 feature_parameters 配置:
        - principal_component_analysis / pca_n_components
        - use_SVM_to_remove_outliers / svm_params
        - DI_threshold
        - use_DBSCAN_to_remove_outliers / dbscan_eps
        - noise_standard_deviation
        """
        ft_params = self.config.get("feature_parameters", {})

        pipe_steps: list[tuple[str, Any]] = [
            ("variance_threshold", ds.VarianceThreshold(threshold=0)),
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ]

        if ft_params.get("principal_component_analysis", False):
            n_components = ft_params.get("pca_n_components", 0.999)
            pipe_steps.append(("pca", ds.PCA(n_components=n_components)))
            pipe_steps.append(
                ("post-pca-scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1))))
            )
            logger.info("启用 PCA 降维")

        if ft_params.get("use_SVM_to_remove_outliers", False):
            svm_params = ft_params.get("svm_params", {"nu": 0.01, "shuffle": False})
            pipe_steps.append(("svm", ds.SVMOutlierExtractor(**svm_params)))
            logger.info("启用 SVM 异常值检测")

        di_threshold = ft_params.get("DI_threshold", 0)
        if di_threshold > 0:
            pipe_steps.append(
                ("di", ds.DissimilarityIndex(di_threshold=di_threshold, n_jobs=-1))
            )
            logger.info(f"启用 DI 漂移检测 (threshold={di_threshold})")

        if ft_params.get("use_DBSCAN_to_remove_outliers", False):
            dbscan_eps = ft_params.get("dbscan_eps", 0.5)
            pipe_steps.append(("dbscan", ds.DBSCAN(eps=dbscan_eps, n_jobs=-1)))
            logger.info("启用 DBSCAN 异常值检测")

        noise_sigma = ft_params.get("noise_standard_deviation", 0)
        if noise_sigma > 0:
            pipe_steps.append(("noise", ds.Noise(sigma=noise_sigma)))
            logger.info(f"启用噪声注入 (sigma={noise_sigma})")

        return Pipeline(pipe_steps)

    def define_label_pipeline(self) -> Pipeline:
        """
        定义标签处理管道（可覆盖）

        使用 datasieve Pipeline - 完全复刻 FreqAI
        """
        return Pipeline([
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ])

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

        # 保存模型
        self.dd.save_model(pair, model, timestamp)

        # 保存管道
        if dk.feature_pipeline:
            joblib.dump(dk.feature_pipeline, dk.data_path / "feature_pipeline.pkl")
        if dk.label_pipeline:
            joblib.dump(dk.label_pipeline, dk.data_path / "label_pipeline.pkl")

        # 保存特征列表
        import json
        metadata = {
            "pair": pair,
            "timestamp": timestamp,
            "training_features_list": dk.training_features_list,
            "label_list": dk.label_list,
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
                logger.info(
                    f"{pair}: 从内存加载特征列表 "
                    f"({len(dk.training_features_list)} 个特征): {dk.training_features_list[:5]}..."
                )
            if "feature_pipeline" in meta_dict:
                dk.feature_pipeline = meta_dict["feature_pipeline"]
            if "label_pipeline" in meta_dict:
                dk.label_pipeline = meta_dict["label_pipeline"]
            return

        # 从磁盘加载元数据（包含特征列表）- 必须在 filter_features 之前加载
        metadata_path = model_path / "metadata.json"
        if metadata_path.exists():
            import json
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            dk.training_features_list = metadata.get("training_features_list", [])
            dk.label_list = metadata.get("label_list", [])
            logger.info(
                f"{pair}: 从 metadata 加载特征列表 "
                f"({len(dk.training_features_list)} 个特征): {dk.training_features_list[:5]}..."
            )
        else:
            raise ValueError(f"{pair}: 未找到 metadata.json，无法加载特征列表")

        # 加载管道
        fp_path = model_path / "feature_pipeline.pkl"
        lp_path = model_path / "label_pipeline.pkl"

        if fp_path.exists():
            dk.feature_pipeline = joblib.load(fp_path)
        else:
            raise ValueError(f"{pair}: 未找到 feature_pipeline.pkl")

        if lp_path.exists():
            dk.label_pipeline = joblib.load(lp_path)
        else:
            raise ValueError(f"{pair}: 未找到 label_pipeline.pkl")
