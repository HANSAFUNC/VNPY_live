# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 在此代码仓库中工作提供指导。

## 快速开始

```bash
# 安装依赖
pip install -e .[alpha]

# 运行测试
pytest tests/

# 运行特定测试
pytest tests/test_xgb_extrema_model.py -v
```

## 项目概述

VeighNa 4.0 - 基于 Python 的开源量化交易系统，配备 AI 驱动的 Alpha 研究能力。

### 核心架构

```
vnpy/
├── alpha/              # AI/ML 量化研究模块 (v4.0+)
│   ├── dataset/        # 特征工程与数据处理
│   │   ├── datasets/   # 预置特征集 (alpha_158, quick_adapter_v5)
│   │   └── processor.py
│   ├── model/          # ML 模型
│   │   └── models/     # Lasso, LightGBM, MLP, XGBoostExtrema
│   ├── strategy/       # 交易策略
│   │   └── strategies/
│   └── lab.py          # 研究工作流管理 (AlphaLab)
├── trader/             # 核心交易引擎
└── [gateway 模块]      # 交易接口 (CTP, XTP 等)
```

### vnpy.alpha 模块

`vnpy.alpha` 模块为 ML 量化策略提供标准化工作流：

1. **数据加载** (`AlphaLab`)
   - `load_bar_df()`: 加载 K 线数据为 Polars DataFrame
   - `load_component_symbols()`: 加载指数成分股代码
   - `save/load_dataset()`, `save/load_model()`, `save/load_signal()`

2. **特征工程** (`AlphaDataset`)
   - `fetch_learn(segment)`: 获取训练数据（特征 + 标签）
   - `fetch_infer(segment)`: 获取推理数据（仅特征）
   - 分段：TRAIN（训练）, VALID（验证）, TEST（测试）

3. **模型训练** (`AlphaModel`)
   - 标准化 API: `fit(dataset)`, `predict(dataset, segment)`
   - 模型：LassoModel, LgbModel, MlpModel, XGBoostExtremaModel

4. **策略回测** (`BacktestingEngine`)
   - 加载信号、运行回测、计算统计

### 关键设计模式

**Segment 数据流：**
```python
# 训练
train_df = dataset.fetch_learn(Segment.TRAIN)
valid_df = dataset.fetch_learn(Segment.VALID)

# 推理
test_df = dataset.fetch_infer(Segment.TEST)
```

**模型工厂模式 (GroupedMultiModel)：**
```python
multi_model = GroupedMultiModel(
    model_factory=lambda: XGBoostExtremaModel(...),
    group_by="vt_symbol",  # 每只股票一个模型
)
```

**固定阈值机制 (XGBoostExtremaModel)：**
- 训练完成后不计算阈值
- 预测时从当前预测数据计算动态阈值（使用 frequency 方式）
- frequency = num_candles / (label_period_candles * 2)，默认 = 5

## 测试

测试位于 `tests/` 目录：

```bash
# 全部测试
pytest tests/ -v

# 带覆盖率
pytest tests/ --cov=vnpy.alpha

# 特定测试类
pytest tests/test_xgb_extrema_model.py::TestDIValuesComputation -v
```

## 常见工作流

### XGBoost 极值选股器工作流

参考 `examples/alpha_research/research_workflow_xgb_extrema.ipynb`：

```python
from vnpy.alpha import AlphaLab
from vnpy.alpha.dataset.datasets.quick_adapter_v5 import QuickAdapterV5Dataset
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel

# 1. 加载数据
lab = AlphaLab("./lab/csi300")
df = lab.load_bar_df(symbols, Interval.DAILY, start, end)

# 2. 创建数据集
dataset = QuickAdapterV5Dataset(df, train_period, valid_period, test_period, ...)
dataset.prepare_data(filters)

# 3. 训练模型
model = XGBoostExtremaModel(learning_rate=0.05, max_depth=6, ...)
model.fit(dataset)

# 4. 生成信号
predictions = model.predict(dataset, Segment.TEST)
result_df = model.get_result_df()

# 5. 回测
from vnpy.alpha.strategy import BacktestingEngine
engine = BacktestingEngine(lab)
engine.add_strategy(StrategyClass, setting, signal_df)
engine.run_backtesting()
```

## 开发注意事项

