# XGBoost Extrema Selector Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create XGBoost-based stock selector with progressive threshold warmup mechanism for predicting price extrema.

**Architecture:** Port freqtrade's XGBoostRegressorQuickAdapterV5 progressive threshold mechanism to VNPY's AlphaModel framework. Key features: dual-direction prediction, progressive warmup with smooth threshold transition, DI value computation with Weibull distribution fitting.

**Tech Stack:** xgboost, scipy (weibull_min), numpy, polars

---

## File Structure

```
vnpy/alpha/model/models/
├── xgb_extrema_model.py    # NEW: Main model implementation (200-300 lines)
└── __init__.py             # MODIFY: Add import and __all__

tests/
├── test_xgb_extrema_model.py  # NEW: Unit tests for threshold logic, DI computation
```

---

### Task 1: Create Model Skeleton with DI Values Computation

**Files:**
- Create: `vnpy/alpha/model/models/xgb_extrema_model.py`
- Test: `tests/test_xgb_extrema_model.py`

- [ ] **Step 1: Write failing test for DI values computation**

```python
# tests/test_xgb_extrema_model.py
import numpy as np
import pytest
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel


class TestDIValuesComputation:
    """Test DI values calculation"""

    def test_compute_di_values_basic(self):
        """Test basic DI values computation"""
        model = XGBoostExtremaModel()
        
        # Normal case: values with non-zero std
        predictions = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
        di_values = model._compute_di_values(predictions)
        
        # DI = (x - mean) / std
        mean = predictions.mean()  # 3.0
        std = predictions.std()    # ~1.41
        
        expected = (predictions - mean) / std
        np.testing.assert_array_almost_equal(di_values, expected)

    def test_compute_di_values_zero_std(self):
        """Test DI values when std is zero (all same values)"""
        model = XGBoostExtremaModel()
        
        predictions = np.array([2.0, 2.0, 2.0])
        di_values = model._compute_di_values(predictions)
        
        # Should return zeros when std is 0
        np.testing.assert_array_equal(di_values, np.zeros_like(predictions))

    def test_compute_di_values_empty(self):
        """Test DI values with empty array"""
        model = XGBoostExtremaModel()
        
        predictions = np.array([])
        di_values = model._compute_di_values(predictions)
        
        # Should return empty array
        assert len(di_values) == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_xgb_extrema_model.py -v`
Expected: FAIL with "ModuleNotFoundError" or "AttributeError"

- [ ] **Step 3: Create model skeleton with `_compute_di_values`**

