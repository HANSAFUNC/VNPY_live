"""AlphaLab V2 - 视图层，组合数据层和索引层"""
from pathlib import Path
from datetime import datetime, timedelta
from typing import Optional, Union

import polars as pl

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData
from vnpy.trader.utility import extract_vt_symbol

from .data_store import DataStore
from .index_manager import IndexManager
from .dataset.template import AlphaDataset, to_datetime
from .model.template import AlphaModel
from .logger import logger


class AlphaLabV2:
    """
    AlphaLab V2 - 投研实验室（分层架构）

    组合数据层（DataStore）和索引层（IndexManager），提供统一的查询接口。
    支持多个指数共享同一份原始数据。

    目录结构：
    lab/
    ├── data/xt/           # 数据层
    ├── index/csi300/      # 索引层
    └── project/my_strategy/   # 项目层（本类管理）
    """

    def __init__(
        self,
        root_path: str,
        project_name: str,
        data_source: str = "xt",
        index_code: str = "all_a"
    ):
        """
        Parameters
        ----------
        root_path : str
            lab 根目录
        project_name : str
            项目名称，如 "xgb_extrema_csi300"
        data_source : str
            数据源，如 "xt"
        index_code : str
            使用的指数代码，如 "csi300", "csi500", "all_a"
        """
        self.root = Path(root_path)
        self.project_name = project_name
        self.data_source = data_source
        self.index_code = index_code

        # 初始化各层
        self.data_store = DataStore(str(self.root), data_source)
        self.index_manager = IndexManager(str(self.root))

        # 项目目录
        self.project_path = self.root / "project" / project_name
        self.dataset_path = self.project_path / "dataset"
        self.model_path = self.project_path / "model"
        self.signal_path = self.project_path / "signal"

        for path in [self.dataset_path, self.model_path, self.signal_path]:
            path.mkdir(parents=True, exist_ok=True)

        # 合约配置
        self.contract_path = self.project_path / "contract.json"

        logger.info(f"AlphaLabV2 初始化：{project_name}")
        logger.info(f"  数据源：{data_source}")
        logger.info(f"  指数：{index_code}")

    def save_bar_data(self, bars: list[BarData]) -> None:
        """保存 K 线数据到数据层"""
        self.data_store.save_bars(bars)

    def load_bar_df(
        self,
        start: Union[datetime, str],
        end: Union[datetime, str],
        interval: Interval = Interval.DAILY,
        extended_days: int = 0
    ) -> pl.DataFrame:
        """
        加载 K 线数据（自动根据 index_code 过滤成分股）

        Parameters
        ----------
        start : datetime or str
            开始日期
        end : datetime or str
            结束日期
        interval : Interval
            K 线周期
        extended_days : int
            向前后扩展的天数

        Returns
        -------
        pl.DataFrame
            K 线数据，包含 vt_symbol 列
        """
        start = to_datetime(start) - timedelta(days=extended_days)
        end = to_datetime(end) + timedelta(days=extended_days // 10)

        # 获取成分股列表
        symbols = self.index_manager.get_all_symbols(
            self.index_code,
            start,
            end
        )

        logger.info(f"加载 {self.index_code} 成分股数据：{len(symbols)} 只")

        # 加载每只股票的 K 线
        dfs = []
        for vt_symbol in symbols:
            bars = self.data_store.load_bars(vt_symbol, interval, start, end)
            if not bars:
                continue

            # 转换为 DataFrame
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
                    "open_interest": bar.open_interest
                })

            if data:
                df = pl.DataFrame(data)
                df = df.with_columns(pl.lit(vt_symbol).alias("vt_symbol"))
                dfs.append(df)

        if not dfs:
            return pl.DataFrame()

        return pl.concat(dfs)

    def load_component_symbols(
        self,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[str]:
        """加载成分股列表"""
        return self.index_manager.get_all_symbols(
            self.index_code,
            start,
            end
        )

    def load_component_filters(
        self,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> dict[str, list[tuple[datetime, datetime]]]:
        """加载成分股过滤器"""
        return self.index_manager.get_component_filters(
            self.index_code,
            start,
            end
        )

    def save_signal(self, name: str, signal: pl.DataFrame) -> None:
        """保存信号"""
        file_path = self.signal_path / f"{name}.parquet"
        signal.write_parquet(file_path)
        logger.info(f"信号已保存：{file_path}")

    def load_signal(self, name: str) -> Optional[pl.DataFrame]:
        """加载信号"""
        file_path = self.signal_path / f"{name}.parquet"
        if not file_path.exists():
            return None
        return pl.read_parquet(file_path)

    def save_model(self, name: str, model: AlphaModel) -> None:
        """保存模型"""
        import pickle
        file_path = self.model_path / f"{name}.pkl"
        with open(file_path, 'wb') as f:
            pickle.dump(model, f)
        logger.info(f"模型已保存：{file_path}")

    def load_model(self, name: str) -> Optional[AlphaModel]:
        """加载模型"""
        import pickle
        file_path = self.model_path / f"{name}.pkl"
        if not file_path.exists():
            return None
        with open(file_path, 'rb') as f:
            return pickle.load(f)

    def save_dataset(self, name: str, dataset: AlphaDataset) -> None:
        """保存数据集"""
        import pickle
        file_path = self.dataset_path / f"{name}.pkl"
        with open(file_path, 'wb') as f:
            pickle.dump(dataset, f)
        logger.info(f"数据集已保存：{file_path}")

    def load_dataset(self, name: str) -> Optional[AlphaDataset]:
        """加载数据集"""
        import pickle
        file_path = self.dataset_path / f"{name}.pkl"
        if not file_path.exists():
            return None
        with open(file_path, 'rb') as f:
            return pickle.load(f)