- **Polars** 是 alpha 模块的主要数据处理库（非 pandas）
- **Segment** 枚举：TRAIN, VALID, TEST - 控制数据获取
- **列命名**：特征列通常以 `%-` 前缀，标签列以 `&-` 前缀
- **XGBoostExtremaModel**：实现来自 freqtrade 的 DI 动态阈值机制（IsolationForest + Weibull 分布）

## 特征归一化

`vnpy.alpha.dataset` 提供 `FreqaiFeaturePipeline` 类，使用 datasieve 库实现 freqtrade 风格的特征处理：

```python
from functools import partial
from vnpy.alpha.dataset import FreqaiFeaturePipeline, process_freqai_feature_pipeline

# 创建管道（VarianceThreshold + MinMaxScaler）
feature_pipeline = FreqaiFeaturePipeline(threshold=0.0, feature_range=(-1, 1))

# 从学习数据拟合
learn_df = dataset.fetch_learn(Segment.TRAIN)
feature_pipeline.fit(learn_df)

# 添加处理器
dataset.add_processor("infer", partial(process_freqai_feature_pipeline, pipeline=feature_pipeline))
dataset.add_processor("learn", partial(process_freqai_feature_pipeline, pipeline=feature_pipeline))

# 处理数据
dataset.process_data()
```

**管道步骤**（与 freqtrade 一致）：
1. `ds.VarianceThreshold(threshold=0.0)` - 移除方差为 0 的特征
2. `SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1)))` - 归一化到 (-1, 1)
3. `ds.DissimilarityIndex(di_threshold, n_jobs)` - DI 异常检测（可选，需设置 `di_threshold > 0`）

**可用处理器：**
- `process_drop_na` - 删除 NaN 行
- `process_fill_na` - 填充 NaN 值
- `process_cs_norm` - 横截面归一化（robust/zscore）
- `process_robust_zscore_norm` - 稳健 Z-Score 归一化
- `process_cs_rank_norm` - 横截面排名归一化
- `FreqaiFeaturePipeline` + `process_freqai_feature_pipeline` - FreqAI 特征处理管道

### FreqAI 管道与 DI 阈值

`FreqaiFeaturePipeline` 支持配置 DI (Dissimilarity Index) 阈值，用于异常检测：

```python
from vnpy.alpha.dataset import FreqaiFeaturePipeline

# 从 ft_params 读取 DI 阈值配置（与 freqtrade 兼容）
ft_params = {"DI_threshold": 0.4, "n_jobs": -1}

# 创建带 DI 的管道
feature_pipeline = FreqaiFeaturePipeline(
    threshold=0.0,
    feature_range=(-1, 1),
    di_threshold=ft_params.get("DI_threshold", 0),  # DI 阈值
    n_jobs=ft_params.get("n_jobs", -1),
)

# 拟合并添加处理器
feature_pipeline.fit(dataset.fetch_learn(Segment.TRAIN))
dataset.add_processor("infer", feature_pipeline)
dataset.add_processor("learn", feature_pipeline)
dataset.process_data()

# DI_values 会自动添加到 DataFrame
# XGBoostExtremaModel.predict() 会自动从 DataFrame 读取 DI_values
```

**DI_values 获取逻辑：**
1. 如果管道包含 DI 步骤（`di_threshold > 0`），`transform()` 会从 `pipeline["di"].di_values` 获取并添加到 DataFrame
2. `XGBoostExtremaModel.predict()` 优先从 DataFrame 读取 `DI_values` 列
3. 如果没有则使用 `IsolationForest` 重新计算（向后兼容）

### 预测值逆向转换（Inverse Transform）

`FreqaiFeaturePipeline` 支持将归一化空间的预测值转换回原始数据范围：

```python
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel

# 创建模型时传入 feature_pipeline 并启用标签缩放
model = XGBoostExtremaModel(
    learning_rate=0.05,
    max_depth=6,
    feature_pipeline=feature_pipeline,  # 用于特征的 inverse_transform
    scale_label=True,  # 对标签进行缩放和逆转换（像 freqtrade 一样）
)

# 训练时标签被缩放到 (-1, 1) 范围
model.fit(dataset)

# 预测时自动执行 inverse_transform
predictions = model.predict(dataset, Segment.TEST)
# predictions 现在是原始范围的 values（如价格百分比变化）
```

