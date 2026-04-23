"""分组多模型包装器 - 为每个分组训练独立的模型。"""

from typing import Any, Callable

import numpy as np
import polars as pl

from vnpy.alpha.dataset import AlphaDataset, Segment
from vnpy.alpha.model import AlphaModel


class FilteredDataset(AlphaDataset):
    """过滤后的数据集包装器。

    允许使用数据的子集（例如按组过滤）与现有的 AlphaModel 实现一起使用。
    """

    def __init__(
        self,
        train_df: pl.DataFrame | None = None,
        valid_df: pl.DataFrame | None = None,
        infer_df: pl.DataFrame | None = None,
        original_dataset: AlphaDataset | None = None,
    ) -> None:
        """初始化 FilteredDataset。

        参数
        ----------
        train_df : pl.DataFrame, optional
            训练数据 DataFrame
        valid_df : pl.DataFrame, optional
            验证数据 DataFrame
        infer_df : pl.DataFrame, optional
            推理数据 DataFrame
        original_dataset : AlphaDataset, optional
            原始数据集，用于继承特征信息
        """
        # 注意：不调用 super().__init__()，因为我们直接提供预计算的 DataFrame
        self._train_df = train_df
        self._valid_df = valid_df
        self._infer_df = infer_df
        self._original_dataset = original_dataset

        # 从原始数据集复制特征信息（如果可用）
        if original_dataset:
            self._feature_names = getattr(original_dataset, '_feature_names', None)
            self._label_col = getattr(original_dataset, '_label_col', None)
        else:
            self._feature_names = None
            self._label_col = None

    def fetch_learn(self, segment: Segment) -> pl.DataFrame:
        """获取用于学习的数据（训练/验证）。

        参数
        ----------
        segment : Segment
            要获取的数据段（TRAIN 或 VALID）

        返回
        -------
        pl.DataFrame
            指定段的数据
        """
        if segment == Segment.TRAIN:
            return self._train_df
        elif segment == Segment.VALID:
            return self._valid_df
        raise ValueError(f"不支持的数据段：{segment}")

    def fetch_infer(self, segment: Segment) -> pl.DataFrame:
        """获取用于推理的数据。

        参数
        ----------
        segment : Segment
            要获取的数据段（TEST 用于推理）

        返回
        -------
        pl.DataFrame
            推理数据
        """
        return self._infer_df

    def prepare_data(self, *args, **kwargs) -> None:
        """无需操作：数据已准备好。"""
        pass

    def process_data(self, *args, **kwargs) -> None:
        """无需操作：数据已处理。"""
        pass


