"""
VNPY RPC 服务端 - 实盘交易服务器

在交易服务器上运行，管理：
1. 交易网关连接（CTP/XT等）
2. Alpha策略执行
3. 数据持久化

远程客户端可以通过 RPC 接口监控和操作。
"""

import signal
import sys
from pathlib import Path

# 添加项目根目录
sys.path.insert(0, str(Path(__file__).parent.parent))

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.alpha.logger import logger

# 配置数据库
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

# RPC 服务地址
RPC_REP_ADDRESS = "tcp://*:2014"  # 接收客户端请求
RPC_PUB_ADDRESS = "tcp://*:2015"  # 向客户端推送数据


class TradingRpcServer:
    """交易 RPC 服务端"""

    def __init__(self):
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.rpc_server = None
        self.live_engine = None

        # 设置信号处理
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """信号处理"""
        logger.info("\n接收到退出信号，正在停止...")
        self.stop()
        sys.exit(0)

    def setup_rpc(self):
        """配置 RPC 服务"""
        from vnpy_rpcservice import RpcServer

        self.rpc_server = RpcServer(self.main_engine, self.event_engine)
        logger.info("RPC 服务已配置")

    def start_rpc(self):
        """启动 RPC 服务"""
        self.rpc_server.start(
            rep_address=RPC_REP_ADDRESS,
            pub_address=RPC_PUB_ADDRESS
        )

        logger.info("=" * 60)
        logger.info("RPC 服务已启动")
        logger.info("=" * 60)
        logger.info(f"请求地址: {RPC_REP_ADDRESS}")
        logger.info(f"推送地址: {RPC_PUB_ADDRESS}")
        logger.info("=" * 60)

    def connect_gateway(self, gateway_name: str, setting: dict):
        """连接交易网关"""
        try:
            if gateway_name == "XT":
                from vnpy_xt import XtGateway
                self.main_engine.add_gateway(XtGateway, gateway_name)

            elif gateway_name == "CTP":
                from vnpy_ctp import CtpGateway
                self.main_engine.add_gateway(CtpGateway, gateway_name)

            else:
                logger.error(f"不支持的网关: {gateway_name}")
                return False

            self.main_engine.connect(setting, gateway_name)
            logger.info(f"已连接网关: {gateway_name}")
            return True

        except ImportError as e:
            logger.error(f"导入网关失败: {e}")
            return False
        except Exception as e:
            logger.error(f"连接网关失败: {e}")
            return False

    def run(self):
        """运行服务端"""
        logger.info("=" * 60)
        logger.info("启动 VNPY 交易 RPC 服务端")
        logger.info("=" * 60)

        # 1. 配置 RPC
        self.setup_rpc()

        # 2. 启动 RPC 服务
        self.start_rpc()

        # 3. 主循环
        logger.info("\n服务端运行中，按 Ctrl+C 停止")
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
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='VNPY RPC 交易服务端')
    parser.add_argument('--rep', default='tcp://*:2014', help='请求响应地址')
    parser.add_argument('--pub', default='tcp://*:2015', help='发布订阅地址')
    parser.add_argument('--gateway', default='XT', help='交易网关')
    parser.add_argument('--account', default='', help='交易账号')

    args = parser.parse_args()

    # 更新配置
    global RPC_REP_ADDRESS, RPC_PUB_ADDRESS
    RPC_REP_ADDRESS = args.rep
    RPC_PUB_ADDRESS = args.pub

    # 创建并运行服务端
    server = TradingRpcServer()

    # 如果使用真实交易，连接网关
    if args.account:
        gateway_setting = {
            "账号类型": "股票账号",
            "账号": args.account
        }
        server.connect_gateway(args.gateway, gateway_setting)

    server.run()


if __name__ == "__main__":
    main()
