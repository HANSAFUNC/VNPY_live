import numpy as np
import polars as pl
import pytest
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel, PREDICTION_COL


class TestDIValuesComputation:
    """Test DI values calculation"""

    def test_compute_di_values_basic(self):
        """Test basic DI values computation"""
        model = XGBoostExtremaModel()
        predictions = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        di_values = model._compute_di_values(predictions)
        mean = predictions.mean()
        std = predictions.std()
        expected = (predictions - mean) / std
        np.testing.assert_array_almost_equal(di_values, expected)

    def test_compute_di_values_zero_std(self):
        """Test DI values when std is zero"""
        model = XGBoostExtremaModel()
        predictions = np.array([2.0, 2.0, 2.0])
        di_values = model._compute_di_values(predictions)
        np.testing.assert_array_equal(di_values, np.zeros_like(predictions))

    def test_compute_di_values_empty(self):
        """Test DI values with empty array"""
        model = XGBoostExtremaModel()
        predictions = np.array([])
        di_values = model._compute_di_values(predictions)
        assert len(di_values) == 0


class TestDynamicThresholds:
    """Test dynamic thresholds calculation"""

    def test_compute_dynamic_thresholds_basic(self):
        """Test dynamic thresholds from sorted predictions"""
        model = XGBoostExtremaModel()
        model.num_candles = 100
        model.label_period_candles = 10

        # Create predictions with clear extrema at tails
        predictions = np.concatenate([
            np.array([5.0, 4.5, 4.0, 3.5, 3.0]),
            np.zeros(90),
            np.array([-3.0, -3.5, -4.0, -4.5, -5.0])
        ])
        # Use Series to create DataFrame to avoid segfault
        pred_df = pl.DataFrame().with_columns(
            pl.Series(PREDICTION_COL, predictions)
        )

        maxima, minima = model._compute_dynamic_thresholds(pred_df)
        assert abs(maxima - 4.0) < 0.5
        assert abs(minima - (-4.0)) < 0.5

    def test_compute_dynamic_thresholds_empty(self):
        """Test dynamic thresholds with empty DataFrame"""
        model = XGBoostExtremaModel()
        pred_df = pl.DataFrame().with_columns(
            pl.Series(PREDICTION_COL, [])
        )
        maxima, minima = model._compute_dynamic_thresholds(pred_df)
        assert isinstance(maxima, float)
        assert isinstance(minima, float)
