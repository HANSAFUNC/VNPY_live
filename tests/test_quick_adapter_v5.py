"""Test QuickAdapterV5Dataset."""

import polars as pl
import numpy as np
from datetime import datetime, timedelta
from vnpy.alpha.dataset.datasets.quick_adapter_v5 import QuickAdapterV5Dataset
from vnpy.alpha.dataset import Segment


def create_test_dataframe(num_symbols: int = 2, num_days: int = 100) -> pl.DataFrame:
    """Create test OHLCV dataframe"""
    data = []
    base_date = datetime(2024, 1, 1)

    for symbol_idx in range(num_symbols):
        symbol = f"STOCK{symbol_idx}"
        for day_idx in range(num_days):
            dt = base_date + timedelta(days=day_idx)
            # Random OHLCV data
            base_price = 100 + symbol_idx * 10
            open_price = base_price + np.random.randn() * 2
            high_price = open_price + np.random.rand() * 3
            low_price = open_price - np.random.rand() * 3
            close_price = open_price + np.random.randn() * 2
            volume = 1000000 + np.random.randint(0, 500000)

            data.append({
                "datetime": dt,
                "vt_symbol": symbol,
                "open": open_price,
                "high": max(high_price, open_price, close_price),
                "low": min(low_price, open_price, close_price),
                "close": close_price,
                "volume": volume,
            })

    return pl.DataFrame(data)


class TestQuickAdapterV5Dataset:
    """Test QuickAdapterV5Dataset features"""

    def test_dataset_creation(self):
        """Test dataset can be created"""
        df = create_test_dataframe()

        dataset = QuickAdapterV5Dataset(
            df=df,
            train_period=("2024-01-01", "2024-02-28"),
            valid_period=("2024-03-01", "2024-03-31"),
            test_period=("2024-04-01", "2024-04-30"),
            periods=[10, 20],
        )

        assert dataset is not None

    def test_feature_engineering_expand_all(self):
        """Test expand_all features are computed"""
        df = create_test_dataframe(num_symbols=1, num_days=50)

        dataset = QuickAdapterV5Dataset(
            df=df,
            train_period=("2024-01-01", "2024-01-31"),
            valid_period=("2024-02-01", "2024-02-15"),
            test_period=("2024-02-16", "2024-02-20"),
            periods=[10],
        )

        dataset.prepare_data()

        # Check RSI feature exists
        assert "%-rsi-10" in dataset.raw_df.columns
        assert "%-mfi-10" in dataset.raw_df.columns
        assert "%-adx-10" in dataset.raw_df.columns

    def test_feature_engineering_expand_basic(self):
        """Test expand_basic features are computed"""
        df = create_test_dataframe(num_symbols=1, num_days=50)

        dataset = QuickAdapterV5Dataset(
            df=df,
            train_period=("2024-01-01", "2024-01-31"),
            valid_period=("2024-02-01", "2024-02-15"),
            test_period=("2024-02-16", "2024-02-20"),
            periods=[10],
        )

        dataset.prepare_data()

        # Check basic features exist
        assert "%-pct-change" in dataset.raw_df.columns
        assert "%-raw_volume" in dataset.raw_df.columns
        assert "%-obv" in dataset.raw_df.columns
        assert "%-bb_width" in dataset.raw_df.columns
        assert "%-ibs" in dataset.raw_df.columns
        assert "%-macd" in dataset.raw_df.columns

    def test_feature_engineering_standard(self):
        """Test standard features are computed"""
        df = create_test_dataframe(num_symbols=1, num_days=50)

        dataset = QuickAdapterV5Dataset(
            df=df,
            train_period=("2024-01-01", "2024-01-31"),
            valid_period=("2024-02-01", "2024-02-15"),
            test_period=("2024-02-16", "2024-02-20"),
            periods=[10],
        )

        dataset.prepare_data()

        # Check time features exist
        assert "%-day_of_week" in dataset.raw_df.columns
        assert "%-hour_of_day" in dataset.raw_df.columns

    def test_label_set(self):
        """Test label expression is set"""
        df = create_test_dataframe()

        dataset = QuickAdapterV5Dataset(
            df=df,
            train_period=("2024-01-01", "2024-02-28"),
            valid_period=("2024-03-01", "2024-03-31"),
            test_period=("2024-04-01", "2024-04-30"),
        )

        assert dataset.label_expression == "ts_delay(close, -3) / ts_delay(close, -1) - 1"

    def test_fetch_learn(self):
        """Test fetch_learn returns data"""
        df = create_test_dataframe(num_symbols=1, num_days=100)

        dataset = QuickAdapterV5Dataset(
            df=df,
            train_period=("2024-01-01", "2024-02-28"),
            valid_period=("2024-03-01", "2024-03-31"),
            test_period=("2024-04-01", "2024-04-30"),
            periods=[10],
        )

        dataset.prepare_data()

        train_df = dataset.fetch_learn(Segment.TRAIN)
        assert len(train_df) > 0
        assert "label" in train_df.columns

    def test_multiple_periods(self):
        """Test multiple periods generate multiple features"""
        df = create_test_dataframe(num_symbols=1, num_days=100)

        periods = [10, 20, 30]
        dataset = QuickAdapterV5Dataset(
            df=df,
            train_period=("2024-01-01", "2024-02-28"),
            valid_period=("2024-03-01", "2024-03-31"),
            test_period=("2024-04-01", "2024-04-30"),
            periods=periods,
        )

        dataset.prepare_data()

        # Check features for each period exist
        for period in periods:
            assert f"%-rsi-{period}" in dataset.raw_df.columns
            assert f"%-mfi-{period}" in dataset.raw_df.columns