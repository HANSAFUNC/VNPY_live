"""StockAI 工具函数模块"""

import logging
from datetime import datetime
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
