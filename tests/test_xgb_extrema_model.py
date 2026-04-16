import numpy as np
import polars as pl
import pytest
from unittest.mock import MagicMock
import xgboost as xgb
from datetime import datetime
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel, PREDICTION_COL, DEFAULT_MAXIMA_THRESHOLD, DEFAULT_MINIMA_THRESHOLD
from vnpy.alpha.dataset import AlphaDataset, Segment


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


class TestProgressiveThresholds:
    """Test progressive threshold warmup mechanism"""

    def test_progressive_thresholds_before_warmup(self):
        """Test defaults before MIN_CANDLES_FOR_DYNAMIC"""
        model = XGBoostExtremaModel()
        model._prediction_count = 10

        predictions = np.array([1.0, 2.0, 3.0])
        warmup_progress = 0.1

        maxima, minima = model._compute_progressive_thresholds(predictions, warmup_progress)
        assert maxima == DEFAULT_MAXIMA_THRESHOLD
        assert minima == DEFAULT_MINIMA_THRESHOLD

    def test_progressive_thresholds_partial_warmup(self):
        """Test mixing during partial warmup"""
        model = XGBoostExtremaModel(num_candles=200)
        model._prediction_count = 100

        model._historic_predictions["test"] = pl.DataFrame().with_columns(
            pl.Series(PREDICTION_COL, np.array([5.0, 4.0, 3.0, 2.0, 1.0]))
        )

        predictions = np.array([1.0, 2.0, 3.0])
        warmup_progress = 0.5

        maxima, minima = model._compute_progressive_thresholds(predictions, warmup_progress)
        assert maxima != DEFAULT_MAXIMA_THRESHOLD
        assert abs(maxima) < 10

    def test_progressive_thresholds_full_warmup(self):
        """Test dynamic thresholds after full warmup"""
        model = XGBoostExtremaModel(num_candles=10)
        model._prediction_count = 200

        model._historic_predictions["test"] = pl.DataFrame().with_columns(
            pl.Series(PREDICTION_COL, np.array([10.0, 8.0, 6.0, 4.0, 2.0, 0.0, -2.0, -4.0, -6.0, -8.0]))
        )

        predictions = np.array([1.0, 2.0, 3.0])
        warmup_progress = 1.0

        maxima, minima = model._compute_progressive_thresholds(predictions, warmup_progress)
        # With num_candles=10, frequency=1, so maxima is the top value (10.0)
        assert abs(maxima - 10.0) < 2.0


class TestProgressiveDICutoff:
    """Test progressive DI cutoff with Weibull distribution"""

    def test_di_cutoff_before_warmup(self):
        """Test default cutoff before warmup"""
        model = XGBoostExtremaModel()
        model._prediction_count = 10

        di_values = np.array([1.0, 2.0, 3.0])
        warmup_progress = 0.1

        cutoff, params = model._compute_progressive_di_cutoff(di_values, warmup_progress)
        assert cutoff == model.DEFAULT_DI_CUTOFF
        assert params == (0.0, 0.0, 0.0)

    def test_di_cutoff_with_data(self):
        """Test Weibull fitting with real data"""
        model = XGBoostExtremaModel(num_candles=200)
        model._prediction_count = 100

        di_values = np.abs(np.random.randn(100)) + 0.5

        cutoff, params = model._compute_progressive_di_cutoff(di_values, 0.5)
        assert cutoff > 0
        assert isinstance(params, tuple)
        assert len(params) == 3

    def test_di_cutoff_handles_exception(self):
        """Test exception handling"""
        model = XGBoostExtremaModel()
        model._prediction_count = 100

        di_values = np.array([])

        cutoff, params = model._compute_progressive_di_cutoff(di_values, 0.5)
        assert cutoff == model.DEFAULT_DI_CUTOFF
        assert params == (0.0, 0.0, 0.0)


class TestModelTraining:
    """Test model training"""

    def test_fit_creates_model(self):
        """Test that fit creates a model instance"""
        model = XGBoostExtremaModel(n_estimators=10)

        dataset = MagicMock(spec=AlphaDataset)

        # Create training data
        train_data = []
        for i in range(1, 6):
            train_data.append({
                "datetime": datetime(2024, 1, i),
                "vt_symbol": "AAPL",
                "feature1": np.random.randn(),
                "feature2": np.random.randn(),
                "label": np.random.randn(),
            })
        train_df = pl.DataFrame(train_data)

        # Create validation data
        valid_data = []
        for i in range(6, 9):
            valid_data.append({
                "datetime": datetime(2024, 1, i),
                "vt_symbol": "AAPL",
                "feature1": np.random.randn(),
                "feature2": np.random.randn(),
                "label": np.random.randn(),
            })
        valid_df = pl.DataFrame(valid_data)

        dataset.fetch_learn.side_effect = lambda segment: (
            train_df if segment == Segment.TRAIN else valid_df
        )

        model.fit(dataset)

        assert model.model is not None
        assert isinstance(model.model, xgb.Booster)


