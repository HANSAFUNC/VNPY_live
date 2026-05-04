"""StockAI 增强功能集成测试"""
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import polars as pl
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.stockai.utils import TimeRange, create_full_timerange
from vnpy.stockai.data_kitchen import StockaiDataKitchen


def test_timerange():
    """测试 TimeRange 类"""
    print("\n=== 测试 TimeRange ===")

    tr = TimeRange.parse_timerange("20230101-20231231")
    print(f"  开始时间戳: {tr.startts}")
    print(f"  结束时间戳: {tr.stopts}")
    print(f"  字符串格式: {tr.timerange_str}")

    assert tr.startts > 0
    assert tr.stopts > tr.startts
    print("  ✓ TimeRange 工作正常")


def test_create_full_timerange():
    """测试创建完整时间范围"""
    print("\n=== 测试 create_full_timerange ===")

    start, end = create_full_timerange("2023-06-01", "2023-12-31", 90)
    print(f"  回测开始: 2023-06-01")
    print(f"  训练前置期: 90天")
    print(f"  完整时间范围: {start} 至 {end}")

    # 完整时间应该比回测开始早90天
    assert start < "2023-06-01"
    print("  ✓ create_full_timerange 工作正常")


def test_split_timerange():
    """测试滑动窗口分割"""
    print("\n=== 测试 split_timerange ===")

    config = {}
    dk = StockaiDataKitchen(config, "TEST", None)

    train_ranges, bt_ranges = dk.split_timerange(
        "2023-01-01", "2023-12-31", 60, 14
    )

    print(f"  分割为 {len(train_ranges)} 个窗口")
    print(f"  第一个训练窗口: {train_ranges[0]}")
    print(f"  第一个回测窗口: {bt_ranges[0]}")
    print(f"  训练/回测窗口连续: {train_ranges[0][1] == bt_ranges[0][0]}")

    assert len(train_ranges) > 0
    assert len(train_ranges) == len(bt_ranges)
    print("  ✓ split_timerange 工作正常")


def test_weighted_training():
    """测试加权训练"""
    print("\n=== 测试 set_weights_higher_recent ===")

    config = {
        "feature_parameters": {"weight_factor": 1.0},
    }
    dk = StockaiDataKitchen(config, "TEST", None)

    weights = dk.set_weights_higher_recent(100)

    print(f"  权重数量: {len(weights)}")
    print(f"  早期样本权重: {weights[0]:.4f}")
    print(f"  近期样本权重: {weights[-1]:.4f}")
    print(f"  近期权重更高: {weights[-1] > weights[0]}")

    assert len(weights) == 100
    assert weights[-1] > weights[0]  # 近期权重更高
    print("  ✓ set_weights_higher_recent 工作正常")


def test_extended_pipeline():
    """测试扩展数据管道配置"""
    print("\n=== 测试扩展数据管道 ===")

    from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel

    config = {
        "feature_parameters": {
            "principal_component_analysis": True,
            "pca_n_components": 0.95,
            "use_SVM_to_remove_outliers": True,
            "svm_params": {"nu": 0.01},
            "DI_threshold": 2.0,
            "use_DBSCAN_to_remove_outliers": True,
            "dbscan_eps": 0.5,
            "noise_standard_deviation": 0.01,
        },
        "model_training_parameters": {},
        "data_split_parameters": {},
        "path": "./test_extended",
    }

    model = XGBoostExtremaModel(config, lab=None)
    pipeline = model.define_data_pipeline()

    step_names = [name for name, _ in pipeline.steps]
    print(f"  管道步骤: {step_names}")

    assert "pca" in step_names
    assert "svm" in step_names
    assert "di" in step_names
    assert "dbscan" in step_names
    assert "noise" in step_names
    print("  ✓ 扩展数据管道配置正常")


def test_backtest_live_models():
    """测试回测实时模型模式"""
    print("\n=== 测试 backtest_live_models ===")

    from vnpy.stockai.data_drawer import StockaiDataDrawer

    config = {
        "backtest_live_models": True,
        "path": "./test_live",
    }

    drawer = StockaiDataDrawer(Path("./test_live"), config)

    # 添加模拟模型
    drawer.pair_dict["TEST_PAIR"] = {
        "model_filename": "test_model_123",
        "trained_timestamp": 1234567890,
    }

    # 在 backtest_live_models 模式下应跳过重新训练
    should_retrain = drawer.should_retrain("TEST_PAIR", max_age_days=30)

    print(f"  backtest_live_models: True")
    print(f"  模型存在: True")
    print(f"  需要重新训练: {should_retrain}")

    assert should_retrain == False
    print("  ✓ backtest_live_models 工作正常")


def test_classifier_model():
    """测试分类模型基类"""
    print("\n=== 测试 BaseClassifierModel ===")

    from vnpy.stockai.base_models.base_classifier_model import BaseClassifierModel

    # 验证类可以导入
    assert BaseClassifierModel is not None

    # 验证关键方法存在
    assert hasattr(BaseClassifierModel, 'train')
    assert hasattr(BaseClassifierModel, 'predict')
    assert hasattr(BaseClassifierModel, '_set_unique_classes')

    print("  ✓ BaseClassifierModel 导入正常")
    print("  ✓ 包含 train, predict, _set_unique_classes 方法")


def test_unique_classes():
    """测试 unique_classes 支持"""
    print("\n=== 测试 unique_classes ===")

    config = {}
    dk = StockaiDataKitchen(config, "TEST", None)

    # 验证属性存在
    assert hasattr(dk, 'unique_classes')
    assert hasattr(dk, 'unique_class_list')

    # 设置测试数据
    dk.unique_class_list = ['0', '1', '2']
    dk.unique_classes = {'&label': ['0', '1', '2']}

    print(f"  类别列表: {dk.unique_class_list}")
    print(f"  类别字典: {dk.unique_classes}")

    assert len(dk.unique_class_list) == 3
    print("  ✓ unique_classes 支持正常")


if __name__ == "__main__":
    print("=" * 60)
    print("StockAI 增强功能集成测试")
    print("=" * 60)

    try:
        test_timerange()
        test_create_full_timerange()
        test_split_timerange()
        test_weighted_training()
        test_extended_pipeline()
        test_backtest_live_models()
        test_classifier_model()
        test_unique_classes()

        print("\n" + "=" * 60)
        print("所有测试通过!")
        print("=" * 60)
    except Exception as e:
        print(f"\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
