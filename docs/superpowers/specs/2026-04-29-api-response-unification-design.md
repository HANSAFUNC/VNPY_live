# API 统一返回格式设计文档

> **日期:** 2026-04-29  
> **主题:** Web Dashboard 后端 API 响应格式统一

---

## 目标

统一 `vnpy_webtrader` 所有 API 的返回格式，解决当前返回格式混乱的问题：
- 列表 API 错误时返回 `[]`，无法区分空数据和错误
- 字典 API 有的返回 `{"error": ...}`，有的返回 `{"success": False, "message": ...}`
- `get_kline_data` 错误时返回 `0` 的 bug

---

## 设计方案

### 统一响应格式

所有 API 返回统一结构：

```json
{
  "success": true/false,
  "data": T,              // 成功时存在
  "error": {              // 失败时存在
    "code": "ERROR_CODE",
    "message": "人类可读的错误描述"
  }
}
```

### 错误代码规范

| 错误代码 | 使用场景 |
|---------|---------|
| `NOT_FOUND` | 资源不存在（如信号文件不存在） |
| `RPC_ERROR` | RPC 调用失败或方法不可用 |
| `VALIDATION_ERROR` | 请求参数验证失败 |
| `INTERNAL_ERROR` | 内部服务器错误 |
| `UNAUTHORIZED` | 未授权访问 |

### 类型定义

```python
from typing import Generic, TypeVar, Optional
from pydantic import BaseModel

class ErrorDetail(BaseModel):
    code: str
    message: str

T = TypeVar('T')

class ApiResponse(BaseModel, Generic[T]):
    success: bool
    data: Optional[T] = None
    error: Optional[ErrorDetail] = None
```

### 响应构建工具

```python
def success_response(data: T) -> ApiResponse[T]:
    return ApiResponse(success=True, data=data)

def error_response(code: str, message: str) -> ApiResponse:
    return ApiResponse(success=False, error=ErrorDetail(code=code, message=message))
```

---

## API 改造清单

| API 路径 | 当前返回类型 | 新返回类型 |
|---------|------------|-----------|
| `GET /api/kline/{vt_symbol}` | `list` | `ApiResponse[list]` |
| `GET /api/lab/kline/{vt_symbol}` | `list` | `ApiResponse[list[dict]]` |
| `GET /api/lab/components` | `list` | `ApiResponse[list[str]]` |
| `GET /api/lab/coverage` | `dict` | `ApiResponse[DataCoverage]` |
| `GET /api/lab/projects` | `list` | `ApiResponse[list[str]]` |
| `POST /api/lab/project/switch` | `dict` | `ApiResponse[dict]` |
| `POST /api/lab/project/create` | `dict` | `ApiResponse[dict]` |
| `DELETE /api/lab/project/{name}` | `dict` | `ApiResponse[dict]` |
| `GET /api/lab/signals` | `list` | `ApiResponse[list[str]]` |
| `GET /api/lab/signal/{name}` | `dict` | `ApiResponse[list[Signal]]` |
| `DELETE /api/lab/signal/{name}` | `dict` | `ApiResponse[dict]` |
| `GET /api/trading/mode` | `dict` | `ApiResponse[dict]` |
| `GET /api/ticks` | `list` | `ApiResponse[list]` |
| `GET /api/orders` | `list` | `ApiResponse[list]` |
| `GET /api/trades` | `list` | `ApiResponse[list]` |
| `GET /api/positions` | `list` | `ApiResponse[list]` |
| `GET /api/accounts` | `list` | `ApiResponse[list]` |
| `GET /api/contracts` | `list` | `ApiResponse[list]` |

---

## 前端适配

### 响应拦截器更新

```typescript
// client.ts
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: { code: string; message: string };
}

client.interceptors.response.use(
  (response) => {
    const result = response.data as ApiResponse<unknown>;
    if (!result.success) {
      return Promise.reject(new Error(result.error?.message || 'Unknown error'));
    }
    return result.data;
  },
  (error) => Promise.reject(error)
);
```

### API 方法签名更新

移除 `loadSignal` 中的手动错误检查，由拦截器统一处理：

```typescript
// 改造前
async loadSignal(name: string): Promise<Signal[]> {
  const result = await client.get(`/lab/signal/${name}`) as { data: Signal[]; error?: string };
  if (result.error) {
    throw new Error(result.error);
  }
  return result.data;
}

// 改造后
loadSignal(name: string): Promise<Signal[]> {
  return client.get(`/lab/signal/${name}`);
}
```

---

## HTTP 状态码

统一返回 HTTP 200，由响应体中的 `success` 字段区分成功/失败。

---

## 设计完成

准备开始实施。
