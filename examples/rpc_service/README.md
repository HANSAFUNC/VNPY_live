# VNPY RPC 服务使用指南

使用 `vnpy_rpcservice` 实现分布式交易架构。

## 架构概览

```
┌─────────────────┐         RPC协议          ┌─────────────────┐
│   Web看板/     │  ═══════════════════►   │   交易服务器    │
│   客户端       │   (ZeroMQ TCP)         │   (RPC服务端)   │
│                 │                        │                 │
│  - 远程监控    │  ◄═══════════════════   │  - 连接交易所  │
│  - 策略管理    │   行情/成交推送          │  - 执行策略    │
│  - 下单撤单   │                        │  - 数据持久化  │
└─────────────────┘                        └─────────────────┘
```

## 安装

```bash
pip install vnpy_rpcservice
```

## 使用方式

### 方式一：基础 RPC 示例

**1. 启动服务端**

```bash
python examples/rpc_service/rpc_demo.py server
```

**2. 启动客户端**

```bash
python examples/rpc_service/rpc_demo.py client
```

### 方式二：Web看板 + RPC（推荐）

**1. 在交易服务器启动 RPC 服务端**

```bash
python examples/rpc_service/rpc_server.py
```

可选参数：
```bash
python examples/rpc_service/rpc_server.py \
    --rep tcp://*:2014 \
    --pub tcp://*:2015 \
    --gateway XT \
    --account your_account
```

**2. 在本地启动 Web 看板（作为 RPC 客户端）**

```bash
python examples/rpc_service/rpc_web_dashboard.py
```

如果服务端在其他机器：
```bash
python examples/rpc_service/rpc_web_dashboard.py \
    --rpc-req tcp://192.168.1.100:2014 \
    --rpc-sub tcp://192.168.1.100:2015
```

**3. 访问 Web 看板**

浏览器打开 http://localhost:8000

### 方式三：Alpha策略RPC服务端 + Web看板

**1. 启动Alpha策略RPC服务端**

```bash
python examples/rpc_service/rpc_server_alpha.py
```

带交易账号参数：
```bash
python examples/rpc_service/rpc_server_alpha.py \
    --rep tcp://*:2014 \
    --pub tcp://*:2015 \
    --gateway XT \
    --account your_account
```

**2. 启动Web看板（RPC模式）**

```bash
python web_dashboard_rpc.py
```

连接远程服务器：
```bash
python web_dashboard_rpc.py \
    --rpc-req tcp://192.168.1.100:2014 \
    --rpc-sub tcp://192.168.1.100:2015 \
    --port 8080
```

**3. 访问Web看板**

浏览器打开 http://localhost:8000

---

## 完整部署示例

### 场景：交易服务器 + Web监控端

```
┌─────────────────┐         RPC          ┌─────────────────┐
│  交易服务器      │  ◄────────────────►  │  Web监控端       │
│  (云端/本地)     │   tcp://:2014/2015  │  (本机/远程)     │
├─────────────────┤                      ├─────────────────┤
│ - RPC服务端     │                      │ - Web看板       │
│ - Alpha策略     │                      │ - 实时监控      │
│ - 交易网关      │                      │ - 远程查看      │
└─────────────────┘                      └─────────────────┘
```

```bash
# 交易服务器
python examples/rpc_service/rpc_server_alpha.py \
    --rep tcp://0.0.0.0:2014 \
    --pub tcp://0.0.0.0:2015 \
    --account your_account

# Web监控端
python web_dashboard_rpc.py \
    --rpc-req tcp://server_ip:2014 \
    --rpc-sub tcp://server_ip:2015 \
    --port 8080
```

---

## 端口配置

| 地址 | 说明 | 默认 |
|------|------|------|
| REP | 接收客户端请求 | tcp://*:2014 |
| PUB | 推送行情/成交 | tcp://*:2015 |

客户端需使用对应地址连接：
- REQ → 服务端的 REP
- SUB → 服务端的 PUB

## 典型部署场景

### 场景1：本地开发测试

服务端和客户端在同一台机器，使用默认地址。

### 场景2：局域网部署

```
交易服务器(192.168.1.100):
  python rpc_server.py --rep tcp://0.0.0.0:2014 --pub tcp://0.0.0.0:2015

Web看板(本地):
  python rpc_web_dashboard.py --rpc-req tcp://192.168.1.100:2014 --rpc-sub tcp://192.168.1.100:2015
```

### 场景3：云服务器部署

```
云服务器(公网IP):
  python rpc_server.py --rep tcp://0.0.0.0:2014 --pub tcp://0.0.0.0:2015

本地客户端:
  python rpc_web_dashboard.py --rpc-req tcp://your.server.ip:2014 --rpc-sub tcp://your.server.ip:2015
```

**注意：** 云服务器需开放对应端口的安全组规则。

## API说明

### 服务端 API

服务端自动暴露 `MainEngine` 和 `EventEngine` 的所有方法，包括：

- `get_all_accounts()` - 查询账户
- `get_all_positions()` - 查询持仓
- `get_all_orders()` - 查询订单
- `send_order(req, gateway_name)` - 发送订单
- `cancel_order(req, gateway_name)` - 撤单
- `subscribe(req, gateway_name)` - 订阅行情

### 事件推送

服务端通过 PUB 地址推送实时事件：
- `EVENT_TICK` - 行情推送
- `EVENT_TRADE` - 成交推送
- `EVENT_ORDER` - 订单推送
- `EVENT_POSITION` - 持仓推送
- `EVENT_ACCOUNT` - 账户推送

## 安全建议

1. **内网使用**：生产环境建议在内网部署，避免暴露公网
2. **VPN/专线**：跨地域使用 VPN 或专线连接
3. **防火墙**：限制可连接的 IP 地址
4. **SSL/TLS**：如需公网传输，考虑使用 SSL 加密

## 故障排查

### 连接失败
- 检查服务端是否已启动
- 检查防火墙和安全组设置
- 使用 `telnet` 测试端口连通性

### 数据不更新
- 检查 PUB/SUB 地址配置是否正确
- 查看服务端日志是否有推送

### 性能问题
- RPC 适合低频交易（分钟/日频）
- 高频交易建议直连交易所或使用 CTP/xtp 等网关
