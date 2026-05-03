"""StockAI - FreqAI兼容的股票机器学习预测管道"""

from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen
from .stockai_interface import IStockaiModel
from .base_models.base_regression_model import BaseRegressionModel

__version__ = "0.1.0"

__all__ = [
    "StockaiDataDrawer",
    "StockaiDataKitchen",
    "IStockaiModel",
    "BaseRegressionModel",
]

# Lazy import for optional dependencies
def __getattr__(name):
    if name == "XGBoostExtremaModel":
        from .prediction_models.xgb_extrema_model import XGBoostExtremaModel
        return XGBoostExtremaModel
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
