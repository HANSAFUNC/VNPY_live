"""XGBoost extrema selector model with progressive threshold warmup."""

import logging
from typing import cast

import numpy as np
import polars as pl
import scipy.stats
import xgboost as xgb
from xgboost import XGBRegressor
from vnpy.alpha.dataset import AlphaDataset, Segment
from vnpy.alpha.model import AlphaModel


# Constants for extrema detection
MIN_CANDLES_FOR_DYNAMIC = 50
DEFAULT_MAXIMA_THRESHOLD = 2.0
DEFAULT_MINIMA_THRESHOLD = -2.0
DEFAULT_DI_CUTOFF = 2.0
PREDICTION_COL = "&s-extrema"


class XGBoostExtremaModel(AlphaModel):
    """
    XGBoost model for predicting stock price extrema (maxima/minima).

    Uses progressive threshold warmup mechanism from freqtrade for adaptive
    extremum detection based on local statistics.
    """

    # Class-level constants for prediction column name and thresholds
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
        # Progressive threshold parameters
        maxima_threshold: float = DEFAULT_MAXIMA_THRESHOLD,
        minima_threshold: float = DEFAULT_MINIMA_THRESHOLD,
        di_cutoff: float = DEFAULT_DI_CUTOFF,
        min_candles: int = MIN_CANDLES_FOR_DYNAMIC,
        # Dynamic threshold parameters
        num_candles: int = 100,
        label_period_candles: int = 10,
    ):
        """
        Initialize XGBoost Extrema Model.

        Parameters
        ----------
        learning_rate : float
            Learning rate for XGBoost
        max_depth : int
            Maximum depth of trees
        n_estimators : int
            Number of boosting rounds
        early_stopping_rounds : int
            Rounds for early stopping
        eval_metric : str
            Evaluation metric
        seed : int | None
            Random seed
        maxima_threshold : float
            Threshold for detecting maxima (positive DI values)
        minima_threshold : float
            Threshold for detecting minima (negative DI values)
        di_cutoff : float
            Cutoff value for DI-based extremum detection
        min_candles : int
            Minimum candles required for dynamic threshold calculation
        num_candles : int
            Number of candles for dynamic threshold calculation
        label_period_candles : int
            Label period in candles for frequency calculation
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

        # Progressive threshold parameters
        self.maxima_threshold: float = maxima_threshold
        self.minima_threshold: float = minima_threshold
        self.di_cutoff: float = di_cutoff
        self.min_candles: int = min_candles

        # Dynamic threshold parameters
        self.num_candles: int = num_candles
        self.label_period_candles: int = label_period_candles

        # Model state
        self.model: XGBRegressor | None = None
        self._feature_names: list[str] | None = None

        # State tracking for progressive thresholds (freqtrade compatible)
        self._exchange_candles: int | None = None  # Initial candle count at model start
        self._predictions_history: np.ndarray | None = None
        self._prediction_count: int = 0
        self._historic_predictions: dict[str, pl.DataFrame] = {}
        self._dynamic_thresholds: dict[str, float] = {
            "maxima": maxima_threshold,
            "minima": abs(minima_threshold),
        }
        self._last_result_df: pl.DataFrame | None = None

    def _compute_di_values(self, predictions: np.ndarray) -> np.ndarray:
        """
        Compute DI (Divergence Indicator) values from predictions.

        DI values are calculated as z-scores of predictions:
        DI = (prediction - mean) / std

        This normalization helps identify statistical extremes in the
        prediction distribution.

        Parameters
        ----------
        predictions : np.ndarray
            Raw predictions from the model

        Returns
        -------
        np.ndarray
            DI values (z-scores), same shape as input

        Notes
        -----
        - Returns zeros for empty arrays
        - Returns zeros when standard deviation is zero
        """
        # Handle empty array
        if len(predictions) == 0:
            return predictions.copy()

        # Compute statistics
        mean = predictions.mean()
        std = predictions.std()

        # Handle zero std case
        if std == 0:
            return np.zeros_like(predictions)

        # Compute DI values as z-scores
        di_values = (predictions - mean) / std
        return di_values

    def _compute_dynamic_thresholds(
        self,
        pred_df_full: pl.DataFrame,
    ) -> tuple[float, float]:
        """
        Compute dynamic thresholds from prediction data.

        Uses sorted predictions to calculate thresholds based on the top and
        bottom frequency-weighted predictions.

        Parameters
        ----------
        pred_df_full : pl.DataFrame
            DataFrame containing predictions in PREDICTION_COL column

        Returns
        -------
        tuple[float, float]
            Tuple of (maxima_threshold, minima_threshold)
        """
        if len(pred_df_full) == 0:
            return DEFAULT_MAXIMA_THRESHOLD, DEFAULT_MINIMA_THRESHOLD

        # Sort predictions by value
        predictions = pred_df_full.sort(self.PREDICTION_COL, descending=True)

        # Calculate frequency based on num_candles and label_period_candles
        frequency = max(1, int(self.num_candles / (self.label_period_candles * 2)))
        frequency = min(frequency, len(predictions))

        # Calculate thresholds from top and bottom predictions
        max_pred = predictions.head(frequency)[self.PREDICTION_COL].mean()
        min_pred = predictions.tail(frequency)[self.PREDICTION_COL].mean()

        # Handle NaN or None values
        if max_pred is None or np.isnan(max_pred):
            max_pred = DEFAULT_MAXIMA_THRESHOLD
        if min_pred is None or np.isnan(min_pred):
            min_pred = DEFAULT_MINIMA_THRESHOLD

        return float(max_pred), float(min_pred)

    def _get_historic_predictions_df(self, symbol: str | None = None) -> pl.DataFrame:
        """
        Merge all historic predictions across symbols with window limit.

        Uses tail(num_candles) to limit to recent predictions (freqtrade compatible).

        Parameters
        ----------
        symbol : str | None
            Optional symbol to filter. If None, merges all symbols.

        Returns
        -------
        pl.DataFrame
            DataFrame containing historic predictions limited to num_candles,
            in PREDICTION_COL column
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

        # Apply tail(num_candles) window limit (freqtrade compatible)
        if len(pred_df) > self.num_candles:
            pred_df = pred_df.tail(self.num_candles)

        return pred_df

    def _compute_progressive_thresholds(
        self,
        pred_df_full: pl.DataFrame,
        warmup_progress: float,
    ) -> tuple[float, float]:
        """
        Compute progressive thresholds with warmup.

        During warmup period, blends default thresholds with dynamic thresholds
        based on progress through the warmup period.

        Parameters
        ----------
        pred_df_full : pl.DataFrame
            DataFrame containing historical predictions
        warmup_progress : float
            Progress through warmup period (0.0 to 1.0)

        Returns
        -------
        tuple[float, float]
            Tuple of (maxima_threshold, minima_threshold)
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
        """
        Compute progressive DI cutoff using Weibull distribution.

        During warmup period, blends default DI cutoff with dynamic cutoff
        computed from Weibull distribution fitting of historical DI values.

        Parameters
        ----------
        pred_df_full : pl.DataFrame
            DataFrame containing historical DI_values column
        warmup_progress : float
            Progress through warmup period (0.0 to 1.0)

        Returns
        -------
        tuple[float, tuple[float, float, float]]
            Tuple of (cutoff, (shape, loc, scale)) where:
            - cutoff: The computed DI cutoff value
            - shape, loc, scale: Weibull distribution parameters
        """
        if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

        # Extract DI values from historical predictions (freqtrade compatible)
        if "DI_values" not in pred_df_full.columns or len(pred_df_full) < 10:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

        di_values = pred_df_full["DI_values"].to_numpy()
        di_values = di_values[~np.isnan(di_values)]  # Drop NaN values

        if len(di_values) < 10:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

        try:
            # Fit Weibull distribution to historical DI values
            f = scipy.stats.weibull_min.fit(di_values)
            dynamic_cutoff = scipy.stats.weibull_min.ppf(0.999, *f)

            # Blend default and dynamic cutoff based on warmup progress
            cutoff = (
                self.DEFAULT_DI_CUTOFF * (1 - warmup_progress)
                + dynamic_cutoff * warmup_progress
            )

            # Blend Weibull parameters progressively
            params = tuple(
                0.0 * (1 - warmup_progress) + f[i] * warmup_progress
                for i in range(3)
            )

            return cutoff, params
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to compute DI cutoff: {e}")
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)

    def fit(self, dataset: AlphaDataset) -> None:
        """
        Fit the XGBoost model using the dataset.

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset containing features and labels

        Returns
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
        logger.info(f"Model trained with {self.model.best_iteration + 1} rounds")

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        Make predictions using the trained model with threshold calculation.

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset containing features
        segment : Segment
            The segment to make predictions on

        Returns
        -------
        np.ndarray
            Prediction results

        Raises
        ------
        ValueError
            If the model has not been fitted yet
        """
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")

        df = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])

        feature_cols = df.columns[2:-1] if "label" in df.columns else df.columns[2:]
        data = df.select(feature_cols).to_numpy()

        predictions = self.model.predict(data)

        # Record initial exchange candles count (freqtrade compatible)
        if self._exchange_candles is None:
            self._exchange_candles = self._prediction_count
            logger = logging.getLogger(__name__)
            logger.info(f"Initial exchange candles recorded: {self._exchange_candles}")

        self._prediction_count += len(predictions)

        # Compute DI values for current batch
        di_values = self._compute_di_values(predictions)

        # Build initial result_df with predictions and DI values
        result_df = pl.DataFrame().with_columns(
            df["vt_symbol"].alias("vt_symbol"),
            df["datetime"].alias("datetime"),
            pl.Series(predictions).alias(self.PREDICTION_COL),
            pl.Series(di_values).alias("DI_values"),
        )

        # Store predictions by symbol for historic tracking BEFORE computing thresholds
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

        # Get historic predictions with window limit (freqtrade compatible)
        pred_df_full = self._get_historic_predictions_df()

        # Calculate warmup progress (freqtrade style)
        new_predictions = self._prediction_count - self._exchange_candles
        warmup_progress = min(1.0, max(0.0, new_predictions / self.num_candles))

        # Log warmup progress
        if warmup_progress < 1.0:
            progress_pct = int(warmup_progress * 100)
            candles_needed = self.num_candles - new_predictions
            logger = logging.getLogger(__name__)
            logger.info(
                f"Threshold warmup progress: {progress_pct}% "
                f"({new_predictions}/{self.num_candles} new candles, need {candles_needed} more)"
            )
        else:
            logger = logging.getLogger(__name__)
            logger.info(f"Threshold warmup complete, total {new_predictions} new candles")

        # Compute thresholds using stored historic predictions (freqtrade compatible)
        maxima_threshold, minima_threshold = self._compute_progressive_thresholds(
            pred_df_full, warmup_progress
        )
        di_cutoff, di_params = self._compute_progressive_di_cutoff(
            pred_df_full, warmup_progress
        )

        # Compute DI stats for storage (freqtrade compatible)
        di_mean = pred_df_full["DI_values"].mean() if len(pred_df_full) > 0 else 0.0
        di_std = pred_df_full["DI_values"].std() if len(pred_df_full) > 0 else 0.0
        if di_std is None or np.isnan(di_std):
            di_std = 0.0
        if di_mean is None or np.isnan(di_mean):
            di_mean = 0.0

        # Add threshold columns to result_df
        result_df = result_df.with_columns(
            pl.Series([maxima_threshold] * len(predictions)).alias("&s-maxima_sort_threshold"),
            pl.Series([minima_threshold] * len(predictions)).alias("&s-minima_sort_threshold"),
            pl.Series([di_cutoff] * len(predictions)).alias("DI_cutoff"),
            pl.Series([di_params[0]] * len(predictions)).alias("DI_value_param1"),
            pl.Series([di_params[1]] * len(predictions)).alias("DI_value_param2"),
            pl.Series([di_params[2]] * len(predictions)).alias("DI_value_param3"),
            pl.Series([di_mean] * len(predictions)).alias("DI_value_mean"),
            pl.Series([di_std] * len(predictions)).alias("DI_value_std"),
            # Labels stats initialized to 0 (freqtrade compatible)
            pl.Series([0.0] * len(predictions)).alias("labels_mean"),
            pl.Series([0.0] * len(predictions)).alias("labels_std"),
        )

        self._last_result_df = result_df

        logger = logging.getLogger(__name__)
        logger.info(
            f"Predicted {len(predictions)} samples, warmup: {int(warmup_progress * 100)}%, "
            f"thresholds: ({maxima_threshold:.2f}, {minima_threshold:.2f})"
        )

        return predictions

    def get_result_df(self) -> pl.DataFrame | None:
        """
        Get full prediction result DataFrame.

        Returns
        -------
        pl.DataFrame | None
            DataFrame containing all prediction results with thresholds,
            or None if predict() has not been called yet
        """
        return self._last_result_df

    def _prepare_data(self, dataset: AlphaDataset) -> tuple:
        """
        Prepare data for training and validation.

        Parameters
        ----------
        dataset : AlphaDataset
            The dataset containing features and labels

        Returns
        -------
        tuple
            Tuple of (X_train, y_train, X_valid, y_valid) as numpy arrays

        Raises
        ------
        ValueError
            If data preparation fails
        """
        X_train: np.ndarray
        y_train: np.ndarray
        X_valid: np.ndarray
        y_valid: np.ndarray

        for segment in [Segment.TRAIN, Segment.VALID]:
            df = dataset.fetch_learn(segment)
            df = df.sort(["datetime", "vt_symbol"])
            feature_cols = df.columns[2:-1]
            data = df.select(feature_cols).to_numpy()
            label = df["label"].to_numpy()

            if segment == Segment.TRAIN:
                X_train = data
                y_train = label
                self._feature_names = feature_cols
            else:
                X_valid = data
                y_valid = label

        return X_train, y_train, X_valid, y_valid

    def detail(self) -> None:
        """
        Display model details with feature importance.

        Returns
        -------
        None
        """
        if self.model is None:
            logging.info("Model not fitted yet")
            return

        # Get feature importance
        importance = self.model.get_booster().get_score(importance_type="gain")
        logging.info("Feature importance (gain):")
        for feat, score in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20]:
            logging.info(f"  {feat}: {score:.4f}")
