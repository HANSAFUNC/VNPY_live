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

        # Model state
        self.model: xgb.Booster | None = None
        self._feature_names: list[str] | None = None

        # State tracking for progressive thresholds
        self._predictions_history: np.ndarray | None = None
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
