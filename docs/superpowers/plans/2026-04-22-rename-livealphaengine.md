# 重构 LiveAlphaEngine 为 TradeEngine 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `LiveAlphaEngine` 重命名为 `TradeEngine`，移除 `RpcWebEngine` 中的 mock 参数，统一由 `TradeEngine` 管理模拟/实盘数据

**Architecture:** `TradeEngine` 内部通过 `paper_trading` 参数区分模拟盘和实盘，Web 看板统一从 `TradeEngine` 获取数据（而非 RPC 或 mock）

**Tech Stack:** Python, vnpy framework

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `vnpy/alpha/strategy/live_engine.py` | 重命名类 `LiveAlphaEngine` → `TradeEngine` |
| `vnpy/alpha/strategy/__init__.py` | 更新导出 `TradeEngine`，保留 `LiveAlphaEngine` 别名向后兼容 |
| `vnpy/web/rpc_engine.py` | 移除 mock 参数，仅保留 `live_engine` 绑定 |
| `xgb_extrema_live_trading.py` | 更新导入和 `LiveTrader` 中的引用 |

---

## Task 1: 重命名 LiveAlphaEngine 为 TradeEngine

**Files:**
- Modify: `vnpy/alpha/strategy/live_engine.py`

- [ ] **Step 1: 修改类名**

```python
# 修改前
class LiveAlphaEngine:
    """Alpha 策略实盘交易引擎"""

# 修改后
class TradeEngine:
    """交易引擎（支持模拟盘和实盘）"""
```

- [ ] **Step 2: 更新类文档字符串**

```python
class TradeEngine:
    """交易引擎

    支持两种模式：
    1. 实盘模式 (paper_trading=False): 真实订单发送到交易所
    2. 模拟盘模式 (paper_trading=True): 使用实时行情，本地模拟撮合

    与 BacktestingEngine 保持接口兼容，方便策略无缝切换。
    """
```

- [ ] **Step 3: Commit**

```bash
git add vnpy/alpha/strategy/live_engine.py
git commit -m "refactor(strategy): 重命名 LiveAlphaEngine 为 TradeEngine"
```

---

## Task 2: 更新 strategy __init__.py 导出

**Files:**
- Modify: `vnpy/alpha/strategy/__init__.py`

- [ ] **Step 1: 更新导入和导出**

```python
from .template import AlphaStrategy
from .backtesting import BacktestingEngine
from .live_engine import TradeEngine

# 向后兼容别名
LiveAlphaEngine = TradeEngine

__all__ = [
    "AlphaStrategy",
    "BacktestingEngine",
    "TradeEngine",
    "LiveAlphaEngine",  # 向后兼容
]
```

- [ ] **Step 2: Commit**

```bash
git add vnpy/alpha/strategy/__init__.py
git commit -m "refactor(strategy): 更新导出 TradeEngine，保留 LiveAlphaEngine 别名"
```

---

## Task 3: 移除 RpcWebEngine 的 mock 参数

**Files:**
- Modify: `vnpy/web/rpc_engine.py`

- [ ] **Step 1: 修改 __init__ 签名，移除 mock 参数**

```python
# 修改前
def __init__(
    self,
    main_engine: MainEngine,
    event_engine: EventEngine,
    req_address: str = "tcp://localhost:2014",
    sub_address: str = "tcp://localhost:2015",
    mock_capital: float = 1_000_000.0,
    mock_commission_rate: float = 0.0003,
    mock_tax_rate: float = 0.001,
) -> None:

# 修改后
def __init__(
    self,
    main_engine: MainEngine,
    event_engine: EventEngine,
    req_address: str = "tcp://localhost:2014",
    sub_address: str = "tcp://localhost:2015",
) -> None:
```

- [ ] **Step 2: 移除 mock 参数的初始化**

```python
# 删除以下代码
# self.mock_capital = mock_capital
# self.mock_commission_rate = mock_commission_rate
# self.mock_tax_rate = mock_tax_rate
# self._mock_account: Optional[dict] = None
```

