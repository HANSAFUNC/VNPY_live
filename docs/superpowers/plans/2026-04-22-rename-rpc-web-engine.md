# 重命名 RpcWebEngine 避免与 RPC 引擎混淆实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重命名 `RpcWebEngine` 类为 `WebRemoteEngine`，避免与 `vnpy_rpcservice` 的 RPC 引擎混淆

**Architecture:** `vnpy_rpcservice` 是真正的 RPC 引擎，`vnpy/web/rpc_engine.py` 是 Web 看板的远程模式支持，需要明确区分命名

**Tech Stack:** Python, FastAPI, WebSocket

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `vnpy/web/rpc_engine.py` | 重命名类 `RpcWebEngine` → `WebRemoteEngine` |
| `vnpy/web/__init__.py` | 更新导出，保留 `RpcWebEngine` 别名向后兼容 |
| `xgb_extrema_live_trading.py` | 更新引用 |
| `web_dashboard_rpc.py` | 更新引用 |
| `examples/rpc_service/rpc_server_alpha.py` | 如有引用则更新 |

---

## Task 1: 重命名 RpcWebEngine 类为 WebRemoteEngine

**Files:**
- Modify: `vnpy/web/rpc_engine.py`

- [ ] **Step 1: 修改类名和文档字符串**

```python
# 修改前
class RpcWebEngine(WebEngine):
    """RPC客户端模式的Web引擎

    通过RPC连接到远程交易服务器，而不是本地MainEngine。
    继承WebEngine以保持所有Web功能，重载数据获取方法。
    """
    engine_name: str = "RpcWebEngine"

# 修改后
class WebRemoteEngine(WebEngine):
    """Web看板远程引擎

    通过RPC客户端连接到远程交易服务器，数据从远程获取。
    用于 Web 看板在本地显示远程交易服务器的数据。
    继承WebEngine以保持所有Web功能，重载数据获取方法。
    """
    engine_name: str = "WebRemoteEngine"
```

- [ ] **Step 2: 更新所有文档字符串中的引用**

```python
# 修改前
"""RPC模式的Web看板引擎

支持远程连接交易服务器，所有数据通过RPC获取。
"""

# 修改后
"""Web看板远程引擎

支持通过RPC客户端连接远程交易服务器，所有数据从远程获取。
"""
```

- [ ] **Step 3: Commit**

```bash
git add vnpy/web/rpc_engine.py
git commit -m "refactor(web): 重命名 RpcWebEngine 为 WebRemoteEngine"
```

---

## Task 2: 更新 web __init__.py 导出

**Files:**
- Modify: `vnpy/web/__init__.py`

- [ ] **Step 1: 更新导入和导出**

```python
# vnpy/web/__init__.py

try:
    from .engine import WebEngine
except ImportError:
    WebEngine = None  # fastapi not installed

try:
    from .rpc_engine import WebRemoteEngine
except ImportError:
    WebRemoteEngine = None

# 向后兼容别名
RpcWebEngine = WebRemoteEngine

from .templates import (
    DashboardData,
    StrategyStatus,
    PositionView,
    TradeView,
    SignalView,
    AccountData,
    CandleData,
    ChartData,
    StatsData,
)

__all__ = [
    "WebEngine",
    "WebRemoteEngine",
    "RpcWebEngine",  # 向后兼容
    "DashboardData",
    "StrategyStatus",
    "PositionView",
    "TradeView",
    "SignalView",
    "AccountData",
    "CandleData",
    "ChartData",
    "StatsData",
]

__version__ = "1.0.0"
```

- [ ] **Step 2: Commit**

```bash
git add vnpy/web/__init__.py
git commit -m "refactor(web): 更新导出 WebRemoteEngine，保留 RpcWebEngine 别名"
```

---

## Task 3: 更新 xgb_extrema_live_trading.py 引用

**Files:**
- Modify: `xgb_extrema_live_trading.py`

- [ ] **Step 1: 更新导入和实例化**

