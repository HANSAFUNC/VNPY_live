"""
XGBoost 极值选股策略实盘交易示例

使用 TradeEngine 进行实盘交易，连接迅投研或其他交易网关。
"""
import signal
import sys
from datetime import datetime, timedelta
from time import sleep

from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.trader.setting import SETTINGS

# 配置数据库和数据服务
SETTINGS["database.name"] = "postgresql"
SETTINGS["database.host"] = "localhost"
SETTINGS["database.port"] = "5432"
SETTINGS["database.database"] = "vnpy"
SETTINGS["database.user"] = "vnpy"
SETTINGS["database.password"] = "vnpy"

SETTINGS["datafeed.name"] = "xt"
SETTINGS["datafeed.username"] = "client"
SETTINGS["datafeed.password"] = ""

from vnpy.alpha.lab_v2 import AlphaLabV2
from vnpy.alpha.strategy import TradeEngine
from vnpy.alpha.strategy.strategies.xgb_extrema_strategy import XGBExtremaStrategy
from vnpy.trader.constant import Interval, Direction
from vnpy.alpha.logger import logger
from pathlib import Path

# 获取脚本所在目录的绝对路径
SCRIPT_DIR = Path(__file__).parent.resolve()
LAB_PATH = SCRIPT_DIR / "lab"


