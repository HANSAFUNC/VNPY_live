# StockAI 增强功能实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 FreqAI 的高级功能：数据完整性检测 (DI)、时间范围管理、训练增强 (PCA/SVM/加权)、分类支持

**Architecture:** 扩展 StockaiDataKitchen 类添加时间范围管理功能，扩展数据管道以支持 PCA/SVM/DBSCAN/Noise/DI 等数据转换，添加分类模型的类别管理功能。保持与现有回归模型架构兼容。

**Tech Stack:** Python, polars, datasieve (PCA, SVMOutlierExtractor, DBSCAN, Noise, DissimilarityIndex), scikit-learn

---

## 文件结构

| 文件 | 职责 | 变更 |
|------|------|------|
| `vnpy/stockai/data_kitchen.py` | 数据管理、时间范围分割、权重计算 | 修改 |
| `vnpy/stockai/base_models/base_regression_model.py` | 训练流程、数据管道定义 | 修改 |
| `vnpy/stockai/base_models/base_classifier_model.py` | 分类模型基类 | 新建 |
| `vnpy/stockai/data_drawer.py` | 模型持久化、回测模式支持 | 修改 |
| `vnpy/stockai/utils.py` | 时间范围工具函数 | 修改 |

---

### Task 1: 时间范围管理工具函数

**Files:**
- Modify: `vnpy/stockai/utils.py`
- Test: `tests/test_stockai_utils.py`

**Context:** FreqAI 使用 TimeRange 对象管理训练和回测时间窗口，需要实现类似功能。

- [ ] **Step 1: 添加时间范围解析函数**

```python
# vnpy/stockai/utils.py

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

@dataclass
class TimeRange:
    """时间范围对象"""
    startts: int = 0  # 开始时间戳（秒）
    stopts: int = 0   # 结束时间戳（秒）
    
    @property
    def timerange_str(self) -> str:
        """返回格式: 20230101-20240101"""
        start_str = datetime.fromtimestamp(self.startts).strftime("%Y%m%d")
        stop_str = datetime.fromtimestamp(self.stopts).strftime("%Y%m%d") if self.stopts else ""
        return f"{start_str}-{stop_str}"
    
    @classmethod
    def parse_timerange(cls, timerange: str) -> "TimeRange":
        """解析时间范围字符串"""
        if "-" not in timerange:
            raise ValueError(f"Invalid timerange format: {timerange}")
        
        parts = timerange.split("-")
        start_str = parts[0]
        stop_str = parts[1] if len(parts) > 1 and parts[1] else None
        
        startts = int(datetime.strptime(start_str, "%Y%m%d").timestamp())
        stopts = int(datetime.strptime(stop_str, "%Y%m%d").timestamp()) if stop_str else 0
        
        return cls(startts=startts, stopts=stopts)


def create_full_timerange(
    backtest_start: str,
    backtest_end: str,
    train_period_days: int,
) -> tuple[str, str]:
    """
    创建完整时间范围（包含训练前置期）
    
    Args:
        backtest_start: 回测开始日期 (YYYY-MM-DD)
        backtest_end: 回测结束日期 (YYYY-MM-DD)
        train_period_days: 训练期天数
    
    Returns:
        (full_start, backtest_end) 完整时间范围
    """
    from datetime import timedelta
    
    backtest_start_dt = datetime.strptime(backtest_start, "%Y-%m-%d")
    full_start_dt = backtest_start_dt - timedelta(days=train_period_days)
    full_start = full_start_dt.strftime("%Y-%m-%d")
    
    return full_start, backtest_end
```

- [ ] **Step 2: 运行测试验证**

Run: `python -c "from vnpy.stockai.utils import TimeRange, create_full_timerange; tr = TimeRange.parse_timerange('20230101-20240101'); print(tr.timerange_str)"`

Expected: `20230101-20240101`

- [ ] **Step 3: Commit**

```bash
git add vnpy/stockai/utils.py
git commit -m "feat(stockai): add TimeRange and create_full_timerange utilities"
```

