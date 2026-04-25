"""
XGBoost 极值选股器

使用 QuickAdapterV5Dataset 和 XGBoostExtremaModel 进行股票极值预测选股
"""
import warnings
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

import polars as pl
import numpy as np
from datetime import datetime, timedelta
from typing import Optional
from pathlib import Path

from vnpy.trader.constant import Interval
from vnpy.alpha.lab_v2 import AlphaLabV2
from vnpy.alpha import Segment
from vnpy.alpha.dataset.datasets.quick_adapter_v5 import QuickAdapterV5Dataset
from vnpy.alpha.model.models.xgb_extrema_model import XGBoostExtremaModel
from vnpy.alpha.model.models.grouped_multi_model import GroupedMultiModel
from vnpy.trader.database import DB_TZ
from vnpy.alpha.logger import logger

# 获取脚本所在目录的绝对路径
SCRIPT_DIR = Path(__file__).parent.resolve()
LAB_PATH = SCRIPT_DIR / "lab"

# 成分股数量配置
CSI300_TOP_N = 300  # 沪深300成分股数量

class XGBoostExtremaSelector:
    """XGBoost 极值选股器"""

    def __init__(
        self,
        lab: AlphaLabV2,
        name: str,
        index_symbol: str,
        start: str,
        end: str,
        interval: Interval = Interval.DAILY,
        extended_days: int = 100,
        top_n: int = 100,
        train_period_days: int = 100,
    ):
        """
        初始化选股器

        Args:
            lab: AlphaLab 实例
            name: 任务名称
            index_symbol: 指数代码（如"000300.SSE"）
            start: 开始日期
            end: 结束日期
            interval: K 线周期
            extended_days: 扩展天数
            top_n: 选股数量
            train_period_days: 训练期天数（从 end 往前推，训练期 = end - train_period_days 到 end 的 70% 位置）
        """
        self.lab = lab
        self.name = name
        self.index_symbol = index_symbol
        self.start = start
        self.end = end
        self.interval = interval
        self.extended_days = extended_days
        self.top_n = top_n
        self.train_period_days = train_period_days

        self.dataset: Optional[QuickAdapterV5Dataset] = None
        self.multi_model: Optional[GroupedMultiModel] = None
        self.result_df: Optional[pl.DataFrame] = None
        self.signal_df: Optional[pl.DataFrame] = None

    def load_data(self) -> pl.DataFrame:
        """加载指数成分股数据"""
        logger.info("=" * 60)
        logger.info("1. 加载数据")
        logger.info("=" * 60)

        # 加载成分股代码（从索引层）
        component_symbols = self.lab.load_component_symbols(
            self.start, self.end
        )
        logger.info(f"成分股数量：{len(component_symbols)}")

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
        # AlphaLabV2: load_bar_df 不需要 symbols 参数，自动从 index_code 获取
        df = self.lab.load_bar_df(
            start=data_start_str,
            end=self.end,
            interval=self.interval,
            extended_days=0
        )

        # 检查数据是否足够，不足时尝试下载
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

            # 准备下载列表
            task_symbols = list(set(symbols + [self.index_symbol]))

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
        # AlphaLabV2: load_component_filters 不需要 index_symbol 参数
        filters = self.lab.load_component_filters(
            train_start_str, self.end
        )

        # 准备特征和标签数据
        dataset.prepare_data(filters, max_workers=3)
        logger.info(f"特征数量：{len(dataset.feature_results)}")

        # 使用 FreqAI 风格的特征处理管道
        from functools import partial
        from vnpy.alpha.dataset import FreqaiFeaturePipeline, process_freqai_feature_pipeline

        # 从 ft_params 读取 DI 阈值配置（与 freqtrade 兼容）
        ft_params = {
            "DI_threshold": 20,  # DI 阈值，用于异常检测
            "n_jobs": -1,         # 并行线程数
        }

        # 创建管道（VarianceThreshold + MinMaxScaler + DissimilarityIndex）
        feature_pipeline = FreqaiFeaturePipeline(
            threshold=0.0,
            feature_range=(-1, 1),
            di_threshold=ft_params.get("DI_threshold", 0),  # 设置 DI 阈值
            n_jobs=ft_params.get("n_jobs", -1),
        )

        # 从学习数据拟合
        feature_pipeline.fit(dataset.fetch_learn(Segment.TRAIN))

        # 添加处理器（特征缩放到 (-1, 1)）
        dataset.add_processor("infer", partial(process_freqai_feature_pipeline, pipeline=feature_pipeline))
        dataset.add_processor("learn", partial(process_freqai_feature_pipeline, pipeline=feature_pipeline))

        # 数据预处理（特征缩放 + DI 计算）
        dataset.process_data()

        logger.info(f"处理后特征数量：{len([c for c in dataset.learn_df.columns if c.startswith('%-')])}")

        # 保存 feature_pipeline 以便模型进行 inverse_transform
        self.feature_pipeline = feature_pipeline

        self.dataset = dataset
        return dataset

    def train_model(self) -> GroupedMultiModel:
        """训练多模型（每只股票一个模型）"""
        logger.info("\n" + "=" * 60)
        logger.info("3. 训练模型")
        logger.info("=" * 60)

        # 获取 feature_pipeline（如果已创建）
        feature_pipeline = getattr(self, 'feature_pipeline', None)
        logger.info(f"feature_pipeline 是否存在: {feature_pipeline is not None}")
        if feature_pipeline is not None:
            logger.info(f"feature_pipeline._data_min 是否存在: {hasattr(feature_pipeline, '_data_min')}")
            logger.info(f"feature_pipeline.feature_cols 数量: {len(feature_pipeline.feature_cols) if feature_pipeline.feature_cols else 0}")

        multi_model = GroupedMultiModel(
            model_factory=lambda: XGBoostExtremaModel(
                learning_rate=0.05,
                max_depth=6,
                n_estimators=100,
                early_stopping_rounds=50,
                num_candles=300,
                label_period_candles=50,
                feature_pipeline=feature_pipeline,  # 传递管道用于 inverse_transform
                scale_label=True,  # 对标签进行缩放（像 freqtrade 一样）
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

        # 检查是否有原始范围的特征
        raw_volume_cols = [col for col in result_df.columns if "volume" in col.lower()]
        logger.info(f"成交量相关列：{raw_volume_cols}")

        # 打印预测值范围
        if "&s-extrema" in result_df.columns:
            logger.info(f"预测值 &s-extrema 范围：[{result_df['&s-extrema'].min():.6f}, {result_df['&s-extrema'].max():.6f}]")

        # 检查是否有特征列（%-前缀）
        feature_cols = [col for col in result_df.columns if col.startswith("%-")]
        logger.info(f"特征列数量：{len(feature_cols)}")
        if feature_cols:
            logger.info(f"前5个特征列：{feature_cols[:5]}")

        # 从原始数据获取成交量（使用 raw_df）
        raw_df = self.dataset.fetch_raw(Segment.TEST)

        # 如果 result_df 中没有特征列，从 raw_df 获取
        feature_cols = [col for col in result_df.columns if col.startswith("%-")]
        if not feature_cols:
            logger.warning("警告：result_df 中没有特征列，从 raw_df 获取特征...")
            # 获取原始特征列（不包括 datetime, vt_symbol, close 等基础列）
            raw_feature_cols = [col for col in raw_df.columns if col.startswith("%-")]
            if raw_feature_cols:
                raw_features_df = raw_df.select(["datetime", "vt_symbol"] + raw_feature_cols)
                result_df = result_df.join(raw_features_df, on=["datetime", "vt_symbol"], how="left")
                logger.info(f"已添加 {len(raw_feature_cols)} 个原始特征到 result_df")

        # 获取成交量（使用 %-raw_volume 列）
        if "%-raw_volume" in raw_df.columns:
            volume_df = raw_df.select(["datetime", "vt_symbol", "%-raw_volume"])
        elif "volume" in raw_df.columns:
            volume_df = raw_df.select(["datetime", "vt_symbol", "volume"])
            volume_df = volume_df.rename({"volume": "%-raw_volume"})
        else:
            logger.warning("警告：未找到成交量列，使用空值")
            volume_df = raw_df.select(["datetime", "vt_symbol"])
            volume_df = volume_df.with_columns(pl.lit(0.0).alias("%-raw_volume"))

        # 打印成交量范围以检查是否正常
        logger.info(f"成交量范围：[{volume_df['%-raw_volume'].min():.2f}, {volume_df['%-raw_volume'].max():.2f}]")

        # 检查 result_df 中的预测值范围
        if "&s-extrema" in result_df.columns:
            logger.info(f"预测值范围：[{result_df['&s-extrema'].min():.6f}, {result_df['&s-extrema'].max():.6f}]")

        # 使用模型输出的阈值筛选信号（加入 DI 值过滤）
        # 筛选 maxima 信号 (预测值 > maxima 阈值 且 DI 值异常 → 卖出)
        maxima_signals = result_df.filter(
            (pl.col("&s-extrema") > pl.col("&s-maxima_sort_threshold")) 
        ).select(["datetime", "vt_symbol", "&s-extrema","DI_values","DI_cutoff"])
        maxima_signals = maxima_signals.with_columns(pl.lit(-1).alias("signal"))
        logger.info(f"Maxima 信号数量：{len(maxima_signals)}")

        # 筛选 minima 信号 (预测值 < minima 阈值 且 DI 值异常 → 买入)
        minima_signals = result_df.filter(
            (pl.col("&s-extrema") < pl.col("&s-minima_sort_threshold")) 
        ).select(["datetime", "vt_symbol", "&s-extrema","DI_values","DI_cutoff"])
        minima_signals = minima_signals.with_columns(pl.lit(1).alias("signal"))
        logger.info(f"Minima 信号数量：{len(minima_signals)}")

        # 合并信号
        signal_df = pl.concat([maxima_signals, minima_signals]).sort(
            ["datetime", "vt_symbol"]
        )

        # 合并成交量数据
        signal_df = signal_df.join(volume_df, on=["datetime", "vt_symbol"], how="left")

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

        # 保存信号
        self.lab.save_signal(self.name, self.signal_df)
        logger.info(f"信号已保存：{self.name}")

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
    # 创建数据中心 - AlphaLabV2（分层架构）
    # 参数：lab路径、项目名称、数据源、指数代码
    lab = AlphaLabV2(
        str(LAB_PATH),
        project_name="xgb_extrema",
        data_source="xt",
        index_code="csi300"  # 使用沪深300指数成分股
    )

    # 任务名称
    name = "300_xgb_extrema"

    # 指数代码
    index_symbol = "000300.SSE"

    # 测试期（需要预测的日期范围）
    start = "2026-04-14"
    end = "2026-04-15"

    # ========================================
    # 选股器参数配置
    # ========================================
    selector = XGBoostExtremaSelector(
        lab=lab,
        name=name,
        index_symbol=index_symbol,
        start=start,
        end=end,
        top_n=300,              # 选股数量（沪深300最多300只）
        train_period_days=300,  # 训练期天数（从 start 往前推）
        extended_days=100,      # 额外缓冲天数
    )

    # 运行选股
    signal_df = selector.run()

    # 显示结果
    logger.info("\n最终信号预览:")
    logger.info(signal_df.head(10))


if __name__ == "__main__":
    main()