```python
# vnpy/alpha/model/models/xgb_extrema_model.py
import logging
from typing import Any

import numpy as np
import polars as pl
import scipy.stats
import xgboost as xgb

from vnpy.alpha.dataset import AlphaDataset, Segment
from vnpy.alpha.model import AlphaModel


logger = logging.getLogger(__name__)


class XGBoostExtremaModel(AlphaModel):
    """
    XGBoost极值选股器
    
    移植freqtrade的渐进式阈值预热机制，用于预测价格极值（maxima/minima）
    """

    # 渐进式阈值常量（保持freqtrade命名）
    MIN_CANDLES_FOR_DYNAMIC: int = 50
    DEFAULT_MAXIMA_THRESHOLD: float = 2.0
    DEFAULT_MINIMA_THRESHOLD: float = -2.0
    DEFAULT_DI_CUTOFF: float = 2.0

    # 列名常量
    PREDICTION_COL: str = "&s-extrema"

    def __init__(
        self,
        learning_rate: float = 0.1,
        max_depth: int = 6,
        n_estimators: int = 1000,
        early_stopping_rounds: int = 50,
        num_candles: int = 200,
        label_period_candles: int = 10,
        objective: str = "reg:squarederror",
        eval_metric: str = "rmse",
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        seed: int | None = None,
    ) -> None:
        """
        Initialize XGBoost Extrema Model
        
        Parameters
        ----------
        learning_rate : float
            Learning rate for XGBoost
        max_depth : int
            Maximum tree depth
        n_estimators : int
            Number of boosting rounds
        early_stopping_rounds : int
            Early stopping threshold
        num_candles : int
            Target candles for warmup
        label_period_candles : int
            Label period for frequency calculation
        objective : str
            XGBoost objective function
        eval_metric : str
            Evaluation metric
        subsample : float
            Subsample ratio
        colsample_bytree : float
            Column sample ratio
        seed : int | None
            Random seed
        """
        # XGBoost parameters
        self.params: dict = {
            "objective": objective,
            "learning_rate": learning_rate,
            "max_depth": max_depth,
            "subsample": subsample,
            "colsample_bytree": colsample_bytree,
            "seed": seed,
            "eval_metric": eval_metric,
        }
        self.n_estimators: int = n_estimators
        self.early_stopping_rounds: int = early_stopping_rounds

        # Progressive threshold parameters
        self.num_candles: int = num_candles
        self.label_period_candles: int = label_period_candles

        # State tracking
        self._prediction_count: int = 0
        self._historic_predictions: dict[str, pl.DataFrame] = {}

        # Model instance
        self.model: xgb.Booster | None = None

        # Last prediction result DataFrame
        self._last_result_df: pl.DataFrame | None = None

    def _compute_di_values(self, predictions: np.ndarray) -> np.ndarray:
        """
        Compute DI (Directional Index) values
        
        DI measures how much predictions deviate from the mean.
        DI = (prediction - mean) / std
        
        Parameters
        ----------
        predictions : np.ndarray
            Raw prediction values
            
        Returns
        -------
        np.ndarray
            DI values (standardized deviation)
        """
        if len(predictions) == 0:
            return np.array([])
            
        mean = predictions.mean()
        std = predictions.std()
        
        if std == 0:
            return np.zeros_like(predictions)
            
        return (predictions - mean) / std

    # Placeholder methods (implement in later tasks)
    def fit(self, dataset: AlphaDataset) -> None:
        """Fit the model - placeholder"""
        raise NotImplementedError("fit not implemented")

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """Make predictions - placeholder"""
        raise NotImplementedError("predict not implemented")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_xgb_extrema_model.py::TestDIValuesComputation -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add vnpy/alpha/model/models/xgb_extrema_model.py tests/test_xgb_extrema_model.py
git commit -m "feat: add XGBoostExtremaModel skeleton with DI values computation"
```

---

### Task 2: Implement Dynamic Thresholds Calculation

**Files:**
- Modify: `vnpy/alpha/model/models/xgb_extrema_model.py`
- Test: `tests/test_xgb_extrema_model.py`

- [ ] **Step 1: Write failing test for dynamic thresholds**

```python
# tests/test_xgb_extrema_model.py (append to file)

class TestDynamicThresholds:
    """Test dynamic thresholds calculation"""

    def test_compute_dynamic_thresholds_basic(self):
        """Test dynamic thresholds from sorted predictions"""
        model = XGBoostExtremaModel(num_candles=100, label_period_candles=10)
        
        # Create mock prediction DataFrame
        # frequency = num_candles / (label_period_candles * 2) = 100 / 20 = 5
        pred_df = pl.DataFrame({
            model.PREDICTION_COL: np.concatenate([
                np.array([5.0, 4.5, 4.0, 3.5, 3.0]),  # top 5 (maxima)
                np.random.randn(90),                   # middle
                np.array([-3.0, -3.5, -4.0, -4.5, -5.0])  # bottom 5 (minima)
            ])
        })
        
        maxima, minima = model._compute_dynamic_thresholds(pred_df)
        
        # Maxima should be mean of top 5: (5+4.5+4+3.5+3)/5 = 4.0
        assert abs(maxima - 4.0) < 0.5  # Allow some variance
        # Minima should be mean of bottom 5
        assert abs(minima - (-4.0)) < 0.5

    def test_compute_dynamic_thresholds_empty(self):
        """Test dynamic thresholds with empty DataFrame"""
        model = XGBoostExtremaModel()
        
        pred_df = pl.DataFrame({model.PREDICTION_COL: []})
        
        # Should handle empty gracefully (return defaults or raise)
        # Based on spec, frequency = max(1, int(...)), so at least 1
        maxima, minima = model._compute_dynamic_thresholds(pred_df)
        
        # With empty data, should return reasonable defaults
        assert isinstance(maxima, float)
        assert isinstance(minima, float)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_xgb_extrema_model.py::TestDynamicThresholds -v`
