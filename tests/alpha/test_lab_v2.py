"""Tests for AlphaLabV2, DataStore, and IndexManager

Note: These tests avoid importing through vnpy.alpha.__init__.py
to prevent triggering Python 3.10+ type hint errors in Python 3.9.
"""
import sys
import pytest
from datetime import datetime
from pathlib import Path

# Add vnpy to path for direct imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


@pytest.fixture
def temp_lab_path(tmp_path):
    """Create temporary lab path with index configured"""
    # Import IndexManager directly
    from vnpy.alpha.index_manager import IndexManager

    index_mgr = IndexManager(str(tmp_path))
    index_mgr.create_index("test_index", "测试指数", "000001.SH")
    index_mgr.save_components("test_index", "2024-01-02", ["600519.SSE"])
    index_mgr.save_components("test_index", "2024-01-03", ["600519.SSE"])

    yield tmp_path


def test_data_store_save_and_load(temp_lab_path):
    """Test DataStore save and load bars"""
    from vnpy.alpha.data_store import DataStore
    from vnpy.trader.constant import Interval, Exchange
    from vnpy.trader.object import BarData

    store = DataStore(str(temp_lab_path), source="test")

    bars = [
        BarData(
            symbol="600519",
            exchange=Exchange.SSE,
            datetime=datetime(2024, 1, 2),
            interval=Interval.DAILY,
            open_price=100.0,
            high_price=105.0,
            low_price=99.0,
            close_price=102.0,
            volume=10000,
            turnover=1000000,
            gateway_name="TEST"
        )
    ]

    store.save_bars(bars)

    loaded = store.load_bars(
        "600519.SSE",
        Interval.DAILY,
        datetime(2024, 1, 1),
        datetime(2024, 1, 3)
    )

    assert len(loaded) == 1
    assert loaded[0].close_price == 102.0


def test_index_manager_create_and_save(temp_lab_path):
    """Test IndexManager create index and save components"""
    from vnpy.alpha.index_manager import IndexManager

    mgr = IndexManager(str(temp_lab_path))

    # Test create index
    mgr.create_index("csi300", "沪深 300", "000300.SH")
    indices = mgr.list_indices()
    assert "csi300" in indices

    # Test save and load components
    mgr.save_components("csi300", "2024-01-02", ["600519.SSE", "000001.SZSE"])
    components = mgr.load_components("csi300", "2024-01-02", "2024-01-02")

    assert datetime(2024, 1, 2) in components
    assert "600519.SSE" in components[datetime(2024, 1, 2)]


def test_index_manager_get_all_symbols(temp_lab_path):
    """Test IndexManager get all symbols"""
    from vnpy.alpha.index_manager import IndexManager

    mgr = IndexManager(str(temp_lab_path))

    symbols = mgr.get_all_symbols("test_index", "2024-01-01", "2024-01-03")
    assert "600519.SSE" in symbols


def test_index_manager_get_component_filters(temp_lab_path):
    """Test IndexManager get component filters"""
    from vnpy.alpha.index_manager import IndexManager

    mgr = IndexManager(str(temp_lab_path))

    filters = mgr.get_component_filters("test_index", "2024-01-01", "2024-01-03")
    assert "600519.SSE" in filters


def test_lab_v2_initialization(temp_lab_path):
    """Test AlphaLabV2 initialization"""
    from vnpy.alpha.lab_v2 import AlphaLabV2

    lab = AlphaLabV2(
        str(temp_lab_path),
        "test_project",
        data_source="test",
        index_code="test_index"
    )

    assert lab.project_name == "test_project"
    assert lab.data_source == "test"
    assert lab.index_code == "test_index"
    assert lab.project_path.exists()
    assert lab.dataset_path.exists()
    assert lab.model_path.exists()
    assert lab.signal_path.exists()


def test_lab_v2_save_and_load_bar_data(temp_lab_path):
    """Test AlphaLabV2 save and load bar data"""
    from vnpy.alpha.lab_v2 import AlphaLabV2
    from vnpy.trader.constant import Interval, Exchange
    from vnpy.trader.object import BarData

    lab = AlphaLabV2(
        str(temp_lab_path),
        "test_project",
        data_source="test",
        index_code="test_index"
    )

    bars = [
        BarData(
            symbol="600519",
            exchange=Exchange.SSE,
            datetime=datetime(2024, 1, 2),
            interval=Interval.DAILY,
            open_price=100.0,
            high_price=105.0,
            low_price=99.0,
            close_price=102.0,
            volume=10000,
            turnover=1000000,
            gateway_name="TEST"
        )
    ]

    lab.save_bar_data(bars)

    df = lab.load_bar_df(
        "2024-01-01",
        "2024-01-03",
        interval=Interval.DAILY
    )

    assert len(df) == 1
    assert df["close"][0] == 102.0
    assert "vt_symbol" in df.columns
    assert df["vt_symbol"][0] == "600519.SSE"


def test_lab_v2_load_component_symbols(temp_lab_path):
    """Test AlphaLabV2 load component symbols"""
    from vnpy.alpha.lab_v2 import AlphaLabV2

    lab = AlphaLabV2(
        str(temp_lab_path),
        "test_project",
        data_source="test",
        index_code="test_index"
    )

    symbols = lab.load_component_symbols("2024-01-01", "2024-01-03")
    assert "600519.SSE" in symbols


def test_lab_v2_save_and_load_signal(temp_lab_path):
    """Test AlphaLabV2 save and load signal"""
    import polars as pl
    from vnpy.alpha.lab_v2 import AlphaLabV2

    lab = AlphaLabV2(
        str(temp_lab_path),
        "test_project",
        data_source="test",
        index_code="test_index"
    )

    signal_df = pl.DataFrame({
        "datetime": [datetime(2024, 1, 2)],
        "vt_symbol": ["600519.SSE"],
        "signal": [1.0]
    })

    lab.save_signal("test_signal", signal_df)

    loaded = lab.load_signal("test_signal")
    assert loaded is not None
    assert len(loaded) == 1
    assert loaded["signal"][0] == 1.0


def test_lab_v2_load_signal_not_exists(temp_lab_path):
    """Test AlphaLabV2 load non-existent signal"""
    from vnpy.alpha.lab_v2 import AlphaLabV2

    lab = AlphaLabV2(
        str(temp_lab_path),
        "test_project",
        data_source="test",
        index_code="test_index"
    )

    loaded = lab.load_signal("nonexistent")
    assert loaded is None


def test_lab_v2_load_component_filters(temp_lab_path):
    """Test AlphaLabV2 load component filters"""
    from vnpy.alpha.lab_v2 import AlphaLabV2

    lab = AlphaLabV2(
        str(temp_lab_path),
        "test_project",
        data_source="test",
        index_code="test_index"
    )

    filters = lab.load_component_filters("2024-01-01", "2024-01-03")
    assert "600519.SSE" in filters
    assert len(filters["600519.SSE"]) > 0
