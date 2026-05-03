# StockAI 设计文档

**日期**: 2026-05-04  
**版本**: 1.0  
**目标**: 基于 FreqAI 源码复刻，为 vnpy 提供独立的 AI 预测管道

---

## 1. 概述

StockAI 是一个复刻 FreqAI 架构的预测管道系统，用于股票市场的机器学习预测。设计完全基于 FreqAI 源码结构，适配 vnpy 生态系统。

### 核心设计原则

1. **复刻 FreqAI 架构**: 保持与 FreqAI 相同的类结构和接口
2. **最小化改动**: 直接使用现有的 AlphaLabV2 和 QuickAdapterV5Dataset
3. **配置驱动**: JSON 配置文件管理所有参数
4. **每只股票独立**: 每只股票有自己的模型和数据管理

---

## 2. 目录结构

```
vnpy/stockai/
├── __init__.py
├── stockai_interface.py       # IStockaiModel (复刻 IFreqaiModel)
├── data_kitchen.py            # StockaiDataKitchen (复刻 FreqaiDataKitchen)
├── data_drawer.py             # StockaiDataDrawer (复刻 FreqaiDataDrawer)
├── base_models/
│   ├── __init__.py
│   └── base_regression_model.py   # BaseRegressionModel
├── prediction_models/
│   ├── __init__.py
│   └── xgb_extrema_model.py       # XGBoostExtremaModel
└── utils.py
```

---

## 3. 核心类设计

### 3.1 IStockaiModel (主接口)

**复刻**: `freqtrade/freqai/freqai_interface.py` 中的 `IFreqaiModel`

```python
class IStockaiModel(ABC):
    """
    StockAI 模型接口
    
    职责:
    - 定义训练和预测的抽象接口
    - 管理 DataDrawer 全局实例
    - 协调 DataKitchen 的创建
    """
    
    def __init__(
        self,
        config: dict,
        lab: AlphaLabV2,
    ):
        self.config = config
        self.lab = lab
        self.full_path = Path(config.get("path", "./stockai_data"))
        self.full_path.mkdir(parents=True, exist_ok=True)
        
        # 全局数据抽屉（持久化存储）
        self.dd = StockaiDataDrawer(self.full_path, config)
        
        # 当前数据厨房（临时，每次训练/预测时创建）
        self.dk: Optional[StockaiDataKitchen] = None
    
    @abstractmethod
    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """训练模型 - 子类实现"""
        pass
    
    @abstractmethod
    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """预测 - 子类实现"""
        pass
```

### 3.2 StockaiDataKitchen (数据厨房)

**复刻**: `freqtrade/freqai/data_kitchen.py` 中的 `FreqaiDataKitchen`

```python
class StockaiDataKitchen:
    """
    单只股票的数据管理单元
    
    职责:
    - 加载和管理单只股票的数据
    - 特征/标签的过滤和处理
    - 训练/测试数据分割
    - 管道拟合和转换
    
    生命周期: 临时对象，每次训练/预测时创建，完成后销毁
    """
    
    def __init__(
        self,
        config: dict,
        pair: str,
        lab: AlphaLabV2,
    ):
        self.config = config
        self.pair = pair
        self.lab = lab
        
        # 数据路径
        self.data_path = Path()
        
        # 数据存储
        self.data_dictionary: dict[str, pl.DataFrame] = {}
        self.full_df: pl.DataFrame = pl.DataFrame()
        
        # 特征管道
        self.feature_pipeline: Optional[Any] = None
        self.label_pipeline: Optional[Any] = None
        
        # 特征/标签列表
        self.training_features_list: list[str] = []
        self.label_list: list[str] = []
        
        # 训练元数据
        self.train_period: tuple[str, str] = ("", "")
        self.test_period: tuple[str, str] = ("", "")
        self.model_filename: str = ""
    
    def set_paths(self, trained_timestamp: Optional[int] = None) -> None:
        """设置数据路径"""
        pass
    
    def load_data(
        self,
        start: str,
        end: str,
        dataset_class: Type[AlphaDataset] = QuickAdapterV5Dataset,
    ) -> pl.DataFrame:
        """从 lab 加载数据"""
        pass
    
    def filter_features(
        self,
        df: pl.DataFrame,
        training_filter: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        过滤特征和标签
        
        - 识别 %-前缀的特征列
        - 识别 &-前缀的标签列
        - 处理 NaN/Null
        """
        pass
    
    def make_train_test_datasets(
        self,
        features: pl.DataFrame,
        labels: pl.DataFrame,
    ) -> dict[str, Any]:
        """
        分割训练/测试数据
        
        返回字典:
        - train_features: 训练特征
        - train_labels: 训练标签
        - test_features: 测试特征
        - test_labels: 测试标签
        """
        pass
```

