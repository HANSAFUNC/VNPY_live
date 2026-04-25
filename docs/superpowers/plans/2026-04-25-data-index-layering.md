# 数据源与成分股索引分层架构实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 重构 lab 目录结构，将数据源层与成分股索引层分离，支持多个指数（沪深300/中证500/上证50等）共享同一份原始 K 线数据，避免重复下载。

**Architecture:** 采用三层架构：1) Data Layer（按数据源组织原始 K 线数据），2) Index Layer（按指数存储成分股历史），3) View Layer（AlphaLab 提供统一查询接口）。数据流向：迅投 -> Data Layer -> Index Layer（定义股票范围）-> View Layer（组合查询）。

**Tech Stack:** Python, Polars (Parquet), shelve, pathlib, vnpy

---

## 问题分析

当前设计的问题：
```
lab/csi300/          # 数据和索引绑定
├── daily/           # 只包含沪深300成分股的K线
├── component/       # 沪深300成分股历史
└── ...
```

问题：
1. 下载了沪深A股全部5200只股票，但 lab/csi300 这个命名让人以为只有300只
2. 如果想跑中证500策略，需要重复下载大量重叠数据（沪深300和中证500有100+重合）
3. 数据存储分散，无法统一管理和增量更新

---

## 新架构设计

```
lab/
├── data/                    # 数据层（所有原始K线）
│   ├── xt/                  # 迅投数据源
│   │   ├── daily/           # 全部A股日线（5200只）
│   │   ├── minute/          # 分钟线
│   │   └── meta.json        # 数据元信息
│   └── rq/                  # 未来可接入其他数据源
│
├── index/                   # 索引层（成分股定义）
│   ├── csi300/              # 沪深300
│   │   ├── components/      # 历史成分股（shelve）
│   │   └── config.json      # 指数配置
│   ├── csi500/              # 中证500
│   ├── sse50/               # 上证50
│   └── all_a/               # 全A股（伪指数，包含全部）
│
└── project/                 # 项目层（策略工作区）
    ├── xgb_extrema_csi300/  # 具体策略实例
    │   ├── dataset/         # 数据集缓存
    │   ├── model/           # 模型文件
    │   ├── signal/          # 信号输出
    │   └── config.json      # 策略配置（指定数据源+指数）
    └── momentum_csi500/
```

---

## 文件结构变更

**新增文件：**
- `vnpy/alpha/data_store.py` - 数据层管理器（DataStore）
- `vnpy/alpha/index_manager.py` - 索引层管理器（IndexManager）
- `vnpy/alpha/lab_v2.py` - 新的 AlphaLabV2（视图层）
- `examples/migrate_lab.py` - 数据迁移脚本

**修改文件：**
- `examples/alpha_research/download_data_xt.ipynb` - 适配新架构
- `xgb_extrema_selector.py` - 使用新的 Lab API

---

## Task 1: 创建数据层管理器 (DataStore)

**Files:**
- Create: `vnpy/alpha/data_store.py`
- Test: `tests/alpha/test_data_store.py`

- [ ] **Step 1: 创建 DataStore 类骨架**

```python
"""数据层管理器 - 管理原始K线数据存储"""
from pathlib import Path
from datetime import datetime
from typing import Optional
import polars as pl

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData


class DataStore:
    """
    数据层管理器

    职责：
    1. 按数据源（xt/rq）存储原始K线数据
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
            数据源名称，如 "xt"（迅投）、"rq"（ ricequant）
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
        """保存K线数据（同现有 AlphaLab.save_bar_data）"""
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
            raise ValueError(f"不支持的周期: {interval}")

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
        """加载K线数据"""
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
            bars.append(BarData(
                symbol=vt_symbol.split(".")[0],
                exchange=vt_symbol.split(".")[1],
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
            ))

        return bars

    def _update_meta(self, vt_symbol: str, interval: Interval, df: pl.DataFrame):
        """更新数据元信息"""
        import json

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
        import json

        if not self.meta_file.exists():
            return None

        with open(self.meta_file, 'r', encoding='utf-8') as f:
            meta = json.load(f)

        key = f"{vt_symbol}_{interval.value}"
        return meta.get(key)
```

- [ ] **Step 2: 创建测试文件**

Run: `mkdir -p tests/alpha`

