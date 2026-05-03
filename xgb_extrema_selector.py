"""
XGBoost 极值选股器 (StockAI 版本)

使用 QuickAdapterV5Dataset 进行特征工程，使用 StockAI 架构进行训练和预测
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import polars as pl
import numpy as np

from vnpy.trader.constant import Interval
from vnpy.alpha.lab_v2 import AlphaLabV2Engine as AlphaLabV2
from vnpy.alpha.dataset.datasets.quick_adapter_v5 import QuickAdapterV5Dataset
from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel
from vnpy.stockai.data_drawer import StockaiDataDrawer
from vnpy.alpha.logger import logger


# 获取脚本所在目录的绝对路径
SCRIPT_DIR = Path(__file__).parent.resolve()
LAB_PATH = SCRIPT_DIR / "lab"


@dataclass
class SelectorConfig:
    """选股器配置"""
    # 数据参数
    top_n: int = 300                    # 选股数量（沪深300最多300只）
    train_period_days: int = 300        # 训练期天数（从 start 往前推）
    extended_days: int = 100            # 额外缓冲天数
    interval: Interval = Interval.DAILY # K线周期

    # DI（Dissimilarity Index）参数
    di_threshold: float = 0.0           # DI阈值，0表示禁用（避免内存溢出）

    # XGBoost参数
    learning_rate: float = 0.05
    max_depth: int = 6
    n_estimators: int = 100
    early_stopping_rounds: int = 50

    # 信号过滤参数
    min_volume_percentile: float = 0.2    # 最小成交量百分位（剔除低流动性股票）

    # 批次处理参数
    data_batch_size: int = 50             # 数据加载批次大小

    # StockAI 参数
    num_candles: int = 200                # 用于阈值计算的K线数量
    label_period_candles: int = 10        # 标签周期
    test_size: float = 0.2                # 测试集比例
    shuffle: bool = False                 # 是否打乱数据


# 默认配置
DEFAULT_CONFIG = SelectorConfig()


class XGBoostExtremaSelector:
    """XGBoost 极值选股器 (StockAI 版本)"""

    def __init__(
        self,
        lab: AlphaLabV2,
        name: str,
        start: str,
        end: str,
        config: SelectorConfig = None,
        stockai_path: Optional[Path] = None,
    ):
        """
        初始化选股器

        Args:
            lab: AlphaLab 实例（已包含指数代码配置）
            name: 任务名称
            start: 开始日期
            end: 结束日期
            config: 选股器配置（使用默认配置如果为 None）
            stockai_path: StockAI 数据存储路径
        """
        self.lab = lab
        self.name = name
        self.start = start
        self.end = end

        # 使用配置或默认配置
        self.config = config if config else SelectorConfig()

        # 从配置展开常用参数
        self.interval = self.config.interval
        self.extended_days = self.config.extended_days
        self.top_n = self.config.top_n
        self.train_period_days = self.config.train_period_days

        # 数据集和结果
        self.dataset: Optional[QuickAdapterV5Dataset] = None
        self.result_df: Optional[pl.DataFrame] = None
        self.signal_df: Optional[pl.DataFrame] = None

        # 成分股列表
        self.component_symbols: list[str] = []

        # StockAI 配置
        self.stockai_path = stockai_path or (LAB_PATH / "stockai_data" / name)
        self.stockai_config = self._build_stockai_config()

        # 模型字典 {pair: XGBoostExtremaModel}
        self.models: dict[str, XGBoostExtremaModel] = {}

    def _build_stockai_config(self) -> dict:
        """构建 StockAI 配置"""
        return {
            "path": str(self.stockai_path),
            "interval": self.interval.value if hasattr(self.interval, 'value') else str(self.interval),
            "feature_parameters": {
                "num_candles": self.config.num_candles,
                "label_period_candles": self.config.label_period_candles,
            },
            "model_training_parameters": {
                "learning_rate": self.config.learning_rate,
                "max_depth": self.config.max_depth,
                "n_estimators": self.config.n_estimators,
                "early_stopping_rounds": self.config.early_stopping_rounds,
            },
            "data_split_parameters": {
                "test_size": self.config.test_size,
                "shuffle": self.config.shuffle,
            },
            "train_period_days": self.train_period_days,
        }

    def load_data_batch(self, symbols: list[str], data_start: str, data_end: str) -> Optional[pl.DataFrame]:
        """分批加载数据，避免内存溢出"""
        batch_size = self.config.data_batch_size
        all_dfs = []

        for i in range(0, len(symbols), batch_size):
            batch = symbols[i:i + batch_size]
            logger.info(f"  加载批次 {i//batch_size + 1}/{(len(symbols) + batch_size - 1)//batch_size} ({len(batch)} 只股票)")

            df_batch = self.lab.load_bars_df(
                batch,
                self.interval,
                data_start,
                data_end,
                extended_days=0
            )
            if df_batch is not None and len(df_batch) > 0:
                all_dfs.append(df_batch)

        if not all_dfs:
            return None

        return pl.concat(all_dfs)

    def load_data(self) -> pl.DataFrame:
        """加载指数成分股数据"""
        logger.info("=" * 60)
        logger.info("1. 加载数据")
        logger.info("=" * 60)

        # 加载成分股代码
        logger.info(f"Lab root路径: {self.lab.root}")
        logger.info(f"IndexManager索引路径: {self.lab.index_manager.index_path}")
        logger.info(f"IndexManager index_code: {self.lab.index_code}")

        # 检查索引目录
        index_dir = self.lab.index_manager.index_path / self.lab.index_code
        logger.info(f"指数目录: {index_dir}")
        if index_dir.exists():
            files = list(index_dir.iterdir())
            logger.info(f"指数目录内容: {[f.name for f in files]}")

        self.component_symbols = self.lab.get_component_symbols(
            start=self.start,
            end=self.end
        )
        logger.info(f"指数代码：{self.lab.index_code}")
        logger.info(f"日期范围：{self.start} ~ {self.end}")
        logger.info(f"成分股数量：{len(self.component_symbols)}")

        if not self.component_symbols:
            raise ValueError(f"未找到指数 {self.lab.index_code} 的成分股数据")

        # 只取前 top_n 只股票
        top_symbols = self.component_symbols[:self.top_n]
        logger.info(f"选股范围：前{len(top_symbols)}只成分股")

        # 计算数据范围
        start_dt = datetime.strptime(self.start, "%Y-%m-%d")
        train_buffer_days = self.train_period_days + self.extended_days
        data_start_dt = start_dt - timedelta(days=train_buffer_days)
        data_start_str = data_start_dt.strftime("%Y-%m-%d")

        logger.info(f"数据范围：{data_start_str} ~ {self.end}")
        logger.info(f"  - 测试期：{self.start} ~ {self.end}")
        logger.info(f"  - 训练期：从{self.start}往前推{self.train_period_days}天")
        logger.info(f"  - 缓冲期：{self.extended_days}天")

        # 分批加载数据
        logger.info(f"开始分批加载数据（批次大小: {self.config.data_batch_size}）...")
        df = self.load_data_batch(top_symbols, data_start_str, self.end)

        if df is None:
            df = pl.DataFrame()

        logger.info(f"数据形状：{df.shape}")
        return df

    def create_dataset(self, df: pl.DataFrame) -> QuickAdapterV5Dataset:
        """创建数据集（用于特征工程）"""
        logger.info("\n" + "=" * 60)
        logger.info("2. 创建数据集")
        logger.info("=" * 60)

        # 计算日期范围
        start_dt = datetime.strptime(self.start, "%Y-%m-%d")
        train_buffer_days = self.train_period_days + self.extended_days
        train_start_dt = start_dt - timedelta(days=train_buffer_days)
        train_start_str = train_start_dt.strftime("%Y-%m-%d")

        # 训练期占 80%，验证期占 20%
        train_end_offset = int(self.train_period_days * 0.8)
        train_end_dt = start_dt - timedelta(days=self.train_period_days - train_end_offset)
        train_end_str = train_end_dt.strftime("%Y-%m-%d")

        # 验证期结束于测试期开始前
        valid_end_dt = start_dt - timedelta(days=1)
        valid_end_str = valid_end_dt.strftime("%Y-%m-%d")

        train_period = (train_start_str, train_end_str)
        valid_period = (train_end_str, valid_end_str)
        test_period = (self.start, self.end)

        logger.info(f"训练期：{train_period}")
        logger.info(f"验证期：{valid_period}")
        logger.info(f"测试期：{test_period}")

        dataset = QuickAdapterV5Dataset(
            df,
            train_period=train_period,
            valid_period=valid_period,
            test_period=test_period,
            periods=[10, 20, 30, 40],
            label_period_candles=self.config.label_period_candles,
            include_shifted_candles=[1, 2, 3],
        )

        # 加载指数成分过滤器
        filters = self.lab.get_component_filters(
            start=train_start_str,
            end=self.end
        )

        # 准备特征和标签数据
        dataset.prepare_data(filters, max_workers=3)
        logger.info(f"特征数量：{len(dataset.feature_results)}")

        # 数据预处理
        dataset.process_data()

        feature_cols = [c for c in dataset.learn_df.columns if c.startswith('%-')]
        logger.info(f"处理后特征数量：{len(feature_cols)}")

        self.dataset = dataset
        return dataset

    def train_models(self) -> dict[str, XGBoostExtremaModel]:
        """训练模型（每只股票一个模型）"""
        logger.info("\n" + "=" * 60)
        logger.info("3. 训练模型 (StockAI)")
        logger.info("=" * 60)

        models = {}
        learn_df = self.dataset.learn_df

        # 按股票分组训练
        unique_symbols = learn_df["vt_symbol"].unique().to_list()
        total = len(unique_symbols)

        logger.info(f"需要训练 {total} 个模型")

        for i, symbol in enumerate(unique_symbols, 1):
            logger.info(f"\n[{i}/{total}] 训练模型: {symbol}")

            # 创建模型实例
            model = XGBoostExtremaModel(self.stockai_config, self.lab)

            try:
                # 使用 StockAI 的高层训练接口
                model.start_training(
                    pair=symbol,
                    start=self.start,
                    end=self.end,
                )
                models[symbol] = model
                logger.info(f"  [OK] 训练完成: {symbol}")
            except Exception as e:
                logger.error(f"  [FAIL] 训练失败: {symbol} - {e}")
                continue

        self.models = models

        # 显示统计信息
        trained_count = len(models)
        logger.info(f"\n训练完成: {trained_count}/{total} 个模型")

        return models

    def generate_signals(self) -> pl.DataFrame:
        """生成交易信号"""
        logger.info("\n" + "=" * 60)
        logger.info("4. 生成信号 (StockAI)")
        logger.info("=" * 60)

        all_predictions = []

        # 按股票预测
        for symbol, model in self.models.items():
            logger.info(f"预测: {symbol}")

            try:
                # 使用 StockAI 的高层预测接口
                predictions = model.start_prediction(
                    pair=symbol,
                    start=self.start,
                    end=self.end,
                )

                # 添加股票代码列
                predictions = predictions.with_columns([
                    pl.col("pair").alias("vt_symbol"),
                ])

                all_predictions.append(predictions)

            except Exception as e:
                logger.error(f"预测失败: {symbol} - {e}")
                continue

        if not all_predictions:
            logger.warning("没有预测结果")
            return pl.DataFrame()

        # 合并所有预测
        result_df = pl.concat(all_predictions).sort(["datetime", "vt_symbol"])
        self.result_df = result_df

        logger.info(f"结果形状：{result_df.shape}")

        # 生成信号（基于阈值）
        maxima_signals = result_df.filter(
            pl.col("prediction") > pl.col("maxima_threshold")
        ).select(["datetime", "vt_symbol", "prediction"])

        minima_signals = result_df.filter(
            pl.col("prediction") < pl.col("minima_threshold")
        ).select(["datetime", "vt_symbol", "prediction"])

        # 添加信号列
        maxima_signals = maxima_signals.with_columns(pl.lit(-1).alias("signal"))
        minima_signals = minima_signals.with_columns(pl.lit(1).alias("signal"))

        logger.info(f"Maxima 信号数量：{len(maxima_signals)}")
        logger.info(f"Minima 信号数量：{len(minima_signals)}")

        # 合并信号
        signal_df = pl.concat([maxima_signals, minima_signals]).sort(
            ["datetime", "vt_symbol"]
        )

        logger.info(f"\n总信号数量：{len(signal_df)}")
        logger.info(f"买入信号 (1): {len(signal_df.filter(pl.col('signal') == 1))}")
        logger.info(f"卖出信号 (-1): {len(signal_df.filter(pl.col('signal') == -1))}")

        self.signal_df = signal_df
        return signal_df

    def save_results(self):
        """保存结果"""
        logger.info("\n" + "=" * 60)
        logger.info("5. 保存结果")
        logger.info("=" * 60)

        # StockAI 模型已通过 DataDrawer 自动保存
        logger.info(f"模型已保存到: {self.stockai_path}")

        # 获取 DataDrawer 保存的元数据
        if self.models:
            first_model = list(self.models.values())[0]
            drawer = first_model.dd
            logger.info(f"已训练模型数: {len(drawer.pair_dict)}")

        # 添加元数据到信号 DataFrame
        if self.signal_df is not None and len(self.signal_df) > 0:
            signal_with_meta = self.signal_df.with_columns([
                pl.lit(self.name).alias("model_name"),
                pl.lit(self.start).alias("start_date"),
                pl.lit(self.end).alias("end_date"),
                pl.lit(self.lab.index_code).alias("index_code"),
                pl.lit(self.config.di_threshold).alias("di_threshold"),
                pl.lit(len(self.models)).alias("num_models"),
            ])

            # 保存信号
            self.lab.save_signal(self.name, signal_with_meta)
            logger.info(f"信号已保存：{self.name}")
            logger.info(f"  - 模型名称: {self.name}")
            logger.info(f"  - 日期范围: {self.start} ~ {self.end}")
            logger.info(f"  - 指数代码: {self.lab.index_code}")
            logger.info(f"  - DI阈值: {self.config.di_threshold}")
            logger.info(f"  - 训练模型数: {len(self.models)}")

    def run(self) -> pl.DataFrame:
        """运行完整选股流程"""
        logger.info("\n" + "#" * 60)
        logger.info(f"# XGBoost 极值选股器 (StockAI) - {self.name}")
        logger.info("#" * 60)

        # 1. 加载数据
        df = self.load_data()

        # 2. 创建数据集（特征工程）
        self.create_dataset(df)

        # 3. 训练模型
        self.train_models()

        # 4. 生成信号
        signal_df = self.generate_signals()
        if signal_df is None:
            logger.warning("信号生成返回 None，创建空 DataFrame")
            signal_df = pl.DataFrame()
        self.signal_df = signal_df

        # 5. 保存结果
        self.save_results()

        logger.info("\n" + "=" * 60)
        logger.info("选股完成!")
        logger.info("=" * 60)

        return self.signal_df


def main():
    """主函数"""
    # ========================================
    # 数据服务配置（迅投研）
    # ========================================
    from vnpy.trader.setting import SETTINGS

    # 数据库配置
    SETTINGS["database.name"] = "postgresql"
    SETTINGS["database.host"] = "localhost"
    SETTINGS["database.port"] = "5432"
    SETTINGS["database.database"] = "vnpy"
    SETTINGS["database.user"] = "vnpy"
    SETTINGS["database.password"] = "vnpy"

    # 数据服务配置
    SETTINGS["datafeed.name"] = "xt"
    SETTINGS["datafeed.username"] = "client"
    SETTINGS["datafeed.password"] = ""

    # ========================================
    # 任务参数配置
    # ========================================
    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    # 创建数据中心
    lab = AlphaLabV2(
        main_engine=main_engine,
        event_engine=event_engine,
        root_path=str(LAB_PATH),
        project_name="xgb_extrema",
        data_source="xt",
        index_code="csi300"
    )

    # 任务名称
    name = "300_xgb_extrema_stockai"

    # 测试期
    start = "2026-04-14"
    end = "2026-04-15"

    # ========================================
    # 选股器参数配置
    # ========================================
    config = SelectorConfig(
        top_n=100,
        train_period_days=300,
        extended_days=100,
        di_threshold=0,
        learning_rate=0.05,
        max_depth=6,
        n_estimators=100,
        early_stopping_rounds=50,
        min_volume_percentile=0.2,
        data_batch_size=50,
        num_candles=200,
        label_period_candles=10,
        test_size=0.2,
        shuffle=False,
    )

    selector = XGBoostExtremaSelector(
        lab=lab,
        name=name,
        start=start,
        end=end,
        config=config,
        stockai_path=LAB_PATH / "stockai_data" / name,
    )

    # 运行选股
    signal_df = selector.run()

    # 显示结果
    if signal_df is not None and len(signal_df) > 0:
        logger.info("\n最终信号预览:")
        logger.info(signal_df.head(10))
    else:
        logger.warning("\n没有生成信号")


if __name__ == "__main__":
    main()