### 3.3 StockaiDataDrawer (数据抽屉)

**复刻**: `freqtrade/freqai/data_drawer.py` 中的 `FreqaiDataDrawer`

```python
class StockaiDataDrawer:
    """
    全局数据存储管理
    
    职责:
    - 管理所有股票的模型和预测历史
    - 持久化存储到磁盘
    - 模型版本管理
    - 历史预测查询
    
    生命周期: 全局单例，与 IStockaiModel 生命周期一致
    """
    
    def __init__(self, full_path: Path, config: dict):
        self.config = config
        self.full_path = full_path
        
        # 股票元数据 {pair: metadata}
        self.pair_dict: dict[str, dict] = {}
        
        # 已加载的模型 {model_filename: model}
        self.model_dictionary: dict[str, Any] = {}
        
        # 历史预测 {pair: DataFrame}
        self.historic_predictions: dict[str, pl.DataFrame] = {}
        
        # 持久化路径
        self.historic_predictions_path = full_path / "historic_predictions.parquet"
        self.pair_dictionary_path = full_path / "pair_dictionary.json"
        self.global_metadata_path = full_path / "global_metadata.json"
        
        # 从磁盘加载
        self.load_drawer_from_disk()
        self.load_historic_predictions_from_disk()
    
    def load_drawer_from_disk(self) -> None:
        """加载 pair_dictionary.json"""
        pass
    
    def load_historic_predictions_from_disk(self) -> None:
        """加载 historic_predictions.parquet"""
        pass
    
    def save_historic_predictions_to_disk(self) -> None:
        """保存历史预测到 Parquet"""
        pass
    
    def model_filename(self, pair: str, timestamp: int) -> str:
        """生成模型文件名"""
        return f"sub-train-{pair}_{timestamp}"
    
    def save_model(
        self,
        pair: str,
        model: Any,
        timestamp: int,
    ) -> None:
        """保存模型到磁盘"""
        pass
    
    def load_model(self, pair: str, timestamp: int) -> Any:
        """加载模型"""
        pass
    
    def update_pair_dict(self, pair: str, metadata: dict) -> None:
        """更新股票元数据"""
        pass
```

### 3.4 BaseRegressionModel (回归基类)

**复刻**: `freqtrade/freqai/base_models/BaseRegressionModel.py`

```python
class BaseRegressionModel(IStockaiModel):
    """
    回归模型基类
    
    职责:
    - 提供通用的训练流程
    - 提供通用的预测流程
    - 定义抽象 fit() 方法供子类实现
    """
    
    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        通用训练流程:
        1. 过滤特征和标签
        2. 分割训练/测试数据
        3. 拟合特征管道
        4. 拟合标签管道
        5. 转换训练数据
        6. 调用子类的 fit() 训练模型
        7. 保存模型
        """
        # 1. 过滤
        features_filtered, labels_filtered = dk.filter_features(df, training_filter=True)
        
        # 2. 分割
        dd = dk.make_train_test_datasets(features_filtered, labels_filtered)
        
        # 3. 定义管道（子类可覆盖）
        dk.feature_pipeline = self.define_data_pipeline()
        dk.label_pipeline = self.define_label_pipeline()
        
        # 4. 拟合管道
        dk.feature_pipeline.fit(dd["train_features"])
        dk.label_pipeline.fit(dd["train_labels"])
        
        # 5. 转换数据
        dd["train_features"] = dk.feature_pipeline.transform(dd["train_features"])
        dd["train_labels"] = dk.label_pipeline.transform(dd["train_labels"])
        
        if len(dd.get("test_features", [])) > 0:
            dd["test_features"] = dk.feature_pipeline.transform(dd["test_features"])
            dd["test_labels"] = dk.label_pipeline.transform(dd["test_labels"])
        
        # 6. 训练模型
        model = self.fit(dd, dk)
        
        # 7. 保存
        timestamp = int(datetime.now().timestamp())
        self.dd.save_model(pair, model, timestamp)
        self.dd.update_pair_dict(pair, {
            "model_filename": self.dd.model_filename(pair, timestamp),
            "trained_timestamp": timestamp,
        })
        
        return model
    
    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """
        通用预测流程:
        1. 过滤特征
        2. 管道转换
        3. 预测
        4. 反向转换
        5. 保存预测历史
        """
        # 1. 过滤
        features, _ = dk.filter_features(df)
        
        # 2. 转换
        features = dk.feature_pipeline.transform(features)
        
        # 3. 加载模型并预测
        model = self.dd.load_model(dk.pair)
        predictions = model.predict(features)
        
        # 4. 反向转换
        predictions = dk.label_pipeline.inverse_transform(predictions)
        
        # 5. 保存历史
        pred_df = pl.DataFrame({
            "datetime": df["datetime"],
            "pair": dk.pair,
            "prediction": predictions,
        })
        self._update_historic_predictions(dk.pair, pred_df)
        
        return pred_df
    
    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> Any:
        """子类实现具体训练逻辑"""
        pass
    
    def define_data_pipeline(self) -> Any:
        """定义特征处理管道 - 子类可覆盖"""
        pass
    
    def define_label_pipeline(self) -> Any:
        """定义标签处理管道 - 子类可覆盖"""
        pass
```

