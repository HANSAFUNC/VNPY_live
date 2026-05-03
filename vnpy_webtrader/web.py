from pathlib import Path
import sys
import logging

# 添加项目根目录到路径（支持从任意位置运行）
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

logger = logging.getLogger(__name__)

from enum import Enum
from typing import Any, Literal, Optional
import asyncio
import json
from datetime import datetime, timedelta, timezone
import secrets
from collections import deque

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status, Depends, Query
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from jose import jwt, JWTError
from passlib.context import CryptContext

from vnpy.rpc import RpcClient
from vnpy.trader.object import (
    AccountData,
    ContractData,
    OrderData,
    OrderRequest,
    PositionData,
    SubscribeRequest,
    CancelRequest,
    TickData,
    TradeData
)
from vnpy.trader.constant import (
    Exchange,
    Direction,
    OrderType,
    Offset,
)
from vnpy.trader.utility import load_json, get_file_path
from vnpy_webtrader.response import ApiResponse, success_response, error_response, Errors


# Web服务运行配置
SETTING_FILENAME = "web_trader_setting.json"
SETTING_FILEPATH = get_file_path(SETTING_FILENAME)

setting: dict = load_json(SETTING_FILEPATH)

# 确保配置有默认值
default_setting = {
    "username": "admin",
    "password": "admin",
    "req_address": "tcp://localhost:2014",
    "sub_address": "tcp://localhost:2015"
}
for key, value in default_setting.items():
    if key not in setting:
        setting[key] = value

USERNAME = setting["username"]              # 用户名
PASSWORD = setting["password"]              # 密码
REQ_ADDRESS = setting["req_address"]        # 请求服务地址
SUB_ADDRESS = setting["sub_address"]        # 订阅服务地址


SECRET_KEY = "test"                     # 数据加密密钥
ALGORITHM = "HS256"                     # 加密算法
ACCESS_TOKEN_EXPIRE_MINUTES = 9999999        # 令牌超时（分钟）


# 实例化CryptContext用于处理哈希密码
pwd_context: CryptContext = CryptContext(schemes=["sha256_crypt"], deprecated="auto")

# FastAPI密码鉴权工具
oauth2_scheme: OAuth2PasswordBearer = OAuth2PasswordBearer(tokenUrl="/api/token")

# RPC客户端
rpc_client: RpcClient = None

# 日志存储（内存中，最多1000条）
logs_buffer: deque = deque(maxlen=1000)


def add_log(level: str, source: str, message: str) -> None:
    """添加日志到缓冲区"""
    log_entry = {
        'id': len(logs_buffer),
        'time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'level': level,
        'source': source,
        'message': message
    }
    logs_buffer.append(log_entry)


def to_dict(o: object) -> dict:
    """将对象转换为字典"""
    data: dict = {}
    for k, v in o.__dict__.items():
        if isinstance(v, Enum):
            data[k] = v.value
        elif isinstance(v, datetime):
            data[k] = str(v)
        else:
            data[k] = v
    return data


class Token(BaseModel):
    """令牌数据"""
    access_token: str
    token_type: str


def authenticate_user(current_username: str, username: str, password: str) -> str | Literal[False]:
    """校验用户"""
    hashed_password = pwd_context.hash(PASSWORD)

    if not secrets.compare_digest(current_username, username):
        return False

    if not pwd_context.verify(password, hashed_password):
        return False

    return username


def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """创建令牌"""
    to_encode: dict = data.copy()

    if expires_delta:
        expire: datetime = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=15)

    to_encode.update({"exp": expire})
    encoded_jwt: str = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


async def get_access(token: str = Depends(oauth2_scheme)) -> bool:
    """REST鉴权"""
    credentials_exception: HTTPException = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload: dict = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username_value = payload.get("sub")
        if username_value is None:
            raise credentials_exception
        username: str = username_value
    except JWTError as err:
        raise credentials_exception from err

    if not secrets.compare_digest(USERNAME, username):
        raise credentials_exception

    return True


# 创建FastAPI应用
app: FastAPI = FastAPI()

# 配置CORS中间件 - 允许跨域请求
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境应指定具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 确定静态文件目录（优先级：web_dashboard_v2 > web_dashboard > vnpy_webtrader/static）
web_dashboard_v2_dist = Path(__file__).parent.parent / "web_dashboard_v2" / "dist"
web_dashboard_static = Path(__file__).parent.parent / "web_dashboard" / "static"
vnpy_webtrader_static = Path(__file__).parent / "static"

if web_dashboard_v2_dist.exists():
    static_directory = web_dashboard_v2_dist
    dashboard_version = "v2 (Vue3 + Element Plus)"
elif web_dashboard_static.exists():
    static_directory = web_dashboard_static
    dashboard_version = "v1"
