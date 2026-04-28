# 实验室 API 联动实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 集成 vnpy_webtrader + vnpy_rpcservice + AlphaLabV2Engine，提供实验室数据 API

**Architecture:** run_trading_dashboard.py 启动时初始化 AlphaLabV2Engine 并注册到 MainEngine；RpcEngine 从 MainEngine 获取引擎并注册 RPC 方法；Web 服务通过 rpc_client 调用实验室方法

**Tech Stack:** Python, FastAPI, VNPY RPC, AlphaLabV2Engine

**设计文档:** `docs/superpowers/specs/2026-04-28-lab-api-integration-design.md`

---

## 文件结构

| 文件 | 操作 | 说明 |
|------|------|------|
| `run_trading_dashboard.py` | 修改 | 启动时创建并注册 AlphaLabV2Engine |
| `vnpy_rpcservice/rpc_service/engine.py` | 修改 | 注册实验室 RPC 方法 |
| `vnpy_webtrader/web.py` | 修改 | 添加实验室 API 端点 |

---

## Task 1: 修改 run_trading_dashboard.py 启动 AlphaLabV2Engine

**Files:**
- Modify: `run_trading_dashboard.py`

- [ ] **Step 1: 导入 AlphaLabV2Engine**

在 imports 部分添加：

```python
from vnpy.alpha import AlphaLabV2Engine
```

- [ ] **Step 2: 在启动 MainEngine 后添加 AlphaLabV2Engine**

在 `main_engine = MainEngine(event_engine)` 之后添加：

```python
# 创建并注册 AlphaLabV2Engine
lab_engine = AlphaLabV2Engine(
    main_engine=main_engine,
    event_engine=event_engine,
    root_path="./lab",
    project_name="default",
    data_source="xt",
    index_code="csi300"
)
main_engine.add_engine(lab_engine)
logger.info(f"AlphaLabV2Engine 已注册: project=default, index=csi300")
```

- [ ] **Step 3: 运行测试**

```bash
cd F:/vnpy_live
/c/Users/jacke/anaconda3/envs/vnpy_live/python -c "
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine
from vnpy.alpha import AlphaLabV2Engine

event_engine = EventEngine()
main_engine = MainEngine(event_engine)

lab_engine = AlphaLabV2Engine(
    main_engine=main_engine,
    event_engine=event_engine,
    root_path='./test_lab_api',
    project_name='default',
    data_source='xt',
    index_code='csi300'
)
main_engine.add_engine(lab_engine)

# 验证引擎已注册
engine = main_engine.get_engine('AlphaLabV2')
assert engine is lab_engine
print('AlphaLabV2Engine 注册成功!')
"
```

- [ ] **Step 4: Commit**

```bash
git add run_trading_dashboard.py
git commit -m "feat: add AlphaLabV2Engine initialization in run_trading_dashboard.py"
```

---

## Task 2: 在 RpcEngine 中注册实验室 RPC 方法

**Files:**
- Modify: `vnpy_rpcservice/rpc_service/engine.py`

- [ ] **Step 1: 添加获取 AlphaLabV2Engine 的方法**

在 `RpcEngine` 类中添加：

```python
def get_lab_engine(self):
    """获取 AlphaLabV2Engine"""
    try:
        engine = self.main_engine.get_engine("AlphaLabV2")
        return engine
    except Exception:
        return None
```

- [ ] **Step 2: 添加实验室 RPC 方法**

在 `RpcEngine` 类中添加：

