"""
Alpha策略RPC服务端

完整的交易服务器，支持：
- RPC远程连接
- Alpha策略执行
- Web数据推送

在交易服务器运行，客户端通过RPC/Web远程监控。
"""
import signal
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.alpha.logger import logger
from vnpy_rpcservice import RpcServer

# 配置
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

SETTINGS["datafeed.name"] = "xt"
SETTINGS["datafeed.username"] = "client"
SETTINGS["datafeed.password"] = ""

RPC_REP_ADDRESS = "tcp://*:2014"
RPC_PUB_ADDRESS = "tcp://*:2015"


class AlphaRpcServer:
    """Alpha策略RPC服务端"""

    def __init__(self):
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.rpc_server = None
        self.live_engine = None

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理"""
        logger.info("\n接收到退出信号，正在停止...")
        self.stop()
        sys.exit(0)

    def start_rpc(self):
        """启动RPC服务"""
        self.rpc_server = RpcServer(self.main_engine, self.event_engine)
        self.rpc_server.start(
            rep_address=RPC_REP_ADDRESS,
            pub_address=RPC_PUB_ADDRESS
        )

        logger.info("=" * 60)
        logger.info("Alpha策略RPC服务端已启动")
        logger.info("=" * 60)
        logger.info(f"请求地址: {RPC_REP_ADDRESS}")
        logger.info(f"推送地址: {RPC_PUB_ADDRESS}")
        logger.info("=" * 60)

    def connect_gateway(self, gateway_name: str = "XT", account: str = ""):
        """连接交易网关"""
        try:
            if gateway_name == "XT":
                from vnpy_xt import XtGateway
                self.main_engine.add_gateway(XtGateway, gateway_name)

                if account:
                    setting = {"账号类型": "股票账号", "账号": account}
                    self.main_engine.connect(setting, gateway_name)
                    logger.info(f"已连接网关: {gateway_name}")
                    return True

        except Exception as e:
            logger.error(f"连接网关失败: {e}")
            return False

    def run(self):
        """运行服务端"""
        logger.info("=" * 60)
        logger.info("启动Alpha策略RPC服务端")
        logger.info(f"时间: {datetime.now()}")
        logger.info("=" * 60)

        self.start_rpc()

        logger.info("\n服务端运行中，按Ctrl+C停止")
        logger.info("=" * 60)

        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """停止服务"""
        logger.info("\n正在停止服务...")
        if self.live_engine:
            self.live_engine.stop_trading()
        if self.rpc_server:
            self.rpc_server.stop()
        self.main_engine.close()
        logger.info("服务已停止")


def main():
    import argparse

    parser = argparse.ArgumentParser(description='Alpha策略RPC服务端')
    parser.add_argument('--rep', default=RPC_REP_ADDRESS, help='请求地址')
    parser.add_argument('--pub', default=RPC_PUB_ADDRESS, help='推送地址')
    parser.add_argument('--gateway', default='XT', help='网关名称')
    parser.add_argument('--account', default='', help='交易账号')

    args = parser.parse_args()

    global RPC_REP_ADDRESS, RPC_PUB_ADDRESS
    RPC_REP_ADDRESS = args.rep
    RPC_PUB_ADDRESS = args.pub

    server = AlphaRpcServer()
    if args.account:
        server.connect_gateway(args.gateway, args.account)
    server.run()


if __name__ == "__main__":
    main()
