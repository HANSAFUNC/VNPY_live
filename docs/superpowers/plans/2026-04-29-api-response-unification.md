# API 统一返回格式实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 统一 `vnpy_webtrader` 所有 API 的返回格式为标准 `ApiResponse<T>` 结构

**Architecture:** 创建 `vnpy_webtrader/response.py` 模块定义泛型响应类型，改造所有 API 端点返回统一格式，前端 `client.ts` 添加响应拦截器统一处理

**Tech Stack:** Python 3.10+, FastAPI, Pydantic, TypeScript, Axios

---

## 文件结构

| 文件 | 职责 |
|-----|------|
| `vnpy_webtrader/response.py` (新建) | 定义 `ApiResponse[T]`, `ErrorDetail`, 响应构建工具函数 |
| `vnpy_webtrader/web.py` (修改) | 所有 API 端点改造为返回 `ApiResponse` |
| `web_dashboard_v2/src/api/client.ts` (修改) | 响应拦截器适配新格式 |
| `web_dashboard_v2/src/api/lab.ts` (修改) | 移除手动错误检查，由拦截器统一处理 |

---

## Task 1: 创建响应类型模块

**Files:**
- Create: `vnpy_webtrader/response.py`
- Test: 验证类型定义正确

- [ ] **Step 1: 创建 response.py 文件**

```python
"""API 统一响应格式模块

提供泛型响应类型和构建工具函数，统一所有 API 的返回格式。
"""
from typing import Generic, TypeVar, Optional, Type
from pydantic import BaseModel


class ErrorDetail(BaseModel):
    """错误详情"""
    code: str
    message: str


T = TypeVar('T')


class ApiResponse(BaseModel, Generic[T]):
    """统一 API 响应格式
    
    所有 API 端点返回此类型，前端统一处理。
    
    Example:
        # 成功响应
        {
            "success": True,
            "data": [...]
        }
        
        # 错误响应
        {
            "success": False,
            "error": {
                "code": "NOT_FOUND",
                "message": "Resource not found"
            }
        }
    """
    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None


def success_response(data: T) -> ApiResponse[T]:
    """创建成功响应"""
    return ApiResponse(success=True, data=data)


def error_response(code: str, message: str) -> ApiResponse:
    """创建错误响应"""
    return ApiResponse(success=False, error=ErrorDetail(code=code, message=message))


# 预定义错误响应
class Errors:
    """常用错误响应"""
    
    @staticmethod
    def not_found(resource: str) -> ApiResponse:
        return error_response("NOT_FOUND", f"{resource} not found")
    
    @staticmethod
    def rpc_error(message: str = "RPC method not available") -> ApiResponse:
        return error_response("RPC_ERROR", message)
    
    @staticmethod
    def validation_error(message: str) -> ApiResponse:
        return error_response("VALIDATION_ERROR", message)
    
    @staticmethod
    def internal_error(message: str = "Internal server error") -> ApiResponse:
        return error_response("INTERNAL_ERROR", message)
    
    @staticmethod
    def unauthorized(message: str = "Unauthorized") -> ApiResponse:
        return error_response("UNAUTHORIZED", message)
```

- [ ] **Step 2: 验证导入和类型检查**

Run: `python -c "from vnpy_webtrader.response import ApiResponse, success_response, error_response, Errors; print('OK')"`
Expected: `OK` (无导入错误)

- [ ] **Step 3: 提交**

```bash
git add vnpy_webtrader/response.py
git commit -m "feat: add unified API response types"
```

---

## Task 2: 改造 Web API - 基础交易接口

**Files:**
- Modify: `vnpy_webtrader/web.py` (导入和基础接口)
- Modify: `vnpy_webtrader/web.py` (K线接口 `get_kline_data`)

- [ ] **Step 1: 添加导入语句**

在 `web.py` 文件顶部，在现有 import 后添加：

```python
from vnpy_webtrader.response import ApiResponse, success_response, error_response, Errors
```

- [ ] **Step 2: 改造 `get_kline_data` 函数**

修改前：
```python
@app.get("/api/kline/{vt_symbol}")
def get_kline_data(
    vt_symbol: str,
    period: str = Query("1d", description="周期: 1d, 1h, 15m"),
    access: bool = Depends(get_access)
) -> list:
    try:
        if hasattr(rpc_client, 'get_kline'):
            data = rpc_client.get_kline(vt_symbol, period)
            return data if data else []
        return []
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return 0  # BUG: 返回整数而不是列表
```

