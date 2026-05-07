"""StockAI 工具函数模块"""

import calendar
import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import polars as pl

logger = logging.getLogger(__name__)


def convert_polars_to_pandas(df: pl.DataFrame) -> pd.DataFrame:
    """
    将 polars DataFrame 转换为 pandas DataFrame

    FreqAI 风格: 保留 date 列（从 datetime 列转换）

    参数:
        df: polars DataFrame

    返回:
        pandas DataFrame，包含 date 列
    """
    if df is None or df.is_empty():
        return pd.DataFrame()

    pd_df = df.to_pandas()

    # 将 datetime 列重命名为 date（FreqAI 标准列名）
    if "datetime" in pd_df.columns:
        pd_df["date"] = pd.to_datetime(pd_df["datetime"])
        pd_df.drop(columns=["datetime"], inplace=True)

    return pd_df


def convert_pandas_to_polars(df: pd.DataFrame) -> pl.DataFrame:
    """
    将 pandas DataFrame 转换为 polars DataFrame

    FreqAI 风格: 将 date 列转回 datetime 列

    参数:
        df: pandas DataFrame

    返回:
        polars DataFrame，包含 datetime 列
    """
    if df is None or df.empty:
        return pl.DataFrame()

    pd_df = df.copy()

    # 将 date 列重命名为 datetime（polars 标准列名）
    if "date" in pd_df.columns:
        pd_df["datetime"] = pd.to_datetime(pd_df["date"])
        pd_df.drop(columns=["date"], inplace=True)

    # 转换回 polars
    return pl.from_pandas(pd_df)


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


def save_parquet(df: Any, path: Path) -> None:
    """保存 DataFrame 到 Parquet 文件 (支持 polars 和 pandas)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(df, pl.DataFrame):
        df.write_parquet(path)
    elif isinstance(df, pd.DataFrame):
        df.to_parquet(path)
    else:
        raise TypeError(f"Unsupported DataFrame type: {type(df)}")


def load_parquet(path: Path, as_pandas: bool = False) -> Optional[Any]:
    """
    从 Parquet 文件加载 DataFrame

    参数:
        path: 文件路径
        as_pandas: 是否返回 pandas DataFrame (默认 polars)

    返回:
        DataFrame 或 None
    """
    if not path.exists():
        return None
    if as_pandas:
        return pd.read_parquet(path)
    return pl.read_parquet(path)


def query_by_time(
    df: Any,
    start: Optional[datetime] = None,
    end: Optional[datetime] = None,
) -> Any:
    """
    根据时间范围过滤DataFrame

    参数:
        df: 输入DataFrame（必须包含datetime或date列）
        start: 开始时间（可选）
        end: 结束时间（可选）

    返回:
        过滤后的DataFrame (类型与输入一致)
    """
    date_col = "date" if isinstance(df, pd.DataFrame) and "date" in df.columns else "datetime"

    if isinstance(df, pl.DataFrame):
        if start:
            df = df.filter(pl.col("datetime") >= start)
        if end:
            df = df.filter(pl.col("datetime") <= end)
        return df.sort("datetime")
    elif isinstance(df, pd.DataFrame):
        if date_col in df.columns:
            if start:
                df = df[df[date_col] >= start]
            if end:
                df = df[df[date_col] <= end]
            return df.sort_values(date_col)
        else:
            # datetime 是索引
            if start:
                df = df[df.index >= start]
            if end:
                df = df[df.index <= end]
            return df.sort_index()
    else:
        raise TypeError(f"Unsupported DataFrame type: {type(df)}")


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
    """
    创建完整时间范围（包含训练前置期）

    Args:
        backtest_start: 回测开始日期 (YYYY-MM-DD 或 YYYYMMDD)
        backtest_end: 回测结束日期 (YYYY-MM-DD 或 YYYYMMDD)
        train_period_days: 训练期天数

    Returns:
        (full_start, backtest_end) 完整时间范围 (YYYY-MM-DD 格式)
    """
    # 支持两种日期格式
    if "-" in backtest_start:
        start_dt = datetime.strptime(backtest_start, "%Y-%m-%d")
    else:
        start_dt = datetime.strptime(backtest_start, "%Y%m%d")

    full_start = start_dt - timedelta(days=train_period_days)
    return full_start.strftime("%Y-%m-%d"), backtest_end


def split_timerange(
        start_date: str,
        end_date: str,
        train_period_days: int,
        backtest_period_days: int,
    ) -> tuple[list[tuple[str, str]], list[tuple[str, str]]]:
        """
        将完整时间范围分割为多个训练和回测窗口 (滑动窗口)

        参数:
            start_date: 起始日期 (格式: YYYY-MM-DD)
            end_date: 结束日期 (格式: YYYY-MM-DD)
            train_period_days: 训练窗口天数
            backtest_period_days: 回测窗口天数

        返回:
            (training_ranges, backtesting_ranges) - 每个元素为 (start, end) 日期字符串
        """
        fmt = "%Y-%m-%d"
        start = datetime.strptime(start_date, fmt)
        end = datetime.strptime(end_date, fmt)

        training_ranges: list[tuple[str, str]] = []
        backtesting_ranges: list[tuple[str, str]] = []

        # 计算滑动步长：每次向前滑动 backtest_period_days
        step_days = backtest_period_days

        current_train_start = start
        while True:
            train_end = current_train_start + timedelta(days=train_period_days)
            bt_start = train_end
            bt_end = bt_start + timedelta(days=backtest_period_days)

            # 如果预测期超出数据范围，结束
            if bt_start >= end:
                break

            # 如果预测期部分超出，仍然保留（截断到 end）
            if bt_end > end:
                bt_end = end

            training_ranges.append((current_train_start.strftime(fmt), train_end.strftime(fmt)))
            backtesting_ranges.append((bt_start.strftime(fmt), bt_end.strftime(fmt)))

            # 滑动到下一个窗口
            current_train_start = current_train_start + timedelta(days=step_days)

        return training_ranges, backtesting_ranges