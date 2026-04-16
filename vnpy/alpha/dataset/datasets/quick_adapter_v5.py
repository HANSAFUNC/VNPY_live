"""QuickAdapterV5 feature dataset from freqtrade."""

import polars as pl
import numpy as np
import talib
from typing import cast

from vnpy.alpha import AlphaDataset


class QuickAdapterV5Dataset(AlphaDataset):
    """Dataset with features from freqtrade QuickAdapterV5 strategy"""

    def __init__(
        self,
        df: pl.DataFrame,
        train_period: tuple[str, str],
        valid_period: tuple[str, str],
        test_period: tuple[str, str],
        periods: list[int] = [10, 20, 30, 40, 50],
    ) -> None:
        """Constructor

        Parameters
        ----------
        df : pl.DataFrame
            Raw OHLCV data
        train_period : tuple[str, str]
            Training period
        valid_period : tuple[str, str]
            Validation period
        test_period : tuple[str, str]
            Test period
        periods : list[int]
            Periods for expand_all features
        """
        super().__init__(
            df=df,
            train_period=train_period,
            valid_period=valid_period,
            test_period=test_period,
        )

        self.periods = periods

        # Add features using result DataFrame (talib required)
        self._add_expand_all_features()
        self._add_expand_basic_features()
        self._add_standard_features()

        # Set label
        self.set_label("ts_delay(close, -3) / ts_delay(close, -1) - 1")

    def _add_expand_all_features(self) -> None:
        """Add period-based features (expand_all)"""
        for period in self.periods:
            # RSI
            rsi_df = self._compute_talib_feature(
                "rsi", period,
                lambda o, h, l, c, v: talib.RSI(c, timeperiod=period)
            )
            self.add_feature(f"%-rsi-{period}", result=rsi_df)

            # MFI
            mfi_df = self._compute_talib_feature(
                "mfi", period,
                lambda o, h, l, c, v: talib.MFI(h, l, c, v, timeperiod=period)
            )
            self.add_feature(f"%-mfi-{period}", result=mfi_df)

            # ADX
            adx_df = self._compute_talib_feature(
                "adx", period,
                lambda o, h, l, c, v: talib.ADX(h, l, c, timeperiod=period)
            )
            self.add_feature(f"%-adx-{period}", result=adx_df)

            # CCI
            cci_df = self._compute_talib_feature(
                "cci", period,
                lambda o, h, l, c, v: talib.CCI(h, l, c, timeperiod=period)
            )
            self.add_feature(f"%-cci-{period}", result=cci_df)

            # ROCR
            rocr_df = self._compute_talib_feature(
                "rocr", period,
                lambda o, h, l, c, v: talib.ROCR(c, timeperiod=period)
            )
            self.add_feature(f"%-rocr-{period}", result=rocr_df)

            # ATR
            atr_df = self._compute_talib_feature(
                "atr", period,
                lambda o, h, l, c, v: talib.ATR(h, l, c, timeperiod=period)
            )
            self.add_feature(f"%-atr-{period}", result=atr_df)

            # ATR%
            atr_pct_df = self._compute_talib_feature(
                "atrp", period,
                lambda o, h, l, c, v: talib.ATR(h, l, c, timeperiod=period) / c * 1000
            )
            self.add_feature(f"%-atrp-{period}", result=atr_pct_df)

            # LINEARREG_ANGLE
            linear_df = self._compute_talib_feature(
                "linear", period,
                lambda o, h, l, c, v: talib.LINEARREG_ANGLE(c, timeperiod=period)
            )
            self.add_feature(f"%-linear-{period}", result=linear_df)

            # ER (Efficiency Ratio) - needs custom calculation
            er_df = self._compute_er(period)
            self.add_feature(f"%-er-{period}", result=er_df)

            # CMF (Chaikin Money Flow) - needs custom calculation
            cmf_df = self._compute_cmf(period)
            self.add_feature(f"%-cmf-{period}", result=cmf_df)

            # TCP (Top Percent Change) - needs custom calculation
            tcp_df = self._compute_tcp(period)
            self.add_feature(f"%-tcp-{period}", result=tcp_df)

            # CTI (Correlation Trend Indicator) - needs pandas_ta
            cti_df = self._compute_cti(period)
            self.add_feature(f"%-cti-{period}", result=cti_df)

            # CHOP (Choppiness Index) - needs custom calculation
            chop_df = self._compute_chop(period)
            self.add_feature(f"%-chop-{period}", result=chop_df)

    def _add_expand_basic_features(self) -> None:
        """Add basic features (expand_basic)"""
        # pct_change
        pct_df = self._compute_feature(lambda o, h, l, c, v: np.zeros(len(c)))
        pct_df = pct_df.with_columns(
            pl.col("data").shift(1).over("vt_symbol").alias("prev_close")
        )
        pct_df = pct_df.with_columns(
            ((pl.col("data") - pl.col("prev_close")) / pl.col("prev_close")).alias("data")
        )
        self.add_feature("%-pct-change", result=pct_df.select(["datetime", "vt_symbol", "data"]))

        # raw_volume
        vol_df = self.df.select(["datetime", "vt_symbol", pl.col("volume").alias("data")])
        self.add_feature("%-raw_volume", result=vol_df)

        # OBV
        obv_df = self._compute_talib_feature(
            "obv", 0,
            lambda o, h, l, c, v: talib.OBV(c, v)
        )
        self.add_feature("%-obv", result=obv_df)

        # BB width
        bb_df = self._compute_bb_width()
        self.add_feature("%-bb_width", result=bb_df)

        # IBS (Internal Bar Strength)
        ibs_df = self.df.select([
            "datetime",
            "vt_symbol",
            ((pl.col("close") - pl.col("low")) / (pl.col("high") - pl.col("low") + 1e-12)).alias("data")
        ])
        self.add_feature("%-ibs", result=ibs_df)

        # EMA distances
        ema50_df = self._compute_talib_feature(
            "ema50", 50,
            lambda o, h, l, c, v: talib.EMA(c, timeperiod=50)
        )
        dist_ema50_df = self._compute_distance(ema50_df)
        self.add_feature("%-distema50", result=dist_ema50_df)

        ema12_df = self._compute_talib_feature(
            "ema12", 12,
            lambda o, h, l, c, v: talib.EMA(c, timeperiod=12)
        )
        dist_ema12_df = self._compute_distance(ema12_df)
        self.add_feature("%-distema12", result=dist_ema12_df)

        ema26_df = self._compute_talib_feature(
            "ema26", 26,
            lambda o, h, l, c, v: talib.EMA(c, timeperiod=26)
        )
        dist_ema26_df = self._compute_distance(ema26_df)
        self.add_feature("%-distema26", result=dist_ema26_df)

        # MACD
        macd_df = self._compute_talib_feature(
            "macd", 0,
            lambda o, h, l, c, v: talib.MACD(c, fastperiod=12, slowperiod=26, signalperiod=9)[0]
        )
        self.add_feature("%-macd", result=macd_df)

        macdsignal_df = self._compute_talib_feature(
            "macdsignal", 0,
            lambda o, h, l, c, v: talib.MACD(c, fastperiod=12, slowperiod=26, signalperiod=9)[1]
        )
        self.add_feature("%-macdsignal", result=macdsignal_df)

        macdhist_df = self._compute_talib_feature(
            "macdhist", 0,
            lambda o, h, l, c, v: talib.MACD(c, fastperiod=12, slowperiod=26, signalperiod=9)[2]
        )
        self.add_feature("%-macdhist", result=macdhist_df)

        # dist_to_macdsignal
        macd_signal_dist_df = self._compute_distance_two_features(macd_df, macdsignal_df)
        self.add_feature("%-dist_to_macdsignal", result=macd_signal_dist_df)

        # dist_to_zerohist
        zero_hist_dist_df = macdhist_df.with_columns(
            pl.col("data").abs().alias("data")
        )
        self.add_feature("%-dist_to_zerohist", result=zero_hist_dist_df)

        # VWAP bands
        vwap_width_df, vwap_upper_dist_df, vwap_middle_dist_df, vwap_lower_dist_df = self._compute_vwap_features()
        self.add_feature("%-vwap_width", result=vwap_width_df)
        self.add_feature("%-dist_to_vwap_upperband", result=vwap_upper_dist_df)
        self.add_feature("%-dist_to_vwap_middleband", result=vwap_middle_dist_df)
        self.add_feature("%-dist_to_vwap_lowerband", result=vwap_lower_dist_df)

        # tail, wick
        tail_df = self.df.select([
            "datetime",
            "vt_symbol",
            (pl.col("close") - pl.col("low")).abs().alias("data")
        ])
        self.add_feature("%-tail", result=tail_df)

        wick_df = self.df.select([
            "datetime",
            "vt_symbol",
            (pl.col("high") - pl.col("close")).abs().alias("data")
        ])
        self.add_feature("%-wick", result=wick_df)

        # Pivot points distances (simplified - using recent high/low)
        pivot_dfs = self._compute_pivot_features()
        for name, df in pivot_dfs.items():
            self.add_feature(f"%-{name}", result=df)

        # Raw price features
        self.add_feature("%-raw_price", result=self.df.select(["datetime", "vt_symbol", pl.col("close").alias("data")]))
        self.add_feature("%-raw_open", result=self.df.select(["datetime", "vt_symbol", pl.col("open").alias("data")]))
        self.add_feature("%-raw_low", result=self.df.select(["datetime", "vt_symbol", pl.col("low").alias("data")]))
        self.add_feature("%-raw_high", result=self.df.select(["datetime", "vt_symbol", pl.col("high").alias("data")]))

    def _add_standard_features(self) -> None:
        """Add time features (standard)"""
        # day_of_week
        dow_df = self.df.select([
            "datetime",
            "vt_symbol",
            ((pl.col("datetime").dt.weekday() + 1) / 7).alias("data")
        ])
        self.add_feature("%-day_of_week", result=dow_df)

        # hour_of_day
        hod_df = self.df.select([
            "datetime",
            "vt_symbol",
            ((pl.col("datetime").dt.hour() + 1) / 25).alias("data")
        ])
        self.add_feature("%-hour_of_day", result=hod_df)

    def _compute_talib_feature(
        self,
        name: str,
        period: int,
        func
    ) -> pl.DataFrame:
        """Compute feature using talib function"""
        # Convert to pandas for talib
        pdf = self.df.to_pandas()

        # Sort by symbol and datetime for proper grouping
        pdf = pdf.sort_values(["vt_symbol", "datetime"])

        # Compute per symbol
        results = []
        for symbol in pdf["vt_symbol"].unique():
            symbol_df = pdf[pdf["vt_symbol"] == symbol]

            o = symbol_df["open"].values
            h = symbol_df["high"].values
            l = symbol_df["low"].values
            c = symbol_df["close"].values
            v = symbol_df["volume"].values

            try:
                data = func(o, h, l, c, v)
            except Exception:
                data = np.zeros(len(c))

            results.append(pl.DataFrame({
                "datetime": symbol_df["datetime"].values,
                "vt_symbol": symbol,
                "data": data
            }))

        return pl.concat(results)

    def _compute_feature(self, func) -> pl.DataFrame:
        """Compute basic feature"""
        pdf = self.df.to_pandas()
        pdf = pdf.sort_values(["vt_symbol", "datetime"])

        results = []
        for symbol in pdf["vt_symbol"].unique():
            symbol_df = pdf[pdf["vt_symbol"] == symbol]

            o = symbol_df["open"].values
            h = symbol_df["high"].values
            l = symbol_df["low"].values
            c = symbol_df["close"].values
            v = symbol_df["volume"].values

            data = func(o, h, l, c, v)

            results.append(pl.DataFrame({
                "datetime": symbol_df["datetime"].values,
                "vt_symbol": symbol,
                "data": data
            }))

        return pl.concat(results)

    def _compute_er(self, period: int) -> pl.DataFrame:
        """Compute Efficiency Ratio (Kaufman's ER)"""
        df = self.df.sort(["vt_symbol", "datetime"])

        # Change = abs(close - close[period])
        change_df = df.with_columns(
            (pl.col("close") - pl.col("close").shift(period).over("vt_symbol")).abs().alias("change")
        )

        # Volatility = sum(abs(close - close[1]), period)
        volatility_df = df.with_columns(
            (pl.col("close") - pl.col("close").shift(1).over("vt_symbol")).abs().alias("delta")
        )
        volatility_df = volatility_df.with_columns(
            pl.col("delta").rolling_sum(period).over("vt_symbol").alias("volatility")
        )

        # ER = change / volatility
        er_df = change_df.join(volatility_df.select(["datetime", "vt_symbol", "volatility"]), on=["datetime", "vt_symbol"])
        er_df = er_df.with_columns(
            (pl.col("change") / (pl.col("volatility") + 1e-12)).alias("data")
        )

        return er_df.select(["datetime", "vt_symbol", "data"])

    def _compute_cmf(self, period: int) -> pl.DataFrame:
        """Compute Chaikin Money Flow"""
        df = self.df.sort(["vt_symbol", "datetime"])

        # MFV = ((close - low) - (high - close)) / (high - low) * volume
        mfv_df = df.with_columns(
            (((pl.col("close") - pl.col("low")) - (pl.col("high") - pl.col("close")))
             / (pl.col("high") - pl.col("low") + 1e-12) * pl.col("volume")).alias("mfv")
        )

        # CMF = sum(MFV, period) / sum(volume, period)
        cmf_df = mfv_df.with_columns([
            pl.col("mfv").rolling_sum(period).over("vt_symbol").alias("mfv_sum"),
            pl.col("volume").rolling_sum(period).over("vt_symbol").alias("vol_sum")
        ])
        cmf_df = cmf_df.with_columns(
            (pl.col("mfv_sum") / (pl.col("vol_sum") + 1e-12)).alias("data")
        )

        return cmf_df.select(["datetime", "vt_symbol", "data"])

    def _compute_tcp(self, period: int) -> pl.DataFrame:
        """Compute Top Percent Change"""
        df = self.df.sort(["vt_symbol", "datetime"])

        if period == 0:
            tcp_df = df.with_columns(
                ((pl.col("open") - pl.col("close")) / pl.col("close")).alias("data")
            )
        else:
            tcp_df = df.with_columns(
                pl.col("open").rolling_max(period).over("vt_symbol").alias("open_max")
            )
            tcp_df = tcp_df.with_columns(
                ((pl.col("open_max") - pl.col("close")) / pl.col("close")).alias("data")
            )

        return tcp_df.select(["datetime", "vt_symbol", "data"])

    def _compute_cti(self, period: int) -> pl.DataFrame:
        """Compute Correlation Trend Indicator"""
        # CTI = correlation between close and linear sequence
        df = self.df.sort(["vt_symbol", "datetime"])

        cti_df = df.with_columns(
            pl.col("close").rolling_map(
                lambda s: np.corrcoef(s, np.arange(len(s)))[0, 1] if len(s) > 1 else 0,
                period
            ).over("vt_symbol").alias("data")
        )

        return cti_df.select(["datetime", "vt_symbol", "data"])

    def _compute_chop(self, period: int) -> pl.DataFrame:
        """Compute Choppiness Index"""
        df = self.df.sort(["vt_symbol", "datetime"])

        # CHOP = 100 * log10(sum(ATR, period) / (max(high, period) - min(low, period))) / log10(period)
        atr_df = df.with_columns(
            (pl.col("high") - pl.col("low")).alias("atr_raw")
        )

        chop_df = atr_df.with_columns([
            pl.col("atr_raw").rolling_sum(period).over("vt_symbol").alias("atr_sum"),
            pl.col("high").rolling_max(period).over("vt_symbol").alias("high_max"),
            pl.col("low").rolling_min(period).over("vt_symbol").alias("low_min")
        ])

        chop_df = chop_df.with_columns(
            (100 * np.log10(pl.col("atr_sum") / (pl.col("high_max") - pl.col("low_min") + 1e-12))
             / np.log10(period)).alias("data")
        )

        return chop_df.select(["datetime", "vt_symbol", "data"])

    def _compute_bb_width(self) -> pl.DataFrame:
        """Compute Bollinger Band width"""
        df = self.df.sort(["vt_symbol", "datetime"])

        # Typical price
        tp_df = df.with_columns(
            ((pl.col("high") + pl.col("low") + pl.col("close")) / 3).alias("tp")
        )

        # BB with window=14, std=2.2
        bb_df = tp_df.with_columns([
            pl.col("tp").rolling_mean(14).over("vt_symbol").alias("bb_mid"),
            pl.col("tp").rolling_std(14).over("vt_symbol").alias("bb_std")
        ])

        bb_df = bb_df.with_columns([
            (pl.col("bb_mid") + 2.2 * pl.col("bb_std")).alias("bb_upper"),
            (pl.col("bb_mid") - 2.2 * pl.col("bb_std")).alias("bb_lower")
        ])

        bb_df = bb_df.with_columns(
            ((pl.col("bb_upper") - pl.col("bb_lower")) / (pl.col("bb_mid") + 1e-12)).alias("data")
        )

        return bb_df.select(["datetime", "vt_symbol", "data"])

    def _compute_distance(self, feature_df: pl.DataFrame) -> pl.DataFrame:
        """Compute distance from close to feature"""
        merged_df = self.df.join(feature_df, on=["datetime", "vt_symbol"])

        dist_df = merged_df.with_columns(
            (pl.col("close") - pl.col("data")).abs().alias("data")
        )

        return dist_df.select(["datetime", "vt_symbol", "data"])

    def _compute_distance_two_features(self, df1: pl.DataFrame, df2: pl.DataFrame) -> pl.DataFrame:
        """Compute distance between two features"""
        merged_df = df1.join(df2.rename({"data": "data2"}), on=["datetime", "vt_symbol"])

        dist_df = merged_df.with_columns(
            (pl.col("data") - pl.col("data2")).abs().alias("data")
        )

        return dist_df.select(["datetime", "vt_symbol", "data"])

    def _compute_vwap_features(self) -> tuple[pl.DataFrame, ...]:
        """Compute VWAP band features"""
        df = self.df.sort(["vt_symbol", "datetime"])

        window = 20
        num_std = 1

        # VWAP = sum(close * volume, window) / sum(volume, window)
        vwap_df = df.with_columns([
            (pl.col("close") * pl.col("volume")).alias("cv")
        ])
        vwap_df = vwap_df.with_columns([
            pl.col("cv").rolling_sum(window).over("vt_symbol").alias("cv_sum"),
            pl.col("volume").rolling_sum(window).over("vt_symbol").alias("vol_sum")
        ])
        vwap_df = vwap_df.with_columns(
            (pl.col("cv_sum") / (pl.col("vol_sum") + 1e-12)).alias("vwap")
        )

        # VWAP std
        vwap_df = vwap_df.with_columns(
            pl.col("vwap").rolling_std(window).over("vt_symbol").alias("vwap_std")
        )

        # Bands
        vwap_df = vwap_df.with_columns([
            (pl.col("vwap") + num_std * pl.col("vwap_std")).alias("vwap_upper"),
            (pl.col("vwap") - num_std * pl.col("vwap_std")).alias("vwap_lower")
        ])

        # Width
        width_df = vwap_df.with_columns(
            ((pl.col("vwap_upper") - pl.col("vwap_lower")) / (pl.col("vwap") + 1e-12) * 100).alias("data")
        )
        width_df = width_df.select(["datetime", "vt_symbol", "data"])

        # Distances
        merged_df = self.df.join(vwap_df, on=["datetime", "vt_symbol"])

        upper_dist_df = merged_df.with_columns(
            (pl.col("close") - pl.col("vwap_upper")).abs().alias("data")
        ).select(["datetime", "vt_symbol", "data"])

        middle_dist_df = merged_df.with_columns(
            (pl.col("close") - pl.col("vwap")).abs().alias("data")
        ).select(["datetime", "vt_symbol", "data"])

        lower_dist_df = merged_df.with_columns(
            (pl.col("close") - pl.col("vwap_lower")).abs().alias("data")
        ).select(["datetime", "vt_symbol", "data"])

        return width_df, upper_dist_df, middle_dist_df, lower_dist_df

    def _compute_pivot_features(self) -> dict[str, pl.DataFrame]:
        """Compute simplified pivot point features"""
        df = self.df.sort(["vt_symbol", "datetime"])

        # Use rolling high/low as simplified pivot points
        period = 20

        pivot_df = df.with_columns([
            pl.col("high").rolling_max(period).over("vt_symbol").alias("r1"),
            pl.col("low").rolling_min(period).over("vt_symbol").alias("s1"),
        ])

        merged_df = self.df.join(pivot_df, on=["datetime", "vt_symbol"])

        features = {}

        # dist_to_r1
        features["dist_to_r1"] = merged_df.with_columns(
            (pl.col("close") - pl.col("r1")).abs().alias("data")
        ).select(["datetime", "vt_symbol", "data"])

        # dist_to_s1
        features["dist_to_s1"] = merged_df.with_columns(
            (pl.col("close") - pl.col("s1")).abs().alias("data")
        ).select(["datetime", "vt_symbol", "data"])

        return features