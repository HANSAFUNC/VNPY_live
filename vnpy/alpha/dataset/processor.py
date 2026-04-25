from datetime import datetime
from typing import Optional, Union, Dict, List, Tuple, Any

import numpy as np
import polars as pl
import datasieve.transforms as ds
from datasieve.transforms import SKLearnWrapper
from datasieve.pipeline import Pipeline
from sklearn.preprocessing import MinMaxScaler

from .utility import to_datetime


class FreqaiFeaturePipeline:
    """Freqtrade FreqAI 风格的特征处理管道

    使用 datasieve 库实现：
    - VarianceThreshold: 移除低方差特征
    - MinMaxScaler: 归一化到 (-1, 1) 范围
    """

    def __init__(
        self,
        threshold: float = 0.0,
        feature_range: Tuple = (-1, 1),
        dataset=None,
        di_threshold: Optional[float] = None,
        n_jobs: int = -1,
    ):
        """初始化管道

        参数
        ----------
        threshold : float
            方差阈值，默认 0.0（移除方差为 0 的特征）
        feature_range : tuple
            MinMaxScaler 缩放范围，默认 (-1, 1)
        dataset : optional
            AlphaDataset 实例，自动拟合并添加处理器
        di_threshold : float, optional
            Dissimilarity Index 阈值，用于异常检测（来自 ft_params.DI_threshold）
        n_jobs : int
            DI 计算的并行线程数，默认 -1（全部核心）
        """
        self.threshold = threshold
        self.feature_range = feature_range
        self.di_threshold = di_threshold
        self.n_jobs = n_jobs
        self.pipeline: Optional[Pipeline] = None
        self.feature_cols: list[str] = []
        self._dataset = dataset

        # 如果传入 dataset，自动拟合并添加处理器
        if dataset is not None:
            self._auto_fit_and_add(dataset)

    def _prepare_data(self, df: pl.DataFrame) -> Tuple[np.ndarray, List[str]]:
        """准备数据

        参数
        ----------
        df : pl.DataFrame
            输入 DataFrame

        返回
        -------
        tuple[np.ndarray, list[str]]
            (X 数组，特征列名列表)
        """
        feature_cols = [col for col in df.columns if col.startswith("%-")]
        if not feature_cols:
            return np.array([]), []

        _df = df.fill_nan(None)
        X = _df.select(feature_cols).to_numpy()
        X = np.nan_to_num(X, nan=0.0)

        return X, feature_cols

    def _auto_fit_and_add(self, dataset) -> None:
        """自动从训练数据拟合并添加处理器"""
        from vnpy.alpha.dataset import Segment

        learn_df = dataset.fetch_learn(Segment.TRAIN)
        self.fit(learn_df)
        dataset.add_processor("infer", self)
        dataset.add_processor("learn", self)

    def fit(self, df: pl.DataFrame) -> "FreqaiFeaturePipeline":
        """拟合管道

        参数
        ----------
        df : pl.DataFrame
            训练数据 DataFrame

        返回
        -------
        FreqaiFeaturePipeline
            self
        """
        X, self.feature_cols = self._prepare_data(df)

        if not self.feature_cols:
            return self

        # 存储原始数据的 min 和 max，用于 inverse_transform
        self._data_min = np.nanmin(X, axis=0)
        self._data_max = np.nanmax(X, axis=0)

        # 存储标签列的 min 和 max（如果存在）
        label_cols = [col for col in df.columns if col.startswith("&")]
        if label_cols:
            label_data = df[label_cols[0]].to_numpy()
            self._label_min = np.nanmin(label_data)
            self._label_max = np.nanmax(label_data)
            self._label_col = label_cols[0]
        else:
            self._label_min = None
            self._label_max = None
            self._label_col = None

        # 创建管道步骤
        pipe_steps = [
            ("const", ds.VarianceThreshold(threshold=self.threshold)),
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=self.feature_range))),
        ]

        # 如果设置了 DI 阈值，添加 DissimilarityIndex 步骤
        if self.di_threshold is not None and self.di_threshold > 0:
            pipe_steps.append(("di", ds.DissimilarityIndex(
                di_threshold=self.di_threshold,
                n_jobs=self.n_jobs
            )))

        # 创建并拟合管道
        self.pipeline = Pipeline(pipe_steps)

        # 设置 feature_list 以便 VarianceThreshold 使用
        self.pipeline.feature_list = self.feature_cols
        self.pipeline.fit(X)
        return self

    def __call__(self, df: pl.DataFrame) -> pl.DataFrame:
        """使实例可调用，作为处理器使用

        参数
        ----------
        df : pl.DataFrame
            输入 DataFrame

        返回
        -------
        pl.DataFrame
            转换后的 DataFrame
        """
        return self.transform(df)

    def transform(self, df: pl.DataFrame) -> pl.DataFrame:
        """转换数据

        参数
        ----------
        df : pl.DataFrame
            输入 DataFrame

        返回
        -------
        pl.DataFrame
            转换后的 DataFrame，如果管道包含 DI 步骤则添加 DI_values 列
        """
        if not self.feature_cols or self.pipeline is None:
            return df

        X, _ = self._prepare_data(df)
        if X.size == 0:
            return df

        # 转换 - datasieve Pipeline 返回 (X_transformed, y, sample_weight)
        X_transformed, _, _ = self.pipeline.transform(X)

        # 获取特征列表（从管道的 VarianceThreshold 步骤）
        try:
            feature_list = self.pipeline["const"].feature_list
        except (KeyError, AttributeError):
            feature_list = self.feature_cols

        # 获取保留的特征
        keep_cols = list(feature_list) if feature_list is not None and len(feature_list) > 0 else self.feature_cols

        # 写回 DataFrame
        pdf = df.to_pandas()
        for i, col in enumerate(keep_cols):
            pdf[col] = X_transformed[:, i]

        # 删除被过滤的特征
        dropped_cols = [col for col in self.feature_cols if col not in keep_cols]
        if dropped_cols:
            pdf = pdf.drop(columns=dropped_cols)

        # 如果管道包含 DI 步骤，从管道中获取 DI_values
        if self.di_threshold is not None and self.di_threshold > 0:
            try:
                di_values = self.pipeline["di"].di_values
                pdf["DI_values"] = di_values
            except (KeyError, AttributeError):
                # DI 步骤不存在或 di_values 不可用
                pass

        return pl.from_pandas(pdf)

    def inverse_transform_predictions(self, predictions: np.ndarray, feature_cols: Optional[List[str]] = None, target_col: Optional[str] = None) -> Union[Dict[str, np.ndarray], np.ndarray]:
        """逆向转换预测值到原始特征空间

        将归一化空间（-1 到 1）的预测值转换回原始数据范围。
        使用 MinMaxScaler 的逆变换公式：
        X_original = X_scaled * (X_max - X_min) + X_min

        参数
        ----------
        predictions : np.ndarray
            模型的预测值（归一化后的空间，形状为 (n_samples,) 或 (n_samples, n_features)）
        feature_cols : list[str], optional
            要逆向转换的特征列名，如果为 None 则使用拟合时的特征列表
        target_col : str, optional
            如果提供，则返回该列的逆向转换结果（用于标签预测值）

        返回
        -------
        dict[str, np.ndarray] | np.ndarray
            逆向转换后的特征字典 {feature_name: values}，如果指定 target_col 则返回对应的数组
        """
        if self.pipeline is None:
            raise ValueError("管道尚未拟合。请先调用 fit()。")

        if not hasattr(self, '_data_min') or not hasattr(self, '_data_max'):
            raise ValueError("管道未存储原始数据统计信息。请重新拟合。")

        # 获取特征列表
        if feature_cols is None:
            try:
                feature_cols = self.pipeline["const"].feature_list
            except (KeyError, AttributeError):
                feature_cols = self.feature_cols

        if not feature_cols:
            return {}

        n_features = len(feature_cols)

        # 处理预测值
        if predictions.ndim == 1:
            # 如果是 1D 预测，假设所有特征使用相同的预测值
            X_scaled = np.tile(predictions.reshape(-1, 1), (1, n_features))
        else:
            X_scaled = predictions

        # 确保特征数量匹配
        if X_scaled.shape[1] != n_features:
            raise ValueError(f"预测值的特征数量 ({X_scaled.shape[1]}) 与拟合时的特征数量 ({n_features}) 不匹配")

        # 从 MinMaxScaler 获取缩放参数
        try:
            scaler = self.pipeline["scaler"].sklearn_transformer
            data_min = scaler.data_min_
            data_max = scaler.data_max_
        except (KeyError, AttributeError):
            # 如果无法从 scaler 获取，使用存储的统计信息
            data_min = self._data_min
            data_max = self._data_max

        # 逆向转换公式（MinMaxScaler）
        feature_range = self.feature_range
        range_diff = feature_range[1] - feature_range[0]

        # 转换回 [0, 1] 范围
        X_std = (X_scaled - feature_range[0]) / range_diff

        # 转换回原始范围
        X_original = X_std * (data_max - data_min) + data_min

        # 如果指定了 target_col，返回第一个特征的转换结果
        if target_col:
            return X_original[:, 0]

        # 返回字典
        return {col: X_original[:, i] for i, col in enumerate(feature_cols)}

    def inverse_transform_features(self, df: pl.DataFrame) -> pl.DataFrame:
        """将缩放后的特征数据转换回原始范围

        使用 MinMaxScaler 的逆变换公式将特征列从 (-1, 1) 转换回原始范围。

        参数
        ----------
        df : pl.DataFrame
            包含缩放后特征的 DataFrame

        返回
        -------
        pl.DataFrame
            特征已转换回原始范围的 DataFrame
        """
        if self.pipeline is None:
            raise ValueError("管道尚未拟合。请先调用 fit()。")

        if not hasattr(self, '_data_min') or not hasattr(self, '_data_max'):
            raise ValueError("管道未存储原始数据统计信息。请重新拟合。")

        # 从 MinMaxScaler 获取缩放参数
        try:
            scaler = self.pipeline["scaler"].sklearn_transformer
            data_min = scaler.data_min_
            data_max = scaler.data_max_
        except (KeyError, AttributeError):
            data_min = self._data_min
            data_max = self._data_max

        # 获取特征列表
        feature_cols = self.feature_cols
        if not feature_cols:
            return df

        # 创建新的 DataFrame
        result_df = df.clone()

        # 逆向转换公式
        feature_range = self.feature_range
        range_diff = feature_range[1] - feature_range[0]

        for i, col in enumerate(feature_cols):
            if col in result_df.columns:
                # 获取原始值
                scaled_values = result_df[col].to_numpy()
                # 转换回 [0, 1] 范围
                X_std = (scaled_values - feature_range[0]) / range_diff
                # 转换回原始范围
                X_original = X_std * (data_max[i] - data_min[i]) + data_min[i]
                # 更新 DataFrame
                result_df = result_df.with_columns(pl.Series(X_original).alias(col))

        return result_df

    def inverse_transform_label(self, predictions: np.ndarray) -> np.ndarray:
        """逆向转换标签预测值到原始范围

        使用标签列的 min/max 将归一化空间（-1 到 1）的预测值转换回原始数据范围。

        参数
        ----------
        predictions : np.ndarray
            模型的预测值（归一化后的空间，形状为 (n_samples,)）

        返回
        -------
        np.ndarray
            逆向转换后的预测值
        """
        if self.pipeline is None:
            raise ValueError("管道尚未拟合。请先调用 fit()。")

        if not hasattr(self, '_label_min') or not hasattr(self, '_label_max') or self._label_min is None:
            raise ValueError("管道未存储标签统计信息。拟合时未找到标签列。")

        # 逆向转换公式（MinMaxScaler）
        feature_range = self.feature_range
        range_diff = feature_range[1] - feature_range[0]

        # 转换回 [0, 1] 范围
        y_std = (predictions - feature_range[0]) / range_diff

        # 转换回原始标签范围
        y_original = y_std * (self._label_max - self._label_min) + self._label_min

        return y_original

    def fit_transform(self, df: pl.DataFrame) -> pl.DataFrame:
        """拟合并转换

        参数
        ----------
        df : pl.DataFrame
            输入 DataFrame

        返回
        -------
        pl.DataFrame
            转换后的 DataFrame
        """
        self.fit(df)
        return self.transform(df)


