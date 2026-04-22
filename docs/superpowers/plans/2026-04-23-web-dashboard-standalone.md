# Web 看板独立化实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Web 看板从 `vnpy/web/` 迁移到独立目录 `web_dashboard/`，作为通用监控看板，通过监听 RPC PUB 地址接收数据，不绑定任何引擎

**Architecture:** WebDashboard 是独立的 Web 服务，通过 ZeroMQ SUB 订阅 RpcServer 的事件推送，支持任意 VNPY RPC 服务端

**Tech Stack:** FastAPI, WebSocket, ZeroMQ, Vue3

---

## 架构图

### 独立架构
```
┌─────────────────────────────────────────────────────────┐
│                  web_dashboard/                         │
│  ┌──────────────────────────────────────────────────┐  │
│  │              WebDashboard (独立服务)               │  │
│  │  ┌──────────┐  ┌──────────┐  ┌────────────────┐  │  │
│  │  │  ZMQ SUB │  │  FastAPI │  │  WebSocket     │  │  │
│  │  │  (接收)  │  │  (HTTP)  │  │  (推送前端)    │  │  │
│  │  └────┬─────┘  └────┬─────┘  └────────────────┘  │  │
│  │       │             │                              │  │
│  │       └─────────────┴── 数据管理/前端展示          │  │
│  └─────────────────────┬──────────────────────────────┘  │
└────────────────────────┼────────────────────────────────┘
                         │
                         │ ZeroMQ PUB/SUB
                         │
┌────────────────────────┼────────────────────────────────┐
│  VNPY Trading Server   │                                │
│  ┌─────────────────────┴──────────────────────────────┐ │
│  │              RpcServer (PUB地址)                    │ │
│  │  推送: 账户、持仓、成交、行情、订单                  │ │
│  └─────────────────────────────────────────────────────┘ │
│                    MainEngine                             │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐   │
│  │TradeEngine │  │  Gateway   │  │   其他引擎        │   │
│  └────────────┘  └────────────┘  └──────────────────┘   │
└───────────────────────────────────────────────────────────┘
```

### 数据流
```
TradeEngine/Gateway
    ↓ 事件
MainEngine
    ↓ 转发
RpcServer (PUB)
    ↓ ZeroMQ 推送
WebDashboard (SUB)
    ↓ WebSocket
浏览器/前端
```

---

## 文件结构

| 文件/目录 | 操作 | 说明 |
|-----------|------|------|
| `web_dashboard/` | 新建 | 独立项目根目录 |
| `web_dashboard/dashboard/` | 新建 | Python 包 |
| `web_dashboard/dashboard/__init__.py` | 新建 | 包初始化 |
| `web_dashboard/dashboard/data_manager.py` | 新建 | 数据管理器（接收 ZMQ 事件） |
| `web_dashboard/dashboard/app.py` | 新建 | FastAPI 应用 |
| `web_dashboard/dashboard/api.py` | 新建 | REST API 路由 |
| `web_dashboard/dashboard/websocket.py` | 新建 | WebSocket 路由 |
| `web_dashboard/static/` | 新建 | 前端静态文件 |
| `web_dashboard/templates/` | 新建 | HTML 模板 |
| `web_dashboard/main.py` | 新建 | 启动入口 |
| `web_dashboard/requirements.txt` | 新建 | 依赖 |
| `vnpy/web/` | 删除 | 移除旧的 Web 模块 |

---

## Task 1: 创建 web_dashboard 目录结构

**Files:**
- Create: `web_dashboard/dashboard/__init__.py`
- Create: `web_dashboard/static/.gitkeep`
- Create: `web_dashboard/templates/.gitkeep`

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p web_dashboard/dashboard
mkdir -p web_dashboard/static
mkdir -p web_dashboard/templates
touch web_dashboard/dashboard/__init__.py
touch web_dashboard/static/.gitkeep
touch web_dashboard/templates/.gitkeep
```

- [ ] **Step 2: Commit**

```bash
git add web_dashboard/
git commit -m "feat(dashboard): 创建独立 Web 看板目录结构"
```

---

## Task 2: 创建数据管理器（ZMQ 事件接收）

**Files:**
- Create: `web_dashboard/dashboard/data_manager.py`

- [ ] **Step 1: 创建数据管理器**

```python
"""数据管理器 - 接收 RPC 推送事件并管理数据"""
import json
import asyncio
from datetime import datetime
from typing import Dict, List, Optional, Any
import zmq
import zmq.asyncio


