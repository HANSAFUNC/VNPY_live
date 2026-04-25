#!/usr/bin/env python
"""
Lab 数据迁移脚本

将旧的 lab/csi300 结构迁移到新的分层架构：
- K线数据 -> lab/data/xt/daily/
- 成分股数据 -> lab/index/all_a/components/
- 项目数据 -> lab/project/{name}/
"""
import shutil
from pathlib import Path
from datetime import datetime
import shelve

from vnpy.alpha.data_store import DataStore
from vnpy.alpha.index_manager import IndexManager


def migrate_lab(old_lab_path: str, new_lab_path: str):
    """
    迁移 lab 数据

    Parameters
    ----------
    old_lab_path : str
        旧的 lab 路径，如 "./lab/csi300"
    new_lab_path : str
        新的 lab 根路径，如 "./lab"
    """
    old_path = Path(old_lab_path)
    new_path = Path(new_lab_path)

    print("=" * 60)
    print("Lab 数据迁移")
    print("=" * 60)
    print(f"旧路径: {old_path.absolute()}")
    print(f"新路径: {new_path.absolute()}")
    print()

    # 初始化新的数据层
    data_store = DataStore(str(new_path), source="xt")
    index_manager = IndexManager(str(new_path))

    # 1. 迁移 K 线数据
    print("1. 迁移 K 线数据...")
    old_daily = old_path / "daily"
    if old_daily.exists():
        parquet_files = list(old_daily.glob("*.parquet"))
        print(f"   找到 {len(parquet_files)} 个日线文件")

        for file_path in parquet_files:
            # 直接复制 parquet 文件
            vt_symbol = file_path.stem
            new_path_file = data_store.daily_path / f"{vt_symbol}.parquet"
            shutil.copy2(file_path, new_path_file)

        print(f"   [OK] 已迁移到: {data_store.daily_path}")

    # 2. 迁移成分股数据（作为 all_a 指数）
    print("\n2. 迁移成分股数据...")
    old_component = old_path / "component"
    if old_component.exists():
        # 创建 all_a 指数
        index_manager.create_index("all_a", "全部A股", "沪深A股")

        # 迁移 shelve 文件
        for shelve_file in old_component.glob("*"):
            if not shelve_file.is_file() or shelve_file.suffix:
                continue

            index_code = shelve_file.name
            print(f"   迁移指数: {index_code}")

            # 读取旧的 shelve
            with shelve.open(str(shelve_file)) as old_db:
                for date_str, symbols in old_db.items():
                    index_manager.save_components("all_a", date_str, symbols)

        print(f"   [OK] 已迁移到: {index_manager.index_path / 'all_a'}")

    # 3. 迁移项目数据
    print("\n3. 迁移项目数据...")
    old_project_dirs = ["dataset", "model", "signal"]
    for dir_name in old_project_dirs:
        old_dir = old_path / dir_name
        if old_dir.exists():
            # 默认迁移到 default 下（直接放在 lab/ 下）
            new_project_dir = new_path / "default" / dir_name
            new_project_dir.mkdir(parents=True, exist_ok=True)

            for file in old_dir.glob("*"):
                shutil.copy2(file, new_project_dir / file.name)

            print(f"   [OK] {dir_name} -> {new_project_dir}")

    # 4. 迁移合约配置
    print("\n4. 迁移合约配置...")
    old_contract = old_path / "contract.json"
    if old_contract.exists():
        new_contract = new_path / "default" / "contract.json"
        new_contract.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old_contract, new_contract)
        print(f"   [OK] contract.json -> {new_contract}")

    print("\n" + "=" * 60)
    print("迁移完成!")
    print("=" * 60)
    print(f"新架构路径: {new_path.absolute()}")
    print()
    print("目录结构:")
    print(f"  - K线数据: {data_store.daily_path}")
    print(f"  - 成分股:  {index_manager.index_path}/all_a")
    print(f"  - 项目:    {new_path}/default")
    print()
    print("提示：修改你的代码使用 AlphaLabV2:")
    print("  from vnpy.alpha.lab_v2 import AlphaLabV2")
    print('  lab = AlphaLabV2("./lab", "my_strategy", "xt", "all_a")')


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="迁移 Lab 数据到新架构")
    parser.add_argument(
        "--old",
        default="lab/csi300",
        help="旧的 lab 路径"
    )
    parser.add_argument(
        "--new",
        default="lab",
        help="新的 lab 根路径"
    )

    args = parser.parse_args()
    migrate_lab(args.old, args.new)