def process_freqai_feature_pipeline(
    df: pl.DataFrame,
    pipeline: FreqaiFeaturePipeline
) -> pl.DataFrame:
    """FreqAI 特征处理管道处理器

    参数
    ----------
    df : pl.DataFrame
        输入 DataFrame
    pipeline : FreqaiFeaturePipeline
        已拟合的 FreqaiFeaturePipeline 实例

    返回
    -------
    pl.DataFrame
        转换后的 DataFrame
    """
    return pipeline.transform(df)


def process_drop_na(df: pl.DataFrame, names: Optional[List[str]] = None) -> pl.DataFrame:
    """Remove rows with missing values"""
    if names is None:
        names = df.columns[2:-1]

    for name in names:
        df = df.with_columns(
            pl.col(name).fill_nan(None)
        )
    df = df.drop_nulls(subset=names)
    return df


def process_fill_na(df: pl.DataFrame, fill_value: float, fill_label: bool = True) -> pl.DataFrame:
    """Fill missing values"""
    if fill_label:
        df = df.fill_null(fill_value)
        df = df.fill_nan(fill_value)
    else:
        df = df.with_columns(
            [pl.col(col).fill_null(fill_value).fill_nan(fill_value) for col in df.columns[2:-1]]
        )
    return df


def process_cs_norm(
    df: pl.DataFrame,
    names: list[str],
    method: str         # robust/zscore
) -> pl.DataFrame:
    """Cross-sectional normalization"""
    _df: pl.DataFrame = df.fill_nan(None)

    # Median method
    if method == "robust":
        for col in names:
            df = df.with_columns(
                _df.select(
                    (pl.col(col) - pl.col(col).median()).over("datetime").alias(col),
                )
            )

            df = df.with_columns(
                df.select(
                    pl.col(col).abs().median().over("datetime").alias("mad"),
                )
            )

            df = df.with_columns(
                (pl.col(col) / pl.col("mad") / 1.4826).clip(-3, 3).alias(col)
            ).drop(["mad"])
    # Z-Score method
    else:
        for col in names:
            df = df.with_columns(
                _df.select(
                    pl.col(col).mean().over("datetime").alias("mean"),
                    pl.col(col).std().over("datetime").alias("std"),
                )
            )

            df = df.with_columns(
                (pl.col(col) - pl.col("mean")) / pl.col("std").alias(col)
            ).drop(["mean", "std"])

    return df


