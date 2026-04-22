"""
Web看板 RPC模式启动脚本

通过RPC连接远程交易服务器，启动本地Web看板。

使用方式：
    python web_dashboard_rpc.py --rpc-host 192.168.1.100 --port 8080
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.alpha.logger import logger

# 默认数据库配置
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

DEFAULT_RPC_REQ = "tcp://localhost:2014"
DEFAULT_RPC_SUB = "tcp://localhost:2015"


class RpcWebDashboard:
    """RPC模式Web看板管理器"""

    def __init__(
        self,
        rpc_req: str = DEFAULT_RPC_REQ,
        rpc_sub: str = DEFAULT_RPC_SUB,
        host: str = "0.0.0.0",
        port: int = 8000
    ):
        self.rpc_req = rpc_req
        self.rpc_sub = rpc_sub
        self.host = host
        self.port = port

        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.rpc_engine = None

    def start(self) -> None:
        """启动Web看板"""
        logger.info("=" * 60)
        logger.info("Web看板 RPC模式")
        logger.info("=" * 60)
        logger.info(f"RPC地址: {self.rpc_req}")
        logger.info(f"Web地址: http://{self.host}:{self.port}")
        logger.info("=" * 60)

        try:
            from vnpy.web import RpcWebEngine

            # 创建RPC引擎
            self.rpc_engine = RpcWebEngine(
                main_engine=self.main_engine,
                event_engine=self.event_engine,
                req_address=self.rpc_req,
                sub_address=self.rpc_sub
            )

            # 连接RPC
            if not self.rpc_engine.connect_rpc():
                logger.error("RPC连接失败，退出")
                sys.exit(1)

            # 启动Web服务
            self.rpc_engine.start(host=self.host, port=self.port)

        except ImportError as e:
            logger.error(f"导入失败: {e}")
            logger.error("请确保已安装: pip install vnpy_rpcservice fastapi uvicorn")
            sys.exit(1)

    def stop(self):
        """停止服务"""
        if self.rpc_engine:
            self.rpc_engine.disconnect_rpc()
        self.main_engine.close()
        logger.info("服务已停止")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Web看板 RPC模式')
    parser.add_argument('--rpc-req', default=DEFAULT_RPC_REQ,
                       help='RPC请求地址 (默认: tcp://localhost:2014)')
    parser.add_argument('--rpc-sub', default=DEFAULT_RPC_SUB,
                       help='RPC推送地址 (默认: tcp://localhost:2015)')
    parser.add_argument('--host', default='0.0.0.0', help='Web服务监听地址')
    parser.add_argument('--port', type=int, default=8000, help='Web服务监听端口')

    args = parser.parse_args()

    dashboard = RpcWebDashboard(
        rpc_req=args.rpc_req,
        rpc_sub=args.rpc_sub,
        host=args.host,
        port=args.port
    )

    try:
        dashboard.start()
    except KeyboardInterrupt:
        dashboard.stop()


if __name__ == "__main__":
    main()
