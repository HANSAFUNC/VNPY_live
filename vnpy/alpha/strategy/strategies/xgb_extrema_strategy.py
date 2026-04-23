"""XGBoost 极值选股策略

基于 XGBoostExtremaModel 的极值预测信号进行交易：
- 当预测值 > maxima 阈值时，认为是高点，生成卖出信号
- 当预测值 < minima 阈值时，认为是低点，生成买入信号
"""

from collections import defaultdict
from datetime import datetime

import polars as pl

from vnpy.trader.object import BarData, TradeData
from vnpy.trader.constant import Direction
from vnpy.trader.utility import round_to

from vnpy.alpha import AlphaStrategy


class XGBExtremaStrategy(AlphaStrategy):
    """XGBoost 极值选股策略"""

    # 策略参数
    min_days: int = 1               # 最小持有天数
    profit_threshold: float = 0.03  # 盈利阈值（5%）
    cash_ratio: float = 0.95        # 现金利用率
    min_volume: int = 100           # 最小交易单位
    open_rate: float = 0.0005       # 买入费率
    close_rate: float = 0.0015      # 卖出费率
    min_commission: int = 5         # 最低手续费
    price_add: float = 0.0          # 下单价格偏移

    def on_init(self) -> None:
        """策略初始化"""
        self.holding_days: defaultdict = defaultdict(int)
        self.entry_prices: defaultdict = defaultdict(float)  # 记录入场价格

        self.write_log("策略初始化")
        self.write_log(f"最小持有期：{self.min_days}天，盈利阈值：{self.profit_threshold*100}%")

    def on_trade(self, trade: TradeData) -> None:
        """成交回调"""
        if trade.direction == Direction.SHORT:
            # 卖出时清除持仓记录
            self.holding_days.pop(trade.vt_symbol, None)
            self.entry_prices.pop(trade.vt_symbol, None)
            self.write_log(f"卖出平仓：{trade.vt_symbol}, 价格={trade.price}, 数量={trade.volume}")
        else:
            # 买入时记录入场价格
            self.entry_prices[trade.vt_symbol] = trade.price
            self.write_log(f"买入开仓：{trade.vt_symbol}, 价格={trade.price}, 数量={trade.volume}")

    def on_bars(self, bars: dict[str, BarData]) -> None:
        """K 线回调"""
        # 获取最新信号
        last_signal: pl.DataFrame = self.get_signal()
        print(last_signal)
        if last_signal.is_empty():
            return

        # 获取当前持仓
        pos_symbols: list[str] = [vt for vt, pos in self.pos_data.items() if pos]

        # 更新持有天数
        for vt_symbol in pos_symbols:
            self.holding_days[vt_symbol] += 1

        # 买入列表：signal=1 且不在持仓中的
        buy_df = last_signal.filter(
            (pl.col("signal") == 1) &
            (~pl.col("vt_symbol").is_in(pos_symbols))
        )
        buy_symbols: list[str] = buy_df["vt_symbol"].to_list()

        # 卖出列表：signal=-1 且满足持有期和盈利条件
        sell_df = last_signal.filter(pl.col("signal") == -1)
        sell_symbols: set[str] = set()
        for vt_symbol in pos_symbols:
            # 检查最小持有期（少于 3 天跳过）
            if self.holding_days.get(vt_symbol, 0) < self.min_days:
                continue

            if vt_symbol in sell_df["vt_symbol"]:
                sell_symbols.add(vt_symbol)
            else:
                # 检查盈利是否达到阈值
                entry_price = self.entry_prices.get(vt_symbol, 0)
                if entry_price > 0:
                    current_price = bars.get(vt_symbol, None)
                    if current_price:
                        profit_pct = (current_price.close_price - entry_price) / entry_price
                        if profit_pct >= self.profit_threshold:
                            sell_symbols.add(vt_symbol)

        sell_symbols: set[str] = set(pos_symbols).difference(sell_symbols)

        # 执行调仓
        self._execute_rebalance(buy_symbols, sell_symbols, bars)

    def _execute_rebalance(self, buy_symbols: list[str], sell_symbols: set[str], bars: dict[str, BarData]) -> None:
        """执行调仓交易"""
        # 获取可用资金
        cash: float = self.get_cash_available()

        # 先卖出
        for vt_symbol in sell_symbols:
            bar: BarData | None = bars.get(vt_symbol)
            if not bar:
                continue

            sell_price: float = bar.close_price
            sell_volume: float = self.get_pos(vt_symbol)

            self.set_target(vt_symbol, target=0)

            turnover: float = sell_price * sell_volume
            cost: float = max(turnover * self.close_rate, self.min_commission)
            cash += turnover - cost

        # 再买入
        if buy_symbols:
            # 计算每只股票的买入金额
            buy_value: float = cash * self.cash_ratio / len(buy_symbols)

            for vt_symbol in buy_symbols:
                bar: BarData | None = bars.get(vt_symbol)
                if not bar:
                    continue

                buy_price: float = bar.close_price
                if buy_price <= 0:
                    continue

                # 计算买入数量（考虑手续费）
                buy_volume: float = round_to(buy_value / buy_price, self.min_volume)

                if buy_volume > 0:
                    # 计算买入成本（含手续费）
                    turnover: float = buy_price * buy_volume
                    cost: float = max(turnover * self.open_rate, self.min_commission)
                    total_cost: float = turnover + cost

                    # 检查资金是否足够
                    if total_cost <= cash:
                        self.set_target(vt_symbol, buy_volume)
                        cash -= total_cost

        # 执行交易
        self.execute_trading(bars, price_add=self.price_add)

    def on_stop(self) -> None:
        """策略停止回调"""
        self.write_log("策略停止")
        self.write_log(f"最终持仓数：{len([vt for vt, pos in self.pos_data.items() if pos])}")
