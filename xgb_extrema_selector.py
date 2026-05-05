"""
XGBoost 极值选股器 (StockAI + FreqAI 架构)

设计:
- 策略层: 使用 QuickAdapterV5Dataset 计算特征 (%-前缀) 和标签 (&-前缀)
- StockAI 层: 只负责训练/预测流程管理
"""
import warnings

from vnpy.alpha import Segment
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning)

from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Callable

import polars as pl
import numpy as np

from vnpy.trader.constant import Interval
from vnpy.alpha.lab_v2 import AlphaLabV2Engine as AlphaLabV2
from vnpy.alpha.dataset.datasets.quick_adapter_v5 import QuickAdapterV5Dataset
from vnpy.stockai.prediction_models.xgb_extrema_model import XGBoostExtremaModel
from vnpy.stockai.data_kitchen import StockaiDataKitchen
from vnpy.alpha.logger import logger


SCRIPT_DIR = Path(__file__).parent.resolve()
LAB_PATH = SCRIPT_DIR / "lab"


@dataclass
class SelectorConfig:
    """选股器配置 - 支持 StockAI 高级功能"""
    # 数据参数
    top_n: int = 300
    train_period_days: int = 300
    extended_days: int = 100
    interval: Interval = Interval.DAILY

    # XGBoost参数
    learning_rate: float = 0.05
    max_depth: int = 6
    n_estimators: int = 100
    early_stopping_rounds: int = 50

    # 数据分割
    test_size: float = 0.2
    shuffle: bool = False

    # 批次处理
    data_batch_size: int = 50

    # 滑动窗口回测参数
    backtest_period_days: int = 1  # 每次预测未来N天

    # QuickAdapterV5 参数
    periods: list[int] = None
    label_period_candles: int = 5
    include_shifted_candles: list[int] = None

    # ===== StockAI 高级功能配置 =====

    # 1. 近期样本加权 (set_weights_higher_recent)
    # weight_factor > 0 时启用，值越大近期样本权重越高
    use_weighted_training: bool = False
    weight_factor: float = 1.0  # 衰减因子，推荐 0.5-2.0

    # 2. PCA 降维
    use_pca: bool = False
    pca_n_components: float = 0.999  # 保留方差比例 (0.9-0.999)

    # 3. SVM 异常值检测
    use_svm_outlier_detection: bool = False
    svm_nu: float = 0.01  # 异常值比例预期
    svm_shuffle: bool = False

    # 4. DI (Dissimilarity Index) 漂移检测
    # DI_threshold > 0 时启用，值越大容忍度越高
    di_threshold: float = 10  # 推荐 0 (禁用) 或 1.0-3.0

    # 5. DBSCAN 异常值检测
    use_dbscan_outlier_detection: bool = False
    dbscan_eps: float = 0.5  # 邻域半径

    # 6. 噪声注入 (数据增强)
    noise_sigma: float = 0  # 噪声标准差，0 表示禁用，推荐 0.001-0.01

    # 7. 回测实时模型模式
    # True: 回测时复用已训练模型，不重新训练
    backtest_live_models: bool = False

    # 8. 重新训练间隔（天）
    retrain_days: int = 5  # 每5天重新训练一次

    # 9. 动态阈值计算 (fit_live_predictions)
    # True: 根据历史预测自适应调整极值阈值
    use_fit_live_predictions: bool = True
    fit_live_predictions_candles: int = 20  # 历史预测样本数

    def __post_init__(self):
        if self.periods is None:
            self.periods = [10, 20, 30, 40]
        if self.include_shifted_candles is None:
            self.include_shifted_candles = [1, 2, 3]


