"""QuickAdapterV5 feature dataset from freqtrade."""

import polars as pl
import pandas as pd
import numpy as np
import talib.abstract as ta
from scipy.signal import argrelextrema
from technical import qtpylib
import pandas_ta as pta

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
        label_period_candles: int = 10,
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
        label_period_candles : int
            Period for extrema detection (freqtrade compatible)
        """
        super().__init__(
            df=df,
            train_period=train_period,
            valid_period=valid_period,
            test_period=test_period,
        )

        self.periods = periods
        self.label_period_candles = label_period_candles

        # Compute features using pandas (freqtrade style)
        feature_df = self._compute_features_pandas()

        # Compute extrema targets (freqtrade style)
        feature_df = self._set_freqai_targets(feature_df)

        # Add each feature as result DataFrame
        for col in feature_df.columns:
            if col.startswith("%-"):
                feat_df = feature_df.select(["datetime", "vt_symbol", col]).rename({col: "data"})
                self.add_feature(col, result=feat_df)

        # Add extrema label column (&s-extrema is the training target)
        extrema_df = feature_df.select(["datetime", "vt_symbol", "&s-extrema"]).rename({"&s-extrema": "data"})
        self.add_feature("&s-extrema", result=extrema_df)

        # Store extrema columns for later use
        self._extrema_df = feature_df.select(["datetime", "vt_symbol", "minima", "maxima", "&s-extrema"])

    def _compute_features_pandas(self) -> pl.DataFrame:
        """Compute all features using pandas/talib (freqtrade style)"""
        # Convert to pandas
        pdf = self.df.to_pandas()
        pdf = pdf.sort_values(["vt_symbol", "datetime"])

        # Compute per symbol
        results = []
        for symbol in pdf["vt_symbol"].unique():
            symbol_pdf = pdf[pdf["vt_symbol"] == symbol].copy()
            symbol_pdf = self._feature_engineering_expand_all(symbol_pdf)
            symbol_pdf = self._feature_engineering_expand_basic(symbol_pdf)
            symbol_pdf = self._feature_engineering_standard(symbol_pdf)
            results.append(symbol_pdf)

        # Concat and convert back to polars
        full_pdf = pd.concat(results)
        full_pl = pl.from_pandas(full_pdf)

        return full_pl

    def _feature_engineering_expand_all(self, dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Add period-based features (freqtrade style)"""
        for period in self.periods:
            dataframe[f"%-rsi-{period}"] = ta.RSI(dataframe, timeperiod=period)
            dataframe[f"%-mfi-{period}"] = ta.MFI(dataframe, timeperiod=period)
            dataframe[f"%-adx-{period}"] = ta.ADX(dataframe, timeperiod=period)
            dataframe[f"%-cci-{period}"] = ta.CCI(dataframe, timeperiod=period)
            dataframe[f"%-er-{period}"] = pta.er(dataframe['close'], length=period)
            dataframe[f"%-rocr-{period}"] = ta.ROCR(dataframe, timeperiod=period)
            dataframe[f"%-cmf-{period}"] = chaikin_mf(dataframe, periods=period)
            dataframe[f"%-tcp-{period}"] = top_percent_change(dataframe, period)
            dataframe[f"%-cti-{period}"] = pta.cti(dataframe['close'], length=period)
            dataframe[f"%-chop-{period}"] = qtpylib.chopiness(dataframe, period)
            dataframe[f"%-linear-{period}"] = ta.LINEARREG_ANGLE(dataframe, timeperiod=period)
            dataframe[f"%-atr-{period}"] = ta.ATR(dataframe, timeperiod=period)
            dataframe[f"%-atr-{period}p"] = dataframe[f"%-atr-{period}"] / dataframe['close'] * 1000
        return dataframe

    def _feature_engineering_expand_basic(self, dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Add basic features (freqtrade style)"""
        dataframe[f"%-pct-change"] = dataframe["close"].pct_change()
        dataframe[f"%-raw_volume"] = dataframe["volume"]
        dataframe[f"%-obv"] = ta.OBV(dataframe)

        # Bollinger Bands
        bollinger = qtpylib.bollinger_bands(qtpylib.typical_price(dataframe), window=14, stds=2.2)
        dataframe["bb_lowerband"] = bollinger["lower"]
        dataframe["bb_middleband"] = bollinger["mid"]
        dataframe["bb_upperband"] = bollinger["upper"]
        dataframe[f"%-bb_width"] = (dataframe["bb_upperband"] - dataframe["bb_lowerband"]) / dataframe["bb_middleband"]

        # IBS
        dataframe[f"%-ibs"] = (dataframe['close'] - dataframe['low']) / (dataframe['high'] - dataframe['low'])

        # EMA distances
        dataframe['ema_50'] = ta.EMA(dataframe, timeperiod=50)
        dataframe['ema_12'] = ta.EMA(dataframe, timeperiod=12)
        dataframe['ema_26'] = ta.EMA(dataframe, timeperiod=26)
        dataframe[f"%-distema50"] = get_distance(dataframe['close'], dataframe['ema_50'])
        dataframe[f"%-distema12"] = get_distance(dataframe['close'], dataframe['ema_12'])
        dataframe[f"%-distema26"] = get_distance(dataframe['close'], dataframe['ema_26'])

        # MACD
        macd = ta.MACD(dataframe)
        dataframe[f"%-macd"] = macd['macd']
        dataframe[f"%-macdsignal"] = macd['macdsignal']
        dataframe[f"%-macdhist"] = macd['macdhist']
        dataframe[f"%-dist_to_macdsignal"] = get_distance(dataframe[f"%-macd"], dataframe[f"%-macdsignal"])
        dataframe[f"%-dist_to_zerohist"] = get_distance(0, dataframe[f"%-macdhist"])

        # VWAP bands
        vwap_low, vwap, vwap_high = VWAPB(dataframe, 20, 1)
        dataframe['vwap_upperband'] = vwap_high
        dataframe['vwap_middleband'] = vwap
        dataframe['vwap_lowerband'] = vwap_low
        dataframe[f"%-vwap_width"] = ((dataframe['vwap_upperband'] - dataframe['vwap_lowerband']) / dataframe['vwap_middleband']) * 100
        dataframe[f"%-dist_to_vwap_upperband"] = get_distance(dataframe['close'], dataframe['vwap_upperband'])
        dataframe[f"%-dist_to_vwap_middleband"] = get_distance(dataframe['close'], dataframe['vwap_middleband'])
        dataframe[f"%-dist_to_vwap_lowerband"] = get_distance(dataframe['close'], dataframe['vwap_lowerband'])

        # Tail/Wick
        dataframe[f"%-tail"] = (dataframe['close'] - dataframe['low']).abs()
        dataframe[f"%-wick"] = (dataframe['high'] - dataframe['close']).abs()

        # Pivot points (simplified - using rolling high/low/close)
        dataframe['pivot'] = (dataframe['high'].shift(1) + dataframe['low'].shift(1) + dataframe['close'].shift(1)) / 3
        dataframe['r1'] = 2 * dataframe['pivot'] - dataframe['low'].shift(1)
        dataframe['s1'] = 2 * dataframe['pivot'] - dataframe['high'].shift(1)
        dataframe['r2'] = dataframe['pivot'] + (dataframe['high'].shift(1) - dataframe['low'].shift(1))
        dataframe['s2'] = dataframe['pivot'] - (dataframe['high'].shift(1) - dataframe['low'].shift(1))
        dataframe['r3'] = dataframe['high'].shift(1) + 2 * (dataframe['pivot'] - dataframe['low'].shift(1))
        dataframe['s3'] = dataframe['low'].shift(1) - 2 * (dataframe['high'].shift(1) - dataframe['pivot'])
        dataframe[f"%-dist_to_r1"] = get_distance(dataframe['close'], dataframe['r1'])
        dataframe[f"%-dist_to_r2"] = get_distance(dataframe['close'], dataframe['r2'])
        dataframe[f"%-dist_to_r3"] = get_distance(dataframe['close'], dataframe['r3'])
        dataframe[f"%-dist_to_s1"] = get_distance(dataframe['close'], dataframe['s1'])
        dataframe[f"%-dist_to_s2"] = get_distance(dataframe['close'], dataframe['s2'])
        dataframe[f"%-dist_to_s3"] = get_distance(dataframe['close'], dataframe['s3'])

        # Raw price
        dataframe[f"%-raw_price"] = dataframe["close"]
        dataframe[f"%-raw_open"] = dataframe["open"]
        dataframe[f"%-raw_low"] = dataframe["low"]
        dataframe[f"%-raw_high"] = dataframe["high"]

        return dataframe

    def _feature_engineering_standard(self, dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Add time features (freqtrade style)"""
        dataframe[f"%-day_of_week"] = (dataframe["datetime"].dt.weekday + 1) / 7
        dataframe[f"%-hour_of_day"] = (dataframe["datetime"].dt.hour + 1) / 25
        return dataframe

    def _set_freqai_targets(self, dataframe: pd.DataFrame, **kwargs) -> pd.DataFrame:
        """Set extrema targets (freqtrade style)

        Uses argrelextrema to find local minima and maxima.
        Labels are smoothed with gaussian rolling window.

        Parameters
        ----------
        dataframe : pd.DataFrame
            OHLCV data for a single symbol

        Returns
        -------
        pd.DataFrame
            DataFrame with added columns:
            - &s-extrema: extrema labels (-1 for minima, 1 for maxima, smoothed)
            - minima: binary indicator for minima points
            - maxima: binary indicator for maxima points
        """
        # Initialize extrema column
        dataframe["&s-extrema"] = 0

        # Find local minima (using low prices)
        min_peaks = argrelextrema(
            dataframe["low"].values,
            np.less,
            order=self.label_period_candles
        )

        # Find local maxima (using high prices)
        max_peaks = argrelextrema(
            dataframe["high"].values,
            np.greater,
            order=self.label_period_candles
        )

        # Mark minima points
        for mp in min_peaks[0]:
            dataframe.at[mp, "&s-extrema"] = -1

        # Mark maxima points
        for mp in max_peaks[0]:
            dataframe.at[mp, "&s-extrema"] = 1

        # Create binary indicator columns
        dataframe["minima"] = np.where(dataframe["&s-extrema"] == -1, 1, 0)
        dataframe["maxima"] = np.where(dataframe["&s-extrema"] == 1, 1, 0)

        # Smooth extrema labels with gaussian window (freqtrade style)
        dataframe['&s-extrema'] = dataframe['&s-extrema'].rolling(
            window=5, win_type='gaussian', center=True
        ).mean(std=0.5)

        return dataframe


# Helper functions from freqtrade
def top_percent_change(dataframe: pd.DataFrame, length: int) -> pd.Series:
    """Percentage change of the current close from the range maximum Open price"""
    if length == 0:
        return (dataframe['open'] - dataframe['close']) / dataframe['close']
    else:
        return (dataframe['open'].rolling(length).max() - dataframe['close']) / dataframe['close']


def chaikin_mf(df: pd.DataFrame, periods: int = 20) -> pd.Series:
    """Chaikin Money Flow"""
    close = df['close']
    low = df['low']
    high = df['high']
    volume = df['volume']
    mfv = ((close - low) - (high - close)) / (high - low)
    mfv = mfv.fillna(0.0)
    mfv *= volume
    cmf = mfv.rolling(periods).sum() / volume.rolling(periods).sum()
    return cmf


def VWAPB(dataframe: pd.DataFrame, window_size: int = 20, num_of_std: int = 1):
    """VWAP bands"""
    df = dataframe.copy()
    df['vwap'] = qtpylib.rolling_vwap(df, window=window_size)
    rolling_std = df['vwap'].rolling(window=window_size).std()
    df['vwap_low'] = df['vwap'] - (rolling_std * num_of_std)
    df['vwap_high'] = df['vwap'] + (rolling_std * num_of_std)
    return df['vwap_low'], df['vwap'], df['vwap_high']


def get_distance(p1, p2):
    """Get distance between two points"""
    return abs(p1 - p2)