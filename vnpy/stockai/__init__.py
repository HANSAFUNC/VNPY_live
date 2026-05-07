"""StockAI - FreqAI 兼容的股票机器学习预测管道"""

from .base_models.base_classifier_model import BaseClassifierModel
from .base_models.base_regression_model import BaseRegressionModel
from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen
from .stockai_interface import IFreqaiModel

__version__ = "0.2.0"

__all__ = [
    "IFreqaiModel",  # 主接口 (FreqAI 风格命名)
    "StockaiDataDrawer",
    "StockaiDataKitchen",
    "BaseRegressionModel",
    "BaseClassifierModel",
]

# 向后兼容: IStockaiModel 是 IFreqaiModel 的别名
IStockaiModel = IFreqaiModel

# Lazy import for optional dependencies
def __getattr__(name):
    if name == "XGBoostRegressor":
        from .prediction_models.XGBoostRegressor import XGBoostRegressor
        return XGBoostRegressor
    if name == "LightGBMRegressor":
        from .prediction_models.LightGBMRegressor import LightGBMRegressor
        return LightGBMRegressor
    if name == "XGBoostExtremaModel":
        from .prediction_models.xgb_extrema_model import XGBoostExtremaModel
        return XGBoostExtremaModel
    raise AttributeError(f"module '{__name__}' has no attribute '{name}'")
