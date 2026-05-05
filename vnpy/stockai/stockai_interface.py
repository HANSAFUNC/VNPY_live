"""StockAI 模型接口基类 - 完全复刻 FreqAI IFreqaiModel"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional, Tuple

import numpy as np
import polars as pl

from vnpy.alpha.logger import logger

from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen


class IStockaiModel(ABC):
    """
    StockAI 模型接口 - 完全复刻 FreqAI IFreqaiModel

    职责:
    - 管理训练和预测流程
    - 协调 DataDrawer (持久化存储) 和 DataKitchen (临时数据)
    - 特征计算在策略层完成，本层只识别特征列 (%-前缀) 和标签列 (&-前缀)
    """

    def __init__(self, config: dict, lab: Any):
        """
        初始化模型接口

        参数:
            config: 配置字典
            lab: AlphaLabV2 实例 (数据源)
        """
        self.config = config
        self.lab = lab

        # 路径设置
        self.full_path = Path(config.get("path", "./stockai_data"))
        self.full_path.mkdir(parents=True, exist_ok=True)

        # 全局数据抽屉 (持久化存储)
        self.dd = StockaiDataDrawer(self.full_path, config)

        # 当前数据厨房 (临时，每次训练/预测时创建)
        self.dk: Optional[StockaiDataKitchen] = None

        # 模型引用
        self.model: Optional[Any] = None

        # 特征参数
        self.ft_params = config.get("feature_parameters", {})
        self.data_split_params = config.get("data_split_parameters", {})
        self.model_training_params = config.get("model_training_parameters", {})

        # 运行模式
        self.live = False

        logger.info(f"StockAI 模型接口初始化完成，路径: {self.full_path}")

    def start(
        self,
        train_df: pl.DataFrame,
        predict_df: pl.DataFrame,
        pair: str,
        feature_engineering_fn: Optional[callable] = None,
    ) -> pl.DataFrame:
        """
        主入口 - 从策略层接收数据，执行训练/预测

        参数:
            train_df: 训练数据
            predict_df: 预测数据
            pair: 股票代码
            feature_engineering_fn: 可选的特征计算函数

        返回:
            带预测结果的 DataFrame
        """
        # 创建数据厨房
        dk = StockaiDataKitchen(self.config, pair, self.lab)
        self.dk = dk

        # 检查是否需要训练
        if self.dd.should_retrain(pair):
            logger.info(f"{pair}: 开始训练新模型")

            # 如果提供了特征计算函数，执行特征计算
            train_data = train_df
            if feature_engineering_fn:
                train_data = feature_engineering_fn(train_data)

            # 识别特征列和标签列
            dk.find_features(train_data)
            dk.find_labels(train_data)

            if not dk.training_features_list:
                raise ValueError(f"{pair}: 未找到特征列（需要%-前缀）")
            if not dk.label_list:
                raise ValueError(f"{pair}: 未找到标签列（需要&-前缀）")

            self.model = self.train(train_data, pair, dk)
        else:
            logger.info(f"{pair}: 加载已有模型")
            self.model = self.dd.load_model(pair)
            # 预测时需要加载元数据获取特征列表
            self._load_metadata(pair, dk)

        # 如果提供了特征计算函数，执行特征计算
        predict_data = predict_df
        if feature_engineering_fn:
            predict_data = feature_engineering_fn(predict_data)

        # 识别特征
        dk.find_features(predict_data)

        # 执行预测
        predictions_df, do_predict = self.predict(predict_data, dk)

        # 设置初始返回值 (用于历史预测累积)
        if pair not in self.dd.historic_predictions:
            self.dd.set_initial_return_values(pair, predictions_df, predict_data)

        # 合并预测结果
        result_df = self._attach_predictions(predict_data, predictions_df, dk)

        # 附加返回值到DataFrame (使用 model_return_values)
        result_df = self.dd.attach_return_values_to_return_dataframe(pair, result_df)

        return result_df

    def start_backtesting(
        self,
        df: pl.DataFrame,
        pair: str,
        train_start: str,
        train_end: str,
        predict_start: str,
        predict_end: str,
        feature_engineering_fn: Optional[callable] = None,
    ) -> pl.DataFrame:
        """
        回测入口 - 滑动窗口训练/预测

        参数:
            df: 策略层传入的完整数据 (包含特征)
            pair: 股票代码
            train_start/train_end: 训练期
            predict_start/predict_end: 预测期
            feature_engineering_fn: 特征计算函数

        返回:
            预测期带预测结果的 DataFrame
        """
        # 创建数据厨房
        dk = StockaiDataKitchen(self.config, pair, self.lab)
        self.dk = dk

        # 特征计算
        if feature_engineering_fn:
            df = feature_engineering_fn(df)

        # 识别特征和标签
        dk.find_features(df)
        dk.find_labels(df)

        # 分割训练集和预测集
        train_df = df.filter(
            (pl.col("datetime") >= train_start) & (pl.col("datetime") < train_end)
        )
        predict_df = df.filter(
            (pl.col("datetime") >= predict_start) & (pl.col("datetime") <= predict_end)
        )

        if len(train_df) == 0:
            logger.warning(f"{pair}: 训练集为空")
            return predict_df

        # 训练
        self.model = self.train(train_df, pair, dk)

        # 预测
        predictions_df, do_predict = self.predict(predict_df, dk)

        # 设置初始返回值 (用于历史预测累积)
        if pair not in self.dd.historic_predictions:
            self.dd.set_initial_return_values(pair, predictions_df, predict_df)

        # 合并结果
        result_df = self._attach_predictions(predict_df, predictions_df, dk)

        # 附加返回值到DataFrame (使用 model_return_values)
        result_df = self.dd.attach_return_values_to_return_dataframe(pair, result_df)

        return result_df

    @abstractmethod
    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        训练模型 - 子类必须实现

        参数:
            df: 已包含特征列 (%-前缀) 和标签列 (&-前缀) 的训练数据
            pair: 股票代码
            dk: 数据厨房

        返回:
            训练好的模型对象
        """
        pass

    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        实际模型拟合 - 子类必须实现

        参数:
            data_dictionary: 包含 train_features, train_labels, test_features, test_labels 的字典
            dk: 数据厨房

        返回:
            拟合好的模型
        """
        pass

    @abstractmethod
    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> Tuple[pl.DataFrame, np.ndarray]:
        """
        预测 - 子类必须实现

        参数:
            df: 已包含特征列的预测数据
            dk: 数据厨房

        返回:
            (predictions_df, do_predict)
            - predictions_df: 预测结果 DataFrame
            - do_predict: numpy 数组，指示哪些位置可以预测 (1) 或需要跳过 (0)
        """
        pass

    def define_data_pipeline(self) -> Any:
        """
        定义特征处理管道 - 子类可覆盖

        使用 datasieve Pipeline - 复刻 FreqAI
        """
        import datasieve.transforms as ds
        from datasieve.pipeline import Pipeline
        from datasieve.transforms import SKLearnWrapper
        from sklearn.preprocessing import MinMaxScaler

        return Pipeline([
            ("variance_threshold", ds.VarianceThreshold(threshold=0)),
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ])

    def define_label_pipeline(self) -> Any:
        """
        定义标签处理管道 - 子类可覆盖

        使用 datasieve Pipeline - 复刻 FreqAI
        """
        import datasieve.transforms as ds
        from datasieve.pipeline import Pipeline
        from datasieve.transforms import SKLearnWrapper
        from sklearn.preprocessing import MinMaxScaler

        return Pipeline([
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ])

    def _load_metadata(self, pair: str, dk: StockaiDataKitchen) -> None:
        """
        从元数据加载特征列表和标签列表

        参数:
            pair: 股票代码
            dk: 数据厨房实例
        """
        if pair not in self.dd.pair_dict:
            raise ValueError(f"未找到 {pair} 的模型元数据")

        filename = self.dd.pair_dict[pair]["model_filename"]
        model_path = self.dd.full_path / filename

        # 加载元数据
        metadata_path = model_path / "metadata.json"
        if metadata_path.exists():
            import json
            with open(metadata_path, "r", encoding="utf-8") as f:
                metadata = json.load(f)
            dk.training_features_list = metadata.get("training_features_list", [])
            dk.label_list = metadata.get("label_list", [])
            logger.info(
                f"{pair}: 从元数据加载了 {len(dk.training_features_list)} 个特征"
            )
        else:
            raise ValueError(f"{pair}: 未找到 metadata.json")

    def _attach_predictions(
        self,
        df: pl.DataFrame,
        predictions: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """将预测结果合并到原始 DataFrame"""
        # 删除原始标签列（如果存在），避免与预测结果列名冲突
        label_cols = dk.label_list if dk.label_list else []
        df_cleaned = df.drop(label_cols) if label_cols else df

        # 根据 datetime 合并
        result = df_cleaned.join(predictions, on="datetime", how="left")
        return result

    def save_data(self, model: Any, pair: str, dk: StockaiDataKitchen) -> None:
        """
        保存模型和相关数据到磁盘 (FreqAI风格)

        参数:
            model: 训练好的模型
            pair: 股票代码
            dk: 数据厨房实例
        """
        import json

        # 保存模型
        self.dd.save_model(pair, model, dk.data_path.name.split("_")[-1])

        # 保存管道
        if dk.feature_pipeline:
            joblib.dump(dk.feature_pipeline, dk.data_path / "feature_pipeline.pkl")
        if dk.label_pipeline:
            joblib.dump(dk.label_pipeline, dk.data_path / "label_pipeline.pkl")

        # 构建元数据
        metadata = {
            "pair": pair,
            "data_path": str(dk.data_path),
            "model_filename": dk.model_filename,
            "training_features_list": dk.training_features_list,
            "label_list": dk.label_list,
        }

        # 保存元数据
        with open(dk.data_path / "metadata.json", "w", encoding="utf-8") as f:
            json.dump(metadata, f, indent=2)

        # 更新 meta_data_dictionary (内存缓存)
        if pair not in self.dd.meta_data_dictionary:
            self.dd.meta_data_dictionary[pair] = {}
        self.dd.meta_data_dictionary[pair]["metadata"] = metadata
        self.dd.meta_data_dictionary[pair]["feature_pipeline"] = dk.feature_pipeline
        self.dd.meta_data_dictionary[pair]["label_pipeline"] = dk.label_pipeline

        # 缓存模型
        self.dd.model_dictionary[dk.model_filename] = model

        logger.info(f"模型和数据已保存: {pair}")

    def load_data(self, pair: str, dk: StockaiDataKitchen) -> Any:
        """
        加载模型和相关数据 (FreqAI风格)

        参数:
            pair: 股票代码
            dk: 数据厨房实例

        返回:
            加载的模型
        """
        if pair not in self.dd.pair_dict:
            raise ValueError(f"未找到 {pair} 的模型元数据")

        filename = self.dd.pair_dict[pair]["model_filename"]
        dk.model_filename = filename
        dk.data_path = Path(self.dd.pair_dict[pair]["data_path"])

        # 优先从内存加载 (meta_data_dictionary)
        if pair in self.dd.meta_data_dictionary:
            logger.info(f"{pair}: 从内存缓存加载模型数据")
            meta_dict = self.dd.meta_data_dictionary[pair]
            if "metadata" in meta_dict:
                dk.training_features_list = meta_dict["metadata"].get("training_features_list", [])
                dk.label_list = meta_dict["metadata"].get("label_list", [])
            if "feature_pipeline" in meta_dict:
                dk.feature_pipeline = meta_dict["feature_pipeline"]
            if "label_pipeline" in meta_dict:
                dk.label_pipeline = meta_dict["label_pipeline"]

            # 从内存缓存获取模型
            if pair in self.dd.model_dictionary:
                return self.dd.model_dictionary[pair]

        # 从磁盘加载模型
        model = self.dd.load_model(pair)
        return model
