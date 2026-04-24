"""Alpha 策略实盘交易引擎

将 AlphaStrategy 策略与真实交易网关连接，实现:
- 实时行情接收 (Tick/Bar)
- 信号执行与订单管理
- 持仓和资金同步
- 与回测引擎兼容的接口
"""

from collections import defaultdict
from datetime import datetime, time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from vnpy.trader.gateway import BaseGateway

import polars as pl
from vnpy.event import Event, EventEngine
from vnpy.trader.engine import MainEngine, BaseEngine
from vnpy.trader.event import EVENT_TICK, EVENT_TRADE, EVENT_ORDER, EVENT_POSITION, EVENT_ACCOUNT
from vnpy.trader.object import (
    BarData, TickData, TradeData, OrderData, PositionData, AccountData,
    OrderRequest, CancelRequest, SubscribeRequest, ContractData
)
from vnpy.trader.constant import Interval, Direction, Offset, Exchange, OrderType

from vnpy.alpha.lab import AlphaLab
from vnpy.alpha.strategy.template import AlphaStrategy
from vnpy.alpha.logger import logger


class TradeEngine(BaseEngine):
    """交易引擎

    统一交易接口，通过 MainEngine 自动区分模拟盘/实盘:
    - 加载 vnpy_paperaccount 后: 所有订单本地模拟撮合
    - 未加载: 订单发送到真实交易所

    自动检测机制：
    - 如果 MainEngine.get_gateway() 返回 None 或找不到网关
      自动假设为模拟盘模式（用于统计报告）

    与 BacktestingEngine 保持接口兼容，方便策略无缝切换。
    """

    engine_name: str = "TradeEngine"
    gateway_name: str = "LIVE"

    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        lab: AlphaLab,
        gateway_name: str,
    ) -> None:
        """初始化实盘引擎

        Parameters
        ----------
        main_engine : MainEngine
            VNPY 主引擎（如果加载了 vnpy_paperaccount，会自动拦截订单）
        event_engine : EventEngine
            事件引擎
        lab : AlphaLab
            Alpha 实验室（用于加载信号）
        gateway_name : str
            交易网关名称（如 "XT", "CTP", "PAPER"）
        """
        super().__init__(main_engine, event_engine, self.engine_name)

        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.lab: AlphaLab = lab
        self.gateway_name: str = gateway_name

        # 策略相关
        self.strategy: AlphaStrategy | None = None
        self.strategy_class: type[AlphaStrategy] | None = None
        self.signal_df: pl.DataFrame | None = None
        self.current_date: datetime | None = None

        # 行情数据
        self.ticks: dict[str, TickData] = {}
        self.bars: dict[str, BarData] = {}
        self.vt_symbols: list[str] = []
        self.interval: Interval = Interval.DAILY

        # 交易状态
        self.active_orders: dict[str, OrderData] = {}
        self.positions: dict[str, PositionData] = {}
        self.account: AccountData | None = None

        # 资金设置
        self.capital: float = 0
        self.cash: float = 0
        self.cash_ratio: float = 0.95  # 现金利用率

        # 交易费率（从合约配置加载）
        self.long_rates: dict[str, float] = {}
        self.short_rates: dict[str, float] = {}
        self.sizes: dict[str, float] = {}
        self.priceticks: dict[str, float] = {}

        # 运行状态
        self.trading: bool = False
        self.trading_start_time: time = time(9, 30)  # 开始交易时间
        self.trading_end_time: time = time(14, 55)   # 结束交易时间

        # 注册事件监听
        self.register_event()

        logger.info(f"TradeEngine 初始化完成，网关: {gateway_name}")

    def register_event(self) -> None:
        """注册事件监听"""
        self.event_engine.register(EVENT_TICK, self.process_tick_event)
        self.event_engine.register(EVENT_TRADE, self.process_trade_event)
        self.event_engine.register(EVENT_ORDER, self.process_order_event)
        self.event_engine.register(EVENT_POSITION, self.process_position_event)
        self.event_engine.register(EVENT_ACCOUNT, self.process_account_event)
        logger.info("事件监听注册完成")

    def add_strategy(
        self,
        strategy_class: type[AlphaStrategy],
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict,
        signal_df: pl.DataFrame
    ) -> None:
        """添加策略

        Parameters
        ----------
        strategy_class : type[AlphaStrategy]
            策略类
        strategy_name : str
            策略名称
        vt_symbols : list[str]
            交易标的列表
        setting : dict
            策略参数设置
        signal_df : pl.DataFrame
            交易信号 DataFrame
        """
        self.strategy_class = strategy_class
        self.vt_symbols = vt_symbols
        self.signal_df = signal_df

        # 创建策略实例
        self.strategy = strategy_class(
            strategy_engine=self,
            strategy_name=strategy_name,
            vt_symbols=vt_symbols,
            setting=setting
        )

        # 加载合约设置
        self._load_contract_settings()

        logger.info(f"策略 {strategy_name} 已添加，标的数：{len(vt_symbols)}")

    def _load_contract_settings(self) -> None:
        """加载合约交易设置"""
        contract_settings = self.lab.load_contract_setttings()
        for vt_symbol in self.vt_symbols:
            setting = contract_settings.get(vt_symbol)
            if setting:
                self.long_rates[vt_symbol] = setting.get("long_rate", 0.0005)
                self.short_rates[vt_symbol] = setting.get("short_rate", 0.0015)
                self.sizes[vt_symbol] = setting.get("size", 1)
                self.priceticks[vt_symbol] = setting.get("pricetick", 0.01)
            else:
                logger.warning(f"找不到合约 {vt_symbol} 配置，使用默认")
                self.long_rates[vt_symbol] = 0.0005
                self.short_rates[vt_symbol] = 0.0015
                self.sizes[vt_symbol] = 1
                self.priceticks[vt_symbol] = 0.01

    def subscribe_market_data(self, vt_symbols: list[str] | None = None) -> None:
        """订阅行情（模拟/实盘统一处理）

        Parameters
        ----------
        vt_symbols : list[str] | None
            要订阅的标的列表，默认使用 self.vt_symbols
        """
        if vt_symbols is None:
            vt_symbols = self.vt_symbols

        for vt_symbol in vt_symbols:
            try:
                if self.gateway_name:
                    # 统一通过网关订阅
                    self.main_engine.subscribe(SubscribeRequest(
                        symbol=vt_symbol.split('.')[0],
                        exchange=Exchange(vt_symbol.split('.')[1])
                    ), self.gateway_name)
                    logger.info(f"订阅行情: {vt_symbol}")
                else:
                    logger.warning(f"未配置网关，无法订阅 {vt_symbol}")
            except Exception as e:
                logger.error(f"订阅 {vt_symbol} 失败: {e}")

    def start_trading(self, capital: float = 1_000_000, cash_ratio: float = 0.95) -> None:
        """启动实盘交易

        Parameters
        ----------
        capital : float
            初始资金（用于计算仓位）
        cash_ratio : float
            现金利用率
        """
        if not self.strategy:
            logger.error("策略未添加，无法启动")
            return

        self.capital = capital
        self.cash_ratio = cash_ratio
        self.trading = True

        # 订阅行情（统一通过网关订阅，由 MainEngine 处理模拟/实盘）
        self.subscribe_market_data()

        # 初始化策略
        self.strategy.on_init()

        # 统一更新账户和持仓
        self._update_account()
        self._update_positions()

        logger.info(f"交易已启动，初始资金：{capital:,.2f}，现金利用率：{cash_ratio}")

    def _update_account(self) -> None:
        """更新账户信息"""
        try:
            if self.gateway_name:
                # 统一从网关获取账户（无论模拟/实盘）
                accounts = self.main_engine.get_all_accounts()
                account = None
                for acc in accounts:
                    if acc.gateway_name == self.gateway_name:
                        account = acc
                        break

                if account:
                    self.account = account
                    self.cash = account.available
                else:
                    # 网关未返回数据，使用默认值
                    self._init_paper_account()
            else:
                # 无网关时使用本地模拟
                self._init_paper_account()
        except Exception as e:
            logger.warning(f"更新账户信息失败: {e}")
            self._init_paper_account()

    def _update_positions(self) -> None:
        """更新持仓信息"""
        try:
            if self.gateway_name:
                # 统一从网关获取持仓
                positions = self.main_engine.get_all_positions()
                self.positions = {
                    pos.vt_positionid: pos
                    for pos in positions
                    if pos.gateway_name == self.gateway_name
                }
            else:
                # 无网关时使用空持仓
                self.positions = {}
        except Exception as e:
            logger.warning(f"更新持仓信息失败: {e}")
            self.positions = {}

    def _init_paper_account(self) -> None:
        """初始化模拟账户（当无法从网关获取时使用）"""
        if not hasattr(self, '_paper_account_initialized'):
            self.account = AccountData(
                gateway_name=self.gateway_name or "PAPER",
                accountid="PAPER_ACCOUNT",
                balance=self.capital,
                frozen=0.0
            )
            # 手动设置可用资金
            object.__setattr__(self.account, 'available', self.capital)
            self.cash = self.capital
            self._paper_account_initialized = True

    def stop_trading(self) -> None:
        """停止实盘交易"""
        self.trading = False

        # 撤掉所有未完成订单
        self.cancel_all()

        if self.strategy:
            self.strategy.on_stop()

        logger.info("交易已停止")

    # ==================== 事件处理 ====================

    def process_tick_event(self, event: Event) -> None:
        """处理 Tick 行情事件"""
        tick: TickData = event.data
        self.ticks[tick.vt_symbol] = tick

        # 只处理订阅的标的
        if tick.vt_symbol not in self.vt_symbols:
            return

        # 检查是否在交易时段
        if not self.is_trading_time():
            return

        # 更新当前日期（用于获取信号）
        tick_date = tick.datetime.date()
        if self.current_date != tick_date:
            self.current_date = tick_date
            self.on_new_day(tick_date)

        # 生成合成 K 线（如果需要）
        if self.interval != Interval.TICK:
            self.update_bar_from_tick(tick)

    def process_trade_event(self, event: Event) -> None:
        """处理成交事件"""
        trade: TradeData = event.data

        # 更新策略持仓
        if self.strategy and trade.vt_symbol in self.vt_symbols:
            self.strategy.update_trade(trade)
            self.strategy.on_trade(trade)

        logger.info(f"成交: {trade.vt_symbol}, 方向: {trade.direction.value}, "
                   f"价格: {trade.price}, 数量: {trade.volume}")

    def process_order_event(self, event: Event) -> None:
        """处理订单事件"""
        order: OrderData = event.data

        if order.is_active():
            self.active_orders[order.vt_orderid] = order
        else:
            self.active_orders.pop(order.vt_orderid, None)

        # 更新策略订单状态
        if self.strategy:
            self.strategy.update_order(order)

    def process_position_event(self, event: Event) -> None:
        """处理持仓事件"""
        position: PositionData = event.data
        self.positions[position.vt_symbol] = position

        # 更新策略持仓
        if self.strategy and position.vt_symbol in self.vt_symbols:
            # 计算净持仓
            net_pos = position.volume - position.frozen
            if position.direction == Direction.SHORT:
                net_pos = -net_pos
            self.strategy.pos_data[position.vt_symbol] = net_pos

    def process_account_event(self, event: Event) -> None:
        """处理账户事件"""
        account: AccountData = event.data
        self.account = account
        self.cash = account.available

    def on_new_day(self, trade_date) -> None:
        """新的一天回调"""
        logger.info(f"新的交易日: {trade_date}")

        # 如果是日频策略，获取当日信号并执行
        if self.interval == Interval.DAILY and self.strategy:
            self.execute_daily_signals(trade_date)

    def execute_daily_signals(self, trade_date) -> None:
        """执行日频信号"""
        if self.signal_df is None or self.signal_df.is_empty():
            return

        # 过滤当日信号
        date_str = trade_date.strftime("%Y-%m-%d")
        daily_signals = self.signal_df.filter(
            pl.col("datetime").cast(str).str.starts_with(date_str)
        )

        if daily_signals.is_empty():
            logger.info(f"{date_str} 无交易信号")
            return

        logger.info(f"{date_str} 信号数: {len(daily_signals)}")

        # 构建 bars（使用最新 tick 或前收盘价）
        bars: dict[str, BarData] = {}
        for vt_symbol in self.vt_symbols:
            tick = self.ticks.get(vt_symbol)
            if tick:
                bar = BarData(
                    symbol=tick.symbol,
                    exchange=tick.exchange,
                    datetime=tick.datetime,
                    interval=Interval.DAILY,
                    open_price=tick.open_price or tick.last_price,
                    high_price=tick.high_price or tick.last_price,
                    low_price=tick.low_price or tick.last_price,
                    close_price=tick.last_price,
                    volume=tick.volume,
                    gateway_name=self.gateway_name
                )
                bars[vt_symbol] = bar

        # 调用策略 on_bars
        if bars:
            self.bars = bars
            try:
                self.strategy.on_bars(bars)
            except Exception as e:
                logger.error(f"策略 on_bars 执行异常: {e}")

    def update_bar_from_tick(self, tick: TickData) -> None:
        """从 Tick 更新 K 线（简化版，实际应该用 BarGenerator）"""
        # 这里简化处理，直接使用 tick 价格作为当前 bar
        bar = BarData(
            symbol=tick.symbol,
            exchange=tick.exchange,
            datetime=tick.datetime,
            interval=self.interval,
            open_price=tick.open_price or tick.last_price,
            high_price=tick.high_price or tick.last_price,
            low_price=tick.low_price or tick.last_price,
            close_price=tick.last_price,
            volume=tick.volume,
            gateway_name=self.gateway_name
        )
        self.bars[tick.vt_symbol] = bar

    def is_trading_time(self) -> bool:
        """检查是否在交易时段"""
        now = datetime.now().time()
        return self.trading_start_time <= now <= self.trading_end_time

    # ==================== 交易接口（与 BacktestingEngine 兼容） ====================

    def send_order(
        self,
        strategy: AlphaStrategy,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ) -> list[str]:
        """发送订单

        注：模拟盘/实盘通过 MainEngine 自动区分
        - 如果加载了 vnpy_paperaccount，MainEngine.send_order 会被拦截，自动本地撮合
        - 如果没有加载，订单会发送到真实交易所
        TradeEngine 只需统一调用 MainEngine.send_order
        """
        if not self.trading:
            logger.warning("交易未启动，无法下单")
            return []

        return self._send_order_to_main_engine(vt_symbol, direction, offset, price, volume)

    def _send_order_to_main_engine(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ) -> list[str]:
        """发送订单到 MainEngine

        MainEngine 会根据是否加载 paperaccount 自动处理:
        - 已加载 vnpy_paperaccount: 本地模拟撮合
        - 未加载: 发送到真实交易所
        """
        symbol, exchange_str = vt_symbol.split(".")

        req = OrderRequest(
            symbol=symbol,
            exchange=Exchange(exchange_str),
            direction=direction,
            type=OrderType.LIMIT,
            volume=volume,
            price=round(price, 4),
            offset=offset
        )

        vt_orderid: str = self.main_engine.send_order(req, self.gateway_name)

        if vt_orderid:
            logger.info(f"[TradeEngine] 下单: {vt_symbol}, {direction.value}, "
                       f"{offset.value}, 价格: {price}, 数量: {volume}, 订单号: {vt_orderid}")
            return [vt_orderid]
        else:
            logger.error(f"[TradeEngine] 下单失败: {vt_symbol}")
            return []

    def cancel_order(self, strategy: AlphaStrategy, vt_orderid: str) -> None:
        """撤单

        注：模拟盘/实盘通过 MainEngine 自动区分
        - 如果加载了 vnpy_paperaccount，MainEngine.cancel_order 会被拦截
        - 如果没有加载，撤单请求会发送到真实交易所
        """
        order = self.main_engine.get_order(vt_orderid)
        if not order:
            return

        req = CancelRequest(
            symbol=order.symbol,
            exchange=order.exchange,
            orderid=order.orderid
        )
        self.main_engine.cancel_order(req, self.gateway_name)

    def cancel_all(self) -> None:
        """撤销所有活跃订单"""
        for vt_orderid in list(self.active_orders.keys()):
            if self.strategy:
                self.cancel_order(self.strategy, vt_orderid)

    def query_account(self) -> None:
        """查询账户

        注：如果加载了 vnpy_paperaccount，会返回模拟账户数据
        """
        gateway = self.main_engine.get_gateway(self.gateway_name)
        if gateway:
            gateway.query_account()

    def query_positions(self) -> None:
        """查询持仓

        注：如果加载了 vnpy_paperaccount，会返回模拟持仓数据
        """
        gateway = self.main_engine.get_gateway(self.gateway_name)
        if gateway:
            gateway.query_position()

    # ==================== 查询接口（与 BacktestingEngine 兼容） ====================

    def get_cash_available(self) -> float:
        """获取可用资金"""
        return self.cash if self.account else self.capital

    def get_holding_value(self) -> float:
        """获取持仓市值"""
        total_value = 0.0
        for vt_symbol, position in self.positions.items():
            tick = self.ticks.get(vt_symbol)
            if tick:
                price = tick.last_price
                volume = position.volume if position.direction == Direction.LONG else -position.volume
                total_value += price * volume
        return total_value

    def get_signal(self) -> pl.DataFrame:
        """获取当前信号（与回测引擎兼容）"""
        if self.signal_df is None:
            return pl.DataFrame()

        # 返回当日信号
        if self.current_date:
            date_str = self.current_date.strftime("%Y-%m-%d")
            return self.signal_df.filter(
                pl.col("datetime").cast(str).str.starts_with(date_str)
            )
        return self.signal_df

    def write_log(self, msg: str, strategy: AlphaStrategy | None = None) -> None:
        """写入日志"""
        source = strategy.strategy_name if strategy else "TradeEngine"
        logger.info(f"[{source}] {msg}")

    def get_pos(self, vt_symbol: str) -> float:
        """获取持仓

        统一从 MainEngine 获取持仓数据
        - 如果加载了 vnpy_paperaccount，返回模拟持仓
        - 否则返回真实持仓
        """
        position = self.positions.get(vt_symbol)
        if not position:
            return 0.0
        if position.direction == Direction.LONG:
            return position.volume
        else:
            return -position.volume
