"""
XGBoost 极值选股器

使用 QuickAdapterV5Dataset 和 XGBoostExtremaModel 进行股票极值预测选股
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from dataclasses import dataclass
import polars as pl
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from vnpy.trader.constant import Interval
from vnpy.alpha.lab_v2 import AlphaLabV2Engine as AlphaLabV2
from vnpy.alpha import Segment
from vnpy.alpha.dataset.datasets.quick_adapter_v5 import QuickAdapterV5Dataset
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel
from vnpy.alpha.model.models.grouped_multi_model import GroupedMultiModel
from vnpy.trader.database import DB_TZ
from vnpy.alpha.logger import logger


# 获取脚本所在目录的绝对路径
SCRIPT_DIR = Path(__file__).parent.resolve()
LAB_PATH = SCRIPT_DIR / "lab"


@dataclass
class SelectorConfig:
    """选股器配置"""
    # 数据参数
    top_n: int = 300                    # 选股数量（沪深300最多300只）
    train_period_days: int = 100        # 训练期天数（从 start 往前推）
    extended_days: int = 100            # 额外缓冲天数
    interval: Interval = Interval.DAILY # K线周期

    # DI（Dissimilarity Index）参数
    di_threshold: float = 5.0           # DI阈值，0表示禁用（避免内存溢出）

    # XGBoost参数
    learning_rate: float = 0.05
    max_depth: int = 6
    n_estimators: int = 100
    early_stopping_rounds: int = 50

    # 信号过滤参数
    min_volume_percentile: float = 0.2    # 最小成交量百分位（剔除低流动性股票）

    # 批次处理参数
    data_batch_size: int = 50             # 数据加载批次大小


# 默认配置
DEFAULT_CONFIG = SelectorConfig()

class XGBoostExtremaSelector:
    """XGBoost 极值选股器"""

    def __init__(
        self,
        lab: AlphaLabV2,
        name: str,
        start: str,
        end: str,
        config: SelectorConfig = None,
    ):
        """
        初始化选股器

        Args:
            lab: AlphaLab 实例（已包含指数代码配置）
            name: 任务名称
            start: 开始日期
            end: 结束日期
            config: 选股器配置（使用默认配置如果为 None）
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

        self.dataset: Optional[QuickAdapterV5Dataset] = None
        self.multi_model: Optional[GroupedMultiModel] = None
        self.result_df: Optional[pl.DataFrame] = None
        self.signal_df: Optional[pl.DataFrame] = None

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

        # 加载成分股代码（从索引层）
        # 使用实例默认的 index_code，也可指定其他指数
        logger.info(f"Lab root路径: {self.lab.root}")
        logger.info(f"IndexManager索引路径: {self.lab.index_manager.index_path}")
        logger.info(f"IndexManager index_code: {self.lab.index_code}")

        # 检查索引目录是否存在
        index_dir = self.lab.index_manager.index_path / self.lab.index_code
        logger.info(f"指数目录: {index_dir}")
        logger.info(f"指数目录是否存在: {index_dir.exists()}")
        if index_dir.exists():
            files = list(index_dir.iterdir())
            logger.info(f"指数目录内容: {[f.name for f in files]}")

        component_symbols = self.lab.get_component_symbols(
            start=self.start,
            end=self.end
        )
        logger.info(f"指数代码：{self.lab.index_code}")
        logger.info(f"日期范围：{self.start} ~ {self.end}")
        logger.info(f"成分股数量：{len(component_symbols)}")

        if not component_symbols:
            logger.error(f"错误：未找到指数 {self.lab.index_code} 的成分股数据")
            logger.error(f"请确保已运行 download_data.py 下载数据")
            logger.error(f"数据目录：{LAB_PATH}")
            raise ValueError(f"未找到指数 {self.lab.index_code} 的成分股数据")

        # 只取前 top_n 只股票
        top_symbols = component_symbols[:self.top_n]
        logger.info(f"选股范围：前{len(top_symbols)}只成分股")

        # 计算需要的数据范围
        # 从 start 往前推：train_period_days + extended_days
        start_dt = datetime.strptime(self.start, "%Y-%m-%d")
        end_dt = datetime.strptime(self.end, "%Y-%m-%d")

        # 训练期 + 缓冲期从 start 往前推
        train_buffer_days = self.train_period_days + self.extended_days
        data_start_dt = start_dt - timedelta(days=train_buffer_days)
        data_start_str = data_start_dt.strftime("%Y-%m-%d")

        # 总数据范围 = 训练期 + 缓冲期 + 测试期
        total_days = (end_dt - data_start_dt).days

        logger.info(f"数据范围：{data_start_str} ~ {self.end} (共{total_days}天)")
        logger.info(f"  - 测试期：{(end_dt - start_dt).days}天 ({self.start} ~ {self.end})")
        logger.info(f"  - 训练期 + 验证期：{self.train_period_days}天 (从{self.start}往前推)")
        logger.info(f"  - 缓冲期：{self.extended_days}天")

        # 加载成分股数据（从计算的开始时间到 end）
        # 使用分批加载避免内存溢出
        logger.info(f"开始分批加载数据（批次大小: {self.config.data_batch_size}）...")
        df = self.load_data_batch(top_symbols, data_start_str, self.end)

        # 检查数据是否足够，不足时尝试下载
        if df is None:
            df = pl.DataFrame()
        df = self._ensure_sufficient_data(df, top_symbols, data_start_str, total_days)

        logger.info(f"数据形状：{df.shape}")

        return df

    def _ensure_sufficient_data(
        self,
        df: pl.DataFrame,
        symbols: list[str],
        required_start: str,
        needed_days: int
    ) -> pl.DataFrame:
        """
        检查数据是否足够，不足时自动下载补充

        Parameters
        ----------
        df : pl.DataFrame
            已加载的数据
        symbols : list[str]
            股票代码列表
        required_start : str
            需要的开始日期
        needed_days : int
            需要的总天数
        """
        if len(df) == 0:
            min_date = None
            max_date = None
            actual_days = 0
        else:
            min_date = df["datetime"].min()
            max_date = df["datetime"].max()
            actual_days = (max_date - min_date).days

        logger.info(f"实际数据范围：{min_date} ~ {max_date} (共{actual_days}天)")
        logger.info(f"需要数据范围：{required_start} ~ {self.end} (共{needed_days}天)")

        # 检查数据是否满足要求
        required_start_dt = datetime.strptime(required_start, "%Y-%m-%d")

        # 允许 5 天的偏差（周末和节假日）
        tolerance_days = 5
        data_sufficient = (
            len(df) > 0
            and min_date <= required_start_dt + timedelta(days=tolerance_days)
            and actual_days >= needed_days - tolerance_days
        )

        if data_sufficient:
            logger.info(f"[OK] 数据充足（偏差在容忍范围内）")
            return df

        # 数据不足，尝试下载
        missing_days = needed_days - actual_days
        logger.info(f"\n数据不足：当前{actual_days}天，需要{needed_days}天 (缺{missing_days}天)")
        logger.info("正在下载缺失数据...")

        try:
            # 使用迅投研下载数据
            from tqdm import tqdm
            from vnpy.trader.constant import Exchange
            from vnpy.trader.object import HistoryRequest
            from vnpy.trader.datafeed import get_datafeed

            # 初始化数据服务
            datafeed = get_datafeed()

            # 准备下载列表（包括指数本身）
            # 从 IndexManager 获取指数的 xt_code
            index_info = self.lab.index_manager.get_index_info(self.lab.index_code)
            index_xt_code = index_info.get("xt_code") if index_info else None
            if index_xt_code:
                # 转换迅投代码格式 000300.SH -> 000300.SSE
                index_vt_symbol = index_xt_code.replace(".SH", ".SSE").replace(".SZ", ".SZSE")
                task_symbols = list(set(symbols + [index_vt_symbol]))
            else:
                task_symbols = symbols

            # 轮询下载
            start_dt = datetime.strptime(required_start, "%Y-%m-%d")
            end_dt = datetime.strptime(self.end, "%Y-%m-%d")
            start_dt = start_dt.replace(tzinfo=DB_TZ)
            end_dt = end_dt.replace(tzinfo=DB_TZ)

            for vt_symbol in tqdm(task_symbols, desc="下载数据"):
                try:
                    symbol, exchange_str = vt_symbol.split(".")
                    req = HistoryRequest(
                        symbol=symbol,
                        exchange=Exchange(exchange_str),
                        start=start_dt,
                        end=end_dt,
                        interval=self.interval
                    )
                    bars = datafeed.query_bar_history(req)
                    if bars:
                        self.lab.save_bar_data(bars)
                    else:
                        logger.warning(f"警告：{vt_symbol} 下载失败")
                except Exception as e:
                    logger.error(f"下载 {vt_symbol} 失败：{e}")
                    continue

            logger.info("[OK] 下载完成，重新加载数据...")

            # 重新加载数据
            df = self.lab.load_bar_df(
                start=required_start,
                end=self.end,
                interval=self.interval,
                extended_days=0
            )

            # 再次检查
            if len(df) > 0:
                min_date = df["datetime"].min()
                max_date = df["datetime"].max()
                actual_days = (max_date - min_date).days
                logger.info(f"[OK] 数据已更新：{actual_days}天")
            else:
                logger.warning("警告：重新加载后数据仍为空")

        except ImportError as e:
            logger.warning(f"缺少依赖：{e}")
            logger.info("请安装：pip install tqdm xtquant")
        except Exception as e:
            logger.warning(f"下载失败：{e}")
            logger.info("请手动运行 download_data_xt.ipynb 下载数据")

        return df

    def create_dataset(self, df: pl.DataFrame) -> QuickAdapterV5Dataset:
        """创建数据集"""
        logger.info("\n" + "=" * 60)
        logger.info("2. 创建数据集")
        logger.info("=" * 60)

        # 计算数据的实际日期范围
        min_date = df["datetime"].min()
        max_date = df["datetime"].max()
        actual_days = (max_date - min_date).days

        logger.info(f"数据日期范围：{min_date} ~ {max_date} (共{actual_days}天)")
        logger.info(f"需要训练期天数：{self.train_period_days}天")

        # 按 train_period_days 划分训练/验证周期
        # 训练期 + 验证期：end 往前推 train_period_days 天
        # 训练期：80%
        # 验证期：20%
        # 测试期：用户传入的 start 到 end
        end_dt = datetime.strptime(self.end, "%Y-%m-%d")
        start_dt = datetime.strptime(self.start, "%Y-%m-%d")

        # 训练期 + 验证期从 start 往前推
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
            label_period_candles=10,
            include_shifted_candles=[1, 2, 3],
        )

        # 加载指数成分过滤器（使用训练期开始时间，以覆盖完整数据范围）
        # AlphaLabV2: load_component_filters index_code 可选，默认使用实例的 index_code
        filters = self.lab.get_component_filters(
            start=train_start_str,
            end=self.end
        )

        # 准备特征和标签数据
        dataset.prepare_data(filters, max_workers=3)
        logger.info(f"特征数量：{len(dataset.feature_results)}")

        # 数据预处理
        dataset.process_data()

        logger.info(f"处理后特征数量：{len([c for c in dataset.learn_df.columns if c.startswith('%-')])}")

        self.dataset = dataset
        return dataset

    def train_model(self) -> GroupedMultiModel:
        """训练多模型（每只股票一个模型）"""
        logger.info("\n" + "=" * 60)
        logger.info("3. 训练模型")
        logger.info("=" * 60)

        multi_model = GroupedMultiModel(
            model_factory=lambda: XGBoostExtremaModel(
                learning_rate=self.config.learning_rate,
                max_depth=self.config.max_depth,
                n_estimators=self.config.n_estimators,
                early_stopping_rounds=self.config.early_stopping_rounds,
                num_candles=200,
                label_period_candles=10,
                scale_label=False,  # 对标签进行缩放（像 freqtrade 一样）
            ),
            group_by="vt_symbol",
            min_samples_per_group=100,
        )

        logger.info("开始训练多模型...")
        multi_model.fit(self.dataset)

        # 查看模型信息
        info = multi_model.detail()
        logger.info(f"\n多模型信息:")
        logger.info(f"  类型：{info['type']}")
        logger.info(f"  分组字段：{info['group_by']}")
        logger.info(f"  训练模型数：{info['num_groups']}")
        logger.info(f"  是否有全局模型：{info['has_global_model']}")
        logger.info(f"  前 10 个分组：{info['groups'][:10]}")

        self.multi_model = multi_model
        return multi_model

    def generate_signals(self) -> pl.DataFrame:
        """生成交易信号"""
        logger.info("\n" + "=" * 60)
        logger.info("4. 生成信号")
        logger.info("=" * 60)

        # 运行预测
        self.multi_model.predict(self.dataset, Segment.TEST)

        # 获取结果 DataFrame
        result_df = self.multi_model.get_results_df()

        self.result_df = result_df
        logger.info(f"结果形状：{result_df.shape}")
        logger.info(f"结果列：{result_df.columns}")

   
        # 检查 result_df 中的预测值范围
        if "&s-extrema" in result_df.columns:
            logger.info(f"预测值范围：[{result_df['&s-extrema'].min():.6f}, {result_df['&s-extrema'].max():.6f}]")

        # 仅使用阈值筛选信号
        logger.info("使用阈值筛选信号")
        maxima_signals = result_df.filter(
            pl.col("&s-extrema") > pl.col("&s-maxima_sort_threshold")
        ).select(["datetime", "vt_symbol", "&s-extrema","DI_values","DI_cutoff","&s-minima_sort_threshold","&s-maxima_sort_threshold"])
        minima_signals = result_df.filter(
            pl.col("&s-extrema") < pl.col("&s-minima_sort_threshold")
        ).select(["datetime", "vt_symbol", "&s-extrema","DI_values","DI_cutoff","&s-minima_sort_threshold","&s-maxima_sort_threshold"])

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

        # 保存模型
        self.lab.save_model(f"{self.name}_multi", self.multi_model)
        logger.info(f"模型已保存：{self.name}_multi")

        # 添加元数据到信号 DataFrame
        signal_with_meta = self.signal_df.with_columns([
            pl.lit(self.name).alias("model_name"),
            pl.lit(self.start).alias("start_date"),
            pl.lit(self.end).alias("end_date"),
            pl.lit(self.lab.index_code).alias("index_code"),
            pl.lit(self.config.di_threshold).alias("di_threshold"),
            pl.lit(len(self.multi_model.models_) if self.multi_model else 0).alias("num_models"),
        ])

        # 保存信号
        self.lab.save_signal(self.name, signal_with_meta)
        logger.info(f"信号已保存：{self.name}")
        logger.info(f"  - 模型名称: {self.name}")
        logger.info(f"  - 日期范围: {self.start} ~ {self.end}")
        logger.info(f"  - 指数代码: {self.lab.index_code}")
        logger.info(f"  - DI阈值: {self.config.di_threshold}")
        logger.info(f"  - 训练模型数: {len(self.multi_model.models_) if self.multi_model else 0}")

    def run(self) -> pl.DataFrame:
        """运行完整选股流程"""
        logger.info("\n" + "#" * 60)
        logger.info(f"# XGBoost 极值选股器 - {self.name}")
        logger.info("#" * 60)

        # 1. 加载数据
        df = self.load_data()

        # 2. 创建数据集
        self.create_dataset(df)

        # 3. 训练模型
        self.train_model()

        # 4. 生成信号
        self.generate_signals()

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
    # 创建事件引擎和主引擎（AlphaLabV2需要）
    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine

    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    # 创建数据中心 - AlphaLabV2（分层架构）
    # 参数：lab路径、项目名称、数据源、指数代码
    lab = AlphaLabV2(
        main_engine=main_engine,
        event_engine=event_engine,
        root_path=str(LAB_PATH),
        project_name="xgb_extrema",
        data_source="xt",
        index_code="csi300"  # 使用沪深300指数成分股
    )

    # 任务名称
    name = "300_xgb_extrema"

    # 测试期（需要预测的日期范围）
    start = "2026-04-14"
    end = "2026-04-15"

    # ========================================
    # 选股器参数配置（使用 SelectorConfig）
    # ========================================
    config = SelectorConfig(
        top_n=100,              # 选股数量（沪深300最多300只）
        train_period_days=300,  # 训练期天数（从 start 往前推）
        extended_days=100,      # 额外缓冲天数
        di_threshold=0,         # DI阈值（0表示禁用，避免内存溢出）
        learning_rate=0.05,     # XGBoost学习率
        max_depth=6,            # XGBoost树深度
        n_estimators=100,       # XGBoost树数量
        early_stopping_rounds=50,  # 早停轮数
        min_volume_percentile=0.2, # 成交量过滤阈值（剔除最低的20%）
        data_batch_size=50,     # 数据加载批次大小
    )

    selector = XGBoostExtremaSelector(
        lab=lab,
        name=name,
        start=start,
        end=end,
        config=config,          # 传入配置对象
    )

    # 运行选股
    signal_df = selector.run()

    # 显示结果
    logger.info("\n最终信号预览:")
    logger.info(signal_df.head(10))


if __name__ == "__main__":
    main()
