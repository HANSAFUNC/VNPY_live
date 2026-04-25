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
            "name": "沪深 300",
            "xt_code": "000300.SH",
            "description": "沪深 300 指数"
        },
        "csi500": {
            "name": "中证 500",
            "xt_code": "000905.SH",
            "description": "中证 500 指数"
        },
        "sse50": {
            "name": "上证 50",
            "xt_code": "000016.SH",
            "description": "上证 50 指数"
        },
        "all_a": {
            "name": "全部 A 股",
            "xt_code": "沪深 A 股",
            "description": "全部沪深 A 股"
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

        logger.info(f"创建指数配置：{index_code} ({name})")

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