```python
# tests/alpha/test_data_store.py
import pytest
from datetime import datetime
from pathlib import Path
import shutil

from vnpy.alpha.data_store import DataStore
from vnpy.trader.constant import Interval, Exchange
from vnpy.trader.object import BarData


@pytest.fixture
def temp_datastore(tmp_path):
    """创建临时数据存储"""
    store = DataStore(str(tmp_path), source="test")
    yield store
    # 清理
    if tmp_path.exists():
        shutil.rmtree(tmp_path)


def test_save_and_load_bars(temp_datastore):
    """测试保存和加载K线数据"""
    # 创建测试数据
    bars = [
        BarData(
            symbol="600519",
            exchange=Exchange.SSE,
            datetime=datetime(2024, 1, 1),
            interval=Interval.DAILY,
            open_price=100.0,
            high_price=105.0,
            low_price=99.0,
            close_price=102.0,
            volume=10000,
            turnover=1000000,
            gateway_name="TEST"
        ),
        BarData(
            symbol="600519",
            exchange=Exchange.SSE,
            datetime=datetime(2024, 1, 2),
            interval=Interval.DAILY,
            open_price=102.0,
            high_price=106.0,
            low_price=101.0,
            close_price=104.0,
            volume=12000,
            turnover=1200000,
            gateway_name="TEST"
        )
    ]

    # 保存
    temp_datastore.save_bars(bars)

    # 加载
    loaded = temp_datastore.load_bars(
        "600519.SSE",
        Interval.DAILY,
        datetime(2024, 1, 1),
        datetime(2024, 1, 2)
    )

    assert len(loaded) == 2
    assert loaded[0].close_price == 102.0
    assert loaded[1].close_price == 104.0


def test_list_symbols(temp_datastore):
    """测试列出股票代码"""
    bars = [
        BarData(
            symbol="600519",
            exchange=Exchange.SSE,
            datetime=datetime(2024, 1, 1),
            interval=Interval.DAILY,
            open_price=100.0,
            high_price=105.0,
            low_price=99.0,
            close_price=102.0,
            volume=10000,
            turnover=1000000,
            gateway_name="TEST"
        )
    ]

    temp_datastore.save_bars(bars)
    symbols = temp_datastore.list_symbols(Interval.DAILY)

    assert "600519.SSE" in symbols
```

- [ ] **Step 3: 运行测试**

Run: `pytest tests/alpha/test_data_store.py -v`

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add vnpy/alpha/data_store.py tests/alpha/test_data_store.py
git commit -m "feat: add DataStore for raw K-line data management"
```

---

## Task 2: 创建索引层管理器 (IndexManager)

**Files:**
- Create: `vnpy/alpha/index_manager.py`
- Test: `tests/alpha/test_index_manager.py`

- [ ] **Step 1: 创建 IndexManager 类**

```python
"""索引层管理器 - 管理指数成分股历史"""
import shelve
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Union
from collections import defaultdict

from vnpy.alpha.logger import logger


