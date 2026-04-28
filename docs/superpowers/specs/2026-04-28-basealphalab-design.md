# BaseAlphaLab + AlphaLabV2Engine 设计规范

> **日期:** 2026-04-28  
> **主题:** AlphaLab 抽象基类封装与 V2 引擎实现

---

## 1. 设计目标

1. **统一接口**: 定义 `BaseAlphaLab` 抽象基类，规范所有 Lab 的数据访问和更新接口
2. **引擎化**: `AlphaLabV2Engine` 继承 `BaseEngine`，可作为标准引擎注册到 `MainEngine`
3. **向后兼容**: 旧版 `AlphaLab` 保持独立，新版 `AlphaLabV2Engine` 走引擎架构
4. **分层架构**: V2 版本组合 `DataStore` + `IndexManager`，支持多数据源和指数成分股管理

---

## 2. 架构设计

### 2.1 类层次结构

```
┌─────────────────────────────────────────────────────────────┐
│                      BaseAlphaLab (ABC)                      │
│                   完整接口定义 + 工具方法                     │
├─────────────────────────────────────────────────────────────┤
│  数据查询接口 (抽象方法)                                      │
│    - load_bars(vt_symbol, interval, start, end)            │
│    - load_bars_df(symbols, interval, start, end)           │
│    - get_component_symbols(index_code, start, end)         │
│    - load_contract_settings()                              │
│    - get_contract_setting(vt_symbol)                       │
├─────────────────────────────────────────────────────────────┤
│  数据更新接口 (抽象方法)                                      │
│    - save_bars(bars)                                       │
│    - save_contract_setting(vt_symbol, ...)                 │
│    - update_daily_data(symbols, start, end, incremental)   │
│    - get_last_update_date(vt_symbol, interval)             │
│    - get_data_coverage()                                   │
├─────────────────────────────────────────────────────────────┤
│  通用工具方法 (具体实现)                                      │
│    - _to_datetime(), _normalize_symbol()                   │
│    - _bar_to_dict(), _dict_to_bar()                        │
│    - _ensure_path(), _extract_vt_symbol()                  │
└─────────────────────────────────────────────────────────────┘
            ▲                           ▲
            │                           │
    ┌───────┘                           └───────┐
    │                                           │
AlphaLab                                    AlphaLabV2Engine
(旧版，直接实现)                           (新版，组合实现)
    │                                           │
    │    ┌──────────────────────────────────────┘
    │    │
    │    ├── 继承 BaseAlphaLab (数据接口)
    │    ├── 继承 BaseEngine (引擎接口)
    │    └── 注册到 MainEngine
    │
    └── 独立使用，不注册到 MainEngine

AlphaLabV2Engine 内部组合:
    - DataStore: 管理原始 K 线数据 (data/xt/, data/rq/)
    - IndexManager: 管理指数成分股 (index/csi300/, index/csi500/)
    - project_path: 项目特定数据 (project/{name}/)
```

### 2.2 与 MainEngine 集成

```python
# 启动时注册引擎
main_engine = MainEngine(event_engine)

# 添加 Lab 引擎
lab_engine = AlphaLabV2Engine(
    main_engine=main_engine,
    event_engine=event_engine,
    root_path="./lab",
    project_name="xgb_extrema",
    data_source="xt",
    index_code="csi300"
)
main_engine.add_engine(lab_engine)

# TradeEngine 获取 Lab 引用
class TradeEngine(BaseEngine):
    def __init__(self, ...):
        # 方式1: 通过引擎名称获取
        self.lab = self.main_engine.get_engine("AlphaLabV2")
        
        # 方式2: 使用默认 Lab（向后兼容）
        if not self.lab:
            from vnpy.alpha import AlphaLab
            self.lab = AlphaLab("./lab/csi300")
```

---

## 3. 接口详细规范

### 3.1 BaseAlphaLab 抽象基类

```python
from abc import ABC, abstractmethod
from typing import Optional, Union, Any
from datetime import datetime
from pathlib import Path

import polars as pl
from vnpy.trader.constant import Interval
from vnpy.trader.object import BarData


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
                "failed": list[tuple[str, str]],  # (symbol, error_msg)
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
        from vnpy.trader.object import BarData
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
```

---

## 4. 实现类规范

### 4.1 AlphaLabV2Engine (新版)