class XGBoostExtremaSelector:
    """XGBoost 极值选股器 - 策略层"""

    def __init__(
        self,
        lab: AlphaLabV2,
        name: str,
        start: str,
        end: str,
        config: SelectorConfig = None,
        stockai_path: Optional[Path] = None,
    ):
        self.lab = lab
        self.name = name
        self.start = start
        self.end = end
        self.config = config if config else SelectorConfig()

        self.interval = self.config.interval
        self.top_n = self.config.top_n
        self.train_period_days = self.config.train_period_days
        self.extended_days = self.config.extended_days

        # StockAI 配置
        self.stockai_path = stockai_path or (LAB_PATH / "stockai_data" / name)
        self.stockai_config = self._build_stockai_config()

        # 数据集
        self.dataset: Optional[QuickAdapterV5Dataset] = None
        self.result_df: Optional[pl.DataFrame] = None
        self.signal_df: Optional[pl.DataFrame] = None

        # StockAI 模型实例
        self.stockai_model: Optional[XGBoostExtremaModel] = None

    def _build_stockai_config(self) -> dict:
        """构建 StockAI 配置"""
        return {
            "path": str(self.stockai_path),
            "interval": self.interval.value if hasattr(self.interval, 'value') else str(self.interval),
            "feature_parameters": {
                "periods": self.config.periods,
                "label_period_candles": self.config.label_period_candles,
                "include_shifted_candles": self.config.include_shifted_candles,
                # 近期样本加权
                "weight_factor": self.config.weight_factor if self.config.use_weighted_training else 0,
                # PCA 降维
                "principal_component_analysis": self.config.use_pca,
                "pca_n_components": self.config.pca_n_components,
                # SVM 异常值检测
                "use_SVM_to_remove_outliers": self.config.use_svm_outlier_detection,
                "svm_params": {"nu": self.config.svm_nu, "shuffle": self.config.svm_shuffle},
                # DI 漂移检测
                "DI_threshold": self.config.di_threshold,
                # DBSCAN 异常值检测
                "use_DBSCAN_to_remove_outliers": self.config.use_dbscan_outlier_detection,
                "dbscan_eps": self.config.dbscan_eps,
                # 噪声注入
                "noise_standard_deviation": self.config.noise_sigma,
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
            # 回测实时模型模式
            "backtest_live_models": self.config.backtest_live_models,
            # 重新训练间隔
            "retrain_days": self.config.retrain_days,
            # 动态阈值计算
            "fit_live_predictions": self.config.use_fit_live_predictions,
            "fit_live_predictions_candles": self.config.fit_live_predictions_candles,
        }

    def load_data(self) -> pl.DataFrame:
        """加载指数成分股数据"""
        logger.info("=" * 60)
        logger.info("1. 加载数据")
        logger.info("=" * 60)

        # 获取成分股
        component_symbols = self.lab.get_component_symbols(
            start=self.start, end=self.end
        )
        logger.info(f"指数: {self.lab.index_code}, 成分股: {len(component_symbols)}")

        if not component_symbols:
            raise ValueError(f"未找到指数 {self.lab.index_code} 的成分股数据")

        # 取前 top_n
        top_symbols = component_symbols[:self.top_n]
        logger.info(f"选股范围: 前{len(top_symbols)}只")

        # 计算数据范围
        start_dt = datetime.strptime(self.start, "%Y-%m-%d")
        train_buffer_days = self.train_period_days + self.extended_days
        data_start_dt = start_dt - timedelta(days=train_buffer_days)
        data_start_str = data_start_dt.strftime("%Y-%m-%d")

        logger.info(f"数据范围: {data_start_str} ~ {self.end}")

        # 分批加载
        batch_size = self.config.data_batch_size
        all_dfs = []

        for i in range(0, len(top_symbols), batch_size):
            batch = top_symbols[i:i + batch_size]
            logger.info(f"  加载批次 {i//batch_size + 1}: {len(batch)} 只")

            df_batch = self.lab.load_bars_df(
                batch, self.interval, data_start_str, self.end
            )
            if df_batch is not None and len(df_batch) > 0:
                all_dfs.append(df_batch)

        if not all_dfs:
            return pl.DataFrame()

        df = pl.concat(all_dfs)
        logger.info(f"数据形状: {df.shape}")
        return df

    def compute_features(self, df: pl.DataFrame) -> QuickAdapterV5Dataset:
        """
        计算特征 - 策略层负责

        使用 QuickAdapterV5Dataset 生成:
        - %-前缀的特征列
        - &-前缀的标签列 (&s-extrema)
        """
        logger.info("\n" + "=" * 60)
        logger.info("2. 计算特征")
        logger.info("=" * 60)

        # 计算日期范围
        start_dt = datetime.strptime(self.start, "%Y-%m-%d")
        train_buffer_days = self.train_period_days + self.extended_days
        train_start_dt = start_dt - timedelta(days=train_buffer_days)
        train_start_str = train_start_dt.strftime("%Y-%m-%d")

        # 训练/验证/测试期分割
        train_end_offset = int(self.train_period_days * 0.8)
        train_end_dt = start_dt - timedelta(days=self.train_period_days - train_end_offset)
        train_end_str = train_end_dt.strftime("%Y-%m-%d")

        valid_end_dt = start_dt - timedelta(days=1)
        valid_end_str = valid_end_dt.strftime("%Y-%m-%d")

        train_period = (train_start_str, train_end_str)
        valid_period = (train_end_str, valid_end_str)
        test_period = (self.start, self.end)

        logger.info(f"训练期: {train_period}")
        logger.info(f"验证期: {valid_period}")
        logger.info(f"测试期: {test_period}")

        # 创建 Dataset - 内部计算特征
        dataset = QuickAdapterV5Dataset(
            df,
            train_period=train_period,
            valid_period=valid_period,
            test_period=test_period,
            periods=self.config.periods,
            label_period_candles=self.config.label_period_candles,
            include_shifted_candles=self.config.include_shifted_candles,
        )

        # 准备数据
        filters = self.lab.get_component_filters(start=train_start_str, end=self.end)
        dataset.prepare_data(filters, max_workers=3)
        dataset.process_data()

        # 统计特征数量
        feature_cols = [c for c in dataset.learn_df.columns if c.startswith('%-')]
        logger.info(f"特征数量: {len(feature_cols)}")
        logger.info(f"标签: &s-extrema")

        self.dataset = dataset
        return dataset

    def train_models(self) -> XGBoostExtremaModel:
        """
        训练模型 - 使用 StockAI

        每只股票一个模型，使用 learn_df 中的特征和标签
        """
        logger.info("\n" + "=" * 60)
        logger.info("3. 训练模型 (StockAI)")
        logger.info("=" * 60)

        # 创建 StockAI 模型实例
        stockai_model = XGBoostExtremaModel(self.stockai_config, self.lab)
        self.stockai_model = stockai_model

        learn_df = self.dataset.fetch_learn(Segment.TRAIN)
        unique_symbols = learn_df["vt_symbol"].unique().to_list()
        total = len(unique_symbols)

        logger.info(f"需要训练 {total} 个模型")

        trained_count = 0

        for i, symbol in enumerate(unique_symbols, 1):
            logger.info(f"\n[{i}/{total}] 训练: {symbol}")

            try:
                # 提取该股票的数据 (已包含 %-特征 和 &-标签)
                symbol_df = learn_df.filter(pl.col("vt_symbol") == symbol)

                if len(symbol_df) == 0:
                    logger.warning(f"  [SKIP] 无数据: {symbol}")
                    continue

                # 使用 StockAI 训练
                # stockai_model.start() 会:
                # 1. 识别特征列 (%-前缀) 和标签列 (&-前缀)
                # 2. 检查是否需要重新训练
                # 3. 执行训练流程
                stockai_model.start(
                    df=symbol_df,
                    pair=symbol,
                )

                trained_count += 1
                logger.info(f"  [OK] 训练完成: {symbol}")

            except Exception as e:
                logger.error(f"  [FAIL] 训练失败: {symbol} - {e}")
                import traceback
                logger.error(traceback.format_exc())

        logger.info(f"\n训练完成: {trained_count}/{total} 个模型")
        return stockai_model

    def generate_signals(self) -> pl.DataFrame:
        """生成交易信号"""
        logger.info("\n" + "=" * 60)
        logger.info("4. 生成信号")
        logger.info("=" * 60)

        if not self.stockai_model:
            logger.error("StockAI 模型未初始化")
            return pl.DataFrame()

        test_df = self.dataset.fetch_infer(Segment.TEST)    
        unique_symbols = test_df["vt_symbol"].unique().to_list()

        all_predictions = []

        for symbol in unique_symbols:
            try:
                # 提取该股票的数据
                symbol_df = test_df.filter(pl.col("vt_symbol") == symbol)

                if len(symbol_df) == 0:
                    continue

                # 使用 StockAI start 方法进行预测
                # start 方法会处理模型加载和预测
                result_df = self.stockai_model.start(
                    df=symbol_df,
                    pair=symbol,
                )
              
                # logger.info(f"预测结果: {result_df.head(10)}")
                # 提取预测结果并添加股票代码
                # 保留所有预测相关列（包括阈值和DI参数）
                prediction_col = "&s-extrema"
                if prediction_col in result_df.columns:
                    # 选择所有需要的列
                    select_cols = [
                        "datetime",
                        prediction_col,
                        "&s-maxima_sort_threshold",
                        "&s-minima_sort_threshold",
                        "DI_cutoff",
                        "DI_values",
                 
                    ]
                    # 只选择实际存在的列
                    available_cols = [c for c in select_cols if c in result_df.columns]
                    predictions_df = result_df.select(available_cols).with_columns([pl.lit(symbol).alias("vt_symbol")])
                    logger.info(f"预测结果: {predictions_df.head(10)}")
                    all_predictions.append(predictions_df)

            except Exception as e:
                logger.error(f"预测失败: {symbol} - {e}")
                import traceback
                logger.error(traceback.format_exc())
                continue

        if not all_predictions:
            logger.warning("没有预测结果")
            return pl.DataFrame()

        # 合并预测结果
        result_df = pl.concat(all_predictions).sort(["datetime", "vt_symbol"])
        self.result_df = result_df

        logger.info(f"预测结果形状: {result_df.shape}")
     
        # 生成信号 (基于阈值)
        # 使用动态阈值：预测值 > maxima_threshold 为极大值点，< minima_threshold 为极小值点

        maxima_signals = result_df.filter(
            pl.col("&s-extrema") > pl.col("&s-maxima_sort_threshold")
        ).select([
            "datetime", "vt_symbol", "&s-extrema",
            "&s-maxima_sort_threshold", "&s-minima_sort_threshold",
            "DI_cutoff"
        ])

        minima_signals = result_df.filter(
            pl.col("&s-extrema") < pl.col("&s-minima_sort_threshold")
        ).select([
            "datetime", "vt_symbol", "&s-extrema",
            "&s-maxima_sort_threshold", "&s-minima_sort_threshold",
            "DI_cutoff"
        ])

        # 添加信号列
        maxima_signals = maxima_signals.with_columns(pl.lit(-1).alias("signal"))
        minima_signals = minima_signals.with_columns(pl.lit(1).alias("signal"))

        logger.info(f"Maxima 信号: {len(maxima_signals)}")
        logger.info(f"Minima 信号: {len(minima_signals)}")

        # 合并信号
        signal_df = pl.concat([maxima_signals, minima_signals]).sort(
            ["datetime", "vt_symbol"]
        )

        self.signal_df = signal_df

        # 保存信号到 lab
        if self.lab and hasattr(self.lab, 'save_signal') and len(signal_df) > 0:
            self.lab.save_signal(self.name, signal_df)
            logger.info(f"信号已保存到 lab: {self.name}")

        return signal_df

    def run_sliding_window(self) -> pl.DataFrame:
        """
        滑动窗口回测

        每隔 backtest_period_days 训练一次，每次使用 train_period_days 历史数据
        用于累积历史预测，支持 fit_live_predictions 动态阈值
        """
        from vnpy.stockai.utils import create_full_timerange

        logger.info("\n" + "#" * 60)
        logger.info(f"# XGBoost 极值选股器 - 滑动窗口回测 - {self.name}")
        logger.info("#" * 60)

        # 1. 加载数据
        df = self.load_data()

        # 2. 计算特征 (策略层)
        self.compute_features(df)

        # 3. 使用 DataKitchen 分割时间窗口
        # 需要完整时间范围（包含训练前置期）
        full_start, full_end = create_full_timerange(
            self.start, self.end, self.train_period_days
        )

        # 创建临时 DataKitchen 用于分割
        temp_dk = StockaiDataKitchen(self.stockai_config, "TEMP", self.lab)
        train_ranges, predict_ranges = temp_dk.split_timerange(
            full_start, full_end,
            self.train_period_days,
            self.config.backtest_period_days
        )

        logger.info(f"\n时间窗口分割完成:")
        logger.info(f"  训练窗口数量: {len(train_ranges)}")
        logger.info(f"  预测窗口数量: {len(predict_ranges)}")
        logger.info(f"  时间范围: {full_start} ~ {full_end}")
        if len(train_ranges) > 0:
            for i, (tr, pr) in enumerate(zip(train_ranges, predict_ranges)):
                logger.info(f"    窗口 {i+1}: 训练 {tr[0]}~{tr[1]}, 预测 {pr[0]}~{pr[1]}")

        all_signals = []

        # 创建单个 StockAI 模型实例（所有窗口和股票共享 DataDrawer）
        stockai_model = XGBoostExtremaModel(self.stockai_config, self.lab)

        # 4. 滑动窗口循环
        for i, (train_range, predict_range) in enumerate(zip(train_ranges, predict_ranges)):
            logger.info(f"\n{'='*60}")
            logger.info(f"窗口 {i+1}/{len(train_ranges)}")
            logger.info(f"  训练期: {train_range}")
            logger.info(f"  预测期: {predict_range}")
            logger.info(f"{'='*60}")

            # 4.1 分割数据集
            # 将字符串日期转换为 datetime 进行比较
            train_start_dt = datetime.strptime(train_range[0], "%Y-%m-%d")
            train_end_dt = datetime.strptime(train_range[1], "%Y-%m-%d")
            predict_start_dt = datetime.strptime(predict_range[0], "%Y-%m-%d")
            predict_end_dt = datetime.strptime(predict_range[1], "%Y-%m-%d")

            train_df = self.dataset.learn_df.filter(
                (pl.col("datetime") >= train_start_dt) & (pl.col("datetime") < train_end_dt)
            )
            predict_df = self.dataset.learn_df.filter(
                (pl.col("datetime") >= predict_start_dt) & (pl.col("datetime") <= predict_end_dt)
            )

            if len(train_df) == 0:
                logger.warning(f"  [SKIP] 训练集为空")
                continue

            if len(predict_df) == 0:
                logger.warning(f"  [SKIP] 预测集为空")
                continue

            logger.info(f"  训练样本: {len(train_df)}, 预测样本: {len(predict_df)}")

            # 4.2 为每只股票训练和预测（共享 model 实例）
            window_signals = self._process_window(train_df, predict_df, stockai_model, i+1)

            if len(window_signals) > 0:
                all_signals.append(window_signals)
                logger.info(f"  本窗口信号数: {len(window_signals)}")

        # 5. 合并所有窗口的信号
        if all_signals:
            self.signal_df = pl.concat(all_signals).sort(["datetime", "vt_symbol"])
            logger.info(f"\n{'='*60}")
            logger.info(f"滑动窗口回测完成! 总信号数: {len(self.signal_df)}")
            logger.info(f"{'='*60}")

            # 保存信号
            if self.lab and hasattr(self.lab, 'save_signal'):
                self.lab.save_signal(self.name, self.signal_df)
        else:
            logger.warning("未生成任何信号")
            self.signal_df = pl.DataFrame()

        return self.signal_df

    def _process_window(self, train_df: pl.DataFrame, predict_df: pl.DataFrame, stockai_model: XGBoostExtremaModel, window_idx: int) -> pl.DataFrame:
        """处理单个窗口的训练和预测"""
        # 获取唯一股票列表
        train_symbols = train_df["vt_symbol"].unique().to_list()
        predict_symbols = predict_df["vt_symbol"].unique().to_list()
        all_symbols = list(set(train_symbols + predict_symbols))

        all_predictions = []

        # 训练并预测每只股票
        for symbol in all_symbols:
            try:
                # 提取该股票数据
                symbol_train = train_df.filter(pl.col("vt_symbol") == symbol)
                symbol_predict = predict_df.filter(pl.col("vt_symbol") == symbol)

                if len(symbol_train) == 0:
                    continue
                if len(symbol_predict) == 0:
                    continue
                # 训练和预测：传入训练数据和预测数据，start() 内部处理
                result_df = stockai_model.start(
                    train_df=symbol_train,
                    predict_df=symbol_predict,
                    pair=symbol
                )
                   

                # 提取预测结果
                prediction_col = "&s-extrema"
                if prediction_col in result_df.columns:
                    pred = result_df.select([
                        "datetime", prediction_col,
                        "&s-maxima_sort_threshold", "&s-minima_sort_threshold",
                        "DI_values",
                        "DI_cutoff"
                    ]).with_columns([pl.lit(symbol).alias("vt_symbol")])
                    all_predictions.append(pred)
                    logger.info(f"预测结果: {pred.tail(10)}")
            except Exception as e:
                logger.error(f"  {symbol} 处理失败: {e}")
                continue

        # 合并预测并生成信号
        if not all_predictions:
            return pl.DataFrame()

        result_df = pl.concat(all_predictions).sort(["datetime", "vt_symbol"])

        # 生成信号
        maxima_signals = result_df.filter(
            pl.col("&s-extrema") > pl.col("&s-maxima_sort_threshold")
        ).select([
            "datetime", "vt_symbol", "&s-extrema",
            "&s-maxima_sort_threshold", "&s-minima_sort_threshold", "DI_cutoff", "DI_values"
        ]).with_columns(pl.lit(-1).alias("signal"))

        minima_signals = result_df.filter(
            pl.col("&s-extrema") < pl.col("&s-minima_sort_threshold")
        ).select([
            "datetime", "vt_symbol", "&s-extrema",
            "&s-maxima_sort_threshold", "&s-minima_sort_threshold", "DI_cutoff", "DI_values"
        ]).with_columns(pl.lit(1).alias("signal"))

        return pl.concat([maxima_signals, minima_signals]) if len(maxima_signals) > 0 or len(minima_signals) > 0 else pl.DataFrame()

    def run(self) -> pl.DataFrame:
        """运行完整选股流程"""
        logger.info("\n" + "#" * 60)
        logger.info(f"# XGBoost 极值选股器 - {self.name}")
        logger.info("#" * 60)

        # 1. 加载数据
        df = self.load_data()

        # 2. 计算特征 (策略层)
        self.compute_features(df)

        # 3. 训练模型 (StockAI)
        self.train_models()

        # 4. 生成信号
        self.generate_signals()

        logger.info("\n" + "=" * 60)
        logger.info("选股完成!")
        logger.info("=" * 60)

        return self.signal_df


def main():
    """主函数"""
    from vnpy.trader.setting import SETTINGS
    from vnpy.event import EventEngine
    from vnpy.trader.engine import MainEngine

    # 配置
    SETTINGS["database.name"] = "postgresql"
    SETTINGS["database.host"] = "localhost"
    SETTINGS["database.port"] = "5432"
    SETTINGS["database.database"] = "vnpy"
    SETTINGS["database.user"] = "vnpy"
    SETTINGS["database.password"] = "vnpy"
    SETTINGS["datafeed.name"] = "xt"
    SETTINGS["datafeed.username"] = "client"
    SETTINGS["datafeed.password"] = ""

    # 初始化
    event_engine = EventEngine()
    main_engine = MainEngine(event_engine)

    lab = AlphaLabV2(
        main_engine=main_engine,
        event_engine=event_engine,
        root_path=str(LAB_PATH),
        project_name="xgb_extrema",
        data_source="xt",
        index_code="csi300"
    )

    # 配置 - 滑动窗口回测
    config = SelectorConfig(
        top_n=100,
        train_period_days=120,      # 每次训练用前120天
        extended_days=100,
        backtest_period_days=1,     # 每5天重新训练
        use_fit_live_predictions=True,
        fit_live_predictions_candles=20,
        retrain_days=5
    )

    selector = XGBoostExtremaSelector(
        lab=lab,
        name="300_xgb_extrema",
        start="2026-04-01",         # 回测开始
        end="2026-04-30",           # 回测结束
        config=config,
    )

    # 运行滑动窗口回测
    signal_df = selector.run_sliding_window()

    if signal_df is not None and len(signal_df) > 0:
        logger.info("\n最终信号:")
        logger.info(signal_df.head(10))
    else:
        logger.warning("\n没有生成信号")


if __name__ == "__main__":
    main()