### 3.5 XGBoostExtremaModel (具体实现)

**复刻**: `freqtrade/freqai/prediction_models/XGBoostRegressorQuickAdapterV5.py`

```python
class XGBoostExtremaModel(BaseRegressionModel):
    """
    XGBoost 极值模型 - 复刻 QuickAdapterV5
    
    特性:
    - 渐进式阈值预热
    - 动态阈值计算
    - DI 异常检测
    """
    
    # 默认阈值
    DEFAULT_MAXIMA_THRESHOLD = 2.0
    DEFAULT_MINIMA_THRESHOLD = -2.0
    DEFAULT_DI_CUTOFF = 2.0
    MIN_CANDLES_FOR_DYNAMIC = 50
    
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> Any:
        """XGBoost 训练"""
        from xgboost import XGBRegressor
        
        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]
        
        model = XGBRegressor(
            learning_rate=self.config.get("learning_rate", 0.05),
            max_depth=self.config.get("max_depth", 6),
            n_estimators=self.config.get("n_estimators", 100),
            early_stopping_rounds=self.config.get("early_stopping_rounds", 50),
        )
        
        if len(data_dictionary.get("test_features", [])) > 0:
            model.fit(
                X=X, y=y,
                eval_set=[(data_dictionary["test_features"], data_dictionary["test_labels"])],
            )
        else:
            model.fit(X=X, y=y)
        
        return model
    
    def fit_live_predictions(
        self,
        dk: StockaiDataKitchen,
        pair: str,
    ) -> None:
        """
        渐进式阈值计算
        
        直接复刻 QuickAdapterV5 的逻辑:
        - 计算预热进度
        - 混合默认阈值和动态阈值
        - 计算 DI cutoff
        """
        # 获取历史预测数量
        historic_len = len(self.dd.historic_predictions.get(pair, []))
        
        # 计算预热进度
        num_candles = self.config.get("fit_live_predictions_candles", 200)
        warmup_progress = min(1.0, historic_len / num_candles)
        
        # 获取预测数据
        pred_df = self.dd.historic_predictions[pair].tail(num_candles)
        
        # 计算渐进阈值
        maxima_threshold, minima_threshold = self._compute_progressive_thresholds(
            pred_df, warmup_progress, num_candles
        )
        
        # 计算 DI cutoff
        di_cutoff, di_params = self._compute_progressive_di_cutoff(
            pred_df, warmup_progress
        )
        
        # 存储到 dk.data
        dk.data["extra_returns_per_train"] = {
            "&s-maxima_sort_threshold": maxima_threshold,
            "&s-minima_sort_threshold": minima_threshold,
            "DI_cutoff": di_cutoff,
            "DI_value_param1": di_params[0],
            "DI_value_param2": di_params[1],
            "DI_value_param3": di_params[2],
        }
    
    def _compute_progressive_thresholds(
        self,
        pred_df: pl.DataFrame,
        warmup_progress: float,
        num_candles: int,
    ) -> tuple[float, float]:
        """计算渐进式阈值"""
        pass
    
    def _compute_progressive_di_cutoff(
        self,
        pred_df: pl.DataFrame,
        warmup_progress: float,
    ) -> tuple[float, tuple]:
        """计算渐进式 DI cutoff"""
        pass
```

