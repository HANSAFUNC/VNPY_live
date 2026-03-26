from collections import defaultdict
from typing import Dict

from vnpy.trader.constant import Direction, Interval
from vnpy.trader.object import BarData, TickData
from vnpy.trader.utility import ArrayManager

from vnpy_portfoliostrategy import StrategyTemplate
from vnpy_portfoliostrategy.utility import PortfolioBarGenerator


class PortfolioSmaCrossStrategy(StrategyTemplate):
    """
    Portfolio SMA cross strategy (demo).

    fast_sma > slow_sma -> target = +fixed_size
    fast_sma < slow_sma -> target = -fixed_size
    equal -> target = 0
    """

    author = "chatgpt-demo"

    # Parameters (must be int/float/bool/str)
    fast_window: int = 10
    slow_window: int = 30
    fixed_size: int = 1
    price_add: float = 0.0
    history_days: int = 60

    parameters = [
        "fast_window",
        "slow_window",
        "fixed_size",
        "price_add",
        "history_days",
    ]
    variables = []

    def __init__(
        self,
        strategy_engine,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict,
    ) -> None:
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        warmup = max(self.fast_window, self.slow_window) + 5
        self.ams: Dict[str, ArrayManager] = {s: ArrayManager(size=warmup) for s in self.vt_symbols}

        self.fast_sma: Dict[str, float] = {}
        self.slow_sma: Dict[str, float] = {}

        # Real-time: Tick -> pbg -> on_bars
        self.pbg = PortfolioBarGenerator(self.on_bars)

        # Optional: keep some runtime stats per symbol (not shown in UI)
        self.last_signal: Dict[str, int] = defaultdict(int)

    def on_init(self) -> None:
        self.write_log("策略初始化")
        self.load_bars(self.history_days, Interval.MINUTE)

    def on_start(self) -> None:
        self.write_log("策略启动")

    def on_stop(self) -> None:
        self.write_log("策略停止")

    def on_tick(self, tick: TickData) -> None:
        # Feed ticks to bar generator; it will trigger on_bars.
        self.pbg.update_tick(tick)

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        # Update ArrayManager for each symbol in this slice
        for vt_symbol, bar in bars.items():
            self.ams[vt_symbol].update_bar(bar)

        # Require warmup completion for all symbols involved in this slice
        for vt_symbol in bars.keys():
            if not self.ams[vt_symbol].inited:
                return

        # Compute target net position based on SMA cross
        for vt_symbol in bars.keys():
            am = self.ams[vt_symbol]
            fast = am.sma(self.fast_window)
            slow = am.sma(self.slow_window)
            self.fast_sma[vt_symbol] = fast
            self.slow_sma[vt_symbol] = slow

            if fast > slow:
                target = self.fixed_size
            elif fast < slow:
                target = -self.fixed_size
            else:
                target = 0

            self.last_signal[vt_symbol] = target
            self.set_target(vt_symbol, target)

        # Let the engine handle cancel/rebalance orders.
        self.rebalance_portfolio(bars)
        self.put_event()

    def calculate_price(self, vt_symbol: str, direction: Direction, reference: float) -> float:
        # Override if you want price offset control.
        # For real trading, reference is usually bar.close_price.
        if direction == Direction.LONG:
            return reference + self.price_add
        return reference - self.price_add