class GroupedMultiModel(AlphaModel):
    """分组多模型包装器 - 为每个分组训练独立的模型。

    此包装器允许为不同的分组训练独立的模型
    （例如，每只股票、每个行业、每个板块）。每个分组获得一个
    仅在该分组数据上训练的模型。

    特性：
    - 按任何 DataFrame 列灵活分组
    - 可选全局模型用于合成完整结果
    - 可配置的每组最小样本数
    - 限制最大分组数量（用于内存控制）

    示例
    -------
    >>> # 每只股票训练一个模型
    >>> model = GroupedMultiModel(
    ...     model_factory=lambda: XGBoostExtremaModel(learning_rate=0.1),
    ...     group_by="vt_symbol",
    ...     min_samples_per_group=100
    ... )
    >>> model.fit(dataset)
    >>> predictions = model.predict(dataset, Segment.TEST)

    >>> # 每个行业训练一个模型
    >>> model = GroupedMultiModel(
    ...     model_factory=lambda: XGBoostExtremaModel(),
    ...     group_by="industry"
    ... )
    >>> model.fit(dataset)

    >>> # 每个（行业，市值）组合训练一个模型
    >>> model = GroupedMultiModel(
    ...     model_factory=lambda: XGBoostExtremaModel(),
    ...     group_by=["industry", "market_cap_bucket"]
    ... )
    >>> model.fit(dataset)
    """

    def __init__(
        self,
        model_factory: Callable[[], AlphaModel],
        group_by: str | list[str] = "vt_symbol",
        max_groups: int | None = None,
        min_samples_per_group: int = 100,
        train_global_model: bool = False,
    ) -> None:
        """初始化 GroupedMultiModel。

        参数
        ----------
        model_factory : Callable[[], AlphaModel]
            创建新 AlphaModel 实例的工厂函数。
            必须是无参可调用的。
        group_by : str | list[str], optional
            用于分组的列名。默认是 "vt_symbol"。
            可以是单个列名或列名列表。
        max_groups : int | None, optional
            要训练模型的最大分组数。
            如果为 None，则训练所有分组。
        min_samples_per_group : int, optional
            训练分组模型所需的最小样本数。
            样本少于该值的分组将被跳过。
            默认是 100。
        train_global_model : bool, optional
            是否训练全局模型。
            如果为 True，则先训练一个全局模型用于合成完整数据集的预测结果。
            如果为 False（默认），则只训练分组模型。
            默认是 False。
        """
        self.model_factory = model_factory
        self.group_by = [group_by] if isinstance(group_by, str) else list(group_by)
        self.max_groups = max_groups
        self.min_samples_per_group = min_samples_per_group
        self.train_global_model = train_global_model

        # 模型存储
        self.models_: dict[str, AlphaModel] = {}
        self.global_model_: AlphaModel | None = None
        self._group_result_dfs: dict[str, pl.DataFrame] = {}

    def __getstate__(self) -> dict:
        """自定义 pickle 序列化 - 排除 model_factory。"""
        state = self.__dict__.copy()
        # 移除 model_factory，因为它可能是 lambda（不可 pickle）
        state['model_factory'] = None
        return state

    def __setstate__(self, state: dict) -> None:
        """自定义 pickle 反序列化。"""
        self.__dict__.update(state)
        # model_factory 在训练后不需要，保持为 None

    def _build_filter_expr(self, group_values: dict[str, Any]) -> pl.Expr:
        """从分组值构建 polars 过滤表达式。

        参数
        ----------
        group_values : dict[str, Any]
            将列名映射到值的字典

        返回
        -------
        pl.Expr
            用于过滤的 Polars 表达式
        """
        exprs = [pl.col(col) == value for col, value in group_values.items()]
        if len(exprs) == 1:
            return exprs[0]
        return pl.all_horizontal(exprs)

    def _make_group_key(self, row: tuple) -> str:
        """从分组值创建字符串键。

        参数
        ----------
        row : tuple
            分组值作为元组（来自 iter_rows()）

        返回
        -------
        str
            分组的字符串键
        """
        return "::".join(str(v) for v in row)

    def _parse_group_key(self, key: str) -> tuple:
        """将字符串键解析回分组值。

        参数
        ----------
        key : str
            由 _make_group_key 创建的字符串键

        返回
        -------
        tuple
            分组值的元组
        """
        return tuple(key.split("::"))

    def fit(self, dataset: AlphaDataset) -> None:
        """为每个分组拟合模型。

        参数
        ----------
        dataset : AlphaDataset
            包含特征和标签的数据集
        """
        print("=" * 60)
        print("开始执行 GroupedMultiModel.fit()")
        print("=" * 60)

        # 1. 获取训练和验证数据
        print("\n[步骤 1] 获取训练和验证数据...")
        df_train = dataset.fetch_learn(Segment.TRAIN).sort(["datetime", "vt_symbol"])
        df_valid = dataset.fetch_learn(Segment.VALID).sort(["datetime", "vt_symbol"])
        print(f"  训练数据：{len(df_train)} 行")
        print(f"  验证数据：{len(df_valid)} 行")

        # 2. 可选：训练全局模型（用于完整数据集合成）
        print(f"\n[步骤 2] 训练全局模型 (train_global_model={self.train_global_model})...")
        if self.train_global_model:
            print("  正在创建并训练全局模型...")
            self.global_model_ = self.model_factory()
            self.global_model_.fit(dataset)
            print("  ✓ 全局模型训练完成")
        else:
            print("  跳过全局模型训练")

        # 3. 获取唯一分组
        print("\n[步骤 3] 获取唯一分组...")
        groups_df = df_train.select(self.group_by).unique()
        groups = list(groups_df.iter_rows(named=False))
        print(f"  共找到 {len(groups)} 个分组")

        # 4. 为每个分组训练模型
        print("\n[步骤 4] 为每个分组训练模型...")
        trained_count = 0
        skipped_count = 0

        for i, row in enumerate(groups):
            # 检查最大分组数限制
            if self.max_groups is not None and i >= self.max_groups:
                print(f"  已达到最大分组数限制 ({self.max_groups})，停止训练")
                break

            # 为该分组构建过滤表达式
            group_values = dict(zip(self.group_by, row))
            filter_expr = self._build_filter_expr(group_values)

            # 过滤该分组的数据
            group_train = df_train.filter(filter_expr)
            group_valid = df_valid.filter(filter_expr)

            # 检查是否有足够的样本
            if len(group_train) < self.min_samples_per_group:
                print(f"  [跳过] {row}: 样本数 {len(group_train)} < {self.min_samples_per_group}")
                skipped_count += 1
                continue

            # 为该分组创建过滤数据集
            group_dataset = FilteredDataset(
                train_df=group_train,
                valid_df=group_valid,
                original_dataset=dataset
            )

            # 打印训练进度
            print(f"  [训练] {i+1}/{len(groups)}: {row} (样本数：{len(group_train)})")

            # 训练该分组的模型
            model = self.model_factory()
            model.fit(group_dataset)

            # 使用分组键存储模型
            group_key = self._make_group_key(row)
            self.models_[group_key] = model

            print(f"  [OK] {row} 训练完成")
            trained_count += 1

        print("\n" + "=" * 60)
        print("训练完成!")
        print(f"  训练模型数：{trained_count}")
        print(f"  跳过模型数：{skipped_count}")
        print(f"  全局模型：{'有' if self.global_model_ else '无'}")
        print("=" * 60)

    def predict(self, dataset: AlphaDataset, segment: Segment) -> np.ndarray:
        """使用分组模型进行预测。

        参数
        ----------
        dataset : AlphaDataset
            用于推理的数据集
        segment : Segment
            要预测的数据段（通常是 TEST）

        返回
        -------
        np.ndarray
            预测数组，与原始数据顺序对齐
        """
        # 1. 获取推理数据
        df = dataset.fetch_infer(segment).sort(["datetime", "vt_symbol"])
        original_order = df.select(["datetime", "vt_symbol"])

        # 2. 对每个分组进行预测
        predictions = []
        for group_key, model in self.models_.items():
            # 解析分组键以获取过滤值
            group_values = self._parse_group_key(group_key)
            group_values_dict = dict(zip(self.group_by, group_values))
            filter_expr = self._build_filter_expr(group_values_dict)

            # 过滤该分组的数据
            group_df = df.filter(filter_expr)
            if len(group_df) == 0:
                continue

            # 为该分组创建过滤数据集
            group_dataset = FilteredDataset(
                infer_df=group_df,
                original_dataset=dataset
            )

            # 进行预测
            group_preds = model.predict(group_dataset, segment)

            # 如果可用，从模型获取 result_df（包含阈值等）
            if hasattr(model, "get_result_df"):
                group_result_df = model.get_result_df()
                if group_result_df is not None:
                    self._group_result_dfs[group_key] = group_result_df

            # 记录带标识符的预测
            for dt, vs, pred in zip(
                group_df["datetime"], group_df["vt_symbol"], group_preds
            ):
                predictions.append((dt, vs, pred))

        # 3. 运行全局模型预测（用于整个数据集）
        if self.global_model_ is not None:
            self.global_model_.predict(dataset, segment)

            # 存储全局模型的 result_df
            if hasattr(self.global_model_, "get_result_df"):
                global_result_df = self.global_model_.get_result_df()
                if global_result_df is not None:
                    self._group_result_dfs["__global__"] = global_result_df

        # 4. 创建预测 DataFrame
        preds_df = pl.DataFrame(
            predictions,
            schema={"datetime": pl.Datetime, "vt_symbol": pl.Utf8, "prediction": pl.Float64},
            orient="row"
        )

        # 5. 左连接以保留所有原始行
        result = original_order.join(preds_df, on=["datetime", "vt_symbol"], how="left")

        # 6. 排序并返回
        result = result.sort(["datetime", "vt_symbol"])
        return result["prediction"].fill_null(0.0).to_numpy()

    def get_results_df(self) -> pl.DataFrame | None:
        """获取所有分组模型的合并结果 DataFrame。

        如果可用则返回全局模型的 result_df（包含完整数据集），
        否则拼接分组级别的 result_dfs。

        返回
        -------
        pl.DataFrame | None
            包含预测和阈值的合并 DataFrame，
            如果没有可用的 result_dfs 则返回 None
        """
        # 优先级 1：返回全局模型的 result_df（覆盖整个数据集）
        if "__global__" in self._group_result_dfs:
            return self._group_result_dfs["__global__"]

        # 优先级 2：拼接所有分组的 result_dfs
        if not self._group_result_dfs:
            return None

        result_dfs = list(self._group_result_dfs.values())
        if len(result_dfs) == 1:
            return result_dfs[0]

        combined = pl.concat(result_dfs)
        return combined.sort(["datetime", "vt_symbol"])

    def get_model(self, group_value: str | tuple) -> AlphaModel | None:
        """获取特定分组的模型。

        参数
        ----------
        group_value : str | tuple
            分组值（单列分组为字符串，多列分组为元组）

        返回
        -------
        AlphaModel | None
            该分组的模型，如果未找到则返回 None
        """
        if isinstance(group_value, tuple):
            key = self._make_group_key(group_value)
        else:
            key = str(group_value)
        return self.models_.get(key)

    def list_groups(self) -> list[str]:
        """列出所有已训练的分组。

        返回
        -------
        list[str]
            分组键列表
        """
        return list(self.models_.keys())


    def detail(self) -> dict:
        """输出模型的详细信息。

        返回
        -------
        dict
            包含模型详细信息的字典
        """
        return {
            "type": "GroupedMultiModel",
            "group_by": self.group_by,
            "num_groups": len(self.models_),
            "has_global_model": self.global_model_ is not None,
            "min_samples_per_group": self.min_samples_per_group,
            "max_groups": self.max_groups,
            "groups": list(self.models_.keys())[:10],  # 前 10 个分组
        }
