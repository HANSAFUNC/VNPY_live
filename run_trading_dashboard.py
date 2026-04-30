#!/usr/bin/env python
"""
统一启动交易 + Web 看板 (Vue3 独立服务版)

使用方式:
    python run_trading_dashboard.py --mode paper --capital 1000000 --xt-account your_xt_account

参数:
    --mode: 运行模式 (backtest/paper/live)，默认 paper
    --capital: 初始资金，默认 1000000
    --gateway: 交易网关，默认 XT
    --xt-account: 迅投研账号（实盘/模拟盘需要）
    --host: Web API服务地址，默认 0.0.0.0
    --port: Web API服务端口，默认 8000
    --vue-port: Vue dev server端口，默认 3000
    --no-vue: 不自动启动 Vue dev server（手动启动 npm run dev）
"""
import subprocess
import sys
import time
import signal
import argparse
import json
from pathlib import Path

from vnpy.trader.setting import SETTINGS

# 全局配置：是否显示交易服务详细输出
VERBOSE = True  # 设置为 True 开启详细输出

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
    print(f"[OK] Web配置已确认: {config_path}")
    print(f"  登录用户: {setting['username']}")
    print(f"  RPC地址: {setting['req_address']}")

    return setting


class TradingDashboardLauncher:
    """交易 + Web看板统一启动器"""

    def __init__(self):
        self.trader_proc = None
        self.web_proc = None  # FastAPI 后端
        self.vue_proc = None  # Vue dev server
        self.rpc_ready = False

    def signal_handler(self, signum, frame):
        """信号处理 - 优雅退出"""
        print("\n\n[WARN] 接收到退出信号，正在停止服务...")
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
                    print("[OK] RPC 服务已就绪")
                    return True
            except Exception:
                pass

            time.sleep(0.5)

        print(f"[ERROR] RPC 服务启动超时 ({timeout}秒)")
        return False

    def wait_for_port(self, host, port, timeout=30, service_name="服务"):
        """等待端口就绪"""
        import socket

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                result = sock.connect_ex((host, port))
                sock.close()
                if result == 0:
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def start_trading(self, mode, capital, gateway, xt_account):
        """启动交易服务"""
        import threading
        import queue

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
        output_queue = queue.Queue()
        rpc_ready_event = threading.Event()

        def read_output():
            try:
                for line in self.trader_proc.stdout:
                    if line:
                        output_queue.put(line.rstrip())
                        if "RPC 服务已启动" in line or "tcp://*:2014" in line or "RPC service started" in line:
                            rpc_ready_event.set()
            except Exception:
                pass

        def print_output():
            """后台线程持续打印输出"""
            if not VERBOSE:
                return
            try:
                while True:
                    try:
                        line = output_queue.get(timeout=0.1)
                        print(f"[交易] {line}")
                    except queue.Empty:
                        if self.trader_proc.poll() is not None:
                            break
                        continue
            except Exception:
                pass

        # 启动读取线程
        output_thread = threading.Thread(target=read_output, daemon=True)
        output_thread.start()

        # 启动打印线程
        print_thread = threading.Thread(target=print_output, daemon=True)
        print_thread.start()

        print("启动交易中...")
        start_time = time.time()
        timeout = 60

        while time.time() - start_time < timeout:
            # 检查进程是否退出
            if self.trader_proc.poll() is not None:
                print("\n[ERROR] 交易进程已退出")
                return False

            # 检测 RPC 就绪
            if rpc_ready_event.is_set():
                self.rpc_ready = True
                break

            time.sleep(0.5)

        return self.rpc_ready

    def start_web_backend(self, host, port):
        """启动 FastAPI 后端服务"""
        import threading
        import queue

        print("\n" + "=" * 60)
        print(f"启动 Web API 后端 (http://{host}:{port})")
        print("=" * 60)

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

        # 读取输出同时检测端口
        output_queue = queue.Queue()
        server_ready = threading.Event()

        def read_output():
            """读取输出"""
            try:
                for line in self.web_proc.stdout:
                    if line:
                        output_queue.put(line.rstrip())
                        # 检测 Uvicorn 启动成功的标志
                        if "Application startup complete" in line or "Uvicorn running" in line:
                            server_ready.set()
            except Exception:
                pass

        # 启动读取线程
        output_thread = threading.Thread(target=read_output, daemon=True)
        output_thread.start()

        # 等待服务启动（同时检测端口和输出）
        print("等待 Web API 启动...")
        start_time = time.time()
        timeout = 60

        while time.time() - start_time < timeout:
            # 打印输出
            while not output_queue.empty():
                line = output_queue.get()
                print(f"[API] {line}")

            # 检查进程是否退出
            if self.web_proc.poll() is not None:
                print("\n[ERROR] Web API 进程已退出")
                while not output_queue.empty():
                    print(f"[API] {output_queue.get()}")
                return False

            # 检测端口或输出标志
            if self.wait_for_port(host, port, timeout=1, service_name="Web API") or server_ready.is_set():
                print(f"[OK] Web API 已启动: http://{host}:{port}")
                # 继续后台读取输出
                threading.Thread(target=read_output, daemon=True).start()
                return True

            time.sleep(0.5)

        print(f"[ERROR] Web API 启动超时")
        return False

    def start_vue_dev_server(self, vue_port):
        """启动 Vue dev server"""
        import threading
        import queue

        vue_project = Path("web_dashboard_v2")
        if not vue_project.exists():
            print(f"[WARN] Vue 项目目录不存在: {vue_project}")
            return False

        print("\n" + "=" * 60)
        print(f"启动 Vue dev server (http://localhost:{vue_port})")
        print("=" * 60)

        # 检测 npm 命令
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

        cmd = [npm_cmd, "run", "dev"]

        try:
            self.vue_proc = subprocess.Popen(
                cmd,
                cwd=str(vue_project),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                universal_newlines=True,
                shell=(sys.platform == "win32")
            )
        except FileNotFoundError:
            print(f"[ERROR] 找不到 npm 命令，请确保 Node.js 已安装")
            return False

        # 读取输出同时检测端口
        output_queue = queue.Queue()
        server_ready = threading.Event()

        def read_output():
            """读取输出"""
            try:
                for line in self.vue_proc.stdout:
                    if line:
                        output_queue.put(line.rstrip())
                        # 检测 Vite 启动成功的标志
                        if "ready in" in line or "Local:" in line or "http://localhost:" in line:
                            server_ready.set()
            except Exception:
                pass

        # 启动读取线程
        output_thread = threading.Thread(target=read_output, daemon=True)
        output_thread.start()

        # 等待服务启动
        print("等待 Vue dev server 启动...")
        start_time = time.time()
        timeout = 60

        while time.time() - start_time < timeout:
            # 打印输出
            while not output_queue.empty():
                line = output_queue.get()
                print(f"[Vue] {line}")

            # 检查进程是否退出
            if self.vue_proc.poll() is not None:
                print("\n[ERROR] Vue dev server 进程已退出")
                while not output_queue.empty():
                    print(f"[Vue] {output_queue.get()}")
                return False

            # 检测端口或输出标志
            if self.wait_for_port("localhost", vue_port, timeout=1, service_name="Vue") or server_ready.is_set():
                print(f"[OK] Vue dev server 已启动: http://localhost:{vue_port}")
                # 继续后台读取输出
                threading.Thread(target=read_output, daemon=True).start()
                return True

            time.sleep(0.5)

        print(f"[WARN] Vue dev server 启动检测超时，但可能仍在启动中...")
        return True  # 继续运行，不阻塞

    def monitor(self):
        """监控子进程状态"""
        # 主循环：检查进程是否退出
        while True:
            time.sleep(1)

            if self.trader_proc and self.trader_proc.poll() is not None:
                print("\n[ERROR] 交易服务已退出")
                break

            if self.web_proc and self.web_proc.poll() is not None:
                print("\n[ERROR] Web API 服务已退出")
                break

            if self.vue_proc and self.vue_proc.poll() is not None:
                print("\n[WARN] Vue dev server 已退出")
                self.vue_proc = None

    def stop(self):
        """停止所有服务"""
        print("\n停止服务中...")

        if self.vue_proc:
            self.vue_proc.terminate()
            try:
                self.vue_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.vue_proc.kill()
            print("[OK] Vue dev server 已停止")

        if self.web_proc:
            self.web_proc.terminate()
            try:
                self.web_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.web_proc.kill()
            print("[OK] Web API 服务已停止")

        if self.trader_proc:
            self.trader_proc.terminate()
            try:
                self.trader_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.trader_proc.kill()
            print("[OK] 交易服务已停止")

    def run(self, mode, capital, gateway, xt_account, host, port, vue_port, no_vue):
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

            # 3. 启动 Web API 后端
            if not self.start_web_backend(host, port):
                self.stop()
                return 1

            # 4. 启动 Vue dev server（如果未禁用）
            vue_started = False
            if not no_vue:
                vue_started = self.start_vue_dev_server(vue_port)

            # 5. 打印成功信息
            print("\n" + "=" * 60)
            print("[OK] 所有服务已启动！")
            print("=" * 60)
            print(f"交易模式: {mode}")
            print(f"初始资金: {capital:,.0f}")
            print(f"网关: {gateway}")
            print(f"迅投账号: {xt_account}")
            print("-" * 60)
            print(f"Web API 后端: http://{host}:{port}")
            if vue_started:
                print(f"Vue 看板: http://localhost:{vue_port}")
                print("\n请访问 Vue 看板地址使用系统")
            else:
                print(f"\nVue dev server 未启动")
                print(f"如需手动启动，请运行: cd web_dashboard_v2 && npm run dev")
            print("-" * 60)
            print("按 Ctrl+C 停止所有服务")
            print("=" * 60 + "\n")

            # 6. 监控进程
            self.monitor()

            return 0

        except Exception as e:
            print(f"\n发生错误: {e}")
            import traceback
            traceback.print_exc()
            self.stop()
            return 1


def main():
    parser = argparse.ArgumentParser(description='启动交易 + Web看板 (Vue3独立服务版)')
    parser.add_argument('--mode', choices=['backtest', 'paper', 'live'],
                       default='paper', help='运行模式')
    parser.add_argument('--capital', type=float, default=1_000_000,
                       help='初始资金（默认100万）')
    parser.add_argument('--gateway', default='XT', help='交易网关')
    parser.add_argument('--xt-account', default='your_account',
                       help='迅投研账号（实盘/模拟盘需要）')
    parser.add_argument('--host', default='0.0.0.0', help='Web API服务地址')
    parser.add_argument('--port', type=int, default=8000, help='Web API服务端口')
    parser.add_argument('--vue-port', type=int, default=3000,
                       help='Vue dev server端口（默认3000）')
    parser.add_argument('--no-vue', action='store_true',
                       help='不自动启动 Vue dev server')

    args = parser.parse_args()

    launcher = TradingDashboardLauncher()
    return launcher.run(
        args.mode, args.capital, args.gateway,
        args.xt_account, args.host, args.port,
        args.vue_port, args.no_vue
    )


if __name__ == "__main__":
    sys.exit(main())
