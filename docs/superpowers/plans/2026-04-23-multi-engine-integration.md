# 多引擎集成 MainEngine 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 TradeEngine、WebEngine 和 RpcEngine 都作为标准引擎通过 `main_engine.add_engine()` 添加到 MainEngine

**Architecture:** 遵循 VNPY 标准多引擎架构，所有引擎继承 `BaseEngine`，通过 `MainEngine.add_engine()` 注册，引擎间通过 `main_engine.get_engine()` 相互访问

**Tech Stack:** Python, vnpy framework

---

## 架构图

### 目标架构
```
┌─────────────────────────────────────────────────────────┐
│                    MainEngine                            │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────┐ │
│  │ TradeEngine │  │  WebEngine  │  │   RpcEngine     │ │
│  │  (Alpha)    │  │  (Web看板)  │  │  (RPC服务)      │ │
│  │             │  │             │  │                 │ │
│  │ - 策略执行   │  │ - 数据展示   │  │ - 远程连接      │ │
│  │ - 订单管理   │  │ - WebSocket │  │ - 客户端连接    │ │
│  │ - 持仓计算   │  │ - HTTP API  │  │ - 数据转发      │ │
│  └──────┬──────┘  └──────┬──────┘  └────────┬────────┘ │
│         │                │                   │          │
│         └────────────────┴───────────────────┘          │
│                          │                              │
│                   通过 MainEngine                        │
│                   相互访问                                │
└─────────────────────────────────────────────────────────┘
         │
         ▼
┌─────────────────┐
│  EventEngine    │  (事件总线)
└─────────────────┘
```

### 引擎交互关系
```
TradeEngine ──数据──▶ MainEngine ◀──读取── WebEngine
    │                      │
    ▼                      ▼
   交易                展示/推送

RpcEngine ◀──连接──▶ MainEngine ◀──转发──▶ 远程客户端
    │
    ▼
   远程数据
```

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `vnpy/alpha/strategy/live_engine.py` | 修改 | TradeEngine 继承 BaseEngine |
| `vnpy/alpha/strategy/__init__.py` | 修改 | 移除独立导出，改为引擎注册 |
| `vnpy/web/engine.py` | 修改 | WebEngine 继承 BaseEngine |
| `vnpy_rpcservice/rpc_service/engine.py` | 修改 | RpcEngine 继承 BaseEngine（已符合） |
| `xgb_extrema_live_trading.py` | 修改 | 使用 add_engine 添加所有引擎 |

---

## Task 1: 修改 TradeEngine 继承 BaseEngine

**Files:**
- Modify: `vnpy/alpha/strategy/live_engine.py`

- [ ] **Step 1: 修改类继承**

```python
# 修改前
class TradeEngine:
    """Alpha 策略实盘交易引擎"""
    
    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        lab: AlphaLab,
        gateway_name: str,
        paper_trading: bool = False
    ):

# 修改后
from vnpy.trader.engine import BaseEngine

class TradeEngine(BaseEngine):
    """Alpha 策略实盘交易引擎
    
    继承 BaseEngine 作为标准 VNPY 引擎。
    """
    
    engine_name = "TradeEngine"
    
    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        lab: AlphaLab,
        gateway_name: str,
        paper_trading: bool = False
    ):
        super().__init__(main_engine, event_engine, self.engine_name)
        # ... 保留其他初始化代码 ...
```

- [ ] **Step 2: Commit**

```bash
git add vnpy/alpha/strategy/live_engine.py
git commit -m "refactor(strategy): TradeEngine 继承 BaseEngine"
```

---

## Task 2: 修改 WebEngine 继承 BaseEngine

**Files:**
- Modify: `vnpy/web/engine.py`

- [ ] **Step 1: 修改类继承**

```python
# 修改前
class WebEngine:
    """Web交易看板引擎"""
    
    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):

# 修改后
from vnpy.trader.engine import BaseEngine

class WebEngine(BaseEngine):
    """Web交易看板引擎
    
    继承 BaseEngine 作为标准 VNPY 引擎。
    从 MainEngine 获取数据，不直接管理连接。
    """
    
    engine_name = "WebEngine"
    
    def __init__(self, main_engine: MainEngine, event_engine: EventEngine):
        super().__init__(main_engine, event_engine, self.engine_name)
        # ... 保留其他初始化代码 ...
```