class LiveTrader:
    """实盘/模拟盘交易管理器"""

    def __init__(
        self,
        paper_trading: bool = True,
        enable_rpc: bool = True,
        xt_account: str = "your_account",  # 迅投账号
    ):
        """
        初始化

        Parameters
        ----------
        paper_trading : bool
            True=模拟盘（本地撮合），False=实盘（真实交易）
        enable_rpc : bool
            是否启用 RPC 服务（供 Web Dashboard 连接）
        xt_account : str
            迅投研账号（用于连接 XT 网关）
        """
        self.paper_trading = paper_trading
        self.enable_rpc = enable_rpc
        self.xt_account = xt_account

        self.event_engine = EventEngine()
        self.main_engine = MainEngine(self.event_engine)

        # 模拟盘模式：添加 PaperAccountApp 以拦截订单
        if paper_trading:
            try:
                from vnpy_paperaccount import PaperAccountApp
                self.main_engine.add_app(PaperAccountApp)
                logger.info("[OK] PaperAccountApp 已加载，订单将在本地撮合")
            except ImportError:
                logger.warning("vnpy_paperaccount 未安装，模拟盘功能可能受限")
                logger.warning("请安装: pip install vnpy-paperaccount")

        # 使用 AlphaLabV2（分层架构）
        self.lab = AlphaLabV2(
            str(LAB_PATH),
            project_name="xgb_extrema",
            data_source="xt",
            index_code="csi300"  # 使用沪深300指数成分股
        )
        self.live_engine: TradeEngine | None = None
        self.rpc_engine = None
        self.gateway_name = "XT"  # 迅投研网关

        # 信号文件路径（由选股器生成）
        self.signal_name = "300_xgb_extrema"

        # 交易参数
        self.index_symbol = "000300.SSE"
        self.top_n = 300  # 沪深300最多300只成分股
        self.capital = 1_000_000  # 100万初始资金
        self.cash_ratio = 0.95    # 95% 现金利用率

        # 设置信号处理
        signal.signal(signal.SIGINT, self.signal_handler)
        signal.signal(signal.SIGTERM, self.signal_handler)

    def signal_handler(self, signum, frame):
        """信号处理 - 优雅退出"""
        logger.info("\n\n[WARN] 接收到退出信号 (Ctrl+C)")
        self.stop()
        sys.exit(0)

    def load_signals(self) -> None:
        """加载选股器生成的信号"""
        logger.info("=" * 60)
        logger.info("加载交易信号")
        logger.info("=" * 60)

        signal_df = self.lab.load_signal(self.signal_name)

        if signal_df is None or signal_df.is_empty():
            logger.error(f"错误：找不到信号文件 {self.signal_name}")
            logger.error("请先运行选股器生成信号：python xgb_extrema_selector.py")
            sys.exit(1)

        logger.info(f"信号数量：{len(signal_df)}")
        logger.info(f"信号日期范围：{signal_df['datetime'].min()} ~ {signal_df['datetime'].max()}")
        logger.info(f"买入信号：{len(signal_df.filter(signal_df['signal'] == 1))}")
        logger.info(f"卖出信号：{len(signal_df.filter(signal_df['signal'] == -1))}")

        # 过滤今日信号
        today = datetime.now().strftime("%Y-%m-%d")
        today_signals = signal_df.filter(
            signal_df['datetime'].cast(str).str.starts_with(today)
        )

        if not today_signals.is_empty():
            logger.info(f"\n今日 ({today}) 交易信号：")
            logger.info(today_signals)
        else:
            logger.info(f"\n今日 ({today}) 无交易信号")

        self.signal_df = signal_df

        # 获取标的列表
        self.vt_symbols = signal_df['vt_symbol'].unique().to_list()
        logger.info(f"\n交易标的数：{len(self.vt_symbols)}")

    def connect_gateway(self) -> bool:
        """连接交易网关"""
        logger.info("\n" + "=" * 60)
        logger.info(f"连接交易网关: {self.gateway_name}")
        logger.info("=" * 60)

        try:
            # 迅投研网关设置
            if self.gateway_name == "XT":
                from vnpy_xt import XtGateway

                self.main_engine.add_gateway(XtGateway, self.gateway_name)

                # 迅投登录配置
                setting = {
                    "账号类型": "股票账号",          # 或 "信用账号"
                    "账号": self.xt_account,
                    "仿真交易": "是" if self.paper_trading else "否",
                    "股票市场": "是",                # 启用股票市场
                    "期货市场": "否",                # 禁用期货市场
                    "期权市场": "否",                # 禁用期权市场
                    "QMT路径": "F:\江海证券QMT实盘_交易",            # QMT安装路径（请根据实际情况修改）
                    "资金账号": "123456"
                }

                self.main_engine.connect(setting, self.gateway_name)
                logger.info(f"[{self.gateway_name}] 连接中...")

                # 等待连接成功
                sleep(5)

                # 检查连接状态
                gateway = self.main_engine.get_gateway(self.gateway_name)
                if gateway:
                    logger.info(f"[{self.gateway_name}] 连接成功")
                    return True
                else:
                    logger.error(f"[{self.gateway_name}] 连接失败")
                    return False

            else:
                logger.error(f"不支持的网关类型: {self.gateway_name}")
                return False

        except ImportError as e:
            logger.error(f"导入网关失败: {e}")
            logger.error("请安装 vnpy_xt: pip install vnpy_xt")
            return True

        except Exception as e:
            logger.error(f"连接网关异常: {e}")
            return False

    def setup_strategy(self) -> None:
        """设置策略"""
        logger.info("\n" + "=" * 60)
        mode_str = "模拟盘" if self.paper_trading else "实盘"
        logger.info(f"设置交易策略 ({mode_str}模式)")
        logger.info("=" * 60)

        # 创建 TradeEngine（自动根据是否加载 paperaccount 决定模拟/实盘）
        # 模拟盘模式下使用 "PAPER" 网关，让 PaperEngine 拦截订单
        engine_gateway = self.gateway_name
        self.live_engine = TradeEngine(
            main_engine=self.main_engine,
            event_engine=self.event_engine,
            lab=self.lab,
            gateway_name=engine_gateway
        )

        # 手动注册到 MainEngine 的 engines 字典
        self.main_engine.engines[self.live_engine.engine_name] = self.live_engine

        # 策略参数
        strategy_setting = {
            "min_days": 1,
            "profit_threshold": 0.03,
            "cash_ratio": self.cash_ratio,
            "min_volume": 100,
            "open_rate": 0.0005,
            "close_rate": 0.0015,
            "min_commission": 5,
            "price_add": 0.0,
        }

        # 添加策略
        self.live_engine.add_strategy(
            strategy_class=XGBExtremaStrategy,
            strategy_name="XGBExtremaLive",
            vt_symbols=self.vt_symbols,
            setting=strategy_setting,
            signal_df=self.signal_df
        )

        logger.info("策略设置完成")
        logger.info(f"  策略：XGBExtremaLive")
        logger.info(f"  初始资金：{self.capital:,.2f}")
        logger.info(f"  现金利用率：{self.cash_ratio * 100:.0f}%")

    def start(self) -> None:
        """启动交易"""
        mode_str = "模拟盘" if self.paper_trading else "实盘"
        logger.info("\n" + "=" * 60)
        logger.info(f"启动{mode_str}交易")
        logger.info("=" * 60)

        # 启动引擎
        self.live_engine.start_trading(
            capital=self.capital,
            cash_ratio=self.cash_ratio
        )

        # 启动 RPC 服务（如启用）
        if self.enable_rpc:
            self._start_rpc_service()

        logger.info(f"\n{mode_str}交易已启动！")
        if self.enable_rpc:
            logger.info("RPC 服务已启动: tcp://*:2014 (REP), tcp://*:2015 (PUB)")
        logger.info("按 Ctrl+C 停止交易")
        logger.info("=" * 60)

        # 主循环
        try:
            while True:
                sleep(1)
                self.print_status()
        except KeyboardInterrupt:
            logger.info("\n\n⚠ 用户中断 (Ctrl+C)")
            self.stop()
        except Exception as e:
            logger.info(f"\n\n✗ 发生错误: {e}")
            self.stop()
            raise

    def _start_rpc_service(self):
        """启动 RPC 服务"""
        try:
            # 从本地 vnpy_rpcservice 导入
            from vnpy_rpcservice.rpc_service.engine import RpcEngine

            # 创建 RpcEngine
            self.rpc_engine = RpcEngine(
                main_engine=self.main_engine,
                event_engine=self.event_engine
            )

            # 手动注册到 MainEngine 的 engines 字典
            self.main_engine.engines[self.rpc_engine.engine_name] = self.rpc_engine

            # 启动 RPC 服务
            self.rpc_engine.start(
                rep_address="tcp://*:2014",
                pub_address="tcp://*:2015"
            )

            logger.info("[RPC] 服务启动成功")
            logger.info("  REP 地址: tcp://*:2014")
            logger.info("  PUB 地址: tcp://*:2015")
        except ImportError as e:
            logger.error(f"[RPC] 导入失败: {e}")
            logger.error("  请检查 vnpy_rpcservice 模块是否存在")
        except Exception as e:
            logger.error(f"[RPC] 启动失败: {e}")

    def stop(self) -> None:
        """停止交易"""
        mode_str = "模拟盘" if self.paper_trading else "实盘"
        logger.info(f"\n正在停止{mode_str}交易...")

        if self.live_engine:
            self.live_engine.stop_trading()

        if self.rpc_engine:
            self.rpc_engine.stop()
            logger.info("[RPC] 服务已停止")

        self.main_engine.close()

        logger.info(f"\n{mode_str}交易已停止")
        logger.info("感谢使用，再见！")

    def print_status(self) -> None:
        """打印交易状态（每分钟一次）"""
        if not hasattr(self, '_last_print'):
            self._last_print = datetime.now()

        now = datetime.now()
        if (now - self._last_print).seconds >= 60:
            self._last_print = now

            mode_str = "模拟盘" if self.paper_trading else "实盘"
            logger.info(f"\n[{now.strftime('%H:%M:%S')}] {mode_str}状态更新:")

            if self.live_engine:
                # 获取账户和持仓
                if self.paper_trading:
                    # 模拟盘：从 paper_positions 获取
                    account = self.live_engine.account
                    positions = getattr(self.live_engine, 'paper_positions', {})
                    active_orders = self.live_engine.active_orders

                    if account:
                        logger.info(f"  账户资金: {account.balance:,.2f}")
                        logger.info(f"  可用资金: {account.available:,.2f}")
                        logger.info(f"  持仓市值: {self.live_engine.get_holding_value():,.2f}")

                    if positions:
                        logger.info(f"  持仓数量: {len(positions)}")
                        for vt_symbol, pos in list(positions.items())[:5]:
                            direction = "多" if pos.get('direction') == Direction.LONG else "空"
                            logger.info(f"    {vt_symbol}: {direction} {pos['volume']} 股 @ {pos['price']:.2f}")

                    if active_orders:
                        logger.info(f"  活跃订单: {len(active_orders)}")

                    # 打印当日盈亏
                    if hasattr(self.live_engine, 'initial_capital'):
                        pnl = account.balance - self.live_engine.initial_capital
                        pnl_pct = pnl / self.live_engine.initial_capital * 100
                        logger.info(f"  当日盈亏: {pnl:,.2f} ({pnl_pct:.2f}%)")
                else:
                    # 实盘：从网关获取
                    account = self.live_engine.account
                    positions = self.live_engine.positions
                    active_orders = self.live_engine.active_orders

                    if account:
                        logger.info(f"  账户资金: {account.balance:,.2f}")
                        logger.info(f"  可用资金: {account.available:,.2f}")
                        logger.info(f"  冻结资金: {account.frozen:,.2f}")

                    if positions:
                        logger.info(f"  持仓数量: {len(positions)}")
                        for vt_symbol, pos in list(positions.items())[:5]:
                            direction = "多" if pos.direction.value == "多" else "空"
                            logger.info(f"    {vt_symbol}: {direction} {pos.volume} 股")

                    if active_orders:
                        logger.info(f"  活跃订单: {len(active_orders)}")


