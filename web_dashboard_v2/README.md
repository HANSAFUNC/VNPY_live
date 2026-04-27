# VNPY Dashboard V2

基于 Vue 3 + TypeScript + Vite + Pinia + Element Plus 重构的 VNPY Web 交易终端。

## 功能特性

### 已实现功能

- **用户认证** - JWT Token 登录/登出，路由守卫保护
- **多策略支持** - 策略切换、状态管理、布局持久化
- **交易数据** - 账户资金、持仓、委托、成交实时显示
- **行情数据** - Tick、K线数据，合约订阅
- **日志系统** - 按级别/来源过滤，关键词搜索
- **拖拽布局** - 使用 vue-grid-layout 实现可拖拽网格
- **暗黑模式** - 支持亮色/暗色主题切换
- **响应式设计** - 适配桌面和平板设备

## 技术栈

| 技术 | 版本 | 用途 |
|------|------|------|
| Vue | 3.5+ | 响应式 UI 框架 |
| TypeScript | 5.6+ | 类型安全 |
| Vite | 6.2+ | 构建工具 |
| Pinia | 2.3+ | 状态管理 |
| Vue Router | 4.2+ | 路由管理 |
| Element Plus | 2.9+ | UI 组件库 |
| vue-grid-layout | 3.0+ | 拖拽布局 |
| axios | 1.7+ | HTTP 客户端 |

## 项目结构

```
web_dashboard_v2/
├── public/                     # 静态资源
├── src/
│   ├── api/                    # API 客户端
│   │   ├── client.ts           # axios 配置
│   │   ├── auth.ts             # 认证 API
│   │   ├── trading.ts          # 交易 API
│   │   ├── market.ts           # 行情 API
│   │   ├── logs.ts             # 日志 API
│   │   ├── websocket.ts        # WebSocket 管理器
│   │   └── index.ts            # 统一导出
│   ├── assets/styles/          # 全局样式
│   │   ├── variables.scss      # SCSS 变量
│   │   └── global.scss         # 全局样式
│   ├── components/layout/      # 布局组件
│   │   ├── NavBar.vue          # 顶部导航
│   │   ├── SideBar.vue         # 侧边栏
│   │   └── DraggableGrid.vue   # 可拖拽网格
│   ├── constants/              # 常量定义
│   ├── layouts/                # 页面布局
│   ├── router/                 # 路由配置
│   ├── stores/                 # Pinia Store
│   │   ├── auth.ts             # 认证状态
│   │   ├── bot.ts              # 多策略管理
│   │   ├── trading.ts          # 交易数据
│   │   ├── market.ts           # 行情数据
│   │   ├── logs.ts             # 日志数据
│   │   ├── ui.ts               # UI 状态
│   │   └── index.ts            # Store 入口
│   ├── types/                  # TypeScript 类型
│   │   ├── models.ts           # 业务模型
│   │   ├── api.ts              # API 类型
│   │   └── components.ts       # 组件类型
│   ├── utils/                  # 工具函数
│   │   ├── formatters.ts       # 格式化函数
│   │   └── storage.ts          # 本地存储
│   ├── views/                  # 页面视图
│   │   ├── LoginView.vue       # 登录页
│   │   ├── DashboardView.vue   # 总览页
│   │   ├── TradeView.vue       # 交易页
│   │   └── LogsView.vue        # 日志页
│   ├── widgets/                # 可拖拽部件
│   │   ├── AccountSummaryWidget.vue
│   │   ├── PositionWidget.vue
│   │   ├── TradeHistoryWidget.vue
│   │   ├── SignalWidget.vue
│   │   └── StatWidget.vue
│   ├── App.vue                 # 根组件
│   ├── main.ts                 # 应用入口
│   └── env.d.ts                # 类型声明
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
└── .env.example
```

## 快速开始

### 安装依赖

```bash
cd web_dashboard_v2
npm install
```

### 配置环境变量

```bash
cp .env.example .env
```

编辑 `.env`：
```
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000/ws
```

### 开发模式

```bash
npm run dev
```

访问 http://localhost:3000

### 生产构建

```bash
npm run build
```

构建输出到 `dist/` 目录。

### 类型检查

```bash
npm run type-check
```

## 后端集成

Dashboard V2 需要配合 VNPY WebTrader 后端使用：

```python
# 启动 VNPY WebTrader
python -m vnpy_webtrader
```

后端 API 地址：http://localhost:8000
- REST API: `/account`, `/position`, `/order`, `/trade`, `/tick`, `/logs`
- WebSocket: `/ws/`

## 页面说明

### 登录页 (/login)

- 用户名/密码登录
- 登录成功后自动连接 WebSocket

### 总览页 (/dashboard)

- 可拖拽网格布局
- 账户概览、持仓列表、成交历史
- 交易信号、统计指标

### 交易页 (/trade)

- K 线图（待接入 ECharts）
- 快速下单表单
- 当前挂单列表

### 日志页 (/logs)

- 日志级别过滤
- 来源过滤
- 关键词搜索

## 开发指南

### 添加新的 Widget

1. 在 `src/widgets/` 创建组件
2. 在 `src/constants/index.ts` 添加到默认布局
3. 在 `DashboardView.vue` 添加 slot

### 添加新的 Store

1. 在 `src/stores/` 创建 Store
2. 在 `src/stores/index.ts` 导出
3. 使用 `defineStore('name', () => {...})` 格式

### API 调用

```typescript
import { tradingApi } from '@/api';

const positions = await tradingApi.getPositions();
```

## 注意事项

1. **K 线图** - 当前为占位符，需接入 ECharts 实现完整 K 线功能
2. **交易信号** - 当前为模拟数据，需接入 WebSocket 实时信号
3. **多策略** - 需在 BotStore 中配置策略列表

## 贡献

1. Fork 本仓库
2. 创建特性分支 (`git checkout -b feature/xxx`)
3. 提交更改 (`git commit -am 'Add xxx'`)
4. 推送分支 (`git push origin feature/xxx`)
5. 创建 Pull Request

## 许可证

MIT License
