"""XGBoost 极值选股模型 - 使用动态阈值计算。"""

import logging

import numpy as np
import polars as pl
import scipy.stats
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import MinMaxScaler
from xgboost import XGBRegressor
from vnpy.alpha.dataset import AlphaDataset, Segment
from vnpy.alpha.model import AlphaModel


# 极值检测常量
DEFAULT_MAXIMA_THRESHOLD = 2.0
DEFAULT_MINIMA_THRESHOLD = -2.0
DEFAULT_DI_CUTOFF = 2.0
PREDICTION_COL = "&s-extrema"


class XGBoostExtremaModel(AlphaModel):
    """用于预测股票价格极值（最高点/最低点）的 XGBoost 模型。

    使用动态阈值机制，基于预测值的分布计算阈值。
    使用 DI (Deviation Index) 值和 Weibull 分布计算 cutoff。
    DI 值使用 IsolationForest 多变量异常检测算法（与 freqtrade datasieve 类似）。
    """

    # 类级别常量：预测列名和阈值
    PREDICTION_COL = PREDICTION_COL
    DEFAULT_MAXIMA_THRESHOLD = DEFAULT_MAXIMA_THRESHOLD
    DEFAULT_MINIMA_THRESHOLD = DEFAULT_MINIMA_THRESHOLD
    DEFAULT_DI_CUTOFF = DEFAULT_DI_CUTOFF

    def __init__(
        self,
        learning_rate: float = 0.1,
        max_depth: int = 6,
        n_estimators: int = 100,
        early_stopping_rounds: int = 50,
        eval_metric: str = "rmse",
        seed: int | None = None,
        # 动态阈值参数
        num_candles: int = 100,
        label_period_candles: int = 10,
        # 特征管道（用于 inverse_transform）
        feature_pipeline=None,
        # 是否对标签进行缩放（像 freqtrade 一样）
        scale_label: bool = True,
    ):
        """初始化 XGBoost 极值模型。

        参数
        ----------
        learning_rate : float
            XGBoost 学习率
        max_depth : int
            树的最大深度
        n_estimators : int
             boosting 轮数
        early_stopping_rounds : int
            提前停止轮数
        eval_metric : str
            评估指标
        seed : int | None
            随机种子
        num_candles : int
            动态阈值计算的 K 线数量（用于 frequency 计算）
        label_period_candles : int
            标签周期的 K 线数（用于频率计算）
        feature_pipeline : optional
            FreqaiFeaturePipeline 实例，用于特征的 inverse_transform
        scale_label : bool
            是否对标签进行缩放（像 freqtrade 一样），默认 True
        """
        self.params: dict = {
            "objective": "reg:squarederror",
            "learning_rate": learning_rate,
            "max_depth": max_depth,
            "seed": seed,
        }

        self.n_estimators: int = n_estimators
        self.early_stopping_rounds: int = early_stopping_rounds
        self.eval_metric: str = eval_metric

        # 动态阈值参数
        self.num_candles: int = num_candles
        self.label_period_candles: int = label_period_candles

        # 特征管道（用于 inverse_transform）
        self.feature_pipeline = feature_pipeline

        # 标签缩放器
        self.scale_label = scale_label
        self._label_scaler: MinMaxScaler | None = None

        # 模型状态
        self.model: XGBRegressor | None = None
        self._feature_names: list[str] | None = None
        self._last_result_df: pl.DataFrame | None = None
        self._di_model: IsolationForest | None = None

    def _fit_di_model(self, features: np.ndarray) -> None:
        """训练 DI（异常检测）模型。

        使用 IsolationForest 在特征空间中进行多变量异常检测。
        这与 freqtrade 使用的 datasieve OutlierDetector 功能类似。

        参数
        ----------
        features : np.ndarray
            特征数据 (n_samples, n_features)
        """
        self._di_model = IsolationForest(
            n_estimators=100,
            contamination=0.1,  # 假设 10% 的异常值
            random_state=self.params.get("seed"),
            n_jobs=-1,
        )
        self._di_model.fit(features)

    def _compute_di_values(self, features: np.ndarray) -> np.ndarray:
        """从特征数据计算 DI（偏离指标）值。

        使用 IsolationForest 的 anomaly_score 方法计算每个样本的异常分数。
        这与 freqtrade datasieve 的 OutlierDetector 功能一致。

        参数
        ----------
        features : np.ndarray
            特征数据 (n_samples, n_features)

        返回
        -------
        np.ndarray
            DI 值（异常分数），形状为 (n_samples,)

        注意
        -----
        - 需要在调用前确保已训练好 DI 模型 (_fit_di_model)
        - 分数越负表示越异常
        """
        if self._di_model is None:
            raise ValueError("DI 模型尚未训练。请先调用 _fit_di_model()。")

        # 使用 IsolationForest 的 decision_function 获取异常分数
        # 分数越负表示越异常（normal=0, outlier<0）
        di_values = self._di_model.decision_function(features)
        return di_values

    def _compute_dynamic_thresholds(
        self,
        pred_df_full: pl.DataFrame,
    ) -> tuple[float, float, float, tuple, float, float]:
        """从预测数据计算动态阈值和 DI cutoff。

        使用排序后的预测值，根据顶部和底部 frequency 计算阈值。
        使用 Weibull 分布拟合 DI 值计算 cutoff。

        参数
        ----------
        pred_df_full : pl.DataFrame
            包含 PREDICTION_COL 和 DI_values 列的预测 DataFrame

        返回
        -------
        tuple[float, float, float, tuple, float, float]
            (maxima_threshold, minima_threshold, di_cutoff, di_params, di_mean, di_std) 元组
        """
        if len(pred_df_full) == 0:
            return (
                DEFAULT_MAXIMA_THRESHOLD,
                DEFAULT_MINIMA_THRESHOLD,
                DEFAULT_DI_CUTOFF,
                (0.0, 0.0, 0.0),
                0.0,
                0.0,
            )

        # 按值降序排序预测
        predictions = pred_df_full.sort(self.PREDICTION_COL, descending=True)

        # 基于 frequency 计算阈值
        frequency = max(1, int(self.num_candles / (self.label_period_candles * 2)))
        frequency = min(frequency, len(predictions))

        # 从顶部和底部预测计算阈值
        max_pred = predictions.head(frequency)[self.PREDICTION_COL].mean()
        min_pred = predictions.tail(frequency)[self.PREDICTION_COL].mean()

        # 处理 NaN 或 None 值
        if max_pred is None or np.isnan(max_pred):
            max_pred = DEFAULT_MAXIMA_THRESHOLD
        if min_pred is None or np.isnan(min_pred):
            min_pred = DEFAULT_MINIMA_THRESHOLD

        # 计算 DI cutoff（使用 Weibull 分布）
        di_values = pred_df_full["DI_values"].to_numpy().astype(float)
        di_mean = float(np.mean(di_values))
        di_std = float(np.std(di_values))

        # 使用 Weibull 分布拟合 DI 值
        try:
            di_params = scipy.stats.weibull_min.fit(di_values)
            di_cutoff = float(scipy.stats.weibull_min.ppf(0.999, *di_params))
        except Exception:
            # 拟合失败时使用默认值
            di_params = (0.0, 0.0, 0.0)
            di_cutoff = DEFAULT_DI_CUTOFF

        return (
            float(max_pred),
            float(min_pred),
            di_cutoff,
            di_params,
            di_mean,
            di_std,
        )

    def fit(self, dataset: AlphaDataset) -> None:
        """
        Fit the XGBoost model using the dataset.

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset containing features and labels

        返回
        -------
        None
        """
        X_train, y_train, X_valid, y_valid = self._prepare_data(dataset)

        # 存储标签统计信息用于参考
        self._label_min = float(np.nanmin(y_train))
        self._label_max = float(np.nanmax(y_train))
        self._label_mean = float(np.nanmean(y_train))
        self._label_std = float(np.nanstd(y_train))

        # 从原始数据获取原始特征用于 DI 训练（避免在缩放后的特征上计算 DI）
        # 注意：_prepare_data 返回的 X_train 可能已经被缩放处理器处理过
        # 我们需要从原始数据集 dataset.df 重新提取原始特征
        # 处理 FilteredDataset 情况（GroupedMultiModel 使用）
        original_dataset = getattr(dataset, '_original_dataset', None)
        source_dataset = original_dataset if original_dataset else dataset

        # 检查原始数据集是否有 df 属性（AlphaDataset 有，FilteredDataset 没有）
        source_df = getattr(source_dataset, 'df', None)
        data_periods = getattr(source_dataset, 'data_periods', None)

        if source_df is not None:
            self._di_feature_cols = [col for col in source_df.columns if col.startswith("%-")]
            if self._di_feature_cols and data_periods is not None:
                # 获取训练期的原始数据
                train_period = data_periods.get(Segment.TRAIN)
                if train_period:
                    raw_train_df = source_df.filter(
                        (pl.col("datetime") >= pl.lit(train_period[0])) &
                        (pl.col("datetime") <= pl.lit(train_period[1]))
                    ).sort(["datetime", "vt_symbol"])

                    if len(raw_train_df) > 0:
                        # 获取处理后数据的 datetime/vt_symbol 用于匹配
                        processed_train_df = dataset.fetch_learn(Segment.TRAIN).sort(["datetime", "vt_symbol"])

                        # 通过 join 确保行匹配
                        matched_df = processed_train_df.select(["datetime", "vt_symbol"]).join(
                            raw_train_df.select(["datetime", "vt_symbol"] + self._di_feature_cols),
                            on=["datetime", "vt_symbol"],
                            how="left"
                        )
                        X_train_raw = matched_df.select(self._di_feature_cols).to_numpy()
                        X_train_raw = np.nan_to_num(X_train_raw, nan=0.0, posinf=1e10, neginf=-1e10)
                        logger = logging.getLogger(__name__)
                        logger.info(f"DI 模型使用原始特征训练，匹配行数：{len(matched_df)}, 特征范围：[{np.min(X_train_raw):.2f}, {np.max(X_train_raw):.2f}]")
                    else:
                        X_train_raw = X_train
                        self._di_feature_cols = []
                else:
                    X_train_raw = X_train
            else:
                X_train_raw = X_train
        else:
            # 无法访问原始数据，回退到使用缩放后的特征
            X_train_raw = X_train
            self._di_feature_cols = []

        logger = logging.getLogger(__name__)
        logger.info(f"原始标签范围：[{self._label_min:.6f}, {self._label_max:.6f}], 均值：{self._label_mean:.6f}")
        logger.info(f"scale_label={self.scale_label}, 准备创建 _label_scaler")

        # 如果设置了 scale_label，对标签进行缩放
        if self.scale_label:
            self._label_scaler = MinMaxScaler(feature_range=(-1, 1))
            y_train = self._label_scaler.fit_transform(y_train.reshape(-1, 1)).ravel()
            y_valid = self._label_scaler.transform(y_valid.reshape(-1, 1)).ravel()
            logger.info(f"缩放后标签范围：[{np.min(y_train):.6f}, {np.max(y_train):.6f}]")
            logger.info(f"_label_scaler 已创建：data_min_={self._label_scaler.data_min_}, data_max_={self._label_scaler.data_max_}")
        else:
            logger.info(f"scale_label=False，跳过标签缩放")

        self.model = XGBRegressor(
            objective="reg:squarederror",
            learning_rate=self.params["learning_rate"],
            max_depth=self.params["max_depth"],
            n_estimators=self.n_estimators,
            random_state=self.params["seed"],
            eval_metric=self.eval_metric,
            early_stopping_rounds=self.early_stopping_rounds,
        )

        self.model.fit(
            X_train,
            y_train,
            eval_set=[(X_train, y_train), (X_valid, y_valid)],
            verbose=False,
        )

        # 训练 DI 模型（使用原始特征，而非缩放后的特征）
        if hasattr(self, '_di_feature_cols') and len(self._di_feature_cols) > 0:
            self._fit_di_model(X_train_raw)
            logger = logging.getLogger(__name__)
            logger.info(f"DI 模型已在原始特征上训练，共 {len(self._di_feature_cols)} 个特征")
        else:
            # 回退到使用缩放后的特征（不推荐，但保持兼容性）
            self._fit_di_model(X_train)
            logger = logging.getLogger(__name__)
            logger.warning("DI 模型在缩放后的特征上训练，DI 值可能不准确")

        logger = logging.getLogger(__name__)
        logger.info(f"模型训练完成，最佳迭代轮数：{self.model.best_iteration + 1}")

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """使用训练好的模型进行预测，包含阈值计算。

        参数
        ----------
        dataset : AlphaDataset
            包含特征的数据集
        segment : Segment
            要预测的数据段

        返回
        -------
        np.ndarray
            预测结果

        Raises
        ------
        ValueError
            如果模型尚未拟合
        """
        if self.model is None:
            raise ValueError("模型尚未拟合。请先调用 fit()。")

        df = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])

        # 使用与_prepare_data 相同的逻辑：排除标签列（& 前缀）
        # 以及 minima/maxima 列
        feature_cols = [col for col in df.columns[2:] if not col.startswith("&") and col not in ("minima", "maxima")]
        data = df.select(feature_cols).to_numpy()

        predictions = self.model.predict(data)

        # 日志：预测值范围
        logger = logging.getLogger(__name__)
        logger.info(f"模型预测值（缩放空间）范围：[{np.min(predictions):.6f}, {np.max(predictions):.6f}], 均值：{np.mean(predictions):.6f}")
        logger.info(f"scale_label={self.scale_label}, _label_scaler is not None={self._label_scaler is not None}, hasattr={hasattr(self, '_label_scaler')}")
        if hasattr(self, '_label_scaler') and self._label_scaler is not None:
            logger.info(f"_label_scaler: data_min_={self._label_scaler.data_min_}, data_max_={self._label_scaler.data_max_}")
        else:
            logger.warning(f"_label_scaler 不存在或为空！")

        # 如果标签被缩放了，进行 inverse_transform 转换回原始范围
        if self.scale_label and self._label_scaler is not None:
            try:
                predictions = self._label_scaler.inverse_transform(predictions.reshape(-1, 1)).ravel()
                logger.info(f"已执行 inverse_transform，预测值已转换回原始范围")
                logger.info(f"逆转换后预测值范围：[{np.min(predictions):.6f}, {np.max(predictions):.6f}], 均值：{np.mean(predictions):.6f}")
            except Exception as e:
                logger.warning(f"inverse_transform 失败：{e}，使用原始预测值")

        # 使用原始特征计算 DI 值（而非缩放后的特征）
        # 从原始数据集获取原始数据，并通过 join 确保行匹配
        # 处理 FilteredDataset 情况（GroupedMultiModel 使用）
        original_dataset = getattr(dataset, '_original_dataset', None)
        source_dataset = original_dataset if original_dataset else dataset
        source_df = getattr(source_dataset, 'df', None)
        data_periods = getattr(source_dataset, 'data_periods', None)

        try:
            if hasattr(self, '_di_feature_cols') and len(self._di_feature_cols) > 0 and source_df is not None and data_periods is not None:
                # 获取当前 segment 的原始数据
                period = data_periods.get(segment)
                if period:
                    start_dt = pl.lit(period[0])
                    end_dt = pl.lit(period[1])
                    raw_df = source_df.filter(
                        (pl.col("datetime") >= start_dt) & (pl.col("datetime") <= end_dt)
                    ).sort(["datetime", "vt_symbol"])

                    # 检查原始数据中的特征列
                    available_cols = [col for col in self._di_feature_cols if col in raw_df.columns]
                    if len(available_cols) > 0:
                        # 通过 join 确保行与处理后的 df 匹配
                        # df 已经排序，包含 datetime 和 vt_symbol
                        raw_matched = df.select(["datetime", "vt_symbol"]).join(
                            raw_df.select(["datetime", "vt_symbol"] + available_cols),
                            on=["datetime", "vt_symbol"],
                            how="left"
                        )
                        di_data = raw_matched.select(available_cols).to_numpy()
                        di_data = np.nan_to_num(di_data, nan=0.0, posinf=1e10, neginf=-1e10)
                        di_values = self._compute_di_values(di_data)
                        logger.info(f"使用原始特征计算 DI_values（{len(available_cols)} 个特征），"
                                   f"匹配行数：{len(raw_matched)}, DI 范围：[{np.min(di_values):.6f}, {np.max(di_values):.6f}]")
                    else:
                        logger.warning(f"原始数据中找不到 DI 特征列，回退到使用当前数据")
                        di_values = self._compute_di_values(data)
                else:
                    di_values = self._compute_di_values(data)
            else:
                # 没有存储特征列信息或无法访问原始数据，使用当前数据（缩放后的）
                di_values = self._compute_di_values(data)
                if source_df is None:
                    logger.warning(f"无法访问原始数据集 df，DI 在缩放后的特征上计算")
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"使用原始特征计算 DI 失败：{e}，回退到缩放特征")
            di_values = self._compute_di_values(data)

        logger = logging.getLogger(__name__)
        logger.info(f"使用 IsolationForest 计算 DI_values，共 {len(di_values)} 个")
        logger.info(f"DI_values 范围：[{np.min(di_values):.6f}, {np.max(di_values):.6f}], 均值：{np.mean(di_values):.6f}")

        # 构建包含预测值和 DI 值的 result_df
        result_df = pl.DataFrame().with_columns(
            df["vt_symbol"].alias("vt_symbol"),
            df["datetime"].alias("datetime"),
            pl.Series(predictions).alias(self.PREDICTION_COL),
            pl.Series(di_values).alias("DI_values"),
        )

        # 如果设置了 feature_pipeline，将特征转换回原始范围
        if self.feature_pipeline is not None:
            try:
                logger.info(f"feature_pipeline 存在，检查逆转换条件...")
                logger.info(f"feature_pipeline 类型: {type(self.feature_pipeline)}")
                logger.info(f"feature_pipeline.feature_cols: {len(self.feature_pipeline.feature_cols) if self.feature_pipeline.feature_cols else 0}")
                logger.info(f"_data_min 是否存在: {hasattr(self.feature_pipeline, '_data_min')}")
                # 获取特征列（%-前缀的列）
                feature_cols_in_df = [col for col in df.columns if col.startswith("%-")]
                logger.info(f"df 中的特征列数量: {len(feature_cols_in_df)}")
                if feature_cols_in_df:
                    # 选择特征列
                    features_df = df.select(["datetime", "vt_symbol"] + feature_cols_in_df)
                    # 打印逆转换前的特征范围
                    for col in feature_cols_in_df[:3]:
                        logger.info(f"逆转换前 {col} 范围: [{df[col].min():.6f}, {df[col].max():.6f}]")
                    # 逆转换特征
                    features_original_df = self.feature_pipeline.inverse_transform_features(features_df)
                    # 打印逆转换后的特征范围
                    for col in feature_cols_in_df[:3]:
                        logger.info(f"逆转换后 {col} 范围: [{features_original_df[col].min():.6f}, {features_original_df[col].max():.6f}]")
                    # 合并到 result_df
                    result_df = result_df.join(
                        features_original_df.select(["datetime", "vt_symbol"] + feature_cols_in_df),
                        on=["datetime", "vt_symbol"],
                        how="left"
                    )
                    logger.info(f"特征已转换回原始范围，共 {len(feature_cols_in_df)} 个特征")
            except Exception as e:
                logger.warning(f"特征 inverse_transform 失败：{e}")
                import traceback
                logger.warning(traceback.format_exc())

        # 从当前预测数据计算动态阈值（包含 DI cutoff）
        maxima_threshold, minima_threshold, di_cutoff, di_params, di_mean, di_std = self._compute_dynamic_thresholds(result_df)

        # 添加阈值列到 result_df
        result_df = result_df.with_columns(
            pl.Series([maxima_threshold] * len(predictions)).alias("&s-maxima_sort_threshold"),
            pl.Series([minima_threshold] * len(predictions)).alias("&s-minima_sort_threshold"),
            pl.Series([di_cutoff] * len(predictions)).alias("DI_cutoff"),
            pl.Series([di_params[0]] * len(predictions)).alias("DI_value_param1"),
            pl.Series([di_params[1]] * len(predictions)).alias("DI_value_param2"),
            pl.Series([di_params[2]] * len(predictions)).alias("DI_value_param3"),
            pl.Series([di_mean] * len(predictions)).alias("DI_value_mean"),
            pl.Series([di_std] * len(predictions)).alias("DI_value_std"),
            # 标签统计初始化为 0（与 freqtrade 兼容）
            pl.Series([0.0] * len(predictions)).alias("labels_mean"),
            pl.Series([0.0] * len(predictions)).alias("labels_std"),
        )

        self._last_result_df = result_df

        logger = logging.getLogger(__name__)
        logger.info(
            f"预测 {len(predictions)} 个样本，"
            f"阈值：({maxima_threshold:.2f}, {minima_threshold:.2f}), "
            f"DI cutoff: {di_cutoff:.2f}, DI params: {di_params}"
        )

        return predictions

    def get_result_df(self) -> pl.DataFrame | None:
        """获取完整的预测结果 DataFrame。

        返回
        -------
        pl.DataFrame | None
            包含所有预测结果和阈值的 DataFrame，
            如果尚未调用 predict() 则返回 None
        """
        return self._last_result_df

    def _prepare_data(self, dataset: AlphaDataset) -> tuple:
        """准备训练和验证数据（freqtrade 风格）。

        自动通过 '&' 前缀识别标签列（freqtrade 约定）。

        参数
        ----------
        dataset : AlphaDataset
            包含特征和标签的数据集

        返回
        -------
        tuple
            (X_train, y_train, X_valid, y_valid) 元组，作为 numpy 数组

        Raises
        ------
        ValueError
            如果未找到标签列或数据准备失败
        """
        X_train: np.ndarray
        y_train: np.ndarray
        X_valid: np.ndarray
        y_valid: np.ndarray

        for segment in [Segment.TRAIN, Segment.VALID]:
            df = dataset.fetch_learn(segment)
            df = df.sort(["datetime", "vt_symbol"])

            # 通过 '&' 前缀查找标签列（freqtrade 风格）
            label_cols = [col for col in df.columns if col.startswith("&")]
            if not label_cols:
                raise ValueError("未找到标签列（缺少 '&' 前缀的列）")

            # 使用第一个标签列（通常是 &s-extrema）
            label_col = label_cols[0]

            # 特征列：datetime/vt_symbol 之后的所有列，排除标签
            feature_cols = [col for col in df.columns[2:] if not col.startswith("&")]
            data = df.select(feature_cols).to_numpy()
            label = df[label_col].to_numpy()

            # 清理标签中的 NaN 和 inf 值
            label = np.nan_to_num(label, nan=0.0, posinf=1e10, neginf=-1e10)

            # 清理特征中的 NaN 和 inf 值
            data = np.nan_to_num(data, nan=0.0, posinf=1e10, neginf=-1e10)

            if segment == Segment.TRAIN:
                X_train = data
                y_train = label
                self._feature_names = feature_cols
                self._label_col = label_col
            else:
                X_valid = data
                y_valid = label

        return X_train, y_train, X_valid, y_valid

    def detail(self) -> None:
        """显示模型详细信息，包含特征重要性。

        返回
        -------
        None
        """
        if self.model is None:
            logging.info("模型尚未拟合")
            return

        # 获取特征重要性
        importance = self.model.get_booster().get_score(importance_type="gain")
        logging.info("特征重要性（gain）：")
        for feat, score in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20]:
            logging.info(f"  {feat}: {score:.4f}")
