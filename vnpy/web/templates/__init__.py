"""数据模型模板"""

from pydantic import BaseModel, Field
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


class CandleData(BaseModel):
    """K线数据"""
    timestamp: str
    open: float
    high: float
    low: float
    close: float
    volume: float


class ChartData(BaseModel):
    """图表数据"""
    vt_symbol: str
    candles: List[CandleData]
    indicators: Dict[str, List[float]] = {}  # 技术指标


class StatsData(BaseModel):
    """统计数据"""
    total_return: float  # 总收益率
    annual_return: float  # 年化收益
    max_drawdown: float  # 最大回撤
    sharpe_ratio: float  # 夏普比率
    win_rate: float  # 胜率
    profit_factor: float  # 盈亏比
    total_trades: int  # 总交易次数
    winning_trades: int  # 盈利次数
    losing_trades: int  # 亏损次数
    avg_profit: float  # 平均盈利
    avg_loss: float  # 平均亏损


class SignalStock(BaseModel):
    """信号股票"""
    vt_symbol: str
    signal: int  # 1=买入, -1=卖出
    strength: float = 1.0  # 信号强度
    datetime: str = ""
    close_price: float = 0.0
    volume: float = 0.0


class StockPoolData(BaseModel):
    """股票池数据"""
    buy_stocks: List[SignalStock] = []  # 今日买入股票
    sell_stocks: List[SignalStock] = []  # 今日卖出股票
    last_update: str = ""


class DashboardData(BaseModel):
    """看板数据"""
    account: Dict[str, float]
    positions: List[PositionView]
    trades: List[TradeView]
    strategies: List[StrategyStatus]
    signals: List[SignalView]
    chart_data: Dict[str, List[CandleData]] = {}
    available_symbols: List[str] = []  # Lab 中所有可用股票
    current_symbol: str = ""  # 当前选中的股票
    stock_pool: StockPoolData = Field(default_factory=StockPoolData)  # 股票池
    stats: Optional[StatsData] = None
    timestamp: str = ""

    def __init__(self, **data):
        super().__init__(**data)
        self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
