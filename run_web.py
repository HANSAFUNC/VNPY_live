"""
独立启动 vnpy_webtrader Web 服务（无需 VNPY GUI）

使用方法:
    python run_web.py

环境变量:
    WEB_USERNAME=admin      # 登录用户名
    WEB_PASSWORD=admin      # 登录密码
    REQ_ADDRESS=tcp://localhost:2014  # RPC 请求地址
    SUB_ADDRESS=tcp://localhost:2015  # RPC 订阅地址
"""
import uvicorn
import json
from pathlib import Path
from vnpy.trader.utility import get_file_path


def ensure_config():
    """确保配置文件存在"""
    config_path = get_file_path("web_trader_setting.json")

    if not config_path.exists() or config_path.stat().st_size == 0:
        # 创建默认配置
        default_config = {
            "username": "admin",
            "password": "admin",
            "req_address": "tcp://localhost:2014",
            "sub_address": "tcp://localhost:2015"
        }
        with open(config_path, 'w') as f:
            json.dump(default_config, f, indent=2)
        print("[INFO] 已创建默认配置: {}".format(config_path))
    else:
        print("[INFO] 使用已有配置: {}".format(config_path))

    return config_path


def main():
    """启动 Web 服务"""
    # 确保配置存在
    config_path = ensure_config()

    # 检查 web_dashboard 是否存在
    dashboard_path = Path(__file__).parent / "web_dashboard/static/index.html"
    if dashboard_path.exists():
        print("[INFO] 检测到 web_dashboard，将自动使用 Vue3 看板")
    else:
        print("[INFO] 未检测到 web_dashboard，使用内置看板")

    # 读取配置显示
    with open(config_path) as f:
        config = json.load(f)

    print("=" * 50)
    print("VNPY WebTrader 启动中...")
    print("=" * 50)
    print("访问地址: http://localhost:8000")
    print("API 文档: http://localhost:8000/docs")
    print("RPC 请求: {}".format(config['req_address']))
    print("RPC 订阅: {}".format(config['sub_address']))
    print("登录用户: {}".format(config['username']))
    print("=" * 50)

    # 启动 Uvicorn
    uvicorn.run(
        "vnpy_webtrader.web:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        log_level="info"
    )


if __name__ == "__main__":
    main()
