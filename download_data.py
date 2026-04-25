#!/usr/bin/env python
"""
数据下载脚本 - 下载迅投数据到新架构

使用方式:
    python download_data.py --start 20240101 --end 20260415
"""
import argparse
from datetime import datetime
from pathlib import Path

from tqdm import tqdm
from xtquant import xtdata

from vnpy.trader.database import DB_TZ
from vnpy.trader.constant import Exchange, Interval
from vnpy.trader.object import HistoryRequest
from vnpy.trader.setting import SETTINGS

from vnpy.alpha.data_store import DataStore
from vnpy.alpha.index_manager import IndexManager
from vnpy.alpha import logger


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


def download_data(start_date: str, end_date: str, lab_path: str = "./lab"):
    """
    下载数据到分层架构

    Parameters
    ----------
    start_date : str
        开始日期，格式 YYYYMMDD
    end_date : str
        结束日期，格式 YYYYMMDD
    lab_path : str
        lab根目录路径
    """
    print("=" * 60)
    print("数据下载 - 分层架构")
    print("=" * 60)
    print(f"日期范围: {start_date} ~ {end_date}")
    print(f"lab路径: {lab_path}")
    print()

    # 初始化数据层和索引层
    data_store = DataStore(lab_path, source="xt")
    index_manager = IndexManager(lab_path)

    print(f"数据存储: {data_store.daily_path}")
    print(f"索引存储: {index_manager.index_path}")
    print()

    # 创建指数配置
    index_manager.create_index("csi300", "沪深300", "000300.SH")
    index_manager.create_index("csi500", "中证500", "000905.SH")
    index_manager.create_index("sse50", "上证50", "000016.SH")

    # 1. 获取全部A股列表
    print("\n1. 获取全部A股列表...")
    all_a_codes = xtdata.get_stock_list_in_sector('沪深A股')
    print(f"   沪深A股共 {len(all_a_codes)} 只")

    # 2. 获取指数成分股
    print("\n2. 获取指数成分股...")
    csi300_codes = xtdata.get_stock_list_in_sector('沪深300')
    csi300_symbols = [code.replace(".SH", ".SSE").replace(".SZ", ".SZSE")
                      for code in csi300_codes]
    print(f"   沪深300: {len(csi300_symbols)} 只")

    csi500_codes = xtdata.get_stock_list_in_sector('中证500')
    csi500_symbols = [code.replace(".SH", ".SSE").replace(".SZ", ".SZSE")
                      for code in csi500_codes]
    print(f"   中证500: {len(csi500_symbols)} 只")

    sse50_codes = xtdata.get_stock_list_in_sector('上证50')
    sse50_symbols = [code.replace(".SH", ".SSE").replace(".SZ", ".SZSE")
                      for code in sse50_codes]
    print(f"   上证50: {len(sse50_symbols)} 只")

    # 3. 保存成分股到索引层
    print("\n3. 保存成分股到索引层...")
    days = xtdata.get_trading_dates(market="SZ", start_time=start_date, end_time=end_date)
    print(f"   交易日数: {len(days)}")

    end_datetime = datetime.strptime(end_date, "%Y%m%d").replace(tzinfo=DB_TZ)

    for ts in tqdm(days, desc="   保存成分股"):
        dt = datetime.fromtimestamp(ts / 1000, tz=DB_TZ)
        if dt > end_datetime:
            continue

        date_str = dt.strftime("%Y-%m-%d")

        index_manager.save_components("csi300", date_str, csi300_symbols)
        index_manager.save_components("csi500", date_str, csi500_symbols)
        index_manager.save_components("sse50", date_str, sse50_symbols)

    print(f"   [OK] 成分股已保存到索引层")

    # 4. 下载K线数据
    print("\n4. 下载K线数据到数据层...")

    # 导入数据feed
    from vnpy.trader.datafeed import get_datafeed
    datafeed = get_datafeed()
    result = datafeed.init()
    print(f"   数据服务初始化: {result}")

    # 准备下载列表（合并所有需要的股票）
    all_symbols = list(set(csi300_symbols + csi500_codes + all_a_codes))
    print(f"   需要下载: {len(all_symbols)} 只股票")

    # 时间范围
    start_dt = datetime.strptime(start_date, "%Y%m%d").replace(tzinfo=DB_TZ)
    end_dt = datetime.strptime(end_date, "%Y%m%d").replace(tzinfo=DB_TZ)

    # 下载
    success_count = 0
    fail_count = 0
    skip_count = 0

    for xt_symbol in tqdm(all_symbols, desc="   下载K线"):
        try:
            # 处理交易所代码
            if ".SH" in xt_symbol:
                symbol = xt_symbol.replace(".SH", "")
                exchange = Exchange.SSE
                vt_symbol = xt_symbol.replace(".SH", ".SSE")
            elif ".SZ" in xt_symbol:
                symbol = xt_symbol.replace(".SZ", "")
                exchange = Exchange.SZSE
                vt_symbol = xt_symbol.replace(".SZ", ".SZSE")
            else:
                symbol, exchange_str = xt_symbol.split(".")
                exchange = Exchange(exchange_str)
                vt_symbol = xt_symbol

            # 检查本地已有数据
            existing_info = data_store.get_data_info(vt_symbol, Interval.DAILY)
            if existing_info:
                existing_start = datetime.fromisoformat(existing_info['start']) if existing_info['start'] else None
                existing_end = datetime.fromisoformat(existing_info['end']) if existing_info['end'] else None

                # 检查是否已覆盖请求的范围
                if existing_start and existing_end:
                    if existing_start <= start_dt and existing_end >= end_dt:
                        skip_count += 1
                        continue

            req = HistoryRequest(
                symbol=symbol,
                exchange=exchange,
                start=start_dt,
                end=end_dt,
                interval=Interval.DAILY
            )

            bars = datafeed.query_bar_history(req)
            if bars:
                data_store.save_bars(bars)
                success_count += 1
            else:
                fail_count += 1

        except Exception as e:
            logger.error(f"下载 {xt_symbol} 失败: {e}")
            fail_count += 1

    print(f"   [OK] 下载完成: 成功 {success_count}, 跳过 {skip_count}, 失败 {fail_count}")

    # 5. 总结
    print("\n" + "=" * 60)
    print("下载完成")
    print("=" * 60)
    print(f"\n目录结构:")
    print(f"  数据层: {data_store.daily_path}")
    print(f"  索引层: {index_manager.index_path}")
    print(f"\n支持的指数:")
    for idx in index_manager.list_indices():
        info = index_manager.get_index_info(idx)
        print(f"  - {idx}: {info['name'] if info else 'N/A'}")
    print(f"\n使用示例:")
    print(f'  from vnpy.alpha.lab_v2 import AlphaLabV2')
    print(f'  lab = AlphaLabV2("{lab_path}", "my_strategy", "xt", "csi300")')


def main():
    parser = argparse.ArgumentParser(description="下载迅投数据到新架构")
    parser.add_argument(
        "--start",
        default="20240101",
        help="开始日期 (YYYYMMDD)"
    )
    parser.add_argument(
        "--end",
        default="20260415",
        help="结束日期 (YYYYMMDD)"
    )
    parser.add_argument(
        "--lab-path",
        default="./lab",
        help="lab根目录路径"
    )

    args = parser.parse_args()

    download_data(args.start, args.end, args.lab_path)


if __name__ == "__main__":
    main()
