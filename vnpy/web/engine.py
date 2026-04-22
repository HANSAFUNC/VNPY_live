"""VNPY Web 交易看板引擎

提供类似 freqUI 的网页交易界面，支持：
- 实时数据展示（持仓、盈亏、信号、成交）
- 策略控制（启停、参数调整）
- 图表可视化

使用 FastAPI + WebSocket 实现实时通信。
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
from pathlib import Path
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, List, Set, Any, Optional
from vnpy.event import EventEngine, Event
from vnpy.trader.engine import BaseEngine, MainEngine
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import (
    TickData, TradeData, OrderData, PositionData, AccountData
)
from vnpy.trader.event import (
    EVENT_TICK, EVENT_TRADE, EVENT_ORDER, EVENT_POSITION, EVENT_ACCOUNT
)

from .api import strategy_router, trading_router, account_router
from .templates import (
    DashboardData, AccountData, PositionView, TradeView,
    StrategyStatus, SignalView, CandleData, StatsData,
    SignalStock, StockPoolData  # 新增
)


class ConnectionManager:
    """WebSocket 连接管理器"""

    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        """广播消息到所有连接"""
        disconnected = set()
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                disconnected.add(connection)

        # 清理断开的连接
        for conn in disconnected:
            self.active_connections.discard(conn)


class WebEngine(BaseEngine):
    """Web 交易看板引擎

    可嵌入 MainEngine，提供 HTTP/WebSocket 服务。
    """

    engine_name: str = "WebEngine"

    def __init__(self, main_engine: MainEngine, event_engine: EventEngine) -> None:
        """初始化 Web 引擎"""
        super().__init__(main_engine, event_engine, self.engine_name)

        self.main_engine = main_engine
        self.event_engine = event_engine
        self.manager = ConnectionManager()

        # 股票池数据
        self.stock_pool_data: StockPoolData = StockPoolData()

        # 从 lab 加载的可用股票列表
        self.available_symbols: List[str] = []

        # 当前选中的股票（用于 K 线图）
        self.current_symbol: str = ""

        # 所有股票的历史 K 线缓存
        self.all_candles: Dict[str, List[CandleData]] = {}

        # 数据缓存
        self.ticks: Dict[str, TickData] = {}
        self.trades: Dict[str, TradeData] = {}
        self.orders: Dict[str, OrderData] = {}
        self.positions: Dict[str, PositionData] = {}
        self.account: Optional[AccountData] = None
        self.candles: Dict[str, List[CandleData]] = {}  # K线数据缓存
        self.stats: Optional[StatsData] = None  # 统计数据

        # 运行时状态
        self._running = False
        self._server_task = None

        # 创建 FastAPI 应用
        self.app = self._create_app()

        # 注册事件监听
        self._register_events()

        # 初始化数据
        self.stock_pool_data = self._generate_sample_stock_pool()
        self.available_symbols = self._load_available_symbols()

        # 从数据库加载历史K线数据
        for symbol in self.available_symbols:
            self.all_candles[symbol] = self._load_historical_candles(symbol, days=60)

        if self.available_symbols:
            self.current_symbol = self.available_symbols[0]
        self.stats = self._generate_sample_stats()

    def _create_app(self) -> FastAPI:
        """创建 FastAPI 应用"""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """应用生命周期管理"""
            self._running = True
            # 启动后台任务
            broadcast_task = asyncio.create_task(self._broadcast_loop())
            yield
            # 清理
            self._running = False
            broadcast_task.cancel()

        app = FastAPI(
            title="VNPY Web Dashboard",
            description="VNPY 交易看板 API",
            version="1.0.0",
            lifespan=lifespan
        )

        # 挂载静态文件
        try:
            import vnpy.web
            web_dir = Path(vnpy.web.__file__).parent
            static_dir = web_dir / "static"
            if static_dir.exists():
                app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")
        except Exception as e:
            print(f"Warning: Could not mount static files: {e}")

        # 注册路由
        app.include_router(strategy_router, prefix="/api/strategy", tags=["strategy"])
        app.include_router(trading_router, prefix="/api/trading", tags=["trading"])
        app.include_router(account_router, prefix="/api/account", tags=["account"])

        # 根路径返回主页
        @app.get("/", response_class=HTMLResponse)
        async def root():
            return self._get_index_html()

        # WebSocket 端点
        @app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.manager.connect(websocket)
            try:
                # 发送初始数据
                await websocket.send_json({
                    "type": "init",
                    "data": self._get_dashboard_data().dict()
                })

                # 接收客户端消息
                while True:
                    message = await websocket.receive_json()
                    await self._handle_ws_message(websocket, message)

            except WebSocketDisconnect:
                self.manager.disconnect(websocket)
            except Exception as e:
                print(f"WebSocket error: {e}")
                self.manager.disconnect(websocket)

        return app

    def _get_index_html(self) -> str:
        """获取主页 HTML"""
        return """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>VNPY 交易看板</title>
    <link rel="stylesheet" href="/static/css/style.css">
    <script src="https://unpkg.com/vue@3/dist/vue.global.js"></script>
    <script src="https://unpkg.com/element-plus/dist/index.full.js"></script>
    <link rel="stylesheet" href="https://unpkg.com/element-plus/dist/index.css">
    <script src="https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js"></script>
