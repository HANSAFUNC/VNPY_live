"""StockAI 代码结构检查脚本

不需要外部依赖，仅检查代码结构和语法
"""

import ast
import sys
from pathlib import Path


def check_file_syntax(filepath):
    """检查 Python 文件语法"""
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            source = f.read()
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, str(e)


def check_imports(filepath, valid_imports):
    """检查导入语句"""
    with open(filepath, 'r', encoding='utf-8') as f:
        source = f.read()

    tree = ast.parse(source)
    errors = []

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not any(alias.name.startswith(v) for v in valid_imports):
                    errors.append(f"未知导入: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if node.module and not any(node.module.startswith(v) for v in valid_imports):
                errors.append(f"未知从导入: {node.module}")

    return errors


def main():
    """主函数"""
    project_root = Path("F:/vnpy_live")

    # 定义允许的外部导入
    valid_imports = [
        'logging',
        'datetime',
        'pathlib',
        'typing',
        'abc',
        'unittest',
        'collections',
        'copy',
        'functools',
        'importlib',
        'inspect',
        'json',
        'random',
        're',
        'shutil',
        'threading',
        'time',
        'warnings',
        'joblib',
        'numpy',
        'polars',
        'scipy',
        'sklearn',
        'xgboost',
        'vnpy',
        '.',  # 相对导入
    ]

    # 要检查的文件
    files = [
        'vnpy/stockai/__init__.py',
        'vnpy/stockai/utils.py',
        'vnpy/stockai/data_drawer.py',
        'vnpy/stockai/data_kitchen.py',
        'vnpy/stockai/stockai_interface.py',
        'vnpy/stockai/base_models/__init__.py',
        'vnpy/stockai/base_models/base_regression_model.py',
        'vnpy/stockai/base_models/base_classifier_model.py',
        'vnpy/stockai/prediction_models/__init__.py',
        'vnpy/stockai/prediction_models/XGBoostRegressor.py',
        'vnpy/stockai/prediction_models/LightGBMRegressor.py',
    ]

    # 添加可选检查的旧文件
    optional_files = [
        'vnpy/stockai/prediction_models/xgb_extrema_model.py',
    ]

    print("=" * 60)
    print("StockAI Code Structure Check")
    print("=" * 60)

    all_passed = True

    # 检查必需文件
    print("\n[Required Files]")
    for filepath in files:
        full_path = project_root / filepath

        if not full_path.exists():
            print(f"[FAIL] {filepath}: File not found")
            all_passed = False
            continue

        # Check syntax
        syntax_ok, syntax_error = check_file_syntax(full_path)

        if not syntax_ok:
            print(f"[FAIL] {filepath}: Syntax error")
            print(f"       Error: {syntax_error}")
            all_passed = False
            continue

        print(f"[PASS] {filepath}")

    # 检查可选文件
    print("\n[Optional Files]")
    for filepath in optional_files:
        full_path = project_root / filepath

        if not full_path.exists():
            print(f"[SKIP] {filepath}: File not found (optional)")
            continue

        syntax_ok, syntax_error = check_file_syntax(full_path)

        if not syntax_ok:
            print(f"[FAIL] {filepath}: Syntax error")
            print(f"       Error: {syntax_error}")
            all_passed = False
            continue

        print(f"[PASS] {filepath}")

    print("\n" + "=" * 60)

    if all_passed:
        print("All required files passed syntax check")
    else:
        print("Some files have syntax errors")
        sys.exit(1)


if __name__ == "__main__":
    main()
