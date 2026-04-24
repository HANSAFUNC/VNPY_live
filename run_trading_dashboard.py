#!/usr/bin/env python
"""
统一启动交易 + Web 看板

使用方式:
    python run_trading_dashboard.py --mode paper --capital 1000000 --xt-account your_xt_account

参数:
    --mode: 运行模式 (backtest/paper/live)，默认 paper
    --capital: 初始资金，默认 1000000
    --gateway: 交易网关，默认 XT
    --xt-account: 迅投研账号（实盘/模拟盘需要）
    --host: Web服务地址，默认 0.0.0.0
    --port: Web服务端口，默认 8000
"""
import subprocess
import sys
import time
import signal
import argparse
import json
from pathlib import Path

from vnpy.trader.setting import SETTINGS

# 配置数据库和数据服务
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

SETTINGS["datafeed.name"] = "xt"
SETTINGS["datafeed.username"] = "client"
SETTINGS["datafeed.password"] = ""

def ensure_web_config():
    """确保 Web 配置文件存在"""
    from vnpy.trader.utility import get_file_path, save_json, load_json

    config_file = "web_trader_setting.json"
    config_path = get_file_path(config_file)

    setting = load_json(config_file)

    # 如果配置为空或缺少必要字段，创建默认配置
    default_config = {
        "username": "admin",
        "password": "admin",
        "req_address": "tcp://localhost:2014",
        "sub_address": "tcp://localhost:2015"
    }

    # 合并现有配置和默认配置
    for key, value in default_config.items():
        if key not in setting:
            setting[key] = value

    save_json(config_file, setting)
    print(f"✓ Web配置已确认: {config_path}")
    print(f"  登录用户: {setting['username']}")
    print(f"  RPC地址: {setting['req_address']}")

    return setting