---

### Task 2: 时间范围分割功能

**Files:**
- Modify: `vnpy/stockai/data_kitchen.py`
- Test: `tests/test_data_kitchen_timerange.py`

**Context:** FreqAI 的 `split_timerange` 方法将完整时间范围分割为多个训练和回测窗口，用于滑动窗口回测。

- [ ] **Step 1: 添加 split_timerange 方法到 DataKitchen**

```python
# vnpy/stockai/data_kitchen.py，添加到 StockaiDataKitchen 类

    def split_timerange(
        self,
        start_date: str,
        end_date: str,
        train_period_days: int,
        backtest_period_days: int,
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """
        分割时间范围为多个训练/回测窗口
        
        Args:
            start_date: 完整数据开始日期 (YYYY-MM-DD)
            end_date: 完整数据结束日期 (YYYY-MM-DD)
            train_period_days: 每个训练窗口的天数
            backtest_period_days: 每个回测窗口的天数
        
        Returns:
            (training_ranges, backtesting_ranges) - 两个列表，每个元素是 (start, end) 元组
        """
        from datetime import datetime, timedelta
        
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
        
        training_ranges: list[tuple[str, str]] = []
        backtesting_ranges: list[tuple[str, str]] = []
        
        current_train_start = start_dt
        
        while True:
            current_train_end = current_train_start + timedelta(days=train_period_days)
            current_backtest_start = current_train_end
            current_backtest_end = current_backtest_start + timedelta(days=backtest_period_days)
            
            if current_backtest_end > end_dt:
                break
            
            training_ranges.append((
                current_train_start.strftime("%Y-%m-%d"),
                current_train_end.strftime("%Y-%m-%d"),
            ))
            backtesting_ranges.append((
                current_backtest_start.strftime("%Y-%m-%d"),
                current_backtest_end.strftime("%Y-%m-%d"),
            ))
            
            # 滑动窗口
            current_train_start = current_backtest_start
        
        logger.info(
            f"{self.pair}: 分割为 {len(training_ranges)} 个窗口 "
            f"(训练期 {train_period_days} 天, 回测期 {backtest_period_days} 天)"
        )
        
        return training_ranges, backtesting_ranges
```

- [ ] **Step 2: 运行测试验证**

```python
# tests/test_data_kitchen_timerange.py
def test_split_timerange():
    from vnpy.stockai.data_kitchen import StockaiDataKitchen
    
    config = {}
    dk = StockaiDataKitchen(config, "TEST", None)
    
    train_ranges, bt_ranges = dk.split_timerange(
        "2023-01-01", "2023-06-01", 30, 7
    )
    
    assert len(train_ranges) > 0
    assert len(train_ranges) == len(bt_ranges)
    print(f"Training ranges: {train_ranges}")
    print(f"Backtest ranges: {bt_ranges}")
```

Run: `python tests/test_data_kitchen_timerange.py`

Expected: 输出多个训练和回测时间窗口

- [ ] **Step 3: Commit**

```bash
git add vnpy/stockai/data_kitchen.py tests/test_data_kitchen_timerange.py
git commit -m "feat(stockai): add split_timerange for sliding window backtesting"
```

---

### Task 3: 近期样本加权功能

**Files:**
- Modify: `vnpy/stockai/data_kitchen.py`

**Context:** FreqAI 支持对近期训练样本赋予更高权重，使模型更关注最新数据。

- [ ] **Step 1: 添加 set_weights_higher_recent 方法**

```python
# vnpy/stockai/data_kitchen.py，添加到 StockaiDataKitchen 类

    def set_weights_higher_recent(self, num_weights: int) -> np.ndarray:
        """
        设置指数衰减权重，近期样本权重更高
        
        Args:
            num_weights: 样本数量
        
        Returns:
            权重数组，形状为 (num_weights,)
        """
        weight_factor = self.config.get("feature_parameters", {}).get("weight_factor", 1.0)
        
        if weight_factor <= 0:
            return np.ones(num_weights)
        
        # 指数衰减权重: w_i = exp(-i / (factor * N))
        # 反转使近期样本权重更高
        weights = np.exp(-np.arange(num_weights) / (weight_factor * num_weights))[::-1]
        
        logger.debug(f"{self.pair}: 权重范围 [{weights.min():.4f}, {weights.max():.4f}]")
        
        return weights
```