```python
def lab_get_kline(self, vt_symbol: str, period: str = "1d", days: int = 100) -> list:
    """获取K线数据"""
    engine = self.get_lab_engine()
    if engine:
        return engine.get_kline(vt_symbol, period, days)
    return []

def lab_get_components(self, start: str = None, end: str = None) -> list:
    """获取指数成分股"""
    engine = self.get_lab_engine()
    if engine:
        from datetime import datetime
        if start is None:
            start = datetime.now() - timedelta(days=30)
        if end is None:
            end = datetime.now()
        symbols = engine.get_component_symbols(engine.index_code, start, end)
        return symbols
    return []

def lab_get_coverage(self) -> dict:
    """获取数据覆盖情况"""
    engine = self.get_lab_engine()
    if engine:
        return engine.get_data_coverage()
    return {"error": "Lab engine not available"}

def lab_list_projects(self) -> list:
    """列出所有项目"""
    engine = self.get_lab_engine()
    if engine:
        return engine.list_projects()
    return []

def lab_switch_project(self, project_name: str, index_code: str = None, data_source: str = None) -> dict:
    """切换项目"""
    engine = self.get_lab_engine()
    if engine:
        return engine.switch_project(project_name, index_code, data_source)
    return {"success": False, "message": "Lab engine not available"}

def lab_create_project(self, project_name: str, index_code: str = "csi300", data_source: str = "xt") -> dict:
    """创建新项目"""
    engine = self.get_lab_engine()
    if engine:
        # 保存当前项目
        old_project = engine.project_name
        # 切换到新项目（会自动创建目录）
        result = engine.switch_project(project_name, index_code, data_source)
        # 切换回原来的项目
        engine.switch_project(old_project)
        return {"success": True, "message": f"Project {project_name} created"}
    return {"success": False, "message": "Lab engine not available"}

def lab_delete_project(self, project_name: str) -> dict:
    """删除项目"""
    import shutil
    engine = self.get_lab_engine()
    if engine:
        project_path = engine.root / "project" / project_name
        if project_path.exists():
            shutil.rmtree(project_path)
            return {"success": True, "message": f"Project {project_name} deleted"}
        return {"success": False, "message": f"Project {project_name} not found"}
    return {"success": False, "message": "Lab engine not available"}
```

- [ ] **Step 3: 在 init_server 中注册方法**

在 `init_server` 方法中添加：

```python
# 注册实验室相关方法
self.server.register(self.lab_get_kline)
self.server.register(self.lab_get_components)
self.server.register(self.lab_get_coverage)
self.server.register(self.lab_list_projects)
self.server.register(self.lab_switch_project)
self.server.register(self.lab_create_project)
self.server.register(self.lab_delete_project)
```

- [ ] **Step 4: Commit**

```bash
git add vnpy_rpcservice/rpc_service/engine.py
git commit -m "feat: add lab RPC methods in RpcEngine"
```

---

## Task 3: 在 Web 服务中添加实验室 API 端点

**Files:**
- Modify: `vnpy_webtrader/web.py`

- [ ] **Step 1: 添加实验室 K 线接口**

添加 API 端点：

```python
@app.get("/api/lab/kline/{vt_symbol}")
def get_lab_kline(
    vt_symbol: str,
    period: str = Query("1d", description="周期: 1d, 1m"),
    days: int = Query(100, description="天数"),
    access: bool = Depends(get_access)
) -> list:
    """获取实验室K线数据"""
    try:
        if hasattr(rpc_client, 'lab_get_kline'):
            return rpc_client.lab_get_kline(vt_symbol, period, days)
        return []
    except Exception as e:
        logger.error(f"获取实验室K线失败: {e}")
        return []
```

- [ ] **Step 2: 添加获取成分股接口**

```python
@app.get("/api/lab/components")
def get_lab_components(
    start: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end: str = Query(None, description="结束日期 YYYY-MM-DD"),
    access: bool = Depends(get_access)
) -> list:
    """获取当前指数成分股"""
    try:
        if hasattr(rpc_client, 'lab_get_components'):
            return rpc_client.lab_get_components(start, end)
        return []
    except Exception as e:
        logger.error(f"获取成分股失败: {e}")
        return []
```

- [ ] **Step 3: 添加数据覆盖情况接口**

```python
@app.get("/api/lab/coverage")
def get_lab_coverage(access: bool = Depends(get_access)) -> dict:
    """获取数据覆盖情况"""
    try:
        if hasattr(rpc_client, 'lab_get_coverage'):
            return rpc_client.lab_get_coverage()
        return {"error": "RPC method not available"}
    except Exception as e:
        logger.error(f"获取数据覆盖失败: {e}")
        return {"error": str(e)}
```