def process_robust_zscore_norm(
    df: pl.DataFrame,
    fit_start_time: Optional[Union[datetime, str]] = None,
    fit_end_time: Optional[Union[datetime, str]] = None,
    clip_outlier: bool = True
) -> pl.DataFrame:
    """Robust Z-Score normalization"""
    _df: pl.DataFrame = df.fill_nan(None)

    if fit_start_time and fit_end_time:
        fit_start_time = to_datetime(fit_start_time)
        fit_end_time = to_datetime(fit_end_time)
        _df = _df.filter((pl.col("datetime") >= fit_start_time) & (pl.col("datetime") <= fit_end_time))

    cols = df.columns[2:-1]
    X = _df.select(cols).to_numpy()

    mean_train = np.nanmedian(X, axis=0)
    std_train = np.nanmedian(np.abs(X - mean_train), axis=0)
    std_train += 1e-12
    std_train *= 1.4826

    for name in cols:
        normalized_col = (
            (pl.col(name) - mean_train[cols.index(name)]) / std_train[cols.index(name)]
        ).cast(pl.Float64)

        if clip_outlier:
            normalized_col = normalized_col.clip(-3, 3)

        df = df.with_columns(normalized_col.alias(name))

    return df


def process_cs_rank_norm(df: pl.DataFrame, names: list[str]) -> pl.DataFrame:
    """Cross-sectional rank normalization"""
    _df: pl.DataFrame = df.fill_nan(None)

    _df = _df.with_columns([
        ((pl.col(col).rank("average").over("datetime") / pl.col("datetime").count().over("datetime")) - 0.5) * 3.46
        for col in names
    ])

    df = df.with_columns([
        _df[col].alias(col) for col in names
    ])

    return df
