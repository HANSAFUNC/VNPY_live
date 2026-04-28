# BaseAlphaLab + AlphaLabV2Engine 实施计划

> **来源:** docs/superpowers/specs/2026-04-28-basealphalab-design.md  
> **日期:** 2026-04-28

---

## Task 1: 创建 vnpy/alpha/base.py

**目标:** 实现 BaseAlphaLab 抽象基类

**步骤:**
1. 创建新文件 `vnpy/alpha/base.py`
2. 定义抽象基类 `BaseAlphaLab(ABC)`
3. 实现所有抽象方法声明（数据查询、数据更新）
4. 实现通用工具方法（_to_datetime, _normalize_symbol, _bar_to_dict, _dict_to_bar, _ensure_path）

**验证:**
```python
from vnpy.alpha.base import BaseAlphaLab
assert hasattr(BaseAlphaLab, 'load_bars')
assert hasattr(BaseAlphaLab, 'update_daily_data')
print("BaseAlphaLab OK")
```

---

## Task 2: 修改 vnpy/alpha/lab.py

**目标:** 让旧版 AlphaLab 继承 BaseAlphaLab

**步骤:**
1. 修改 `vnpy/alpha/lab.py`
2. 添加 `from .base import BaseAlphaLab`
3. 修改类定义 `class AlphaLab(BaseAlphaLab):`
4. 确保所有抽象方法都有实现
5. 验证向后兼容

**验证:**
```python
from vnpy.alpha import AlphaLab
import inspect
assert issubclass(AlphaLab, BaseAlphaLab)
assert 'load_bars' in [m for m, _ in inspect.getmembers(AlphaLab) if not m.startswith('_')]
print("AlphaLab 继承 OK")
```

---

## Task 3: 创建 vnpy/alpha/lab_v2.py

**目标:** 实现 AlphaLabV2Engine

**步骤:**
1. 创建新文件 `vnpy/alpha/lab_v2.py`
2. 继承 `BaseAlphaLab` 和 `BaseEngine`
3. 组合 `DataStore` 和 `IndexManager`
4. 实现所有抽象方法
5. 添加 `engine_name = "AlphaLabV2"`

**验证:**
```python
from vnpy.alpha.lab_v2 import AlphaLabV2Engine
from vnpy.trader.engine import BaseEngine
from vnpy.alpha.base import BaseAlphaLab
assert issubclass(AlphaLabV2Engine, BaseEngine)
assert issubclass(AlphaLabV2Engine, BaseAlphaLab)
assert AlphaLabV2Engine.engine_name == "AlphaLabV2"
print("AlphaLabV2Engine OK")
```

---

## Task 3a: 添加 switch_project 方法

**目标:** 在 AlphaLabV2Engine 中实现项目切换功能

**步骤:**
1. 在 `lab_v2.py` 中添加 `EVENT_PROJECT_SWITCHED = "eProjectSwitched"` 常量
2. 实现 `switch_project()` 方法
3. 实现 `list_projects()` 方法
4. 在项目目录变更时触发事件

**代码要点:**
```python
def switch_project(self, project_name, index_code=None, data_source=None):
    old_project = self.project_name
    
    # 更新配置
    self.project_name = project_name
    if index_code:
        self.index_code = index_code
    if data_source:
        self.data_source = data_source
        self.data_store = DataStore(str(self.root), self.data_source)
    
    # 更新项目目录
    self.project_path = self.root / "project" / project_name
    # ... 创建子目录
    
    # 触发事件
    self.event_engine.put(Event(EVENT_PROJECT_SWITCHED, {...}))
    
    return {"success": True, ...}
```

**验证:**
```python
result = lab.switch_project("lasso_csi500", index_code="csi500")
assert result["success"]
assert lab.project_name == "lasso_csi500"
assert lab.index_code == "csi500"
```

---

## Task 4: 更新 vnpy/alpha/__init__.py

**目标:** 导出新类

**步骤:**
1. 修改 `vnpy/alpha/__init__.py`
2. 添加 `from .base import BaseAlphaLab`
3. 添加 `from .lab_v2 import AlphaLabV2Engine`
4. 更新 `__all__` 列表

**验证:**
```python
from vnpy.alpha import BaseAlphaLab, AlphaLabV2Engine
print("导入 OK")
```

---

## Task 5: 测试验证

**目标:** 确保旧版兼容性和新版功能

