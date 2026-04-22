"""RPC模式的Web看板引擎

支持远程连接交易服务器，所有数据通过RPC获取。
"""
from typing import Optional, List, Dict
from vnpy.event import EventEngine, Event
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.object import (
    TickData, TradeData, OrderData, PositionData, AccountData
)

from .engine import WebEngine
from .templates import CandleData, StatsData


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
        # 调用BaseEngine初始化（跳过WebEngine的__init__）
        BaseEngine.__init__(self, main_engine, event_engine, self.engine_name)

        self.req_address = req_address
        self.sub_address = sub_address
        self.rpc_client: Optional = None
        self._connected = False

        # 从父类复制必要的初始化
        from .engine import ConnectionManager
        from .templates import StockPoolData

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

        # 创建 FastAPI 应用
        self.app = self._create_app()

        # 注册事件监听
        self._register_events()

        # 初始化数据
        self.stock_pool_data = self._generate_sample_stock_pool()
        self.available_symbols = self._load_available_symbols()

        # 从数据库加载历史K线数据
        from datetime import datetime
        for symbol in self.available_symbols:
            self.all_candles[symbol] = self._load_historical_candles(symbol, days=60)

        if self.available_symbols:
            self.current_symbol = self.available_symbols[0]
        self.stats = self._generate_sample_stats()

    def connect_rpc(self) -> bool:
        """连接到RPC服务端

        Returns
        -------
        bool
            连接成功返回True
        """
        try:
            from vnpy_rpcservice import RpcClient

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
            tick = self.ticks.get(f"{pos.symbol}.{pos.exchange.value}")
            last_price = tick.last_price if tick else pos.price

            pnl = (last_price - pos.price) * pos.volume
            pnl_pct = (last_price / pos.price - 1) * 100 if pos.price else 0

            positions.append({
                "vt_symbol": f"{pos.symbol}.{pos.exchange.value}",
                "direction": pos.direction.value,
                "volume": pos.volume,
                "avg_price": round(pos.price, 2),
                "last_price": round(last_price, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2)
            })
        return positions

    def _get_trade_data(self) -> list:
        """通过RPC获取成交数据"""
        if not self._connected:
            return []

        from datetime import datetime

        trades = []
        for trade in sorted(self.trades.values(), key=lambda x: x.datetime or datetime.min, reverse=True)[:50]:
            trades.append({
                "vt_symbol": f"{trade.symbol}.{trade.exchange.value}",
                "direction": trade.direction.value,
                "price": trade.price,
                "volume": trade.volume,
                "time": trade.datetime.strftime("%H:%M:%S") if trade.datetime else "--"
            })
        return trades
