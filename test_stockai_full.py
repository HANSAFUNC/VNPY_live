"""
StockAI 完整测试脚本 - 验证训练和预测流程
"""
import sys
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import polars as pl
from pathlib import Path
from datetime import datetime, timedelta

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel
from vnpy.stockai.data_kitchen import StockaiDataKitchen
from vnpy.alpha.logger import logger


def create_synthetic_data(n_samples=500, n_features=10) -> pl.DataFrame:
    """创建合成数据用于测试"""
    np.random.seed(42)

    from datetime import datetime, timedelta
    base_date = datetime(2023, 1, 1)
    dates = [base_date + timedelta(days=i) for i in range(n_samples)]

    # 创建特征列 (带 %-前缀)
    data = {"datetime": dates}
    for i in range(n_features):
        data[f"%feature_{i}"] = np.random.randn(n_samples)

    # 创建标签列 (带 &-前缀) - 模拟未来收益
    data["&target"] = np.random.randn(n_samples) * 0.1

    return pl.DataFrame(data)


def test_stockai_pipeline():
    """测试完整的 StockAI 流程"""
    print("=" * 60)
    print("StockAI 完整测试")
    print("=" * 60)

    # 1. 创建配置
    config = {
        "path": "./test_stockai_data",
        "feature_parameters": {},
        "model_training_parameters": {
            "learning_rate": 0.05,
            "max_depth": 3,
            "n_estimators": 50,
            "early_stopping_rounds": 10,
        },
        "data_split_parameters": {
            "test_size": 0.2,
            "shuffle": False,
        },
    }

    # 2. 创建合成数据
    print("\n1. 创建合成数据...")
    df = create_synthetic_data(n_samples=500, n_features=10)
    print(f"   数据形状: {df.shape}")
    print(f"   特征列: {[c for c in df.columns if '%' in c]}")
    print(f"   标签列: {[c for c in df.columns if '&' in c]}")

    # 3. 创建模型实例
    print("\n2. 创建 XGBoostExtremaModel...")
    model = XGBoostExtremaModel(config, lab=None)
    print("   模型创建成功")

    # 4. 测试训练
    print("\n3. 测试训练流程...")
    pair = "TEST_PAIR"

    # 创建数据厨房
    dk = StockaiDataKitchen(config, pair, lab=None)

    # 识别特征和标签
    dk.find_features(df)
    dk.find_labels(df)
    print(f"   识别到 {len(dk.training_features_list)} 个特征")
    print(f"   识别到 {len(dk.label_list)} 个标签")

    # 训练
    trained_model = model.train(df, pair, dk)
    model.model = trained_model  # 设置模型引用供 predict 使用
    print(f"   训练完成，模型类型: {type(trained_model).__name__}")

    # 5. 测试预测
    print("\n4. 测试预测流程...")

    # 创建新的数据用于预测
    predict_df = create_synthetic_data(n_samples=50, n_features=10)
    print(f"   预测数据形状: {predict_df.shape}")

    # 预测
    predictions_df, do_predict = model.predict(predict_df, dk)
    print(f"   预测结果形状: {predictions_df.shape}")
    print(f"   预测列: {predictions_df.columns}")
    print(f"   有效预测数量: {do_predict.sum()}/{len(do_predict)}")

    # 检查预测值
    pred_values = predictions_df["&target"].to_numpy()
    print(f"   预测值范围: [{pred_values.min():.4f}, {pred_values.max():.4f}]")
    print(f"   预测值均值: {pred_values.mean():.4f}")

    if np.isnan(pred_values).all():
        print("   ERROR: 所有预测值都是 NaN!")
        return False
    elif np.isnan(pred_values).any():
        nan_count = np.isnan(pred_values).sum()
        print(f"   WARNING: {nan_count} 个预测值是 NaN")
    else:
        print("   SUCCESS: 所有预测值都有效")

    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)
    return True


if __name__ == "__main__":
    try:
        success = test_stockai_pipeline()
        sys.exit(0 if success else 1)
    except Exception as e:
        logger.error(f"测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
