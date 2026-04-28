"""AlphaLab 抽象基类 - 定义统一数据接口"""
from abc import ABC, abstractmethod
from typing import Optional, Union, Any
from datetime import datetime
from pathlib import Path

import polars as pl
from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData, Exchange


class BaseAlphaLab(ABC):
    """AlphaLab 抽象基类

    定义完整的数据访问和更新接口，提供通用工具方法。
    子类必须实现所有抽象方法。
    """

    # ==================== 数据查询接口 (抽象方法) ====================

    @abstractmethod
    def load_bars(
        self,
        vt_symbol: str,
        interval: Interval,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[BarData]:
        """加载单只股票的 K 线数据

        Parameters
        ----------
        vt_symbol : str
            标的代码，如 "600519.SSE"
        interval : Interval
            K 线周期 (DAILY, MINUTE)
        start : datetime or str
            开始日期
        end : datetime or str
            结束日期

        Returns
        -------
        list[BarData]
            K 线数据列表
        """
        pass

    @abstractmethod
    def load_bars_df(
        self,
        vt_symbols: list[str],
        interval: Interval,
        start: Union[datetime, str],
        end: Union[datetime, str],
        extended_days: int = 0
    ) -> Optional[pl.DataFrame]:
        """加载多只股票 K 线数据为 DataFrame

        Parameters
        ----------
        vt_symbols : list[str]
            股票代码列表
        interval : Interval
            K 线周期
        start : datetime or str
            开始日期
        end : datetime or str
            结束日期
        extended_days : int
            向前后扩展的天数（用于计算指标）

        Returns
        -------
        pl.DataFrame or None
            包含 vt_symbol 列的 DataFrame
        """
        pass

    @abstractmethod
    def get_component_symbols(
        self,
        index_code: str,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[str]:
        """获取指数成分股列表

        Parameters
        ----------
        index_code : str
            指数代码，如 "csi300", "csi500", "all_a"
        start : datetime or str
            开始日期
        end : datetime or str
            结束日期

        Returns
        -------
        list[str]
            成分股 vt_symbol 列表（去重）
        """
        pass

    @abstractmethod
    def load_contract_settings(self) -> dict[str, dict]:
        """加载所有合约配置

        Returns
        -------
        dict[str, dict]
            {vt_symbol: {"size": float, "pricetick": float, ...}}
        """
        pass

    @abstractmethod
    def get_contract_setting(self, vt_symbol: str) -> Optional[dict]:
        """获取单个合约配置

        Parameters
        ----------
        vt_symbol : str
            标的代码

        Returns
        -------
        dict or None
            合约配置，不存在返回 None
        """
        pass

    # ==================== 数据更新接口 (抽象方法) ====================

    @abstractmethod
    def save_bars(self, bars: list[BarData]) -> None:
        """保存 K 线数据

        Parameters
        ----------
        bars : list[BarData]
            K 线数据列表
        """
        pass

    @abstractmethod
    def save_contract_setting(
        self,
        vt_symbol: str,
        size: float,
        pricetick: float,
        long_rate: float = 0,
        short_rate: float = 0
    ) -> None:
        """保存合约配置

        Parameters
        ----------
        vt_symbol : str
            标的代码
        size : float
            合约乘数
        pricetick : float
            最小价格变动
        long_rate : float
            多头手续费率
        short_rate : float
            空头手续费率
        """
        pass

    @abstractmethod
    def update_daily_data(
        self,
        symbols: Optional[list[str]] = None,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        incremental: bool = True
    ) -> dict[str, Any]:
        """更新每日数据（收盘后调用）

        Parameters
        ----------
        symbols : list[str], optional
            要更新的股票代码列表，为 None 时自动获取当前成分股
        start_date : str or datetime, optional
            开始日期，为 None 时自动计算
        end_date : str or datetime, optional
            结束日期，默认为今天
        incremental : bool
            是否增量更新，True=只更新缺失数据

        Returns
        -------
        dict
            {
                "success": list[str],
                "failed": list[tuple[str, str]],
                "skipped": list[str],
                "total_count": int,
                "updated_count": int,
                "time_range": tuple[datetime, datetime]
            }
        """
        pass

    @abstractmethod
    def get_last_update_date(
        self,
        vt_symbol: str,
        interval: Interval
    ) -> Optional[datetime]:
        """获取某只股票最后更新日期

        Parameters
        ----------
        vt_symbol : str
            标的代码
        interval : Interval
            K 线周期

        Returns
        -------
        datetime or None
            最后更新日期，无数据返回 None
        """
        pass

    @abstractmethod
    def get_data_coverage(self) -> dict[str, Any]:
        """获取数据覆盖情况统计

        Returns
        -------
        dict
            {
                "total_symbols": int,
                "daily_files": int,
                "minute_files": int,
                "date_range": {"start": datetime, "end": datetime},
                "last_update": datetime,
                "missing_data": list[str]
            }
        """
        pass

    @abstractmethod
    def switch_project(
        self,
        project_name: str,
        index_code: Optional[str] = None,
        data_source: Optional[str] = None
    ) -> dict[str, Any]:
        """切换到新的实验项目

        动态切换项目配置，无需重新创建引擎。
        常用于回测不同策略或不同指数成分股。

        Parameters
        ----------
        project_name : str
            新项目名称，如 "lasso_csi500"
        index_code : str, optional
            新的指数代码，为 None 时保持当前
        data_source : str, optional
            新的数据源，为 None 时保持当前

        Returns
        -------
        dict
            {
                "success": bool,
                "old_project": str,
                "new_project": str,
                "index_code": str,
                "data_source": str,
                "message": str
            }
        """
        pass

    def list_projects(self) -> list[str]:
        """列出所有可用的实验项目

        Returns
        -------
        list[str]
            项目名称列表
        """
        # 默认实现，子类可覆盖
        return []

    # ==================== 通用工具方法 (具体实现) ====================

    def _to_datetime(self, value: Union[str, datetime]) -> datetime:
        """将字符串或日期转换为 datetime"""
        if isinstance(value, str):
            # 支持多种格式
            formats = [
                "%Y-%m-%d %H:%M:%S",
                "%Y-%m-%d",
                "%Y%m%d",
                "%Y/%m/%d"
            ]
            for fmt in formats:
                try:
                    return datetime.strptime(value, fmt)
                except ValueError:
                    continue
            raise ValueError(f"无法解析日期格式: {value}")
        return value

    def _normalize_symbol(self, vt_symbol: str) -> str:
        """标准化股票代码格式

        SH -> SSE, SZ -> SZSE
        """
        if ".SH" in vt_symbol:
            return vt_symbol.replace(".SH", ".SSE")
        elif ".SZ" in vt_symbol:
            return vt_symbol.replace(".SZ", ".SZSE")
        return vt_symbol

    def _bar_to_dict(self, bar: BarData) -> dict:
        """BarData 转换为字典"""
        return {
            "datetime": bar.datetime.replace(tzinfo=None) if bar.datetime else None,
            "open": bar.open_price,
            "high": bar.high_price,
            "low": bar.low_price,
            "close": bar.close_price,
            "volume": bar.volume,
            "turnover": bar.turnover,
            "open_interest": bar.open_interest
        }

    def _dict_to_bar(
        self,
        data: dict,
        symbol: str,
        exchange: Exchange,
        interval: Interval
    ) -> BarData:
        """字典转换为 BarData"""
        return BarData(
            symbol=symbol,
            exchange=exchange,
            datetime=data["datetime"],
            interval=interval,
            open_price=data["open"],
            high_price=data["high"],
            low_price=data["low"],
            close_price=data["close"],
            volume=data["volume"],
            turnover=data.get("turnover", 0),
            open_interest=data.get("open_interest", 0),
            gateway_name="DB"
        )

    def _ensure_path(self, path: Path) -> None:
        """确保目录存在"""
        path.mkdir(parents=True, exist_ok=True)

    def _extract_vt_symbol(self, vt_symbol: str) -> tuple[str, str]:
        """从 vt_symbol 提取 symbol 和 exchange"""
        parts = vt_symbol.split(".")
        if len(parts) == 2:
            return parts[0], parts[1]
        return vt_symbol, ""
