"""StockAI 模块测试

测试 StockAI 核心组件：
1. utils.py - 工具函数
2. data_drawer.py - 数据抽屉
3. data_kitchen.py - 数据厨房
4. stockai_interface.py - 模型接口
5. base_regression_model.py - 回归基类
6. xgb_extrema_model.py - XGBoost模型
"""

import pytest
import tempfile
import shutil
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, MagicMock
import numpy as np
import polars as pl


# ==================== Fixtures ====================

@pytest.fixture
def temp_dir():
    """创建临时目录"""
    temp_path = tempfile.mkdtemp()
    yield Path(temp_path)
    shutil.rmtree(temp_path)


@pytest.fixture
def sample_config():
    """示例配置"""
    return {
        "path": "./test_stockai_data",
        "feature_parameters": {
            "num_candles": 200,
            "label_period_candles": 10
        },
        "model_training_parameters": {
            "learning_rate": 0.05,
            "max_depth": 6,
            "n_estimators": 100,
            "early_stopping_rounds": 50
        },
        "data_split_parameters": {
            "test_size": 0.2,
            "shuffle": False
        },
        "train_period_days": 300
    }


@pytest.fixture
def sample_df():
    """示例 DataFrame"""
    dates = pl.date_range(
        start=datetime(2025, 1, 1),
        end=datetime(2025, 3, 1),
        interval="1d",
        eager=True
    )
    n = len(dates)
    return pl.DataFrame({
        "datetime": dates,
        "vt_symbol": ["000001.SZSE"] * n,
        "open": np.random.randn(n).cumsum() + 10,
        "high": np.random.randn(n).cumsum() + 11,
        "low": np.random.randn(n).cumsum() + 9,
        "close": np.random.randn(n).cumsum() + 10,
        "volume": np.random.randint(1000, 10000, n),
        "%-feature1": np.random.randn(n),
        "%-feature2": np.random.randn(n),
        "&s-extrema": np.random.randn(n),
    })


@pytest.fixture
def mock_lab():
    """模拟 AlphaLabV2"""
    lab = Mock()
    lab.config = {"interval": "d"}
    return lab


# ==================== Test utils.py ====================

def test_get_timestamp():
    """测试时间戳生成"""
    from vnpy.stockai.utils import get_timestamp

    ts1 = get_timestamp()
    ts2 = get_timestamp()

    assert isinstance(ts1, int)
    assert ts2 >= ts1


def test_save_load_json(temp_dir):
    """测试 JSON 保存和加载"""
    from vnpy.stockai.utils import save_json, load_json

    test_data = {"key": "value", "number": 123, "nested": {"a": 1}}
    file_path = temp_dir / "test.json"

    # 保存
    save_json(test_data, file_path)
    assert file_path.exists()

    # 加载
    loaded = load_json(file_path)
    assert loaded == test_data

    # 加载不存在的文件
    assert load_json(temp_dir / "nonexistent.json") is None


def test_save_load_parquet(temp_dir, sample_df):
    """测试 Parquet 保存和加载"""
    from vnpy.stockai.utils import save_parquet, load_parquet

    file_path = temp_dir / "test.parquet"

    # 保存
    save_parquet(sample_df, file_path)
    assert file_path.exists()

    # 加载
    loaded = load_parquet(file_path)
    assert loaded is not None
    assert loaded.shape == sample_df.shape
    assert list(loaded.columns) == list(sample_df.columns)

    # 加载不存在的文件
    assert load_parquet(temp_dir / "nonexistent.parquet") is None


def test_query_by_time():
    """测试时间范围查询"""
    from vnpy.stockai.utils import query_by_time
    from datetime import date

    # 创建测试数据
    dates = pl.date_range(
        start=date(2025, 1, 1),
        end=date(2025, 3, 1),
        interval="1d",
        eager=True
    )
    df = pl.DataFrame({
        "datetime": dates,
        "value": range(len(dates))
    })

    start = date(2025, 1, 15)
    end = date(2025, 2, 15)

    result = query_by_time(df, start, end)

    assert len(result) > 0
    assert result["datetime"].min() >= start
    assert result["datetime"].max() <= end


# ==================== Test data_drawer.py ====================