Expected: FAIL with "AttributeError: _compute_dynamic_thresholds"

- [ ] **Step 3: Implement `_compute_dynamic_thresholds`**

```python
# vnpy/alpha/model/models/xgb_extrema_model.py (add method)

    def _compute_dynamic_thresholds(
        self,
        pred_df_full: pl.DataFrame,
    ) -> tuple[float, float]:
        """
        Compute dynamic thresholds from prediction data
        
        Sort predictions and take mean of extreme values.
        
        Parameters
        ----------
        pred_df_full : pl.DataFrame
            DataFrame containing historical predictions
            
        Returns
        -------
        tuple[float, float]
            (maxima_threshold, minima_threshold)
        """
        if len(pred_df_full) == 0:
            return self.DEFAULT_MAXIMA_THRESHOLD, self.DEFAULT_MINIMA_THRESHOLD
        
        # Sort predictions descending
        predictions = pred_df_full.sort(self.PREDICTION_COL, descending=True)
        
        # Calculate frequency (number of extreme values to consider)
        frequency = max(1, int(self.num_candles / (self.label_period_candles * 2)))
        
        # Limit frequency to available data
        frequency = min(frequency, len(predictions))
        
        # Get extreme prediction means
        max_pred = predictions.head(frequency)[self.PREDICTION_COL].mean()
        min_pred = predictions.tail(frequency)[self.PREDICTION_COL].mean()
        
        # Handle NaN cases
        if max_pred is None or np.isnan(max_pred):
            max_pred = self.DEFAULT_MAXIMA_THRESHOLD
        if min_pred is None or np.isnan(min_pred):
            min_pred = self.DEFAULT_MINIMA_THRESHOLD
        
        return float(max_pred), float(min_pred)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_xgb_extrema_model.py::TestDynamicThresholds -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vnpy/alpha/model/models/xgb_extrema_model.py tests/test_xgb_extrema_model.py
git commit -m "feat: implement dynamic thresholds calculation"
```

---

### Task 3: Implement Progressive Thresholds with Warmup

**Files:**
- Modify: `vnpy/alpha/model/models/xgb_extrema_model.py`
- Test: `tests/test_xgb_extrema_model.py`

- [ ] **Step 1: Write failing test for progressive thresholds**

```python
# tests/test_xgb_extrema_model.py (append)

class TestProgressiveThresholds:
    """Test progressive threshold warmup mechanism"""

    def test_progressive_thresholds_before_warmup(self):
        """Test that before MIN_CANDLES_FOR_DYNAMIC, use default thresholds"""
        model = XGBoostExtremaModel()
        model._prediction_count = 10  # Less than 50
        
        predictions = np.array([1.0, 2.0, 3.0])
        warmup_progress = 0.1
        
        maxima, minima = model._compute_progressive_thresholds(predictions, warmup_progress)
        
        # Should use defaults when below MIN_CANDLES_FOR_DYNAMIC
        assert maxima == model.DEFAULT_MAXIMA_THRESHOLD
        assert minima == model.DEFAULT_MINIMA_THRESHOLD

    def test_progressive_thresholds_partial_warmup(self):
        """Test mixing during partial warmup (50-200 candles)"""
        model = XGBoostExtremaModel(num_candles=200)
        model._prediction_count = 100  # Between 50 and 200
        
        # Add some historic predictions
        model._historic_predictions["test"] = pl.DataFrame({
            model.PREDICTION_COL: np.array([5.0, 4.0, 3.0, 2.0, 1.0])
        })
        
        predictions = np.array([1.0, 2.0, 3.0])
        warmup_progress = 0.5  # 100/200
        
        maxima, minima = model._compute_progressive_thresholds(predictions, warmup_progress)
        
        # Should be a mix of default and dynamic
        # 50% progress means 50% weight on dynamic
        assert maxima != model.DEFAULT_MAXIMA_THRESHOLD  # Not pure default
        assert abs(maxima) < 10  # Reasonable range

    def test_progressive_thresholds_full_warmup(self):
        """Test using dynamic thresholds after full warmup"""
        model = XGBoostExtremaModel(num_candles=200)
        model._prediction_count = 200  # Reached target
        
        model._historic_predictions["test"] = pl.DataFrame({
            model.PREDICTION_COL: np.array([10.0, 8.0, 6.0, 4.0, 2.0, 0.0, -2.0, -4.0, -6.0, -8.0])
        })
        
        predictions = np.array([1.0, 2.0, 3.0])
        warmup_progress = 1.0  # Full warmup
        
        maxima, minima = model._compute_progressive_thresholds(predictions, warmup_progress)
        
        # Should use dynamic thresholds (100% weight)
        # Dynamic from data: top 5 mean ~ 6.0, bottom 5 mean ~ -4.0
        assert abs(maxima - 6.0) < 2.0  # Allow for frequency calculation
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_xgb_extrema_model.py::TestProgressiveThresholds -v`
Expected: FAIL with "AttributeError: _compute_progressive_thresholds"

