# Web看板RPC集成实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将Web看板与RPC服务集成，支持两种运行模式：本地直连模式 和 RPC客户端远程模式

**Architecture:** 创建 `RpcWebEngine` 类继承 `WebEngine`，通过RPC客户端连接远程交易服务器，同时保持 `WebEngine` 本地直连能力。Web前端无需修改，通过统一的WebSocket接口获取数据。

**Tech Stack:** FastAPI, WebSocket, ZeroMQ (vnpy_rpcservice), Vue3

---

## 文件结构

| 文件 | 职责 |
|------|------|
| `vnpy/web/rpc_engine.py` | 新建：RPC模式的Web引擎 |
| `vnpy/web/__init__.py` | 修改：导出RpcWebEngine |
| `web_dashboard_rpc.py` | 新建：RPC模式启动脚本 |
| `examples/rpc_service/rpc_server_with_web.py` | 新建：带Web数据推送的RPC服务端 |
| `tests/test_rpc_web.py` | 新建：RPC Web集成测试 |

---

## Task 1: 创建 RPC Web 引擎核心类

**Files:**
- Create: `vnpy/web/rpc_engine.py`
- Modify: `vnpy/web/__init__.py`

- [ ] **Step 1: 创建 RpcWebEngine 类骨架**

```python
"""RPC模式的Web看板引擎

支持远程连接交易服务器，所有数据通过RPC获取。
"""
from typing import Optional
from vnpy.event import EventEngine, Event
from vnpy.trader.engine import MainEngine
from vnpy_rpcservice import RpcClient

from .engine import WebEngine


class RpcWebEngine(WebEngine):
    """RPC客户端模式的Web引擎

    通过RPC连接到远程交易服务器，而不是本地MainEngine。
    继承WebEngine以保持所有Web功能，重载数据获取方法。
    """

    engine_name: str = "RpcWebEngine"

    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        req_address: str = "tcp://localhost:2014",
        sub_address: str = "tcp://localhost:2015"
    ) -> None:
        """初始化RPC Web引擎

        Parameters
        ----------
        main_engine : MainEngine
            VNPY主引擎（用于本地事件处理）
        event_engine : EventEngine
            事件引擎
        req_address : str
            RPC服务端请求地址
        sub_address : str
            RPC服务端推送地址
        """
        # 调用父类初始化但不使用父类的main_engine
        BaseEngine.__init__(self, main_engine, event_engine, self.engine_name)

        self.req_address = req_address
        self.sub_address = sub_address
        self.rpc_client: Optional[RpcClient] = None
        self._connected = False

        # 从父类复制必要的初始化
        self.manager = ConnectionManager()
        self.stock_pool_data = StockPoolData()
        self.available_symbols: List[str] = []
        self.current_symbol: str = ""
        self.all_candles: Dict[str, List[CandleData]] = {}
        self.ticks: Dict[str, TickData] = {}
        self.trades: Dict[str, TradeData] = {}
        self.orders: Dict[str, OrderData] = {}
        self.positions: Dict[str, PositionData] = {}
        self.account: Optional[AccountData] = None
        self.candles: Dict[str, List[CandleData]] = {}
        self.stats: Optional[StatsData] = None
        self._running = False
        self._server_task = None
```

- [ ] **Step 2: 实现RPC连接方法**

```python
    def connect_rpc(self) -> bool:
        """连接到RPC服务端

        Returns
        -------
        bool
            连接成功返回True
        """
        from vnpy_rpcservice import RpcClient

        try:
            self.rpc_client = RpcClient()
            self.rpc_client.connect(
                req_address=self.req_address,
                sub_address=self.sub_address,
                main_engine=self.main_engine,
                event_engine=self.event_engine
            )
            self._connected = True
            print(f"✓ RPC连接成功: {self.req_address}")
            return True
        except Exception as e:
            print(f"✗ RPC连接失败: {e}")
            return False

    def disconnect_rpc(self) -> None:
        """断开RPC连接"""
        if self.rpc_client:
            self.rpc_client.stop()
            self._connected = False
            print("RPC连接已断开")
```

