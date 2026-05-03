# StockAI 实现计划

> **执行说明:** 本计划使用 superpowers:subagent-driven-development 或 superpowers:executing-plans 分任务执行

**目标:** 实现 vnpy/stockai 模块 - 基于 FreqAI 架构的股票机器学习预测管道

**架构:** 复刻 FreqAI 模式：IStockaiModel(接口) → BaseRegressionModel(基类) → XGBoostExtremaModel(实现类)。数据管理通过 StockaiDataKitchen(单只股票) 和 StockaiDataDrawer(全局存储) 分离

**技术栈:** Python, polars, pyarrow, xgboost, scikit-learn, joblib

---

## 文件结构

```
vnpy/stockai/
├── __init__.py                 # 模块入口，导出所有类
├── utils.py                    # 工具函数（时间戳、文件读写等）
├── data_drawer.py              # StockaiDataDrawer - 全局存储管理
├── data_kitchen.py             # StockaiDataKitchen - 单只股票数据管理
├── stockai_interface.py       # IStockaiModel - 模型接口基类
├── base_models/
│   ├── __init__.py
│   └── base_regression_model.py   # BaseRegressionModel - 回归模型基类
└── prediction_models/
    ├── __init__.py
    └── xgb_extrema_model.py       # XGBoostExtremaModel - XGBoost实现
```

---

## 任务1: 创建目录结构和工具函数

**涉及文件:**
- 新建: `vnpy/stockai/__init__.py`
- 新建: `vnpy/stockai/utils.py`
- 新建: `vnpy/stockai/base_models/__init__.py`
- 新建: `vnpy/stockai/prediction_models/__init__.py`

- [ ] **步骤1.1: 创建目录结构**

```bash
mkdir -p vnpy/stockai/base_models
mkdir -p vnpy/stockai/prediction_models
touch vnpy/stockai/base_models/__init__.py
touch vnpy/stockai/prediction_models/__init__.py
```

- [ ] **步骤1.2: 编写 utils.py**

功能：提供工具函数供其他模块使用

```python
"""StockAI 工具函数模块"""

import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import polars as pl

logger = logging.getLogger(__name__)


def get_timestamp() -> int:
    """获取当前时间戳（秒）"""
    return int(datetime.now().timestamp())


def save_json(data: dict, path: Path) -> None:
    """保存字典到JSON文件"""
    import json
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_json(path: Path) -> Optional[dict]:
    """从JSON文件加载字典"""
    import json
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_parquet(df: pl.DataFrame, path: Path) -> None:
    """保存DataFrame到Parquet文件"""
    path.parent.mkdir(parents=True, exist_ok=True)
    df.write_parquet(path)


def load_parquet(path: Path) -> Optional[pl.DataFrame]:
    """从Parquet文件加载DataFrame"""
    if not path.exists():
        return None
    return pl.read_parquet(path)
```

- [ ] **步骤1.3: 提交代码**

```bash
git add vnpy/stockai/
git commit -m "feat(stockai): 创建目录结构和工具函数"
```

---

## 任务2: 实现 StockaiDataDrawer（数据抽屉）

**涉及文件:**
- 新建: `vnpy/stockai/data_drawer.py`

**功能说明:**
StockaiDataDrawer 是全局存储管理器，负责：
- 管理所有股票的模型和预测历史
- 将数据持久化到磁盘
- 维护模型版本信息
- 提供历史预测查询

生命周期：单例模式，与 IStockaiModel 生命周期一致

- [ ] **步骤2.1: 编写 data_drawer.py**

