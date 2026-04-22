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
from vnpy.trader.engine import MainEngine
from vnpy.trader.event import EVENT_TICK, EVENT_TRADE, EVENT_ORDER, EVENT_POSITION, EVENT_ACCOUNT
from vnpy.trader.object import (
    BarData, TickData, TradeData, OrderData, PositionData, AccountData,
    OrderRequest, CancelRequest, SubscribeRequest, ContractData
)
from vnpy.trader.constant import Interval, Direction, Offset, Status, Exchange, OrderType

from vnpy.alpha.lab import AlphaLab
from vnpy.alpha.strategy.template import AlphaStrategy
from vnpy.alpha.logger import logger


class LiveAlphaEngine:
    """Alpha 策略实盘交易引擎

    支持三种模式：
    1. 实盘模式 (paper_trading=False): 真实订单发送到交易所
    2. 模拟盘模式 (paper_trading=True): 使用实时行情，本地模拟撮合
    3. 回测模式: 使用 BacktestingEngine

    与 BacktestingEngine 保持接口兼容，方便策略无缝切换。
    """

    gateway_name: str = "LIVE"

    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        lab: AlphaLab,
        gateway_name: str,
        paper_trading: bool = False
    ) -> None:
        """初始化实盘引擎

        Parameters
        ----------
        main_engine : MainEngine
            VNPY 主引擎
        event_engine : EventEngine
            事件引擎
        lab : AlphaLab
            Alpha 实验室（用于加载信号）
        gateway_name : str
            交易网关名称（如 "XT", "CTP"）
        paper_trading : bool
            是否为模拟盘模式（使用真实行情，本地模拟成交）
        """
        self.main_engine: MainEngine = main_engine
        self.event_engine: EventEngine = event_engine
        self.lab: AlphaLab = lab
        self.gateway_name: str = gateway_name
        self.paper_trading: bool = paper_trading

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

        logger.info(f"LiveAlphaEngine 初始化完成，网关: {gateway_name}")

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

        # 初始化模拟盘状态（计数器等）
        if self.paper_trading:
            self.initial_capital = capital
            self.paper_positions = {}
            self.paper_trades = []
            self.order_count = 0
            self.trade_count = 0

        # 订阅行情（模拟/实盘统一通过网关订阅）
        self.subscribe_market_data()

        # 初始化策略
        self.strategy.on_init()

        # 统一更新账户和持仓
        self._update_account()
        self._update_positions()

        mode = "模拟盘" if self.paper_trading else "实盘"
        logger.info(f"{mode}交易已启动，初始资金：{capital:,.2f}，现金利用率：{cash_ratio}")

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
            if self.paper_trading:
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
                # 无网关时使用本地
                if self.paper_trading:
                    self.positions = {}
        except Exception as e:
            logger.warning(f"更新持仓信息失败: {e}")
            if self.paper_trading:
                self.positions = {}

    def _init_paper_account(self) -> None:
        """初始化模拟账户"""
        if not hasattr(self, '_paper_account_initialized'):
            self.account = AccountData(
                gateway_name=self.gateway_name or "PAPER",
                accountid="PAPER_ACCOUNT",
                balance=self.initial_capital,
                frozen=0.0
            )
            # 手动设置可用资金
            object.__setattr__(self.account, 'available', self.initial_capital)
            self.cash = self.initial_capital
            self._paper_account_initialized = True

    def stop_trading(self) -> None:
        """停止实盘交易"""
        self.trading = False

        # 撤掉所有未完成订单
        self.cancel_all()

        if self.strategy:
            self.strategy.on_stop()

        # 模拟盘模式：打印交易统计
        if self.paper_trading and hasattr(self, 'paper_trades'):
            self._print_paper_trading_stats()

        mode = "模拟盘" if self.paper_trading else "实盘"
        logger.info(f"{mode}交易已停止")

    def _print_paper_trading_stats(self) -> None:
        """打印模拟盘交易统计"""
        if not hasattr(self, 'paper_trades'):
            return

        total_trades = len(self.paper_trades)
        if total_trades == 0:
            logger.info("模拟盘：无成交记录")
            return

        # 计算盈亏
        total_pnl = 0.0
        buy_amount = 0.0
        sell_amount = 0.0

        for trade in self.paper_trades:
            volume = trade.volume * self.sizes.get(trade.vt_symbol, 1)
            amount = trade.price * volume
            if trade.direction == Direction.LONG:
                buy_amount += amount
            else:
                sell_amount += amount

        # 计算持仓市值
        holding_value = 0.0
        for vt_symbol, pos in self.paper_positions.items():
            tick = self.ticks.get(vt_symbol)
            if tick:
                holding_value += pos['volume'] * tick.last_price

        current_balance = self.cash + holding_value
        total_return = (current_balance - self.initial_capital) / self.initial_capital * 100

        logger.info("=" * 60)
        logger.info("模拟盘交易统计")
        logger.info("=" * 60)
        logger.info(f"总成交次数：{total_trades}")
        logger.info(f"买入金额：{buy_amount:,.2f}")
        logger.info(f"卖出金额：{sell_amount:,.2f}")
        logger.info(f"当前现金：{self.cash:,.2f}")
        logger.info(f"持仓市值：{holding_value:,.2f}")
        logger.info(f"总资产：{current_balance:,.2f}")
        logger.info(f"总收益率：{total_return:,.2f}%")
        logger.info("=" * 60)

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
        """发送订单"""
        if not self.trading:
            logger.warning("交易未启动，无法下单")
            return []

        if self.paper_trading:
            # 模拟盘：本地撮合
            return self._paper_send_order(vt_symbol, direction, offset, price, volume)
        else:
            # 实盘：发送到交易所
            return self._live_send_order(vt_symbol, direction, offset, price, volume)

    def _paper_send_order(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ) -> list[str]:
        """模拟盘本地撮合"""
        symbol, exchange_str = vt_symbol.split(".")

        # 生成订单号
        self.order_count += 1
        orderid = str(self.order_count)
        vt_orderid = f"{self.gateway_name or 'PAPER'}.{self.order_count:08d}"

        # 创建订单对象
        order = OrderData(
            gateway_name=self.gateway_name or "PAPER",
            symbol=symbol,
            exchange=Exchange(exchange_str),
            orderid=orderid,
            type=OrderType.LIMIT,
            direction=direction,
            offset=offset,
            price=round(price, 4),
            volume=volume,
            traded=0,
            status=Status.SUBMITTING,
            datetime=datetime.now()
        )

        self.active_orders[order.vt_orderid] = order

        # 本地撮合
        return self._match_paper_order(order, vt_symbol)

    def _match_paper_order(self, order: OrderData, vt_symbol: str) -> list[str]:
        """模拟盘本地撮合逻辑"""
        direction = order.direction
        volume = order.volume
        price = order.price

        # 检查资金/持仓是否足够
        if direction == Direction.LONG:
            # 买入检查资金
            required_cash = price * volume * self.sizes.get(vt_symbol, 1)
            if required_cash > self.cash:
                logger.warning(f"[模拟盘] 资金不足，无法买入 {vt_symbol}，需要 {required_cash:,.2f}，"
                              f"可用 {self.cash:,.2f}")
                order.status = Status.REJECTED
                return []
        else:
            # 卖出检查持仓
            pos = self.paper_positions.get(vt_symbol)
            available_volume = pos['volume'] if pos and pos['direction'] == Direction.LONG else 0
            if available_volume < volume:
                logger.warning(f"[模拟盘] 持仓不足，无法卖出 {vt_symbol}，需要 {volume}，"
                              f"可用 {available_volume}")
                order.status = Status.REJECTED
                return []

        # 模拟撮合：立即以当前最新价格成交
        tick = self.ticks.get(vt_symbol)
        if tick:
            symbol, exchange_str = vt_symbol.split(".")

            # 使用最新价成交
            fill_price = tick.last_price
            fill_volume = volume

            # 更新订单状态为已成交
            order.traded = fill_volume
            order.status = Status.ALLTRADED
            order.datetime = datetime.now()
            self.active_orders.pop(order.vt_orderid, None)

            # 创建成交记录
            self.trade_count += 1
            trade = TradeData(
                symbol=symbol,
                exchange=Exchange(exchange_str),
                gateway_name=self.gateway_name or "PAPER",
                orderid=order.orderid,
                tradeid=str(self.trade_count),
                vt_orderid=order.vt_orderid,
                vt_tradeid=f"{self.gateway_name or 'PAPER'}.{self.trade_count:08d}",
                direction=direction,
                offset=order.offset,
                price=fill_price,
                volume=fill_volume,
                datetime=datetime.now()
            )

            # 更新资金和持仓
            self._update_paper_account(trade)

            # 通知策略成交
            if self.strategy:
                self.strategy.update_trade(trade)
                self.strategy.on_trade(trade)

            logger.info(f"[模拟盘] 成交: {vt_symbol}, {direction.value}, "
                       f"价格: {fill_price}, 数量: {fill_volume}")

            return [order.vt_orderid]
        else:
            # 没有行情，无法撮合
            logger.warning(f"[模拟盘] 无行情数据，无法撮合 {vt_symbol}")
            order.status = Status.REJECTED
            return []

    def _live_send_order(
        self,
        vt_symbol: str,
        direction: Direction,
        offset: Offset,
        price: float,
        volume: float
    ) -> list[str]:
        """实盘发送订单到交易所"""
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
            logger.info(f"[实盘] 下单成功: {vt_symbol}, {direction.value}, "
                       f"{offset.value}, 价格: {price}, 数量: {volume}, 订单号: {vt_orderid}")
            return [vt_orderid]
        else:
            logger.error(f"[实盘] 下单失败: {vt_symbol}")
            return []

    def _update_paper_account(self, trade: TradeData) -> None:
        """更新模拟盘账户"""
        vt_symbol = f"{trade.symbol}.{trade.exchange.value}"
        size = self.sizes.get(vt_symbol, 1)
        amount = trade.price * trade.volume * size
        commission_rate = self.long_rates.get(vt_symbol, 0.0005) if trade.direction == Direction.LONG else self.short_rates.get(vt_symbol, 0.0015)
        commission = max(amount * commission_rate, 5)  # 最低5元手续费

        if trade.direction == Direction.LONG:
            # 买入：扣现金，加持仓
            total_cost = amount + commission
            self.cash -= total_cost

            # 更新持仓
            if vt_symbol not in self.paper_positions:
                self.paper_positions[vt_symbol] = {
                    'volume': 0,
                    'price': 0,
                    'direction': Direction.LONG
                }

            pos = self.paper_positions[vt_symbol]
            # 计算平均成本
            total_volume = pos['volume'] + trade.volume
            if total_volume > 0:
                pos['price'] = (pos['price'] * pos['volume'] + trade.price * trade.volume) / total_volume
            pos['volume'] = total_volume

            self.paper_trades.append(trade)

        else:
            # 卖出：加现金，减持仓
            self.cash += amount - commission

            # 更新持仓
            pos = self.paper_positions.get(vt_symbol)
            if pos:
                pos['volume'] -= trade.volume
                if pos['volume'] <= 0:
                    del self.paper_positions[vt_symbol]

            self.paper_trades.append(trade)

        # 更新账户对象
        if self.account:
            holding_value = sum(
                pos['volume'] * (self.ticks.get(sym).last_price if self.ticks.get(sym) else pos['price'])
                for sym, pos in self.paper_positions.items()
            )
            self.account.balance = self.cash + holding_value
            self.account.available = self.cash

    def cancel_order(self, strategy: AlphaStrategy, vt_orderid: str) -> None:
        """撤单"""
        if self.paper_trading:
            # 模拟盘：直接移除订单
            order = self.active_orders.pop(vt_orderid, None)
            if order:
                order.status = Status.CANCELLED
                logger.info(f"[模拟盘] 撤单成功: {vt_orderid}")
        else:
            # 实盘：发送到交易所
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
        """查询账户"""
        if not self.paper_trading:
            gateway = self.main_engine.get_gateway(self.gateway_name)
            if gateway:
                gateway.query_account()

    def query_positions(self) -> None:
        """查询持仓"""
        if not self.paper_trading:
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
        source = strategy.strategy_name if strategy else "LiveAlphaEngine"
        logger.info(f"[{source}] {msg}")

    def get_pos(self, vt_symbol: str) -> float:
        """获取持仓"""
        if self.paper_trading and hasattr(self, 'paper_positions'):
            # 模拟盘：从 paper_positions 获取
            pos = self.paper_positions.get(vt_symbol)
            if pos:
                return pos['volume'] if pos['direction'] == Direction.LONG else -pos['volume']
            return 0.0
        else:
            # 实盘：从券商持仓获取
            position = self.positions.get(vt_symbol)
            if not position:
                return 0.0
            if position.direction == Direction.LONG:
                return position.volume
            else:
                return -position.volume
