"""StockAI 工具函数模块"""

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import polars as pl

logger = logging.getLogger(__name__)


def get_timestamp() -> int:
    """获取当前时间戳（秒）"""
    return int(datetime.now().timestamp())


def save_json(data: dict, path: Path) -> None:
    """保存字典到JSON文件"""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: Path) -> Optional[dict]:
    """从JSON文件加载字典"""
    import json
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_parquet(df: pl.DataFrame, path: Path) -> None:
    """保存DataFrame到Parquet文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


def load_parquet(path: Path) -> Optional[pl.DataFrame]:
    """从Parquet文件加载DataFrame"""
    if not path.exists():
        return None
    return pl.read_parquet(path)


def query_by_time(
    df: pl.DataFrame,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> pl.DataFrame:
    """
    根据时间范围过滤DataFrame

    参数:
        df: 输入DataFrame（必须包含datetime列）
        start: 开始时间（可选）
        end: 结束时间（可选）

    返回:
        过滤后的DataFrame
    """
    if start:
        df = df.filter(pl.col("datetime") >= start)
    if end:
        df = df.filter(pl.col("datetime") <= end)
    return df.sort("datetime")


@dataclass
class TimeRange:
    startts: int = 0
    stopts: int = 0

    @property
    def timerange_str(self) -> str:
        start = datetime.utcfromtimestamp(self.startts).strftime("%Y%m%d")
        end = datetime.utcfromtimestamp(self.stopts).strftime("%Y%m%d")
        return f"{start}-{end}"

    @classmethod
    def parse_timerange(cls, timerange: str) -> "TimeRange":
        parts = timerange.split("-")
        if len(parts) != 2:
            raise ValueError(f"Invalid timerange format: {timerange}, expected 'YYYYMMDD-YYYYMMDD'")

        start_dt = datetime.strptime(parts[0], "%Y%m%d")
        end_dt = datetime.strptime(parts[1], "%Y%m%d")

        return cls(
            startts=calendar.timegm(start_dt.timetuple()),
            stopts=calendar.timegm(end_dt.timetuple()),
        )


def create_full_timerange(
    backtest_start: str,
    backtest_end: str,
    train_period_days: int,
) -> tuple[str, str]:
    start_dt = datetime.strptime(backtest_start, "%Y%m%d")
    full_start = start_dt - timedelta(days=train_period_days)
    return full_start.strftime("%Y%m%d"), backtest_end