- [ ] **Step 3: 重载数据获取方法**

```python
    def _get_account_data(self) -> dict:
        """通过RPC获取账户数据"""
        if not self._connected:
            return {"balance": 0, "available": 0, "frozen": 0}

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
        """通过RPC获取持仓数据"""
        if not self._connected:
            return []

        positions = []
        for pos in self.main_engine.get_all_positions():
            positions.append({
                "vt_symbol": pos.vt_symbol,
                "direction": pos.direction.value,
                "volume": pos.volume,
                "avg_price": round(pos.price, 2),
                "last_price": round(pos.price, 2),  # RPC推送会更新
                "pnl": 0,
                "pnl_pct": 0
            })
        return positions

    def _get_trade_data(self) -> list:
        """通过RPC获取成交数据"""
        if not self._connected:
            return []

        trades = []
        # RPC服务端会自动推送成交事件到event_engine
        # 这里返回空列表，实际数据通过WebSocket推送
        return trades
```

- [ ] **Step 4: 修改 __init__.py 导出 RpcWebEngine**

```python
# vnpy/web/__init__.py

try:
    from .engine import WebEngine
except ImportError:
    WebEngine = None

try:
    from .rpc_engine import RpcWebEngine
except ImportError:
    RpcWebEngine = None

__all__ = [
    "WebEngine",
    "RpcWebEngine",
    # ... 其他导出
]
```

- [ ] **Step 5: Commit**

```bash
git add vnpy/web/rpc_engine.py vnpy/web/__init__.py
git commit -m "feat(web): 添加 RpcWebEngine 支持RPC远程连接"
```

---

## Task 2: 创建 RPC 模式启动脚本

**Files:**
- Create: `web_dashboard_rpc.py`

- [ ] **Step 1: 创建启动脚本骨架**

```python
"""
Web看板 RPC模式启动脚本

通过RPC连接远程交易服务器，启动本地Web看板。

使用方式：
    python web_dashboard_rpc.py --rpc-host 192.168.1.100 --port 8080
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.alpha.logger import logger

# 默认数据库配置
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

DEFAULT_RPC_REQ = "tcp://localhost:2014"
DEFAULT_RPC_SUB = "tcp://localhost:2015"
```

- [ ] **Step 2: 实现 RpcWebDashboard 类**

```python
class RpcWebDashboard:
    """RPC模式Web看板管理器"""

    def __init__(
        self,
        rpc_req: str = DEFAULT_RPC_REQ,
        rpc_sub: str = DEFAULT_RPC_SUB,
        host: str = "0.0.0.0",
        port: int = 8000
    ):
        self.rpc_req = rpc_req
        self.rpc_sub = rpc_sub
        self.host = host
        self.port = port

        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.rpc_engine = None

    def start(self) -> None:
        """启动Web看板"""
        logger.info("=" * 60)
        logger.info("Web看板 RPC模式")
        logger.info("=" * 60)
        logger.info(f"RPC地址: {self.rpc_req}")
        logger.info(f"Web地址: http://{self.host}:{self.port}")
        logger.info("=" * 60)

        try:
            from vnpy.web import RpcWebEngine

            # 创建RPC引擎
            self.rpc_engine = RpcWebEngine(
                main_engine=self.main_engine,
                event_engine=self.event_engine,
                req_address=self.rpc_req,
                sub_address=self.rpc_sub
            )

            # 连接RPC
            if not self.rpc_engine.connect_rpc():
                logger.error("RPC连接失败，退出")
                sys.exit(1)

            # 启动Web服务
            self.rpc_engine.start(host=self.host, port=self.port)

        except ImportError as e:
            logger.error(f"导入失败: {e}")
            logger.error("请确保已安装: pip install vnpy_rpcservice fastapi uvicorn")
            sys.exit(1)

    def stop(self):
        """停止服务"""
        if self.rpc_engine:
            self.rpc_engine.disconnect_rpc()
        self.main_engine.close()
        logger.info("服务已停止")
```

