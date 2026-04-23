"""测试 FreqaiFeaturePipeline 的 DI 功能"""

import numpy as np
import polars as pl
from datetime import datetime, timedelta
from vnpy.alpha.dataset import FreqaiFeaturePipeline, process_freqai_feature_pipeline

# 创建测试数据
dates = [datetime(2026, 1, 1) + timedelta(days=i) for i in range(100)]
symbols = ["000001.SZ", "000002.SZ", "000003.SZ"]

data = []
for date in dates:
    for symbol in symbols:
        data.append({
            "datetime": date,
            "vt_symbol": symbol,
            "%-feature1": np.random.randn(),
            "%-feature2": np.random.randn(),
            "%-feature3": np.random.randn(),
            "&-label": np.random.randn()
        })

df = pl.DataFrame(data)
print("输入 DataFrame:")
print(df.head())
print(f"列：{df.columns}")
print(f"形状：{df.shape}")

# 创建不带 DI 的管道
print("\n" + "=" * 60)
print("测试 1: 不带 DI 的管道")
print("=" * 60)

pipeline_no_di = FreqaiFeaturePipeline(threshold=0.0, feature_range=(-1, 1))
pipeline_no_di.fit(df)
result_df_no_di = pipeline_no_di.transform(df)

print(f"转换后列：{result_df_no_di.columns}")
print(f"DI_values 是否存在：{'DI_values' in result_df_no_di.columns}")

# 创建带 DI 的管道
print("\n" + "=" * 60)
print("测试 2: 带 DI 的管道 (di_threshold=0.4)")
print("=" * 60)

pipeline_with_di = FreqaiFeaturePipeline(
    threshold=0.0,
    feature_range=(-1, 1),
    di_threshold=0.4,
    n_jobs=-1
)
pipeline_with_di.fit(df)
result_df_with_di = pipeline_with_di.transform(df)

print(f"转换后列：{result_df_with_di.columns}")
print(f"DI_values 是否存在：{'DI_values' in result_df_with_di.columns}")

if "DI_values" in result_df_with_di.columns:
    print(f"DI_values 范围：[{result_df_with_di['DI_values'].min():.4f}, {result_df_with_di['DI_values'].max():.4f}]")
    print(f"DI_values 均值：{result_df_with_di['DI_values'].mean():.4f}")
    print(f"DI_values 标准差：{result_df_with_di['DI_values'].std():.4f}")

    # 检查管道中的 DI 值
    print(f"\n管道中的 DI_values: {pipeline_with_di.pipeline['di'].di_values[:5]}")

print("\n测试完成!")