class IndexManager:
    """
    索引层管理器

    职责：
    1. 管理各指数的历史成分股数据
    2. 支持按日期查询成分股
    3. 计算成分股的连续持有期
    """

    # 支持的指数配置
    INDEX_CONFIG = {
        "csi300": {
            "name": "沪深300",
            "xt_code": "000300.SH",  # 迅投代码
            "description": "沪深300指数"
        },
        "csi500": {
            "name": "中证500",
            "xt_code": "000905.SH",
            "description": "中证500指数"
        },
        "sse50": {
            "name": "上证50",
            "xt_code": "000016.SH",
            "description": "上证50指数"
        },
        "all_a": {
            "name": "全部A股",
            "xt_code": "沪深A股",  # 迅投板块名称
            "description": "全部沪深A股"
        }
    }

    def __init__(self, root_path: str):
        """
        Parameters
        ----------
        root_path : str
            lab 根目录，如 "./lab"
        """
        self.root = Path(root_path)
        self.index_path = self.root / "index"
        self.index_path.mkdir(parents=True, exist_ok=True)

    def create_index(self, index_code: str, name: str, xt_code: str) -> None:
        """
        创建新指数配置

        Parameters
        ----------
        index_code : str
            指数代码，如 "csi300"
        name : str
            指数名称
        xt_code : str
            迅投代码
        """
        index_dir = self.index_path / index_code
        index_dir.mkdir(exist_ok=True)

        config = {
            "code": index_code,
            "name": name,
            "xt_code": xt_code,
            "created_at": datetime.now().isoformat()
        }

        with open(index_dir / "config.json", 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        logger.info(f"创建指数配置: {index_code} ({name})")

    def save_components(
        self,
        index_code: str,
        date: Union[str, datetime],
        symbols: list[str]
    ) -> None:
        """
        保存某日的成分股列表

        Parameters
        ----------
        index_code : str
            指数代码，如 "csi300"
        date : str or datetime
            日期，如 "2024-01-02"
        symbols : list[str]
            成分股 vt_symbol 列表
        """
        index_dir = self.index_path / index_code
        index_dir.mkdir(exist_ok=True)

        if isinstance(date, datetime):
            date_str = date.strftime("%Y-%m-%d")
        else:
            date_str = date

        # 使用 shelve 存储
        db_path = index_dir / "components"
        with shelve.open(str(db_path)) as db:
            db[date_str] = symbols

    def load_components(
        self,
        index_code: str,
        start: Union[str, datetime],
        end: Union[str, datetime]
    ) -> dict[datetime, list[str]]:
        """
        加载时间范围内的成分股历史

        Parameters
        ----------
        index_code : str
            指数代码
        start : str or datetime
            开始日期
        end : str or datetime
            结束日期

        Returns
        -------
        dict[datetime, list[str]]
            每日成分股列表
        """
        if isinstance(start, str):
            start = datetime.strptime(start, "%Y-%m-%d")
        if isinstance(end, str):
            end = datetime.strptime(end, "%Y-%m-%d")

        index_dir = self.index_path / index_code
        db_path = index_dir / "components"

        if not db_path.exists():
            return {}

        result = {}
        with shelve.open(str(db_path)) as db:
            for key in db.keys():
                dt = datetime.strptime(key, "%Y-%m-%d")
                if start <= dt <= end:
                    result[dt] = db[key]

        return dict(sorted(result.items()))

    def get_all_symbols(
        self,
        index_code: str,
        start: Union[str, datetime],
        end: Union[str, datetime]
    ) -> list[str]:
        """
        获取时间范围内出现过的所有成分股（去重）

        Returns
        -------
        list[str]
            所有出现过的 vt_symbol（去重排序）
        """
        components = self.load_components(index_code, start, end)
        all_symbols = set()
        for symbols in components.values():
            all_symbols.update(symbols)
        return sorted(list(all_symbols))

    def get_component_filters(
        self,
        index_code: str,
        start: Union[str, datetime],
        end: Union[str, datetime]
    ) -> dict[str, list[tuple[datetime, datetime]]]:
        """
        获取成分股的连续持有期（用于回测过滤）

        Returns
        -------
        dict[str, list[tuple[datetime, datetime]]]
            每只股票的在指数中的时间段列表
        """
        components = self.load_components(index_code, start, end)

        # 按日期排序
        dates = sorted(components.keys())

        # 收集每只股票的在榜期间
        symbol_periods: dict[str, list[tuple[datetime, datetime]]] = defaultdict(list)

        for vt_symbol in self.get_all_symbols(index_code, start, end):
            period_start = None
            period_end = None

            for dt in dates:
                if vt_symbol in components[dt]:
                    if period_start is None:
                        period_start = dt
                    period_end = dt
                else:
                    if period_start and period_end:
                        symbol_periods[vt_symbol].append((period_start, period_end))
                        period_start = None
                        period_end = None

            # 处理最后一个持有期
            if period_start and period_end:
                symbol_periods[vt_symbol].append((period_start, period_end))

        return dict(symbol_periods)

    def list_indices(self) -> list[str]:
        """列出所有已配置的指数"""
        return [d.name for d in self.index_path.iterdir() if d.is_dir()]

    def get_index_info(self, index_code: str) -> Optional[dict]:
        """获取指数配置信息"""
        config_file = self.index_path / index_code / "config.json"
        if not config_file.exists():
            return None

        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
```

- [ ] **Step 2: 创建测试**

```python
# tests/alpha/test_index_manager.py
import pytest
from datetime import datetime
from pathlib import Path
import shutil

from vnpy.alpha.index_manager import IndexManager


@pytest.fixture
def temp_index_manager(tmp_path):
    """创建临时索引管理器"""
    mgr = IndexManager(str(tmp_path))
    yield mgr
    # 清理
    if tmp_path.exists():
        shutil.rmtree(tmp_path)


def test_create_index(temp_index_manager):
    """测试创建指数"""
    temp_index_manager.create_index(
        "test_index",
        "测试指数",
        "000001.SH"
    )

    indices = temp_index_manager.list_indices()
    assert "test_index" in indices


def test_save_and_load_components(temp_index_manager):
    """测试保存和加载成分股"""
    # 创建指数
    temp_index_manager.create_index("csi300", "沪深300", "000300.SH")

    # 保存成分股
    temp_index_manager.save_components(
        "csi300",
        "2024-01-02",
        ["600519.SSE", "000001.SZSE", "000858.SZSE"]
    )

    temp_index_manager.save_components(
        "csi300",
        "2024-01-03",
        ["600519.SSE", "000001.SZSE"]  # 000858 被移出
    )

    # 加载
    components = temp_index_manager.load_components(
        "csi300",
        "2024-01-02",
        "2024-01-03"
    )

    assert len(components) == 2
    assert "000858.SZSE" in components[datetime(2024, 1, 2)]
    assert "000858.SZSE" not in components[datetime(2024, 1, 3)]


def test_get_all_symbols(temp_index_manager):
    """测试获取所有股票代码"""
    temp_index_manager.create_index("csi300", "沪深300", "000300.SH")

    temp_index_manager.save_components(
        "csi300",
        "2024-01-02",
        ["600519.SSE", "000001.SZSE"]
    )

    temp_index_manager.save_components(
        "csi300",
        "2024-01-03",
        ["600519.SSE", "000858.SZSE"]
    )

    all_symbols = temp_index_manager.get_all_symbols(
        "csi300",
        "2024-01-02",
        "2024-01-03"
    )

    assert len(all_symbols) == 3
    assert "600519.SSE" in all_symbols
    assert "000001.SZSE" in all_symbols
    assert "000858.SZSE" in all_symbols
```

- [ ] **Step 3: 运行测试**

Run: `pytest tests/alpha/test_index_manager.py -v`

Expected: PASS

- [ ] **Step 4: 提交**

```bash
git add vnpy/alpha/index_manager.py tests/alpha/test_index_manager.py
git commit -m "feat: add IndexManager for index component management"
```

---

## Task 3: 创建新的 AlphaLabV2（视图层）

**Files:**
- Create: `vnpy/alpha/lab_v2.py`
- Test: `tests/alpha/test_lab_v2.py`

- [ ] **Step 1: 创建 AlphaLabV2 类**

```python
"""AlphaLab V2 - 视图层，组合数据层和索引层"""
from pathlib import Path
from datetime import datetime
from typing import Optional

import polars as pl

from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData
from vnpy.trader.utility import extract_vt_symbol

from .data_store import DataStore
from .index_manager import IndexManager
from .dataset import AlphaDataset, to_datetime
from .model import AlphaModel
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

        logger.info(f"AlphaLabV2 初始化: {project_name}")
        logger.info(f"  数据源: {data_source}")
        logger.info(f"  指数: {index_code}")

    def save_bar_data(self, bars: list[BarData]) -> None:
        """保存K线数据到数据层"""
        self.data_store.save_bars(bars)

    def load_bar_df(
        self,
        start: datetime | str,
        end: datetime | str,
        interval: Interval = Interval.DAILY,
        extended_days: int = 0
    ) -> pl.DataFrame:
        """
        加载K线数据（自动根据 index_code 过滤成分股）

        Parameters
        ----------
        start : datetime or str
            开始日期
        end : datetime or str
            结束日期
        interval : Interval
            K线周期
        extended_days : int
            向前后扩展的天数

        Returns
        -------
        pl.DataFrame
            K线数据，包含 vt_symbol 列
        """
        start = to_datetime(start) - __import__('datetime').timedelta(days=extended_days)
        end = to_datetime(end) + __import__('datetime').timedelta(days=extended_days // 10)

        # 获取成分股列表
        symbols = self.index_manager.get_all_symbols(
            self.index_code,
            start,
            end
        )

        logger.info(f"加载 {self.index_code} 成分股数据: {len(symbols)} 只")

        # 加载每只股票的K线
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
        start: datetime | str,
        end: datetime | str
    ) -> list[str]:
        """加载成分股列表"""
        return self.index_manager.get_all_symbols(
            self.index_code,
            start,
            end
        )

    def load_component_filters(
        self,
        start: datetime | str,
        end: datetime | str
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
        logger.info(f"信号已保存: {file_path}")

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
        logger.info(f"模型已保存: {file_path}")

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
        logger.info(f"数据集已保存: {file_path}")

    def load_dataset(self, name: str) -> Optional[AlphaDataset]:
        """加载数据集"""
        import pickle
        file_path = self.dataset_path / f"{name}.pkl"
        if not file_path.exists():
            return None
        with open(file_path, 'rb') as f:
            return pickle.load(f)
```

- [ ] **Step 2: 运行测试**

Run: `pytest tests/alpha/test_lab_v2.py -v`

Expected: PASS

- [ ] **Step 3: 提交**

```bash
git add vnpy/alpha/lab_v2.py tests/alpha/test_lab_v2.py
git commit -m "feat: add AlphaLabV2 with layered architecture"
```

---

## Task 4: 创建数据迁移脚本

**Files:**
- Create: `examples/migrate_lab.py`

- [ ] **Step 1: 编写迁移脚本**

```python
#!/usr/bin/env python
"""
Lab 数据迁移脚本

将旧的 lab/csi300 结构迁移到新的分层架构：
- K线数据 -> lab/data/xt/daily/
- 成分股数据 -> lab/index/all_a/components/
- 项目数据 -> lab/project/{name}/
"""
import shutil
from pathlib import Path
from datetime import datetime
import shelve

from vnpy.alpha.data_store import DataStore
from vnpy.alpha.index_manager import IndexManager
from vnpy.alpha.lab import AlphaLab
from vnpy.trader.constant import Interval


def migrate_lab(old_lab_path: str, new_lab_path: str):
    """
    迁移 lab 数据

    Parameters
    ----------
    old_lab_path : str
        旧的 lab 路径，如 "./lab/csi300"
    new_lab_path : str
        新的 lab 根路径，如 "./lab"
    """
    old_path = Path(old_lab_path)
    new_path = Path(new_lab_path)

    print("=" * 60)
    print("Lab 数据迁移")
    print("=" * 60)
    print(f"旧路径: {old_path.absolute()}")
    print(f"新路径: {new_path.absolute()}")
    print()

    # 初始化新的数据层
    data_store = DataStore(str(new_path), source="xt")
    index_manager = IndexManager(str(new_path))

    # 1. 迁移 K 线数据
    print("1. 迁移 K 线数据...")
    old_daily = old_path / "daily"
    if old_daily.exists():
        parquet_files = list(old_daily.glob("*.parquet"))
        print(f"   找到 {len(parquet_files)} 个日线文件")

        for file_path in parquet_files:
            # 直接复制 parquet 文件
            vt_symbol = file_path.stem
            new_path_file = data_store.daily_path / f"{vt_symbol}.parquet"
            shutil.copy2(file_path, new_path_file)

        print(f"   [OK] 已迁移到: {data_store.daily_path}")

    # 2. 迁移成分股数据（作为 all_a 指数）
    print("\n2. 迁移成分股数据...")
    old_component = old_path / "component"
    if old_component.exists():
        # 创建 all_a 指数
        index_manager.create_index("all_a", "全部A股", "沪深A股")

        # 迁移 shelve 文件
        for shelve_file in old_component.glob("*"):
            if not shelve_file.is_file() or shelve_file.suffix:
                continue

            index_code = shelve_file.name
            print(f"   迁移指数: {index_code}")

            # 读取旧的 shelve
            with shelve.open(str(shelve_file)) as old_db:
                for date_str, symbols in old_db.items():
                    index_manager.save_components("all_a", date_str, symbols)

        print(f"   [OK] 已迁移到: {index_manager.index_path / 'all_a'}")

    # 3. 迁移项目数据
    print("\n3. 迁移项目数据...")
    old_project_dirs = ["dataset", "model", "signal"]
    for dir_name in old_project_dirs:
        old_dir = old_path / dir_name
        if old_dir.exists():
            # 默认迁移到 project/default 下
            new_project_dir = new_path / "project" / "default" / dir_name
            new_project_dir.mkdir(parents=True, exist_ok=True)

            for file in old_dir.glob("*"):
                shutil.copy2(file, new_project_dir / file.name)

            print(f"   [OK] {dir_name} -> {new_project_dir}")

    # 4. 迁移合约配置
    print("\n4. 迁移合约配置...")
    old_contract = old_path / "contract.json"
    if old_contract.exists():
        new_contract = new_path / "project" / "default" / "contract.json"
        new_contract.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_contract, new_contract)
        print(f"   [OK] contract.json -> {new_contract}")

    print("\n" + "=" * 60)
    print("迁移完成!")
    print("=" * 60)
    print(f"新架构路径: {new_path.absolute()}")
    print()
    print("目录结构:")
    print(f"  - K线数据: {data_store.daily_path}")
    print(f"  - 成分股:  {index_manager.index_path}/all_a")
    print(f"  - 项目:    {new_path}/project/default")
    print()
    print("提示：修改你的代码使用 AlphaLabV2:")
    print("  from vnpy.alpha.lab_v2 import AlphaLabV2")
    print('  lab = AlphaLabV2("./lab", "my_strategy", "xt", "all_a")')


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="迁移 Lab 数据到新架构")
    parser.add_argument(
        "--old",
        default="lab/csi300",
        help="旧的 lab 路径"
    )
    parser.add_argument(
        "--new",
        default="lab",
        help="新的 lab 根路径"
    )

    args = parser.parse_args()
    migrate_lab(args.old, args.new)