- [ ] **Step 3: Implement `_compute_progressive_thresholds` and `_get_historic_predictions_df`**

```python
# vnpy/alpha/model/models/xgb_extrema_model.py (add methods)

    def _get_historic_predictions_df(self) -> pl.DataFrame:
        """
        Merge all historic predictions across symbols
        
        Returns
        -------
        pl.DataFrame
            Combined DataFrame with all historic predictions
        """
        if not self._historic_predictions:
            return pl.DataFrame({self.PREDICTION_COL: []})
        
        return pl.concat(list(self._historic_predictions.values()))

    def _compute_progressive_thresholds(
        self,
        predictions: np.ndarray,
        warmup_progress: float,
    ) -> tuple[float, float]:
        """
        Compute progressive thresholds with warmup
        
        Progressive mixing: default -> dynamic as warmup_progress increases.
        
        Parameters
        ----------
        predictions : np.ndarray
            Current predictions
        warmup_progress : float
            Warmup progress (0.0 to 1.0)
            
        Returns
        -------
        tuple[float, float]
            (maxima_threshold, minima_threshold)
        """
        # Before MIN_CANDLES_FOR_DYNAMIC, use pure defaults
        if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
            return self.DEFAULT_MAXIMA_THRESHOLD, self.DEFAULT_MINIMA_THRESHOLD
        
        # Compute dynamic thresholds from historic data
        pred_df_full = self._get_historic_predictions_df()
        dynamic_maxima, dynamic_minima = self._compute_dynamic_thresholds(pred_df_full)
        
        # Mix based on warmup progress
        # 0% progress: 100% default
        # 100% progress: 100% dynamic
        maxima_threshold = (
            self.DEFAULT_MAXIMA_THRESHOLD * (1 - warmup_progress)
            + dynamic_maxima * warmup_progress
        )
        minima_threshold = (
            self.DEFAULT_MINIMA_THRESHOLD * (1 - warmup_progress)
            + dynamic_minima * warmup_progress
        )
        
        return maxima_threshold, minima_threshold
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_xgb_extrema_model.py::TestProgressiveThresholds -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vnpy/alpha/model/models/xgb_extrema_model.py tests/test_xgb_extrema_model.py
git commit -m "feat: implement progressive thresholds with warmup mechanism"
```

---

### Task 4: Implement Progressive DI Cutoff with Weibull

**Files:**
- Modify: `vnpy/alpha/model/models/xgb_extrema_model.py`
- Test: `tests/test_xgb_extrema_model.py`

- [ ] **Step 1: Write failing test for DI cutoff**

