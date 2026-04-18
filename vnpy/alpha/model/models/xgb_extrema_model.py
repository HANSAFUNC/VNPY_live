"""XGBoost 极值选股模型 - 使用渐进式阈值预热机制。"""

import logging
from typing import cast

import numpy as np
import polars as pl
import scipy.stats
import xgboost as xgb
from xgboost import XGBRegressor
from vnpy.alpha.dataset import AlphaDataset, Segment
from vnpy.alpha.model import AlphaModel


# 极值检测常量
MIN_CANDLES_FOR_DYNAMIC = 50
DEFAULT_MAXIMA_THRESHOLD = 2.0
DEFAULT_MINIMA_THRESHOLD = -2.0
DEFAULT_DI_CUTOFF = 2.0
PREDICTION_COL = "&s-extrema"


class XGBoostExtremaModel(AlphaModel):
    """用于预测股票价格极值（最高点/最低点）的 XGBoost 模型。

    使用来自 freqtrade 的渐进式阈值预热机制，用于自适应
    极值检测。
    """

    # 类级别常量：预测列名和阈值
    PREDICTION_COL = PREDICTION_COL
    DEFAULT_MAXIMA_THRESHOLD = DEFAULT_MAXIMA_THRESHOLD
    DEFAULT_MINIMA_THRESHOLD = DEFAULT_MINIMA_THRESHOLD
    DEFAULT_DI_CUTOFF = DEFAULT_DI_CUTOFF
    MIN_CANDLES_FOR_DYNAMIC = MIN_CANDLES_FOR_DYNAMIC

    def __init__(
        self,
        learning_rate: float = 0.1,
        max_depth: int = 6,
        n_estimators: int = 100,
        early_stopping_rounds: int = 50,
        eval_metric: str = "rmse",
        seed: int | None = None,
        # 渐进式阈值参数
        maxima_threshold: float = DEFAULT_MAXIMA_THRESHOLD,
        minima_threshold: float = DEFAULT_MINIMA_THRESHOLD,
        di_cutoff: float = DEFAULT_DI_CUTOFF,
        min_candles: int = MIN_CANDLES_FOR_DYNAMIC,
        # 动态阈值参数
        num_candles: int = 100,
        label_period_candles: int = 10,
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
        maxima_threshold : float
            检测极大值的阈值（正 DI 值）
        minima_threshold : float
            检测极小值的阈值（负 DI 值）
        di_cutoff : float
            DI 基极值检测的截止值
        min_candles : int
            动态阈值计算所需的最小 K 线数
        num_candles : int
            动态阈值计算的 K 线数量
        label_period_candles : int
            标签周期的 K 线数（用于频率计算）
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

        # 渐进式阈值参数
        self.maxima_threshold: float = maxima_threshold
        self.minima_threshold: float = minima_threshold
        self.di_cutoff: float = di_cutoff
        self.min_candles: int = min_candles

        # 动态阈值参数
        self.num_candles: int = num_candles
        self.label_period_candles: int = label_period_candles

        # 模型状态
        self.model: XGBRegressor | None = None
        self._feature_names: list[str] | None = None

        # 渐进式阈值的状态跟踪（freqtrade 兼容）
        self._exchange_candles: int | None = None  # 模型启动时的初始 K 线计数
        self._predictions_history: np.ndarray | None = None
        self._prediction_count: int = 0
        self._historic_predictions: dict[str, pl.DataFrame] = {}
        self._dynamic_thresholds: dict[str, float] = {
            "maxima": maxima_threshold,
            "minima": abs(minima_threshold),
        }
        self._last_result_df: pl.DataFrame | None = None

    def _compute_di_values(self, predictions: np.ndarray) -> np.ndarray:
        """从预测值计算 DI（偏离指标）值。

        DI 值计算为预测值的 z-score：
        DI = (prediction - mean) / std

        这种标准化有助于识别预测分布中的统计极值。

        参数
        ----------
        predictions : np.ndarray
            模型的原始预测值

        返回
        -------
        np.ndarray
            DI 值（z-score），与输入形状相同

        注意
        -----
        - 空数组返回零
        - 当标准差为零时返回零
        """
        # 处理空数组
        if len(predictions) == 0:
            return predictions.copy()

        # 计算统计量
        mean = predictions.mean()
        std = predictions.std()

        # 处理零标准差情况
        if std == 0:
            return np.zeros_like(predictions)

        # 计算 DI 值为 z-score
        di_values = (predictions - mean) / std
        return di_values

    def _compute_dynamic_thresholds(
        self,
        pred_df_full: pl.DataFrame,
    ) -> tuple[float, float]:
        """从预测数据计算动态阈值。

        使用排序后的预测值，根据顶部和底部频率加权预测计算阈值。

        参数
        ----------
        pred_df_full : pl.DataFrame
            包含 PREDICTION_COL 列的预测 DataFrame

        返回
        -------
        tuple[float, float]
            (maxima_threshold, minima_threshold) 元组
        """
        if len(pred_df_full) == 0:
            return DEFAULT_MAXIMA_THRESHOLD, DEFAULT_MINIMA_THRESHOLD

        # 按值降序排序预测
        predictions = pred_df_full.sort(self.PREDICTION_COL, descending=True)

        # 基于 num_candles 和 label_period_candles 计算频率
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

        return float(max_pred), float(min_pred)

    def _get_historic_predictions_df(self, symbol: str | None = None) -> pl.DataFrame:
        """使用窗口限制合并所有符号的历史预测。

        使用 tail(num_candles) 限制为最近的预测（freqtrade 兼容）。

        参数
        ----------
        symbol : str | None
            可选的符号过滤器。如果为 None，则合并所有符号。

        返回
        -------
        pl.DataFrame
            包含历史预测的 DataFrame，限制为 num_candles，
            在 PREDICTION_COL 列中
        """
        if not self._historic_predictions:
            return pl.DataFrame().with_columns(
                pl.Series(self.PREDICTION_COL, [])
            )

        if symbol is not None:
            if symbol not in self._historic_predictions:
                return pl.DataFrame().with_columns(
                    pl.Series(self.PREDICTION_COL, [])
                )
            pred_df = self._historic_predictions[symbol]
        else:
            pred_df = pl.concat(list(self._historic_predictions.values()))

        # 应用 tail(num_candles) 窗口限制（freqtrade 兼容）
        if len(pred_df) > self.num_candles:
            pred_df = pred_df.tail(self.num_candles)

        return pred_df

    def _compute_progressive_thresholds(
        self,
        pred_df_full: pl.DataFrame,
        warmup_progress: float,
    ) -> tuple[float, float]:
        """使用预热计算渐进式阈值。

        在预热期间，基于预热进度将默认阈值与动态阈值混合。

        参数
        ----------
        pred_df_full : pl.DataFrame
            包含历史预测的 DataFrame
        warmup_progress : float
            预热进度（0.0 到 1.0）

        返回
        -------
        tuple[float, float]
            (maxima_threshold, minima_threshold) 元组
        """
        if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
            return self.DEFAULT_MAXIMA_THRESHOLD, self.DEFAULT_MINIMA_THRESHOLD

        dynamic_maxima, dynamic_minima = self._compute_dynamic_thresholds(pred_df_full)

        maxima_threshold = (
            self.DEFAULT_MAXIMA_THRESHOLD * (1 - warmup_progress)
            + dynamic_maxima * warmup_progress
        )
        minima_threshold = (
            self.DEFAULT_MINIMA_THRESHOLD * (1 - warmup_progress)
            + dynamic_minima * warmup_progress
        )

        return maxima_threshold, minima_threshold

    def _compute_progressive_di_cutoff(
        self,
        pred_df_full: pl.DataFrame,
        warmup_progress: float,
    ) -> tuple[float, tuple[float, float, float]]:
        """使用 Weibull 分布计算渐进式 DI 截止值。

        在预热期间，基于历史 DI 值的 Weibull 分布拟合，
        将默认 DI 截止值与动态截止值混合。

        参数
        ----------
        pred_df_full : pl.DataFrame
            包含历史 DI_values 列的 DataFrame
        warmup_progress : float
            预热进度（0.0 到 1.0）

        返回
        -------
        tuple[float, tuple[float, float, float]]
            (cutoff, (shape, loc, scale)) 元组：
            - cutoff：计算得到的 DI 截止值
            - shape, loc, scale：Weibull 分布参数
        """
        if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

        # 从历史预测中提取 DI 值（freqtrade 风格）
        if "DI_values" not in pred_df_full.columns or len(pred_df_full) < 10:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

        di_values = pred_df_full["DI_values"].to_numpy()
        di_values = di_values[~np.isnan(di_values)]  # 丢弃 NaN 值

        if len(di_values) < 10:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

        try:
            # 拟合 Weibull 分布到历史 DI 值
            f = scipy.stats.weibull_min.fit(di_values)
            dynamic_cutoff = scipy.stats.weibull_min.ppf(0.999, *f)

            # 基于预热进度混合默认和动态截止值
            cutoff = (
                self.DEFAULT_DI_CUTOFF * (1 - warmup_progress)
                + dynamic_cutoff * warmup_progress
            )

            # 渐进式混合 Weibull 参数
            params = tuple(
                0.0 * (1 - warmup_progress) + f[i] * warmup_progress
                for i in range(3)
            )

            return cutoff, params
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"计算 DI 截止值失败：{e}")
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

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

        # 记录初始交易所 K 线计数（freqtrade 兼容）
        if self._exchange_candles is None:
            self._exchange_candles = self._prediction_count
            logger = logging.getLogger(__name__)
            logger.info(f"已记录初始交易所 K 线数：{self._exchange_candles}")

        self._prediction_count += len(predictions)

        # 计算当前批次的 DI 值
        di_values = self._compute_di_values(predictions)

        # 构建包含预测值和 DI 值的初始 result_df
        result_df = pl.DataFrame().with_columns(
            df["vt_symbol"].alias("vt_symbol"),
            df["datetime"].alias("datetime"),
            pl.Series(predictions).alias(self.PREDICTION_COL),
            pl.Series(di_values).alias("DI_values"),
        )

        # 在计算阈值之前，按符号存储预测值用于历史跟踪
        symbols = df["vt_symbol"].to_numpy()
        unique_symbols = np.unique(symbols)

        for symbol in unique_symbols:
            symbol_df = result_df.filter(pl.col("vt_symbol") == symbol)
            if symbol not in self._historic_predictions:
                self._historic_predictions[symbol] = symbol_df
            else:
                self._historic_predictions[symbol] = pl.concat(
                    [self._historic_predictions[symbol], symbol_df]
                )

        # 获取带有窗口限制的历史预测（freqtrade 兼容）
        pred_df_full = self._get_historic_predictions_df()

        # 计算预热进度（freqtrade 风格）
        new_predictions = self._prediction_count - self._exchange_candles
        warmup_progress = min(1.0, max(0.0, new_predictions / self.num_candles))

        # 记录预热进度
        if warmup_progress < 1.0:
            progress_pct = int(warmup_progress * 100)
            candles_needed = self.num_candles - new_predictions
            logger = logging.getLogger(__name__)
            logger.info(
                f"阈值预热进度：{progress_pct}% "
                f"({new_predictions}/{self.num_candles} 根新 K 线，还需要 {candles_needed} 根)"
            )
        else:
            logger = logging.getLogger(__name__)
            logger.info(f"阈值预热完成，共 {new_predictions} 根新 K 线")

        # 使用存储的历史预测计算阈值（freqtrade 兼容）
        maxima_threshold, minima_threshold = self._compute_progressive_thresholds(
            pred_df_full, warmup_progress
        )
        di_cutoff, di_params = self._compute_progressive_di_cutoff(
            pred_df_full, warmup_progress
        )

        # 计算 DI 统计值用于存储（freqtrade 兼容）
        di_mean = pred_df_full["DI_values"].mean() if len(pred_df_full) > 0 else 0.0
        di_std = pred_df_full["DI_values"].std() if len(pred_df_full) > 0 else 0.0
        if di_std is None or np.isnan(di_std):
            di_std = 0.0
        if di_mean is None or np.isnan(di_mean):
            di_mean = 0.0

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
            # 标签统计初始化为 0（freqtrade 兼容）
            pl.Series([0.0] * len(predictions)).alias("labels_mean"),
            pl.Series([0.0] * len(predictions)).alias("labels_std"),
        )

        self._last_result_df = result_df

        logger = logging.getLogger(__name__)
        logger.info(
            f"预测 {len(predictions)} 个样本，预热：{int(warmup_progress * 100)}%, "
            f"阈值：({maxima_threshold:.2f}, {minima_threshold:.2f})"
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

    def get_thresholds(self, dataset: AlphaDataset) -> tuple[float, float]:
        """从训练数据计算极大值和极小值阈值。

        参数
        ----------
        dataset : AlphaDataset
            包含带有标签列的训练数据的数据集

        返回
        -------
        tuple[float, float]
            (maxima_threshold, minima_threshold) 元组
            - maxima_threshold: &s-extrema 的 90% 分位数（卖出信号阈值）
            - minima_threshold: &s-extrema 的 10% 分位数（买入信号阈值）
        """
        train_df = dataset.fetch_learn(Segment.TRAIN)
        label_cols = [col for col in train_df.columns if col.startswith("&")]
        if not label_cols:
            raise ValueError("未找到标签列（缺少 '&' 前缀的列）")

        label_col = label_cols[0]
        maxima_threshold = train_df[label_col].quantile(0.9).item()
        minima_threshold = train_df[label_col].quantile(0.1).item()

        return maxima_threshold, minima_threshold