```

- [ ] **Step 2: 提交**

```bash
git add examples/migrate_lab.py
git commit -m "feat: add lab migration script for new architecture"
```

---

## Task 5: 更新下载脚本

**Files:**
- Modify: `examples/alpha_research/download_data_xt.ipynb`

- [ ] **Step 1: 更新下载脚本使用新架构**

```python
# 新版本的下载脚本片段
from vnpy.alpha.data_store import DataStore
from vnpy.alpha.index_manager import IndexManager
from vnpy.trader.constant import Interval, Exchange
from vnpy.trader.object import HistoryRequest
from vnpy.trader.datafeed import get_datafeed

# 初始化数据层和索引层
data_store = DataStore("./lab", source="xt")
index_manager = IndexManager("./lab")

# 创建 all_a 指数（如果不存在）
index_manager.create_index("all_a", "全部A股", "沪深A股")

# 下载全部A股数据（只下载一次）
datafeed = get_datafeed()

# 获取全部A股列表
from xtquant import xtdata
all_stocks = xtdata.get_stock_list_in_sector('沪深A股')

for xt_symbol in tqdm(all_stocks):
    symbol = xt_symbol.replace(".SH", "").replace(".SZ", "")
    exchange = Exchange.SSE if ".SH" in xt_symbol else Exchange.SZSE

    req = HistoryRequest(
        symbol=symbol,
        exchange=exchange,
        start=start_date,
        end=end_date,
        interval=Interval.DAILY
    )

    bars = datafeed.query_bar_history(req)
    if bars:
        data_store.save_bars(bars)

