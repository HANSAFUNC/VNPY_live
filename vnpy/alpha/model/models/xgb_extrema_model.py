"""XGBoost extrema selector model with progressive threshold warmup."""

import logging
from typing import cast

import numpy as np
import polars as pl
import scipy.stats
import xgboost as xgb

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
        self.model: xgb.Booster | None = None
        self._feature_names: list[str] | None = None

        # State tracking for progressive thresholds
        self._predictions_history: np.ndarray | None = None
        self._prediction_count: int = 0
        self._historic_predictions: dict[str, pl.DataFrame] = {}
        self._dynamic_thresholds: dict[str, float] = {
            "maxima": maxima_threshold,
            "minima": abs(minima_threshold),
        }

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

    def _get_historic_predictions_df(self) -> pl.DataFrame:
        """
        Merge all historic predictions across symbols.

        Returns
        -------
        pl.DataFrame
            DataFrame containing all historic predictions in PREDICTION_COL column
        """
        if not self._historic_predictions:
            return pl.DataFrame().with_columns(
                pl.Series(self.PREDICTION_COL, [])
            )
        return pl.concat(list(self._historic_predictions.values()))

    def _compute_progressive_thresholds(
        self,
        predictions: np.ndarray,
        warmup_progress: float,
    ) -> tuple[float, float]:
        """
        Compute progressive thresholds with warmup.

        During warmup period, blends default thresholds with dynamic thresholds
        based on progress through the warmup period.

        Parameters
        ----------
        predictions : np.ndarray
            Current predictions for threshold calculation
        warmup_progress : float
            Progress through warmup period (0.0 to 1.0)

        Returns
        -------
        tuple[float, float]
            Tuple of (maxima_threshold, minima_threshold)
        """
        if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
            return self.DEFAULT_MAXIMA_THRESHOLD, self.DEFAULT_MINIMA_THRESHOLD

        pred_df_full = self._get_historic_predictions_df()
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

        Raises
        ------
        NotImplementedError
            This method is a placeholder for Task 1 skeleton
        """
        raise NotImplementedError("fit method to be implemented in Task 2")

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        Make predictions using the trained model.

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
        NotImplementedError
            This method is a placeholder for Task 1 skeleton
        ValueError
            If the model has not been fitted yet
        """
        raise NotImplementedError("predict method to be implemented in Task 2")

    def _update_progressive_thresholds(self, di_values: np.ndarray) -> None:
        """
        Update dynamic thresholds based on recent DI values distribution.

        Uses progressive warmup mechanism to adapt thresholds based on
        local statistical properties of predictions.

        Parameters
        ----------
        di_values : np.ndarray
            Recent DI values for threshold adaptation
        """
        if len(di_values) < self.min_candles:
            return

        # Update dynamic thresholds based on recent distribution
        positive_extremes = di_values[di_values > 0]
        negative_extremes = di_values[di_values < 0]

        if len(positive_extremes) > 0:
            self._dynamic_thresholds["maxima"] = max(
                self.maxima_threshold,
                np.percentile(positive_extremes, 90) if len(positive_extremes) > 10 else self.maxima_threshold
            )

        if len(negative_extremes) > 0:
            self._dynamic_thresholds["minima"] = max(
                abs(self.minima_threshold),
                abs(np.percentile(negative_extremes, 10)) if len(negative_extremes) > 10 else abs(self.minima_threshold)
            )

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
        NotImplementedError
            This method is a placeholder for Task 2
        """
        raise NotImplementedError("_prepare_data method to be implemented in Task 2")

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
        importance = self.model.get_score(importance_type="gain")
        logging.info("Feature importance (gain):")
        for feat, score in sorted(importance.items(), key=lambda x: x[1], reverse=True)[:20]:
            logging.info(f"  {feat}: {score:.4f}")
