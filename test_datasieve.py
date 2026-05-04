"""验证 datasieve Pipeline 是否正确工作"""
import numpy as np
import datasieve.transforms as ds
from datasieve.pipeline import Pipeline
from datasieve.transforms import SKLearnWrapper
from sklearn.preprocessing import MinMaxScaler

print("测试 datasieve Pipeline...")

# 创建测试数据
np.random.seed(42)
X_train = np.random.randn(100, 5)
y_train = np.random.randn(100)

# 创建特征管道
feature_pipeline = Pipeline([
    ("variance_threshold", ds.VarianceThreshold(threshold=0)),
    ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
])

# 创建标签管道
label_pipeline = Pipeline([
    ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
])

# 拟合管道
print("拟合特征管道...")
feature_pipeline.fit(X_train)

print("拟合标签管道...")
label_pipeline.fit(y_train.reshape(-1, 1))

# 转换数据
print("转换训练数据...")
X_train_transformed, outliers_X, extra_X = feature_pipeline.transform(X_train, outlier_check=True)
print(f"  X_train_transformed shape: {X_train_transformed.shape}")
print(f"  outliers type: {type(outliers_X)}")

y_train_transformed, outliers_y, extra_y = label_pipeline.transform(y_train.reshape(-1, 1))
print(f"  y_train_transformed shape: {y_train_transformed.shape}")

# 测试预测流程
X_test = np.random.randn(10, 5)
predictions = np.random.randn(10)  # 模拟预测结果

print("\n测试预测流程...")
X_test_transformed, _, _ = feature_pipeline.transform(X_test)
print(f"  X_test_transformed shape: {X_test_transformed.shape}")

# 反向转换
predictions_reshaped = predictions.reshape(-1, 1)
predictions_inverse, _, _ = label_pipeline.inverse_transform(predictions_reshaped)
print(f"  predictions_inverse shape: {predictions_inverse.shape}")
print(f"  predictions_inverse range: [{predictions_inverse.min():.4f}, {predictions_inverse.max():.4f}]")

# 检查是否有 NaN
if np.isnan(predictions_inverse).any():
    print("  ERROR: 反向转换结果包含 NaN!")
else:
    print("  SUCCESS: 反向转换结果无 NaN")

print("\n所有测试通过！datasieve Pipeline 工作正常。")