def run_backtest_mode():
    """回测模式（用于验证策略）"""
    logger.info("=" * 60)
    logger.info("回测模式 - 验证策略逻辑")
    logger.info("=" * 60)

    from vnpy.alpha.strategy import BacktestingEngine
    from vnpy.alpha import Segment

    lab = AlphaLabV2(
        str(LAB_PATH),
        project_name="xgb_extrema",
        data_source="xt",
        index_code="csi300"
    )

    # 加载信号
    signal_df = lab.load_signal("300_xgb_extrema")
    if signal_df is None:
        logger.info("请先运行选股器生成信号")
        return

    # 获取交易标的
    vt_symbols = signal_df['vt_symbol'].unique().to_list()

    # 创建回测引擎
    engine = BacktestingEngine(lab)

    # 设置参数
    start_date = signal_df['datetime'].min()
    end_date = signal_df['datetime'].max()

    engine.set_parameters(
        vt_symbols=vt_symbols,
        interval=Interval.DAILY,
        start=start_date,
        end=end_date,
        capital=1_000_000,
        risk_free=0.02,
        annual_days=240
    )

    # 添加策略
    engine.add_strategy(
        XGBExtremaStrategy,
        {
            "min_days": 1,
            "profit_threshold": 0.03,
            "cash_ratio": 0.95,
            "min_volume": 100,
        },
        signal_df
    )

    # 加载数据并运行
    engine.load_data()
    engine.run_backtesting()

    # 计算结果
    engine.calculate_result()
    statistics = engine.calculate_statistics()

    logger.info("\n回测完成！")
    logger.info(f"总收益率: {statistics.get('total_return', 0):.2f}%")
    logger.info(f"年化收益: {statistics.get('annual_return', 0):.2f}%")
    logger.info(f"最大回撤: {statistics.get('max_ddpercent', 0):.2f}%")