```python
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.event import EventEngine

from .base import BaseAlphaLab
from .data_store import DataStore
from .index_manager import IndexManager


class AlphaLabV2Engine(BaseAlphaLab, BaseEngine):
    """AlphaLab V2 引擎
    
    继承 BaseAlphaLab 实现数据接口，继承 BaseEngine 注册到 MainEngine。
    组合 DataStore 和 IndexManager 实现分层数据管理。
    """
    
    engine_name: str = "AlphaLabV2"
    
    def __init__(
        self,
        main_engine: MainEngine,
        event_engine: EventEngine,
        root_path: str,
        project_name: str,
        data_source: str = "xt",
        index_code: str = "all_a"
    ):
        """
        Parameters
        ----------
        main_engine : MainEngine
            主引擎引用
        event_engine : EventEngine
            事件引擎
        root_path : str
            Lab 根目录，如 "./lab"
        project_name : str
            项目名称，如 "xgb_extrema_csi300"
        data_source : str
            数据源名称，如 "xt", "rq"
        index_code : str
            指数代码，如 "csi300", "csi500", "all_a"
        """
        # 初始化 BaseEngine
        BaseEngine.__init__(self, main_engine, event_engine, self.engine_name)
        
        # 初始化配置
        self.root = Path(root_path)
        self.project_name = project_name
        self.data_source = data_source
        self.index_code = index_code
        
        # 组合数据层和索引层
        self.data_store = DataStore(str(self.root), data_source)
        self.index_manager = IndexManager(str(self.root))
        
        # 项目目录
        self.project_path = self.root / "project" / project_name
        self.dataset_path = self.project_path / "dataset"
        self.model_path = self.project_path / "model"
        self.signal_path = self.project_path / "signal"
        
        for path in [self.dataset_path, self.model_path, self.signal_path]:
            self._ensure_path(path)
        
        self.contract_path = self.project_path / "contract.json"
        
        self.write_log(f"AlphaLabV2Engine 初始化: {project_name}")
    
    # ========== BaseAlphaLab 接口实现 ==========
    
    def load_bars(
        self,
        vt_symbol: str,
        interval: Interval,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[BarData]:
        """实现：委托给 DataStore"""
        start = self._to_datetime(start)
        end = self._to_datetime(end)
        return self.data_store.load_bars(vt_symbol, interval, start, end)
    
    def load_bars_df(
        self,
        vt_symbols: list[str],
        interval: Interval,
        start: Union[datetime, str],
        end: Union[datetime, str],
        extended_days: int = 0
    ) -> Optional[pl.DataFrame]:
        """实现：根据 index_code 自动获取成分股"""
        # 如果没有指定 symbols，使用当前指数成分股
        if not vt_symbols:
            vt_symbols = self.get_component_symbols(self.index_code, start, end)
        
        # 委托给 DataStore
        start = self._to_datetime(start) - timedelta(days=extended_days)
        end = self._to_datetime(end)
        return self.data_store.load_bars_df(vt_symbols, interval, start, end)
    
    def get_component_symbols(
        self,
        index_code: str,
        start: Union[datetime, str],
        end: Union[datetime, str]
    ) -> list[str]:
        """实现：委托给 IndexManager"""
        start = self._to_datetime(start)
        end = self._to_datetime(end)
        return self.index_manager.get_all_symbols(index_code, start, end)
    
    def load_contract_settings(self) -> dict[str, dict]:
        """实现：从项目目录加载"""
        if self.contract_path.exists():
            with open(self.contract_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    
    def get_contract_setting(self, vt_symbol: str) -> Optional[dict]:
        """实现：从配置中查找"""
        settings = self.load_contract_settings()
        return settings.get(vt_symbol)
    
    def save_bars(self, bars: list[BarData]) -> None:
        """实现：委托给 DataStore"""
        self.data_store.save_bars(bars)
    
    def save_contract_setting(
        self,
        vt_symbol: str,
        size: float,
        pricetick: float,
        long_rate: float = 0,
        short_rate: float = 0
    ) -> None:
        """实现：保存到项目目录"""
        settings = self.load_contract_settings()
        settings[vt_symbol] = {
            "size": size,
            "pricetick": pricetick,
            "long_rate": long_rate,
            "short_rate": short_rate
        }
        with open(self.contract_path, 'w', encoding='utf-8') as f:
            json.dump(settings, f, indent=4, ensure_ascii=False)
    
    def update_daily_data(
        self,
        symbols: Optional[list[str]] = None,
        start_date: Optional[Union[str, datetime]] = None,
        end_date: Optional[Union[str, datetime]] = None,
        incremental: bool = True
    ) -> dict[str, Any]:
        """实现：从数据源下载并更新"""
        # 自动获取成分股
        if not symbols:
            end = self._to_datetime(end_date) if end_date else datetime.now()
            start = self._to_datetime(start_date) if start_date else end - timedelta(days=365)
            symbols = self.get_component_symbols(self.index_code, start, end)
        
        result = {
            "success": [],
            "failed": [],
            "skipped": [],
            "total_count": len(symbols),
            "updated_count": 0,
            "time_range": (start_date, end_date)
        }
        
        for symbol in symbols:
            try:
                # 检查是否需要更新
                if incremental:
                    last_date = self.get_last_update_date(symbol, Interval.DAILY)
                    if last_date and last_date.date() >= datetime.now().date():
                        result["skipped"].append(symbol)
                        continue
                
                # 从数据源下载（通过 MainEngine 获取 Gateway）
                # 或使用独立的数据服务
                bars = self._download_from_source(symbol, start_date, end_date)
                
                if bars:
                    self.save_bars(bars)
                    result["success"].append(symbol)
                    result["updated_count"] += 1
                else:
                    result["failed"].append((symbol, "无数据"))
                    
            except Exception as e:
                result["failed"].append((symbol, str(e)))
        
        return result
    
    def get_last_update_date(self, vt_symbol: str, interval: Interval) -> Optional[datetime]:
        """实现：查询 DataStore 元信息"""
        return self.data_store.get_last_update(vt_symbol, interval)
    
    def get_data_coverage(self) -> dict[str, Any]:
        """实现：统计 DataStore"""
        return self.data_store.get_coverage()
    
    def switch_project(
        self,
        project_name: str,
        index_code: Optional[str] = None,
        data_source: Optional[str] = None
    ) -> dict[str, Any]:
        """实现：切换实验项目"""
        old_project = self.project_name
        old_index = self.index_code
        old_source = self.data_source
        
        try:
            # 更新配置
            self.project_name = project_name
            if index_code:
                self.index_code = index_code
            if data_source:
                self.data_source = data_source
                # 数据源改变时需要重新初始化 DataStore
                self.data_store = DataStore(str(self.root), self.data_source)
            
            # 更新项目目录
            self.project_path = self.root / "project" / project_name
            self.dataset_path = self.project_path / "dataset"
            self.model_path = self.project_path / "model"
            self.signal_path = self.project_path / "signal"
            
            for path in [self.dataset_path, self.model_path, self.signal_path]:
                self._ensure_path(path)
            
            self.contract_path = self.project_path / "contract.json"
            
            # 触发项目切换事件（供其他组件监听）
            self.event_engine.put(Event(EVENT_PROJECT_SWITCHED, {
                "old_project": old_project,
                "new_project": project_name,
                "index_code": self.index_code,
                "data_source": self.data_source
            }))
            
            self.write_log(f"切换到项目: {project_name} (指数: {self.index_code})")
            
            return {
                "success": True,
                "old_project": old_project,
                "new_project": project_name,
                "index_code": self.index_code,
                "data_source": self.data_source,
                "message": f"成功切换到 {project_name}"
            }
            
        except Exception as e:
            # 回滚配置
            self.project_name = old_project
            self.index_code = old_index
            self.data_source = old_source
            
            return {
                "success": False,
                "old_project": old_project,
                "new_project": project_name,
                "index_code": old_index,
                "data_source": old_source,
                "message": f"切换失败: {str(e)}"
            }
    
    def list_projects(self) -> list[str]:
        """实现：列出所有项目"""
        project_root = self.root / "project"
        if not project_root.exists():
            return []
        return [d.name for d in project_root.iterdir() if d.is_dir()]
    
    # ========== 内部方法 ==========
    
    def _download_from_source(
        self,
        vt_symbol: str,
        start: Optional[datetime],
        end: Optional[datetime]
    ) -> list[BarData]:
        """从数据源下载数据（内部实现）"""
        # 方式1: 通过 MainEngine 的 Gateway
        gateway = self.main_engine.get_gateway(self.data_source)
        if gateway:
            # 调用 Gateway 的历史数据接口
            pass
        
        # 方式2: 使用独立的数据服务
        if self.data_source == "xt":
            from xtquant import xtdata
            # ... 调用迅投接口
            pass
        
        return []
```

