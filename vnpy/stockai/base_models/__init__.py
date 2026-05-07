"""StockAI 基础模型模块"""

from .base_classifier_model import BaseClassifierModel
from .base_regression_model import BaseRegressionModel

__all__ = [
    "BaseRegressionModel",
    "BaseClassifierModel",
]