def test_data_drawer_init(temp_dir, sample_config):
    """测试数据抽屉初始化"""
    from vnpy.stockai.data_drawer import StockaiDataDrawer

    drawer = StockaiDataDrawer(temp_dir, sample_config)

    assert drawer.full_path == temp_dir
    assert drawer.pair_dict == {}
    assert drawer.model_dictionary == {}
    assert drawer.historic_predictions == {}


def test_data_drawer_save_load_model(temp_dir, sample_config):
    """测试模型保存和加载"""
    from vnpy.stockai.data_drawer import StockaiDataDrawer
    import joblib

    drawer = StockaiDataDrawer(temp_dir, sample_config)

    # 创建测试模型
    test_model = {"weights": [1, 2, 3], "bias": 0.5}
    pair = "000001.SZSE"
    timestamp = 1234567890

    # 保存
    drawer.save_model(pair, test_model, timestamp)

    # 验证文件存在
    model_path = temp_dir / f"sub-train-000001_SZSE_{timestamp}"
    assert model_path.exists()
    assert (model_path / "model.pkl").exists()

    # 验证元数据
    assert pair in drawer.pair_dict
    assert drawer.pair_dict[pair]["trained_timestamp"] == timestamp

    # 加载
    loaded = drawer.load_model(pair)
    assert loaded == test_model


def test_data_drawer_append_predictions(temp_dir, sample_config, sample_df):
    """测试预测追加"""
    from vnpy.stockai.data_drawer import StockaiDataDrawer

    drawer = StockaiDataDrawer(temp_dir, sample_config)

    pair = "000001.SZSE"
    pred_df = sample_df.select(["datetime"]).with_columns([
        pl.lit(pair).alias("pair"),
        pl.col("datetime").cast(pl.Float64).alias("prediction")
    ])

    # 追加
    drawer.append_predictions(pair, pred_df)

    # 验证
    assert pair in drawer.historic_predictions
    assert len(drawer.historic_predictions[pair]) == len(pred_df)


def test_data_drawer_should_retrain(temp_dir, sample_config):
    """测试重训练判断"""
    from vnpy.stockai.data_drawer import StockaiDataDrawer
    from vnpy.stockai.utils import get_timestamp

    drawer = StockaiDataDrawer(temp_dir, sample_config)
    pair = "000001.SZSE"

    # 无模型时需要重训练
    assert drawer.should_retrain(pair, max_age_days=30) is True

    # 添加元数据（30天前）
    old_timestamp = get_timestamp() - 31 * 86400
    drawer.pair_dict[pair] = {
        "model_filename": "test",
        "trained_timestamp": old_timestamp
    }

    # 超过30天需要重训练
    assert drawer.should_retrain(pair, max_age_days=30) is True

    # 更新为1天前
    drawer.pair_dict[pair]["trained_timestamp"] = get_timestamp() - 86400
    assert drawer.should_retrain(pair, max_age_days=30) is False


# ==================== Test data_kitchen.py ====================

def test_data_kitchen_init(sample_config, mock_lab):
    """测试数据厨房初始化"""
    from vnpy.stockai.data_kitchen import StockaiDataKitchen

    pair = "000001.SZSE"
    kitchen = StockaiDataKitchen(sample_config, pair, mock_lab)

    assert kitchen.pair == pair
    assert kitchen.config == sample_config
    assert kitchen.lab == mock_lab
    assert kitchen.full_df.shape == (0, 0)


def test_data_kitchen_filter_features(sample_config, mock_lab, sample_df):
    """测试特征过滤"""
    from vnpy.stockai.data_kitchen import StockaiDataKitchen

    pair = "000001.SZSE"
    kitchen = StockaiDataKitchen(sample_config, pair, mock_lab)
    kitchen.full_df = sample_df

    # 过滤
    features, labels = kitchen.filter_features(sample_df)

    # 验证特征列
    assert len(kitchen.training_features_list) == 2
    assert "%-feature1" in kitchen.training_features_list
    assert "%-feature2" in kitchen.training_features_list

    # 验证标签列
    assert len(kitchen.label_list) == 1
    assert "&s-extrema" in kitchen.label_list

    # 验证数据形状
    assert features.shape[0] == sample_df.shape[0]
    assert labels.shape[0] == sample_df.shape[0]


