"""
缠论 (Chan Theory) 策略

基于 Freqtrade FNGBandSniperAIDivergenceV6 策略的缠论部分复刻

核心组件:
1. 分型 (Fractal) - 顶分型和底分型检测
2. 笔 (Stroke) - 连接相邻分型
3. 线段 (Segment) - 由至少 3 笔构成
4. 中枢 (Zhongshu) - 三段重叠区间
5. 三类买卖点 - Type1/2/3 买卖信号
6. 缠论中枢 - 基于三段重叠计算
7. 筹码中枢 (POC) - 成交量加权价格中心
8. VWAP 中枢 - 成交量加权平均价格

买卖点说明:
- 一类买点：底背驰（价格新低）后的反转点
- 二类买点：一类买点后第一次回调不创新低
- 三类买点：中枢突破后回踩不进中枢
- 一类卖点：顶背驰（价格新高）后的反转点
- 二类卖点：一类卖点后第一次反弹不创新高
- 三类卖点：中枢跌破后回抽不进中枢

成交量相关:
- use_volume_filter: 成交量过滤，成交量为 0 时不交易
- POC 中枢：成交量最大价格水平，用于确认支撑/压力
- VWAP 中枢：成交量加权平均成本，用于确认趋势强度
"""

from __future__ import annotations

from typing import Dict, List, Optional
from dataclasses import dataclass
from enum import Enum

import numpy as np

from vnpy.trader.constant import Direction, Interval
from vnpy.trader.object import BarData, TickData
from vnpy.trader.utility import ArrayManager

from vnpy_portfoliostrategy import StrategyTemplate
from vnpy_portfoliostrategy.utility import PortfolioBarGenerator


# ===================== 缠论数据结构 =====================

class FractalType(Enum):
    """分型类型"""
    TOP = 1       # 顶分型
    BOTTOM = -1   # 底分型


@dataclass
class Fractal:
    """分型"""
    index: int
    price: float
    fractal_type: FractalType
    confirmed: bool = True


@dataclass
class Stroke:
    """笔"""
    start_fractal: Fractal
    end_fractal: Fractal
    direction: int  # 1=向上，-1=向下
    high: float
    low: float

    @property
    def amplitude(self) -> float:
        return abs(self.high - self.low)


@dataclass
class Segment:
    """线段"""
    strokes: List[Stroke]
    direction: int
    high: float
    low: float


@dataclass
class Zhongshu:
    """中枢"""
    start_index: int
    end_index: int
    high: float  # ZG - 中枢上沿
    low: float   # ZD - 中枢下沿

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2

    @property
    def range(self) -> float:
        return self.high - self.low


class BuySellPointType(Enum):
    """买卖点类型"""
    BUY_1 = 1      # 一类买点 - 趋势背驰反转
    BUY_2 = 2      # 二类买点 - 回调不创新低
    BUY_3 = 3      # 三类买点 - 突破回踩不进中枢
    SELL_1 = -1    # 一类卖点
    SELL_2 = -2    # 二类卖点
    SELL_3 = -3    # 三类卖点


@dataclass
class BuySellPoint:
    """买卖点"""
    index: int
    price: float
    bs_type: BuySellPointType
    strength: float = 1.0  # 强度得分 0-1


# ===================== 缠论处理器 =====================