else:
    static_directory = vnpy_webtrader_static
    dashboard_version = "builtin"

print(f"[Web] 使用看板版本: {dashboard_version}, 静态目录: {static_directory}")

# 挂载静态文件目录
app.mount("/static", StaticFiles(directory=static_directory), name="static")


@app.get("/")
def index() -> HTMLResponse:
    """获取主页面"""
    try:
        # 按优先级查找 index.html
        index_paths = [
            Path(__file__).parent.parent / "web_dashboard_v2" / "dist" / "index.html",
            Path(__file__).parent.parent / "web_dashboard" / "static" / "index.html",
            Path(__file__).parent / "static" / "index.html",
        ]

        index_path: Path | None = None
        for path in index_paths:
            if path.exists():
                index_path = path
                break

        if index_path is None:
            return HTMLResponse(f"<h1>404</h1><p>找不到页面，搜索路径: {[str(p) for p in index_paths]}</p>", status_code=404)

        with open(index_path, encoding="utf-8") as f:
            content: str = f.read()

        return HTMLResponse(content)
    except Exception as e:
        return HTMLResponse(f"<h1>错误</h1><p>{e}</p>", status_code=500)


@app.post("/api/token", response_model=Token)
def login(form_data: OAuth2PasswordRequestForm = Depends()) -> dict:  # noqa: B008
    """用户登录"""
    auth_result = authenticate_user(USERNAME, form_data.username, form_data.password)
    if not auth_result:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token_expires: timedelta = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token: str = create_access_token(
        data={"sub": auth_result}, expires_delta=access_token_expires
    )
    return {"access_token": access_token, "token_type": "bearer"}


@app.post("/api/tick/{vt_symbol}")
def subscribe(vt_symbol: str, access: bool = Depends(get_access)) -> None:  # noqa: ARG001
    """订阅行情"""
    contract: ContractData | None = rpc_client.get_contract(vt_symbol)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到合约{vt_symbol}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    req: SubscribeRequest = SubscribeRequest(contract.symbol, contract.exchange)
    rpc_client.subscribe(req, contract.gateway_name)


@app.get("/api/tick")
def get_all_ticks(access: bool = Depends(get_access)) -> ApiResponse[list]:  # noqa: ARG001
    """查询行情信息"""
    try:
        data = [to_dict(tick) for tick in rpc_client.get_all_ticks()]
        return success_response(data)
    except Exception as e:
        logger.error(f"获取Ticks失败: {e}")
        return Errors.internal_error(str(e))


class OrderRequestModel(BaseModel):
    """委托请求模型"""
    symbol: str
    exchange: Exchange
    direction: Direction
    type: OrderType
    volume: float
    price: float = 0
    offset: Offset = Offset.NONE
    reference: str = ""


class SwitchProjectRequest(BaseModel):
    """切换项目请求"""
    project_name: str
    index_code: Optional[str] = None
    data_source: Optional[str] = None


class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    project_name: str
    index_code: str = "csi300"
    data_source: str = "xt"


class SwitchIndexRequest(BaseModel):
    """切换指数请求"""
    index_code: str


@app.post("/api/order")
def send_order(model: OrderRequestModel, access: bool = Depends(get_access)) -> str:  # noqa: ARG001
    """委托下单"""
    req: OrderRequest = OrderRequest(**model.__dict__)

    contract: ContractData | None = rpc_client.get_contract(req.vt_symbol)
    if not contract:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到合约{req.symbol} {req.exchange.value}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    vt_orderid: str = rpc_client.send_order(req, contract.gateway_name)
    return vt_orderid


@app.delete("/api/order/{vt_orderid}")
def cancel_order(vt_orderid: str, access: bool = Depends(get_access)) -> None:  # noqa: ARG001
    """委托撤单"""
    order: OrderData | None = rpc_client.get_order(vt_orderid)
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到委托{vt_orderid}",
            headers={"WWW-Authenticate": "Bearer"},
        )

    req: CancelRequest = order.create_cancel_request()
    rpc_client.cancel_order(req, order.gateway_name)


@app.get("/api/order")
def get_all_orders(access: bool = Depends(get_access)) -> ApiResponse[list]:  # noqa: ARG001
    """查询委托信息"""
    try:
        data = [to_dict(order) for order in rpc_client.get_all_orders()]
        return success_response(data)
    except Exception as e:
        logger.error(f"获取委托失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/trade")
def get_all_trades(access: bool = Depends(get_access)) -> ApiResponse[list]:  # noqa: ARG001
    """查询成交信息"""
    try:
        data = [to_dict(trade) for trade in rpc_client.get_all_trades()]
        return success_response(data)
    except Exception as e:
        logger.error(f"获取成交失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/position")