```python
"""StockAI 数据抽屉 - 全局持久化存储管理"""

import logging
from pathlib import Path
from typing import Any, Optional

import joblib
import polars as pl

from .utils import get_timestamp, load_json, load_parquet, save_json, save_parquet

logger = logging.getLogger(__name__)


class StockaiDataDrawer:
    """
    全局数据存储管理器
    
    职责:
    - 存储每只股票元数据（模型文件名、训练时间戳）
    - 缓存已加载的模型在内存中
    - 持久化预测历史到磁盘
    - 管理模型版本
    
    对应 FreqAI 的 FreqaiDataDrawer 类
    """

    def __init__(self, full_path: Path, config: dict):
        """
        初始化数据抽屉
        
        参数:
            full_path: 数据存储根目录
            config: 配置字典
        """
        self.config = config
        self.full_path = full_path
        self.full_path.mkdir(parents=True, exist_ok=True)
        
        # 内存存储结构
        self.pair_dict: dict[str, dict] = {}  # {股票代码: 元数据}
        self.model_dictionary: dict[str, Any] = {}  # {文件名: 模型对象}
        self.historic_predictions: dict[str, pl.DataFrame] = {}  # {股票代码: 预测历史}
        
        # 文件路径
        self.historic_predictions_path = full_path / "historic_predictions.parquet"
        self.pair_dictionary_path = full_path / "pair_dictionary.json"
        
        # 从磁盘加载已有数据
        self._load_from_disk()
        
        logger.info(f"数据抽屉初始化完成，路径: {full_path}")

    def _load_from_disk(self) -> None:
        """从磁盘加载已有数据"""
        # 加载股票元数据
        data = load_json(self.pair_dictionary_path)
        if data:
            self.pair_dict = data
            logger.info(f"已加载 {len(self.pair_dict)} 只股票的元数据")
        
        # 加载预测历史
        df = load_parquet(self.historic_predictions_path)
        if df is not None:
            for pair in df["pair"].unique().to_list():
                self.historic_predictions[pair] = df.filter(pl.col("pair") == pair)
            logger.info(f"已加载 {len(self.historic_predictions)} 只股票的历史预测")

    def _generate_model_filename(self, pair: str, timestamp: int) -> str:
        """生成模型文件名"""
        safe_pair = pair.replace(".", "_")
        return f"sub-train-{safe_pair}_{timestamp}"

    def save_model(self, pair: str, model: Any, timestamp: int) -> None:
        """
        保存模型到磁盘
        
        参数:
            pair: 股票代码
            model: 模型对象
            timestamp: 时间戳
        """
        filename = self._generate_model_filename(pair, timestamp)
        model_path = self.full_path / filename
        model_path.mkdir(parents=True, exist_ok=True)
        
        # 使用 joblib 保存模型
        model_file = model_path / "model.pkl"
        joblib.dump(model, model_file)
        
        # 缓存到内存
        self.model_dictionary[filename] = model
        
        # 更新元数据
        self.pair_dict[pair] = {
            "model_filename": filename,
            "trained_timestamp": timestamp,
            "data_path": str(model_path),
        }
        save_json(self.pair_dict, self.pair_dictionary_path)
        
        logger.info(f"模型已保存: {filename} ({pair})")

    def load_model(self, pair: str) -> Any:
        """
        加载模型（优先从内存缓存）
        
        参数:
            pair: 股票代码
            
        返回:
            模型对象
        """
        if pair not in self.pair_dict:
            raise ValueError(f"未找到 {pair} 的模型")
        
        filename = self.pair_dict[pair]["model_filename"]
        
        # 检查内存缓存
        if filename in self.model_dictionary:
            return self.model_dictionary[filename]
        
        # 从磁盘加载
        model_path = self.full_path / filename / "model.pkl"
        if not model_path.exists():
            raise FileNotFoundError(f"模型文件不存在: {model_path}")
        
        model = joblib.load(model_path)
        self.model_dictionary[filename] = model
        logger.info(f"模型已加载: {filename} ({pair})")
        
        return model

    def append_predictions(self, pair: str, predictions: pl.DataFrame) -> None:
        """
        追加预测结果到历史
        
        参数:
            pair: 股票代码
            predictions: 预测结果DataFrame
        """
        if pair in self.historic_predictions:
            self.historic_predictions[pair] = pl.concat(
                [self.historic_predictions[pair], predictions]
            )
        else:
            self.historic_predictions[pair] = predictions
        
        # 持久化到磁盘
        self._save_predictions_to_disk()

    def _save_predictions_to_disk(self) -> None:
        """将所有预测历史保存到磁盘"""
        if not self.historic_predictions:
            return
        
        all_preds = pl.concat(list(self.historic_predictions.values()))
        save_parquet(all_preds, self.historic_predictions_path)

    def get_historic_predictions(
        self,
        pair: str,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
    ) -> Optional[pl.DataFrame]:
        """
        获取历史预测
        
        参数:
            pair: 股票代码
            start: 开始时间（可选）
            end: 结束时间（可选）
            
        返回:
            预测历史DataFrame
        """
        if pair not in self.historic_predictions:
            return None
        
        df = self.historic_predictions[pair]
        
        if start:
            df = df.filter(pl.col("datetime") >= start)
        if end:
            df = df.filter(pl.col("datetime") <= end)
        
        return df.sort("datetime")

    def should_retrain(self, pair: str, max_age_days: int = 30) -> bool:
        """
        检查是否需要重新训练
        
        参数:
            pair: 股票代码
            max_age_days: 模型最大年龄（天）
            
        返回:
            True 如果需要重新训练
        """
        if pair not in self.pair_dict:
            return True
        
        last_trained = self.pair_dict[pair].get("trained_timestamp", 0)
        age_days = (get_timestamp() - last_trained) / 86400
        
        return age_days > max_age_days
```

