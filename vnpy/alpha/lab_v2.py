"""AlphaLab V2 引擎 - 支持 MainEngine 注册的分层架构版本"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Union, Any
import json

import polars as pl

from vnpy.event import Event, EventEngine
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData

from .base import BaseAlphaLab
from .data_store import DataStore
from .index_manager import IndexManager
from .logger import logger


EVENT_PROJECT_SWITCHED = "eProjectSwitched"


class AlphaLabV2Engine(BaseEngine, BaseAlphaLab):
    """
    AlphaLab V2 引擎

    继承 BaseEngine（用于注册到 MainEngine）和 BaseAlphaLab（统一数据接口）。
    采用分层架构：DataStore（数据层）+ IndexManager（索引层）+ Project（项目层）。

    Parameters
    ----------
    main_engine : MainEngine
        VeighNa 主引擎
    event_engine : EventEngine
        事件引擎
    root_path : str
        Lab 根目录
    project_name : str
        项目名称
    data_source : str
        数据源名称（如 "xt", "rq"）
    index_code : str
        指数代码（如 "csi300", "csi500", "all_a"）
    """

    engine_name: str = "AlphaLabV2"

    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        root_path: str,
        project_name: str,
        data_source: str,
        index_code: str
    ) -> None:
        """构造函数"""
        BaseEngine.__init__(self, main_engine, event_engine, self.engine_name)

        # 基础配置
        self.root: Path = Path(root_path)
        self.project_name: str = project_name
        self.data_source: str = data_source
        self.index_code: str = index_code

        # 项目目录
        self.project_path: Path = self.root / "project" / project_name
        self._ensure_project_dirs()

        # 合约配置
        self.contract_file: Path = self.project_path / "contract.json"
        self._contracts: dict[str, dict] = {}
        self._load_contracts()

        # 分层组件
        self.data_store: DataStore = DataStore(str(self.root), data_source)
        self.index_manager: IndexManager = IndexManager(str(self.root))

    def _ensure_project_dirs(self) -> None:
        """确保项目目录结构存在"""
        dirs = [
            self.project_path / "dataset",
            self.project_path / "model",
            self.project_path / "signal",
        ]
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)

    def _load_contracts(self) -> None:
        """加载合约配置"""
        if self.contract_file.exists():
            with open(self.contract_file, 'r', encoding='utf-8') as f:
                self._contracts = json.load(f)

    def _save_contracts(self) -> None:
        """保存合约配置"""
        with open(self.contract_file, 'w', encoding='utf-8') as f:
            json.dump(self._contracts, f, indent=2, ensure_ascii=False)

    # ==================== 数据查询接口 ====================

    def load_bars(
        self,
        vt_symbol: str,
        interval: Interval,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[BarData]:
        """加载单只股票的 K 线数据"""
        start_dt = self._to_datetime(start)
        end_dt = self._to_datetime(end)
        return self.data_store.load_bars(vt_symbol, interval, start_dt, end_dt)

    def load_bars_df(
        self,
        vt_symbols: list[str],
        interval: Interval,
        start: Union[datetime, str],
        end: Union[datetime, str],
        extended_days: int = 0
    ) -> Optional[pl.DataFrame]:
        """加载多只股票 K 线数据为 DataFrame"""
        if not vt_symbols:
            return None

        start_dt = self._to_datetime(start) - timedelta(days=extended_days)
        end_dt = self._to_datetime(end)

        dfs: list[pl.DataFrame] = []

        for vt_symbol in vt_symbols:
            bars = self.data_store.load_bars(vt_symbol, interval, start_dt, end_dt)
            if not bars:
                continue

            data = []
            for bar in bars:
                data.append({
                    "datetime": bar.datetime,
                    "open": bar.open_price,
                    "high": bar.high_price,
                    "low": bar.low_price,
                    "close": bar.close_price,
                    "volume": bar.volume,
                    "turnover": bar.turnover,
                    "open_interest": bar.open_interest,
                })

            df = pl.DataFrame(data)
            if df.is_empty():
                continue

            # 添加 vwap
            df = df.with_columns(
                (pl.col("turnover") / pl.col("volume")).alias("vwap")
            )

            # 标准化价格
            close_0 = df.select(pl.col("close")).item(0, 0)
            if close_0 > 0:
                df = df.with_columns([
                    (pl.col("open") / close_0).alias("open"),
                    (pl.col("high") / close_0).alias("high"),
                    (pl.col("low") / close_0).alias("low"),
                    (pl.col("close") / close_0).alias("close"),
                ])

            # 处理停牌日
            numeric_cols = [c for c in df.columns if c != "datetime"]
            mask = df[numeric_cols].sum_horizontal() == 0
            for col in numeric_cols:
                df = df.with_columns(
                    pl.when(mask).then(float("nan")).otherwise(pl.col(col)).alias(col)
                )

            # 添加 symbol 列
            df = df.with_columns(pl.lit(vt_symbol).alias("vt_symbol"))
            dfs.append(df)

        if not dfs:
            return None

        return pl.concat(dfs)

    def get_component_symbols(
        self,
        index_code: str,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[str]:
        """获取指数成分股列表"""
        return self.index_manager.get_all_symbols(index_code, start, end)

    def load_contract_settings(self) -> dict[str, dict]:
        """加载所有合约配置"""
        return self._contracts.copy()

    def get_contract_setting(self, vt_symbol: str) -> Optional[dict]:
        """获取单个合约配置"""
        return self._contracts.get(vt_symbol)

    # ==================== 数据更新接口 ====================

    def save_bars(self, bars: list[BarData]) -> None:
        """保存 K 线数据"""
        self.data_store.save_bars(bars)

    def save_contract_setting(
        self,
        vt_symbol: str,
        size: float,
        pricetick: float,
        long_rate: float = 0,
        short_rate: float = 0
    ) -> None:
        """保存合约配置"""
        self._contracts[vt_symbol] = {
            "size": size,
            "pricetick": pricetick,
            "long_rate": long_rate,
            "short_rate": short_rate,
        }
        self._save_contracts()

    def update_daily_data(
        self,
        symbols: Optional[list[str]] = None,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        incremental: bool = True
    ) -> dict[str, Any]:
        """
        更新每日数据（收盘后调用）

        注意：此方法需要外部数据源支持，当前实现返回提示信息。
        实际使用时，需要接入具体的数据下载器（如 XtDownloader）。
        """
        logger.warning("update_daily_data 需要外部数据源支持，当前为占位实现")

        # 如果没有提供 symbols，获取当前指数成分股
        if symbols is None:
            if end_date is None:
                end_date = datetime.now()
            if start_date is None:
                start_date = end_date - timedelta(days=30)

            symbols = self.get_component_symbols(self.index_code, start_date, end_date)

        return {
            "success": [],
            "failed": [(s, "需要外部数据源") for s in symbols] if symbols else [],
            "skipped": [],
            "total_count": len(symbols) if symbols else 0,
            "updated_count": 0,
            "time_range": (start_date, end_date) if start_date and end_date else (None, None),
            "message": "请使用外部数据下载器（如 XtDownloader）更新数据"
        }

    def get_last_update_date(
        self,
        vt_symbol: str,
        interval: Interval
    ) -> Optional[datetime]:
        """获取某只股票最后更新日期"""
        info = self.data_store.get_data_info(vt_symbol, interval)
        if info and info.get("end"):
            return datetime.fromisoformat(info["end"])
        return None

    def get_data_coverage(self) -> dict[str, Any]:
        """获取数据覆盖情况统计"""
        daily_symbols = self.data_store.list_symbols(Interval.DAILY)
        minute_symbols = self.data_store.list_symbols(Interval.MINUTE)

        # 获取数据范围
        all_starts, all_ends = [], []
        for symbol in daily_symbols[:10]:  # 采样前10个
            info = self.data_store.get_data_info(symbol, Interval.DAILY)
            if info:
                if info.get("start"):
                    all_starts.append(datetime.fromisoformat(info["start"]))
                if info.get("end"):
                    all_ends.append(datetime.fromisoformat(info["end"]))

        date_range = {
            "start": min(all_starts) if all_starts else None,
            "end": max(all_ends) if all_ends else None
        }

        last_update = max(all_ends) if all_ends else None

        return {
            "total_symbols": len(set(daily_symbols + minute_symbols)),
            "daily_files": len(daily_symbols),
            "minute_files": len(minute_symbols),
            "date_range": date_range,
            "last_update": last_update,
            "missing_data": []
        }

    def switch_project(
        self,
        project_name: str,
        index_code: Optional[str] = None,
        data_source: Optional[str] = None
    ) -> dict[str, Any]:
        """
        切换到新的实验项目

        动态切换项目配置，无需重新创建引擎。
        """
        old_project = self.project_name
        old_index = self.index_code
        old_source = self.data_source

        # 更新配置
        self.project_name = project_name
        if index_code is not None:
            self.index_code = index_code
        if data_source is not None:
            self.data_source = data_source
            # 重新创建 DataStore
            self.data_store = DataStore(str(self.root), data_source)

        # 更新项目目录
        self.project_path = self.root / "project" / project_name
        self._ensure_project_dirs()

        # 重新加载合约配置
        self.contract_file = self.project_path / "contract.json"
        self._load_contracts()

        # 触发事件
        event_data = {
            "old_project": old_project,
            "new_project": project_name,
            "old_index": old_index,
            "new_index": self.index_code,
            "old_source": old_source,
            "new_source": self.data_source,
        }
        self.event_engine.put(Event(EVENT_PROJECT_SWITCHED, event_data))

        logger.info(f"项目切换: {old_project} -> {project_name}, "
                    f"指数: {old_index} -> {self.index_code}, "
                    f"数据源: {old_source} -> {self.data_source}")

        return {
            "success": True,
            "old_project": old_project,
            "new_project": project_name,
            "index_code": self.index_code,
            "data_source": self.data_source,
            "message": f"成功切换到项目 {project_name}"
        }

    def list_projects(self) -> list[str]:
        """列出所有可用的实验项目"""
        project_dir = self.root / "project"
        if not project_dir.exists():
            return []
        return [d.name for d in project_dir.iterdir() if d.is_dir()]

    def get_kline(
        self,
        vt_symbol: str,
        period: str = "1d",
        days: int = 100
    ) -> list[dict]:
        """
        获取K线数据（Web API格式）

        Parameters
        ----------
        vt_symbol : str
            标的代码，如 "600519.SSE"
        period : str
            周期，如 "1d"(日线), "1h"(小时), "15m"(15分钟)
        days : int
            获取最近多少天的数据，默认100天

        Returns
        -------
        list[dict]
            K线数据列表，每项为 {"datetime": str, "open": float, "close": float,
                                  "high": float, "low": float, "volume": float}
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

            # 计算日期范围
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)

            # 加载K线数据
            bars = self.load_bars(vt_symbol, interval, start_date, end_date)

            if not bars:
                return []

            # 转换为Web API格式
            result = []
            for bar in bars:
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
            logger.error(f"获取K线数据失败: {vt_symbol}, {e}")
            return []

    # ==================== 额外工具方法 ====================

    def get_component_filters(
        self,
        index_code: str,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> dict[str, list[tuple[datetime, datetime]]]:
        """获取成分股的连续持有期（用于回测过滤）"""
        return self.index_manager.get_component_filters(index_code, start, end)

    def save_components(
        self,
        index_code: str,
        date: Union[str, datetime],
        symbols: list[str]
    ) -> None:
        """保存某日的成分股列表"""
        self.index_manager.save_components(index_code, date, symbols)

    # ==================== 信号相关方法 ====================

    def save_signal(self, name: str, signal: pl.DataFrame) -> None:
        """保存信号到项目目录"""
        file_path = self.project_path / "signal" / f"{name}.parquet"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        signal.write_parquet(file_path)
        logger.info(f"信号已保存: {file_path}")

    def load_signal(self, name: str) -> Optional[pl.DataFrame]:
        """从项目目录加载信号"""
        file_path = self.project_path / "signal" / f"{name}.parquet"
        if not file_path.exists():
            logger.error(f"信号文件不存在: {name}")
            return None
        return pl.read_parquet(file_path)

    def remove_signal(self, name: str) -> bool:
        """删除信号文件"""
        file_path = self.project_path / "signal" / f"{name}.parquet"
        if not file_path.exists():
            logger.error(f"信号文件不存在: {name}")
            return False
        file_path.unlink()
        return True

    def list_all_signals(self) -> list[str]:
        """列出所有信号"""
        signal_dir = self.project_path / "signal"
        if not signal_dir.exists():
            return []
        return [f.stem for f in signal_dir.glob("*.parquet")]


# 向后兼容别名
AlphaLabV2 = AlphaLabV2Engine
