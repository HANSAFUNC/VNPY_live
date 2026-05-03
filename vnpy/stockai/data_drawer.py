"""StockAI 数据抽屉 - 全局持久化存储管理"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import joblib
import polars as pl

from .utils import get_timestamp, load_json, load_parquet, save_json, save_parquet

logger = logging.getLogger(__name__)


class StockaiDataDrawer:
    """
    全局数据存储管理器

    职责:
    - 存储每只股票元数据（模型文件名、训练时间戳）
    - 缓存已加载的模型在内存中
    - 持久化预测历史到磁盘
    - 管理模型版本

    对应 FreqAI 的 FreqaiDataDrawer 类
    """

    def __init__(self, full_path: Path, config: dict):
        """
        初始化数据抽屉

        参数:
            full_path: 数据存储根目录
            config: 配置字典
        """
        self.config = config
        self.full_path = full_path
        self.full_path.mkdir(parents=True, exist_ok=True)

        # 内存存储结构
        self.pair_dict: dict[str, dict] = {}  # {股票代码: 元数据}
        self.model_dictionary: dict[str, Any] = {}  # {文件名: 模型对象}
        self.historic_predictions: dict[str, pl.DataFrame] = {}  # {股票代码: 预测历史}

        # 文件路径
        self.historic_predictions_path = full_path / "historic_predictions.parquet"
        self.pair_dictionary_path = full_path / "pair_dictionary.json"

        # 从磁盘加载已有数据
        self._load_from_disk()

        logger.info(f"数据抽屉初始化完成，路径: {full_path}")

    def _load_from_disk(self) -> None:
        """从磁盘加载已有数据"""
        # 加载股票元数据
        data = load_json(self.pair_dictionary_path)
        if data:
            self.pair_dict = data
            logger.info(f"已加载 {len(self.pair_dict)} 只股票的元数据")

        # 加载预测历史
        df = load_parquet(self.historic_predictions_path)
        if df is not None:
            for pair in df["pair"].unique().to_list():
                self.historic_predictions[pair] = df.filter(pl.col("pair") == pair)
            logger.info(f"已加载 {len(self.historic_predictions)} 只股票的历史预测")

    def _generate_model_filename(self, pair: str, timestamp: int) -> str:
        """生成模型文件名"""
        safe_pair = pair.replace(".", "_")
        return f"sub-train-{safe_pair}_{timestamp}"

    def save_model(self, pair: str, model: Any, timestamp: int) -> None:
        """
        保存模型到磁盘

        参数:
            pair: 股票代码
            model: 模型对象
            timestamp: 时间戳
        """
        filename = self._generate_model_filename(pair, timestamp)
        model_path = self.full_path / filename
        model_path.mkdir(parents=True, exist_ok=True)

        # 使用 joblib 保存模型
        model_file = model_path / "model.pkl"
        joblib.dump(model, model_file)

        # 缓存到内存
        self.model_dictionary[filename] = model

        # 更新元数据
        self.pair_dict[pair] = {
            "model_filename": filename,
            "trained_timestamp": timestamp,
            "data_path": str(model_path),
        }
        save_json(self.pair_dict, self.pair_dictionary_path)

        logger.info(f"模型已保存: {filename} ({pair})")

    def load_model(self, pair: str) -> Any:
        """
        加载模型（优先从内存缓存）

        参数:
            pair: 股票代码

        返回:
            模型对象
        """
        if pair not in self.pair_dict:
            raise ValueError(f"未找到 {pair} 的模型")

        filename = self.pair_dict[pair]["model_filename"]

        # 检查内存缓存
        if filename in self.model_dictionary:
            return self.model_dictionary[filename]

        # 从磁盘加载
        model_path = self.full_path / filename / "model.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")

        model = joblib.load(model_path)
        self.model_dictionary[filename] = model
        logger.info(f"模型已加载: {filename} ({pair})")

        return model

    def append_predictions(self, pair: str, predictions: pl.DataFrame) -> None:
        """
        追加预测结果到历史

        参数:
            pair: 股票代码
            predictions: 预测结果DataFrame
        """
        if pair in self.historic_predictions:
            self.historic_predictions[pair] = pl.concat(
                [self.historic_predictions[pair], predictions]
            )
        else:
            self.historic_predictions[pair] = predictions

        # 持久化到磁盘
        self._save_predictions_to_disk()

    def _save_predictions_to_disk(self) -> None:
        """将所有预测历史保存到磁盘"""
        if not self.historic_predictions:
            return

        all_preds = pl.concat(list(self.historic_predictions.values()))
        save_parquet(all_preds, self.historic_predictions_path)

    def get_historic_predictions(
        self,
        pair: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Optional[pl.DataFrame]:
        """
        获取历史预测

        参数:
            pair: 股票代码
            start: 开始时间（可选）
            end: 结束时间（可选）

        返回:
            预测历史DataFrame
        """
        if pair not in self.historic_predictions:
            return None

        df = self.historic_predictions[pair]

        if start:
            df = df.filter(pl.col("datetime") >= start)
        if end:
            df = df.filter(pl.col("datetime") <= end)

        return df.sort("datetime")

    def should_retrain(self, pair: str, max_age_days: int = 30) -> bool:
        """
        检查是否需要重新训练

        参数:
            pair: 股票代码
            max_age_days: 模型最大年龄（天）

        返回:
            True 如果需要重新训练
        """
        if pair not in self.pair_dict:
            return True

        last_trained = self.pair_dict[pair].get("trained_timestamp", 0)
        age_days = (get_timestamp() - last_trained) / 86400

        return age_days > max_age_days
