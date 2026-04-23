"""
VNPY RPC 服务示例

使用 vnpy_rpcservice 实现分布式交易架构：
- RpcServer: 运行在主服务器上，管理交易引擎和策略
- RpcClient: 运行在客户端，远程操作交易

典型部署场景：
1. 服务端部署在交易服务器（连接交易所）
2. 客户端可以远程监控和管理交易
"""

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS

# 配置数据库
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"


class RpcServerManager:
    """RPC服务端管理器

    在交易服务器上运行，提供远程调用接口
    """

    def __init__(self, rep_address: str = "tcp://*:2014", pub_address: str = "tcp://*:2015"):
        """
        Parameters
        ----------
        rep_address : str
            请求响应地址（客户端发送请求）
        pub_address : str
            发布订阅地址（服务端推送数据）
        """
        self.rep_address = rep_address
        self.pub_address = pub_address

        # 创建引擎
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)

        # RPC服务器
        self.rpc_server = None

    def start(self):
        """启动RPC服务"""
        from vnpy_rpcservice import RpcServer

        # 创建RPC服务器
        self.rpc_server = RpcServer(self.main_engine, self.event_engine)

        # 启动服务
        self.rpc_server.start(
            rep_address=self.rep_address,
            pub_address=self.pub_address
        )

        print("=" * 60)
        print("VNPY RPC 服务已启动")
        print("=" * 60)
        print(f"请求地址: {self.rep_address}")
        print(f"推送地址: {self.pub_address}")
        print("=" * 60)

        # 保持运行
        try:
            while True:
                import time
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def stop(self):
        """停止服务"""
        if self.rpc_server:
            self.rpc_server.stop()
        self.main_engine.close()
        print("\nRPC服务已停止")

    def connect_gateway(self, gateway_name: str, setting: dict):
        """连接交易网关（服务端调用）"""
        if gateway_name == "XT":
            from vnpy_xt import XtGateway
            self.main_engine.add_gateway(XtGateway, gateway_name)
            self.main_engine.connect(setting, gateway_name)
            print(f"已连接网关: {gateway_name}")


class RpcClientManager:
    """RPC客户端管理器

    远程连接到交易服务器，进行操作和监控
    """

    def __init__(self, req_address: str = "tcp://localhost:2014", sub_address: str = "tcp://localhost:2015"):
        """
        Parameters
        ----------
        req_address : str
            服务端请求地址
        sub_address : str
            服务端推送地址
        """
        self.req_address = req_address
        self.sub_address = sub_address

        # 创建引擎
        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)

        # RPC客户端
        self.rpc_client = None

    def connect(self):
        """连接到RPC服务端"""
        from vnpy_rpcservice import RpcClient

        # 创建RPC客户端
        self.rpc_client = RpcClient()

        # 连接服务端
        self.rpc_client.connect(
            req_address=self.req_address,
            sub_address=self.sub_address,
            main_engine=self.main_engine,
            event_engine=self.event_engine
        )

        print("=" * 60)
        print("VNPY RPC 客户端已连接")
        print("=" * 60)
        print(f"请求地址: {self.req_address}")
        print(f"推送地址: {self.sub_address}")
        print("=" * 60)

    def disconnect(self):
        """断开连接"""
        if self.rpc_client:
            self.rpc_client.stop()
        self.main_engine.close()
        print("已断开RPC连接")

    def get_account(self):
        """查询账户"""
        accounts = self.main_engine.get_all_accounts()
        return accounts

    def get_positions(self):
        """查询持仓"""
        positions = self.main_engine.get_all_positions()
        return positions

    def get_orders(self):
        """查询订单"""
        orders = self.main_engine.get_all_orders()
        return orders

    def send_order(self, vt_symbol: str, direction: str, price: float, volume: float):
        """发送订单"""
        from vnpy.trader.constant import Direction, Exchange, OrderType
        from vnpy.trader.object import OrderRequest

        symbol, exchange_str = vt_symbol.split(".")

        req = OrderRequest(
            symbol=symbol,
            exchange=Exchange(exchange_str),
            direction=Direction(direction),
            type=OrderType.LIMIT,
            volume=volume,
            price=price
        )

        # 通过RPC发送到服务端执行
        vt_orderid = self.main_engine.send_order(req, "RPC")
        return vt_orderid

    def cancel_order(self, vt_orderid: str):
        """撤单"""
        from vnpy.trader.object import CancelRequest

        order = self.main_engine.get_order(vt_orderid)
        if not order:
            return False

        req = CancelRequest(
            symbol=order.symbol,
            exchange=order.exchange,
            orderid=order.orderid
        )

        self.main_engine.cancel_order(req, "RPC")
        return True


def run_server():
    """启动RPC服务端"""
    server = RpcServerManager(
        rep_address="tcp://*:2014",
        pub_address="tcp://*:2015"
    )

    # 可以在这里预连接网关
    # server.connect_gateway("XT", {"账号类型": "股票账号", "账号": "your_account"})

    server.start()


def run_client():
    """启动RPC客户端"""
    client = RpcClientManager(
        req_address="tcp://localhost:2014",
        sub_address="tcp://localhost:2015"
    )

    client.connect()

    try:
        # 示例：查询账户和持仓
        print("\n查询账户...")
        accounts = client.get_account()
        for acc in accounts:
            print(f"  账户: {acc.accountid}, 余额: {acc.balance}")

        print("\n查询持仓...")
        positions = client.get_positions()
        for pos in positions:
            print(f"  {pos.vt_symbol}: {pos.volume} @ {pos.price}")

        # 保持连接，接收推送
        print("\n按 Ctrl+C 退出")
        while True:
            import time
            time.sleep(1)

    except KeyboardInterrupt:
        client.disconnect()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='VNPY RPC 服务')
    parser.add_argument('mode', choices=['server', 'client'], help='运行模式')
    parser.add_argument('--rep', default='tcp://*:2014', help='请求地址（服务端）')
    parser.add_argument('--pub', default='tcp://*:2015', help='推送地址（服务端）')
    parser.add_argument('--req', default='tcp://localhost:2014', help='请求地址（客户端）')
    parser.add_argument('--sub', default='tcp://localhost:2015', help='推送地址（客户端）')

    args = parser.parse_args()

    if args.mode == 'server':
        server = RpcServerManager(rep_address=args.rep, pub_address=args.pub)
        print(f"启动RPC服务端...")
        print(f"  REP: {args.rep}")
        print(f"  PUB: {args.pub}")
        server.start()
    else:
        client = RpcClientManager(req_address=args.req, sub_address=args.sub)
        print(f"连接RPC服务端...")
        print(f"  REQ: {args.req}")
        print(f"  SUB: {args.sub}")
        client.connect()
        run_client()
