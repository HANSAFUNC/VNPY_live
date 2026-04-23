"""测试 EventEngine 事件流"""
import asyncio
from datetime import datetime
from vnpy.event import Event, EventEngine
from vnpy.trader.object import AccountData
from vnpy.trader.constant import Exchange


def test_event_flow():
    """测试事件流"""
    print("=" * 60)
    print("测试 EventEngine 事件流")
    print("=" * 60)

    # 创建 EventEngine
    event_engine = EventEngine()
    event_engine.start()

    # 测试事件计数
    event_count = {}

    def on_test_event(event):
        event_count[event.type] = event_count.get(event.type, 0) + 1
        print(f"收到事件: {event.type}, 数据: {event.data}")

    # 注册处理器
    event_engine.register("eTest", on_test_event)
    event_engine.register_general(on_test_event)

    # 发送测试事件
    account = AccountData(
        gateway_name="TEST",
        accountid="test_account",
        balance=1000000.0,
        available=950000.0,
        frozen=50000.0
    )

    event = Event("eAccount", account)
    event_engine.put(event)

    # 等待事件处理
    import time
    time.sleep(0.5)

    print()
    print("=" * 60)
    print("事件统计:")
    print("=" * 60)
    for event_type, count in event_count.items():
        print(f"  {event_type}: {count} 次")

    if not event_count:
        print("  未收到任何事件!")
    else:
        print("  EventEngine 工作正常!")

    event_engine.stop()


if __name__ == "__main__":
    test_event_flow()
