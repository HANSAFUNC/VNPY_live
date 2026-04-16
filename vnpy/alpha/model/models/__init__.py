from .lasso_model import LassoModel
from .lgb_model import LgbModel
from .xgb_extrema_model import XGBoostExtremaModel

# MlpModel requires torch - import only if available
try:
    from .mlp_model import MlpModel
    __all__ = [
        "LassoModel",
        "LgbModel",
        "MlpModel",
        "XGBoostExtremaModel",
    ]
except ImportError:
    __all__ = [
        "LassoModel",
        "LgbModel",
        "XGBoostExtremaModel",
    ]