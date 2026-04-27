# VNPY Dashboard V2 动态 API URL 设计文档

> **日期:** 2026-04-27  
> **目标:** 实现类似 freqUI 的多服务器管理，登录时动态指定 VNPY API 地址

---

## 1. 需求概述

### 当前问题
- Dashboard 的 API URL 在构建时通过 `.env` 固定
- 每个 VNPY 实例需要单独部署一套 Dashboard
- 无法一个 Dashboard 管理多个 VNPY 实例

### 目标方案
- Dashboard 作为独立静态应用部署
- 登录时输入/选择要连接的 VNPY 服务器地址
- 支持保存和管理多个服务器地址
- 完全解耦前后端部署

---

## 2. 架构设计

```
┌─────────────────────────────────────────────┐
│         VNPY Dashboard V2 (静态 SPA)         │
│    (可部署在: 本地/Github Pages/任何服务器)    │
└──────────────────────┬──────────────────────┘
                       │ 登录时选择 API URL
       ┌───────────────┼───────────────┐
       ▼               ▼               ▼
┌─────────────┐ ┌─────────────┐ ┌─────────────┐
│ VNPY 本地   │ │ VNPY 服务器 │ │ VNPY 云端   │
│ :8000       │ │ :8001       │ │ :443        │
└─────────────┘ └─────────────┘ └─────────────┘
```

---

## 3. 功能设计

### 3.1 登录页面增强

**新增表单字段:**
- 服务器地址输入框 (URL)
- 已保存地址下拉选择
- "记住此服务器" 复选框

**交互流程:**
1. 用户输入服务器地址
2. 点击"检测连接"验证地址可用性
3. 输入用户名密码
4. 登录成功后保存服务器配置

### 3.2 服务器管理

**数据存储:**
```typescript
interface ServerConfig {
  id: string;           // 唯一标识
  name: string;         // 显示名称(用户自定义)
  url: string;          // API 地址
  wsUrl: string;        // WebSocket 地址
  lastUsed: number;     // 最后使用时间
  isDefault?: boolean;  // 是否默认
}
```

**存储位置:** localStorage (`vnpy_servers`)

**功能:**
- 自动保存登录成功的服务器
- 支持重命名/删除已保存的服务器
- 显示最近使用的服务器列表
- 记住上次使用的服务器

### 3.3 动态 API Client

**修改内容:**
- 移除 `import.meta.env.VITE_API_BASE_URL`
- axios client 支持运行时设置 baseURL
- WebSocket 支持动态 URL
- 登录后将 URL 写入 pinia store

**代码示例:**
```typescript
// 动态设置 API 地址
function setApiBaseUrl(url: string) {
  client.defaults.baseURL = url;
  wsManager.setUrl(url.replace('http', 'ws') + '/ws');
}
```

### 3.4 CORS 跨域支持

**VNPY 后端修改:**
```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境建议限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

---

## 4. 界面设计

### 登录页布局
```
┌─────────────────────────────────────────┐
│              VNPY Dashboard             │
│                                         │
│  服务器地址: [http://localhost:8000 ▼]  │
│              (或从列表选择)             │
│                                         │
│  用户名:    [admin           ]          │
│  密码:      [••••••••        ]          │
│                                         │
│  [ ] 记住此服务器                       │
│                                         │
│         [  检测连接  ]                  │
│                                         │
│         [    登 录    ]                 │
│                                         │
└─────────────────────────────────────────┘
```

### 服务器选择下拉
```
┌─────────────────────────────────────────┐
│ 最近使用           ▼                    │
├─────────────────────────────────────────┤
│ 💾 本地开发 (localhost:8000)            │
│ 💾 测试服务器 (192.168.1.100:8000)      │
│ ─────────────────────────────────────── │
│ ➕ 添加新服务器...                      │
│ 📝 管理已保存的服务器                   │
└─────────────────────────────────────────┘
```

---

## 5. 数据流设计

```
用户输入 URL
    ↓
检测连接 (GET / 或 /docs)
    ↓
设置 axios baseURL
设置 WebSocket URL
    ↓
登录验证 (POST /token)
    ↓
保存服务器配置到 localStorage
    ↓
进入 Dashboard
    ↓
所有 API 请求使用动态 URL
```

---

## 6. 文件修改清单

### 需要修改的文件

| 文件 | 修改内容 |
|------|----------|
| `src/views/LoginView.vue` | 增加 URL 输入、服务器选择、连接检测 |
| `src/api/client.ts` | 移除环境变量，支持动态 baseURL |
| `src/api/websocket.ts` | 支持动态 WebSocket URL |
| `src/stores/auth.ts` | 登录时传入并保存 URL |
| `src/utils/storage.ts` | 增加服务器配置存取函数 |
| `.env.example` | 移除 VITE_API_BASE_URL（可选） |

### 需要新增的文件

| 文件 | 用途 |
|------|------|
| `src/components/ServerSelector.vue` | 服务器选择下拉组件 |
| `src/utils/servers.ts` | 服务器配置管理（CRUD） |

### VNPY 后端修改

| 文件 | 修改内容 |
|------|----------|
| `vnpy_webtrader/web.py` | 添加 CORS 中间件 |

---

## 7. 安全考虑

1. **HTTPS 优先** - 生产环境建议使用 HTTPS
2. **CORS 限制** - 生产环境限制 `allow_origins` 为具体域名
3. **URL 验证** - 只允许 http/https 协议
4. **本地存储加密** - 敏感信息可简单混淆存储

---

## 8. 兼容性

- 支持 HTTP 和 HTTPS
- 支持自定义端口
- 支持 IP 地址和域名
- 支持反向代理后的路径（如 `/vnpy/api`）

---

## 批准记录

- **设计日期:** 2026-04-27
- **状态:** 待审核

**请审核上述设计文档，确认后我将创建详细的实现计划。**
