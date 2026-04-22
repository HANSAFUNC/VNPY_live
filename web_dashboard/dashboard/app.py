"""FastAPI 应用"""
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from .data_manager import DataManager

# 获取静态文件目录（相对于本文件位置）
STATIC_DIR = Path(__file__).parent.parent / "static"
TEMPLATE_DIR = Path(__file__).parent.parent / "templates"

data_manager = DataManager()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await data_manager.start()
    print("[App] 数据管理器已启动")
    yield
    await data_manager.stop()
    print("[App] 数据管理器已停止")


app = FastAPI(
    title="VNPY Web Dashboard",
    description="通用交易监控看板",
    version="1.0.0",
    lifespan=lifespan
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", response_class=HTMLResponse)
async def index():
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
            pre { background: #f5f5f5; padding: 10px; overflow: auto; max-height: 300px; }
            .status { color: #666; font-size: 12px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>VNPY Web Dashboard</h1>
            <p>通用交易监控看板</p>
        </div>
        <div class="status" id="status">正在连接 WebSocket...</div>
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
            // 数据存储
            let positions = {};
            let trades = [];

            console.log('正在连接 WebSocket...');
            const ws = new WebSocket(`ws://${window.location.host}/ws`);

            ws.onopen = function() {
                console.log('WebSocket 已连接');
                document.getElementById('status').textContent = 'WebSocket 已连接 - 等待数据...';
                document.getElementById('status').style.color = 'green';
            };

            ws.onmessage = function(event) {
                console.log('原始消息:', event.data);
                try {
                    const data = JSON.parse(event.data);
                    console.log('收到数据:', data);
                    document.getElementById('status').textContent = 'WebSocket 已连接 - 最后更新: ' + new Date().toLocaleTimeString();

                    if (data.type === 'account') {
                        document.getElementById('account').textContent = JSON.stringify(data.data, null, 2);
                    } else if (data.type === 'position') {
                        positions[data.data.vt_symbol] = data.data;
                        document.getElementById('positions').textContent = JSON.stringify(Object.values(positions), null, 2);
                    } else if (data.type === 'trade') {
                        trades.unshift(data.data);
                        if (trades.length > 20) trades = trades.slice(0, 20);
                        document.getElementById('trades').textContent = JSON.stringify(trades, null, 2);
                    } else {
                        console.log('未知数据类型:', data.type);
                    }
                } catch (e) {
                    console.error('解析消息失败:', e, event.data);
                }
            };

            ws.onclose = function(event) {
                console.log('WebSocket 已断开:', event.code, event.reason);
                document.getElementById('status').textContent = 'WebSocket 已断开 (代码: ' + event.code + ')';
                document.getElementById('status').style.color = 'red';
            };

            ws.onerror = function(error) {
                console.error('WebSocket 错误:', error);
                document.getElementById('status').textContent = 'WebSocket 错误';
                document.getElementById('status').style.color = 'red';
            };
        </script>
    </body>
    </html>
    """


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    print(f"[WebSocket] 客户端已连接: {websocket.client}")
    data_manager.register_websocket(websocket)

    # 发送当前数据快照
    try:
        if data_manager.account:
            await websocket.send_json({"type": "account", "data": data_manager.account})
            print("[WebSocket] 发送初始账户数据")
        if data_manager.positions:
            for pos in data_manager.positions.values():
                await websocket.send_json({"type": "position", "data": pos})
            print(f"[WebSocket] 发送初始持仓数据: {len(data_manager.positions)} 条")
    except Exception as e:
        print(f"[WebSocket] 发送初始数据失败: {e}")

    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception as e:
        print(f"[WebSocket] 连接异常: {e}")
    finally:
        data_manager.unregister_websocket(websocket)
        print("[WebSocket] 客户端已断开")


@app.get("/api/account")
async def get_account():
    return data_manager.account or {}


@app.get("/api/positions")
async def get_positions():
    return list(data_manager.positions.values())


@app.get("/api/trades")
async def get_trades():
    return data_manager.trades