- [ ] **步骤2.2: 提交代码**

```bash
git add vnpy/stockai/data_drawer.py
git commit -m "feat(stockai): 实现 StockaiDataDrawer 数据抽屉"
```

---

## 任务3: 实现 StockaiDataKitchen（数据厨房）

**涉及文件:**
- 新建: `vnpy/stockai/data_kitchen.py`

**功能说明:**
StockaiDataKitchen 是单只股票的数据管理单元，负责：
- 加载和管理单只股票的数据
- 识别特征列（%-前缀）和标签列（&-前缀）
- 分割训练集和测试集
- 管理特征管道和标签管道

生命周期：临时对象，每次训练或预测时创建

- [ ] **步骤3.1: 编写 data_kitchen.py**

```python
"""StockAI 数据厨房 - 单只股票数据管理"""

import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional, Type

import numpy as np
import polars as pl
from sklearn.model_selection import train_test_split

logger = logging.getLogger(__name__)


class StockaiDataKitchen:
    """
    单只股票数据管理单元
    
    职责:
    - 加载和管理一只股票的数据
    - 过滤特征列（%-前缀）和标签列（&-前缀）
    - 分割训练集和测试集
    - 管理特征管道和标签管道
    
    对应 FreqAI 的 FreqaiDataKitchen 类
    """

    def __init__(self, config: dict, pair: str, lab: Any):
        """
        初始化数据厨房
        
        参数:
            config: 配置字典
            pair: 股票代码
            lab: AlphaLabV2 实例
        """
        self.config = config
        self.pair = pair
        self.lab = lab
        
        # 路径
        self.data_path = Path()
        
        # 数据存储
        self.data_dictionary: dict[str, Any] = {}
        self.full_df: pl.DataFrame = pl.DataFrame()
        
        # 管道对象
        self.feature_pipeline: Optional[Any] = None
        self.label_pipeline: Optional[Any] = None
        
        # 特征和标签列名列表
        self.training_features_list: list[str] = []
        self.label_list: list[str] = []
        
        # 训练/测试时间段
        self.train_period: tuple[str, str] = ("", "")
        self.test_period: tuple[str, str] = ("", "")
        
        # 模型文件名
        self.model_filename: str = ""
        
        # 额外数据存储
        self.data: dict[str, Any] = {"extra_returns_per_train": {}}

    def load_data(
        self,
        start: str,
        end: str,
        train_period_days: int = 300,
    ) -> pl.DataFrame:
        """
        从 lab 加载数据
        
        参数:
            start: 测试期开始日期
            end: 测试期结束日期
            train_period_days: 训练期天数（从start往前推）
            
        返回:
            加载的DataFrame
        """
        # 计算时间段
        start_dt = datetime.strptime(start, "%Y-%m-%d")
        train_start_dt = start_dt - timedelta(days=train_period_days)
        train_start = train_start_dt.strftime("%Y-%m-%d")
        
        self.train_period = (train_start, start)
        self.test_period = (start, end)
        
        # 从 lab 加载数据
        df = self.lab.load_bars_df(
            symbols=[self.pair],
            interval=self.lab.config.get("interval", "d"),
            start=train_start,
            end=end,
        )
        
        if df is None or len(df) == 0:
            raise ValueError(f"{self.pair}: 未能加载数据")
        
        self.full_df = df
        logger.info(f"{self.pair}: 已加载 {len(df)} 行数据")
        
        return df

    def filter_features(
        self,
        df: pl.DataFrame,
        training_filter: bool = False,
    ) -> tuple[pl.DataFrame, pl.DataFrame]:
        """
        过滤特征和标签
        
        特征列: %-前缀
        标签列: &-前缀
        
        参数:
            df: 输入DataFrame
            training_filter: 是否用于训练过滤
            
        返回:
            (特征DataFrame, 标签DataFrame)
        """
        # 识别列
        feature_cols = [c for c in df.columns if c.startswith("%-")]
        label_cols = [c for c in df.columns if c.startswith("&")]
        
        if not feature_cols:
            raise ValueError("未找到特征列（需要%-前缀）")
        if not label_cols:
            raise ValueError("未找到标签列（需要&-前缀）")
        
        self.training_features_list = feature_cols
        self.label_list = label_cols
        
        # 提取数据
        features_df = df.select(feature_cols)
        labels_df = df.select(label_cols)
        
        # 处理缺失值
        features_df = features_df.fill_null(0.0)
        labels_df = labels_df.fill_null(0.0)
        
        logger.info(f"{self.pair}: 特征 {len(feature_cols)} 列，标签 {len(label_cols)} 列")
        
        return features_df, labels_df

    def make_train_test_datasets(
        self,
        features: pl.DataFrame,
        labels: pl.DataFrame,
    ) -> dict[str, Any]:
        """
        分割训练集和测试集
        
        参数:
            features: 特征DataFrame
            labels: 标签DataFrame
            
        返回:
            包含训练/测试数据的字典
        """
        # 转换为 numpy
        X = features.to_numpy()
        y = labels.to_numpy().ravel() if labels.shape[1] == 1 else labels.to_numpy()
        
        # 分割参数
        test_size = self.config.get("data_split_parameters", {}).get("test_size", 0.2)
        shuffle = self.config.get("data_split_parameters", {}).get("shuffle", False)
        
        # 分割数据
        if test_size > 0:
            X_train, X_test, y_train, y_test = train_test_split(
                X, y, test_size=test_size, shuffle=shuffle
            )
        else:
            X_train, y_train = X, y
            X_test, y_test = np.array([]), np.array([])
        
        self.data_dictionary = {
            "train_features": X_train,
            "train_labels": y_train,
            "test_features": X_test,
            "test_labels": y_test,
        }
        
        logger.info(f"{self.pair}: 训练集 {len(X_train)}，测试集 {len(X_test)}")
        
        return self.data_dictionary
```