def get_all_positions(access: bool = Depends(get_access)) -> ApiResponse[list]:  # noqa: ARG001
    """查询持仓信息"""
    try:
        data = [to_dict(position) for position in rpc_client.get_all_positions()]
        return success_response(data)
    except Exception as e:
        logger.error(f"获取持仓失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/account")
def get_all_accounts(access: bool = Depends(get_access)) -> ApiResponse[list]:  # noqa: ARG001
    """查询账户资金"""
    try:
        data = [to_dict(account) for account in rpc_client.get_all_accounts()]
        return success_response(data)
    except Exception as e:
        logger.error(f"获取账户失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/contract")
def get_all_contracts(access: bool = Depends(get_access)) -> ApiResponse[list]:  # noqa: ARG001
    """查询合约信息"""
    try:
        data = [to_dict(contract) for contract in rpc_client.get_all_contracts()]
        return success_response(data)
    except Exception as e:
        logger.error(f"获取合约失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/trading_mode")
def get_trading_mode(access: bool = Depends(get_access)) -> ApiResponse[dict]:  # noqa: ARG001
    """查询交易模式（实盘/模拟盘）"""
    try:
        # 从RPC客户端获取引擎信息
        engines = rpc_client.get_all_engines() if hasattr(rpc_client, 'get_all_engines') else {}
        # 检查 TradeEngine 的网关名称判断模式
        for engine_name, engine in engines.items():
            if hasattr(engine, 'gateway_name'):
                is_paper = engine.gateway_name == "PAPER"
                return success_response({
                    "mode": "paper" if is_paper else "live",
                    "mode_text": "模拟盘" if is_paper else "实盘",
                    "engine": engine_name
                })
        # 默认返回模拟盘（如果无法确定）
        return success_response({"mode": "paper", "mode_text": "模拟盘", "engine": "unknown"})
    except Exception as e:
        logger.error(f"获取交易模式失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/kline/{vt_symbol}")
def get_kline_data(
    vt_symbol: str,
    period: str = Query("1d", description="周期: 1d, 1h, 15m"),
    access: bool = Depends(get_access)  # noqa: ARG001
) -> ApiResponse[list]:
    """获取K线数据"""
    try:
        # 从RPC获取K线数据
        if hasattr(rpc_client, 'get_kline'):
            data = rpc_client.get_kline(vt_symbol, period)
            return success_response(data if data else [])
        # 如果没有K线接口，返回错误
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/kline/{vt_symbol}")
def get_lab_kline(
    vt_symbol: str,
    period: str = Query("1d", description="周期: 1d, 1m"),
    days: int = Query(100, description="天数"),
    access: bool = Depends(get_access)
) -> ApiResponse[list[dict]]:
    """获取实验室K线数据"""
    try:
        if hasattr(rpc_client, 'lab_get_kline'):
            data = rpc_client.lab_get_kline(vt_symbol, period, days)
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取实验室K线失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/components")
def get_lab_components(
    start: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end: str = Query(None, description="结束日期 YYYY-MM-DD"),
    access: bool = Depends(get_access)
) -> ApiResponse[list[str]]:
    """获取当前指数成分股"""
    try:
        if hasattr(rpc_client, 'lab_get_components'):
            data = rpc_client.lab_get_components(start, end)
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取成分股失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/coverage")
def get_lab_coverage(access: bool = Depends(get_access)) -> ApiResponse[dict]:
    """获取数据覆盖情况"""
    try:
        if hasattr(rpc_client, 'lab_get_coverage'):
            data = rpc_client.lab_get_coverage()
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取数据覆盖失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/projects")
def get_lab_projects(access: bool = Depends(get_access)) -> ApiResponse[list[str]]:
    """列出所有实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_list_projects'):
            data = rpc_client.lab_list_projects()
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")
        return Errors.internal_error(str(e))


@app.post("/api/lab/project/switch")
def switch_lab_project(
    request: SwitchProjectRequest,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    """切换实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_switch_project'):
            data = rpc_client.lab_switch_project(
                request.project_name,
                request.index_code,
                request.data_source
            )
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"切换项目失败: {e}")
        return Errors.internal_error(str(e))


