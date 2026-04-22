"""数据管理器 - 接收 RPC 推送事件并管理数据"""
import asyncio
from typing import Dict, List, Optional, Any
import zmq
import zmq.asyncio


class DataManager:
    """数据管理器

    通过 ZeroMQ SUB 订阅 RpcServer 的事件推送，
    维护账户、持仓、成交、订单、行情等数据。
    """

    def __init__(self, sub_address: str = "tcp://localhost:2015"):
        self.sub_address = sub_address
        self.context: Optional[zmq.asyncio.Context] = None
        self.socket: Optional[zmq.asyncio.Socket] = None
        self._running = False

        # 数据存储
        self.account: Optional[Dict] = None
        self.positions: Dict[str, Dict] = {}
        self.trades: List[Dict] = []
        self.orders: Dict[str, Dict] = {}
        self.ticks: Dict[str, Dict] = {}

        # WebSocket 连接列表
        self.websockets: List[Any] = []

    async def start(self):
        """启动 ZMQ 订阅"""
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.SUB)
        self.socket.connect(self.sub_address)
        self.socket.setsockopt_string(zmq.SUBSCRIBE, "")
        self._running = True
        print(f"[DataManager] 已连接到 {self.sub_address}")
        asyncio.create_task(self._receive_loop())

    async def stop(self):
        """停止 ZMQ 订阅"""
        self._running = False
        if self.socket:
            self.socket.close()
        if self.context:
            self.context.term()

    async def _receive_loop(self):
        """接收事件循环"""
        while self._running:
            try:
                if self.socket:
                    # RpcServer 使用 send_pyobj (pickle 序列化)
                    topic, event_data = await self.socket.recv_pyobj()
                    await self._process_event(event_data)
            except Exception as e:
                print(f"[DataManager] 接收错误: {e}")
                await asyncio.sleep(1)

    async def _process_event(self, event):
        """处理接收到的事件

        RpcEngine 发送的是 vnpy.event.Event 对象
        """
        event_type = event.type
        data = event.data

        if not event_type or not data:
            return

        # 忽略定时器和日志事件
        if event_type in ("eTimer", "eRpcLog"):
            return

        if event_type == "eAccount":
            self.account = self._format_account(data)
            await self._broadcast({"type": "account", "data": self.account})
        elif event_type == "ePosition":
            position = self._format_position(data)
            self.positions[position["vt_symbol"]] = position
            await self._broadcast({"type": "position", "data": position})
        elif event_type == "eTrade":
            trade = self._format_trade(data)
            self.trades.insert(0, trade)
            if len(self.trades) > 100:
                self.trades = self.trades[:100]
            await self._broadcast({"type": "trade", "data": trade})
        elif event_type == "eOrder":
            order = self._format_order(data)
            self.orders[order["vt_orderid"]] = order
            await self._broadcast({"type": "order", "data": order})
        elif event_type == "eTick":
            tick = self._format_tick(data)
            self.ticks[tick["vt_symbol"]] = tick
            await self._broadcast({"type": "tick", "data": tick})

    def _format_account(self, data) -> Dict:
        """格式化账户数据"""
        # data 可能是 AccountData 对象或字典
        if hasattr(data, '__dict__'):
            return {
                "balance": getattr(data, 'balance', 0),
                "available": getattr(data, 'available', 0),
                "frozen": getattr(data, 'frozen', 0),
                "gateway_name": getattr(data, 'gateway_name', ''),
            }
        return {"balance": data.get("balance", 0), "available": data.get("available", 0), "frozen": data.get("frozen", 0)}

    def _format_position(self, data) -> Dict:
        """格式化持仓数据"""
        if hasattr(data, '__dict__'):
            return {
                "vt_symbol": getattr(data, 'vt_symbol', ''),
                "direction": str(getattr(data, 'direction', '')),
                "volume": getattr(data, 'volume', 0),
                "price": getattr(data, 'price', 0),
                "pnl": getattr(data, 'pnl', 0),
                "gateway_name": getattr(data, 'gateway_name', ''),
            }
        return {"vt_symbol": data.get("vt_symbol", ""), "volume": data.get("volume", 0)}

    def _format_trade(self, data) -> Dict:
        """格式化成交数据"""
        if hasattr(data, '__dict__'):
            return {
                "vt_symbol": getattr(data, 'vt_symbol', ''),
                "direction": str(getattr(data, 'direction', '')),
                "price": getattr(data, 'price', 0),
                "volume": getattr(data, 'volume', 0),
                "time": getattr(data, 'time', ''),
                "gateway_name": getattr(data, 'gateway_name', ''),
            }
        return {"vt_symbol": data.get("vt_symbol", ""), "price": data.get("price", 0)}

    def _format_order(self, data) -> Dict:
        """格式化订单数据"""
        if hasattr(data, '__dict__'):
            return {
                "vt_orderid": getattr(data, 'vt_orderid', ''),
                "vt_symbol": getattr(data, 'vt_symbol', ''),
                "direction": str(getattr(data, 'direction', '')),
                "price": getattr(data, 'price', 0),
                "volume": getattr(data, 'volume', 0),
                "traded": getattr(data, 'traded', 0),
                "status": str(getattr(data, 'status', '')),
            }
        return {"vt_orderid": data.get("vt_orderid", ""), "vt_symbol": data.get("vt_symbol", "")}

    def _format_tick(self, data) -> Dict:
        """格式化行情数据"""
        if hasattr(data, '__dict__'):
            return {
                "vt_symbol": getattr(data, 'vt_symbol', ''),
                "last_price": getattr(data, 'last_price', 0),
                "volume": getattr(data, 'volume', 0),
                "open_price": getattr(data, 'open_price', 0),
                "high_price": getattr(data, 'high_price', 0),
                "low_price": getattr(data, 'low_price', 0),
                "datetime": str(getattr(data, 'datetime', '')),
            }
        return {"vt_symbol": data.get("vt_symbol", ""), "last_price": data.get("last_price", 0)}

    async def _broadcast(self, message: Dict):
        for ws in self.websockets[:]:
            try:
                await ws.send_json(message)
            except Exception:
                self.websockets.remove(ws)

    def register_websocket(self, ws):
        self.websockets.append(ws)

    def unregister_websocket(self, ws):
        if ws in self.websockets:
            self.websockets.remove(ws)