</head>
<body>
    <div id="app">
        <el-container>
            <el-header>
                <h1>VNPY 交易看板</h1>
                <div class="header-status">
                    <el-tag :type="wsStatus.type">{{ wsStatus.text }}</el-tag>
                    <span class="update-time">{{ lastUpdate }}</span>
                </div>
            </el-header>
            <el-main>
                <div class="dashboard">
                    <el-tabs v-model="activeTab" type="border-card">
                        <!-- Tab 1: 交易 -->
                        <el-tab-pane label="交易" name="trading">
                            <el-row :gutter="20" class="overview-row">
                                <el-col :span="6">
                                    <el-card class="metric-card">
                                        <div class="metric-label">总资产</div>
                                        <div class="metric-value">{{ formatMoney(account.balance) }}</div>
                                    </el-card>
                                </el-col>
                                <el-col :span="6">
                                    <el-card class="metric-card">
                                        <div class="metric-label">可用资金</div>
                                        <div class="metric-value">{{ formatMoney(account.available) }}</div>
                                    </el-card>
                                </el-col>
                                <el-col :span="6">
                                    <el-card class="metric-card">
                                        <div class="metric-label">当日盈亏</div>
                                        <div class="metric-value" :class="pnlClass">{{ formatMoney(dailyPnl) }}</div>
                                    </el-card>
                                </el-col>
                                <el-col :span="6">
                                    <el-card class="metric-card">
                                        <div class="metric-label">持仓市值</div>
                                        <div class="metric-value">{{ formatMoney(positionValue) }}</div>
                                    </el-card>
                                </el-col>
                            </el-row>
                            <el-row class="main-content">
                                <el-col :span="16">
                                    <el-card>
                                        <template #header>
                                            <span>持仓明细</span>
                                            <el-button type="primary" size="small" @click="refreshData">刷新</el-button>
                                        </template>
                                        <el-table :data="positions" stripe>
                                            <el-table-column prop="vt_symbol" label="代码" width="120"></el-table-column>
                                            <el-table-column prop="direction" label="方向" width="80">
                                                <template #default="scope">
                                                    <el-tag :type="scope.row.direction === '多' ? 'danger' : 'success'">
                                                        {{ scope.row.direction }}
                                                    </el-tag>
                                                </template>
                                            </el-table-column>
                                            <el-table-column prop="volume" label="数量" width="100"></el-table-column>
                                            <el-table-column prop="avg_price" label="成本价" width="100"></el-table-column>
                                            <el-table-column prop="last_price" label="现价" width="100"></el-table-column>
                                            <el-table-column prop="pnl" label="盈亏">
                                                <template #default="scope">
                                                    <span :class="scope.row.pnl >= 0 ? 'profit' : 'loss'">
                                                        {{ formatMoney(scope.row.pnl) }}
                                                    </span>
                                                </template>
                                            </el-table-column>
                                            <el-table-column prop="pnl_pct" label="盈亏率">
                                                <template #default="scope">
                                                    <span :class="scope.row.pnl_pct >= 0 ? 'profit' : 'loss'">
                                                        {{ scope.row.pnl_pct.toFixed(2) }}%
                                                    </span>
                                                </template>
                                            </el-table-column>
                                        </el-table>
                                    </el-card>
                                    <el-card style="margin-top: 20px;">
                                        <template #header>
                                            <span>最近成交</span>
                                        </template>
                                        <el-table :data="trades" stripe max-height="300">
                                            <el-table-column prop="time" label="时间" width="100"></el-table-column>
                                            <el-table-column prop="vt_symbol" label="代码" width="120"></el-table-column>
                                            <el-table-column prop="direction" label="方向" width="80"></el-table-column>
                                            <el-table-column prop="price" label="价格" width="100"></el-table-column>
                                            <el-table-column prop="volume" label="数量" width="100"></el-table-column>
                                        </el-table>
                                    </el-card>
                                </el-col>
                                <el-col :span="8">
                                    <el-card>
                                        <template #header>
                                            <span>策略控制</span>
                                        </template>
                                        <div class="strategy-list">
                                            <div v-for="st in strategies" :key="st.name" class="strategy-item">
                                                <div class="strategy-info">
                                                    <span class="strategy-name">{{ st.name }}</span>
                                                    <el-tag :type="st.running ? 'success' : 'info'" size="small">
                                                        {{ st.running ? '运行中' : '已停止' }}
                                                    </el-tag>
                                                </div>
                                                <el-switch v-model="st.running" @change="toggleStrategy(st)"></el-switch>
                                            </div>
                                        </div>
                                    </el-card>
                                    <el-card style="margin-top: 20px;">
                                        <template #header>
                                            <span>今日信号</span>
                                        </template>
                                        <div class="signal-list">
                                            <div v-for="sig in signals" :key="sig.id" class="signal-item">
                                                <span class="symbol">{{ sig.symbol }}</span>
                                                <el-tag :type="sig.action === '买入' ? 'danger' : 'success'" size="small">
                                                    {{ sig.action }}
                                                </el-tag>
                                            </div>
                                        </div>
                                    </el-card>
                                </el-col>
                            </el-row>
                        </el-tab-pane>

                        <!-- Tab 2: 股票池 -->
                        <el-tab-pane label="股票池" name="stock_pool">
                            <el-row :gutter="20">
                                <!-- 今日买入 -->
                                <el-col :span="12">
                                    <el-card>
                                        <template #header>
                                            <span style="color: #f56c6c; font-weight: bold;">📈 今日买入信号</span>
                                            <el-tag type="danger" size="small" style="margin-left: 10px;">
                                                {{ stockPool.buy_stocks?.length || 0 }} 只
                                            </el-tag>
                                        </template>
                                        <el-table :data="stockPool.buy_stocks || []" stripe style="width: 100%">
                                            <el-table-column prop="vt_symbol" label="股票代码" width="120"></el-table-column>
                                            <el-table-column prop="close_price" label="收盘价" width="100">
                                                <template #default="scope">¥{{ scope.row.close_price?.toFixed(2) || '--' }}</template>
                                            </el-table-column>
                                            <el-table-column prop="strength" label="信号强度">
                                                <template #default="scope">
                                                    <el-progress
                                                        :percentage="Math.round((scope.row.strength || 0) * 100)"
                                                        :color="'#f56c6c'"
                                                        :show-text="true">
                                                    </el-progress>
                                                </template>
                                            </el-table-column>
                                            <el-table-column prop="volume" label="成交量" width="120">
                                                <template #default="scope">{{ formatVolume(scope.row.volume) }}</template>
                                            </el-table-column>
                                        </el-table>
                                    </el-card>
                                </el-col>

                                <!-- 今日卖出 -->
                                <el-col :span="12">
                                    <el-card>
                                        <template #header>
                                            <span style="color: #67c23a; font-weight: bold;">📉 今日卖出信号</span>
                                            <el-tag type="success" size="small" style="margin-left: 10px;">
                                                {{ stockPool.sell_stocks?.length || 0 }} 只
                                            </el-tag>
                                        </template>
                                        <el-table :data="stockPool.sell_stocks || []" stripe style="width: 100%">
                                            <el-table-column prop="vt_symbol" label="股票代码" width="120"></el-table-column>
                                            <el-table-column prop="close_price" label="收盘价" width="100">
                                                <template #default="scope">¥{{ scope.row.close_price?.toFixed(2) || '--' }}</template>
                                            </el-table-column>
                                            <el-table-column prop="strength" label="信号强度">
                                                <template #default="scope">
                                                    <el-progress
                                                        :percentage="Math.round((scope.row.strength || 0) * 100)"
                                                        :color="'#67c23a'"
                                                        :show-text="true">
                                                    </el-progress>
                                                </template>
                                            </el-table-column>
                                            <el-table-column prop="volume" label="成交量" width="120">
                                                <template #default="scope">{{ formatVolume(scope.row.volume) }}</template>
                                            </el-table-column>
                                        </el-table>
                                    </el-card>
                                </el-col>
                            </el-row>

                            <!-- 股票池更新时间 -->
                            <el-row style="margin-top: 20px;">
                                <el-col :span="24" style="text-align: center; color: #909399;">
                                    股票池更新时间：{{ stockPool.last_update || '--' }}
                                </el-col>
                            </el-row>
                        </el-tab-pane>

                        <!-- Tab 3: K线图表 -->
                        <el-tab-pane label="K线图表" name="charts">
                            <el-row :gutter="20">
                                <el-col :span="24">
                                    <el-card>
                                        <template #header>
                                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                                <span>K线图表</span>
                                                <div>
                                                    <span style="margin-right: 10px; color: #909399;">选择股票：</span>
                                                    <el-select
                                                        v-model="selectedSymbol"
                                                        size="small"
                                                        style="width: 150px;"
                                                        @change="onStockChange"
                                                        placeholder="选择股票">
                                                        <el-option
                                                            v-for="symbol in availableSymbols"
                                                            :key="symbol"
                                                            :label="symbol"
                                                            :value="symbol">
                                                        </el-option>
                                                    </el-select>
                                                </div>
                                            </div>
                                        </template>
                                        <div id="kline-chart" style="height: 500px;"></div>
                                    </el-card>
                                </el-col>
                            </el-row>
                            <el-row :gutter="20" style="margin-top: 20px;">
                                <el-col :span="24">
                                    <el-card>
                                        <template #header>
                                            <span>技术指标</span>
                                        </template>
                                        <div id="indicator-chart" style="height: 200px;"></div>
                                    </el-card>
                                </el-col>
                            </el-row>
                        </el-tab-pane>

                        <!-- Tab 4: 数据分析 -->
                        <el-tab-pane label="数据分析" name="analysis">
                            <el-row :gutter="20">
                                <el-col :span="8">
                                    <el-card class="stats-card">
                                        <template #header>
                                            <span>收益指标</span>
                                        </template>
                                        <div class="stats-grid">
                                            <div class="stat-item">
                                                <div class="stat-label">总收益率</div>
                                                <div class="stat-value" :class="(stats?.total_return || 0) >= 0 ? 'profit' : 'loss'">{{ (stats?.total_return || 0).toFixed(2) }}%</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-label">年化收益</div>
                                                <div class="stat-value" :class="(stats?.annual_return || 0) >= 0 ? 'profit' : 'loss'">{{ (stats?.annual_return || 0).toFixed(2) }}%</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-label">最大回撤</div>
                                                <div class="stat-value loss">{{ (stats?.max_drawdown || 0).toFixed(2) }}%</div>
                                            </div>
                                        </div>
                                    </el-card>
                                </el-col>
                                <el-col :span="8">
                                    <el-card class="stats-card">
                                        <template #header>
                                            <span>风险指标</span>
                                        </template>
                                        <div class="stats-grid">
                                            <div class="stat-item">
                                                <div class="stat-label">夏普比率</div>
                                                <div class="stat-value">{{ (stats?.sharpe_ratio || 0).toFixed(2) }}</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-label">胜率</div>
                                                <div class="stat-value">{{ (stats?.win_rate || 0).toFixed(1) }}%</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-label">盈亏比</div>
                                                <div class="stat-value">{{ (stats?.profit_factor || 0).toFixed(2) }}</div>
                                            </div>
                                        </div>
                                    </el-card>
                                </el-col>
                                <el-col :span="8">
                                    <el-card class="stats-card">
                                        <template #header>
                                            <span>交易统计</span>
                                        </template>
                                        <div class="stats-grid">
                                            <div class="stat-item">
                                                <div class="stat-label">总交易次数</div>
                                                <div class="stat-value">{{ stats?.total_trades || 0 }}</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-label">盈利次数</div>
                                                <div class="stat-value profit">{{ stats?.winning_trades || 0 }}</div>
                                            </div>
                                            <div class="stat-item">
                                                <div class="stat-label">亏损次数</div>
                                                <div class="stat-value loss">{{ stats?.losing_trades || 0 }}</div>
                                            </div>
                                        </div>
                                    </el-card>
                                </el-col>
                            </el-row>
                            <el-row :gutter="20" style="margin-top: 20px;">
                                <el-col :span="12">
                                    <el-card>
                                        <template #header>
                                            <span>盈亏分布</span>
                                        </template>
                                        <div id="pnl-chart" style="height: 300px;"></div>
                                    </el-card>
                                </el-col>
                                <el-col :span="12">
                                    <el-card>
                                        <template #header>
                                            <span>资金曲线</span>
                                        </template>
                                        <div id="equity-chart" style="height: 300px;"></div>
                                    </el-card>
                                </el-col>
                            </el-row>
                        </el-tab-pane>
                    </el-tabs>
                </div>
            </el-main>
        </el-container>
    </div>
    <script src="/static/js/app.js"></script>