@app.post("/api/lab/project/create")
def create_lab_project(
    request: CreateProjectRequest,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    """创建实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_create_project'):
            data = rpc_client.lab_create_project(
                request.project_name,
                request.index_code,
                request.data_source
            )
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"创建项目失败: {e}")
        return Errors.internal_error(str(e))


@app.delete("/api/lab/project/{project_name}")
def delete_lab_project(
    project_name: str,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    """删除实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_delete_project'):
            data = rpc_client.lab_delete_project(project_name)
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"删除项目失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/signals")
def get_lab_signals(access: bool = Depends(get_access)) -> ApiResponse[list[str]]:
    """列出所有信号"""
    try:
        if hasattr(rpc_client, 'lab_list_signals'):
            data = rpc_client.lab_list_signals()
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取信号列表失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/signal/{name}")
def get_lab_signal(
    name: str,
    access: bool = Depends(get_access)
) -> ApiResponse[list[dict]]:
    """加载信号数据"""
    try:
        if hasattr(rpc_client, 'lab_load_signal'):
            result = rpc_client.lab_load_signal(name)
            if result is None or (isinstance(result, dict) and "error" in result):
                return Errors.not_found(f"Signal {name}")
            return success_response(result)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"加载信号失败: {e}")
        return Errors.internal_error(str(e))


@app.delete("/api/lab/signal/{name}")
def delete_lab_signal(
    name: str,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    """删除信号"""
    try:
        if hasattr(rpc_client, 'lab_remove_signal'):
            data = rpc_client.lab_remove_signal(name)
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"删除信号失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/indices")
def get_lab_indices(access: bool = Depends(get_access)) -> ApiResponse[list[str]]:
    """获取所有指数列表"""
    try:
        if hasattr(rpc_client, 'lab_list_indices'):
            data = rpc_client.lab_list_indices()
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取指数列表失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/lab/index/{index_code}")
def get_lab_index_info(
    index_code: str,
    access: bool = Depends(get_access)
) -> ApiResponse[dict | None]:
    """获取指数信息"""
    try:
        if hasattr(rpc_client, 'lab_get_index_info'):
            data = rpc_client.lab_get_index_info(index_code)
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取指数信息失败: {e}")
        return Errors.internal_error(str(e))


@app.post("/api/lab/index/switch")
def switch_lab_index(
    request: SwitchIndexRequest,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    """切换当前指数"""
    try:
        if hasattr(rpc_client, 'lab_switch_index'):
            data = rpc_client.lab_switch_index(request.index_code)
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"切换指数失败: {e}")
        return Errors.internal_error(str(e))


@app.get("/api/logs")
def get_logs(
    level: str = Query("all", description="日志级别: all, DEBUG, INFO, WARNING, ERROR"),
    source: str = Query("all", description="日志来源: all, system, trade, strategy"),
    keyword: str = Query("", description="关键词搜索"),
    access: bool = Depends(get_access)  # noqa: ARG001
) -> list:
    """获取日志列表"""
    filtered_logs = list(logs_buffer)

    # 按级别过滤
    if level != "all":
        filtered_logs = [log for log in filtered_logs if log['level'] == level]

    # 按来源过滤
    if source != "all":
        filtered_logs = [log for log in filtered_logs if log['source'] == source]

    # 按关键词过滤
    if keyword:
        filtered_logs = [log for log in filtered_logs if keyword in log['message']]

    return filtered_logs


# 活动状态的Websocket连接
active_websockets: list[WebSocket] = []

# 全局事件循环
event_loop: asyncio.AbstractEventLoop = asyncio.get_event_loop()


async def get_websocket_access(
    websocket: WebSocket,
    token: str | None = Query(None)
) -> bool:
    """Websocket鉴权"""
    credentials_exception: HTTPException = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        raise credentials_exception
    else:
        payload: dict = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username_value = payload.get("sub")
        if username_value is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise credentials_exception
        username: str = username_value
        if not secrets.compare_digest(USERNAME, username):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            raise credentials_exception

    return True


# websocket传递数据 - 支持 /ws 和 /ws/
@app.websocket("/ws")
@app.websocket("/ws/")
async def websocket_endpoint(websocket: WebSocket, access: bool = Depends(get_websocket_access)) -> None:  # noqa: ARG001
    """Weboskcet连接处理"""
    await websocket.accept()
    active_websockets.append(websocket)

    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_websockets.remove(websocket)


async def websocket_broadcast(msg: str) -> None:
    """Websocket数据广播"""
    for websocket in active_websockets:
        await websocket.send_text(msg)


def rpc_callback(topic: str, data: Any) -> None:
    """RPC回调函数"""
    if not active_websockets:
        return

    message_data: dict = {
        "topic": topic,
        "data": to_dict(data)
    }
    msg: str = json.dumps(message_data, ensure_ascii=False)
    asyncio.run_coroutine_threadsafe(websocket_broadcast(msg), event_loop)


@app.on_event("startup")
def startup_event() -> None:
    """应用启动事件"""
    global rpc_client
    rpc_client = RpcClient()
    rpc_client.callback = rpc_callback
    rpc_client.subscribe_topic("")
    rpc_client.start(REQ_ADDRESS, SUB_ADDRESS)


@app.on_event("shutdown")
def shutdown_event() -> None:
    """应用停止事件"""
    rpc_client.stop()