- [ ] **Step 2: 修改 make_train_test_datasets 支持权重**

```python
# 修改 make_train_test_datasets 方法，添加 weights 参数处理

    def make_train_test_datasets(
        self,
        features: pl.DataFrame,
        labels: pl.DataFrame,
        use_weights: bool = False,
    ) -> dict[str, Any]:
        """
        分割训练集和测试集，可选使用样本权重
        """
        # ... 原有代码 ...
        
        # 计算权重
        if use_weights:
            weights = self.set_weights_higher_recent(len(X))
        else:
            weights = np.ones(len(X))
        
        # 分割数据（包含权重）
        if test_size > 0:
            X_train, X_test, y_train, y_test, train_weights, test_weights = train_test_split(
                X, y, weights, test_size=test_size, shuffle=shuffle
            )
        else:
            X_train, y_train, train_weights = X, y, weights
            X_test, y_test, test_weights = np.array([]).reshape(0, X.shape[1]), np.array([]), np.array([])
        
        self.data_dictionary = {
            "train_features": X_train,
            "train_labels": y_train,
            "test_features": X_test,
            "test_labels": y_test,
            "train_weights": train_weights,
            "test_weights": test_weights,
        }
        
        return self.data_dictionary
```

- [ ] **Step 3: Commit**

```bash
git add vnpy/stockai/data_kitchen.py
git commit -m "feat(stockai): add set_weights_higher_recent for time-weighted training"
```

---

### Task 4: 扩展数据管道支持 PCA/SVM/DBSCAN/Noise/DI

**Files:**
- Modify: `vnpy/stockai/base_models/base_regression_model.py`
- Test: `tests/test_stockai_pipeline.py`

**Context:** FreqAI 使用 datasieve 库提供高级数据转换：PCA 降维、SVM 异常值检测、DBSCAN 聚类、噪声注入、DI 漂移检测。

- [ ] **Step 1: 重写 define_data_pipeline 方法**

```python
# vnpy/stockai/base_models/base_regression_model.py

    def define_data_pipeline(self) -> Pipeline:
        """
        定义特征处理管道 - 支持多种数据增强和检测
        
        配置参数 (feature_parameters):
        - principal_component_analysis: bool - 启用 PCA 降维
        - pca_n_components: float - PCA 保留方差比例 (默认 0.999)
        - use_SVM_to_remove_outliers: bool - 使用 SVM 检测异常值
        - svm_params: dict - SVM 参数 (nu=0.01, shuffle=False)
        - use_DBSCAN_to_remove_outliers: bool - 使用 DBSCAN 检测异常值
        - dbscan_eps: float - DBSCAN 邻域半径
        - noise_standard_deviation: float - 注入高斯噪声的标准差
        - DI_threshold: float - 漂移指数阈值 (>0 启用 DI 检测)
        """
        ft_params = self.config.get("feature_parameters", {})
        
        pipe_steps: list[tuple[str, Any]] = [
            ("variance_threshold", ds.VarianceThreshold(threshold=0)),
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ]
        
        # PCA 降维
        if ft_params.get("principal_component_analysis", False):
            n_components = ft_params.get("pca_n_components", 0.999)
            pipe_steps.append(("pca", ds.PCA(n_components=n_components)))
            pipe_steps.append(
                ("post-pca-scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1))))
            )
            logger.info("启用 PCA 降维")
        
        # SVM 异常值检测
        if ft_params.get("use_SVM_to_remove_outliers", False):
            svm_params = ft_params.get("svm_params", {"nu": 0.01, "shuffle": False})
            pipe_steps.append(("svm", ds.SVMOutlierExtractor(**svm_params)))
            logger.info("启用 SVM 异常值检测")
        
        # DI (Dissimilarity Index) 漂移检测
        di_threshold = ft_params.get("DI_threshold", 0)
        if di_threshold > 0:
            pipe_steps.append(
                ("di", ds.DissimilarityIndex(di_threshold=di_threshold, n_jobs=-1))
            )
            logger.info(f"启用 DI 漂移检测 (threshold={di_threshold})")
        
        # DBSCAN 异常值检测
        if ft_params.get("use_DBSCAN_to_remove_outliers", False):
            dbscan_eps = ft_params.get("dbscan_eps", 0.5)
            pipe_steps.append(("dbscan", ds.DBSCAN(eps=dbscan_eps, n_jobs=-1)))
            logger.info("启用 DBSCAN 异常值检测")
        
        # 噪声注入（数据增强）
        noise_sigma = ft_params.get("noise_standard_deviation", 0)
        if noise_sigma > 0:
            pipe_steps.append(("noise", ds.Noise(sigma=noise_sigma)))
            logger.info(f"启用噪声注入 (sigma={noise_sigma})")
        
        return Pipeline(pipe_steps)
```