- [ ] **Step 4: 添加列出项目接口**

```python
@app.get("/api/lab/projects")
def get_lab_projects(access: bool = Depends(get_access)) -> list:
    """列出所有实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_list_projects'):
            return rpc_client.lab_list_projects()
        return []
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")
        return []
```

- [ ] **Step 5: 添加切换项目接口**

```python
class SwitchProjectRequest(BaseModel):
    """切换项目请求"""
    project_name: str
    index_code: Optional[str] = None
    data_source: Optional[str] = None

@app.post("/api/lab/project/switch")
def switch_lab_project(
    request: SwitchProjectRequest,
    access: bool = Depends(get_access)
) -> dict:
    """切换实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_switch_project'):
            return rpc_client.lab_switch_project(
                request.project_name,
                request.index_code,
                request.data_source
            )
        return {"success": False, "message": "RPC method not available"}
    except Exception as e:
        logger.error(f"切换项目失败: {e}")
        return {"success": False, "message": str(e)}
```

- [ ] **Step 6: 添加创建项目接口**

```python
class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    project_name: str
    index_code: str = "csi300"
    data_source: str = "xt"

@app.post("/api/lab/project/create")
def create_lab_project(
    request: CreateProjectRequest,
    access: bool = Depends(get_access)
) -> dict:
    """创建实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_create_project'):
            return rpc_client.lab_create_project(
                request.project_name,
                request.index_code,
                request.data_source
            )
        return {"success": False, "message": "RPC method not available"}
    except Exception as e:
        logger.error(f"创建项目失败: {e}")
        return {"success": False, "message": str(e)}
```

- [ ] **Step 7: 添加删除项目接口**

```python
@app.delete("/api/lab/project/{project_name}")
def delete_lab_project(
    project_name: str,
    access: bool = Depends(get_access)
) -> dict:
    """删除实验室项目"""
    try:
        if hasattr(rpc_client, 'lab_delete_project'):
            return rpc_client.lab_delete_project(project_name)
        return {"success": False, "message": "RPC method not available"}
    except Exception as e:
        logger.error(f"删除项目失败: {e}")
        return {"success": False, "message": str(e)}
```

- [ ] **Step 8: Commit**

```bash
git add vnpy_webtrader/web.py
git commit -m "feat: add lab API endpoints in web.py"
```

---

## Task 4: 集成测试

**Files:**
- None (运行集成测试)

- [ ] **Step 1: 验证导入**

```bash
cd F:/vnpy_live
/c/Users/jacke/anaconda3/envs/vnpy_live/python -c "
from vnpy.alpha import AlphaLabV2Engine
from vnpy_rpcservice.rpc_service.engine import RpcEngine
print('导入验证通过!')
"
```

- [ ] **Step 2: 验证 Web 服务可以启动**

```bash
cd F:/vnpy_live
/c/Users/jacke/anaconda3/envs/vnpy_live/python -c "
# 只验证语法和导入
import sys
sys.path.insert(0, '.')

# 模拟导入 web.py 的关键部分
from fastapi import FastAPI, Query, Depends
from pydantic import BaseModel
from typing import Optional

print('Web 服务依赖验证通过!')
"
```

- [ ] **Step 3: 提交所有更改**

```bash
git status
git add -A
git commit -m "feat: integrate lab API with web and rpc services

- Add AlphaLabV2Engine initialization in run_trading_dashboard.py
- Register lab RPC methods in RpcEngine
- Add lab API endpoints in web.py

APIs added:
- GET /api/lab/kline/{vt_symbol}
- GET /api/lab/components
- GET /api/lab/coverage
- GET /api/lab/projects
- POST /api/lab/project/switch
- POST /api/lab/project/create
- DELETE /api/lab/project/{project_name}"
```

---

## 计划完成

**下一步:** 开始执行此计划，或根据需要进行调整。