class TestModelPrediction:
    """Test model prediction with thresholds"""

    def test_predict_returns_ndarray(self):
        """Test predict returns numpy array"""
        model = XGBoostExtremaModel(n_estimators=10)

        train_df = pl.DataFrame().with_columns(
            pl.date_range(start=pl.date(2024, 1, 1), end=pl.date(2024, 1, 10), interval="1d").alias("datetime"),
            pl.lit("AAPL").alias("vt_symbol"),
            pl.Series(np.random.randn(10)).alias("feature1"),
            pl.Series(np.random.randn(10)).alias("feature2"),
            pl.Series(np.random.randn(10)).alias("label"),
        )

        valid_df = pl.DataFrame().with_columns(
            pl.date_range(start=pl.date(2024, 1, 11), end=pl.date(2024, 1, 15), interval="1d").alias("datetime"),
            pl.lit("AAPL").alias("vt_symbol"),
            pl.Series(np.random.randn(5)).alias("feature1"),
            pl.Series(np.random.randn(5)).alias("feature2"),
            pl.Series(np.random.randn(5)).alias("label"),
        )

        test_df = pl.DataFrame().with_columns(
            pl.date_range(start=pl.date(2024, 1, 16), end=pl.date(2024, 1, 20), interval="1d").alias("datetime"),
            pl.lit("AAPL").alias("vt_symbol"),
            pl.Series(np.random.randn(5)).alias("feature1"),
            pl.Series(np.random.randn(5)).alias("feature2"),
            pl.Series(np.random.randn(5)).alias("label"),
        )

        dataset = MagicMock(spec=AlphaDataset)
        dataset.fetch_learn.side_effect = lambda segment: (
            train_df if segment == Segment.TRAIN else valid_df
        )
        dataset.fetch_infer.return_value = test_df

        model.fit(dataset)
        predictions = model.predict(dataset, Segment.TEST)

        assert isinstance(predictions, np.ndarray)
        assert len(predictions) == 5

    def test_predict_stores_result_df(self):
        """Test predict stores full result DataFrame"""
        model = XGBoostExtremaModel(n_estimators=10)

        train_df = pl.DataFrame().with_columns(
            pl.date_range(start=pl.date(2024, 1, 1), end=pl.date(2024, 1, 10), interval="1d").alias("datetime"),
            pl.lit("AAPL").alias("vt_symbol"),
            pl.Series(np.random.randn(10)).alias("feature1"),
            pl.Series(np.random.randn(10)).alias("feature2"),
            pl.Series(np.random.randn(10)).alias("label"),
        )

        valid_df = pl.DataFrame().with_columns(
            pl.date_range(start=pl.date(2024, 1, 11), end=pl.date(2024, 1, 15), interval="1d").alias("datetime"),
            pl.lit("AAPL").alias("vt_symbol"),
            pl.Series(np.random.randn(5)).alias("feature1"),
            pl.Series(np.random.randn(5)).alias("feature2"),
            pl.Series(np.random.randn(5)).alias("label"),
        )

        test_df = pl.DataFrame().with_columns(
            pl.date_range(start=pl.date(2024, 1, 16), end=pl.date(2024, 1, 20), interval="1d").alias("datetime"),
            pl.lit("AAPL").alias("vt_symbol"),
            pl.Series(np.random.randn(5)).alias("feature1"),
            pl.Series(np.random.randn(5)).alias("feature2"),
            pl.Series(np.random.randn(5)).alias("label"),
        )

        dataset = MagicMock(spec=AlphaDataset)
        dataset.fetch_learn.side_effect = lambda segment: (
            train_df if segment == Segment.TRAIN else valid_df
        )
        dataset.fetch_infer.return_value = test_df

        model.fit(dataset)
        predictions = model.predict(dataset, Segment.TEST)

        result_df = model.get_result_df()

        assert result_df is not None
        assert "&s-extrema" in result_df.columns
        assert "DI_values" in result_df.columns

    def test_predict_raises_when_not_fitted(self):
        """Test predict raises ValueError when model not fitted"""
        model = XGBoostExtremaModel()

        dataset = MagicMock(spec=AlphaDataset)

        with pytest.raises(ValueError, match="Model not fitted"):
            model.predict(dataset, Segment.TEST)