---

## 4. 配置格式

```json
{
    "stockai": {
        "enabled": true,
        "path": "./stockai_data",
        
        "feature_parameters": {
            "periods": [10, 20, 30, 40],
            "label_period_candles": 10,
            "include_shifted_candles": [1, 2, 3],
            "DI_threshold": 0
        },
        
        "data_split_parameters": {
            "test_size": 0.2,
            "shuffle": false
        },
        
        "model_training_parameters": {
            "learning_rate": 0.05,
            "max_depth": 6,
            "n_estimators": 100,
            "early_stopping_rounds": 50
        },
        
        "train_period_days": 300,
        "backtest_period_days": 30,
        "fit_live_predictions_candles": 200
    }
}
```

---

## 5. 数据存储格式

### 存储路径结构

```
stockai_data/
├── historic_predictions.parquet    # 所有股票的历史预测
├── pair_dictionary.json            # 股票元数据
├── global_metadata.json            # 全局元数据
└── sub-train-{pair}_{timestamp}/   # 每只股票每个版本的模型
    ├── model.pkl
    └── metadata.json
```

### historic_predictions.parquet 列结构

| 列名 | 类型 | 说明 |
|------|------|------|
| datetime | datetime | 预测时间戳 |
| pair | string | 股票代码 |
| prediction | float | 预测值 (&s-extrema) |
| maxima_threshold | float | 高点阈值 |
| minima_threshold | float | 低点阈值 |
| DI_cutoff | float | DI cutoff |
| DI_values | float | DI 值 |
| model_version | string | 模型版本 |

---

## 6. 使用示例

### 6.1 批量回测

```python
from vnpy.stockai import XGBoostExtremaModel
from vnpy.stockai.config import load_config

# 加载配置
config = load_config("config.json")

# 初始化模型
stockai = XGBoostExtremaModel(config, lab)

# 批量训练并预测
pairs = ["000001.SZSE", "000002.SZSE"]
results = []

for pair in pairs:
    # 创建数据厨房
    dk = StockaiDataKitchen(config, pair, lab)
    
    # 加载数据
    df = dk.load_data("2025-01-01", "2025-06-01")
    
    # 训练
    model = stockai.train(df, pair, dk)
    
    # 预测
    predictions = stockai.predict(df, dk)
    results.append(predictions)

# 合并结果
all_predictions = pl.concat(results)
```

### 6.2 实时预测

```python
# 初始化
stockai = XGBoostExtremaModel(config, lab)

# K线更新时触发
def on_bar_update(pair: str, candle: dict):
    # 创建数据厨房
    dk = StockaiDataKitchen(config, pair, lab)
    
    # 加载最新数据
    df = dk.load_data(candle["start"], candle["end"])
    
    # 检查是否需要重训练
    if stockai.dd.should_retrain(pair):
        stockai.train(df, pair, dk)
    
    # 预测
    predictions = stockai.predict(df, dk)
    
    # 计算动态阈值（实时模式下）
    stockai.fit_live_predictions(dk, pair)
    
    # 获取阈值
    thresholds = dk.data.get("extra_returns_per_train", {})
    
    return predictions, thresholds
```

### 6.3 查询历史预测

```python
# 直接访问 DataDrawer
history = stockai.dd.historic_predictions.get("000001.SZSE")

# 按时间范围查询
filtered = history.filter(
    (pl.col("datetime") >= "2025-01-01") &
    (pl.col("datetime") <= "2025-06-01")
)
```

---

## 7. 与 FreqAI 的对应关系

| FreqAI 类 | StockAI 类 | 说明 |
|-----------|-----------|------|
| IFreqaiModel | IStockaiModel | 主接口 |
| FreqaiDataKitchen | StockaiDataKitchen | 数据厨房 |
| FreqaiDataDrawer | StockaiDataDrawer | 数据抽屉 |
| BaseRegressionModel | BaseRegressionModel | 回归基类 |
| XGBoostRegressor | XGBoostExtremaModel | 具体实现 |
| DataProvider | AlphaLabV2 | 数据源 |

---

## 8. 依赖

- polars (数据处理)
- pyarrow (Parquet 存储)
- xgboost (模型)
- scikit-learn (管道)
- 现有 vnpy 组件 (AlphaLabV2, QuickAdapterV5Dataset)
