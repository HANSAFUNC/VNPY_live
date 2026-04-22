"""数据模型模板"""

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime


class AccountData(BaseModel):
    """账户数据"""
    balance: float = 0
    available: float = 0
    frozen: float = 0


class PositionView(BaseModel):
    """持仓视图"""
    vt_symbol: str
    direction: str
    volume: int
    avg_price: float
    last_price: float
    pnl: float
    pnl_pct: float


class TradeView(BaseModel):
    """成交视图"""
    vt_symbol: str
    direction: str
    price: float
    volume: int
    time: str


class StrategyStatus(BaseModel):
    """策略状态"""
    name: str
    running: bool
    class_name: str = ""


class SignalView(BaseModel):
    """信号视图"""
    symbol: str
    action: str  # 买入/卖出
    strength: float = 1.0
    time: str = ""


class DashboardData(BaseModel):
    """看板数据"""
    account: Dict[str, float]
    positions: List[PositionView]
    trades: List[TradeView]
    strategies: List[StrategyStatus]
    signals: List[SignalView]
    timestamp: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