### 事件定义

```python
# AlphaLab 相关事件常量
EVENT_PROJECT_SWITCHED = "eProjectSwitched"

# 项目切换事件数据格式
{
    "old_project": str,    # 原项目名称
    "new_project": str,    # 新项目名称
    "index_code": str,     # 当前指数代码
    "data_source": str     # 当前数据源
}
```

### 4.2 AlphaLab (旧版兼容)

```python
class AlphaLab(BaseAlphaLab):
    """AlphaLab 旧版实现（保持兼容）
    
    直接使用本地文件存储，不注册到 MainEngine。
    目录结构: lab/{daily,minute,component,dataset,model,signal}/
    """
    
    def __init__(self, lab_path: str):
        """
        Parameters
        ----------
        lab_path : str
            Lab 目录路径，如 "./lab/csi300"
        """
        self.lab_path = Path(lab_path)
        
        # 子目录
        self.daily_path = self.lab_path / "daily"
        self.minute_path = self.lab_path / "minute"
        self.component_path = self.lab_path / "component"
        self.dataset_path = self.lab_path / "dataset"
        self.model_path = self.lab_path / "model"
        self.signal_path = self.lab_path / "signal"
        
        for path in [self.daily_path, self.minute_path, self.component_path,
                     self.dataset_path, self.model_path, self.signal_path]:
            self._ensure_path(path)
        
        self.contract_path = self.lab_path / "contract.json"
    
    # 实现 BaseAlphaLab 所有抽象方法...
    # （保留原有 AlphaLab 实现逻辑）
```