- [ ] **步骤3.2: 提交代码**

```bash
git add vnpy/stockai/data_kitchen.py
git commit -m "feat(stockai): 实现 StockaiDataKitchen 数据厨房"
```

---

## 任务4: 实现 IStockaiModel（模型接口）

**涉及文件:**
- 新建: `vnpy/stockai/stockai_interface.py`

**功能说明:**
IStockaiModel 是所有模型的抽象基类，定义了训练(train)和预测(predict)接口。子类需要实现这两个方法。

- [ ] **步骤4.1: 编写 stockai_interface.py**

```python
"""StockAI 模型接口基类"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import polars as pl

from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen

logger = logging.getLogger(__name__)


class IStockaiModel(ABC):
    """
    所有StockAI模型的抽象基类
    
    对应 FreqAI 的 IFreqaiModel 类
    
    职责:
    - 定义训练和预测的抽象接口
    - 管理全局 DataDrawer（持久化存储）
    - 创建 DataKitchen（临时数据管理）
    """

    def __init__(self, config: dict, lab: Any):
        """
        初始化模型接口
        
        参数:
            config: 配置字典
            lab: AlphaLabV2 实例
        """
        self.config = config
        self.lab = lab
        
        # 设置路径
        self.full_path = Path(config.get("path", "./stockai_data"))
        self.full_path.mkdir(parents=True, exist_ok=True)
        
        # 初始化全局数据抽屉
        self.dd = StockaiDataDrawer(self.full_path, config)
        
        # 当前数据厨房（临时）
        self.dk: Optional[StockaiDataKitchen] = None
        
        # 模型引用
        self.model: Optional[Any] = None
        
        # 特征参数
        self.ft_params = config.get("feature_parameters", {})
        
        logger.info(f"模型接口初始化完成，路径: {self.full_path}")

    def get_data_kitchen(self, pair: str) -> StockaiDataKitchen:
        """获取或创建数据厨房"""
        return StockaiDataKitchen(self.config, pair, self.lab)

    @abstractmethod
    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        训练模型（子类必须实现）
        
        参数:
            df: 训练数据
            pair: 股票代码
            dk: 数据厨房
            
        返回:
            训练好的模型对象
        """
        pass

    @abstractmethod
    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """
        预测（子类必须实现）
        
        参数:
            df: 输入数据
            dk: 数据厨房
            
        返回:
            预测结果DataFrame
        """
        pass

    def start_training(
        self,
        pair: str,
        start: str,
        end: str,
    ) -> Any:
        """
        高层训练入口
        
        参数:
            pair: 股票代码
            start: 测试期开始
            end: 测试期结束
            
        返回:
            训练好的模型
        """
        # 创建数据厨房
        dk = self.get_data_kitchen(pair)
        self.dk = dk
        
        # 加载数据
        df = dk.load_data(
            start=start,
            end=end,
            train_period_days=self.config.get("train_period_days", 300),
        )
        
        # 训练
        model = self.train(df, pair, dk)
        self.model = model
        
        return model

    def start_prediction(
        self,
        pair: str,
        start: str,
        end: str,
    ) -> pl.DataFrame:
        """
        高层预测入口
        
        参数:
            pair: 股票代码
            start: 预测期开始
            end: 预测期结束
            
        返回:
            预测结果
        """
        # 创建数据厨房
        dk = self.get_data_kitchen(pair)
        self.dk = dk
        
        # 加载数据
        df = dk.load_data(
            start=start,
            end=end,
            train_period_days=0,  # 预测不需要训练数据
        )
        
        # 预测
        predictions = self.predict(df, dk)
        
        # 保存到历史
        self.dd.append_predictions(pair, predictions)
        
        return predictions
```

