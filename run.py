from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.ui import MainWindow, create_qapp
# from vnpy_ctabacktester import CtaBacktesterApp
# from vnpy_datamanager import DataManagerApp
# from vnpy_datarecorder import DataRecorderApp
# from vnpy_paperaccount import PaperAccountApp
from vnpy_portfoliostrategy import PortfolioStrategyApp, StrategyEngine
# from vnpy_riskmanager import RiskManagerApp
# from vnpy_chartwizard import ChartWizardApp
# from vnpy_scripttrader import ScriptTraderApp
# from vnpy_rpcservice import RpcGateway
# from vnpy_ctastrategy import CtaStrategyApp
# from vnpy_algotrading import AlgoTradingApp
# from vnpy_webtrader import WebTraderApp
# from vnpy_rpcservice import RpcServiceApp
# from vnpy_okx import (
#     OkxGateway,
#     OkxDemoGateway
# )

from logging import INFO
import time
from vnpy.trader.setting import SETTINGS
SETTINGS["log.active"] = True
SETTINGS["log.level"] = INFO
SETTINGS["log.file"] = False
SETTINGS["log.console"] = True

SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "guojiantao"
SETTINGS["database.password"] = "123456"

def main():
    """"""
    qapp = create_qapp()

    event_engine = EventEngine()

    main_engine = MainEngine(event_engine)
    # main_engine.add_gateway(OkxGateway)
    # main_engine.add_gateway(OkxDemoGateway)
    # main_engine.add_app(CtaStrategyApp)
    # main_engine.add_app(CtaBacktesterApp)
    # main_engine.add_app(ChartWizardApp)
    portfolio_engine:StrategyEngine = main_engine.add_app(PortfolioStrategyApp)

    # main_engine.add_app(DataManagerApp)
    # main_engine.add_app(DataRecorderApp)
    # main_engine.add_app(PaperAccountApp)

    # 创建策略实例参数
    strategy_name = "PortfolioTopkMomentumStrategy"
    vt_symbols = "rb2410.SHFE,i2409.DCE"  # 合约品种格式：vt_symbol用逗号分隔
    strategy_class_name = "PortfolioTopkMomentumStrategy"

    setting = {
        "fixed_size": 1,
        "boll_window": 20,
        "boll_dev": 2.0  # 注意：浮点数参数要设为浮点数默认值
    }
    portfolio_engine.init_engine()
    vt_symbols_list = [s.strip() for s in vt_symbols.split(",") if s.strip()]
    portfolio_engine.add_strategy(
        strategy_class_name,
        strategy_name,
        vt_symbols_list,
        setting
    )

    portfolio_engine.init_strategy(strategy_name)
    # init_strategy 在内部使用线程池异步执行，避免刚 init 就 start 导致启动失败
    deadline = time.time() + 10
    while time.time() < deadline:
        s = portfolio_engine.strategies.get(strategy_name)
        if s and s.inited:
            break
        time.sleep(0.1)
    # 启动策略
    portfolio_engine.start_strategy(strategy_name)
    # main_engine.add_app(RiskManagerApp)
    # main_engine.add_app(ScriptTraderApp)

    # main_engine.add_app(RpcServiceApp)
    # main_engine.add_app(WebTraderApp)
    # main_engine.add_gateway(RpcGateway)

    # main_engine.add_app(AlgoTradingApp)

    main_window = MainWindow(main_engine, event_engine)
    main_window.showMaximized()

    qapp.exec()


if __name__ == "__main__":
    main()