def test_data_kitchen_filter_features_no_features(sample_config, mock_lab):
    """测试无特征时的错误"""
    from vnpy.stockai.data_kitchen import StockaiDataKitchen

    pair = "000001.SZSE"
    kitchen = StockaiDataKitchen(sample_config, pair, mock_lab)

    # 无特征列的 DataFrame
    bad_df = pl.DataFrame({
        "datetime": [datetime.now()],
        "vt_symbol": [pair],
        "close": [10.0]
    })

    with pytest.raises(ValueError, match="未找到特征列"):
        kitchen.filter_features(bad_df)


def test_data_kitchen_make_train_test_datasets(sample_config, mock_lab, sample_df):
    """测试数据集分割"""
    from vnpy.stockai.data_kitchen import StockaiDataKitchen

    pair = "000001.SZSE"
    kitchen = StockaiDataKitchen(sample_config, pair, mock_lab)
    kitchen.full_df = sample_df

    # 过滤
    features, labels = kitchen.filter_features(sample_df)

    # 分割
    data_dict = kitchen.make_train_test_datasets(features, labels)

    # 验证键存在
    assert "train_features" in data_dict
    assert "train_labels" in data_dict
    assert "test_features" in data_dict
    assert "test_labels" in data_dict

    # 验证比例（test_size=0.2）
    total = len(data_dict["train_features"]) + len(data_dict["test_features"])
    assert total == sample_df.shape[0]


# ==================== Test base_regression_model.py ====================

def test_base_regression_model_init(sample_config, mock_lab):
    """测试回归模型基类初始化"""
    from vnpy.stockai.base_models.base_regression_model import BaseRegressionModel

    # 抽象类不能直接实例化
    with pytest.raises(TypeError):
        BaseRegressionModel(sample_config, mock_lab)


# ==================== Test xgb_extrema_model.py ====================

def test_xgb_extrema_model_init(sample_config, mock_lab):
    """测试 XGBoost 模型初始化"""
    from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel

    model = XGBoostExtremaModel(sample_config, mock_lab)

    assert model.config == sample_config
    assert model.DEFAULT_MAXIMA_THRESHOLD == 2.0
    assert model.DEFAULT_MINIMA_THRESHOLD == -2.0


def test_xgb_extrema_model_compute_progressive_thresholds(sample_config, mock_lab):
    """测试渐进式阈值计算"""
    from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel

    model = XGBoostExtremaModel(sample_config, mock_lab)

    # 创建预测数据
    pred_df = pl.DataFrame({
        "prediction": list(range(100))  # 0-99
    })

    # 完全预热 (progress=1.0)
    maxima, minima = model._compute_progressive_thresholds(pred_df, 1.0)

    # 验证阈值在合理范围
    assert maxima > minima
    assert maxima > 0
    assert minima >= -2.0


def test_xgb_extrema_model_compute_progressive_di_cutoff(sample_config, mock_lab):
    """测试 DI cutoff 计算"""
    from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel

    model = XGBoostExtremaModel(sample_config, mock_lab)

    # 创建包含 di_values 的数据
    pred_df = pl.DataFrame({
        "prediction": np.random.randn(100),
        "di_values": np.random.randn(100)
    })

    # 计算 DI cutoff
    cutoff, params = model._compute_progressive_di_cutoff(pred_df, 0.5)

    # 验证返回值
    assert isinstance(cutoff, float)
    assert isinstance(params, tuple)
    assert len(params) == 3


# ==================== Integration Test ====================

def test_full_pipeline(temp_dir, sample_config, mock_lab, sample_df):
    """完整流程集成测试"""
    from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel
    from vnpy.stockai.data_kitchen import StockaiDataKitchen

    # 更新配置路径
    sample_config["path"] = str(temp_dir)

    # 初始化模型
    model = XGBoostExtremaModel(sample_config, mock_lab)

    # 创建数据厨房
    pair = "000001.SZSE"
    kitchen = StockaiDataKitchen(sample_config, pair, mock_lab)
    kitchen.full_df = sample_df

    # 过滤特征
    features, labels = kitchen.filter_features(sample_df)

    # 分割数据集
    data_dict = kitchen.make_train_test_datasets(features, labels)

    # 验证数据结构
    assert "train_features" in data_dict
    assert "train_labels" in data_dict
    assert data_dict["train_features"].shape[0] > 0


# ==================== Run Tests ====================

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
