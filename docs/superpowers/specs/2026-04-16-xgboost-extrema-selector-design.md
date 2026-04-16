# XGBoost极值选股器设计文档

## 概述

创建XGBoost极值选股器，移植freqtrade的`XGBoostRegressorQuickAdapterV5`渐进式阈值预热机制，集成到VNPY的alpha框架中。

## 目标

- **预测目标**: 双向极值预测（上涨/下跌）
- **训练模式**: 离线训练
- **阈值机制**: 完全移植freqtrade渐进式预热
- **输出格式**: 通过实例变量存储完整DataFrame，`predict()`返回`np.ndarray`

## 目录结构

```
vnpy/alpha/model/models/
├── __init__.py          # 添加导入
├── lgb_model.py         # 现有
├── xgb_extrema_model.py # 新增：XGBoost极值选股器
```

## 核心类设计

```python
class XGBoostExtremaModel(AlphaModel):
    """XGBoost极值选股器，移植freqtrade渐进式阈值预热机制"""

    # 渐进式阈值常量（保持freqtrade命名）
    MIN_CANDLES_FOR_DYNAMIC: int = 50      # 开始计算动态阈值的最小蜡烛数
    DEFAULT_MAXIMA_THRESHOLD: float = 2.0  # 默认上涨阈值
    DEFAULT_MINIMA_THRESHOLD: float = -2.0 # 默认下跌阈值
    DEFAULT_DI_CUTOFF: float = 2.0         # 默认DI截止值
    
    # 列名常量
    PREDICTION_COL: str = "&s-extrema"     # freqtrade兼容的预测值列名

    def __init__(
        self,
        learning_rate: float = 0.1,
        max_depth: int = 6,
        n_estimators: int = 1000,
        early_stopping_rounds: int = 50,
        num_candles: int = 200,              # 预热目标蜡烛数
        label_period_candles: int = 10,      # 标签周期蜡烛数
        objective: str = "reg:squarederror",
        eval_metric: str = "rmse",
        subsample: float = 0.8,
        colsample_bytree: float = 0.8,
        seed: int | None = None,
    ):
        # XGBoost参数
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
        
        # 渐进式阈值参数
        self.num_candles: int = num_candles
        self.label_period_candles: int = label_period_candles
        
        # 状态追踪（关键）
        self._prediction_count: int = 0      # 跨predict调用追踪预测数
        self._historic_predictions: dict[str, pl.DataFrame] = {}  # 按symbol存储历史预测
        
        # 模型实例
        self.model: xgb.Booster | None = None
        
        # 最后预测结果（完整DataFrame）
        self._last_result_df: pl.DataFrame | None = None

    # 核心方法
    def fit(self, dataset: AlphaDataset) -> None:
        """训练模型"""
        
    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """
        返回预测值数组
        
        完整DataFrame存储在 self._last_result_df 中
        """
        
    def get_result_df(self) -> pl.DataFrame | None:
        """获取包含阈值、DI值等完整信息的DataFrame"""
        return self._last_result_df
        
    def _prepare_data(self, dataset: AlphaDataset) -> tuple[xgb.DMatrix, xgb.DMatrix]:
        """准备训练和验证数据"""
        
    def _compute_progressive_thresholds(
        self,
        predictions: np.ndarray,
        warmup_progress: float,
    ) -> tuple[float, float]:
        """计算渐进式阈值，返回(maxima_threshold, minima_threshold)"""
        
    def _compute_dynamic_thresholds(
        self,
        pred_df_full: pl.DataFrame,
    ) -> tuple[float, float]:
        """从历史预测数据计算动态阈值，返回(maxima, minima)"""
        
    def _compute_progressive_di_cutoff(
        self,
        di_values: np.ndarray,
        warmup_progress: float,
    ) -> tuple[float, tuple[float, float, float]]:
        """计算渐进式DI截止值，返回(cutoff, (param1, param2, param3))"""
        
    def _compute_di_values(self, predictions: np.ndarray) -> np.ndarray:
        """计算DI值"""
        
    def _get_historic_predictions_df(self) -> pl.DataFrame:
        """合并所有symbol的历史预测数据"""
        if not self._historic_predictions:
            return pl.DataFrame()
        return pl.concat(list(self._historic_predictions.values()))
```

## 状态管理设计（关键）

```python
# 预热追踪机制
self._prediction_count: int = 0
self._historic_predictions: dict[str, pl.DataFrame] = {}

# 在predict()中更新状态
def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
    # ...获取预测值
    
    # 更新计数
    self._prediction_count += len(predictions)
    
    # 存储历史预测（按symbol）
    for symbol in unique_symbols:
        if symbol not in self._historic_predictions:
            self._historic_predictions[symbol] = pl.DataFrame()
        # Polars使用concat而非extend
        self._historic_predictions[symbol] = pl.concat([
            self._historic_predictions[symbol],
            new_pred_df.filter(pl.col("vt_symbol") == symbol)
        ])
    
    # 计算预热进度
    warmup_progress = min(1.0, max(0.0, self._prediction_count / self.num_candles))
```

## DI值计算说明

**预测列名常量**:
```python
PREDICTION_COL = "&s-extrema"  # freqtrade兼容的预测值列名
```

**DI (Directional Index) 定义**: DI值衡量预测值偏离均值程度。