---

## 5. 使用示例

### 5.1 新版引擎模式（推荐）

```python
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.alpha import AlphaLabV2Engine

# 1. 创建引擎
event_engine = EventEngine()
main_engine = MainEngine(event_engine)

# 2. 添加 Lab 引擎
lab_engine = AlphaLabV2Engine(
    main_engine=main_engine,
    event_engine=event_engine,
    root_path="./lab",
    project_name="xgb_extrema",
    data_source="xt",
    index_code="csi300"
)
main_engine.add_engine(lab_engine)

# 3. TradeEngine 自动获取 Lab
from vnpy.alpha.strategy import TradeEngine
trade_engine = TradeEngine(
    main_engine=main_engine,
    event_engine=event_engine,
    # lab 参数可选，不传时自动从 main_engine 获取
    gateway_name="XT",
    paper_trading=True
)

# 4. 每日更新数据
result = lab_engine.update_daily_data(incremental=True)
print(f"更新成功: {len(result['success'])}, 失败: {len(result['failed'])}")

# 5. 查询数据
bars = lab_engine.load_bars("600519.SSE", Interval.DAILY, "2024-01-01", "2024-12-31")
symbols = lab_engine.get_component_symbols("csi300", "2024-01-01", "2024-12-31")
```

### 5.2 旧版独立模式（兼容）

```python
from vnpy.alpha import AlphaLab

# 直接使用，不注册到 MainEngine
lab = AlphaLab("./lab/csi300")

# 使用相同接口
bars = lab.load_bars("600519.SSE", Interval.DAILY, "2024-01-01", "2024-12-31")
lab.save_bars(bars)
```

---

## 6. 文件结构

```
vnpy/alpha/
├── __init__.py                    # 导出: AlphaLab, AlphaLabV2Engine, BaseAlphaLab
├── base.py                        # BaseAlphaLab 抽象基类
├── lab.py                         # AlphaLab 旧版实现
├── lab_v2.py                      # AlphaLabV2Engine 新版实现
├── data_store.py                  # DataStore 数据层
├── index_manager.py               # IndexManager 索引层
└── ...

Lab 目录结构 (V2):
lab/
├── data/
│   ├── xt/                        # 迅投数据源
│   │   ├── daily/
│   │   ├── minute/
│   │   └── meta.json
│   └── rq/                        # Ricequant 数据源
│       ├── daily/
│       ├── minute/
│       └── meta.json
├── index/
│   ├── csi300/                    # 沪深300成分股
│   ├── csi500/                    # 中证500成分股
│   └── all_a/                     # 全A股
└── project/
    └── xgb_extrema/               # 具体项目
        ├── dataset/
        ├── model/
        ├── signal/
        └── contract.json
```

---

## 7. 自我检查

### 7.1 架构一致性
- ✅ BaseAlphaLab 定义完整接口契约
- ✅ AlphaLabV2Engine 继承 BaseEngine + BaseAlphaLab
- ✅ AlphaLab 保持独立实现
- ✅ TradeEngine 可通过 main_engine.get_engine() 获取 Lab

### 7.2 向后兼容
- ✅ 旧版 AlphaLab 代码无需修改
- ✅ 新版 AlphaLabV2Engine 使用相同接口
- ✅ TradeEngine 支持两种获取 Lab 方式

### 7.3 扩展性
- ✅ 支持多数据源（xt, rq）
- ✅ 支持多指数（csi300, csi500, all_a）
- ✅ 分层架构便于单独扩展数据层/索引层

---

## 8. 实施步骤

1. **创建 `vnpy/alpha/base.py`** - BaseAlphaLab 抽象基类
2. **修改 `vnpy/alpha/lab.py`** - 让 AlphaLab 继承 BaseAlphaLab
3. **创建 `vnpy/alpha/lab_v2.py`** - AlphaLabV2Engine 实现
4. **更新 `vnpy/alpha/__init__.py`** - 导出新类
5. **测试** - 验证旧版兼容性和新版功能

---

**设计完成，等待实施。**
