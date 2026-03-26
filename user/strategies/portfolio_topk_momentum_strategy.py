from __future__ import annotations

from typing import Dict

import numpy as np

from vnpy.trader.constant import Direction, Interval
from vnpy.trader.object import BarData, TickData
from vnpy.trader.utility import ArrayManager

from vnpy_portfoliostrategy import StrategyTemplate
from vnpy_portfoliostrategy.utility import PortfolioBarGenerator


class PortfolioTopkMomentumStrategy(StrategyTemplate):
    """
    Cross-sectional stock selection strategy (demo, long-only).

    Logic (each bar slice):
    - Compute momentum = close[t] / close[t-lookback] - 1 for each symbol
    - Rank by momentum, select top_k symbols
    - Hold +fixed_size for selected symbols, 0 for others
    - Rebalance via StrategyTemplate.rebalance_portfolio
    """

    author = "chatgpt-demo"

    # Parameters
    lookback: int = 20
    top_k: int = 5
    fixed_size: int = 1
    price_add: float = 0.0
    history_days: int = 60

    parameters = [
        "lookback",
        "top_k",
        "fixed_size",
        "price_add",
        "history_days",
    ]

    # Variables shown in UI must be basic types
    last_topk: str = ""
    variables = [
        "last_topk",
    ]

    def __init__(
        self,
        strategy_engine,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict,
    ) -> None:
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)
    
        # Need enough bars for momentum lookback.
        warmup = max(self.lookback + 5, 30)
        self.ams: Dict[str, ArrayManager] = {s: ArrayManager(size=warmup) for s in self.vt_symbols}

        self.pbg = PortfolioBarGenerator(self.on_bars)

    def on_init(self) -> None:
        self.write_log("策略初始化")
        self.load_bars(self.history_days, Interval.MINUTE)
        self.inited = True

    def on_start(self) -> None:
        self.write_log("策略启动")

    def on_stop(self) -> None:
        self.write_log("策略停止")

    def on_tick(self, tick: TickData) -> None:
        self.pbg.update_tick(tick)

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        # Update AM with latest bars
        for vt_symbol, bar in bars.items():
            self.ams[vt_symbol].update_bar(bar)

        # Require warmup for involved symbols
        for vt_symbol in bars.keys():
            if not self.ams[vt_symbol].inited:
                return

        # Compute momentum for symbols in this slice
        momentum: dict[str, float] = {}
        for vt_symbol in bars.keys():
            am = self.ams[vt_symbol]
            close_array = am.close

            # Guard against invalid data
            close_now = float(close_array[-1])
            close_prev = float(close_array[-1 - self.lookback])
            if not close_now or not close_prev:
                continue
            if np.isnan(close_now) or np.isnan(close_prev):
                continue

            momentum[vt_symbol] = close_now / close_prev - 1

        if not momentum:
            return

        # Select top-k by momentum (descending)
        ranked = sorted(momentum.items(), key=lambda kv: kv[1], reverse=True)
        selected = [vt_symbol for vt_symbol, _ in ranked[: max(1, self.top_k)]]
        selected_set = set(selected)

        self.last_topk = ",".join(selected)

        # Update targets for all symbols that appear in this slice
        for vt_symbol in bars.keys():
            if vt_symbol in selected_set:
                self.set_target(vt_symbol, self.fixed_size)
            else:
                self.set_target(vt_symbol, 0)

        # Execute rebalancing
        self.rebalance_portfolio(bars)
        self.put_event()

    def calculate_price(self, vt_symbol: str, direction: Direction, reference: float) -> float:
        if direction == Direction.LONG:
            return reference + self.price_add
        return reference - self.price_add

