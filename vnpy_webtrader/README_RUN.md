# VNPY WebTrader 运行示例

## 前提条件

1. **启动 RPC 服务端**（必须先启动，否则 Web 服务无法连接）

```python
# 在 VNPY 交易中启动 RPC 服务
from vnpy.rpc import RpcServer
from vnpy.event import EventEngine
from vnpy.trader.engine import MainEngine

# 启动 RPC Server
server = RpcServer()
server.start(
    rep_address="tcp://*:2014",    # 请求地址
    pub_address="tcp://*:2015"     # 推送地址
)
```

或者使用 `web_dashboard_rpc.py`（如果已配置）：
```bash
python web_dashboard_rpc.py
```

2. **配置文件**

首次运行会自动创建默认配置 `~/.vntrader/web_trader_setting.json`：
```json
{
  "username": "admin",
  "password": "admin",
  "req_address": "tcp://localhost:2014",
  "sub_address": "tcp://localhost:2015"
}
```

## 启动 Web 服务

### 方式一：独立运行（推荐用于开发测试）

```bash
# 在项目根目录
python run_web.py
```

输出：
```
[INFO] 检测到 web_dashboard，将自动使用 Vue3 看板
[INFO] 使用已有配置: /Users/xxx/.vntrader/web_trader_setting.json
==================================================
VNPY WebTrader 启动中...
==================================================
访问地址: http://localhost:8000
API 文档: http://localhost:8000/docs
RPC 请求: tcp://localhost:2014
RPC 订阅: tcp://localhost:2015
登录用户: admin
==================================================
```

### 方式二：作为 VNPY App 运行

```bash
python vnpy_webtrader/run.py
```

这会启动完整的 VNPY GUI，包含 WebTrader 模块。

## 访问看板

1. **浏览器访问**: http://localhost:8000
2. **登录**: 使用配置中的用户名/密码（默认 admin/admin）
3. **连接 WebSocket**: 登录后自动连接实时数据流

## API 文档

浏览器访问: http://localhost:8000/docs

主要接口：
- `POST /token` - 获取访问令牌
- `GET /account` - 查询账户
- `GET /position` - 查询持仓
- `GET /trade` - 查询成交
- `GET /order` - 查询委托
- `POST /order` - 发送委托
- `DELETE /order/{vt_orderid}` - 撤单
- `WebSocket /ws/` - 实时数据推送

## 架构说明

```
VNPY RPC Server (tcp://*:2014/2015)
        ↑↓ RpcClient
VNPY WebTrader (FastAPI + WebSocket)
        ↑↓
   浏览器 / 客户端
```

- **RPC Server**: VNPY 交易中运行，提供数据和交易功能
- **WebTrader**: 本服务，作为 Web 网关
- **看板**: Vue3 前端（从 web_dashboard/static 加载）

## 故障排查

### 连接失败

检查 RPC 服务是否启动：
```bash
# 查看端口监听
lsof -i :2014
lsof -i :2015
```

### 配置错误

编辑 `~/.vntrader/web_trader_setting.json`，确保地址正确。

### 模块导入错误

确保在 VNPY_Stock 项目根目录运行，且已安装 vnpy：
```bash
pip install -e .
```