```python
# tests/test_xgb_extrema_model.py (append)

class TestProgressiveDICutoff:
    """Test progressive DI cutoff with Weibull distribution"""

    def test_di_cutoff_before_warmup(self):
        """Test default cutoff before warmup"""
        model = XGBoostExtremaModel()
        model._prediction_count = 10
        
        di_values = np.array([1.0, 2.0, 3.0])
        warmup_progress = 0.1
        
        cutoff, params = model._compute_progressive_di_cutoff(di_values, warmup_progress)
        
        # Should use default before MIN_CANDLES_FOR_DYNAMIC
        assert cutoff == model.DEFAULT_DI_CUTOFF
        assert params == (0.0, 0.0, 0.0)

    def test_di_cutoff_with_data(self):
        """Test Weibull fitting with real data"""
        model = XGBoostExtremaModel(num_candles=200)
        model._prediction_count = 100
        
        # Generate some DI values (typically positive, skewed distribution)
        di_values = np.abs(np.random.randn(100)) + 0.5
        
        cutoff, params = model._compute_progressive_di_cutoff(di_values, 0.5)
        
        # Should return a cutoff value
        assert cutoff > 0
        assert isinstance(params, tuple)
        assert len(params) == 3

    def test_di_cutoff_handles_exception(self):
        """Test that exceptions are handled gracefully"""
        model = XGBoostExtremaModel()
        model._prediction_count = 100
        
        # Data that might cause fitting issues
        di_values = np.array([])  # Empty
        
        cutoff, params = model._compute_progressive_di_cutoff(di_values, 0.5)
        
        # Should return defaults on error
        assert cutoff == model.DEFAULT_DI_CUTOFF
        assert params == (0.0, 0.0, 0.0)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_xgb_extrema_model.py::TestProgressiveDICutoff -v`
Expected: FAIL with "AttributeError: _compute_progressive_di_cutoff"

- [ ] **Step 3: Implement `_compute_progressive_di_cutoff`**

```python
# vnpy/alpha/model/models/xgb_extrema_model.py (add method)

    def _compute_progressive_di_cutoff(
        self,
        di_values: np.ndarray,
        warmup_progress: float,
    ) -> tuple[float, tuple[float, float, float]]:
        """
        Compute progressive DI cutoff using Weibull distribution
        
        Parameters
        ----------
        di_values : np.ndarray
            DI values to fit
        warmup_progress : float
            Warmup progress (0.0 to 1.0)
            
        Returns
        -------
        tuple[float, tuple[float, float, float]]
            (cutoff, (param1, param2, param3)) - cutoff and Weibull params
        """
        # Before MIN_CANDLES_FOR_DYNAMIC, use defaults
        if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)
        
        if len(di_values) < 10:
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)
        
        try:
            # Fit Weibull distribution
            f = scipy.stats.weibull_min.fit(di_values)
            
            # Get 99.9% percentile as cutoff
            dynamic_cutoff = scipy.stats.weibull_min.ppf(0.999, *f)
            
            # Progressive mixing
            cutoff = (
                self.DEFAULT_DI_CUTOFF * (1 - warmup_progress)
                + dynamic_cutoff * warmup_progress
            )
            
            # Mix Weibull parameters
            params = tuple(
                0.0 * (1 - warmup_progress) + f[i] * warmup_progress
                for i in range(3)
            )
            
            return cutoff, params
            
        except Exception as e:
            logger.warning(f"Failed to compute DI cutoff: {e}")
            return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_xgb_extrema_model.py::TestProgressiveDICutoff -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vnpy/alpha/model/models/xgb_extrema_model.py tests/test_xgb_extrema_model.py
git commit -m "feat: implement progressive DI cutoff with Weibull distribution"
```

---

### Task 5: Implement Model Training (fit method)

**Files:**
- Modify: `vnpy/alpha/model/models/xgb_extrema_model.py`
- Test: `tests/test_xgb_extrema_model.py`

- [ ] **Step 1: Write failing test for fit method**

```python
# tests/test_xgb_extrema_model.py (append)
import polars as pl
from unittest.mock import MagicMock, PropertyMock
from vnpy.alpha.dataset import AlphaDataset, Segment
import xgboost as xgb


class TestModelTraining:
    """Test model training"""

    def test_fit_creates_model(self):
        """Test that fit creates a model instance"""
        model = XGBoostExtremaModel(n_estimators=10)
        
        # Create mock dataset
        dataset = MagicMock(spec=AlphaDataset)
        
        # Create mock data for training and validation
        train_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 1),
                end=pl.datetime(2024, 1, 5),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 5,
            "feature1": np.random.randn(5),
            "feature2": np.random.randn(5),
            "label": np.random.randn(5),
        })
        
        valid_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 6),
                end=pl.datetime(2024, 1, 8),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 3,
            "feature1": np.random.randn(3),
            "feature2": np.random.randn(3),
            "label": np.random.randn(3),
        })
        
        # Mock fetch_learn to return appropriate data
        dataset.fetch_learn.side_effect = lambda segment: (
            train_df if segment == Segment.TRAIN else valid_df
        )
        
        model.fit(dataset)
        
        assert model.model is not None
        assert isinstance(model.model, xgb.Booster)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_xgb_extrema_model.py::TestModelTraining -v`
