"""FastAPI 应用"""
from fastapi import FastAPI, WebSocket
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager

from .data_manager import DataManager

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

app.mount("/static", StaticFiles(directory="static"), name="static")


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
            pre { background: #f5f5f5; padding: 10px; }
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
            const ws = new WebSocket(`ws://${window.location.host}/ws`);
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                if (data.type === 'account') {
                    document.getElementById('account').textContent = JSON.stringify(data.data, null, 2);
                } else if (data.type === 'position') {
                    document.getElementById('positions').textContent = JSON.stringify(data.data, null, 2);
                } else if (data.type === 'trade') {
                    document.getElementById('trades').textContent = JSON.stringify(data.data, null, 2);
                }
            };
        </script>
    </body>
    </html>
    """


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    data_manager.register_websocket(websocket)
    try:
        if data_manager.account:
            await websocket.send_json({"type": "account", "data": data_manager.account})
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except Exception:
        pass
    finally:
        data_manager.unregister_websocket(websocket)


@app.get("/api/account")
async def get_account():
    return data_manager.account or {}


@app.get("/api/positions")
async def get_positions():
    return list(data_manager.positions.values())


@app.get("/api/trades")
async def get_trades():
    return data_manager.trades