class ChanProcessor:
    """
    缠论核心算法处理器
    """

    def __init__(
        self,
        pivot_window: int = 5,
        min_stroke_kbars: int = 4,
        min_segment_strokes: int = 3,
    ):
        self.pivot_window = pivot_window
        self.min_stroke_kbars = min_stroke_kbars
        self.min_segment_strokes = min_segment_strokes

        self.fractals: List[Fractal] = []
        self.strokes: List[Stroke] = []
        self.segments: List[Segment] = []
        self.zhongshus: List[Zhongshu] = []
        self.buy_sell_points: List[BuySellPoint] = []

    def process(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ) -> Dict:
        """处理 K 线数据，返回缠论结构"""
        n = len(closes)
        if n < self.pivot_window * 3 + 10:
            return self._empty_result()

        # 1. 分型检测
        self.fractals = self._detect_fractals(highs, lows)

        # 2. 笔构建
        self.strokes = self._build_strokes(highs, lows)

        # 3. 线段构建
        self.segments = self._build_segments()

        # 4. 中枢计算
        self.zhongshus = self._calculate_zhongshus()

        # 5. 买卖点检测
        self.buy_sell_points = self._detect_buy_sell_points(highs, lows, closes)

        return {
            'fractals': self.fractals,
            'strokes': self.strokes,
            'segments': self.segments,
            'zhongshus': self.zhongshus,
            'buy_sell_points': self.buy_sell_points,
        }

    def _empty_result(self) -> Dict:
        return {
            'fractals': [],
            'strokes': [],
            'segments': [],
            'zhongshus': [],
        }

    def _detect_fractals(
        self,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> List[Fractal]:
        """
        分型检测

        顶分型：中间 K 线的高点是三根 K 线中最高的
        底分型：中间 K 线的低点是三根 K 线中最低的
        """
        fractals = []
        n = len(highs)

        for i in range(1, n - 1):
            # 顶分型检测
            if highs[i] > highs[i-1] and highs[i] > highs[i+1]:
                confirmed = i + self.pivot_window < n
                if confirmed:
                    future_highs = highs[i+1:i+self.pivot_window+1]
                    confirmed = highs[i] > np.max(future_highs)

                fractals.append(Fractal(
                    index=i,
                    price=highs[i],
                    fractal_type=FractalType.TOP,
                    confirmed=confirmed
                ))

            # 底分型检测
            if lows[i] < lows[i-1] and lows[i] < lows[i+1]:
                confirmed = i + self.pivot_window < n
                if confirmed:
                    future_lows = lows[i+1:i+self.pivot_window+1]
                    confirmed = lows[i] < np.min(future_lows)

                fractals.append(Fractal(
                    index=i,
                    price=lows[i],
                    fractal_type=FractalType.BOTTOM,
                    confirmed=confirmed
                ))

        return fractals

    def _build_strokes(
        self,
        highs: np.ndarray,
        lows: np.ndarray
    ) -> List[Stroke]:
        """
        构建笔

        规则:
        1. 顶底分型交替出现
        2. 至少包含 min_stroke_kbars 根 K 线
        """
        if len(self.fractals) < 2:
            return []

        strokes = []

        for i in range(len(self.fractals) - 1):
            f1 = self.fractals[i]
            f2 = self.fractals[i + 1]

            # 检查分型类型是否交替
            if f1.fractal_type == f2.fractal_type:
                continue

            # 检查 K 线距离
            kbar_distance = f2.index - f1.index
            if kbar_distance < self.min_stroke_kbars:
                continue

            # 确定笔方向
            if f1.fractal_type == FractalType.BOTTOM and f2.fractal_type == FractalType.TOP:
                direction = 1  # 向上笔
            elif f1.fractal_type == FractalType.TOP and f2.fractal_type == FractalType.BOTTOM:
                direction = -1  # 向下笔
            else:
                continue

            # 计算笔的最高和最低点
            start_idx = min(f1.index, f2.index)
            end_idx = max(f1.index, f2.index)

            if start_idx >= len(highs) or end_idx >= len(highs):
                continue

            stroke_high = np.max(highs[start_idx:end_idx + 1])
            stroke_low = np.min(lows[start_idx:end_idx + 1])

            strokes.append(Stroke(
                start_fractal=f1,
                end_fractal=f2,
                direction=direction,
                high=stroke_high,
                low=stroke_low
            ))

        return strokes

    def _build_segments(self) -> List[Segment]:
        """
        构建线段

        规则：线段至少由 3 笔组成
        """
        if len(self.strokes) < self.min_segment_strokes:
            return []

        segments = []
        current_strokes = [self.strokes[0]]

        for i in range(1, len(self.strokes)):
            stroke = self.strokes[i]
            prev_stroke = self.strokes[i - 1]

            # 检查笔的方向是否交替
            if stroke.direction == prev_stroke.direction:
                # 同向笔，更新最后一笔
                current_strokes[-1] = stroke
                continue

            current_strokes.append(stroke)

            # 检查是否满足线段条件
            if len(current_strokes) >= self.min_segment_strokes:
                seg_high = max(s.high for s in current_strokes)
                seg_low = min(s.low for s in current_strokes)
                seg_direction = current_strokes[0].direction

                segments.append(Segment(
                    strokes=current_strokes.copy(),
                    direction=seg_direction,
                    high=seg_high,
                    low=seg_low
                ))

                current_strokes = [stroke]

        return segments

    def _calculate_zhongshus(self) -> List[Zhongshu]:
        """
        计算中枢

        中枢定义：至少 3 个连续线段的重叠区域
        ZG = min(高点)
        ZD = max(低点)
        """
        if len(self.segments) < 3:
            return []

        zhongshus = []

        for i in range(len(self.segments) - 2):
            segs = [self.segments[i], self.segments[i + 1], self.segments[i + 2]]

            zg = min(s.high for s in segs)
            zd = max(s.low for s in segs)

            if zg > zd:
                start_index = segs[0].strokes[0].start_fractal.index
                end_index = segs[-1].strokes[-1].end_fractal.index

                zhongshus.append(Zhongshu(
                    start_index=start_index,
                    end_index=end_index,
                    high=zg,
                    low=zd
                ))

        return zhongshus

    def get_latest_zhongshu(self) -> Optional[Zhongshu]:
        """获取最新的中枢"""
        if self.zhongshus:
            return self.zhongshus[-1]
        return None

    def get_stroke_direction(self) -> int:
        """获取当前笔的方向"""
        if self.strokes:
            return self.strokes[-1].direction
        return 0

    def get_segment_direction(self) -> int:
        """获取当前线段的方向"""
        if self.segments:
            return self.segments[-1].direction
        return 0

    def _detect_buy_sell_points(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ) -> List[BuySellPoint]:
        """
        检测三类买卖点

        一类买点 (B1): 趋势背驰后的反转点（价格新低但力度减弱）
        二类买点 (B2): 一类买点后第一次回调不创新低
        三类买点 (B3): 中枢突破后回踩不进中枢

        一类卖点 (S1): 趋势背驰后的反转点
        二类卖点 (S2): 一类卖点后第一次反弹不创新高
        三类卖点 (S3): 中枢跌破后回抽不进中枢
        """
        if not self.zhongshus or len(self.strokes) < 3:
            return []

        buy_sell_points = []

        for i in range(2, len(self.strokes)):
            stroke = self.strokes[i]
            prev_stroke = self.strokes[i - 1]
            prev_prev_stroke = self.strokes[i - 2]

            # 查找最近的中枢
            current_zhongshu = self._find_nearest_zhongshu(stroke.end_fractal.index)

            if stroke.direction == 1:  # 向上笔
                # 一类买点：底背驰（价格新低）
                if stroke.end_fractal.fractal_type == FractalType.BOTTOM:
                    if prev_prev_stroke.end_fractal.fractal_type == FractalType.BOTTOM:
                        if stroke.end_fractal.price < prev_prev_stroke.end_fractal.price:
                            # 计算背驰强度
                            strength = self._calculate_divergence_strength(
                                prev_prev_stroke.end_fractal,
                                stroke.end_fractal,
                                highs, lows, closes
                            )
                            buy_sell_points.append(BuySellPoint(
                                index=stroke.end_fractal.index,
                                price=stroke.end_fractal.price,
                                bs_type=BuySellPointType.BUY_1,
                                strength=strength
                            ))

                # 二类买点：回调不创新低
                if stroke.end_fractal.fractal_type == FractalType.TOP:
                    if prev_stroke.end_fractal.fractal_type == FractalType.BOTTOM:
                        # 检查之前是否有一类买点
                        has_b1 = any(
                            bsp.bs_type == BuySellPointType.BUY_1
                            for bsp in buy_sell_points
                            if bsp.index < stroke.end_fractal.index
                        )
                        if has_b1 and stroke.end_fractal.price > prev_stroke.end_fractal.price:
                            buy_sell_points.append(BuySellPoint(
                                index=stroke.end_fractal.index,
                                price=stroke.end_fractal.price,
                                bs_type=BuySellPointType.BUY_2,
                                strength=0.8
                            ))

                # 三类买点：回踩不进中枢
                if current_zhongshu and stroke.end_fractal.fractal_type == FractalType.TOP:
                    if prev_stroke.end_fractal.fractal_type == FractalType.BOTTOM:
                        if prev_stroke.end_fractal.price > current_zhongshu.high:
                            buy_sell_points.append(BuySellPoint(
                                index=stroke.end_fractal.index,
                                price=stroke.end_fractal.price,
                                bs_type=BuySellPointType.BUY_3,
                                strength=0.9
                            ))

            else:  # stroke.direction == -1, 向下笔
                # 一类卖点：顶背驰（价格新高）
                if stroke.end_fractal.fractal_type == FractalType.TOP:
                    if prev_prev_stroke.end_fractal.fractal_type == FractalType.TOP:
                        if stroke.end_fractal.price > prev_prev_stroke.end_fractal.price:
                            strength = self._calculate_divergence_strength(
                                prev_prev_stroke.end_fractal,
                                stroke.end_fractal,
                                highs, lows, closes
                            )
                            buy_sell_points.append(BuySellPoint(
                                index=stroke.end_fractal.index,
                                price=stroke.end_fractal.price,
                                bs_type=BuySellPointType.SELL_1,
                                strength=strength
                            ))

                # 二类卖点：反弹不创新高
                if stroke.end_fractal.fractal_type == FractalType.BOTTOM:
                    if prev_stroke.end_fractal.fractal_type == FractalType.TOP:
                        has_s1 = any(
                            bsp.bs_type == BuySellPointType.SELL_1
                            for bsp in buy_sell_points
                            if bsp.index < stroke.end_fractal.index
                        )
                        if has_s1 and stroke.end_fractal.price < prev_stroke.end_fractal.price:
                            buy_sell_points.append(BuySellPoint(
                                index=stroke.end_fractal.index,
                                price=stroke.end_fractal.price,
                                bs_type=BuySellPointType.SELL_2,
                                strength=0.8
                            ))

                # 三类卖点：回抽不进中枢
                if current_zhongshu and stroke.end_fractal.fractal_type == FractalType.BOTTOM:
                    if prev_stroke.end_fractal.fractal_type == FractalType.TOP:
                        if prev_stroke.end_fractal.price < current_zhongshu.low:
                            buy_sell_points.append(BuySellPoint(
                                index=stroke.end_fractal.index,
                                price=stroke.end_fractal.price,
                                bs_type=BuySellPointType.SELL_3,
                                strength=0.9
                            ))

        return buy_sell_points

    def _find_nearest_zhongshu(self, index: int) -> Optional[Zhongshu]:
        """查找最近的中枢"""
        for zs in reversed(self.zhongshus):
            if zs.start_index <= index <= zs.end_index + 10:
                return zs
        return None

    def _calculate_divergence_strength(
        self,
        f1: Fractal,
        f2: Fractal,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray
    ) -> float:
        """
        计算背驰强度

        返回 0-1 之间的值，越大表示背驰越强
        考虑价格变化和成交量因素
        """
        if f1.index >= len(closes) or f2.index >= len(closes):
            return 0.5

        price_change = abs(f2.price - f1.price) / f1.price if f1.price != 0 else 0

        # 价格变化越小，背驰强度越大
        strength = 1.0 / (1.0 + price_change * 100)

        # 如果高点/低点之间的幅度也在减小，增强背驰信号
        if f1.fractal_type == FractalType.BOTTOM and f2.fractal_type == FractalType.BOTTOM:
            # 底背驰：价格新低但幅度减小
            if f2.index < len(highs) and f1.index < len(highs):
                f1_high = highs[f1.index]
                f2_high = highs[f2.index] if f2.index < len(highs) else f1_high
                if f2_high < f1_high:
                    strength *= 1.2  # 增强信号

        return min(max(strength, 0.0), 1.0)

    def get_buy_sell_points(self) -> List[BuySellPoint]:
        """获取买卖点列表"""
        return self.buy_sell_points

    def get_latest_buy_sell_point(self) -> Optional[BuySellPoint]:
        """获取最新的买卖点"""
        if self.buy_sell_points:
            return self.buy_sell_points[-1]
        return None


# ===================== 中枢计算器 =====================

class ChanHubCalculator:
    """
    中枢计算器 (Freqtrade 版本复刻)

    包含三种中枢计算方法:
    1. 缠论中枢 - 基于三段重叠
    2. 筹码中枢 (POC) - 基于成交量加权价格中心
    3. VWAP 中枢 - 基于成交量加权平均价格
    """

    def __init__(self, atr_period: int = 14):
        self.atr_period = atr_period

    def calculate_chan_hub(
        self,
        highs: np.ndarray,
        lows: np.ndarray,
        closes: np.ndarray,
        atr: np.ndarray,
        swing_window: int = 5
    ) -> np.ndarray:
        """
        计算缠论中枢距离

        基于三段重叠原理计算中枢位置，返回价格与中枢的距离 (tanh 标准化)
        """
        n = len(closes)
        result = np.full(n, np.nan)

        for i in range(swing_window * 3, n):
            p_lows = []
            p_highs = []

            for j in range(3):
                start = i - (j + 1) * swing_window
                end = i - j * swing_window
                if start >= 0:
                    p_lows.append(np.min(lows[start:end]))
                    p_highs.append(np.max(highs[start:end]))

            if len(p_lows) == 3:
                hub_max_low = max(p_lows)
                hub_min_high = min(p_highs)

                if hub_max_low < hub_min_high:
                    chan_hub_mid = (hub_max_low + hub_min_high) / 2
                    atr_safe = max(atr[i], 1e-6) if i < len(atr) else 1e-6
                    result[i] = np.tanh((closes[i] - chan_hub_mid) / (atr_safe * 3.0))

        return result

    def calculate_poc_hub(
        self,
        closes: np.ndarray,
        volumes: np.ndarray,
        atr: np.ndarray,
        window: int = 50
    ) -> np.ndarray:
        """
        计算筹码中枢 (POC - Point of Control)

        POC 是成交量分布理论中的关键价格，代表该时间段内成交量最大的价格水平
        """
        n = len(closes)
        result = np.full(n, np.nan)

        for i in range(window, n):
            window_volumes = volumes[i-window:i]
            window_closes = closes[i-window:i]

            max_vol_idx = np.argmax(window_volumes)
            poc_price = window_closes[max_vol_idx]

            atr_safe = max(atr[i], 1e-6) if i < len(atr) else 1e-6
            result[i] = np.tanh((closes[i] - poc_price) / (atr_safe * 3.0))

        return result

    def calculate_vwap_hub(
        self,
        closes: np.ndarray,
        volumes: np.ndarray,
        atr: np.ndarray,
        window: int = 50
    ) -> np.ndarray:
        """
        计算 VWAP 中枢

        VWAP 是成交量加权平均价格，代表市场平均持仓成本
        """
        n = len(closes)
        result = np.full(n, np.nan)

        pv = closes * volumes

        for i in range(window, n):
            window_pv = pv[i-window:i]
            window_vol = volumes[i-window:i]

            vwap = np.sum(window_pv) / max(np.sum(window_vol), 1e-6)

            atr_safe = max(atr[i], 1e-6) if i < len(atr) else 1e-6
            result[i] = np.tanh((closes[i] - vwap) / (atr_safe * 3.0))

        return result


# ===================== 缠论策略 =====================

class PortfolioChanStrategy(StrategyTemplate):
    """
    缠论策略

    基于 Freqtrade FNGBandSniperAIDivergenceV6 的缠论部分
    """

    author = "chan theory port"

    # 阈值常量
    CHAN_HUB_THRESHOLD = 0.3      # 缠论中枢距离阈值
    POC_HUB_THRESHOLD = 0.3       # POC 中枢确认阈值
    VWAP_HUB_THRESHOLD = 0.2      # VWAP 中枢确认阈值

    # 参数
    history_days: int = 60
    price_add: float = 0.0

    # 缠论参数
    pivot_window: int = 5
    swing_window: int = 5
    atr_period: int = 14
    poc_window: int = 50   # 筹码中枢窗口
    vwap_window: int = 50  # VWAP 中枢窗口

    # 交易参数
    fixed_size: int = 1
    use_chan_filter: bool = True
    use_zhongshu_filter: bool = True
    allow_short: bool = False  # 是否允许做空
    use_volume_filter: bool = True  # 是否使用成交量过滤

    parameters = [
        "history_days",
        "price_add",
        "pivot_window",
        "swing_window",
        "atr_period",
        "poc_window",
        "vwap_window",
        "fixed_size",
        "use_chan_filter",
        "use_zhongshu_filter",
        "allow_short",
        "use_volume_filter",
    ]

    # 变量
    chan_status: str = ""
    zhongshu_status: str = ""
    buy_sell_point: str = ""  # 最新买卖点类型和强度
    hub_status: str = ""  # 中枢分布状态 (POC/VWAP)

    variables = [
        "chan_status",
        "zhongshu_status",
        "buy_sell_point",
        "hub_status",
    ]

    def __init__(
        self,
        strategy_engine,
        strategy_name: str,
        vt_symbols: list[str],
        setting: dict,
    ) -> None:
        super().__init__(strategy_engine, strategy_name, vt_symbols, setting)

        warmup = max(self.pivot_window * 10, self.poc_window, self.vwap_window) + 20
        self.ams: Dict[str, ArrayManager] = {s: ArrayManager(size=warmup) for s in self.vt_symbols}

        # 缠论处理器
        self.chan_processors: Dict[str, ChanProcessor] = {}
        self.hub_calculators: Dict[str, ChanHubCalculator] = {}

        for vt_symbol in self.vt_symbols:
            self.chan_processors[vt_symbol] = ChanProcessor(
                pivot_window=self.pivot_window,
                min_stroke_kbars=4,
                min_segment_strokes=3,
            )
            self.hub_calculators[vt_symbol] = ChanHubCalculator(
                atr_period=self.atr_period
            )

        self.pbg = PortfolioBarGenerator(self.on_bars)

    def on_init(self) -> None:
        self.write_log("策略初始化")
        self.load_bars(self.history_days, Interval.MINUTE)
        self.inited = True

    def on_start(self) -> None:
        self.write_log("策略启动")

    def on_stop(self) -> None:
        self.write_log("策略停止")

    def on_tick(self, tick: TickData) -> None:
        self.pbg.update_tick(tick)

    def on_bars(self, bars: Dict[str, BarData]) -> None:
        for vt_symbol, bar in bars.items():
            self.ams[vt_symbol].update_bar(bar)

        for vt_symbol in bars.keys():
            if not self.ams[vt_symbol].inited:
                return

        # 处理每个品种的缠论结构
        for vt_symbol in bars.keys():
            am = self.ams[vt_symbol]
            chan_processor = self.chan_processors[vt_symbol]
            hub_calc = self.hub_calculators[vt_symbol]

            # 获取数据
            highs = am.high_array
            lows = am.low_array
            closes = am.close_array
            volumes = am.volume_array
            atr = am.atr(self.atr_period, array=True)

            # 处理缠论结构
            chan_result = chan_processor.process(highs, lows, closes)

            # 计算中枢特征
            chan_hub_dist = hub_calc.calculate_chan_hub(
                highs, lows, closes, atr, self.swing_window
            )
            poc_hub_dist = hub_calc.calculate_poc_hub(
                closes, volumes, atr, self.poc_window
            )
            vwap_hub_dist = hub_calc.calculate_vwap_hub(
                closes, volumes, atr, self.vwap_window
            )

            # 获取最新状态
            latest_zhongshu = chan_processor.get_latest_zhongshu()
            stroke_dir = chan_processor.get_stroke_direction()
            segment_dir = chan_processor.get_segment_direction()

            # 更新状态显示
            if latest_zhongshu:
                self.zhongshu_status = f"ZG:{latest_zhongshu.high:.2f} ZD:{latest_zhongshu.low:.2f}"
            else:
                self.zhongshu_status = "无中枢"

            self.chan_status = f"笔:{'↑' if stroke_dir > 0 else '↓' if stroke_dir < 0 else '-'} 线段:{'↑' if segment_dir > 0 else '↓' if segment_dir < 0 else '-'}"

            # 显示最新买卖点
            latest_bsp = chan_processor.get_latest_buy_sell_point()
            if latest_bsp:
                bsp_name = latest_bsp.bs_type.name.replace('BUY_', '买').replace('SELL_', '卖')
                self.buy_sell_point = f"{bsp_name} 强度:{latest_bsp.strength:.2f}"
            else:
                self.buy_sell_point = "-"

            # 显示中枢分布状态
            poc_val = poc_hub_dist[-1] if not np.isnan(poc_hub_dist[-1]) else 0
            vwap_val = vwap_hub_dist[-1] if not np.isnan(vwap_hub_dist[-1]) else 0
            poc_side = "+" if poc_val > 0 else "-" if poc_val < 0 else "0"
            vwap_side = "+" if vwap_val > 0 else "-" if vwap_val < 0 else "0"
            self.hub_status = f"POC:{poc_side} VWAP:{vwap_side}"

            # 计算目标仓位
            target = self._calculate_target(
                vt_symbol,
                latest_zhongshu,
                stroke_dir,
                segment_dir,
                closes[-1],
                chan_hub_dist[-1] if not np.isnan(chan_hub_dist[-1]) else 0,
                poc_hub_dist[-1] if not np.isnan(poc_hub_dist[-1]) else 0,
                vwap_hub_dist[-1] if not np.isnan(vwap_hub_dist[-1]) else 0,
                volumes[-1] if len(volumes) > 0 else 0,
            )

            self.set_target(vt_symbol, target)

        # 执行调仓
        self.rebalance_portfolio(bars)
        self.put_event()

    def _calculate_target(
        self,
        vt_symbol: str,
        zhongshu: Optional[Zhongshu],
        stroke_dir: int,
        segment_dir: int,
        close: float,
        chan_hub_dist: float,
        poc_hub_dist: float,
        vwap_hub_dist: float,
        volume: float,
    ) -> int:
        """
        计算目标仓位

        基于缠论结构的买卖信号，结合成交量和中枢位置确认
        """
        # 成交量过滤 - 成交量为 0 时不交易
        if self.use_volume_filter and volume <= 0:
            return 0

        # 缠论中枢距离过滤 - 价格接近中枢时观望 (优先检查)
        if abs(chan_hub_dist) < self.CHAN_HUB_THRESHOLD:
            return 0

        # 确定当前方向信号
        long_signal = False
        short_signal = False

        # 1. 缠论结构过滤 - 笔和线段方向一致
        if self.use_chan_filter:
            if stroke_dir == segment_dir:
                if stroke_dir > 0:
                    long_signal = True
                elif stroke_dir < 0:
                    short_signal = True

        # 2. 中枢过滤 - 价格突破中枢
        if self.use_zhongshu_filter and zhongshu:
            if close > zhongshu.high:
                long_signal = True
            elif close < zhongshu.low:
                short_signal = True
            elif zhongshu.low <= close <= zhongshu.high:
                # 价格在中枢内部，清空信号
                return 0

        # 3. POC 中枢确认 - 筹码密集区确认
        if poc_hub_dist > self.POC_HUB_THRESHOLD:
            long_signal = True
        elif poc_hub_dist < -self.POC_HUB_THRESHOLD:
            short_signal = True

        # 4. VWAP 中枢确认 - 成本区确认
        if vwap_hub_dist > self.VWAP_HUB_THRESHOLD:
            long_signal = True
        elif vwap_hub_dist < -self.VWAP_HUB_THRESHOLD:
            short_signal = True

        # 输出目标仓位
        if long_signal:
            return self.fixed_size
        elif short_signal and self.allow_short:
            return -self.fixed_size
        else:
            return 0

    def calculate_price(self, vt_symbol: str, direction: Direction, reference: float) -> float:
        if direction == Direction.LONG:
            return reference + self.price_add
        return reference - self.price_add