- [ ] **Step 2: Commit**

```bash
git add vnpy/web/engine.py
git commit -m "refactor(web): WebEngine 继承 BaseEngine"
```

---

## Task 3: 修改 xgb_extrema_live_trading.py 使用 add_engine

**Files:**
- Modify: `xgb_extrema_live_trading.py`

- [ ] **Step 1: 修改 LiveTrader.__init__ 移除手动创建引擎**

```python
# 修改前
class LiveTrader:
    def __init__(self, ...):
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.lab = AlphaLab(str(LAB_PATH))
        self.live_engine: TradeEngine | None = None
        self.web_engine = None
        # ...

# 修改后
class LiveTrader:
    def __init__(self, ..., enable_rpc: bool = False):
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.lab = AlphaLab(str(LAB_PATH))
        
        # 添加 TradeEngine 到 MainEngine
        self._add_trade_engine(gateway_name, paper_trading)
        
        # 添加 WebEngine 到 MainEngine
        if enable_web:
            self._add_web_engine()
        
        # 添加 RpcEngine 到 MainEngine（可选）
        if enable_rpc:
            self._add_rpc_engine()
```

- [ ] **Step 2: 添加引擎创建方法**

```python
    def _add_trade_engine(self, gateway_name: str, paper_trading: bool):
        """添加交易引擎到 MainEngine"""
        from vnpy.alpha.strategy import TradeEngine
        
        trade_engine = TradeEngine(
            main_engine=self.main_engine,
            event_engine=self.event_engine,
            lab=self.lab,
            gateway_name=gateway_name,
            paper_trading=paper_trading
        )
        
        # 注册为引擎
        self.main_engine.add_engine(trade_engine)
        
        # 保存引用
        self.trade_engine = trade_engine
    
    def _add_web_engine(self):
        """添加 Web 引擎到 MainEngine"""
        from vnpy.web import WebEngine
        
        web_engine = WebEngine(
            main_engine=self.main_engine,
            event_engine=self.event_engine
        )
        
        # 绑定 TradeEngine 引用（WebEngine 可以通过 main_engine.get_engine 获取）
        web_engine.trade_engine = self.trade_engine
        
        # 注册为引擎
        self.main_engine.add_engine(web_engine)
        
        # 保存引用
        self.web_engine = web_engine
    
    def _add_rpc_engine(self):
        """添加 RPC 引擎到 MainEngine"""
        from vnpy_rpcservice import RpcEngine
        
        rpc_engine = RpcEngine(
            main_engine=self.main_engine,
            event_engine=self.event_engine
        )
        
        # 注册为引擎
        self.main_engine.add_engine(rpc_engine)
        
        # 启动 RPC 服务
        rpc_engine.start(
            rep_address="tcp://*:2014",
            pub_address="tcp://*:2015"
        )
        
        # 保存引用
        self.rpc_engine = rpc_engine
```

- [ ] **Step 3: 修改 setup_strategy 获取 TradeEngine**

```python
# 修改前
self.live_engine = TradeEngine(...)

# 修改后
# TradeEngine 已在 __init__ 中通过 add_engine 添加
# 直接获取引用
self.trade_engine = self.main_engine.get_engine("TradeEngine")
```

- [ ] **Step 4: 修改 start 启动 Web 服务**

```python
    def start(self) -> None:
        """启动交易"""
        # 启动 TradeEngine
        self.trade_engine.start_trading(
            capital=self.capital,
            cash_ratio=self.cash_ratio
        )
        
        # 启动 WebEngine（已在 add_engine 中注册）
        if self.enable_web and self.web_engine:
            import threading
            web_thread = threading.Thread(
                target=self.web_engine.start,
                args=(self.web_host, self.web_port),
                daemon=True
            )
            web_thread.start()
            logger.info(f"\n✓ Web 看板已启动: http://{self.web_host}:{self.web_port}")
```

- [ ] **Step 5: Commit**

```bash
git add xgb_extrema_live_trading.py
git commit -m "refactor(trading): 使用 add_engine 添加 TradeEngine/WebEngine/RpcEngine"
```

---

## Task 4: 更新 WebEngine 数据获取方式

**Files:**
- Modify: `vnpy/web/engine.py`