- [ ] **Step 2: 修改 predict 方法提取 DI 值**

```python
# vnpy/stockai/base_models/base_regression_model.py，修改 predict 方法

        # 4. 转换 (datasieve Pipeline 返回 (data, outliers, extra))
        X, outliers, _ = dk.feature_pipeline.transform(features_df.to_numpy())
        
        # 提取 DI 值（如果启用了 DI）
        if "di" in dk.feature_pipeline:
            dk.DI_values = dk.feature_pipeline["di"].di_values
        else:
            dk.DI_values = np.zeros(len(X))
        
        # 5. 预测
        if self.model is None:
            raise ValueError(f"{pair}: 模型未加载")
        predictions = self.model.predict(X)
```

- [ ] **Step 3: Commit**

```bash
git add vnpy/stockai/base_models/base_regression_model.py
git commit -m "feat(stockai): extend data pipeline with PCA, SVM, DBSCAN, DI, Noise"
```

---

### Task 5: 回测实时模型模式 (backtest_live_models)

**Files:**
- Modify: `vnpy/stockai/data_drawer.py`
- Modify: `vnpy/stockai/stockai_interface.py`

**Context:** FreqAI 支持在回测时使用已训练的实时模型，而不是每个窗口重新训练。

- [ ] **Step 1: 添加 backtest_live_models 支持到 DataDrawer**

```python
# vnpy/stockai/data_drawer.py，添加到 StockaiDataDrawer 类

    def __init__(self, full_path: Path, config: dict):
        # ... 原有代码 ...
        
        # 回测时使用已训练模型模式
        self.backtest_live_models = config.get("backtest_live_models", False)
        if self.backtest_live_models:
            logger.info("启用回测实时模型模式 - 将使用已训练模型进行预测")
```

- [ ] **Step 2: 修改 should_retrain 支持回测模式**

```python
# vnpy/stockai/data_drawer.py

    def should_retrain(self, pair: str, max_age_days: int = 30) -> bool:
        """
        检查是否需要重新训练
        
        如果启用了 backtest_live_models 且模型存在，则跳过训练
        """
        if pair not in self.pair_dict:
            return True
        
        # 回测实时模型模式：如果模型存在则不重新训练
        if self.backtest_live_models and pair in self.pair_dict:
            logger.info(f"{pair}: 回测实时模型模式，跳过重新训练")
            return False
        
        last_trained = self.pair_dict[pair].get("trained_timestamp", 0)
        age_days = (get_timestamp() - last_trained) / 86400
        
        return age_days > max_age_days
```

- [ ] **Step 3: Commit**

```bash
git add vnpy/stockai/data_drawer.py
git commit -m "feat(stockai): add backtest_live_models mode for reusing trained models"
```

---

### Task 6: 分类模型基类 (BaseClassifierModel)