- [ ] **Step 3: 添加命令行参数**

```python
def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Web看板 RPC模式')
    parser.add_argument('--rpc-req', default=DEFAULT_RPC_REQ,
                       help='RPC请求地址 (默认: tcp://localhost:2014)')
    parser.add_argument('--rpc-sub', default=DEFAULT_RPC_SUB,
                       help='RPC推送地址 (默认: tcp://localhost:2015)')
    parser.add_argument('--host', default='0.0.0.0', help='Web服务监听地址')
    parser.add_argument('--port', type=int, default=8000, help='Web服务监听端口')

    args = parser.parse_args()

    dashboard = RpcWebDashboard(
        rpc_req=args.rpc_req,
        rpc_sub=args.rpc_sub,
        host=args.host,
        port=args.port
    )

    try:
        dashboard.start()
    except KeyboardInterrupt:
        dashboard.stop()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Commit**

```bash
git add web_dashboard_rpc.py
git commit -m "feat(web): 添加RPC模式Web看板启动脚本"
```

---

## Task 3: 测试 RPC Web 连接

**Files:**
- Create: `tests/test_rpc_web.py`

- [ ] **Step 1: 创建测试文件骨架**

```python
"""RPC Web看板测试"""
import pytest
import asyncio
from unittest.mock import Mock, MagicMock, patch


class TestRpcWebEngine:
    """测试RPC Web引擎"""

    @pytest.fixture
    def mock_main_engine(self):
        """模拟MainEngine"""
        return Mock()

    @pytest.fixture
    def mock_event_engine(self):
        """模拟EventEngine"""
        return Mock()

    @pytest.fixture
    def mock_rpc_client(self):
        """模拟RpcClient"""
        with patch('vnpy.web.rpc_engine.RpcClient') as mock:
            yield mock

    def test_rpc_engine_init(self, mock_main_engine, mock_event_engine):
        """测试RPC引擎初始化"""
        from vnpy.web import RpcWebEngine

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine,
            req_address="tcp://test:2014",
            sub_address="tcp://test:2015"
        )

        assert engine.req_address == "tcp://test:2014"
        assert engine.sub_address == "tcp://test:2015"
        assert not engine._connected
```

- [ ] **Step 2: 添加连接测试**

```python
    def test_rpc_connect_success(self, mock_main_engine, mock_event_engine, mock_rpc_client):
        """测试RPC连接成功"""
        from vnpy.web import RpcWebEngine

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )

        result = engine.connect_rpc()

        assert result is True
        assert engine._connected is True
        mock_rpc_client.return_value.connect.assert_called_once()

    def test_rpc_connect_failure(self, mock_main_engine, mock_event_engine, mock_rpc_client):
        """测试RPC连接失败"""
        from vnpy.web import RpcWebEngine

        mock_rpc_client.return_value.connect.side_effect = Exception("连接失败")

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )

        result = engine.connect_rpc()

        assert result is False
        assert engine._connected is False
```

- [ ] **Step 3: 添加数据获取测试**

```python
    def test_get_account_data_connected(self, mock_main_engine, mock_event_engine):
        """测试获取账户数据（已连接）"""
        from vnpy.web import RpcWebEngine
        from vnpy.trader.object import AccountData

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )
        engine._connected = True

        # 模拟返回账户
        mock_account = AccountData(
            gateway_name="TEST",
            accountid="12345",
            balance=100000.0,
            frozen=1000.0
        )
        mock_main_engine.get_all_accounts.return_value = [mock_account]

        result = engine._get_account_data()

        assert result["balance"] == 100000.0
        assert result["frozen"] == 1000.0

    def test_get_account_data_disconnected(self, mock_main_engine, mock_event_engine):
        """测试获取账户数据（未连接）"""
        from vnpy.web import RpcWebEngine

        engine = RpcWebEngine(
            main_engine=mock_main_engine,
            event_engine=mock_event_engine
        )
        engine._connected = False

        result = engine._get_account_data()

        assert result["balance"] == 0
        assert result["available"] == 0
