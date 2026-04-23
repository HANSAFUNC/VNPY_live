"""
VNPY Web 交易看板启动示例

此脚本演示如何启动 Web 看板，并与 MainEngine 集成。
"""
import asyncio
import sys
from pathlib import Path

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS
from vnpy.alpha.logger import logger

# 配置数据库和数据服务
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

# 导入 Web 引擎
try:
    from vnpy.web import WebEngine
except ImportError:
    logger.info("错误：无法导入 WebEngine，请确保已安装依赖：")
    logger.info("  pip install fastapi uvicorn websockets")
    sys.exit(1)


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("VNPY Web 交易看板")
    logger.info("=" * 60)

    # 创建事件引擎
    event_engine = EventEngine()

    # 创建主引擎
    main_engine = MainEngine(event_engine)

    # 添加 Web 引擎 - add_engine 返回引擎实例
    web_engine = main_engine.add_engine(WebEngine)

    logger.info("\nWeb 看板引擎已添加")
    logger.info("访问地址: http://localhost:8000")
    logger.info("按 Ctrl+C 停止服务")
    logger.info("=" * 60)

    try:
        # 启动 Web 服务（阻塞模式）
        web_engine.start(host="0.0.0.0", port=8000)
    except KeyboardInterrupt:
        logger.info("\n\n正在停止服务...")
    finally:
        main_engine.close()
        logger.info("服务已停止")


async def async_main():
    """异步模式启动"""
    logger.info("=" * 60)
    logger.info("VNPY Web 交易看板 (异步模式)")
    logger.info("=" * 60)

    event_engine = EventEngine()
    # 不要在这里调用 event_engine.start()
    # MainEngine 会自动启动

    main_engine = MainEngine(event_engine)
    web_engine = main_engine.add_engine(WebEngine)

    logger.info("\nWeb 看板引擎已添加")
    logger.info("访问地址: http://localhost:8000")
    logger.info("=" * 60)

    # 启动 Web 服务
    await web_engine.start_server(host="0.0.0.0", port=8000)

    # 服务停止后清理
    main_engine.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description='VNPY Web 交易看板')
    parser.add_argument('--host', default='0.0.0.0', help='监听地址')
    parser.add_argument('--port', type=int, default=8000, help='监听端口')
    parser.add_argument('--async-mode', action='store_true', help='使用异步模式')

    args = parser.parse_args()

    if args.async_mode:
        asyncio.run(async_main())
    else:
        # 修改启动参数
        from vnpy.web.engine import WebEngine
        original_start = WebEngine.start

        def start_with_args(self, host=None, port=None):
            import uvicorn
            host = host or args.host
            port = port or args.port
            logger.info(f"启动 Web 服务: http://{host}:{port}")
            uvicorn.run(self.app, host=host, port=port)

        WebEngine.start = start_with_args
        main()