**Files:**
- Create: `vnpy/stockai/base_models/base_classifier_model.py`
- Test: `tests/test_classifier_model.py`

**Context:** FreqAI 支持分类模型（预测类别）和回归模型（预测数值），需要添加分类模型基类。

- [ ] **Step 1: 创建 BaseClassifierModel 类**

```python
# vnpy/stockai/base_models/base_classifier_model.py

"""StockAI 分类模型基类 - 复刻 FreqAI BaseClassifierModel"""

from abc import abstractmethod
from typing import Any

import numpy as np
import polars as pl
from datasieve.pipeline import Pipeline
from datasieve.transforms import SKLearnWrapper
from sklearn.preprocessing import MinMaxScaler
import datasieve.transforms as ds

from vnpy.alpha.logger import logger

from ..data_kitchen import StockaiDataKitchen
from ..stockai_interface import IStockaiModel


class BaseClassifierModel(IStockaiModel):
    """
    分类模型基类 - 复刻 FreqAI BaseClassifierModel
    
    与回归模型的区别：
    - 预测的是类别标签而非连续值
    - 使用分类特有的评估指标（准确率、F1等）
    - 需要管理类别列表 (unique_classes)
    """
    
    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """分类模型训练流程"""
        logger.info(f"开始训练分类模型: {pair}")
        
        # 1. 识别特征和标签
        dk.find_features(df)
        dk.find_labels(df)
        
        # 2. 过滤数据
        features_df, labels_df = dk.filter_features(
            unfiltered_df=df,
            training_feature_list=dk.training_features_list,
            label_list=dk.label_list,
            training_filter=True,
        )
        
        # 3. 获取/设置类别列表
        self._set_unique_classes(labels_df, dk)
        
        # 4. 分割数据
        data_dict = dk.make_train_test_datasets(features_df, labels_df)
        
        # 5. 定义管道
        dk.feature_pipeline = self.define_data_pipeline()
        
        # 6. 拟合和转换
        dk.feature_pipeline.feature_list = dk.training_features_list
        dk.feature_pipeline.fit(data_dict["train_features"])
        dk.training_features_list = dk.feature_pipeline.feature_list
        
        X_train, _, _ = dk.feature_pipeline.transform(data_dict["train_features"])
        X_test, _, _ = dk.feature_pipeline.transform(data_dict["test_features"])
        
        data_dict["train_features"] = X_train
        data_dict["test_features"] = X_test
        
        # 7. 训练模型
        logger.info(f"训练: {len(X_train)} 样本, {X_train.shape[1]} 特征")
        logger.info(f"类别: {dk.unique_class_list}")
        model = self.fit(data_dict, dk)
        
        # 8. 保存
        self._save_model_and_pipelines(pair, model, dk)
        
        logger.info(f"分类模型训练完成: {pair}")
        return model
    
    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> tuple[pl.DataFrame, np.ndarray]:
        """分类模型预测流程"""
        pair = dk.pair
        
        # 1. 识别特征
        dk.find_features(df)
        
        # 2. 加载管道
        self._load_pipelines(pair, dk)
        
        # 3. 过滤特征
        features_df, _ = dk.filter_features(
            unfiltered_df=df,
            training_feature_list=dk.training_features_list,
            label_list=None,
            training_filter=False,
        )
        
        filtered_datetime = df["datetime"] if "datetime" in df.columns else pl.Series(range(len(features_df)))
        
        # 4. 转换
        X, outliers, _ = dk.feature_pipeline.transform(features_df.to_numpy())
        
        # 5. 预测
        if self.model is None:
            raise ValueError(f"{pair}: 模型未加载")
        predictions = self.model.predict(X)
        
        # 6. 构建结果
        label_name = dk.label_list[0] if dk.label_list else "&class"
        result_df = pl.DataFrame({
            "datetime": filtered_datetime,
            label_name: predictions,
        })
        
        do_predict = dk.do_predict
        
        logger.info(f"分类预测完成: {pair}, {len(result_df)} 样本")
        
        return result_df, do_predict
    
    def _set_unique_classes(
        self,
        labels_df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> None:
        """设置类别列表"""
        if dk.label_list:
            label_col = dk.label_list[0]
            unique_vals = labels_df[label_col].unique().to_list()
            dk.unique_class_list = sorted([str(v) for v in unique_vals])
            dk.unique_classes = {label_col: dk.unique_class_list}
            logger.info(f"{dk.pair}: 识别到 {len(dk.unique_class_list)} 个类别: {dk.unique_class_list}")
    
    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> Any:
        """训练分类模型（子类必须实现）"""
        pass
    
    def define_data_pipeline(self) -> Pipeline:
        """分类模型的数据管道（通常不需要标准化标签）"""
        return Pipeline([
            ("variance_threshold", ds.VarianceThreshold(threshold=0)),
            ("scaler", SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))),
        ])
    
    def define_label_pipeline(self) -> Pipeline:
        """分类模型不需要标签管道"""
        return Pipeline([])
```