- [ ] **步骤4.2: 提交代码**

```bash
git add vnpy/stockai/stockai_interface.py
git commit -m "feat(stockai): 实现 IStockaiModel 模型接口基类"
```

---

## 任务5: 实现 BaseRegressionModel（回归模型基类）

**涉及文件:**
- 新建: `vnpy/stockai/base_models/base_regression_model.py`

**功能说明:**
BaseRegressionModel 是回归模型的具体基类，实现了通用的训练和预测流程。子类只需实现 fit() 方法。

训练流程：
1. 过滤特征和标签
2. 分割训练/测试集
3. 定义管道
4. 拟合管道
5. 转换数据
6. 训练模型
7. 保存模型

预测流程：
1. 过滤特征
2. 加载管道和模型
3. 转换特征
4. 预测
5. 反向转换
6. 构建结果

- [ ] **步骤5.1: 编写 base_regression_model.py**

```python
"""StockAI 回归模型基类"""

import logging
from abc import abstractmethod
from typing import Any

import joblib
import numpy as np
import polars as pl
from sklearn.preprocessing import MinMaxScaler, StandardScaler
from sklearn.pipeline import Pipeline

from ..data_kitchen import StockaiDataKitchen
from ..stockai_interface import IStockaiModel
from ..utils import get_timestamp

logger = logging.getLogger(__name__)


class BaseRegressionModel(IStockaiModel):
    """
    回归模型基类
    
    实现了通用的训练和预测流程
    子类只需要实现 fit() 方法
    """

    def train(
        self,
        df: pl.DataFrame,
        pair: str,
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        通用训练流程
        
        步骤:
        1. 过滤特征和标签
        2. 分割训练/测试集
        3. 定义管道
        4. 拟合管道
        5. 转换数据
        6. 训练模型
        7. 保存模型
        """
        logger.info(f"开始训练: {pair}")
        
        # 1. 过滤特征
        features, labels = dk.filter_features(df, training_filter=True)
        
        # 2. 分割数据
        data_dict = dk.make_train_test_datasets(features, labels)
        
        # 3. 定义管道
        dk.feature_pipeline = self.define_feature_pipeline()
        dk.label_pipeline = self.define_label_pipeline()
        
        # 4. 拟合管道
        dk.feature_pipeline.fit(data_dict["train_features"])
        dk.label_pipeline.fit(data_dict["train_labels"].reshape(-1, 1))
        
        # 5. 转换数据
        X_train = dk.feature_pipeline.transform(data_dict["train_features"])
        y_train = dk.label_pipeline.transform(
            data_dict["train_labels"].reshape(-1, 1)
        ).ravel()
        
        data_dict["train_features"] = X_train
        data_dict["train_labels"] = y_train
        
        if len(data_dict["test_features"]) > 0:
            X_test = dk.feature_pipeline.transform(data_dict["test_features"])
            y_test = dk.label_pipeline.transform(
                data_dict["test_labels"].reshape(-1, 1)
            ).ravel()
            data_dict["test_features"] = X_test
            data_dict["test_labels"] = y_test
        
        # 6. 训练模型
        logger.info(f"训练: {len(X_train)} 样本, {X_train.shape[1]} 特征")
        model = self.fit(data_dict, dk)
        
        # 7. 保存模型
        timestamp = get_timestamp()
        self.dd.save_model(pair, model, timestamp)
        self._save_pipelines(pair, timestamp, dk)
        
        logger.info(f"训练完成: {pair}")
        
        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """
        通用预测流程
        
        步骤:
        1. 过滤特征
        2. 加载管道和模型
        3. 转换特征
        4. 预测
        5. 反向转换
        6. 构建结果
        """
        pair = dk.pair
        
        # 1. 过滤特征
        features, _ = dk.filter_features(df)
        
        # 2. 加载
        self._load_pipelines(pair, dk)
        model = self.dd.load_model(pair)
        
        # 3. 转换
        X = dk.feature_pipeline.transform(features.to_numpy())
        
        # 4. 预测
        predictions = model.predict(X)
        
        # 5. 反向转换
        predictions = dk.label_pipeline.inverse_transform(
            predictions.reshape(-1, 1)
        ).ravel()
        
        # 6. 构建结果
        result = pl.DataFrame({
            "datetime": df["datetime"],
            "pair": pair,
            "prediction": predictions,
        })
        
        logger.info(f"预测完成: {pair}, {len(result)} 样本")
        
        return result

    @abstractmethod
    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> Any:
        """
        训练模型（子类必须实现）
        
        参数:
            data_dictionary: 包含训练/测试数据的字典
            dk: 数据厨房
            
        返回:
            训练好的模型
        """
        pass

    def define_feature_pipeline(self) -> Pipeline:
        """定义特征处理管道（可覆盖）"""
        return Pipeline([
            ("scaler", StandardScaler()),
        ])

    def define_label_pipeline(self) -> Pipeline:
        """定义标签处理管道（可覆盖）"""
        return Pipeline([
            ("scaler", MinMaxScaler(feature_range=(-1, 1))),
        ])

    def _save_pipelines(
        self,
        pair: str,
        timestamp: int,
        dk: StockaiDataKitchen,
    ) -> None:
        """保存管道"""
        filename = self.dd._generate_model_filename(pair, timestamp)
        model_path = self.dd.full_path / filename
        
        if dk.feature_pipeline:
            joblib.dump(dk.feature_pipeline, model_path / "feature_pipeline.pkl")
        if dk.label_pipeline:
            joblib.dump(dk.label_pipeline, model_path / "label_pipeline.pkl")

    def _load_pipelines(self, pair: str, dk: StockaiDataKitchen) -> None:
        """加载管道"""
        filename = self.dd.pair_dict[pair]["model_filename"]
        model_path = self.dd.full_path / filename
        
        fp_path = model_path / "feature_pipeline.pkl"
        lp_path = model_path / "label_pipeline.pkl"
        
        if fp_path.exists():
            dk.feature_pipeline = joblib.load(fp_path)
        if lp_path.exists():
            dk.label_pipeline = joblib.load(lp_path)
```