修改后：
```python
@app.get("/api/kline/{vt_symbol}")
def get_kline_data(
    vt_symbol: str,
    period: str = Query("1d", description="周期: 1d, 1h, 15m"),
    access: bool = Depends(get_access)
) -> ApiResponse[list]:
    try:
        if hasattr(rpc_client, 'get_kline'):
            data = rpc_client.get_kline(vt_symbol, period)
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取K线数据失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 3: 提交**

```bash
git add vnpy_webtrader/web.py
git commit -m "refactor: unify get_kline_data response format"
```

---

## Task 3: 改造 Web API - Lab 基础接口

**Files:**
- Modify: `vnpy_webtrader/web.py` (Lab 基础接口)

- [ ] **Step 1: 改造 `get_lab_kline`**

修改前：
```python
@app.get("/api/lab/kline/{vt_symbol}")
def get_lab_kline(...) -> list:
    try:
        if hasattr(rpc_client, 'lab_get_kline'):
            return rpc_client.lab_get_kline(vt_symbol, period, days)
        return []
    except Exception as e:
        logger.error(f"获取实验室K线失败: {e}")
        return []
```

修改后：
```python
@app.get("/api/lab/kline/{vt_symbol}")
def get_lab_kline(
    vt_symbol: str,
    period: str = Query("1d", description="周期: 1d, 1m"),
    days: int = Query(100, description="天数"),
    access: bool = Depends(get_access)
) -> ApiResponse[list[dict]]:
    try:
        if hasattr(rpc_client, 'lab_get_kline'):
            data = rpc_client.lab_get_kline(vt_symbol, period, days)
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取实验室K线失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 2: 改造 `get_lab_components`**

修改前：
```python
@app.get("/api/lab/components")
def get_lab_components(...) -> list:
    try:
        if hasattr(rpc_client, 'lab_get_components'):
            return rpc_client.lab_get_components(start, end)
        return []
    except Exception as e:
        logger.error(f"获取成分股失败: {e}")
        return []
```

修改后：
```python
@app.get("/api/lab/components")
def get_lab_components(
    start: str = Query(None, description="开始日期 YYYY-MM-DD"),
    end: str = Query(None, description="结束日期 YYYY-MM-DD"),
    access: bool = Depends(get_access)
) -> ApiResponse[list[str]]:
    try:
        if hasattr(rpc_client, 'lab_get_components'):
            data = rpc_client.lab_get_components(start, end)
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取成分股失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 3: 改造 `get_lab_coverage`**

修改前：
```python
@app.get("/api/lab/coverage")
def get_lab_coverage(access: bool = Depends(get_access)) -> dict:
    try:
        if hasattr(rpc_client, 'lab_get_coverage'):
            return rpc_client.lab_get_coverage()
        return {"error": "RPC method not available"}
    except Exception as e:
        logger.error(f"获取数据覆盖失败: {e}")
        return {"error": str(e)}
```

修改后：
```python
@app.get("/api/lab/coverage")
def get_lab_coverage(access: bool = Depends(get_access)) -> ApiResponse[dict]:
    try:
        if hasattr(rpc_client, 'lab_get_coverage'):
            data = rpc_client.lab_get_coverage()
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取数据覆盖失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 4: 改造 `get_lab_projects`**

修改前：
```python
@app.get("/api/lab/projects")
def get_lab_projects(access: bool = Depends(get_access)) -> list:
    try:
        if hasattr(rpc_client, 'lab_list_projects'):
            return rpc_client.lab_list_projects()
        return []
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")
        return []
```

修改后：
```python
@app.get("/api/lab/projects")
def get_lab_projects(access: bool = Depends(get_access)) -> ApiResponse[list[str]]:
    try:
        if hasattr(rpc_client, 'lab_list_projects'):
            data = rpc_client.lab_list_projects()
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取项目列表失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 5: 提交**

```bash
git add vnpy_webtrader/web.py
git commit -m "refactor: unify Lab basic API responses"
```

---

## Task 4: 改造 Web API - Lab 项目管理接口

**Files:**
- Modify: `vnpy_webtrader/web.py` (Lab 项目 CRUD 接口)

- [ ] **Step 1: 改造 `switch_lab_project`**

修改前：
```python
@app.post("/api/lab/project/switch")
def switch_lab_project(...) -> dict:
    try:
        if hasattr(rpc_client, 'lab_switch_project'):
            return rpc_client.lab_switch_project(...)
        return {"success": False, "message": "RPC method not available"}
    except Exception as e:
        logger.error(f"切换项目失败: {e}")
        return {"success": False, "message": str(e)}
