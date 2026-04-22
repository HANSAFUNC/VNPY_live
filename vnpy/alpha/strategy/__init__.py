from .template import AlphaStrategy
from .backtesting import BacktestingEngine
from .live_engine import TradeEngine

# 向后兼容别名
LiveAlphaEngine = TradeEngine

__all__ = [
    "AlphaStrategy",
    "BacktestingEngine",
    "TradeEngine",
    "LiveAlphaEngine",  # 向后兼容
]