```python
# 修改前
from vnpy.web import RpcWebEngine

self.web_engine = RpcWebEngine(...)

# 修改后
from vnpy.web import WebRemoteEngine

self.web_engine = WebRemoteEngine(...)
```

- [ ] **Step 2: Commit**

```bash
git add xgb_extrema_live_trading.py
git commit -m "refactor(trading): 更新使用 WebRemoteEngine 替代 RpcWebEngine"
```

---

## Task 4: 更新 web_dashboard_rpc.py 引用

**Files:**
- Modify: `web_dashboard_rpc.py`

- [ ] **Step 1: 更新导入和实例化**

```python
# 修改前
from vnpy.web import RpcWebEngine

self.rpc_engine = RpcWebEngine(...)

# 修改后
from vnpy.web import WebRemoteEngine

self.rpc_engine = WebRemoteEngine(...)
```

- [ ] **Step 2: Commit**

```bash
git add web_dashboard_rpc.py
git commit -m "refactor(web): 更新 web_dashboard_rpc.py 使用 WebRemoteEngine"
```

---

## Task 5: 检查并更新其他文件

**Files:**
- Check: `examples/rpc_service/rpc_server_alpha.py`
- Check: `tests/test_rpc_web.py`

- [ ] **Step 1: 检查引用**

```bash
grep -r "RpcWebEngine" --include="*.py" . 2>/dev/null | grep -v __pycache__ | grep -v ".pyc"
```

- [ ] **Step 2: 如有需要，更新引用**

```python
# 如有引用，改为 WebRemoteEngine
from vnpy.web import WebRemoteEngine
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: 更新所有 RpcWebEngine 引用为 WebRemoteEngine"
```

---

## Task 6: 最终验证

- [ ] **Step 1: 验证导入**

```bash
python -c "from vnpy.web import WebRemoteEngine, RpcWebEngine; print('Import OK')"
```

Expected: Import OK

- [ ] **Step 2: 验证别名**

```bash
python -c "from vnpy.web import WebRemoteEngine, RpcWebEngine; assert RpcWebEngine is WebRemoteEngine; print('Alias OK')"
```

Expected: Alias OK

- [ ] **Step 3: 检查无遗漏**

```bash
grep -r "RpcWebEngine" --include="*.py" vnpy/ web_dashboard_rpc.py xgb_extrema_live_trading.py 2>/dev/null | grep -v __pycache__ | grep -v "# 向后兼容"
```

Expected: 无输出（或仅注释中的引用）

- [ ] **Step 4: Final Commit**

```bash
git add -A
git commit -m "refactor: 完成 RpcWebEngine → WebRemoteEngine 重命名"
```

---

## 命名对比说明

| 组件 | 旧名称 | 新名称 | 说明 |
|------|--------|--------|------|
| Web看板远程模式 | `RpcWebEngine` | `WebRemoteEngine` | Web 看板通过 RPC 客户端连接远程服务器 |
| RPC服务引擎 | `RpcEngine` (vnpy_rpcservice) | 不变 | 真正的 RPC 服务端/客户端引擎 |

### 命名逻辑
- `WebRemoteEngine`: Web 看板的**远程模式**引擎
- `RpcEngine`/`RpcGateway`: **RPC 协议**引擎（vnpy_rpcservice）

---

## 自我检查清单

**1. Spec 覆盖:**
- ✅ 类名重命名 RpcWebEngine → WebRemoteEngine
- ✅ 文档字符串更新
- ✅ 导出更新，保留别名
- ✅ 所有引用更新

**2. Placeholder 检查:**
- 无 TBD/TODO
- 所有代码完整

**3. 向后兼容:**
- ✅ RpcWebEngine = WebRemoteEngine 别名
- ✅ 旧代码导入 RpcWebEngine 仍然工作

---

## 执行选项

**Plan complete. Two execution options:**

**1. Subagent-Driven (recommended)** - Fresh subagent per task, review between tasks

**2. Inline Execution** - Execute tasks in this session

**Which approach?**