</body>
</html>
        """

    def _register_events(self) -> None:
        """注册事件监听"""
        self.event_engine.register(EVENT_TICK, self._on_tick)
        self.event_engine.register(EVENT_TRADE, self._on_trade)
        self.event_engine.register(EVENT_ORDER, self._on_order)
        self.event_engine.register(EVENT_POSITION, self._on_position)
        self.event_engine.register(EVENT_ACCOUNT, self._on_account)

    def _on_tick(self, event: Event) -> None:
        """处理 Tick 事件"""
        tick: TickData = event.data
        self.ticks[tick.vt_symbol] = tick

    def _on_trade(self, event: Event) -> None:
        """处理成交事件"""
        trade: TradeData = event.data
        self.trades[trade.vt_tradeid] = trade
        # 推送实时成交通知
        asyncio.create_task(self._push_notification({
            "type": "trade",
            "data": {
                "vt_symbol": f"{trade.symbol}.{trade.exchange.value}",
                "direction": trade.direction.value,
                "price": trade.price,
                "volume": trade.volume,
                "time": trade.datetime.strftime("%H:%M:%S") if trade.datetime else "--"
            }
        }))

    def _on_order(self, event: Event) -> None:
        """处理订单事件"""
        order: OrderData = event.data
        self.orders[order.vt_orderid] = order

    def _on_position(self, event: Event) -> None:
        """处理持仓事件"""
        position: PositionData = event.data
        self.positions[position.vt_positionid] = position

    def _on_account(self, event: Event) -> None:
        """处理账户事件"""
        account: AccountData = event.data
        self.account = account

    def _get_dashboard_data(self) -> DashboardData:
        """获取看板数据"""
        # 返回当前选中股票的 K 线数据
        chart_data = {}
        if self.current_symbol and self.current_symbol in self.all_candles:
            chart_data = {self.current_symbol: self.all_candles[self.current_symbol]}

        return DashboardData(
            account=self._get_account_data(),
            positions=self._get_position_data(),
            trades=self._get_trade_data(),
            strategies=self._get_strategy_data(),
            signals=self._get_signal_data(),
            chart_data=chart_data,
            available_symbols=self.available_symbols,  # 所有可用股票
            current_symbol=self.current_symbol,  # 当前选中
            stock_pool=self.stock_pool_data,  # 股票池
            stats=self._get_stats_data()
        )

    def _get_account_data(self) -> dict:
        """获取账户数据"""
        if not self.account:
            return {"balance": 0, "available": 0, "frozen": 0}
        return {
            "balance": self.account.balance,
            "available": self.account.available,
            "frozen": self.account.frozen
        }

    def _get_position_data(self) -> list:
        """获取持仓数据"""
        positions = []
        for pos in self.positions.values():
            tick = self.ticks.get(f"{pos.symbol}.{pos.exchange.value}")
            last_price = tick.last_price if tick else pos.price

            pnl = (last_price - pos.price) * pos.volume
            pnl_pct = (last_price / pos.price - 1) * 100 if pos.price else 0

            positions.append({
                "vt_symbol": f"{pos.symbol}.{pos.exchange.value}",
                "direction": pos.direction.value,
                "volume": pos.volume,
                "avg_price": round(pos.price, 2),
                "last_price": round(last_price, 2),
                "pnl": round(pnl, 2),
                "pnl_pct": round(pnl_pct, 2)
            })
        return positions

    def _get_trade_data(self) -> list:
        """获取成交数据"""
        trades = []
        for trade in sorted(self.trades.values(), key=lambda x: x.datetime or datetime.min, reverse=True)[:50]:
            trades.append({
                "vt_symbol": f"{trade.symbol}.{trade.exchange.value}",
                "direction": trade.direction.value,
                "price": trade.price,
                "volume": trade.volume,
                "time": trade.datetime.strftime("%H:%M:%S") if trade.datetime else "--"
            })
        return trades

    def _get_strategy_data(self) -> list:
        """获取策略数据（从引擎获取）"""
        # TODO: 从策略引擎获取实际策略状态
        return [
            {"name": "XGBExtremaLive", "running": True}
        ]

    def _get_signal_data(self) -> list:
        """获取信号数据"""
        # TODO: 从信号管理器获取实际信号
        return []

    def _get_chart_data(self) -> Dict[str, List[CandleData]]:
        """获取图表数据（K线）"""
        return self.candles

    def _get_stats_data(self) -> Optional[StatsData]:
        """获取统计数据"""
        return self.stats

    def _load_historical_candles(self, vt_symbol: str, days: int = 60) -> List[CandleData]:
        """从数据库加载历史K线数据"""
        try:
            from vnpy.trader.database import get_database

            database = get_database()
            symbol, exchange_str = vt_symbol.split('.')

            # 计算时间范围
            end = datetime.now()
            start = end - timedelta(days=days)

            # 从数据库查询
            bars = database.load_bar_data(
                symbol=symbol,
                exchange=Exchange(exchange_str),
                interval=Interval.DAILY,
                start=start,
                end=end
            )

            # 转换为 CandleData
            candles = []
            for bar in bars:
                candles.append(CandleData(
                    timestamp=bar.datetime.strftime("%Y-%m-%d"),
                    open=bar.open_price,
                    high=bar.high_price,
                    low=bar.low_price,
                    close=bar.close_price,
                    volume=bar.volume
                ))

            print(f"加载 {vt_symbol} 历史数据: {len(candles)} 条")
            return candles
        except Exception as e:
            print(f"加载历史数据失败 {vt_symbol}: {e}")
            # 失败时返回示例数据
            return self._generate_sample_candles(vt_symbol, num=100)

    def _generate_sample_candles(self, vt_symbol: str, num: int = 100) -> List[CandleData]:
        """生成示例K线数据（用于测试）"""
        import random
        from datetime import timedelta

        candles = []
        base_price = 100.0
        now = datetime.now()

        for i in range(num):
            dt = now - timedelta(minutes=num - i)
            change = random.uniform(-2, 2)
            open_price = base_price + change
            high = open_price + random.uniform(0, 1)
            low = open_price - random.uniform(0, 1)
            close = low + random.uniform(0, high - low)
            volume = random.uniform(1000, 10000)

            candles.append(CandleData(
                timestamp=dt.strftime("%Y-%m-%d %H:%M:%S"),
                open=round(open_price, 2),
                high=round(high, 2),
                low=round(low, 2),
                close=round(close, 2),
                volume=round(volume, 2)
            ))
            base_price = close

        return candles

    def _generate_sample_stock_pool(self) -> StockPoolData:
        """生成示例股票池数据"""
        from datetime import datetime

        # 今日买入股票
        buy_stocks = [
            SignalStock(vt_symbol="000001.SSE", signal=1, strength=0.85,
                       datetime=datetime.now().strftime("%Y-%m-%d"), close_price=12.50, volume=10000),
            SignalStock(vt_symbol="000002.SSE", signal=1, strength=0.72,
                       datetime=datetime.now().strftime("%Y-%m-%d"), close_price=8.30, volume=5000),
            SignalStock(vt_symbol="600519.SSE", signal=1, strength=0.91,
                       datetime=datetime.now().strftime("%Y-%m-%d"), close_price=1680.00, volume=800),
        ]

        # 今日卖出股票
        sell_stocks = [
            SignalStock(vt_symbol="000300.SSE", signal=-1, strength=0.78,
                       datetime=datetime.now().strftime("%Y-%m-%d"), close_price=4.20, volume=20000),
            SignalStock(vt_symbol="600036.SSE", signal=-1, strength=0.65,
                       datetime=datetime.now().strftime("%Y-%m-%d"), close_price=35.60, volume=3000),
        ]

        return StockPoolData(
            buy_stocks=buy_stocks,
            sell_stocks=sell_stocks,
            last_update=datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )

    def _load_available_symbols(self) -> List[str]:
        """从 lab 加载可用股票列表"""
        return [
            "000001.SSE",  # 平安银行
            "000002.SSE",  # 万科A
            "000300.SSE",  # 沪深300
            "600519.SSE",  # 贵州茅台
            "600036.SSE",  # 招商银行
            "000858.SSE",  # 五粮液
            "002415.SSE",  # 海康威视
            "600276.SSE",  # 恒瑞医药
            "600030.SSE",  # 中信证券
            "601318.SSE",  # 中国平安
        ]

    def set_current_symbol(self, vt_symbol: str) -> bool:
        """设置当前选中的股票"""
        if vt_symbol in self.available_symbols:
            self.current_symbol = vt_symbol
            # 如果该股票没有 K 线数据，从数据库加载
            if vt_symbol not in self.all_candles:
                self.all_candles[vt_symbol] = self._load_historical_candles(vt_symbol, days=60)
            return True
        return False

    def _generate_sample_stats(self) -> StatsData:
        """生成示例统计数据（用于测试）"""
        return StatsData(
            total_return=15.5,
            annual_return=45.2,
            max_drawdown=-8.3,
            sharpe_ratio=1.85,
            win_rate=62.5,
            profit_factor=1.73,
            total_trades=120,
            winning_trades=75,
            losing_trades=45,
            avg_profit=1250.0,
            avg_loss=-680.0
        )

    async def _broadcast_loop(self) -> None:
        """后台广播循环 - 定期推送数据更新"""
        while self._running:
            try:
                await self._push_dashboard_update()
                await asyncio.sleep(1)  # 每秒更新一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Broadcast error: {e}")
                await asyncio.sleep(5)

    async def _push_dashboard_update(self) -> None:
        """推送看板数据更新"""
        await self.manager.broadcast({
            "type": "update",
            "data": self._get_dashboard_data().dict()
        })

    async def _push_notification(self, message: dict) -> None:
        """推送通知"""
        await self.manager.broadcast(message)

    async def _handle_ws_message(self, websocket: WebSocket, message: dict) -> None:
        """处理 WebSocket 消息"""
        msg_type = message.get("type")

        if msg_type == "ping":
            await websocket.send_json({"type": "pong"})

        elif msg_type == "get_data":
            # 客户端请求数据
            await websocket.send_json({
                "type": "data",
                "data": self._get_dashboard_data().dict()
            })

        elif msg_type == "toggle_strategy":
            # 切换策略状态
            strategy_name = message.get("name")
            running = message.get("running")
            print(f"Toggle strategy {strategy_name} -> {running}")
            # TODO: 调用策略引擎启停策略

        elif msg_type == "change_stock":
            # 切换股票
            symbol = message.get("symbol")
            if symbol and self.set_current_symbol(symbol):
                print(f"切换到股票: {symbol}")
                # 推送更新后的数据
                await websocket.send_json({
                    "type": "update",
                    "data": self._get_dashboard_data().dict()
                })
            else:
                await websocket.send_json({
                    "type": "error",
                    "message": f"无效的股票代码: {symbol}"
                })

    async def start_server(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """启动 Web 服务器

        Parameters
        ----------
        host : str
            监听地址
        port : int
            监听端口
        """
        import uvicorn
        print(f"启动 Web 服务: http://{host}:{port}")
        config = uvicorn.Config(self.app, host=host, port=port, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()

    def start(self, host: str = "0.0.0.0", port: int = 8000) -> None:
        """同步方式启动服务器（用于非异步环境）"""
        import uvicorn
        print(f"启动 Web 服务: http://{host}:{port}")
        uvicorn.run(self.app, host=host, port=port)
