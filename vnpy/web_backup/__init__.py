"""VNPY Web 交易看板模块

提供类似 freqUI 的网页交易界面，支持实时数据展示和策略控制。

使用示例:
    from vnpy.web import WebEngine
    from vnpy.trader.engine import MainEngine
    from vnpy.event import EventEngine

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    # 添加 Web 引擎
    web_engine = main_engine.add_engine(WebEngine)

    # 启动 Web 服务（阻塞模式）
    web_engine.start(host="0.0.0.0", port=8000)

    # 或使用异步模式
    import asyncio
    asyncio.run(web_engine.start_server(host="0.0.0.0", port=8000))
"""

from .engine import WebEngine
from .templates import (
    DashboardData,
    StrategyStatus,
    PositionView,
    TradeView,
    SignalView,
    AccountData
)

__all__ = [
    "WebEngine",
    "DashboardData",
    "StrategyStatus",
    "PositionView",
    "TradeView",
    "SignalView",
    "AccountData"
]

__version__ = "1.0.0"
