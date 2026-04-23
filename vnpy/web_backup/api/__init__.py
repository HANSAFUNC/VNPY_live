"""Web 看板 API 路由"""

from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from pydantic import BaseModel

# 策略相关路由
strategy_router = APIRouter()


class StrategyStatus(BaseModel):
    """策略状态"""
    name: str
    running: bool
    class_name: str
    vt_symbols: List[str]


class StrategySetting(BaseModel):
    """策略设置"""
    name: str
    setting: Dict[str, Any]


@strategy_router.get("/list", response_model=List[StrategyStatus])
async def list_strategies():
    """获取策略列表"""
    # TODO: 从策略引擎获取
    return [
        StrategyStatus(
            name="XGBExtremaLive",
            running=True,
            class_name="XGBExtremaStrategy",
            vt_symbols=["000001.SZ", "000002.SZ"]
        )
    ]


@strategy_router.post("/{name}/start")
async def start_strategy(name: str):
    """启动策略"""
    # TODO: 调用策略引擎启动
    return {"success": True, "message": f"Strategy {name} started"}


@strategy_router.post("/{name}/stop")
async def stop_strategy(name: str):
    """停止策略"""
    # TODO: 调用策略引擎停止
    return {"success": True, "message": f"Strategy {name} stopped"}


@strategy_router.get("/{name}/settings")
async def get_strategy_settings(name: str):
    """获取策略设置"""
    return {
        "min_days": 1,
        "profit_threshold": 0.03,
        "cash_ratio": 0.95
    }


@strategy_router.post("/{name}/settings")
async def update_strategy_settings(name: str, setting: StrategySetting):
    """更新策略设置"""
    # TODO: 更新策略参数
    return {"success": True, "message": "Settings updated"}


# 交易相关路由
trading_router = APIRouter()


class OrderRequest(BaseModel):
    """下单请求"""
    vt_symbol: str
    direction: str  # 买/卖
    price: float
    volume: int


@trading_router.get("/positions")
async def get_positions():
    """获取持仓"""
    # TODO: 从引擎获取实际持仓
    return []


@trading_router.get("/orders")
async def get_orders(status: str = None):
    """获取订单列表"""
    # status: active, filled, cancelled, all
    return []


@trading_router.post("/order")
async def send_order(order: OrderRequest):
    """发送订单"""
    # TODO: 调用引擎发送订单
    return {"success": True, "order_id": "12345"}


@trading_router.post("/order/{order_id}/cancel")
async def cancel_order(order_id: str):
    """撤单"""
    return {"success": True}


@trading_router.get("/trades")
async def get_trades(limit: int = 50):
    """获取成交记录"""
    return []


@trading_router.get("/signals")
async def get_signals(date: str = None):
    """获取交易信号"""
    # date: YYYY-MM-DD，默认今天
    return []


# 账户相关路由
account_router = APIRouter()


@account_router.get("/summary")
async def get_account_summary():
    """获取账户概览"""
    return {
        "balance": 1000000,
        "available": 500000,
        "frozen": 100000,
        "position_value": 400000,
        "daily_pnl": 5000,
        "total_pnl": 10000
    }


@account_router.get("/daily")
async def get_daily_stats(start_date: str = None, end_date: str = None):
    """获取每日统计"""
    return []


@account_router.get("/pnl")
async def get_pnl_curve(days: int = 30):
    """获取盈亏曲线"""
    return {
        "dates": [],
        "pnl": [],
        "cumsum": []
    }