# 保存每日成分股（沪深300、中证500等）
from xtquant import xtdata

dates = xtdata.get_trading_dates(market="SZ", start_time=start_date, end_time=end_date)

for ts in dates:
    dt = datetime.fromtimestamp(ts / 1000)
    date_str = dt.strftime("%Y%m%d")

    # 获取沪深300成分股
    csi300_codes = xtdata.get_index_weight('000300.SH')
    csi300_symbols = [code.replace(".SH", ".SSE").replace(".SZ", ".SZSE")
                      for code in csi300_codes.keys()]
    index_manager.save_components("csi300", date_str, csi300_symbols)

    # 获取中证500成分股
    csi500_codes = xtdata.get_index_weight('000905.SH')
    csi500_symbols = [code.replace(".SH", ".SSE").replace(".SZ", ".SZSE")
                      for code in csi500_codes.keys()]
    index_manager.save_components("csi500", date_str, csi500_symbols)
```

- [ ] **Step 2: 提交**

```bash
git add examples/alpha_research/download_data_xt.ipynb
git commit -m "feat: update download script for layered architecture"
```

---

## 总结

**新架构优势：**

1. **数据复用**：一份原始数据可被多个指数使用，避免重复下载
2. **灵活切换**：策略可以在沪深300/中证500/上证50之间快速切换
3. **扩展性**：支持接入多个数据源（迅投、RQ、Tushare等）
4. **维护性**：清晰的职责分离，数据层、索引层、视图层各司其职

**使用示例：**

```python
# 沪深300策略
lab_300 = AlphaLabV2("./lab", "my_strategy_300", "xt", "csi300")
df_300 = lab_300.load_bar_df("2024-01-01", "2024-12-31")

# 中证500策略（使用同一批原始数据）
lab_500 = AlphaLabV2("./lab", "my_strategy_500", "xt", "csi500")
df_500 = lab_500.load_bar_df("2024-01-01", "2024-12-31")

# 全A股策略
lab_all = AlphaLabV2("./lab", "my_strategy_all", "xt", "all_a")
df_all = lab_all.load_bar_df("2024-01-01", "2024-12-31")
```

**Plan complete and saved to `docs/superpowers/plans/2026-04-25-data-index-layering.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**