**inverse_transform 原理：**
- **标签缩放**：使用 `MinMaxScaler(feature_range=(-1, 1))` 将标签缩放到 (-1, 1)
- **模型训练**：在缩放后的标签空间进行训练
- **预测逆转换**：使用 `scaler.inverse_transform()` 将预测值转换回原始范围
- **公式**：`X_original = X_scaled * (X_max - X_min) + X_min`

## 文件参考

| 文件 | 用途 |
|------|------|
| `vnpy/alpha/lab.py` | AlphaLab - 数据/模型/信号管理 |
| `vnpy/alpha/dataset/__init__.py` | AlphaDataset 基类，Segment 枚举，处理器导入 |
| `vnpy/alpha/dataset/processor.py` | 数据处理器（归一化、填充等） |
| `vnpy/alpha/model/__init__.py` | AlphaModel 基类 |
| `vnpy/alpha/model/models/xgb_extrema_model.py` | XGBoost 固定阈值模型 |
| `vnpy/alpha/model/models/grouped_multi_model.py` | 多模型包装器（按组分组） |
| `xgb_extrema_selector.py` | XGBoost 极值选股脚本 |
| `vnpy/alpha/strategy/backtesting.py` | 回测引擎 |
| `examples/alpha_research/*.ipynb` | 研究工作流示例 |

## 选股器脚本

`xgb_extrema_selector.py` 是独立的 XGBoost 极值选股脚本：

```python
from xgb_extrema_selector import XGBoostExtremaSelector

selector = XGBoostExtremaSelector(
    lab=lab,
    name="300_xgb_extrema",
    index_symbol="000300.SSE",
    start="2026-02-01",
    end="2026-04-15",
    top_n=100,              # 选股数量
    train_period_days=100,  # 训练期天数（从 start 往前推）
    extended_days=100,      # 额外缓冲天数
)
signal_df = selector.run()
```

**数据范围计算：**
- 测试期：`start` 到 `end`（用户输入的预测期间）
- 训练期 + 验证期：从 `start` 往前推 `train_period_days` 天
- 缓冲期：额外的 `extended_days` 天（用于特征计算）
- 总数据范围：从 `start - (train_period_days + extended_days)` 到 `end`

**自动数据下载：**
- 检测到本地数据不足时，自动通过 xtquant 下载缺失数据
- 使用 5 天容忍度（周末/节假日）

**阈值计算：**
- 训练完成后，使用 `_compute_dynamic_thresholds` 计算固定阈值
- frequency = num_candles / (label_period_candles * 2)，默认 = 15（300/50/2）
- DI_values：使用 IsolationForest 多变量异常检测计算异常分数
- DI_cutoff：使用 Weibull 分布拟合 DI_values，取 99.9% 分位数

## Web 交易看板

`vnpy/web/` 模块提供类似 freqUI 的网页交易界面：

```python
from vnpy.web import WebEngine
from vnpy.trader.engine import MainEngine

# 添加 Web 引擎
main_engine = MainEngine(event_engine)
web_engine = main_engine.add_engine(WebEngine)

# 启动 Web 服务
web_engine.start(host="0.0.0.0", port=8000)
```

**访问地址：** http://localhost:8000

**功能特性：**
- 实时账户概览（总资产、可用资金、当日盈亏）
- 持仓明细（代码、方向、盈亏、盈亏率）
- 成交记录实时监控
- 策略启停控制
- 交易信号展示

**启动脚本：**
```bash
# 启动 Web 看板
python web_dashboard.py

# 指定端口
python web_dashboard.py --port 8080
```

**技术栈：**
- 后端：FastAPI + WebSocket
- 前端：Vue3 + Element Plus
- 图表：ECharts

## 实盘/模拟盘交易

`xgb_extrema_live_trading.py` 支持三种交易模式：

| 模式 | 命令 | 说明 |
|------|------|------|
| 回测 | `--mode backtest` | 历史数据验证 |
| 模拟盘 | `--mode paper` | 实时行情 + 本地撮合 |
| 实盘 | `--mode live` | 真实交易所订单 |

**使用示例：**
```bash
# 1. 生成信号
python xgb_extrema_selector.py

# 2. 模拟盘测试
python xgb_extrema_live_trading.py --mode paper --capital 1000000

# 3. 实盘交易
python xgb_extrema_live_trading.py --mode live --gateway XT --capital 1000000
```

**详细文档：** [docs/LIVE_TRADING_GUIDE.md](docs/LIVE_TRADING_GUIDE.md)