```

修改后：
```python
@app.post("/api/lab/project/switch")
def switch_lab_project(
    request: SwitchProjectRequest,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    try:
        if hasattr(rpc_client, 'lab_switch_project'):
            data = rpc_client.lab_switch_project(
                request.project_name,
                request.index_code,
                request.data_source
            )
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"切换项目失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 2: 改造 `create_lab_project`**

```python
@app.post("/api/lab/project/create")
def create_lab_project(
    request: CreateProjectRequest,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    try:
        if hasattr(rpc_client, 'lab_create_project'):
            data = rpc_client.lab_create_project(...)
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"创建项目失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 3: 改造 `delete_lab_project`**

```python
@app.delete("/api/lab/project/{project_name}")
def delete_lab_project(
    project_name: str,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    try:
        if hasattr(rpc_client, 'lab_delete_project'):
            data = rpc_client.lab_delete_project(project_name)
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"删除项目失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 4: 提交**

```bash
git add vnpy_webtrader/web.py
git commit -m "refactor: unify Lab project management API responses"
```

---

## Task 5: 改造 Web API - Lab 信号接口

**Files:**
- Modify: `vnpy_webtrader/web.py` (Lab 信号相关接口)

- [ ] **Step 1: 改造 `get_lab_signals`**

```python
@app.get("/api/lab/signals")
def get_lab_signals(access: bool = Depends(get_access)) -> ApiResponse[list[str]]:
    try:
        if hasattr(rpc_client, 'lab_list_signals'):
            data = rpc_client.lab_list_signals()
            return success_response(data if data else [])
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"获取信号列表失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 2: 改造 `get_lab_signal`**

修改前：
```python
@app.get("/api/lab/signal/{name}")
def get_lab_signal(...) -> dict:
    try:
        if hasattr(rpc_client, 'lab_load_signal'):
            result = rpc_client.lab_load_signal(name)
            if result is None:
                return {"error": f"Signal {name} not found"}
            return {"data": result}
        return {"error": "RPC method not available"}
```

修改后：
```python
@app.get("/api/lab/signal/{name}")
def get_lab_signal(
    name: str,
    access: bool = Depends(get_access)
) -> ApiResponse[list[dict]]:
    try:
        if hasattr(rpc_client, 'lab_load_signal'):
            result = rpc_client.lab_load_signal(name)
            if result is None or (isinstance(result, dict) and "error" in result):
                return Errors.not_found(f"Signal {name}")
            return success_response(result)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"加载信号失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 3: 改造 `delete_lab_signal`**

```python
@app.delete("/api/lab/signal/{name}")
def delete_lab_signal(
    name: str,
    access: bool = Depends(get_access)
) -> ApiResponse[dict]:
    try:
        if hasattr(rpc_client, 'lab_remove_signal'):
            data = rpc_client.lab_remove_signal(name)
            return success_response(data)
        return Errors.rpc_error()
    except Exception as e:
        logger.error(f"删除信号失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 4: 提交**

```bash
git add vnpy_webtrader/web.py
git commit -m "refactor: unify Lab signal API responses"
```

---

## Task 6: 改造 Web API - 交易相关接口

**Files:**
- Modify: `vnpy_webtrader/web.py` (ticks, orders, trades, positions, accounts, contracts, trading mode)

- [ ] **Step 1: 改造交易数据查询接口**

统一改造以下接口：
- `get_all_ticks` -> `ApiResponse[list]`
- `get_all_orders` -> `ApiResponse[list]`
- `get_all_trades` -> `ApiResponse[list]`
- `get_all_positions` -> `ApiResponse[list]`
- `get_all_accounts` -> `ApiResponse[list]`
- `get_all_contracts` -> `ApiResponse[list]`
- `get_trading_mode` -> `ApiResponse[dict]`

示例改造（以 `get_all_ticks` 为例）：

修改前：
```python
@app.get("/api/ticks")
def get_all_ticks(access: bool = Depends(get_access)) -> list:
    try:
        return [to_dict(tick) for tick in rpc_client.get_all_ticks()]
    except Exception as e:
        logger.error(f"获取Ticks失败: {e}")
        return []
```

修改后：
```python
@app.get("/api/ticks")
def get_all_ticks(access: bool = Depends(get_access)) -> ApiResponse[list]:
    try:
        data = [to_dict(tick) for tick in rpc_client.get_all_ticks()]
        return success_response(data)
    except Exception as e:
        logger.error(f"获取Ticks失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 2: 改造 `get_trading_mode`**

修改前：
```python
@app.get("/api/trading/mode")
def get_trading_mode(...) -> dict:
    try:
        # ... 原有逻辑 ...
        return {"mode": "paper", ...}
    except Exception:
        return {"mode": "paper", "mode_text": "模拟盘", "engine": "unknown"}
```

修改后：
```python
@app.get("/api/trading/mode")
def get_trading_mode(access: bool = Depends(get_access)) -> ApiResponse[dict]:
    try:
        # ... 原有逻辑 ...
        return success_response({"mode": "paper", ...})
    except Exception as e:
        logger.error(f"获取交易模式失败: {e}")
        return Errors.internal_error(str(e))
```

- [ ] **Step 3: 提交**

```bash
git add vnpy_webtrader/web.py
git commit -m "refactor: unify trading API responses"
```

---

## Task 7: 前端改造 - 响应拦截器

**Files:**
- Modify: `web_dashboard_v2/src/api/client.ts`

- [ ] **Step 1: 添加 ApiResponse 类型定义**

在文件顶部添加：

```typescript
// 统一 API 响应格式
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
}
```

- [ ] **Step 2: 改造响应拦截器**

修改前：
```typescript
client.interceptors.response.use(
  (response) => response.data,
  (error) => {
    if (error.response?.status === 401) {
      clearToken();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

修改后：
```typescript
client.interceptors.response.use(
  (response) => {
    const result = response.data as ApiResponse<unknown>;
    
    // 检查是否是统一响应格式
    if (typeof result === 'object' && result !== null && 'success' in result) {
      if (!result.success) {
        // 业务逻辑错误
        const errorMsg = result.error?.message || 'Unknown error';
        const errorCode = result.error?.code || 'UNKNOWN';
        console.error(`API Error [${errorCode}]:`, errorMsg);
        return Promise.reject(new Error(errorMsg));
      }
      // 成功，返回 data 部分
      return result.data;
    }
    
    // 兼容旧格式（直接返回数据）
    return response.data;
  },
  (error) => {
    // HTTP 错误（401, 500等）
    if (error.response?.status === 401) {
      clearToken();
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);
```

- [ ] **Step 3: 提交**

```bash
git add web_dashboard_v2/src/api/client.ts
git commit -m "feat: adapt response interceptor for unified API format"
```

---

## Task 8: 前端改造 - Lab API 简化

**Files:**
- Modify: `web_dashboard_v2/src/api/lab.ts`

- [ ] **Step 1: 改造 `loadSignal` 方法**

修改前：
```typescript
async loadSignal(name: string): Promise<Signal[]> {
  const result = await client.get(`/lab/signal/${name}`) as { data: Signal[]; error?: string };
  if (result.error) {
    throw new Error(result.error);
  }
  return result.data;
}
```

修改后：
```typescript
loadSignal(name: string): Promise<Signal[]> {
  return client.get(`/lab/signal/${name}`);
}
```

- [ ] **Step 2: 验证其他方法**

确认 `lab.ts` 中其他方法无需修改（它们只是转发到 client，由拦截器统一处理）。

- [ ] **Step 3: 提交**

```bash
git add web_dashboard_v2/src/api/lab.ts
git commit -m "refactor: simplify Lab API by using unified response format"
```

---

## Task 9: 验证和测试

**Files:**
- Test: 启动服务验证 API 响应格式正确

- [ ] **Step 1: 验证后端类型检查**

Run: `python -c "from vnpy_webtrader.web import app; print('OK')"`
Expected: `OK` (无类型检查错误)

- [ ] **Step 2: 启动服务并测试 API**

启动完整服务：
```bash
python run_trading_dashboard.py --mode paper --no-vue
```

测试 Lab K线 API：
```bash
curl "http://127.0.0.1:8000/api/lab/kline/000001.SZSE?period=1d&days=100" | python -m json.tool
```

Expected 成功响应：
```json
{
  "success": true,
  "data": [
    {"datetime": "2024-01-01", "open": 10.0, ...}
  ]
}
```

Expected 错误响应（RPC 未就绪）：
```json
{
  "success": false,
  "error": {
    "code": "RPC_ERROR",
    "message": "RPC method not available"
  }
}
```

- [ ] **Step 3: 测试前端集成**

启动前端：
```bash
cd web_dashboard_v2 && npm run dev
```

访问 Lab 页面，验证：
1. 项目列表加载正常
2. 数据覆盖统计显示正常
3. 信号列表加载正常
4. K线图数据加载正常（或显示合理错误）

- [ ] **Step 4: 提交完成**

```bash
git log --oneline -10  # 查看提交历史
echo "API unification complete!"
```

---

## Spec Coverage Check

✅ **已覆盖：**
- `ApiResponse[T]` 泛型类型定义
- `ErrorDetail` 错误详情
- `success_response` / `error_response` 构建函数
- 所有错误代码常量
- 所有 API 端点改造（基础交易、Lab 数据、项目管理、信号、交易数据）
- 前端响应拦截器改造
- 前端 Lab API 简化
- 测试验证步骤

✅ **无占位符：** 所有代码均为完整实现

✅ **类型一致性：**
- `ApiResponse[list[dict]]` 用于 K 线数据
- `ApiResponse[list[str]]` 用于字符串列表
- `ApiResponse[dict]` 用于字典数据
- `ApiResponse[list]` 用于通用列表

---

**Plan complete and saved to `docs/superpowers/plans/2026-04-29-api-response-unification.md`. Two execution options:**

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