```python
def _compute_di_values(self, predictions: np.ndarray) -> np.ndarray:
    """计算DI值"""
    mean = predictions.mean()
    std = predictions.std()
    if std == 0:
        return np.zeros_like(predictions)
    return (predictions - mean) / std  # 标准化偏离度
```

**Weibull分布拟合**: DI值通常呈现偏态分布，Weibull分布能更好拟合极端值尾部，从而计算合理的99.9%分位数作为截止值。

## 数据流

```
输入: AlphaDataset
  ↓
fit():
  fetch_learn(Segment.TRAIN) → 训练数据 → xgb.DMatrix
  fetch_learn(Segment.VALID) → 验证数据 → xgb.DMatrix
  xgb.train() → 模型
  ↓
predict():
  fetch_infer(segment) → 特征数据
  model.predict() → 原始预测值(np.ndarray)
  ↓
  _compute_di_values() → DI值
  ↓
  计算预热进度: warmup_progress = _prediction_count / num_candles
  ↓
  _compute_progressive_thresholds() → 渐进式阈值
  ↓
  构建完整DataFrame存入 _last_result_df
  ↓
  返回 np.ndarray (符合基类签名)
```

## 渐进式阈值过渡逻辑

```python
def _compute_progressive_thresholds(
    self,
    predictions: np.ndarray,
    warmup_progress: float,
) -> tuple[float, float]:
    """
    渐进式阈值计算
    
    0-MIN_CANDLES_FOR_DYNAMIC根: 使用100%默认阈值
    MIN_CANDLES_FOR_DYNAMIC-num_candles根: 混合默认阈值和动态阈值
    达到num_candles后: 使用100%动态阈值
    """
    # 数据不足时使用默认值
    if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
        return self.DEFAULT_MAXIMA_THRESHOLD, self.DEFAULT_MINIMA_THRESHOLD
    
    # 计算动态阈值
    pred_df_full = self._get_historic_predictions_df()
    dynamic_maxima, dynamic_minima = self._compute_dynamic_thresholds(pred_df_full)
    
    # 根据预热进度混合阈值
    maxima_threshold = self.DEFAULT_MAXIMA_THRESHOLD * (1 - warmup_progress) + dynamic_maxima * warmup_progress
    minima_threshold = self.DEFAULT_MINIMA_THRESHOLD * (1 - warmup_progress) + dynamic_minima * warmup_progress
    
    return maxima_threshold, minima_threshold
```

## 动态阈值计算

```python
def _compute_dynamic_thresholds(
    self,
    pred_df_full: pl.DataFrame,
) -> tuple[float, float]:
    """从预测数据计算动态阈值"""
    # 对预测值排序
    predictions = pred_df_full[self.PREDICTION_COL].sort(descending=True)
    
    # 计算频率值（取极端值的数量）
    frequency = max(1, int(self.num_candles / (self.label_period_candles * 2)))
    
    # 获取极端预测值均值
    max_pred = predictions.head(frequency).mean()
    min_pred = predictions.tail(frequency).mean()
    
    return float(max_pred), float(min_pred)
```

## DI截止值计算（Weibull分布）

```python
def _compute_progressive_di_cutoff(
    self,
    di_values: np.ndarray,
    warmup_progress: float,
) -> tuple[float, tuple[float, float, float]]:
    """计算渐进式DI截止值"""
    if self._prediction_count < self.MIN_CANDLES_FOR_DYNAMIC:
        return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)
    
    try:
        # 拟合Weibull分布
        f = scipy.stats.weibull_min.fit(di_values)
        dynamic_cutoff = scipy.stats.weibull_min.ppf(0.999, *f)
        
        # 渐进式混合
        cutoff = self.DEFAULT_DI_CUTOFF * (1 - warmup_progress) + dynamic_cutoff * warmup_progress
        
        # 混合Weibull参数
        params = tuple(
            0.0 * (1 - warmup_progress) + f[i] * warmup_progress
            for i in range(3)
        )
        
        return cutoff, params
    except Exception:
        return self.DEFAULT_DI_CUTOFF, (0.0, 0.0, 0.0)
```

## 输出DataFrame结构

```python
# 存储在 self._last_result_df 中
_columns = [
    "vt_symbol",        # 股票代码
    "datetime",         # 时间戳
    "&s-extrema",       # 预测值
    "&s-maxima_sort_threshold",  # 上涨阈值
    "&s-minima_sort_threshold",  # 下跌阈值
    "DI_values",        # DI值
    "DI_cutoff",        # DI截止值
    "DI_value_param1",  # Weibull参数1 (shape)
    "DI_value_param2",  # Weibull参数2 (loc)
    "DI_value_param3",  # Weibull参数3 (scale)
]
```

## 模块注册

```python
# vnpy/alpha/model/models/__init__.py
from .xgb_extrema_model import XGBoostExtremaModel

__all__ = [
    "LassoModel",
    "LgbModel", 
    "MlpModel",
    "XGBoostExtremaModel",
]
```

## 测试要求

- 单元测试覆盖阈值计算逻辑
- 集成测试验证数据流完整性
- 测试预热状态追踪正确性
- 测试覆盖率 >= 80%

## 依赖

- xgboost
- scipy (weibull_min)
- numpy
- polars