Expected: FAIL with "NotImplementedError"

- [ ] **Step 3: Implement `fit` and `_prepare_data`**

```python
# vnpy/alpha/model/models/xgb_extrema_model.py (replace placeholder methods)

    def _prepare_data(
        self,
        dataset: AlphaDataset,
    ) -> tuple[xgb.DMatrix, xgb.DMatrix]:
        """
        Prepare training and validation data
        
        Parameters
        ----------
        dataset : AlphaDataset
            Dataset containing features and labels
            
        Returns
        -------
        tuple[xgb.DMatrix, xgb.DMatrix]
            (train_data, valid_data)
        """
        dtrain: xgb.DMatrix
        dvalid: xgb.DMatrix
        
        for segment in [Segment.TRAIN, Segment.VALID]:
            df: pl.DataFrame = dataset.fetch_learn(segment)
            df = df.sort(["datetime", "vt_symbol"])
            
            # Extract features (columns between vt_symbol and label)
            # Column order: datetime, vt_symbol, features..., label
            feature_cols = df.columns[2:-1]
            data = df.select(feature_cols).to_numpy()
            label = df["label"].to_numpy()
            
            if segment == Segment.TRAIN:
                dtrain = xgb.DMatrix(data, label=label)
            else:
                dvalid = xgb.DMatrix(data, label=label)
        
        return dtrain, dvalid

    def fit(self, dataset: AlphaDataset) -> None:
        """
        Train the XGBoost model
        
        Parameters
        ----------
        dataset : AlphaDataset
            Dataset containing training and validation data
        """
        # Prepare data
        dtrain, dvalid = self._prepare_data(dataset)
        
        # Train model
        self.model = xgb.train(
            self.params,
            dtrain,
            num_boost_round=self.n_estimators,
            evals=[(dtrain, "train"), (dvalid, "valid")],
            early_stopping_rounds=self.early_stopping_rounds,
            verbose_eval=False
        )
        
        logger.info(f"Model trained with {self.model.num_boosted_rounds()} rounds")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_xgb_extrema_model.py::TestModelTraining -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vnpy/alpha/model/models/xgb_extrema_model.py tests/test_xgb_extrema_model.py
git commit -m "feat: implement model training with XGBoost"
```

---

### Task 6: Implement Prediction with Threshold Calculation

**Files:**
- Modify: `vnpy/alpha/model/models/xgb_extrema_model.py`
- Test: `tests/test_xgb_extrema_model.py`

- [ ] **Step 1: Write failing test for predict method**

```python
# tests/test_xgb_extrema_model.py (append)
from unittest.mock import MagicMock


class TestModelPrediction:
    """Test model prediction with thresholds"""

    def test_predict_returns_ndarray(self):
        """Test predict returns numpy array"""
        model = XGBoostExtremaModel(n_estimators=10)
        
        # Create mock datasets for training and prediction
        train_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 1),
                end=pl.datetime(2024, 1, 10),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 10,
            "feature1": np.random.randn(10),
            "feature2": np.random.randn(10),
            "label": np.random.randn(10),
        })
        
        valid_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 11),
                end=pl.datetime(2024, 1, 15),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 5,
            "feature1": np.random.randn(5),
            "feature2": np.random.randn(5),
            "label": np.random.randn(5),
        })
        
        test_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 16),
                end=pl.datetime(2024, 1, 20),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 5,
            "feature1": np.random.randn(5),
            "feature2": np.random.randn(5),
            "label": np.random.randn(5),
        })
        
        # Create mock dataset
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
        """Test that predict stores full result DataFrame"""
        model = XGBoostExtremaModel(n_estimators=10)
        
        # Same setup as above
        train_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 1),
                end=pl.datetime(2024, 1, 10),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 10,
            "feature1": np.random.randn(10),
            "feature2": np.random.randn(10),
            "label": np.random.randn(10),
        })
        
        valid_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 11),
                end=pl.datetime(2024, 1, 15),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 5,
            "feature1": np.random.randn(5),
            "feature2": np.random.randn(5),
            "label": np.random.randn(5),
        })
        
        test_df = pl.DataFrame({
            "datetime": pl.datetime_range(
                start=pl.datetime(2024, 1, 16),
                end=pl.datetime(2024, 1, 20),
                interval="1d"
            ),
            "vt_symbol": ["AAPL"] * 5,
            "feature1": np.random.randn(5),
            "feature2": np.random.randn(5),
            "label": np.random.randn(5),
        })
        
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_xgb_extrema_model.py::TestModelPrediction -v`
Expected: FAIL with "NotImplementedError"

