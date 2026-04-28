import traceback
from datetime import datetime, timedelta

from vnpy.event import Event, EventEngine
from vnpy.rpc import RpcServer
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.utility import load_json, save_json, extract_vt_symbol
from vnpy.trader.object import LogData, BarData
from vnpy.trader.event import EVENT_TIMER
from vnpy.trader.constant import Interval

import polars as pl
from pathlib import Path


APP_NAME = "RpcService"

EVENT_RPC_LOG = "eRpcLog"


class RpcEngine(BaseEngine):
    """
    VeighNa的rpc服务引擎。
    """
    setting_filename: str = "rpc_service_setting.json"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """构造函数"""
        super().__init__(main_engine, event_engine, APP_NAME)

        self.rep_address: str = "tcp://*:2014"
        self.pub_address: str = "tcp://*:4102"

        self.server: RpcServer

        self.init_server()
        self.load_setting()
        self.register_event()

    def init_server(self) -> None:
        """初始化服务器"""
        self.server = RpcServer()

        self.server.register(self.main_engine.subscribe)
        self.server.register(self.main_engine.send_order)
        self.server.register(self.main_engine.cancel_order)
        self.server.register(self.main_engine.query_history)

        self.server.register(self.main_engine.get_tick)
        self.server.register(self.main_engine.get_order)
        self.server.register(self.main_engine.get_trade)
        self.server.register(self.main_engine.get_position)
        self.server.register(self.main_engine.get_account)
        self.server.register(self.main_engine.get_contract)
        self.server.register(self.main_engine.get_all_ticks)
        self.server.register(self.main_engine.get_all_orders)
        self.server.register(self.main_engine.get_all_trades)
        self.server.register(self.main_engine.get_all_positions)
        self.server.register(self.main_engine.get_all_accounts)
        self.server.register(self.main_engine.get_all_contracts)
        self.server.register(self.main_engine.get_all_active_orders)

        # 注册K线数据查询方法
        self.server.register(self.get_kline)

        # 注册实验室相关方法
        self.server.register(self.lab_get_kline)
        self.server.register(self.lab_get_components)
        self.server.register(self.lab_get_coverage)
        self.server.register(self.lab_list_projects)
        self.server.register(self.lab_switch_project)
        self.server.register(self.lab_create_project)
        self.server.register(self.lab_delete_project)

        # 注册实验室信号相关方法
        self.server.register(self.lab_list_signals)
        self.server.register(self.lab_load_signal)
        self.server.register(self.lab_remove_signal)

    def get_kline(self, vt_symbol: str, period: str = "1d") -> list:
        """
        获取K线数据 - 优先从网关获取，失败则回退到本地文件

        Parameters
        ----------
        vt_symbol : str
            标的代码，如 "600519.SSE"
        period : str
            周期，如 "1d"(日线), "1h"(小时), "15m"(15分钟)

        Returns
        -------
        list
            K线数据列表，每项为 {"datetime": str, "open": float, "close": float, "high": float, "low": float, "volume": float}
        """
        try:
            # 解析 interval
            interval_map = {
                "1d": Interval.DAILY,
                "daily": Interval.DAILY,
                "1m": Interval.MINUTE,
                "1min": Interval.MINUTE,
                "minute": Interval.MINUTE,
            }
            interval = interval_map.get(period, Interval.DAILY)

            # 尝试从网关获取数据
            from vnpy.trader.object import HistoryRequest
            from vnpy.trader.constant import Exchange

            try:
                symbol, exchange_str = vt_symbol.split(".", 1)
                exchange = Exchange(exchange_str)
            except Exception:
                symbol = vt_symbol
                exchange = Exchange.SSE

            end_date = datetime.now()
            start_date = end_date - timedelta(days=100)

            history_request = HistoryRequest(
                symbol=symbol,
                exchange=exchange,
                start=start_date,
                end=end_date,
                interval=interval
            )

            # 获取当前活跃网关
            gateways = self.main_engine.get_all_gateway_names()
            for gateway_name in gateways:
                try:
                    bar_data_list = self.main_engine.query_history(history_request, gateway_name)
                    if bar_data_list and len(bar_data_list) > 0:
                        self.write_log(f"从网关 {gateway_name} 获取到 {len(bar_data_list)} 条K线数据")
                        result = []
                        for bar in bar_data_list:
                            result.append({
                                "datetime": bar.datetime.strftime("%Y-%m-%d %H:%M:%S") if bar.datetime else "",
                                "open": float(bar.open_price),
                                "close": float(bar.close_price),
                                "high": float(bar.high_price),
                                "low": float(bar.low_price),
                                "volume": float(bar.volume)
                            })
                        return result
                except Exception as e:
                    self.write_log(f"网关 {gateway_name} 获取K线失败: {e}")
                    continue

            # 网关获取失败，回退到本地文件
            self.write_log(f"所有网关均无数据，回退到本地文件")
            return self._get_kline_from_local(vt_symbol, interval)

        except Exception as e:
            self.write_log(f"获取K线数据失败: {e}")
            return []

    def _get_kline_from_local(self, vt_symbol: str, interval: Interval) -> list:
        """从本地文件获取K线数据"""
        try:
            # 确定数据目录（从当前文件向上查找 lab 目录）
            current_dir = Path(__file__).resolve().parent
            lab_path = None
            # 向上遍历5层目录查找 lab/csi300
            for _ in range(5):
                test_path = current_dir / "lab" / "csi300"
                if test_path.exists():
                    lab_path = test_path
                    break
                current_dir = current_dir.parent

            if not lab_path:
                # 尝试使用固定路径
                lab_path = Path("F:/vnpy_live/lab/csi300")
                if not lab_path.exists():
                    self.write_log(f"无法找到 lab/csi300 目录")
                    return []

            if interval == Interval.DAILY:
                folder_path = lab_path / "daily"
            elif interval == Interval.MINUTE:
                folder_path = lab_path / "minute"
            else:
                return []

            if not folder_path.exists():
                self.write_log(f"K线目录不存在: {folder_path}")
                return []

            # 尝试转换代码格式 SH -> SSE, SZ -> SZSE
            original_symbol = vt_symbol
            if ".SH" in vt_symbol:
                vt_symbol = vt_symbol.replace(".SH", ".SSE")
            elif ".SZ" in vt_symbol:
                vt_symbol = vt_symbol.replace(".SZ", ".SZSE")

            # 检查文件是否存在
            file_path = folder_path / f"{vt_symbol}.parquet"
            if not file_path.exists():
                self.write_log(f"K线数据文件不存在: {vt_symbol} (原始: {original_symbol}), 路径: {file_path}")
                return []

            # 读取数据
            df = pl.read_parquet(file_path)

            # 获取最近 100 天的数据
            end_date = datetime.now()
            start_date = end_date - timedelta(days=100)
            df = df.filter((pl.col("datetime") >= start_date) & (pl.col("datetime") <= end_date))

            if df.is_empty():
                return []

            # 转换为前端需要的格式
            result = []
            for row in df.iter_rows(named=True):
                result.append({
                    "datetime": row["datetime"].strftime("%Y-%m-%d %H:%M:%S") if isinstance(row["datetime"], datetime) else str(row["datetime"]),
                    "open": float(row["open"]),
                    "close": float(row["close"]),
                    "high": float(row["high"]),
                    "low": float(row["low"]),
                    "volume": float(row["volume"])
                })

            return result

        except Exception as e:
            self.write_log(f"从本地获取K线数据失败: {e}")
            return []

    def get_lab_engine(self):
        """获取 AlphaLabV2Engine"""
        try:
            engine = self.main_engine.get_engine("AlphaLabV2")
            return engine
        except Exception:
            return None

    def lab_get_kline(self, vt_symbol: str, period: str = "1d", days: int = 100) -> list:
        """获取K线数据"""
        engine = self.get_lab_engine()
        if engine:
            return engine.get_kline(vt_symbol, period, days)
        return []

    def lab_get_components(self, start: str = None, end: str = None) -> list:
        """获取指数成分股"""
        engine = self.get_lab_engine()
        if engine:
            if start is None:
                start = datetime.now() - timedelta(days=30)
            if end is None:
                end = datetime.now()
            symbols = engine.get_component_symbols(engine.index_code, start, end)
            return symbols
        return []

    def lab_get_coverage(self) -> dict:
        """获取数据覆盖情况"""
        engine = self.get_lab_engine()
        if engine:
            return engine.get_data_coverage()
        return {"error": "Lab engine not available"}

    def lab_list_projects(self) -> list:
        """列出所有项目"""
        engine = self.get_lab_engine()
        if engine:
            return engine.list_projects()
        return []

    def lab_switch_project(self, project_name: str, index_code: str = None, data_source: str = None) -> dict:
        """切换项目"""
        engine = self.get_lab_engine()
        if engine:
            return engine.switch_project(project_name, index_code, data_source)
        return {"success": False, "message": "Lab engine not available"}

    def lab_create_project(self, project_name: str, index_code: str = "csi300", data_source: str = "xt") -> dict:
        """创建新项目"""
        engine = self.get_lab_engine()
        if engine:
            old_project = engine.project_name
            result = engine.switch_project(project_name, index_code, data_source)
            engine.switch_project(old_project)
            return {"success": True, "message": f"Project {project_name} created"}
        return {"success": False, "message": "Lab engine not available"}

    def lab_delete_project(self, project_name: str) -> dict:
        """删除项目"""
        import shutil
        engine = self.get_lab_engine()
        if engine:
            project_path = engine.root / "project" / project_name
            if project_path.exists():
                shutil.rmtree(project_path)
                return {"success": True, "message": f"Project {project_name} deleted"}
            return {"success": False, "message": f"Project {project_name} not found"}
        return {"success": False, "message": "Lab engine not available"}

    def lab_list_signals(self) -> list:
        """列出所有信号"""
        engine = self.get_lab_engine()
        if engine:
            return engine.list_all_signals()
        return []

    def lab_load_signal(self, name: str) -> list:
        """加载信号数据"""
        engine = self.get_lab_engine()
        if engine:
            df = engine.load_signal(name)
            if df is None:
                return None
            # Convert DataFrame to list of dicts for JSON serialization
            return df.to_dicts()
        return None

    def lab_remove_signal(self, name: str) -> dict:
        """删除信号"""
        engine = self.get_lab_engine()
        if engine:
            result = engine.remove_signal(name)
            return {"success": result, "message": f"Signal {name} removed" if result else f"Signal {name} not found"}
        return {"success": False, "message": "Lab engine not available"}

    def load_setting(self) -> None:
        """读取配置文件"""
        setting: dict[str, str] = load_json(self.setting_filename)
        self.rep_address = setting.get("rep_address", self.rep_address)
        self.pub_address = setting.get("pub_address", self.pub_address)

    def save_setting(self) -> None:
        """保存配置文件"""
        setting: dict[str, str] = {
            "rep_address": self.rep_address,
            "pub_address": self.pub_address
        }
        save_json(self.setting_filename, setting)

    def start(self, rep_address: str, pub_address: str) -> bool:
        """启动rpc服务"""
        if self.server.is_active():
            self.write_log("RPC服务运行中")
            return False

        self.rep_address = rep_address
        self.pub_address = pub_address

        try:
            self.server.start(rep_address, pub_address)
        except:  # noqa
            msg: str = traceback.format_exc()
            self.write_log(f"RPC服务启动失败：{msg}")
            return False

        self.save_setting()
        self.write_log("RPC服务启动成功")
        return True

    def stop(self) -> bool:
        """停止rpc服务"""
        if not self.server.is_active():
            self.write_log("RPC服务未启动")
            return False

        self.server.stop()
        self.server.join()
        self.write_log("RPC服务已停止")
        return True

    def close(self) -> None:
        """关闭rpc服务"""
        self.stop()

    def register_event(self) -> None:
        """注册事件"""
        self.event_engine.register_general(self.process_event)

    def process_event(self, event: Event) -> None:
        """调用事件"""
        if self.server.is_active():
            if event.type == EVENT_TIMER:
                return
            self.server.publish("", event)

    def write_log(self, msg: str) -> None:
        """输出日志"""
        log: LogData = LogData(msg=msg, gateway_name=APP_NAME)
        event: Event = Event(EVENT_RPC_LOG, log)
        self.event_engine.put(event)