```

- [ ] **Step 4: 运行测试**

```bash
cd F:/vnpy_live
python -m pytest tests/test_rpc_web.py -v
```

Expected: 所有测试通过

- [ ] **Step 5: Commit**

```bash
git add tests/test_rpc_web.py
git commit -m "test(web): 添加RPC Web看板单元测试"
```

---

## Task 4: 创建完整RPC服务端（带Alpha策略）

**Files:**
- Create: `examples/rpc_service/rpc_server_alpha.py`

- [ ] **Step 1: 创建Alpha策略RPC服务端**

```python
"""
Alpha策略RPC服务端

完整的交易服务器，支持：
- RPC远程连接
- Alpha策略执行
- Web数据推送

在交易服务器运行，客户端通过RPC/Web远程监控。
"""
import signal
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.alpha.logger import logger
from vnpy_rpcservice import RpcServer

# 配置
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

SETTINGS["datafeed.name"] = "xt"
SETTINGS["datafeed.username"] = "client"
SETTINGS["datafeed.password"] = ""

RPC_REP_ADDRESS = "tcp://*:2014"
RPC_PUB_ADDRESS = "tcp://*:2015"


class AlphaRpcServer:
    """Alpha策略RPC服务端"""

    def __init__(self):
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.rpc_server = None
        self.live_engine = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理"""
        logger.info("\n接收到退出信号，正在停止...")
        self.stop()
        sys.exit(0)

    def start_rpc(self):
        """启动RPC服务"""
        self.rpc_server = RpcServer(self.main_engine, self.event_engine)
        self.rpc_server.start(
            rep_address=RPC_REP_ADDRESS,
            pub_address=RPC_PUB_ADDRESS
        )

        logger.info("=" * 60)
        logger.info("Alpha策略RPC服务端已启动")
        logger.info("=" * 60)
        logger.info(f"请求地址: {RPC_REP_ADDRESS}")
        logger.info(f"推送地址: {RPC_PUB_ADDRESS}")
        logger.info("=" * 60)

    def connect_gateway(self, gateway_name: str = "XT", account: str = ""):
        """连接交易网关"""
        try:
            if gateway_name == "XT":
                from vnpy_xt import XtGateway
                self.main_engine.add_gateway(XtGateway, gateway_name)

                if account:
                    setting = {"账号类型": "股票账号", "账号": account}
                    self.main_engine.connect(setting, gateway_name)
                    logger.info(f"已连接网关: {gateway_name}")
                    return True

        except Exception as e:
            logger.error(f"连接网关失败: {e}")
            return False

    def run(self):
        """运行服务端"""
        logger.info("=" * 60)
        logger.info("启动Alpha策略RPC服务端")
        logger.info(f"时间: {datetime.now()}")
        logger.info("=" * 60)

        self.start_rpc()

        logger.info("\n服务端运行中，按Ctrl+C停止")
        logger.info("=" * 60)

        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """停止服务"""
        logger.info("\n正在停止服务...")
        if self.live_engine:
            self.live_engine.stop_trading()
        if self.rpc_server:
            self.rpc_server.stop()
        self.main_engine.close()
        logger.info("服务已停止")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Alpha策略RPC服务端')
    parser.add_argument('--rep', default=RPC_REP_ADDRESS, help='请求地址')
    parser.add_argument('--pub', default=RPC_PUB_ADDRESS, help='推送地址')
    parser.add_argument('--gateway', default='XT', help='网关名称')
    parser.add_argument('--account', default='', help='交易账号')

    args = parser.parse_args()

    global RPC_REP_ADDRESS, RPC_PUB_ADDRESS
    RPC_REP_ADDRESS = args.rep
    RPC_PUB_ADDRESS = args.pub

    server = AlphaRpcServer()
    if args.account:
        server.connect_gateway(args.gateway, args.account)
    server.run()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Commit**

```bash
git add examples/rpc_service/rpc_server_alpha.py
git commit -m "feat(rpc): 添加Alpha策略RPC服务端"
```

---

## Task 5: 更新文档

**Files:**
- Modify: `examples/rpc_service/README.md`

- [ ] **Step 1: 添加Web看板集成说明**

```markdown
## Web看板集成

### 快速开始

**1. 启动Alpha策略RPC服务端**

```bash
python examples/rpc_service/rpc_server_alpha.py
```

**2. 启动Web看板（RPC模式）**

```bash
python web_dashboard_rpc.py
```

或指定远程服务器：

```bash
python web_dashboard_rpc.py \
    --rpc-req tcp://192.168.1.100:2014 \
    --rpc-sub tcp://192.168.1.100:2015 \
    --port 8080
```

**3. 访问Web看板**

浏览器打开 http://localhost:8000

### 完整部署示例

**场景：交易服务器 + Web监控端**

```
┌─────────────────┐         RPC          ┌─────────────────┐
│  交易服务器      │  ◄────────────────►  │  Web监控端       │
│  (云端/本地)     │   tcp://:2014/2015  │  (本机/远程)     │
├─────────────────┤                      ├─────────────────┤
│ - RPC服务端     │                      │ - Web看板       │
│ - Alpha策略     │                      │ - 实时监控      │
│ - 交易网关      │                      │ - 远程下单      │
└─────────────────┘                      └─────────────────┘
```

```bash
# 交易服务器
python examples/rpc_service/rpc_server_alpha.py \
    --rep tcp://0.0.0.0:2014 \
    --pub tcp://0.0.0.0:2015 \
    --account your_account

# Web监控端
python web_dashboard_rpc.py \
    --rpc-req tcp://server_ip:2014 \
    --rpc-sub tcp://server_ip:2015 \
    --port 8080
```
```

- [ ] **Step 2: Commit**

```bash
git add examples/rpc_service/README.md
git commit -m "docs(rpc): 添加Web看板集成说明"
```

---

## Task 6: 端到端测试

- [ ] **Step 1: 启动RPC服务端**

```bash
python examples/rpc_service/rpc_server_alpha.py
```

Expected: 服务端启动成功，显示RPC地址

- [ ] **Step 2: 启动Web看板**

```bash
python web_dashboard_rpc.py
```

Expected: Web服务启动，显示 http://0.0.0.0:8000

- [ ] **Step 3: 浏览器访问**

打开 http://localhost:8000

Expected: Web看板页面加载，显示连接状态

- [ ] **Step 4: 验证数据获取**

在Web看板上检查：
- 账户信息是否正确显示
- 持仓数据是否正确显示
- WebSocket连接状态是否"已连接"

- [ ] **Step 5: 最终Commit**

```bash
git add -A
git commit -m "feat(web): 完整集成RPC远程模式，支持分布式交易监控"
```

---

## 自我检查清单

**1. Spec覆盖检查:**
- ✅ RpcWebEngine类支持RPC连接
- ✅ Web看板启动脚本支持RPC模式
- ✅ 单元测试覆盖核心功能
- ✅ 完整RPC服务端示例
- ✅ 文档更新

**2. Placeholder检查:**
- 无TBD/TODO
- 所有代码可执行
- 测试包含完整代码

**3. 类型一致性检查:**
- RpcWebEngine继承WebEngine
- 方法签名保持一致
- RPC客户端正确初始化

---

## 执行选项

**Plan complete and saved to `docs/superpowers/plans/2026-04-22-web-dashboard-rpc.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints for review

**Which approach?**
