"""数据层管理器 - 管理原始 K 线数据存储"""
from pathlib import Path
from datetime import datetime
from typing import Optional
import json

import polars as pl

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData
from vnpy.alpha.logger import logger


class DataStore:
    """
    数据层管理器

    职责：
    1. 按数据源（xt/rq）存储原始 K 线数据
    2. 提供统一的读写接口
    3. 管理数据元信息（更新时间、数据范围等）
    """

    def __init__(self, root_path: str, source: str = "xt"):
        """
        Parameters
        ----------
        root_path : str
            lab 根目录，如 "./lab"
        source : str
            数据源名称，如 "xt"（迅投）、"rq"（ricequant）
        """
        self.root = Path(root_path)
        self.source = source

        # 数据目录
        self.data_path = self.root / "data" / source
        self.daily_path = self.data_path / "daily"
        self.minute_path = self.data_path / "minute"

        # 确保目录存在
        for path in [self.daily_path, self.minute_path]:
            path.mkdir(parents=True, exist_ok=True)

        # 元信息文件
        self.meta_file = self.data_path / "meta.json"

    def save_bars(self, bars: list[BarData]) -> None:
        """保存 K 线数据"""
        if not bars:
            return

        bar = bars[0]
        vt_symbol = bar.vt_symbol
        interval = bar.interval

        # 确定存储路径
        if interval == Interval.DAILY:
            folder = self.daily_path
        elif interval == Interval.MINUTE:
            folder = self.minute_path
        else:
            raise ValueError(f"不支持的周期：{interval}")

        file_path = folder / f"{vt_symbol}.parquet"

        # 转换为 DataFrame
        data = []
        for bar in bars:
            data.append({
                "datetime": bar.datetime.replace(tzinfo=None),
                "open": bar.open_price,
                "high": bar.high_price,
                "low": bar.low_price,
                "close": bar.close_price,
                "volume": bar.volume,
                "turnover": bar.turnover,
                "open_interest": bar.open_interest
            })

        new_df = pl.DataFrame(data)

        # 合并现有数据
        if file_path.exists():
            old_df = pl.read_parquet(file_path)
            new_df = pl.concat([old_df, new_df])
            new_df = new_df.unique(subset=["datetime"])
            new_df = new_df.sort("datetime")

        new_df.write_parquet(file_path)

        # 更新元信息
        self._update_meta(vt_symbol, interval, new_df)

    def load_bars(
        self,
        vt_symbol: str,
        interval: Interval,
        start: datetime,
        end: datetime
    ) -> list[BarData]:
        """加载 K 线数据"""
        # 确定路径
        if interval == Interval.DAILY:
            folder = self.daily_path
        else:
            folder = self.minute_path

        file_path = folder / f"{vt_symbol}.parquet"

        if not file_path.exists():
            return []

        df = pl.read_parquet(file_path)
        df = df.filter(
            (pl.col("datetime") >= start) & (pl.col("datetime") <= end)
        )

        # 转换为 BarData
        bars = []
        for row in df.iter_rows(named=True):
            symbol = vt_symbol.split(".")[0]
            exchange = vt_symbol.split(".")[1]
            bars.append(BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=row["datetime"],
                interval=interval,
                open_price=row["open"],
                high_price=row["high"],
                low_price=row["low"],
                close_price=row["close"],
                volume=row["volume"],
                turnover=row.get("turnover"),
                open_interest=row.get("open_interest"),
                gateway_name="DB"
            ))

        return bars

    def _update_meta(self, vt_symbol: str, interval: Interval, df: pl.DataFrame):
        """更新数据元信息"""
        meta = {}
        if self.meta_file.exists():
            with open(self.meta_file, 'r', encoding='utf-8') as f:
                meta = json.load(f)

        key = f"{vt_symbol}_{interval.value}"
        meta[key] = {
            "last_update": datetime.now().isoformat(),
            "rows": len(df),
            "start": str(df["datetime"].min()) if len(df) > 0 else None,
            "end": str(df["datetime"].max()) if len(df) > 0 else None
        }

        with open(self.meta_file, 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)

    def list_symbols(self, interval: Interval) -> list[str]:
        """列出所有可用的股票代码"""
        if interval == Interval.DAILY:
            folder = self.daily_path
        else:
            folder = self.minute_path

        return [f.stem for f in folder.glob("*.parquet")]

    def get_data_info(self, vt_symbol: str, interval: Interval) -> Optional[dict]:
        """获取数据信息"""
        if not self.meta_file.exists():
            return None

        with open(self.meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        key = f"{vt_symbol}_{interval.value}"
        return meta.get(key)