class TradingDashboardLauncher:
    """交易 + Web看板统一启动器"""

    def __init__(self):
        self.trader_proc = None
        self.web_proc = None
        self.rpc_ready = False

    def signal_handler(self, signum, frame):
        """信号处理 - 优雅退出"""
        print("\n\n⚠ 接收到退出信号，正在停止服务...")
        self.stop()
        sys.exit(0)

    def wait_for_rpc(self, timeout=30):
        """等待 RPC 服务启动"""
        import socket

        print("等待 RPC 服务启动...")
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                # 检查 RPC 端口 2014 是否可用
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex(('localhost', 2014))
                sock.close()

                if result == 0:
                    print("✓ RPC 服务已就绪")
                    return True
            except Exception:
                pass

            time.sleep(0.5)

        print(f"✗ RPC 服务启动超时 ({timeout}秒)")
        return False

    def start_trading(self, mode, capital, gateway, xt_account):
        """启动交易服务"""
        print("=" * 60)
        print(f"启动交易服务 (模式: {mode})")
        print("=" * 60)

        cmd = [
            sys.executable,
            "xgb_extrema_live_trading.py",
            "--mode", mode,
            "--capital", str(capital),
            "--gateway", gateway,
            "--xt-account", xt_account,
            "--enable-rpc"
        ]

        self.trader_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # 读取输出直到看到 RPC 启动成功或错误
        print("启动交易中...")
        for line in self.trader_proc.stdout:
            print(f"[交易] {line.rstrip()}")
            if "RPC 服务已启动" in line or "tcp://*:2014" in line:
                self.rpc_ready = True
                break
            if "错误" in line or "Error" in line:
                print("✗ 交易启动失败")
                return False

        return self.rpc_ready

    def start_web(self, host, port):
        """启动 Web 看板"""
        print("\n" + "=" * 60)
        print(f"启动 Web 看板 (http://{host}:{port})")
        print("=" * 60)

        # 检查 web_dashboard 是否存在，优先使用它的前端
        web_dashboard_static = Path("web_dashboard/static")
        if web_dashboard_static.exists():
            print("✓ 检测到 web_dashboard，使用 Vue3 看板")

        cmd = [
            sys.executable,
            "-m", "uvicorn",
            "vnpy_webtrader.web:app",
            "--host", host,
            "--port", str(port),
            "--log-level", "info"
        ]

        self.web_proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            universal_newlines=True
        )

        # 等待 Web 服务启动（简单轮询）
        import socket
        start_time = time.time()
        error_output = []

        # 读取输出同时检查服务是否启动
        while time.time() - start_time < 10:
            # 非阻塞读取输出
            import platform
            if platform.system() == 'Windows':
                # Windows: 使用线程读取避免阻塞
                import threading
                def read_output():
                    try:
                        line = self.web_proc.stdout.readline()
                        if line:
                            error_output.append(line.rstrip())
                            print(f"[Web] {line.rstrip()}")
                    except:
                        pass
                t = threading.Thread(target=read_output, daemon=True)
                t.start()
                t.join(timeout=0.5)
            else:
                # Linux/Mac: 使用 select
                try:
                    import select
                    ready, _, _ = select.select([self.web_proc.stdout], [], [], 0.5)
                    if ready:
                        line = self.web_proc.stdout.readline()
                        if line:
                            error_output.append(line.rstrip())
                            print(f"[Web] {line.rstrip()}")
                except:
                    pass

            # 检查进程是否还在运行
            if self.web_proc.poll() is not None:
                # 进程已退出，读取剩余输出
                time.sleep(0.5)
                remaining = self.web_proc.stdout.read()
                if remaining:
                    for line in remaining.split('\n'):
                        if line.strip():
                            error_output.append(line.rstrip())
                            print(f"[Web] {line.rstrip()}")
                print("\n✗ Web 服务启动失败，错误输出:")
                for line in error_output[-30:]:
                    print(f"  {line}")
                return False

            # 检查端口是否已监听
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.5)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    print(f"✓ Web 服务已启动: http://{host}:{port}")
                    return True
            except:
                pass

            time.sleep(0.5)

        print(f"✓ Web 服务已启动（超时检测）: http://{host}:{port}")
        return True

    def monitor(self):
        """监控子进程输出"""
        import select

        while True:
            # 检查进程是否还在运行
            if self.trader_proc and self.trader_proc.poll() is not None:
                print("\n✗ 交易服务已退出")
                break

            if self.web_proc and self.web_proc.poll() is not None:
                print("\n✗ Web 服务已退出")
                break

            # 读取输出（非阻塞）
            if self.trader_proc:
                try:
                    import os
                    import platform

                    if platform.system() == 'Windows':
                        # Windows 使用不同的方式读取
                        line = self.trader_proc.stdout.readline()
                        if line:
                            print(f"[交易] {line.rstrip()}")
                    else:
                        ready, _, _ = select.select([self.trader_proc.stdout], [], [], 0.1)
                        if ready:
                            line = self.trader_proc.stdout.readline()
                            if line:
                                print(f"[交易] {line.rstrip()}")
                except Exception:
                    pass

            if self.web_proc:
                try:
                    line = self.web_proc.stdout.readline()
                    if line:
                        print(f"[Web] {line.rstrip()}")
                except Exception:
                    pass

            time.sleep(0.1)

    def stop(self):
        """停止所有服务"""
        print("\n停止服务中...")

        if self.trader_proc:
            self.trader_proc.terminate()
            try:
                self.trader_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.trader_proc.kill()
            print("✓ 交易服务已停止")

        if self.web_proc:
            self.web_proc.terminate()
            try:
                self.web_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.web_proc.kill()
            print("✓ Web 服务已停止")

    def run(self, mode, capital, gateway, xt_account, host, port):
        """运行启动流程"""
        # 设置信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

        try:
            # 0. 确保 Web 配置存在
            ensure_web_config()
            # 1. 启动交易服务
            if not self.start_trading(mode, capital, gateway, xt_account):
                print("交易服务启动失败，退出")
                return 1

            # 2. 等待 RPC 就绪
            if not self.wait_for_rpc(timeout=30):
                print("RPC 服务未就绪，但继续尝试启动 Web")

            # 3. 启动 Web 看板
            if not self.start_web(host, port):
                self.stop()
                return 1

            # 4. 打印成功信息
            print("\n" + "=" * 60)
            print("✓ 所有服务已启动！")
            print("=" * 60)
            print(f"交易模式: {mode}")
            print(f"初始资金: {capital:,.0f}")
            print(f"网关: {gateway}")
            print(f"迅投账号: {xt_account}")
            print(f"Web看板: http://{host}:{port}")
            print("\n按 Ctrl+C 停止所有服务")
            print("=" * 60 + "\n")

            # 5. 监控进程
            self.monitor()

            return 0

        except Exception as e:
            print(f"\n发生错误: {e}")
            self.stop()
            return 1


def main():
    parser = argparse.ArgumentParser(description='启动交易 + Web看板')
    parser.add_argument('--mode', choices=['backtest', 'paper', 'live'],
                       default='paper', help='运行模式')
    parser.add_argument('--capital', type=float, default=1_000_000,
                       help='初始资金（默认100万）')
    parser.add_argument('--gateway', default='XT', help='交易网关')
    parser.add_argument('--xt-account', default='your_account',
                       help='迅投研账号（实盘/模拟盘需要）')
    parser.add_argument('--host', default='0.0.0.0', help='Web服务地址')
    parser.add_argument('--port', type=int, default=8000, help='Web服务端口')

    args = parser.parse_args()

    launcher = TradingDashboardLauncher()
    return launcher.run(args.mode, args.capital, args.gateway, args.xt_account, args.host, args.port)


if __name__ == "__main__":
    sys.exit(main())
