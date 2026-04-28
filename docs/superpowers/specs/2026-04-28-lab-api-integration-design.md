# 实验室 API 联动设计方案

> **日期:** 2026-04-28  
> **主题:** vnpy_webtrader + vnpy_rpcservice + AlphaLabV2Engine 联动

---

## 目标

将 Web 交易服务 (`vnpy_webtrader`) 与 RPC 服务 (`vnpy_rpcservice`) 和实验室引擎 (`AlphaLabV2Engine`) 联动，提供统一的实验室数据 API。

---

## 架构设计

### 组件关系

```
run_trading_dashboard.py
    │
    ├──► MainEngine (传入 lab_path="./lab")
    │       │
    │       └──► AlphaLabV2Engine (启动时注册)
    │               engine_name = "AlphaLabV2"
    │
    ├──► RpcEngine (RPC服务)
    │       │
    │       └──► 通过 main_engine.get_engine("AlphaLabV2")
    │           获取实验室引擎，注册 RPC 方法
    │
    └──► Web服务 (FastAPI)
            │
            └──► 通过 rpc_client 调用实验室方法
```

### 数据流

```
Web 请求 ──► vnpy_webtrader/web.py ──► RpcClient ──► RpcEngine
                                              │
                                              ▼
                                         通过 MainEngine 获取
                                         AlphaLabV2Engine
                                              │
                                              ▼
                                         返回实验室数据
```

---

## API 端点设计

| 方法 | 路径 | 说明 | 参数 |
|------|------|------|------|
| GET | `/api/lab/kline/{vt_symbol}` | 获取K线数据 | `period`, `days` |
| GET | `/api/lab/components` | 获取当前指数成分股 | `start`, `end` |
| GET | `/api/lab/coverage` | 数据覆盖情况 | - |
| GET | `/api/lab/projects` | 列出所有项目 | - |
| POST | `/api/lab/project/switch` | 切换项目 | `project_name`, `index_code`, `data_source` |
| POST | `/api/lab/project/create` | 创建项目 | `project_name`, `index_code`, `data_source` |
| DELETE | `/api/lab/project/{project_name}` | 删除项目 | - |

---

## 关键设计决策

### 1. 数据路径配置

- **固定路径**: `./lab`
- **传递方式**: 通过 `run_trading_dashboard.py` 初始化时传给 `MainEngine`

### 2. 项目初始化

- **默认值**: `project_name="default"`, `data_source="xt"`, `index_code="csi300"`
- **启动时机**: `AlphaLabV2Engine` 在 `run_trading_dashboard.py` 启动时注册到 `MainEngine`

### 3. RPC 方法注册

在 `RpcEngine` 中注册以下方法：

```python
self.server.register(self.lab_get_kline)
self.server.register(self.lab_get_components)
self.server.register(self.lab_get_coverage)
self.server.register(self.lab_list_projects)
self.server.register(self.lab_switch_project)
self.server.register(self.lab_create_project)
self.server.register(self.lab_delete_project)
```

### 4. Web API 实现

在 `vnpy_webtrader/web.py` 中实现 API 端点：

```python
@app.get("/api/lab/kline/{vt_symbol}")
def get_lab_kline(vt_symbol: str, period: str = "1d", days: int = 100):
    return rpc_client.lab_get_kline(vt_symbol, period, days)
```

---

## 错误处理

1. **引擎未注册**: 返回 HTTP 503 或空数据
2. **项目不存在**: 返回 HTTP 404
3. **参数错误**: 返回 HTTP 400
4. **内部错误**: 返回 HTTP 500，记录日志

---

## 依赖关系

- `vnpy.alpha.AlphaLabV2Engine` (已实现)
- `vnpy.trader.engine.MainEngine` (已存在)
- `vnpy_rpcservice.RpcEngine` (已存在)
- `vnpy_webtrader.web` (已存在)

---

## 设计完成，准备实施