- [ ] **Step 3: Implement `predict` and `get_result_df`**

```python
# vnpy/alpha/model/models/xgb_extrema_model.py (replace placeholder)

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        Make predictions with threshold calculation
        
        Parameters
        ----------
        dataset : AlphaDataset
            Dataset containing features
        segment : Segment
            Data segment to predict
            
        Returns
        -------
        np.ndarray
            Raw prediction values
        """
        if self.model is None:
            raise ValueError("Model not fitted. Call fit() first.")
        
        # Get inference data
        df: pl.DataFrame = dataset.fetch_infer(segment)
        df = df.sort(["datetime", "vt_symbol"])
        
        # Extract features
        feature_cols = df.columns[2:-1] if "label" in df.columns else df.columns[2:]
        data = df.select(feature_cols).to_numpy()
        
        # Make predictions
        predictions = self.model.predict(xgb.DMatrix(data))
        
        # Update prediction count
        self._prediction_count += len(predictions)
        
        # Compute DI values
        di_values = self._compute_di_values(predictions)
        
        # Compute warmup progress
        warmup_progress = min(1.0, max(0.0, self._prediction_count / self.num_candles))
        
        # Compute thresholds
        maxima_threshold, minima_threshold = self._compute_progressive_thresholds(
            predictions, warmup_progress
        )
        
        # Compute DI cutoff
        di_cutoff, di_params = self._compute_progressive_di_cutoff(di_values, warmup_progress)
        
        # Build result DataFrame
        result_df = pl.DataFrame({
            "vt_symbol": df["vt_symbol"],
            "datetime": df["datetime"],
            self.PREDICTION_COL: predictions,
            "&s-maxima_sort_threshold": [maxima_threshold] * len(predictions),
            "&s-minima_sort_threshold": [minima_threshold] * len(predictions),
            "DI_values": di_values,
            "DI_cutoff": [di_cutoff] * len(predictions),
            "DI_value_param1": [di_params[0]] * len(predictions),
            "DI_value_param2": [di_params[1]] * len(predictions),
            "DI_value_param3": [di_params[2]] * len(predictions),
        })
        
        # Store result
        self._last_result_df = result_df
        
        # Store historic predictions per symbol
        for symbol in df["vt_symbol"].unique():
            symbol_df = result_df.filter(pl.col("vt_symbol") == symbol)
            if symbol not in self._historic_predictions:
                self._historic_predictions[symbol] = symbol_df
            else:
                self._historic_predictions[symbol] = pl.concat([
                    self._historic_predictions[symbol],
                    symbol_df
                ])
        
        logger.info(
            f"Predicted {len(predictions)} samples, "
            f"warmup progress: {int(warmup_progress * 100)}%, "
            f"thresholds: ({maxima_threshold:.2f}, {minima_threshold:.2f})"
        )
        
        return predictions

    def get_result_df(self) -> pl.DataFrame | None:
        """
        Get full prediction result DataFrame
        
        Returns
        -------
        pl.DataFrame | None
            DataFrame with predictions, thresholds, DI values, etc.
        """
        return self._last_result_df
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_xgb_extrema_model.py::TestModelPrediction -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add vnpy/alpha/model/models/xgb_extrema_model.py tests/test_xgb_extrema_model.py
git commit -m "feat: implement prediction with threshold calculation"
```

---

### Task 7: Register Model in __init__.py

**Files:**
- Modify: `vnpy/alpha/model/models/__init__.py`

- [ ] **Step 1: Check current __init__.py content**

```bash
cat vnpy/alpha/model/models/__init__.py
```

Expected: Shows current imports

