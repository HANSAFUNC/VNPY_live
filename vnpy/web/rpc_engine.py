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

        # 从数据库加载历史K线数据（仅在RPC连接后加载）
        if self._connected:
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
            from vnpy.rpc import RpcClient

            self.rpc_client = RpcClient()
            self.rpc_client.subscribe_topic("")
            self.rpc_client.start(
                req_address=self.req_address,
                sub_address=self.sub_address
            )

            # 设置事件回调
            self.rpc_client.callback = self._on_rpc_event

            self._connected = True
            print(f"✓ RPC连接成功: {self.req_address}")

            # RPC连接成功后加载历史数据
            print("正在通过RPC加载历史数据...")
            for symbol in self.available_symbols:
                self.all_candles[symbol] = self._load_historical_candles(symbol, days=60)
            print(f"历史数据加载完成: {len(self.available_symbols)} 个合约")

            return True
        except Exception as e:
            print(f"✗ RPC连接失败: {e}")
            return False

    def _on_rpc_event(self, topic: str, event: Event) -> None:
        """处理RPC推送的事件

        Parameters
        ----------
        topic : str
            事件主题
        event : Event
            事件对象
        """
        if event is None:
            return

        # 将事件放入本地事件引擎
        self.event_engine.put(event)

        # 更新本地数据缓存
        data = event.data
        if hasattr(data, 'vt_symbol'):
            if isinstance(data, TickData):
                self.ticks[data.vt_symbol] = data
            elif isinstance(data, TradeData):
                self.trades[data.vt_tradeid] = data
            elif isinstance(data, OrderData):
                self.orders[data.vt_orderid] = data
            elif isinstance(data, PositionData):
                self.positions[data.vt_symbol] = data
        elif isinstance(data, AccountData):
            self.account = data

    def disconnect_rpc(self) -> None:
        """断开RPC连接"""
        if self.rpc_client:
            self.rpc_client.stop()
            self.rpc_client.join()
            self._connected = False
            print("RPC连接已断开")

    def _get_account_data(self) -> dict:
        """通过RPC获取账户数据"""
        if not self._connected or not self.rpc_client:
            return {"balance": 0, "available": 0, "frozen": 0}

        try:
            accounts = self.rpc_client.get_all_accounts()
            if accounts:
                acc = accounts[0]
                return {
                    "balance": acc.balance,
                    "available": acc.available,
                    "frozen": acc.frozen
                }
        except Exception as e:
            print(f"获取账户数据失败: {e}")
        return {"balance": 0, "available": 0, "frozen": 0}

    def _get_position_data(self) -> list:
        """通过RPC获取持仓数据"""
        if not self._connected or not self.rpc_client:
            return []

        try:
            positions = []
            for pos in self.rpc_client.get_all_positions():
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
        except Exception as e:
            print(f"获取持仓数据失败: {e}")
            return []

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

    def _load_historical_candles(self, vt_symbol: str, days: int = 60) -> list:
        """通过RPC从远程服务器加载历史K线数据

        Parameters
        ----------
        vt_symbol : str
            合约代码 (如: 000001.SZ)
        days : int
            查询天数

        Returns
        -------
        list
            K线数据列表
        """
        if not self._connected:
            # 未连接时返回空数据
            return []

        try:
            from datetime import datetime, timedelta
            from vnpy.trader.object import HistoryRequest
            from vnpy.trader.constant import Exchange, Interval
            from .templates import CandleData

            symbol, exchange_str = vt_symbol.split('.')
            exchange = Exchange(exchange_str)

            # 计算时间范围
            end = datetime.now()
            start = end - timedelta(days=days)

            # 创建历史数据请求
            req = HistoryRequest(
                symbol=symbol,
                exchange=exchange,
                interval=Interval.DAILY,
                start=start,
                end=end
            )

            # 通过RPC查询历史数据
            bars = self.rpc_client.query_history(req, "")

            if not bars:
                print(f"RPC查询历史数据为空: {vt_symbol}")
                return []

            # 转换为 CandleData
            candles = []
            for bar in bars:
                candles.append(CandleData(
                    timestamp=bar.datetime.strftime("%Y-%m-%d"),
                    open=bar.open_price,
                    high=bar.high_price,
                    low=bar.low_price,
                    close=bar.close_price,
                    volume=bar.volume
                ))

            print(f"RPC加载 {vt_symbol} 历史数据: {len(candles)} 条")
            return candles

        except Exception as e:
            print(f"RPC加载历史数据失败 {vt_symbol}: {e}")
            return []