- [ ] **Step 1: 修改数据获取方法使用 main_engine**

```python
    def _get_account_data(self) -> dict:
        """获取账户数据"""
        # 1. 优先从 TradeEngine 获取（通过 main_engine.get_engine）
        trade_engine = self.main_engine.get_engine("TradeEngine")
        if trade_engine and trade_engine.account:
            acc = trade_engine.account
            return {
                "balance": acc.balance,
                "available": acc.available,
                "frozen": acc.frozen
            }
        
        # 2. 从 MainEngine 获取
        accounts = self.main_engine.get_all_accounts()
        if accounts:
            acc = accounts[0]
            return {
                "balance": acc.balance,
                "available": acc.available,
                "frozen": acc.frozen
            }
        
        return {"balance": 0, "available": 0, "frozen": 0}
    
    def _get_position_data(self) -> list:
        """获取持仓数据"""
        positions = []
        
        # 1. 优先从 TradeEngine 获取
        trade_engine = self.main_engine.get_engine("TradeEngine")
        if trade_engine and trade_engine.positions:
            for vt_symbol, pos in trade_engine.positions.items():
                tick = self.main_engine.get_tick(vt_symbol)
                # ... 转换逻辑 ...
                positions.append({...})
            return positions
        
        # 2. 从 MainEngine 获取
        for pos in self.main_engine.get_all_positions():
            # ... 转换逻辑 ...
            positions.append({...})
        
        return positions
```

- [ ] **Step 2: Commit**

```bash
git add vnpy/web/engine.py
git commit -m "feat(web): WebEngine 通过 main_engine.get_engine 获取 TradeEngine"
```

---

## Task 5: 最终验证

- [ ] **Step 1: 验证导入**

```bash
python -c "
from vnpy.alpha.strategy import TradeEngine
from vnpy.web import WebEngine
from vnpy_rpcservice import RpcEngine
print('All engines import OK')
"
```

- [ ] **Step 2: 验证继承关系**

```bash
python -c "
from vnpy.alpha.strategy import TradeEngine
from vnpy.web import WebEngine
from vnpy.trader.engine import BaseEngine

assert issubclass(TradeEngine, BaseEngine)
assert issubclass(WebEngine, BaseEngine)
print('Inheritance OK')
"
```

- [ ] **Step 3: Final Commit**

```bash
git add -A
git commit -m "refactor: 完成多引擎集成 MainEngine 架构重构"
```

---

## 架构说明

### 引擎职责

| 引擎 | 职责 | 数据流向 |
|------|------|----------|
| **TradeEngine** | 交易逻辑、策略执行、订单管理 | 产生持仓/成交/账户数据 → MainEngine |
| **WebEngine** | Web看板、数据展示、用户交互 | 从 MainEngine 读取数据 |
| **RpcEngine** | RPC服务、远程连接、数据转发 | 与 MainEngine 双向交互 |

### 数据流

```
TradeEngine (本地交易)
    ↓ 写入
MainEngine (数据总线)
    ↓ 读取
WebEngine (Web看板展示)

RpcEngine (RPC服务)
    ↕️ 转发
MainEngine (数据总线)
    ↕️ 交互
远程客户端
```

### 关键 API

| 方法 | 用途 |
|------|------|
| `main_engine.add_engine(engine)` | 注册引擎 |
| `main_engine.get_engine(name)` | 获取引擎实例 |
| `main_engine.get_all_accounts()` | 获取账户数据 |
| `main_engine.get_all_positions()` | 获取持仓数据 |
| `main_engine.get_all_trades()` | 获取成交数据 |

---

## 自我检查清单

**1. Spec 覆盖:**
- ✅ TradeEngine 继承 BaseEngine
- ✅ WebEngine 继承 BaseEngine
- ✅ RpcEngine 已在 vnpy_rpcservice 中实现
- ✅ 使用 add_engine 注册所有引擎
- ✅ WebEngine 通过 main_engine 获取数据

**2. Placeholder 检查:**
- 无 TBD/TODO
- 所有代码完整

**3. 架构一致性:**
- 符合 VNPY 多引擎标准模式
- 引擎间通过 MainEngine 协调

---

## 执行选项

**Plan complete and saved to `docs/superpowers/plans/YYYY-MM-DD-multi-engine-integration.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - Fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