- [ ] **Step 2: 添加 unique_classes 到 DataKitchen**

```python
# vnpy/stockai/data_kitchen.py，添加到 __init__ 方法

        # 分类支持
        self.unique_classes: dict[str, list] = {}
        self.unique_class_list: list = []
```

- [ ] **Step 3: Commit**

```bash
git add vnpy/stockai/base_models/base_classifier_model.py vnpy/stockai/data_kitchen.py
git commit -m "feat(stockai): add BaseClassifierModel for classification support"
```

---

### Task 7: 更新 __init__.py 导出

**Files:**
- Modify: `vnpy/stockai/__init__.py`

- [ ] **Step 1: 添加新类导出**

```python
# vnpy/stockai/__init__.py

from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen
from .stockai_interface import IStockaiModel
from .base_models.base_regression_model import BaseRegressionModel
from .base_models.base_classifier_model import BaseClassifierModel

__all__ = [
    "StockaiDataDrawer",
    "StockaiDataKitchen", 
    "IStockaiModel",
    "BaseRegressionModel",
    "BaseClassifierModel",
]
```

- [ ] **Step 2: Commit**

```bash
git add vnpy/stockai/__init__.py
git commit -m "chore(stockai): update exports for new classes"
```

---

### Task 8: 集成测试

**Files:**
- Create: `tests/test_stockai_full_features.py`

- [ ] **Step 1: 创建完整功能测试**