- [ ] **步骤5.2: 提交代码**

```bash
git add vnpy/stockai/base_models/base_regression_model.py
git commit -m "feat(stockai): 实现 BaseRegressionModel 回归模型基类"
```

---

## 任务6: 实现 XGBoostExtremaModel（XGBoost极值模型）

**涉及文件:**
- 新建: `vnpy/stockai/prediction_models/xgb_extrema_model.py`

**功能说明:**
XGBoostExtremaModel 是具体的模型实现，包含：
- XGBoost 训练
- 渐进式阈值计算（FreqAI V5风格）
- 动态阈值混合（默认阈值 + 动态阈值）
- DI cutoff 计算（Weibull分布）

- [ ] **步骤6.1: 编写 xgb_extrema_model.py**

```python
"""StockAI XGBoost 极值预测模型"""

import logging
from typing import Any, Tuple

import numpy as np
import polars as pl
import scipy.stats
from xgboost import XGBRegressor

from ..base_models.base_regression_model import BaseRegressionModel
from ..data_kitchen import StockaiDataKitchen

logger = logging.getLogger(__name__)


class XGBoostExtremaModel(BaseRegressionModel):
    """
    XGBoost 极值预测模型
    
    特性:
    - 渐进式阈值预热
    - 动态阈值计算
    - DI异常检测
    """

    # 默认阈值
    DEFAULT_MAXIMA_THRESHOLD = 2.0
    DEFAULT_MINIMA_THRESHOLD = -2.0
    DEFAULT_DI_CUTOFF = 2.0
    MIN_CANDLES_FOR_DYNAMIC = 50

    def __init__(self, config: dict, lab: Any):
        super().__init__(config, lab)
        
        # 模型参数
        self.model_params = config.get("model_training_parameters", {})
        
        # 特征参数
        self.num_candles = self.ft_params.get("num_candles", 200)
        self.label_period_candles = self.ft_params.get("label_period_candles", 10)

    def fit(
        self,
        data_dictionary: dict[str, Any],
        dk: StockaiDataKitchen,
    ) -> XGBRegressor:
        """训练 XGBoost 模型"""
        X = data_dictionary["train_features"]
        y = data_dictionary["train_labels"]
        
        # 模型参数
        params = {
            "learning_rate": self.model_params.get("learning_rate", 0.05),
            "max_depth": self.model_params.get("max_depth", 6),
            "n_estimators": self.model_params.get("n_estimators", 100),
            "early_stopping_rounds": self.model_params.get("early_stopping_rounds", 50),
            "objective": "reg:squarederror",
            "random_state": 42,
        }
        
        model = XGBRegressor(**params)
        
        # 如果有测试集，使用早停
        if len(data_dictionary.get("test_features", [])) > 0:
            model.fit(
                X=X, y=y,
                eval_set=[(data_dictionary["test_features"], data_dictionary["test_labels"])],
                verbose=False,
            )
        else:
            model.fit(X=X, y=y)
        
        logger.info(f"XGBoost 训练完成: best_iteration={model.best_iteration}")
        
        return model

    def predict(
        self,
        df: pl.DataFrame,
        dk: StockaiDataKitchen,
    ) -> pl.DataFrame:
        """
        预测（带动态阈值）
        
        步骤:
        1. 基础预测
        2. 计算动态阈值
        3. 添加阈值列
        """
        # 基础预测
        result = super().predict(df, dk)
        
        # 计算阈值
        self._compute_thresholds(dk, result)
        
        # 添加阈值列
        extra = dk.data.get("extra_returns_per_train", {})
        result = result.with_columns([
            pl.lit(extra.get("maxima_threshold", self.DEFAULT_MAXIMA_THRESHOLD))
            .alias("maxima_threshold"),
            pl.lit(extra.get("minima_threshold", self.DEFAULT_MINIMA_THRESHOLD))
            .alias("minima_threshold"),
            pl.lit(extra.get("di_cutoff", self.DEFAULT_DI_CUTOFF))
            .alias("di_cutoff"),
        ])
        
        return result

    def _compute_thresholds(
        self,
        dk: StockaiDataKitchen,
        predictions: pl.DataFrame,
    ) -> None:
        """计算动态阈值"""
        pair = dk.pair
        
        # 获取历史预测
        hist_df = self.dd.get_historic_predictions(pair)
        if hist_df is None:
            hist_df = predictions
        else:
            hist_df = pl.concat([hist_df, predictions])
        
        # 计算预热进度
        n_candles = len(hist_df)
        warmup_progress = min(1.0, n_candles / self.num_candles)
        
        # 获取近期预测用于阈值计算
        recent_df = hist_df.tail(self.num_candles)
        
        # 计算阈值
        maxima, minima = self._compute_progressive_thresholds(
            recent_df, warmup_progress
        )
        di_cutoff, di_params = self._compute_progressive_di_cutoff(
            recent_df, warmup_progress
        )
        
        # 存储到数据厨房
        dk.data["extra_returns_per_train"] = {
            "maxima_threshold": maxima,
            "minima_threshold": minima,
            "di_cutoff": di_cutoff,
            "di_param1": di_params[0],
            "di_param2": di_params[1],
            "di_param3": di_params[2],
        }
        
        logger.info(
            f"{pair}: 阈值计算完成 (maxima={maxima:.3f}, minima={minima:.3f}, "
            f"di_cutoff={di_cutoff:.3f}, 进度={warmup_progress:.1%})"
        )

    def _compute_progressive_thresholds(
        self,
        pred_df: pl.DataFrame,
        warmup_progress: float,
    ) -> Tuple[float, float]:
        """计算渐进式阈值（混合默认和动态）"""
        # 默认值
        default_max = self.DEFAULT_MAXIMA_THRESHOLD
        default_min = self.DEFAULT_MINIMA_THRESHOLD
        
        # 数据不足，使用默认值
        if len(pred_df) < self.MIN_CANDLES_FOR_DYNAMIC:
            return default_max, default_min
        
        # 计算动态阈值
        frequency = max(1, int(self.num_candles / (self.label_period_candles * 2)))
        frequency = min(frequency, len(pred_df))
        
        predictions = pred_df["prediction"].to_numpy()
        sorted_preds = np.sort(predictions)[::-1]
        
        dynamic_max = float(np.mean(sorted_preds[:frequency]))
        dynamic_min = float(np.mean(sorted_preds[-frequency:]))
        
        # 混合（根据预热进度）
        maxima = default_max * (1 - warmup_progress) + dynamic_max * warmup_progress
        minima = default_min * (1 - warmup_progress) + dynamic_min * warmup_progress
        
        return maxima, minima

    def _compute_progressive_di_cutoff(
        self,
        pred_df: pl.DataFrame,
        warmup_progress: float,
    ) -> Tuple[float, Tuple[float, float, float]]:
        """使用Weibull分布计算DI截止值"""
        default = self.DEFAULT_DI_CUTOFF
        default_params = (0.0, 0.0, 0.0)
        
        if len(pred_df) < self.MIN_CANDLES_FOR_DYNAMIC:
            return default, default_params
        
        if "di_values" not in pred_df.columns:
            return default, default_params
        
        try:
            di_values = pred_df["di_values"].to_numpy()
            di_values = di_values[~np.isnan(di_values)]
            
            if len(di_values) < 10:
                return default, default_params
            
            # 拟合Weibull分布
            params = scipy.stats.weibull_min.fit(di_values)
            dynamic = float(scipy.stats.weibull_min.ppf(0.999, *params))
            
            # 混合
            cutoff = default * (1 - warmup_progress) + dynamic * warmup_progress
            blended = tuple(
                default_params[i] * (1 - warmup_progress) + params[i] * warmup_progress
                for i in range(3)
            )
            
            return cutoff, blended
            
        except Exception as e:
            logger.warning(f"DI截止值计算失败: {e}")
            return default, default_params
```