class DataManager:
    """数据管理器
    
    通过 ZeroMQ SUB 订阅 RpcServer 的事件推送，
    维护账户、持仓、成交、订单、行情等数据。
    """
    
    def __init__(self, sub_address: str = "tcp://localhost:2015"):
        self.sub_address = sub_address
        self.context: Optional[zmq.asyncio.Context] = None
        self.socket: Optional[zmq.asyncio.Socket] = None
        self._running = False
        
        # 数据存储
        self.account: Optional[Dict] = None
        self.positions: Dict[str, Dict] = {}
        self.trades: List[Dict] = []
        self.orders: Dict[str, Dict] = {}
        self.ticks: Dict[str, Dict] = {}
        self.candles: Dict[str, List[Dict]] = {}
        
        # WebSocket 连接列表（用于推送更新）
        self.websockets: List[Any] = []
    
    async def start(self):
        """启动 ZMQ 订阅"""
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(self.sub_address)
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")  # 订阅所有主题
        self._running = True
        
        print(f"[DataManager] 已连接到 {self.sub_address}")
        
        # 启动接收循环
        asyncio.create_task(self._receive_loop())
    
    async def stop(self):
        """停止 ZMQ 订阅"""
        self._running = False
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()
        print("[DataManager] 已停止")
    
    async def _receive_loop(self):
        """接收事件循环"""
        while self._running:
            try:
                # 非阻塞接收
                if self.socket:
                    event_data = await self.socket.recv_json()
                    await self._process_event(event_data)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[DataManager] 接收错误: {e}")
                await asyncio.sleep(1)
    
    async def _process_event(self, event_data: Dict):
        """处理接收到的"""
        event_type = event_data.get("type")
        data = event_data.get("data")
        
        if not event_type or not data:
            return
        
        # 根据事件类型更新数据
        if event_type == "EVENT_ACCOUNT":
            self.account = self._format_account(data)
            await self._broadcast({"type": "account", "data": self.account})
            
        elif event_type == "EVENT_POSITION":
            position = self._format_position(data)
            self.positions[position["vt_symbol"]] = position
            await self._broadcast({"type": "position", "data": position})
            
        elif event_type == "EVENT_TRADE":
            trade = self._format_trade(data)
            self.trades.insert(0, trade)  # 最新在前
            if len(self.trades) > 100:  # 限制数量
                self.trades = self.trades[:100]
            await self._broadcast({"type": "trade", "data": trade})
            
        elif event_type == "EVENT_ORDER":
            order = self._format_order(data)
            self.orders[order["vt_orderid"]] = order
            await self._broadcast({"type": "order", "data": order})
            
        elif event_type == "EVENT_TICK":
            tick = self._format_tick(data)
            self.ticks[tick["vt_symbol"]] = tick
            await self._broadcast({"type": "tick", "data": tick})
    
    def _format_account(self, data: Dict) -> Dict:
        """格式化账户数据"""
        return {
            "balance": data.get("balance", 0),
            "available": data.get("available", 0),
            "frozen": data.get("frozen", 0),
            "gateway_name": data.get("gateway_name", ""),
        }
    
    def _format_position(self, data: Dict) -> Dict:
        """格式化持仓数据"""
        return {
            "vt_symbol": data.get("vt_symbol", ""),
            "direction": data.get("direction", ""),
            "volume": data.get("volume", 0),
            "price": data.get("price", 0),
            "pnl": data.get("pnl", 0),
            "gateway_name": data.get("gateway_name", ""),
        }
    
    def _format_trade(self, data: Dict) -> Dict:
        """格式化成交数据"""
        return {
            "vt_symbol": data.get("vt_symbol", ""),
            "direction": data.get("direction", ""),
            "price": data.get("price", 0),
            "volume": data.get("volume", 0),
            "time": data.get("time", ""),
            "gateway_name": data.get("gateway_name", ""),
        }
    
    def _format_order(self, data: Dict) -> Dict:
        """格式化订单数据"""
        return {
            "vt_orderid": data.get("vt_orderid", ""),
            "vt_symbol": data.get("vt_symbol", ""),
            "direction": data.get("direction", ""),
            "price": data.get("price", 0),
            "volume": data.get("volume", 0),
            "traded": data.get("traded", 0),
            "status": data.get("status", ""),
        }
    
    def _format_tick(self, data: Dict) -> Dict:
        """格式化行情数据"""
        return {
            "vt_symbol": data.get("vt_symbol", ""),
            "last_price": data.get("last_price", 0),
            "volume": data.get("volume", 0),
            "open_price": data.get("open_price", 0),
            "high_price": data.get("high_price", 0),
            "low_price": data.get("low_price", 0),
            "datetime": data.get("datetime", ""),
        }
    
    async def _broadcast(self, message: Dict):
        """广播消息到所有 WebSocket 连接"""
        for ws in self.websockets[:]:
            try:
                await ws.send_json(message)
            except Exception:
                # 移除失效连接
                self.websockets.remove(ws)
    
    def register_websocket(self, ws):
        """注册 WebSocket 连接"""
        self.websockets.append(ws)
    
    def unregister_websocket(self, ws):
        """注销 WebSocket 连接"""
        if ws in self.websockets:
            self.websockets.remove(ws)