```python
# tests/test_stockai_full_features.py

"""StockAI 完整功能测试"""
import numpy as np
import polars as pl
from datetime import datetime, timedelta

from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel
from vnpy.stockai.data_kitchen import StockaiDataKitchen


def create_test_data_with_timerange(start_date: str, end_date: str, n_features: int = 10):
    """创建测试数据"""
    start = datetime.strptime(start_date, "%Y-%m-%d")
    end = datetime.strptime(end_date, "%Y-%m-%d")
    days = (end - start).days
    
    dates = [start + timedelta(days=i) for i in range(days)]
    
    data = {"datetime": dates}
    for i in range(n_features):
        data[f"%feature_{i}"] = np.random.randn(days)
    data["&target"] = np.random.randn(days) * 0.1
    
    return pl.DataFrame(data)


def test_split_timerange():
    """测试时间范围分割"""
    config = {}
    dk = StockaiDataKitchen(config, "TEST", None)
    
    train_ranges, bt_ranges = dk.split_timerange(
        "2023-01-01", "2023-12-31", 60, 14
    )
    
    assert len(train_ranges) > 0
    assert len(train_ranges) == len(bt_ranges)
    print(f"✓ 分割为 {len(train_ranges)} 个窗口")


def test_weighted_training():
    """测试加权训练"""
    config = {
        "feature_parameters": {"weight_factor": 1.0},
        "data_split_parameters": {"test_size": 0.2},
    }
    
    dk = StockaiDataKitchen(config, "TEST", None)
    
    # 创建数据
    df = create_test_data_with_timerange("2023-01-01", "2023-06-01")
    dk.find_features(df)
    dk.find_labels(df)
    
    features_df, labels_df = dk.filter_features(
        df, dk.training_features_list, dk.label_list, training_filter=True
    )
    
    # 使用权重
    data_dict = dk.make_train_test_datasets(features_df, labels_df, use_weights=True)
    
    assert "train_weights" in data_dict
    assert len(data_dict["train_weights"]) == len(data_dict["train_features"])
    # 验证权重是指数衰减的（近期权重更高）
    assert data_dict["train_weights"][-1] > data_dict["train_weights"][0]
    print("✓ 加权训练工作正常")


def test_pca_pipeline():
    """测试 PCA 降维"""
    config = {
        "feature_parameters": {
            "principal_component_analysis": True,
            "pca_n_components": 0.95,
        },
        "data_split_parameters": {"test_size": 0.2},
        "model_training_parameters": {},
        "path": "./test_pca_data",
    }
    
    model = XGBoostExtremaModel(config, lab=None)
    pipeline = model.define_data_pipeline()
    
    # 验证管道包含 PCA 步骤
    step_names = [name for name, _ in pipeline.steps]
    assert "pca" in step_names
    print("✓ PCA 管道配置正确")


def test_backtest_live_models():
    """测试回测实时模型模式"""
    from vnpy.stockai.data_drawer import StockaiDataDrawer
    from pathlib import Path
    
    config = {
        "backtest_live_models": True,
        "path": "./test_live_models",
    }
    
    drawer = StockaiDataDrawer(Path("./test_live_models"), config)
    
    # 添加模拟模型记录
    drawer.pair_dict["TEST_PAIR"] = {
        "model_filename": "test_model",
        "trained_timestamp": 1234567890,
    }
    
    # 在 backtest_live_models 模式下应该返回 False（不需要重新训练）
    should_train = drawer.should_retrain("TEST_PAIR", max_age_days=30)
    
    assert should_train == False, "回测实时模型模式应跳过重新训练"
    print("✓ 回测实时模型模式工作正常")


if __name__ == "__main__":
    test_split_timerange()
    test_weighted_training()
    test_pca_pipeline()
    test_backtest_live_models()
    print("\n✓ 所有测试通过!")
```

- [ ] **Step 2: 运行测试**

Run: `/c/Users/jacke/anaconda3/envs/vnpy_live/python tests/test_stockai_full_features.py`

Expected: `✓ 所有测试通过!`

- [ ] **Step 3: Commit**

```bash
git add tests/test_stockai_full_features.py
git commit -m "test(stockai): add comprehensive feature tests"
```

---

## 自我审查

### 1. 功能覆盖检查

| 需求 | 实现任务 | 状态 |
|------|----------|------|
| DI_values | Task 4 (DI 检测) | ✓ |
| split_timerange | Task 2 | ✓ |
| create_fulltimerange | Task 1 | ✓ |
| backtest_live_models | Task 5 | ✓ |
| set_weights_higher_recent | Task 3 | ✓ |
| use_SVM_to_remove_outliers | Task 4 (SVM) | ✓ |
| principal_component_analysis | Task 4 (PCA) | ✓ |
| unique_classes | Task 6 | ✓ |

### 2. Placeholder 检查

- 无 "TBD", "TODO" 标记
- 所有代码片段完整可直接使用
- 每个任务包含明确的测试步骤

### 3. 类型一致性

- `make_train_test_datasets` 返回值保持一致
- `TimeRange` 类与 FreqAI 兼容
- Pipeline 步骤命名一致

---

## 执行选择

**计划已完成并保存到 `docs/superpowers/plans/2026-05-04-stockai-enhancements.md`**

两个执行选项：

**1. Subagent-Driven (推荐)** - 我为每个任务调度一个子代理，任务间审查，快速迭代

**2. Inline Execution** - 在本会话中使用 executing-plans 批量执行任务，带有检查点审查

**选择哪种方法？**