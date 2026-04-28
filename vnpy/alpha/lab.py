import json
import shelve
import pickle
from pathlib import Path
from datetime import datetime, timedelta
from collections import defaultdict
from functools import lru_cache
from typing import Optional, Union, Any

import polars as pl

from vnpy.trader.object import BarData
from vnpy.trader.constant import Interval
from vnpy.trader.utility import extract_vt_symbol
from vnpy.trader.object import Exchange

from .base import BaseAlphaLab
from .logger import logger
from .dataset import AlphaDataset, to_datetime
from .model import AlphaModel


class AlphaLab(BaseAlphaLab):
    """Alpha Research Laboratory"""

    def __init__(self, lab_path: str) -> None:
        """Constructor"""
        # Set data paths
        self.lab_path: Path = Path(lab_path)

        self.daily_path: Path = self.lab_path.joinpath("daily")
        self.minute_path: Path = self.lab_path.joinpath("minute")
        self.component_path: Path = self.lab_path.joinpath("component")

        self.dataset_path: Path = self.lab_path.joinpath("dataset")
        self.model_path: Path = self.lab_path.joinpath("model")
        self.signal_path: Path = self.lab_path.joinpath("signal")

        self.contract_path: Path = self.lab_path.joinpath("contract.json")

        # Create folders
        for path in [
            self.lab_path,
            self.daily_path,
            self.minute_path,
            self.component_path,
            self.dataset_path,
            self.model_path,
            self.signal_path
        ]:
            if not path.exists():
                path.mkdir(parents=True)

    def save_bars(self, bars: list[BarData]) -> None:
        """Save bar data"""
        if not bars:
            return

        # Get file path
        bar: BarData = bars[0]

        if bar.interval == Interval.DAILY:
            file_path: Path = self.daily_path.joinpath(f"{bar.vt_symbol}.parquet")
        elif bar.interval == Interval.MINUTE:
            file_path = self.minute_path.joinpath(f"{bar.vt_symbol}.parquet")
        elif bar.interval:
            logger.error(f"Unsupported interval {bar.interval.value}")
            return

        data: list = []
        for bar in bars:
            bar_data: dict = {
                "datetime": bar.datetime.replace(tzinfo=None),
                "open": bar.open_price,
                "high": bar.high_price,
                "low": bar.low_price,
                "close": bar.close_price,
                "volume": bar.volume,
                "turnover": bar.turnover,
                "open_interest": bar.open_interest
            }
            data.append(bar_data)

        new_df: pl.DataFrame = pl.DataFrame(data)

        # If file exists, read and merge
        if file_path.exists():
            old_df: pl.DataFrame = pl.read_parquet(file_path)

            new_df = pl.concat([old_df, new_df])

            new_df = new_df.unique(subset=["datetime"])

            new_df = new_df.sort("datetime")

        # Save to file
        new_df.write_parquet(file_path)

    def load_bars(
        self,
        vt_symbol: str,
        interval: Interval | str,
        start: datetime | str,
        end: datetime | str
    ) -> list[BarData]:
        """Load bar data"""
        # Convert types
        if isinstance(interval, str):
            interval = Interval(interval)

        start = to_datetime(start)
        end = to_datetime(end)

        # Get folder path
        if interval == Interval.DAILY:
            folder_path: Path = self.daily_path
        elif interval == Interval.MINUTE:
            folder_path = self.minute_path
        else:
            logger.error(f"Unsupported interval {interval.value}")
            return []

        # Check if file exists
        file_path: Path = folder_path.joinpath(f"{vt_symbol}.parquet")
        if not file_path.exists():
            logger.error(f"File {file_path} does not exist")
            return []

        # Open file
        df: pl.DataFrame = pl.read_parquet(file_path)

        # Filter by date range
        df = df.filter((pl.col("datetime") >= start) & (pl.col("datetime") <= end))

        # Convert to BarData objects
        bars: list[BarData] = []

        symbol, exchange = extract_vt_symbol(vt_symbol)

        for row in df.iter_rows(named=True):
            bar = BarData(
                symbol=symbol,
                exchange=exchange,
                datetime=row["datetime"],
                interval=interval,
                open_price=row["open"],
                high_price=row["high"],
                low_price=row["low"],
                close_price=row["close"],
                volume=row["volume"],
                turnover=row["turnover"],
                open_interest=row["open_interest"],
                gateway_name="DB"
            )
            bars.append(bar)

        return bars

    def load_bars_df(
        self,
        vt_symbols: list[str],
        interval: Interval | str,
        start: datetime | str,
        end: datetime | str,
        extended_days: int = 0
    ) -> pl.DataFrame | None:
        """Load bar data as DataFrame"""
        if not vt_symbols:
            return None

        # Convert types
        if isinstance(interval, str):
            interval = Interval(interval)

        start = to_datetime(start) - timedelta(days=extended_days)
        end = to_datetime(end) + timedelta(days=extended_days // 10)

        # Get folder path
        if interval == Interval.DAILY:
            folder_path: Path = self.daily_path
        elif interval == Interval.MINUTE:
            folder_path = self.minute_path
        else:
            logger.error(f"Unsupported interval {interval.value}")
            return None

        # Read data for each symbol
        dfs: list = []

        for vt_symbol in vt_symbols:
            # Check if file exists
            file_path: Path = folder_path.joinpath(f"{vt_symbol}.parquet")
            if not file_path.exists():
                logger.error(f"File {file_path} does not exist")
                continue

            # Open file
            df: pl.DataFrame = pl.read_parquet(file_path)

            # Filter by date range
            df = df.filter((pl.col("datetime") >= start) & (pl.col("datetime") <= end))

            # Specify data types
            df = df.with_columns(
                pl.col("open"),
                pl.col("high"),
                pl.col("low"),
                pl.col("close"),
                pl.col("volume"),
                pl.col("turnover"),
                pl.col("open_interest"),
                (pl.col("turnover") / pl.col("volume")).alias("vwap")
            )

            # Check for empty data
            if df.is_empty():
                continue

            # Normalize prices
            close_0: float = df.select(pl.col("close")).item(0, 0)

            df = df.with_columns(
                (pl.col("open") / close_0).alias("open"),
                (pl.col("high") / close_0).alias("high"),
                (pl.col("low") / close_0).alias("low"),
                (pl.col("close") / close_0).alias("close"),
            )

            # Convert zeros to NaN for suspended trading days
            numeric_columns: list = df.columns[1:]                              # Extract numeric columns

            mask: pl.Series = df[numeric_columns].sum_horizontal() == 0         # Sum by row, if 0 then suspended

            df = df.with_columns(                                               # Convert suspended day values to NaN
                [pl.when(mask).then(float("nan")).otherwise(pl.col(col)).alias(col) for col in numeric_columns]
            )

            # Add symbol column
            df = df.with_columns(pl.lit(vt_symbol).alias("vt_symbol"))

            # Cache in list
            dfs.append(df)

        # Concatenate results
        result_df: pl.DataFrame = pl.concat(dfs)
        return result_df

    def save_component_data(
        self,
        index_symbol: str,
        index_components: dict[str, list[str]]
    ) -> None:
        """Save index component data"""
        file_path: Path = self.component_path.joinpath(f"{index_symbol}")

        with shelve.open(str(file_path)) as db:
            db.update(index_components)

    @lru_cache      # noqa
    def load_component_data(
        self,
        index_symbol: str,
        start: datetime | str,
        end: datetime | str
    ) -> dict[datetime, list[str]]:
        """Load index component data as DataFrame"""
        file_path: Path = self.component_path.joinpath(f"{index_symbol}")

        start = to_datetime(start)
        end = to_datetime(end)

        with shelve.open(str(file_path)) as db:
            keys: list[str] = list(db.keys())
            keys.sort()

            index_components: dict[datetime, list[str]] = {}
            for key in keys:
                dt: datetime = datetime.strptime(key, "%Y-%m-%d")
                if start <= dt <= end:
                    index_components[dt] = db[key]

            return index_components

    def load_component_symbols(
        self,
        index_symbol: str,
        start: datetime | str,
        end: datetime | str
    ) -> list[str]:
        """Collect index component symbols"""
        index_components: dict[datetime, list[str]] = self.load_component_data(
            index_symbol,
            start,
            end
        )

        component_symbols: set[str] = set()

        for vt_symbols in index_components.values():
            component_symbols.update(vt_symbols)

        return list(component_symbols)

    def load_component_filters(
        self,
        index_symbol: str,
        start: datetime | str,
        end: datetime | str
    ) -> dict[str, list[tuple[datetime, datetime]]]:
        """Collect index component duration filters"""
        index_components: dict[datetime, list[str]] = self.load_component_data(
            index_symbol,
            start,
            end
        )

        # Get all trading dates and sort
        trading_dates: list[datetime] = sorted(index_components.keys())

        # Initialize component duration dictionary
        component_filters: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)

        # Get all component symbols
        all_symbols: set[str] = set()
        for vt_symbols in index_components.values():
            all_symbols.update(vt_symbols)

        # Iterate through each component to identify its duration in the index
        for vt_symbol in all_symbols:
            period_start: datetime | None = None
            period_end: datetime | None = None

            # Iterate through each trading day to identify continuous holding periods
            for trading_date in trading_dates:
                if vt_symbol in index_components[trading_date]:
                    if period_start is None:
                        period_start = trading_date

                    period_end = trading_date
                else:
                    if period_start and period_end:
                        component_filters[vt_symbol].append((period_start, period_end))
                        period_start = None
                        period_end = None

            # Handle the last holding period
            if period_start and period_end:
                component_filters[vt_symbol].append((period_start, period_end))

        return component_filters

    def save_contract_setting(
        self,
        vt_symbol: str,
        size: float,
        pricetick: float,
        long_rate: float = 0,
        short_rate: float = 0
    ) -> None:
        """Add contract information"""
        contracts: dict = {}

        if self.contract_path.exists():
            with open(self.contract_path, encoding="UTF-8") as f:
                contracts = json.load(f)

        contracts[vt_symbol] = {
            "long_rate": long_rate,
            "short_rate": short_rate,
            "size": size,
            "pricetick": pricetick
        }

        with open(self.contract_path, mode="w+", encoding="UTF-8") as f:
            json.dump(
                contracts,
                f,
                indent=4,
                ensure_ascii=False
            )

    def get_contract_setting(self, vt_symbol: str) -> Optional[dict]:
        """Get contract setting for a specific symbol"""
        contracts = self.load_contract_settings()
        return contracts.get(vt_symbol)

    def load_contract_settings(self) -> dict:
        """Load contract settings"""
        contracts: dict = {}

        if self.contract_path.exists():
            with open(self.contract_path, encoding="UTF-8") as f:
                contracts = json.load(f)

        return contracts

    def save_dataset(self, name: str, dataset: AlphaDataset) -> None:
        """Save dataset"""
        file_path: Path = self.dataset_path.joinpath(f"{name}.pkl")

        with open(file_path, mode="wb") as f:
            pickle.dump(dataset, f)

    def load_dataset(self, name: str) -> AlphaDataset | None:
        """Load dataset"""
        file_path: Path = self.dataset_path.joinpath(f"{name}.pkl")
        if not file_path.exists():
            logger.error(f"Dataset file {name} does not exist")
            return None

        with open(file_path, mode="rb") as f:
            dataset: AlphaDataset = pickle.load(f)
            return dataset

    def remove_dataset(self, name: str) -> bool:
        """Remove dataset"""
        file_path: Path = self.dataset_path.joinpath(f"{name}.pkl")
        if not file_path.exists():
            logger.error(f"Dataset file {name} does not exist")
            return False

        file_path.unlink()
        return True

    def list_all_datasets(self) -> list[str]:
        """List all datasets"""
        return [file.stem for file in self.dataset_path.glob("*.pkl")]

    def save_model(self, name: str, model: AlphaModel) -> None:
        """Save model"""
        file_path: Path = self.model_path.joinpath(f"{name}.pkl")

        with open(file_path, mode="wb") as f:
            pickle.dump(model, f)

    def load_model(self, name: str) -> AlphaModel | None:
        """Load model"""
        file_path: Path = self.model_path.joinpath(f"{name}.pkl")
        if not file_path.exists():
            logger.error(f"Model file {name} does not exist")
            return None

        with open(file_path, mode="rb") as f:
            model: AlphaModel = pickle.load(f)
            return model

    def remove_model(self, name: str) -> bool:
        """Remove model"""
        file_path: Path = self.model_path.joinpath(f"{name}.pkl")
        if not file_path.exists():
            logger.error(f"Model file {name} does not exist")
            return False

        file_path.unlink()
        return True

    def list_all_models(self) -> list[str]:
        """List all models"""
        return [file.stem for file in self.model_path.glob("*.pkl")]

    def save_signal(self, name: str, signal: pl.DataFrame) -> None:
        """Save signal"""
        file_path: Path = self.signal_path.joinpath(f"{name}.parquet")

        signal.write_parquet(file_path)

    def load_signal(self, name: str) -> pl.DataFrame | None:
        """Load signal"""
        file_path: Path = self.signal_path.joinpath(f"{name}.parquet")
        if not file_path.exists():
            logger.error(f"Signal file {name} does not exist")
            return None

        return pl.read_parquet(file_path)

    def remove_signal(self, name: str) -> bool:
        """Remove signal"""
        file_path: Path = self.signal_path.joinpath(f"{name}.parquet")
        if not file_path.exists():
            logger.error(f"Signal file {name} does not exist")
            return False

        file_path.unlink()
        return True

    def list_all_signals(self) -> list[str]:
        """List all signals"""
        return [file.stem for file in self.model_path.glob("*.parquet")]

    # ==================== BaseAlphaLab 抽象方法实现 ====================

    def get_component_symbols(
        self,
        index_code: str,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[str]:
        """Get index component symbols (alias for load_component_symbols)"""
        return self.load_component_symbols(index_code, start, end)

    def update_daily_data(
        self,
        symbols: Optional[list[str]] = None,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        incremental: bool = True
    ) -> dict[str, Any]:
        """Update daily data (not implemented in AlphaLab, use data downloader)"""
        raise NotImplementedError("AlphaLab does not support update_daily_data, use external data downloader")

    def get_last_update_date(
        self,
        vt_symbol: str,
        interval: Interval
    ) -> Optional[datetime]:
        """Get last update date for a symbol"""
        if interval == Interval.DAILY:
            folder_path = self.daily_path
        elif interval == Interval.MINUTE:
            folder_path = self.minute_path
        else:
            return None

        file_path = folder_path / f"{vt_symbol}.parquet"
        if not file_path.exists():
            return None

        try:
            df = pl.read_parquet(file_path)
            if df.is_empty():
                return None
            last_datetime = df.select(pl.col("datetime")).tail(1).item()
            return last_datetime
        except Exception:
            return None

    def get_data_coverage(self) -> dict[str, Any]:
        """Get data coverage statistics"""
        daily_files = list(self.daily_path.glob("*.parquet"))
        minute_files = list(self.minute_path.glob("*.parquet"))

        total_symbols = len(set([f.stem for f in daily_files + minute_files]))

        # Find date range
        all_dates = []
        for file_path in daily_files:
            try:
                df = pl.read_parquet(file_path)
                if not df.is_empty():
                    dates = df.select(pl.col("datetime")).to_series().to_list()
                    all_dates.extend(dates)
            except Exception:
                continue

        if all_dates:
            all_dates.sort()
            date_range = {"start": all_dates[0], "end": all_dates[-1]}
            last_update = all_dates[-1]
        else:
            date_range = {"start": None, "end": None}
            last_update = None

        return {
            "total_symbols": total_symbols,
            "daily_files": len(daily_files),
            "minute_files": len(minute_files),
            "date_range": date_range,
            "last_update": last_update,
            "missing_data": []
        }

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

    def switch_project(
        self,
        project_name: str,
        index_code: Optional[str] = None,
        data_source: Optional[str] = None
    ) -> dict[str, Any]:
        """Switch to a new project (AlphaLab does not support dynamic project switching)"""
        raise NotImplementedError(
            "AlphaLab does not support switch_project. "
            "Create a new AlphaLab instance with a different path instead."
        )