- [ ] **Step 3: 修改 _get_mock_account_data 使用硬编码默认值**

```python
def _get_mock_account_data(self) -> dict:
    """获取模拟账户数据（降级使用）"""
    return {
        "balance": 1000000.0,
        "available": 950000.0,
        "frozen": 50000.0
    }
```

- [ ] **Step 4: 将 live_engine 属性类型改为 TradeEngine**

```python
# 修改前
self.live_engine: Optional = None

# 修改后（添加类型注释）
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from vnpy.alpha.strategy import TradeEngine

self.live_engine: Optional["TradeEngine"] = None
```

- [ ] **Step 5: Commit**

```bash
git add vnpy/web/rpc_engine.py
git commit -m "refactor(web): 移除 RpcWebEngine mock 参数，由 TradeEngine 管理数据"
```

---

## Task 4: 更新 xgb_extrema_live_trading.py

**Files:**
- Modify: `xgb_extrema_live_trading.py`

- [ ] **Step 1: 更新导入语句**

```python
# 修改前
from vnpy.alpha.strategy import LiveAlphaEngine

# 修改后
from vnpy.alpha.strategy import TradeEngine
```

- [ ] **Step 2: 更新 LiveTrader.__init__ 中的类型注释**

```python
# 修改前
self.live_engine: LiveAlphaEngine | None = None

# 修改后
self.live_engine: TradeEngine | None = None
```

- [ ] **Step 3: 更新 setup_strategy 中的实例化**

```python
# 修改前
self.live_engine = LiveAlphaEngine(
    main_engine=self.main_engine,
    event_engine=self.event_engine,
    lab=self.lab,
    gateway_name=self.gateway_name,
    paper_trading=self.paper_trading
)

# 修改后
self.live_engine = TradeEngine(
    main_engine=self.main_engine,
    event_engine=self.event_engine,
    lab=self.lab,
    gateway_name=self.gateway_name,
    paper_trading=self.paper_trading
)
```

- [ ] **Step 4: 更新 start 方法中的 RpcWebEngine 创建**

```python
# 修改前
self.web_engine = RpcWebEngine(
    main_engine=self.main_engine,
    event_engine=self.event_engine,
    req_address=self.rpc_req,
    sub_address=self.rpc_sub,
    mock_capital=self.capital,
)

# 修改后
self.web_engine = RpcWebEngine(
    main_engine=self.main_engine,
    event_engine=self.event_engine,
    req_address=self.rpc_req,
    sub_address=self.rpc_sub,
)
```

- [ ] **Step 5: Commit**

```bash
git add xgb_extrema_live_trading.py
git commit -m "refactor(trading): 更新使用 TradeEngine 替代 LiveAlphaEngine"
```

---

## Task 5: 最终验证

- [ ] **Step 1: 检查是否有遗漏的引用**

```bash
grep -r "LiveAlphaEngine" --include="*.py" vnpy/ examples/ || echo "No references found"
```

Expected: 仅 `__init__.py` 中的别名定义

- [ ] **Step 2: 最终 Commit**

```bash
git add -A
git commit -m "refactor: 完成 LiveAlphaEngine → TradeEngine 重构"
```

---

## 自我检查清单

**1. Spec 覆盖:**
- ✅ LiveAlphaEngine → TradeEngine 重命名
- ✅ 移除 RpcWebEngine 的 mock 参数
- ✅ 保留 LiveAlphaEngine 别名向后兼容
- ✅ 更新所有引用

**2. Placeholder 检查:**
- 无 TBD/TODO
- 所有代码完整可执行

**3. 类型一致性:**
- `TradeEngine` 类名一致
- `live_engine` 类型注释正确

---

## 执行选项

**Plan complete. Two execution options:**

**1. Subagent-Driven (recommended)** - Fresh subagent per task, review between tasks

**2. Inline Execution** - Execute in this session using executing-plans

**Which approach?**
