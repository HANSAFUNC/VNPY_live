# CLAUDE.md

本文件为 Claude Code (claude.ai/code) 提供本代码库的开发指导。

## 项目概述

VeighNa 是基于 Python 的开源量化交易框架。本代码库包含：

- **vnpy/**: 核心框架包
  - **trader/**: 交易引擎和 UI 组件
  - **alpha/**: 机器学习策略模块（基于 ML 的交易策略）
    - dataset/: 因子/特征工程
    - model/: ML 模型训练（Lasso、LightGBM、MLP）
    - strategy/: 策略回测和实盘交易
    - lab.py: 研究工作流管理
  - **stockai/**: FreqAI 兼容的 ML 预测管道（新开发中）
    - data_drawer.py: 全局持久化存储管理
    - data_kitchen.py: 单股票数据管理
    - stockai_interface.py: 模型接口基类
    - base_models/: 回归和分类模型基类
    - prediction_models/: 具体模型实现（XGBoost 等）
  - **event/**: 事件驱动引擎
  - **chart/**: K 线图表组件
  - **rpc/**: 分布式系统 RPC

## 构建和开发命令

### 环境配置
```bash
# Windows（推荐使用 VeighNa Studio）
install.bat

# 或手动 pip 安装 alpha 依赖
pip install -e ".[alpha]"
```

### 代码质量

**使用 ruff 检查：**
```bash
ruff check .
ruff check --fix .
```

**使用 mypy 类型检查：**
```bash
mypy vnpy
```

### 运行测试

**运行所有测试：**
```bash
pytest
```

**运行特定测试：**
```bash
pytest tests/test_specific.py -v
```

**运行覆盖率测试：**
```bash
pytest --cov=vnpy --cov-report=term-missing
```

## 架构说明

### vnpy.alpha 模块

受 Microsoft Qlib 启发。核心设计：

- **AlphaDataset**: 基于表达式的特征工程
- **AlphaModel**: ML 模型抽象（Lasso、LightGBM、MLP 实现）
- **AlphaStrategy**: 集成 ML 信号的策略回测
- **AlphaLab**: 管理数据/模型/信号工作流；数据存储为 parquet 文件

数据流：原始 K 线 → Dataset（特征计算）→ Model（训练）→ Signal → Strategy

### vnpy.stockai 模块

FreqAI 兼容的时序 ML 实现：

- **StockaiDataDrawer**: 全局状态保持（持久化）。存储模型元数据、历史预测、模型缓存
- **StockaiDataKitchen**: 单股票临时数据处理。管理特征/标签过滤、训练测试分割、管道
- **IStockaiModel**: 抽象基类；子类实现 fit() 用于特定算法
- 关键概念：`%` 前缀列为特征，`&` 前缀列为标签/目标

### 关键约定

- alpha 和 stockai 模块使用 polars（非 pandas）进行数据操作
- GUI 组件使用 PySide6
- 全事件驱动架构
- 需要类型提示（mypy 强制检查）
- 所有模块使用 vnpy.alpha.logger 的 loguru 日志器

## 开发规范

**现有 CLAUDE.md（行为规范）：**

1. **编码前思考**：明确权衡，有疑问时询问
2. **简洁优先**：不添加推测性功能，不过早抽象
3. **精准修改**：只修改必要内容，保持现有风格
4. **目标导向**：定义可验证的成功标准

**项目特定补充：**

- 添加 ML 模型时：扩展 base_models，实现 fit() 方法
- 修改数据管道时：确保 polars DataFrame 兼容性
- FreqAI 对齐：属性/方法名与 FreqAI 参考（H:/freqtrade_live）保持一致
- StockAI 使用 `symbol` 参数（而非 `pair`）表示股票代码

## 测试模式

- 单元测试在 tests/ 目录
- 集成测试通常在根目录 check_*.py 文件中
- 示例笔记本在 examples/alpha_research/
- 运行 check_stockai.py 验证 stockai 模块

## 常用任务

**检查 stockai 实现：**
```bash
python check_stockai.py
```

**下载市场数据：**
```bash
python download_data.py
```

**运行 Web 面板：**
```bash
python run_web.py
```