- [ ] **步骤6.2: 提交代码**

```bash
git add vnpy/stockai/prediction_models/xgb_extrema_model.py
git commit -m "feat(stockai): 实现 XGBoostExtremaModel 极值预测模型"
```

---

## 任务7: 实现模块入口 __init__.py

**涉及文件:**
- 修改: `vnpy/stockai/__init__.py`

- [ ] **步骤7.1: 编写 __init__.py**

```python
"""StockAI - FreqAI兼容的股票机器学习预测管道"""

from .data_drawer import StockaiDataDrawer
from .data_kitchen import StockaiDataKitchen
from .stockai_interface import IStockaiModel
from .base_models.base_regression_model import BaseRegressionModel
from .prediction_models.xgb_extrema_model import XGBoostExtremaModel

__version__ = "0.1.0"

__all__ = [
    "StockaiDataDrawer",      # 数据抽屉 - 全局存储
    "StockaiDataKitchen",     # 数据厨房 - 单只股票数据
    "IStockaiModel",          # 模型接口基类
    "BaseRegressionModel",    # 回归模型基类
    "XGBoostExtremaModel",    # XGBoost实现
]
```

- [ ] **步骤7.2: 最终提交**

```bash
git add vnpy/stockai/__init__.py
git commit -m "feat(stockai): 完成模块导出"
```