```

- [ ] **Step 2: Commit**

```bash
git add web_dashboard/dashboard/data_manager.py
git commit -m "feat(dashboard): 创建数据管理器，接收 ZMQ 事件"
```

---

## Task 3: 创建 FastAPI 应用

**Files:**
- Create: `web_dashboard/dashboard/app.py`

- [ ] **Step 1: 创建 FastAPI 应用**

```python
"""FastAPI 应用"""
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from .data_manager import DataManager

# 全局数据管理器实例
data_manager = DataManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时连接 ZMQ
    await data_manager.start()
    print("[App] 数据管理器已启动")
    yield
    # 关闭时断开 ZMQ
    await data_manager.stop()
    print("[App] 数据管理器已停止")


app = FastAPI(
    title="VNPY Web Dashboard",
    description="通用交易监控看板",
    version="1.0.0",
    lifespan=lifespan
)

# 静态文件
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
    """首页"""
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>VNPY Web Dashboard</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .header { background: #1890ff; color: white; padding: 20px; }
            .data-section { margin: 20px 0; }
            .data-title { font-size: 18px; font-weight: bold; margin-bottom: 10px; }
            pre { background: #f5f5f5; padding: 10px; overflow: auto; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>VNPY Web Dashboard</h1>
            <p>通用交易监控看板</p>
        </div>
        
        <div class="data-section">
            <div class="data-title">账户信息</div>
            <pre id="account">等待数据...</pre>
        </div>
        
        <div class="data-section">
            <div class="data-title">持仓信息</div>
            <pre id="positions">等待数据...</pre>
        </div>
        
        <div class="data-section">
            <div class="data-title">最新成交</div>
            <pre id="trades">等待数据...</pre>
        </div>
        
        <script>
            // WebSocket 连接
            const ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onopen = function() {
                console.log('WebSocket 已连接');
            };
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                console.log('收到数据:', data);
                
                // 更新对应区域
                if (data.type === 'account') {
                    document.getElementById('account').textContent = JSON.stringify(data.data, null, 2);
                } else if (data.type === 'position') {
                    const positions = JSON.parse(document.getElementById('positions').textContent) || {};
                    positions[data.data.vt_symbol] = data.data;
                    document.getElementById('positions').textContent = JSON.stringify(positions, null, 2);
                } else if (data.type === 'trade') {
                    const trades = JSON.parse(document.getElementById('trades').textContent) || [];
                    trades.unshift(data.data);
                    if (trades.length > 20) trades.pop();
                    document.getElementById('trades').textContent = JSON.stringify(trades, null, 2);
                }
            };
            
            ws.onclose = function() {
                console.log('WebSocket 已断开');
            };
        </script>
    </body>
    </html>
    """


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket 端点"""
    await websocket.accept()
    print(f"[WebSocket] 客户端已连接")
    
    # 注册到数据管理器
    data_manager.register_websocket(websocket)
    
    try:
        # 发送当前数据
        if data_manager.account:
            await websocket.send_json({"type": "account", "data": data_manager.account})
        
        # 保持连接
        while True:
            # 接收客户端心跳/消息
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception as e:
        print(f"[WebSocket] 连接错误: {e}")
    finally:
        data_manager.unregister_websocket(websocket)
        print("[WebSocket] 客户端已断开")


@app.get("/api/account")
async def get_account():
    """获取账户信息"""
    return data_manager.account or {}


@app.get("/api/positions")
async def get_positions():
    """获取持仓信息"""
    return list(data_manager.positions.values())


@app.get("/api/trades")
async def get_trades():
    """获取成交记录"""
    return data_manager.trades


@app.get("/api/orders")
async def get_orders():
    """获取订单记录"""
    return list(data_manager.orders.values())
```

- [ ] **Step 2: Commit**

```bash
git add web_dashboard/dashboard/app.py
git commit -m "feat(dashboard): 创建 FastAPI 应用和 WebSocket"
```

---

## Task 4: 创建启动入口

**Files:**
- Create: `web_dashboard/main.py`
- Create: `web_dashboard/requirements.txt`

- [ ] **Step 1: 创建启动脚本**

```python
"""Web Dashboard 启动入口"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description='VNPY Web Dashboard')
    parser.add_argument('--sub', default='tcp://localhost:2015',
                       help='RPC PUB 地址 (默认: tcp://localhost:2015)')
    parser.add_argument('--host', default='0.0.0.0',
                       help='Web 服务地址 (默认: 0.0.0.0)')
    parser.add_argument('--port', type=int, default=8080,
                       help='Web 服务端口 (默认: 8080)')
    
    args = parser.parse_args()
    
    # 设置全局配置
    import dashboard.app as app_module
    app_module.data_manager.sub_address = args.sub
    
    print("=" * 60)
    print("VNPY Web Dashboard")
    print("=" * 60)
    print(f"RPC PUB 地址: {args.sub}")
    print(f"Web 地址: http://{args.host}:{args.port}")
    print("=" * 60)
    
    # 启动服务
    uvicorn.run(
        "dashboard.app:app",
        host=args.host,
        port=args.port,
        reload=False
    )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 创建 requirements.txt**

```
fastapi>=0.100.0
uvicorn[standard]>=0.23.0
pyzmq>=25.0.0
websockets>=11.0
```

- [ ] **Step 3: Commit**

```bash
git add web_dashboard/main.py web_dashboard/requirements.txt
git commit -m "feat(dashboard): 创建启动入口和依赖配置"
```

---

## Task 5: 删除旧的 vnpy/web 模块

**Files:**
- Delete: `vnpy/web/` 目录

- [ ] **Step 1: 删除旧的 Web 模块**

```bash
# 备份（如果需要）
# mv vnpy/web vnpy/web_backup

# 删除
git rm -r vnpy/web/
git commit -m "refactor: 删除旧的 vnpy/web 模块（已迁移到独立 web_dashboard）"
```

---

## Task 6: 更新主交易脚本

**Files:**
- Modify: `xgb_extrema_live_trading.py`

- [ ] **Step 1: 移除 Web 相关代码**

删除 `enable_web` 相关代码，Web 看板现在独立运行。

```python
# 删除以下代码：
# - from vnpy.web import WebEngine
# - self.web_engine = ...
# - web_thread = ...

# 保留 TradeEngine 和 RpcEngine（用于服务端推送）
```

- [ ] **Step 2: Commit**

```bash
git add xgb_extrema_live_trading.py
git commit -m "refactor(trading): 移除 Web 看板代码（已独立）"
```

---

## Task 7: 最终验证

- [ ] **Step 1: 安装依赖**

```bash
cd web_dashboard
pip install -r requirements.txt
```

- [ ] **Step 2: 测试启动**

```bash
python main.py --sub tcp://localhost:2015 --port 8080
```

Expected: 服务启动，监听 8080 端口

- [ ] **Step 3: Final Commit**

```bash
git add -A
git commit -m "feat: Web 看板独立化完成"
```

---

## 使用方式

### 启动 VNPY 交易服务（带 RPC）

```bash
python xgb_extrema_live_trading.py --mode paper --enable-rpc
```

### 启动独立 Web 看板

```bash
cd web_dashboard
python main.py --sub tcp://localhost:2015 --port 8080
```

### 浏览器访问

http://localhost:8080

---

## 架构优势

| 特性 | 旧架构 | 新架构 |
|------|--------|--------|
| 耦合度 | 高（Web 绑定到 VNPY 进程） | 低（完全独立） |
| 部署 | 必须在同一机器 | 可以跨机器部署 |
| 监控 | 单实例 | 可以多客户端同时监控 |
| 依赖 | 需要完整 VNPY | 只需 zmq + fastapi |

---

## 自我检查清单

**1. Spec 覆盖:**
- ✅ 创建独立 web_dashboard 目录
- ✅ DataManager 接收 ZMQ 事件
- ✅ FastAPI + WebSocket 服务
- ✅ 删除旧 vnpy/web 模块
- ✅ 更新主交易脚本

**2. Placeholder 检查:**
- 无 TBD/TODO
- 所有代码完整

**3. 架构清晰:**
- Web 看板完全独立
- 通用设计（适配任意 RpcServer）

---

## 执行选项

**Plan complete and saved to `docs/superpowers/plans/YYYY-MM-DD-web-dashboard-standalone.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - Fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
