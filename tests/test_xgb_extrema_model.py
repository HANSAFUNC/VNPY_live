import numpy as np
import pytest
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel


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