- [ ] **Step 2: Update __init__.py**

```python
# vnpy/alpha/model/models/__init__.py
from .lasso_model import LassoModel
from .lgb_model import LgbModel
from .mlp_model import MlpModel
from .xgb_extrema_model import XGBoostExtremaModel

__all__ = [
    "LassoModel",
    "LgbModel",
    "MlpModel",
    "XGBoostExtremaModel",
]
```

- [ ] **Step 3: Verify import works**

Run: `python -c "from vnpy.alpha.model.models import XGBoostExtremaModel; print(XGBoostExtremaModel)"`

Expected: Prints class info without error

- [ ] **Step 4: Commit**

```bash
git add vnpy/alpha/model/models/__init__.py
git commit -m "feat: register XGBoostExtremaModel in module"
```

---

### Task 8: Verify Test Coverage and Edge Cases

**Files:**
- Test: `tests/test_xgb_extrema_model.py`

- [ ] **Step 1: Add edge case tests**

```python
# tests/test_xgb_extrema_model.py (append)

class TestEdgeCases:
    """Test edge cases and error handling"""

    def test_get_result_df_none_before_predict(self):
        """Test get_result_df returns None before any prediction"""
        model = XGBoostExtremaModel()
        
        result = model.get_result_df()
        
        assert result is None

    def test_get_historic_predictions_empty(self):
        """Test _get_historic_predictions_df with empty dict"""
        model = XGBoostExtremaModel()
        
        result = model._get_historic_predictions_df()
        
        assert len(result) == 0

    def test_compute_dynamic_thresholds_with_nan(self):
        """Test dynamic thresholds handles NaN values"""
        model = XGBoostExtremaModel()
        
        pred_df = pl.DataFrame({
            model.PREDICTION_COL: [np.nan, np.nan, np.nan]
        })
        
        maxima, minima = model._compute_dynamic_thresholds(pred_df)
        
        # Should return defaults for NaN data
        assert maxima == model.DEFAULT_MAXIMA_THRESHOLD
        assert minima == model.DEFAULT_MINIMA_THRESHOLD

    def test_progressive_thresholds_exactly_at_min_candles(self):
        """Test behavior exactly at MIN_CANDLES_FOR_DYNAMIC boundary"""
        model = XGBoostExtremaModel()
        model._prediction_count = model.MIN_CANDLES_FOR_DYNAMIC  # Exactly 50
        
        model._historic_predictions["test"] = pl.DataFrame({
            model.PREDICTION_COL: np.array([3.0, 2.0, 1.0])
        })
        
        predictions = np.array([1.0, 2.0, 3.0])
        warmup_progress = model.MIN_CANDLES_FOR_DYNAMIC / model.num_candles
        
        maxima, minima = model._compute_progressive_thresholds(predictions, warmup_progress)
        
        # Should now use dynamic thresholds (boundary case)
        assert maxima != model.DEFAULT_MAXIMA_THRESHOLD
```

- [ ] **Step 2: Run all tests with coverage**

Run: `pytest tests/test_xgb_extrema_model.py -v --cov=vnpy.alpha.model.models.xgb_extrema_model --cov-report=term-missing`

Expected: Coverage >= 80%

- [ ] **Step 3: Final commit**

```bash
git add tests/test_xgb_extrema_model.py
git commit -m "test: add edge case tests for XGBoostExtremaModel"
```

---

### Task 9: Final Verification and Integration Test

**Files:**
- All

- [ ] **Step 1: Run full test suite**

Run: `pytest tests/ -v`

Expected: All tests pass

- [ ] **Step 2: Verify model import and basic usage**

Run: `python -c "
from vnpy.alpha.model.models import XGBoostExtremaModel
import numpy as np

model = XGBoostExtremaModel(n_estimators=10)
predictions = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
di_values = model._compute_di_values(predictions)
print('DI values:', di_values)
print('Model initialized successfully')
"`

Expected: Prints DI values and "Model initialized successfully"

- [ ] **Step 3: Final status check**

```bash
git status
```

Expected: Clean working tree or only uncommitted test files

- [ ] **Step 4: Summary commit (if needed)**

```bash
git add -A
git commit -m "feat: complete XGBoost extrema selector implementation"
```