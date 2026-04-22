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
    """首页 - 返回静态 HTML 文件"""
    index_file = STATIC_DIR / "index.html"
    if index_file.exists():
        with open(index_file, 'r', encoding='utf-8') as f:
            return f.read()
    # 如果文件不存在，返回简单的内联 HTML
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>VNPY Web Dashboard</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            .header { background: #1890ff; color: white; padding: 20px; }
        </style>
    </head>
    <body>
        <div class="header">
            <h1>VNPY Web Dashboard</h1>
            <p>index.html not found</p>
        </div>
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