**步骤:**
1. **向后兼容测试**
   ```python
   from vnpy.alpha import AlphaLab
   lab = AlphaLab("./test_lab")
   assert hasattr(lab, 'load_bars')
   assert hasattr(lab, 'save_bars')
   ```

2. **新版引擎测试**
   ```python
   from vnpy.event import EventEngine
   from vnpy.trader.engine import MainEngine
   from vnpy.alpha import AlphaLabV2Engine
   
   event_engine = EventEngine()
   main_engine = MainEngine(event_engine)
   
   lab = AlphaLabV2Engine(
       main_engine=main_engine,
       event_engine=event_engine,
       root_path="./test_lab_v2",
       project_name="test",
       data_source="xt",
       index_code="csi300"
   )
   
   main_engine.add_engine(lab)
   assert main_engine.get_engine("AlphaLabV2") is lab
   ```

3. **项目切换测试**
   ```python
   # 测试 switch_project
   result = lab.switch_project("test_project_2", index_code="csi500")
   assert result["success"]
   assert lab.project_name == "test_project_2"
   assert lab.index_code == "csi500"
   
   # 测试 list_projects
   projects = lab.list_projects()
   assert "test_project" in projects
   assert "test_project_2" in projects
   print("Project switch OK")
   ```

4. **接口一致性测试**
   ```python
   from vnpy.alpha import AlphaLab, AlphaLabV2Engine, BaseAlphaLab
   from inspect import signature
   
   # 检查方法签名一致
   old_sig = signature(AlphaLab.load_bars)
   new_sig = signature(AlphaLabV2Engine.load_bars)
   assert str(old_sig) == str(new_sig)
   ```

**验证:**
```bash
cd F:/vnpy_live
python -c "
from vnpy.alpha import AlphaLab, AlphaLabV2Engine, BaseAlphaLab
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine

# 基础导入测试
assert issubclass(AlphaLab, BaseAlphaLab)
assert issubclass(AlphaLabV2Engine, BaseAlphaLab)
print('Imports OK')

# 项目切换测试
event_engine = EventEngine()
main_engine = MainEngine(event_engine)
lab = AlphaLabV2Engine(
    main_engine=main_engine,
    event_engine=event_engine,
    root_path='./test_lab',
    project_name='test',
    data_source='xt',
    index_code='csi300'
)
result = lab.switch_project('test2', index_code='csi500')
assert result['success']
assert lab.project_name == 'test2'
assert lab.index_code == 'csi500'
print('Switch project OK')

print('All tests passed!')
"
```

---

## 依赖关系

```
Task 1 (base.py)
    │
    ├──► Task 2 (lab.py 继承) ──► Task 5 (测试)
    │
    └──► Task 3 (lab_v2.py) ──► Task 3a (switch_project) ──► Task 4 (导出) ──► Task 5 (测试)
```

---

## 实施命令

```bash
# Task 1: 创建 base.py
# (写入文件 vnpy/alpha/base.py)

# Task 2: 修改 lab.py
# (修改文件 vnpy/alpha/lab.py)

# Task 3: 创建 lab_v2.py
# (写入文件 vnpy/alpha/lab_v2.py)

# Task 3a: 添加 switch_project 方法
# (在 lab_v2.py 中实现 switch_project 和 list_projects)

# Task 4: 更新 __init__.py
# (修改文件 vnpy/alpha/__init__.py)

# Task 5: 测试
python -c "
from vnpy.alpha import AlphaLab, AlphaLabV2Engine, BaseAlphaLab
from vnpy.trader.engine import BaseEngine
print('Imports OK')

# 验证继承
assert issubclass(AlphaLab, BaseAlphaLab)
assert issubclass(AlphaLabV2Engine, BaseAlphaLab)
assert issubclass(AlphaLabV2Engine, BaseEngine)
print('Inheritance OK')

# 验证 engine_name
assert AlphaLabV2Engine.engine_name == 'AlphaLabV2'
print('Engine name OK')

print('All tests passed!')
"
```

---

## 最终提交

```bash
git add vnpy/alpha/
git commit -m "feat(alpha): add BaseAlphaLab abstract base class and AlphaLabV2Engine

- Create BaseAlphaLab with unified data interface
- AlphaLab inherits BaseAlphaLab for backward compatibility
- AlphaLabV2Engine inherits BaseEngine + BaseAlphaLab
- V2 combines DataStore + IndexManager for layered architecture
- Support registration to MainEngine"
```

---

**计划完成，准备实施。**