def main():
    """主函数"""
    import argparse

    parser = argparse.ArgumentParser(description='XGBoost 极值策略实盘交易')
    parser.add_argument('--mode', choices=['live', 'paper', 'backtest'], default='paper',
                       help='运行模式: live=实盘, paper=模拟盘, backtest=回测')
    parser.add_argument('--gateway', default='XT', help='交易网关名称')
    parser.add_argument('--capital', type=float, default=1_000_000, help='初始资金（默认100万）')
    parser.add_argument('--enable-rpc', action='store_true',default=True,
                       help='启用 RPC 服务（供 Web Dashboard 连接）')

    parser.add_argument('--xt-account', default='your_account',
                       help='迅投研账号（实盘/模拟盘需要）')

    args = parser.parse_args()

    if args.mode == 'backtest':
        run_backtest_mode()
    elif args.mode == 'paper':
        # 模拟盘模式：使用真实行情，本地模拟成交
        logger.info("=" * 60)
        logger.info("模拟盘模式 - 使用实时行情，本地模拟成交")
        logger.info("=" * 60)

        trader = LiveTrader(
            paper_trading=True,
            enable_rpc=args.enable_rpc,
            xt_account=args.xt_account,
        )
        trader.gateway_name = args.gateway  # 使用指定网关获取行情
        trader.capital = args.capital

        # 加载信号
        trader.load_signals()

        # 模拟盘也需要连接网关获取实时行情
        logger.info("\n提示：模拟盘模式连接行情网关获取实时数据")
        logger.info("交易订单将在本地撮合，不会发送到交易所")

        if not trader.connect_gateway():
            logger.error("连接行情网关失败")
            return

        # 设置策略
        trader.setup_strategy()

        # 启动交易
        trader.start()
    else:
        # 实盘模式：真实订单发送到交易所
        logger.info("=" * 60)
        logger.info("实盘模式 - 真实订单发送到交易所")
        logger.info("=" * 60)

        trader = LiveTrader(
            paper_trading=False,
            enable_rpc=args.enable_rpc,
            xt_account=args.xt_account,
        )
        trader.gateway_name = args.gateway
        trader.capital = args.capital

        # 加载信号
        trader.load_signals()

        # 连接网关（实盘必须连接）
        if not trader.connect_gateway():
            logger.info("连接网关失败，退出")
            return

        # 设置策略
        trader.setup_strategy()

        # 启动交易
        trader.start()


if __name__ == "__main__":
    main()
