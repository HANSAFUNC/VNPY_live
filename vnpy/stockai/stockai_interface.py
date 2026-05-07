"""StockAI 模型接口基类 - 完全复刻 FreqAI IFreqaiModel"""

import threading
import time
from abc import ABC, abstractmethod
from collections import deque
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal, Optional

import numpy as np
import numpy.typing as npt
import pandas as pd
import psutil
from pandas import DataFrame

from vnpy.alpha.logger import logger

from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen


class IFreqaiModel(ABC):
    """
    StockAI 模型接口 - 完全复刻 FreqAI IFreqaiModel

    核心设计:
    - start() 统一入口，根据 live 模式分发
    - start_live() 实盘/模拟盘模式
    - start_backtesting() 回测模式（滑动窗口）
    - train/fit/predict 由子类实现
    """

    def __init__(self, config: dict) -> None:
        self.config = config
        self.assert_config(self.config)
        self.freqai_info: dict[str, Any] = config.get("freqai", {})
        self.data_split_parameters: dict[str, Any] = self.freqai_info.get(
            "data_split_parameters", {}
        )
        self.model_training_parameters: dict[str, Any] = self.freqai_info.get(
            "model_training_parameters", {}
        )
        self.identifier: str = self.freqai_info.get("identifier", "no_id")
        self.retrain = False
        self.first = True
        self.set_full_path()
        self.save_backtest_models: bool = self.freqai_info.get(
            "save_backtest_models", True
        )
        if self.save_backtest_models:
            logger.info("Backtesting module configured to save all models.")

        self.dd = StockaiDataDrawer(Path(self.full_path), self.config)
        self.current_candle: datetime = datetime.fromtimestamp(637887600, tz=UTC)
        self.dd.current_candle = self.current_candle
        self.scanning = False
        self.ft_params: dict[str, Any] = self.freqai_info.get(
            "feature_parameters", {}
        )
        self.corr_pairlist: list[str] = self.ft_params.get(
            "include_corr_pairlist", []
        )
        self.keras: bool = self.freqai_info.get("keras", False)

        self.CONV_WIDTH = self.freqai_info.get("conv_width", 1)
        self.class_names: list[str] = []
        self.pair_it = 0
        self.pair_it_train = 0
        self.total_pairs = len(
            self.config.get("exchange", {}).get("pair_whitelist", [])
        )
        self.train_queue: deque = self._set_train_queue()
        self.inference_time: float = 0
        self.train_time: float = 0
        self.begin_time: float = 0
        self.begin_time_train: float = 0
        self.base_tf_seconds = self.freqai_info.get("base_tf_seconds", 86400)
        self.continual_learning = self.freqai_info.get("continual_learning", False)
        self.plot_features = self.ft_params.get("plot_feature_importances", 0)
        self.corr_dataframes: dict[str, DataFrame] = {}
        self.get_corr_dataframes: bool = True
        self._threads: list[threading.Thread] = []
        self._stop_event = threading.Event()
        self.metadata: dict[str, Any] = self.dd.load_global_metadata_from_disk()
        self.data_provider: Any = None
        self.max_system_threads = max(int(psutil.cpu_count() * 2 - 2), 1)
        self.can_short = True
        self.model: Any = None
        self.dk: Optional[StockaiDataKitchen] = None
        self.live = False

        # FreqAI 风格别名
        self.data_split_params = self.data_split_parameters
        self.model_training_params = self.model_training_parameters

        if (
            self.ft_params.get("principal_component_analysis", False)
            and self.continual_learning
        ):
            self.ft_params.update({"principal_component_analysis": False})
            logger.warning(
                "User tried to use PCA with continual learning. Deactivating PCA."
            )

        self.activate_tensorboard: bool = self.freqai_info.get(
            "activate_tensorboard", True
        )
        self.tb_logger: Any = None

        logger.info(f"StockAI 模型接口初始化完成，路径: {self.full_path}")

    def __getstate__(self):
        return {}

    def assert_config(self, config: dict) -> None:
        if not config.get("freqai", {}):
            raise ValueError("配置中缺少 freqai 部分")

    def start(
        self, dataframe: DataFrame, metadata: dict, strategy: Any
    ) -> DataFrame:
        """
        统一入口，根据 live 模式分发到 start_live 或 start_backtesting

        :param dataframe: 完整 DataFrame（来自策略）
        :param metadata: {"pair": pair}
        :param strategy: 策略对象
        """
        self.live = self._check_if_live(strategy)
        self.dd.set_pair_dict_info(metadata)
        self.data_provider = getattr(strategy, "dp", None)
        self.can_short = getattr(strategy, "can_short", True)

        if self.live:
            self.inference_timer("start")
            self.dk = StockaiDataKitchen(
                self.config, self.live, metadata["pair"]
            )
            dk = self.start_live(dataframe, metadata, strategy, self.dk)
            dataframe = dk.remove_features_from_df(dk.return_dataframe)
        else:
            self.dk = StockaiDataKitchen(
                self.config, self.live, metadata["pair"]
            )
            if not self.config.get("freqai_backtest_live_models", False):
                logger.info(
                    f"Training {len(self.dk.training_timeranges)} timeranges"
                )
                dk = self.start_backtesting(
                    dataframe, metadata, self.dk, strategy
                )
                dataframe = dk.remove_features_from_df(dk.return_dataframe)
            else:
                logger.info(
                    "Backtesting using historic predictions (live models)"
                )
                dk = self.start_backtesting_from_historic_predictions(
                    dataframe, metadata, self.dk
                )
                dataframe = dk.return_dataframe

        self.clean_up()
        if self.live:
            self.inference_timer("stop", metadata["pair"])

        return dataframe

    def start_live(
        self,
        dataframe: DataFrame,
        metadata: dict,
        strategy: Any,
        dk: StockaiDataKitchen,
    ) -> StockaiDataKitchen:
        """
        实盘/模拟盘模式

        :param dataframe: 策略传入的 DataFrame
        :param metadata: {"pair": pair}
        :param strategy: 策略对象
        :param dk: 数据厨房
        """
        (_, trained_timestamp) = self.dd.get_pair_dict_info(metadata["pair"])

        if self.dd.historic_data:
            logger.debug(
                f"Updating historic data on pair {metadata['pair']}"
            )
            self.track_current_candle()

        (_, new_trained_timerange, data_load_timerange) = (
            dk.check_if_new_training_required(trained_timestamp)
        )
        stopts = (
            new_trained_timerange.get("stopts", 0)
            if isinstance(new_trained_timerange, dict)
            else new_trained_timerange
        )
        dk.set_paths(metadata["pair"], stopts)

        if not self.scanning:
            self.scanning = True

        try:
            self.model = self.dd.load_model(metadata["pair"])
        except (ValueError, FileNotFoundError):
            self.model = None

        if not self.model:
            logger.warning(
                f"No model ready for {metadata['pair']}, "
                "returning null values to strategy."
            )
            self.dd.return_null_values_to_strategy(dataframe, dk)
            return dk

        dk.find_labels(dataframe)

        self.build_strategy_return_arrays(
            dataframe, dk, metadata["pair"], trained_timestamp
        )

        return dk

    def start_backtesting(
        self,
        dataframe: DataFrame,
        metadata: dict,
        dk: StockaiDataKitchen,
        strategy: Any,
    ) -> StockaiDataKitchen:
        """
        回测模式 - 滑动窗口

        :param dataframe: 策略传入的 DataFrame
        :param metadata: {"pair": pair}
        :param dk: 数据厨房
        :param strategy: 策略对象
        """
        self.pair_it += 1
        train_it = 0
        pair = metadata["pair"]

        for tr_train, tr_backtest in zip(
            dk.training_timeranges,
            dk.backtesting_timeranges,
            strict=False,
        ):
            (_, _) = self.dd.get_pair_dict_info(pair)
            train_it += 1
            total_trains = len(dk.backtesting_timeranges)
            self.training_timerange = tr_train

            dataframe_train = dk.slice_dataframe(tr_train, dataframe)
            dataframe_backtest = dk.slice_dataframe(tr_backtest, dataframe)
            len_backtest_df = len(dataframe_backtest)

            if not self.ensure_data_exists(
                len_backtest_df, tr_backtest, pair
            ):
                continue

            self.log_backtesting_progress(
                tr_train, pair, train_it, total_trains
            )

            train_end_str = tr_train[1]
            fmt = "%Y-%m-%d" if "-" in train_end_str else "%Y%m%d"
            timestamp_model_id = int(
                datetime.strptime(train_end_str, fmt).timestamp()
            )

            dk.set_paths(pair, timestamp_model_id)
            dk.set_new_model_names(pair, timestamp_model_id)

            dk.get_unique_classes_from_labels(dataframe_train)

            if not self.model_exists(dk):
                dk.find_features(dataframe_train)
                dk.find_labels(dataframe_train)

                try:
                    self.model = self.train(dataframe_train, pair, dk)
                except Exception as msg:
                    logger.warning(
                        f"Training {pair} raised exception "
                        f"{msg.__class__.__name__}. "
                        f"Message: {msg}, skipping.",
                        exc_info=True,
                    )
                    self.model = None

                self.dd.pair_dict[pair][
                    "trained_timestamp"
                ] = timestamp_model_id
                if self.save_backtest_models and self.model is not None:
                    logger.info("Saving backtest model to disk.")
                    self.dd.save_model(
                        pair, self.model, timestamp_model_id, dk
                    )
            else:
                try:
                    self.model = self.dd.load_model(pair)
                except (ValueError, FileNotFoundError):
                    self.model = None

            if self.model is not None:
                pred_df, do_preds = self.predict(dataframe_backtest, dk)
                append_df = dk.get_predictions_to_append(
                    pred_df, do_preds, dataframe_backtest
                )
                dk.append_predictions(append_df)
                dk.save_backtesting_prediction(append_df)

        self.backtesting_fit_live_predictions(dk)
        dk.fill_predictions(dataframe)

        return dk

    def start_backtesting_from_historic_predictions(
        self,
        dataframe: DataFrame,
        metadata: dict,
        dk: StockaiDataKitchen,
    ) -> StockaiDataKitchen:
        pair = metadata["pair"]
        dk.return_dataframe = dataframe
        if pair in self.dd.historic_predictions:
            saved_dataframe = self.dd.historic_predictions[pair]
            columns_to_drop = list(
                set(saved_dataframe.columns).intersection(
                    dk.return_dataframe.columns
                )
            )
            dk.return_dataframe = dk.return_dataframe.drop(
                columns=list(columns_to_drop)
            )
            dk.return_dataframe = pd.merge(
                dk.return_dataframe,
                saved_dataframe,
                how="left",
                left_on="date",
                right_on="date_pred",
            )
        return dk

    def build_strategy_return_arrays(
        self,
        dataframe: DataFrame,
        dk: StockaiDataKitchen,
        pair: str,
        trained_timestamp: int,
    ) -> None:
        if pair not in self.dd.model_return_values:
            pred_df, do_preds = self.predict(dataframe, dk)
            if pair not in self.dd.historic_predictions:
                self.set_initial_historic_predictions(
                    pred_df, dk, pair, dataframe
                )
            self.dd.set_initial_return_values(pair, pred_df, dataframe)

            dk.return_dataframe = (
                self.dd.attach_return_values_to_return_dataframe(
                    pair, dataframe
                )
            )
            return
        elif self.dk and self.dk.check_if_model_expired(trained_timestamp):
            pred_df = DataFrame(
                np.zeros((2, len(dk.label_list))), columns=dk.label_list
            )
            do_preds = np.ones(2, dtype=np.int_) * 2
            dk.DI_values = np.zeros(2)
            logger.warning(
                f"Model expired for {pair}, returning null values to "
                "strategy. Strategy construction should take care to "
                "consider this event with prediction == 0 and "
                "do_predict == 2"
            )
        else:
            pred_df, do_preds = self.predict(
                dataframe.iloc[-self.CONV_WIDTH :], dk, first=False
            )

        if (
            self.freqai_info.get("fit_live_predictions_candles", 0)
            and self.live
        ):
            self.fit_live_predictions(dk, pair)
        self.dd.append_model_predictions(
            pair, pred_df, do_preds, dk, dataframe
        )
        dk.return_dataframe = (
            self.dd.attach_return_values_to_return_dataframe(pair, dataframe)
        )

    def check_if_feature_list_matches_strategy(
        self, dk: StockaiDataKitchen
    ) -> None:
        if dk.training_features_list != dk.data.get(
            "training_features_list", dk.training_features_list
        ):
            raise ValueError(
                "Trying to access pretrained model with `identifier` "
                "but found different features furnished by current "
                "strategy. Change `identifier` to train from scratch, or "
                "ensure the strategy is furnishing the same features as "
                "the pretrained model."
            )

    def model_exists(self, dk: StockaiDataKitchen) -> bool:
        if self.dd.model_type == "joblib":
            file_type = ".joblib"
        else:
            file_type = ".pkl"

        path_to_modelfile = Path(
            dk.data_path / f"{dk.model_filename}_model{file_type}"
        )
        file_exists = path_to_modelfile.is_file()
        if file_exists:
            logger.info(
                "Found model at %s", dk.data_path / dk.model_filename
            )
        else:
            logger.info(
                "Could not find model at %s",
                dk.data_path / dk.model_filename,
            )
        return file_exists

    def set_full_path(self) -> None:
        path = self.freqai_info.get("path", "freqai_models")
        self.full_path = Path(path) / self.identifier
        self.full_path.mkdir(parents=True, exist_ok=True)

    def ensure_data_exists(
        self, len_dataframe_backtest: int, tr_backtest: Any, pair: str
    ) -> bool:
        if len_dataframe_backtest == 0:
            tr_start = (
                tr_backtest[0]
                if isinstance(tr_backtest, tuple)
                else str(tr_backtest)
            )
            tr_end = (
                tr_backtest[1]
                if isinstance(tr_backtest, tuple)
                else str(tr_backtest)
            )
            logger.info(
                f"No data found for pair {pair} from "
                f"{tr_start} to {tr_end}. "
                "Probably more than one training within the same "
                "candle period."
            )
            return False
        return True

    def log_backtesting_progress(
        self, tr_train: Any, pair: str, train_it: int, total_trains: int
    ) -> None:
        tr_start = (
            tr_train[0]
            if isinstance(tr_train, tuple)
            else str(tr_train)
        )
        tr_end = (
            tr_train[1]
            if isinstance(tr_train, tuple)
            else str(tr_train)
        )
        logger.info(
            f"Training {pair}, {self.pair_it}/{self.total_pairs} pairs"
            f" from {tr_start} "
            f"to {tr_end}, {train_it}/{total_trains} "
            "trains"
        )

    def backtesting_fit_live_predictions(
        self, dk: StockaiDataKitchen
    ) -> None:
        fit_live_predictions_candles = self.freqai_info.get(
            "fit_live_predictions_candles", 0
        )
        if fit_live_predictions_candles:
            logger.info("Applying fit_live_predictions in backtesting")
            label_columns = [
                col
                for col in dk.full_df.columns
                if (
                    col.startswith("&")
                    and not col.endswith("_mean")
                    and not col.endswith("_std")
                    and col
                    not in dk.data.get("extra_returns_per_train", {})
                )
            ]

            for index in range(len(dk.full_df)):
                if index >= fit_live_predictions_candles:
                    self.dd.historic_predictions[dk.pair] = (
                        dk.full_df.iloc[
                            index - fit_live_predictions_candles : index
                        ]
                    )
                    self.fit_live_predictions(dk, dk.pair)
                    for label in label_columns:
                        if dk.full_df[label].dtype == object:
                            continue
                        if "labels_mean" in dk.data:
                            dk.full_df.at[
                                index, f"{label}_mean"
                            ] = dk.data["labels_mean"][label]
                        if "labels_std" in dk.data:
                            dk.full_df.at[
                                index, f"{label}_std"
                            ] = dk.data["labels_std"][label]

                    for extra_col in dk.data.get(
                        "extra_returns_per_train", {}
                    ):
                        dk.full_df.at[index, f"{extra_col}"] = dk.data[
                            "extra_returns_per_train"
                        ][extra_col]

    def fit_live_predictions(
        self, dk: StockaiDataKitchen, pair: str
    ) -> None:
        import scipy as spy

        full_labels = dk.label_list + dk.unique_class_list

        num_candles = self.freqai_info.get(
            "fit_live_predictions_candles", 100
        )
        dk.data["labels_mean"], dk.data["labels_std"] = {}, {}
        for label in full_labels:
            if (
                self.dd.historic_predictions[dk.pair][label].dtype
                == object
            ):
                continue
            f = spy.stats.norm.fit(
                self.dd.historic_predictions[dk.pair][label].tail(
                    num_candles
                )
            )
            dk.data["labels_mean"][label] = f[0]
            dk.data["labels_std"][label] = f[1]

    def set_initial_historic_predictions(
        self,
        pred_df: DataFrame,
        dk: StockaiDataKitchen,
        pair: str,
        strat_df: DataFrame,
    ) -> None:
        self.dd.historic_predictions[pair] = pred_df
        hist_preds_df = self.dd.historic_predictions[pair]

        for label in hist_preds_df.columns:
            if hist_preds_df[label].dtype == object:
                continue
            hist_preds_df[f"{label}_mean"] = 0
            hist_preds_df[f"{label}_std"] = 0

        hist_preds_df["do_predict"] = 0

        if self.ft_params.get("DI_threshold", 0) > 0:
            hist_preds_df["DI_values"] = 0

        for return_str in dk.data.get("extra_returns_per_train", {}):
            hist_preds_df[return_str] = dk.data[
                "extra_returns_per_train"
            ][return_str]

        if "high" in strat_df.columns:
            hist_preds_df["high_price"] = strat_df["high"]
        if "low" in strat_df.columns:
            hist_preds_df["low_price"] = strat_df["low"]
        if "close" in strat_df.columns:
            hist_preds_df["close_price"] = strat_df["close"]
        if "date" in strat_df.columns:
            hist_preds_df["date_pred"] = strat_df["date"]
        elif "datetime" in strat_df.columns:
            hist_preds_df["date_pred"] = strat_df["datetime"]

    def update_metadata(self, metadata: dict[str, Any]) -> None:
        self.dd.save_global_metadata_to_disk(metadata)
        self.metadata = metadata

    def clean_up(self) -> None:
        self.model = None
        self.dk = None

    def _on_stop(self) -> None:
        self.dd.save_historic_predictions_to_disk()

    def shutdown(self) -> None:
        logger.info("Stopping StockAI")
        self._stop_event.set()

        self.data_provider = None
        self._on_stop()

        if self.freqai_info.get(
            "wait_for_training_iteration_on_reload", True
        ):
            logger.info("Waiting on Training iteration")
            for _thread in self._threads:
                _thread.join()
        else:
            logger.warning(
                "Breaking current training iteration because "
                "you set wait_for_training_iteration_on_reload to False."
            )

    def inference_timer(
        self, do: Literal["start", "stop"] = "start", pair: str = ""
    ) -> None:
        if do == "start":
            self.pair_it += 1
            self.begin_time = time.time()
        elif do == "stop":
            end = time.time()
            time_spent = end - self.begin_time
            if self.freqai_info.get("write_metrics_to_disk", False):
                self.dd.update_metric_tracker(
                    "inference_time", time_spent, pair
                )
            self.inference_time += time_spent
            if self.pair_it == self.total_pairs:
                logger.info(
                    f"Total time spent inferencing pairlist "
                    f"{self.inference_time:.2f} seconds"
                )
                self.pair_it = 0
                self.inference_time = 0

    def train_timer(
        self, do: Literal["start", "stop"] = "start", pair: str = ""
    ) -> None:
        if do == "start":
            self.pair_it_train += 1
            self.begin_time_train = time.time()
        elif do == "stop":
            end = time.time()
            time_spent = end - self.begin_time_train
            if self.freqai_info.get("write_metrics_to_disk", False):
                self.dd.collect_metrics(time_spent, pair)
            self.train_time += time_spent
            if self.pair_it_train == self.total_pairs:
                logger.info(
                    f"Total time spent training pairlist "
                    f"{self.train_time:.2f} seconds"
                )
                self.pair_it_train = 0
                self.train_time = 0

    def get_init_model(self, pair: str) -> Any:
        if (
            pair not in self.dd.model_dictionary
            or not self.continual_learning
        ):
            init_model = None
        else:
            init_model = self.dd.model_dictionary[pair]
        return init_model

    def track_current_candle(self) -> None:
        if (
            hasattr(self.dd, "current_candle")
            and self.dd.current_candle > self.current_candle
        ):
            self.get_corr_dataframes = True
            self.pair_it = 1
            self.current_candle = self.dd.current_candle

    def _set_train_queue(self) -> deque:
        current_pairlist = self.config.get("exchange", {}).get(
            "pair_whitelist", []
        )
        if not self.dd.pair_dict:
            logger.info(
                f"Set fresh train queue from whitelist. "
                f"Queue: {current_pairlist}"
            )
            return deque(current_pairlist)

        best_queue: deque = deque()

        pair_dict_sorted = sorted(
            self.dd.pair_dict.items(),
            key=lambda k: k[1].get("trained_timestamp", 0),
        )
        for pair_item in pair_dict_sorted:
            if pair_item[0] in current_pairlist:
                best_queue.append(pair_item[0])
        for pair_item in current_pairlist:
            if pair_item not in best_queue:
                best_queue.appendleft(pair_item)

        logger.info(
            f"Set existing queue from trained timestamps. "
            f"Best approximation queue: {best_queue}"
        )
        return best_queue

    def _check_if_live(self, strategy: Any) -> bool:
        dp = getattr(strategy, "dp", None)
        if dp is not None:
            runmode = getattr(dp, "runmode", None)
            if runmode is not None:
                return str(runmode) in (
                    "RunMode.DRY_RUN",
                    "RunMode.LIVE",
                )
        return getattr(strategy, "live", False)

    def define_data_pipeline(self, threads: int = -1) -> Any:
        import datasieve.transforms as ds
        from datasieve.pipeline import Pipeline
        from datasieve.transforms import SKLearnWrapper
        from sklearn.preprocessing import MinMaxScaler

        ft_params = self.freqai_info.get("feature_parameters", {})
        pipe_steps = [
            ("const", ds.VarianceThreshold(threshold=0)),
            (
                "scaler",
                SKLearnWrapper(MinMaxScaler(feature_range=(-1, 1))),
            ),
        ]

        if ft_params.get("principal_component_analysis", False):
            pipe_steps.append(("pca", ds.PCA(n_components=0.999)))
            pipe_steps.append(
                (
                    "post-pca-scaler",
                    SKLearnWrapper(
                        MinMaxScaler(feature_range=(-1, 1))
                    ),
                )
            )

        if ft_params.get("use_SVM_to_remove_outliers", False):
            svm_params = ft_params.get(
                "svm_params", {"shuffle": False, "nu": 0.01}
            )
            pipe_steps.append(
                ("svm", ds.SVMOutlierExtractor(**svm_params))
            )

        di = ft_params.get("DI_threshold", 0)
        if di:
            pipe_steps.append(
                (
                    "di",
                    ds.DissimilarityIndex(
                        di_threshold=di, n_jobs=threads
                    ),
                )
            )

        if ft_params.get("use_DBSCAN_to_remove_outliers", False):
            pipe_steps.append(("dbscan", ds.DBSCAN(n_jobs=threads)))

        sigma = ft_params.get("noise_standard_deviation", 0)
        if sigma:
            pipe_steps.append(("noise", ds.Noise(sigma=sigma)))

        return Pipeline(pipe_steps)

    def define_label_pipeline(self, threads: int = -1) -> Any:
        from datasieve.pipeline import Pipeline
        from datasieve.transforms import SKLearnWrapper
        from sklearn.preprocessing import MinMaxScaler

        return Pipeline(
            [
                (
                    "scaler",
                    SKLearnWrapper(
                        MinMaxScaler(feature_range=(-1, 1))
                    ),
                ),
            ]
        )

    @abstractmethod
    def train(
        self,
        unfiltered_df: DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """子类实现：训练流程"""

    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> Any:
        """子类实现：模型拟合"""

    @abstractmethod
    def predict(
        self,
        unfiltered_df: DataFrame,
        dk: StockaiDataKitchen,
        **kwargs,
    ) -> tuple[DataFrame, npt.NDArray[np.int_]]:
        """子类实现：预测"""