---

## 使用示例

### 配置

```json
{
    "stockai": {
        "path": "./stockai_data",
        "feature_parameters": {
            "num_candles": 200,
            "label_period_candles": 10
        },
        "model_training_parameters": {
            "learning_rate": 0.05,
            "max_depth": 6,
            "n_estimators": 100
        },
        "data_split_parameters": {
            "test_size": 0.2,
            "shuffle": false
        },
        "train_period_days": 300
    }
}
```

### 代码

```python
from vnpy.stockai import XGBoostExtremaModel

# 初始化
config = load_config("config.json")
model = XGBoostExtremaModel(config["stockai"], lab)

# 训练
model.start_training("000001.SZSE", "2025-01-01", "2025-06-01")

# 预测
predictions = model.start_prediction("000001.SZSE", "2025-06-01", "2025-12-31")

# 查询历史
history = model.dd.get_historic_predictions("000001.SZSE")
```

---

## 总结

**已完成文件:**
1. `vnpy/stockai/utils.py` - 工具函数
2. `vnpy/stockai/data_drawer.py` - 全局存储
3. `vnpy/stockai/data_kitchen.py` - 单只股票数据
4. `vnpy/stockai/stockai_interface.py` - 模型接口
5. `vnpy/stockai/base_models/base_regression_model.py` - 回归基类
6. `vnpy/stockai/prediction_models/xgb_extrema_model.py` - XGB实现
7. `vnpy/stockai/__init__.py` - 模块入口

**与FreqAI对应关系:**
| FreqAI | StockAI |
|--------|---------|
| IFreqaiModel | IStockaiModel |
| FreqaiDataKitchen | StockaiDataKitchen |
| FreqaiDataDrawer | StockaiDataDrawer |
| BaseRegressionModel | BaseRegressionModel |
| XGBoostRegressor | XGBoostExtremaModel |
