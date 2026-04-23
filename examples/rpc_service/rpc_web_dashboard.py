"""
Web 看板 + RPC 客户端整合示例

将 Web 看板作为 RPC 客户端运行，可以远程监控交易服务器。

部署架构：
┌─────────────┐      RPC      ┌─────────────┐     ┌─────────┐
│   Web看板    │  ═══════►    │  RPC服务端   │ ──► │ 交易所   │
│  (本脚本)    │   (tcp)      │ (交易服务器) │     └─────────┘
└─────────────┘              └─────────────┘

使用方式：
1. 在交易服务器上运行 rpc_server.py
2. 在本机运行此脚本连接并启动 Web 看板
"""

import asyncio
import sys
from pathlib import Path

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

# RPC 服务端地址（修改为你的交易服务器地址）
RPC_REQ_ADDRESS = "tcp://localhost:2014"  # 服务端 REP 地址
RPC_SUB_ADDRESS = "tcp://localhost:2015"  # 服务端 PUB 地址


class RpcWebDashboard:
    """RPC 客户端模式的 Web 看板"""

    def __init__(self):
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)
        self.rpc_client = None
        self.web_engine = None

    def connect_rpc(self):
        """连接到 RPC 服务端"""
        from vnpy_rpcservice import RpcClient

        logger.info("=" * 60)
        logger.info("连接到 RPC 服务端")
        logger.info("=" * 60)
        logger.info(f"请求地址: {RPC_REQ_ADDRESS}")
        logger.info(f"推送地址: {RPC_SUB_ADDRESS}")

        try:
            self.rpc_client = RpcClient()
            self.rpc_client.connect(
                req_address=RPC_REQ_ADDRESS,
                sub_address=RPC_SUB_ADDRESS,
                main_engine=self.main_engine,
                event_engine=self.event_engine
            )
            logger.info("✓ RPC 连接成功")
            return True
        except Exception as e:
            logger.error(f"✗ RPC 连接失败: {e}")
            return False

    def start_web(self, host: str = "0.0.0.0", port: int = 8000):
        """启动 Web 看板"""
        try:
            from vnpy.web import WebEngine
            self.web_engine = self.main_engine.add_engine(WebEngine)
            logger.info(f"✓ Web 看板已启动: http://{host}:{port}")
            return True
        except Exception as e:
            logger.error(f"✗ Web 看板启动失败: {e}")
            return False

    def run(self, host: str = "0.0.0.0", port: int = 8000):
        """运行 Web 看板"""
        # 1. 连接 RPC
        if not self.connect_rpc():
            logger.error("无法连接到 RPC 服务端，请确保服务端已启动")
            sys.exit(1)

        # 2. 启动 Web 看板
        if not self.start_web(host, port):
            sys.exit(1)

        # 3. 测试查询
        self._test_query()

        # 4. 启动服务
        logger.info("=" * 60)
        logger.info("Web 看板运行中，按 Ctrl+C 停止")
        logger.info("=" * 60)

        try:
            # 使用异步模式启动
            asyncio.run(self._async_run(host, port))
        except KeyboardInterrupt:
            self.stop()

    async def _async_run(self, host: str, port: int):
        """异步运行"""
        from vnpy.web.engine import WebEngine

        web_engine = self.main_engine.get_engine(WebEngine.engine_name)
        if web_engine:
            await web_engine.start_server(host=host, port=port)

    def _test_query(self):
        """测试查询服务端数据"""
        logger.info("\n测试查询服务端数据...")

        # 查询账户
        accounts = self.main_engine.get_all_accounts()
        if accounts:
            for acc in accounts:
                logger.info(f"  账户: {acc.accountid}, 余额: {acc.balance:,.2f}")
        else:
            logger.info("  暂无账户数据")

        # 查询持仓
        positions = self.main_engine.get_all_positions()
        if positions:
            for pos in positions[:5]:  # 只显示前5个
                logger.info(f"  持仓: {pos.vt_symbol}, {pos.volume} 股")
        else:
            logger.info("  暂无持仓数据")

        # 查询订单
        orders = self.main_engine.get_all_orders()
        logger.info(f"  当前订单数: {len(orders)}")

    def stop(self):
        """停止服务"""
        logger.info("\n正在停止 Web 看板...")

        if self.rpc_client:
            self.rpc_client.stop()

        self.main_engine.close()
        logger.info("✓ 已停止")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='Web看板 (RPC客户端模式)')
    parser.add_argument('--host', default='0.0.0.0', help='Web服务监听地址')
    parser.add_argument('--port', type=int, default=8000, help='Web服务监听端口')
    parser.add_argument('--rpc-req', default='tcp://localhost:2014', help='RPC请求地址')
    parser.add_argument('--rpc-sub', default='tcp://localhost:2015', help='RPC推送地址')

    args = parser.parse_args()

    # 更新全局地址
    global RPC_REQ_ADDRESS, RPC_SUB_ADDRESS
    RPC_REQ_ADDRESS = args.rpc_req
    RPC_SUB_ADDRESS = args.rpc_sub

    dashboard = RpcWebDashboard()
    dashboard.run(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
