"""诊断工具 - 检查 RPC 数据流"""
import asyncio
import zmq
import zmq.asyncio


async def diagnose_rpc(sub_address: str = "tcp://localhost:2015"):
    """诊断 RPC 数据流"""
    print("=" * 60)
    print("RPC 数据流诊断工具")
    print("=" * 60)
    print(f"连接到: {sub_address}")
    print()

    context = zmq.asyncio.Context()
    socket = context.socket(zmq.SUB)
    socket.connect(sub_address)
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    print("已连接，等待数据...")
    print("按 Ctrl+C 停止")
    print()

    event_count = {}

    try:
        while True:
            try:
                topic, event_data = await socket.recv_pyobj()

                # 心跳检测
                if topic == "heartbeat":
                    print(f"[心跳] {event_data}")
                    continue

                # 事件检测
                if hasattr(event_data, 'type'):
                    event_type = event_data.type
                    event_count[event_type] = event_count.get(event_type, 0) + 1
                    print(f"[事件] 类型: {event_type}, 数据类型: {type(event_data.data).__name__}")
                else:
                    print(f"[未知] 数据: {event_data}")

            except Exception as e:
                print(f"[错误] 接收失败: {e}")
                await asyncio.sleep(1)

    except KeyboardInterrupt:
        print()
        print("=" * 60)
        print("诊断结果:")
        print("=" * 60)
        if event_count:
            for event_type, count in sorted(event_count.items()):
                print(f"  {event_type}: {count} 次")
        else:
            print("  未收到任何事件!")
            print()
            print("可能原因:")
            print("  1. VNPY 交易服务未启动或未启用 RPC (--enable-rpc)")
            print("  2. VNPY 交易服务未连接网关")
            print("  3. 网关未产生事件（无行情、无成交等）")

    finally:
        socket.close()
        context.term()


if __name__ == "__main__":
    asyncio.run(diagnose_rpc())
