# 动态 API URL 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 Dashboard 登录时动态指定 VNPY API 服务器地址，支持多服务器管理

**Architecture:** 移除前端硬编码 API URL，改为登录时由用户输入/选择服务器地址，动态配置 axios 和 WebSocket 客户端，同时 VNPY 后端添加 CORS 跨域支持

**Tech Stack:** Vue 3 + TypeScript + Pinia + axios + Element Plus + FastAPI (CORS)

---

## 文件结构

### 需要修改的文件

| 文件 | 职责 |
|------|------|
| `web_dashboard_v2/src/utils/servers.ts` | 服务器配置 CRUD 操作（localStorage） |
| `web_dashboard_v2/src/api/client.ts` | 移除硬编码 baseURL，支持动态设置 |
| `web_dashboard_v2/src/api/websocket.ts` | 支持动态 WebSocket URL |
| `web_dashboard_v2/src/views/LoginView.vue` | 增加服务器 URL 输入和选择 |
| `web_dashboard_v2/src/stores/auth.ts` | 登录时处理服务器配置 |
| `vnpy_webtrader/web.py` | 添加 CORS 中间件 |

---

## Task 1: 服务器配置管理工具函数

**Files:**
- Create: `web_dashboard_v2/src/utils/servers.ts`
- Modify: `web_dashboard_v2/src/types/models.ts` (添加 ServerConfig 类型)

- [ ] **Step 1: 添加 ServerConfig 类型到 models.ts**

```typescript
// types/models.ts 末尾添加

export interface ServerConfig {
  id: string;
  name: string;
  url: string;
  wsUrl: string;
  lastUsed: number;
  isDefault?: boolean;
}
```

- [ ] **Step 2: 创建 servers.ts 工具函数**

```typescript
// utils/servers.ts
import type { ServerConfig } from '@/types';

const STORAGE_KEY = 'vnpy_servers';

/**
 * 获取所有保存的服务器配置
 */
export function getServers(): ServerConfig[] {
  try {
    const data = localStorage.getItem(STORAGE_KEY);
    return data ? JSON.parse(data) : [];
  } catch {
    return [];
  }
}

/**
 * 保存服务器配置
 */
export function saveServer(server: Omit<ServerConfig, 'id' | 'lastUsed'> & { id?: string }): ServerConfig {
  const servers = getServers();
  const now = Date.now();
  
  if (server.id) {
    // 更新现有配置
    const index = servers.findIndex(s => s.id === server.id);
    if (index >= 0) {
      servers[index] = { ...servers[index], ...server, lastUsed: now };
    }
  } else {
    // 添加新配置
    const newServer: ServerConfig = {
      ...server,
      id: `server_${now}`,
      lastUsed: now,
    };
    servers.push(newServer);
  }
  
  localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
  return server as ServerConfig;
}

/**
 * 删除服务器配置
 */
export function deleteServer(id: string): void {
  const servers = getServers().filter(s => s.id !== id);
  localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
}

/**
 * 获取最近使用的服务器
 */
export function getRecentServers(limit = 5): ServerConfig[] {
  return getServers()
    .sort((a, b) => b.lastUsed - a.lastUsed)
    .slice(0, limit);
}

/**
 * 获取默认服务器
 */
export function getDefaultServer(): ServerConfig | null {
  const servers = getServers();
  return servers.find(s => s.isDefault) || servers[0] || null;
}

/**
 * 设置默认服务器
 */
export function setDefaultServer(id: string): void {
  const servers = getServers().map(s => ({
    ...s,
    isDefault: s.id === id,
  }));
  localStorage.setItem(STORAGE_KEY, JSON.stringify(servers));
}

/**
 * 从 URL 生成 WebSocket URL
 */
export function generateWsUrl(httpUrl: string): string {
  return httpUrl.replace(/^http/, 'ws') + '/ws';
}

/**
 * 验证服务器地址格式
 */
export function validateServerUrl(url: string): boolean {
  try {
    const parsed = new URL(url);
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}
```

- [ ] **Step 3: 导出 servers 函数**

```typescript
// utils/index.ts
export * from './formatters';
export * from './storage';
export * from './servers';  // 添加这行
```

- [ ] **Step 4: 验证类型检查**

Run: `cd web_dashboard_v2 && npm run type-check`
Expected: 无错误

- [ ] **Step 5: 提交**

```bash
git add web_dashboard_v2/src/utils/servers.ts web_dashboard_v2/src/utils/index.ts web_dashboard_v2/src/types/models.ts
git commit -m "feat(dashboard-v2): 添加服务器配置管理工具函数"
```

---

## Task 2: API Client 支持动态 baseURL

**Files:**
- Modify: `web_dashboard_v2/src/api/client.ts`

- [ ] **Step 1: 修改 client.ts 支持动态 baseURL**

```typescript
// api/client.ts
import axios from 'axios';
import { clearToken, getToken } from '@/utils/storage';

// 创建 axios 实例，不设置 baseURL
export const client = axios.create({
  timeout: 10000,
  headers: {
    'Content-Type': 'application/json',
  },
});

// 请求拦截器 - 添加 Token
client.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// 响应拦截器 - 处理错误
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

/**
 * 设置 API baseURL
 */
export function setApiBaseUrl(baseURL: string): void {
  client.defaults.baseURL = baseURL;
}

/**
 * 获取当前 baseURL
 */
export function getApiBaseUrl(): string | undefined {
  return client.defaults.baseURL;
}
```

- [ ] **Step 2: 验证类型检查**

Run: `cd web_dashboard_v2 && npm run type-check`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add web_dashboard_v2/src/api/client.ts
git commit -m "feat(dashboard-v2): API Client 支持动态 baseURL"
```

---

## Task 3: WebSocket 支持动态 URL

**Files:**
- Modify: `web_dashboard_v2/src/api/websocket.ts`

- [ ] **Step 1: 修改 WebSocketManager 支持动态 URL**

```typescript
// api/websocket.ts
import { ref, computed } from 'vue';
import type { WebSocketMessage } from '@/types';
import { getToken } from '@/utils/storage';

export type MessageHandler<T = unknown> = (data: T) => void;

class WebSocketManager {
  private ws: WebSocket | null = null;
  private reconnectTimer: number | null = null;
  private handlers: Map<string, MessageHandler[]> = new Map();
  private reconnectCount = 0;
  private maxReconnectCount = 5;
  private intentionalClose = false;
  private wsUrl: string | null = null;

  public readonly isConnected = ref(false);
  public readonly statusText = computed(() =>
    this.isConnected.value ? '已连接' : '未连接'
  );

  /**
   * 设置 WebSocket URL
   */
  setUrl(url: string): void {
    this.wsUrl = url;
  }

  /**
   * 获取当前 WebSocket URL
   */
  getUrl(): string | null {
    return this.wsUrl;
  }

  connect(): void {
    // 防止重复连接
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }

    // 检查 URL 是否已设置
    if (!this.wsUrl) {
      console.error('WebSocket URL not set');
      return;
    }

    this.intentionalClose = false;

    const token = getToken();
    if (!token) return;

    const url = `${this.wsUrl}?token=${token}`;
    
    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('WebSocket connected');
      this.isConnected.value = true;
      this.reconnectCount = 0;
    };

    this.ws.onmessage = (event: MessageEvent) => {
      try {
        const message: WebSocketMessage = JSON.parse(event.data as string);
        this.handleMessage(message);
      } catch (e) {
        console.error('Failed to parse WebSocket message:', e);
      }
    };

    this.ws.onclose = () => {
      console.log('WebSocket closed');
      this.isConnected.value = false;
      if (!this.intentionalClose) {
        this.scheduleReconnect();
      }
    };

    this.ws.onerror = (error) => {
      console.error('WebSocket error:', error);
    };
  }

  disconnect(): void {
    this.intentionalClose = true;
    if (this.reconnectTimer !== null) {
      clearTimeout(this.reconnectTimer);
      this.reconnectTimer = null;
    }
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
    this.isConnected.value = false;
  }

  private scheduleReconnect(): void {
    if (this.reconnectCount >= this.maxReconnectCount) {
      console.error('Max reconnection attempts reached');
      return;
    }

    const delay = Math.min(1000 * Math.pow(2, this.reconnectCount), 30000);
    this.reconnectCount++;

    this.reconnectTimer = window.setTimeout(() => {
      console.log(`Reconnecting... attempt ${this.reconnectCount}`);
      this.connect();
    }, delay);
  }

  on<T>(topic: string, handler: MessageHandler<T>): void {
    if (!this.handlers.has(topic)) {
      this.handlers.set(topic, []);
    }
    this.handlers.get(topic)!.push(handler as MessageHandler);
  }

  off<T>(topic: string, handler: MessageHandler<T>): void {
    const handlers = this.handlers.get(topic);
    if (handlers) {
      const index = handlers.indexOf(handler as MessageHandler);
      if (index > -1) {
        handlers.splice(index, 1);
      }
    }
  }

  private handleMessage(message: WebSocketMessage): void {
    const handlers = this.handlers.get(message.topic) ?? [];
    handlers.forEach((handler) => {
      try {
        handler(message.data);
      } catch (e) {
        console.error('Message handler error:', e);
      }
    });
  }
}

export const wsManager = new WebSocketManager();
```

- [ ] **Step 2: 验证类型检查**

Run: `cd web_dashboard_v2 && npm run type-check`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add web_dashboard_v2/src/api/websocket.ts
git commit -m "feat(dashboard-v2): WebSocket 支持动态 URL"
```

---

## Task 4: 修改 Auth Store 处理服务器配置

**Files:**
- Modify: `web_dashboard_v2/src/stores/auth.ts`

- [ ] **Step 1: 修改 auth.ts**

```typescript
// stores/auth.ts
import { ref, computed } from 'vue';
import { defineStore } from 'pinia';
import { authApi, wsManager, setApiBaseUrl } from '@/api';
import { setToken, clearToken, getToken } from '@/utils/storage';
import { saveServer, generateWsUrl } from '@/utils/servers';
import type { LoginRequest, ServerConfig } from '@/types';

export const useAuthStore = defineStore(
  'auth',
  () => {
    // State
    const token = ref<string | null>(getToken());
    const isLoggedIn = computed(() => !!token.value);
    const currentServer = ref<ServerConfig | null>(null);

    // Actions
    async function login(credentials: LoginRequest, serverUrl: string): Promise<void> {
      // 1. 设置 API baseURL
      setApiBaseUrl(serverUrl);
      
      // 2. 登录获取 token
      const response = await authApi.login(credentials);
      token.value = response.access_token;
      setToken(response.access_token);
      
      // 3. 设置 WebSocket URL
      const wsUrl = generateWsUrl(serverUrl);
      wsManager.setUrl(wsUrl);
      wsManager.connect();
      
      // 4. 保存服务器配置
      const serverName = new URL(serverUrl).host;
      currentServer.value = saveServer({
        name: serverName,
        url: serverUrl,
        wsUrl: wsUrl,
      });
    }

    function logout(): void {
      token.value = null;
      clearToken();
      wsManager.disconnect();
      currentServer.value = null;
    }

    function setCurrentServer(server: ServerConfig): void {
      currentServer.value = server;
      setApiBaseUrl(server.url);
      wsManager.setUrl(server.wsUrl);
    }

    return {
      token,
      isLoggedIn,
      currentServer,
      login,
      logout,
      setCurrentServer,
    };
  },
  {
    persist: {
      pick: ['token', 'currentServer'],
    },
  }
);
```

- [ ] **Step 2: 验证类型检查**

Run: `cd web_dashboard_v2 && npm run type-check`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add web_dashboard_v2/src/stores/auth.ts
git commit -m "feat(dashboard-v2): Auth Store 支持服务器配置"
```

---

## Task 5: 更新登录页面

**Files:**
- Modify: `web_dashboard_v2/src/views/LoginView.vue`

- [ ] **Step 1: 重写 LoginView.vue**

```vue
<template>
  <div class="login-page">
    <el-card class="login-card">
      <template #header>
        <h1 class="login-title">VNPY Pro</h1>
        <p class="login-subtitle">量化交易终端</p>
      </template>

      <el-form
        ref="formRef"
        :model="form"
        :rules="rules"
        @keyup.enter="handleLogin"
      >
        <!-- 服务器地址 -->
        <el-form-item prop="serverUrl">
          <el-input
            v-model="form.serverUrl"
            placeholder="服务器地址，如 http://localhost:8000"
            :prefix-icon="Link"
            size="large"
          >
            <template #append>
              <el-button :icon="Check" @click="testConnection" :loading="testing">
                检测
              </el-button>
            </template>
          </el-input>
        </el-form-item>

        <!-- 已保存服务器下拉 -->
        <el-form-item v-if="savedServers.length > 0">
          <el-select
            v-model="selectedServerId"
            placeholder="选择已保存的服务器"
            size="large"
            style="width: 100%"
            @change="handleServerSelect"
          >
            <el-option
              v-for="server in savedServers"
              :key="server.id"
              :label="server.name"
              :value="server.id"
            />
          </el-select>
        </el-form-item>

        <el-divider v-if="savedServers.length > 0" />

        <!-- 用户名 -->
        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            size="large"
          />
        </el-form-item>

        <!-- 密码 -->
        <el-form-item prop="password">
          <el-input
            v-model="form.password"
            type="password"
            placeholder="密码"
            :prefix-icon="Lock"
            size="large"
            show-password
          />
        </el-form-item>

        <!-- 记住服务器 -->
        <el-form-item>
          <el-checkbox v-model="form.rememberServer">
            记住此服务器
          </el-checkbox>
        </el-form-item>

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
            style="width: 100%"
          >
            登录
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted } from 'vue';
import { useRouter } from 'vue-router';
import { User, Lock, Link, Check } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { useAuthStore } from '@/stores';
import { getRecentServers, validateServerUrl, getDefaultServer, setApiBaseUrl } from '@/utils/servers';
import type { ServerConfig } from '@/types';

const router = useRouter();
const authStore = useAuthStore();

const formRef = ref<FormInstance>();
const loading = ref(false);
const testing = ref(false);
const savedServers = ref<ServerConfig[]>([]);
const selectedServerId = ref('');

const form = reactive({
  serverUrl: '',
  username: 'admin',
  password: 'admin',
  rememberServer: true,
});

const rules: FormRules = {
  serverUrl: [
    { required: true, message: '请输入服务器地址', trigger: 'blur' },
    { validator: validateUrl, trigger: 'blur' },
  ],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
};

function validateUrl(_rule: unknown, value: string, callback: (error?: Error) => void) {
  if (!validateServerUrl(value)) {
    callback(new Error('请输入有效的 HTTP/HTTPS 地址'));
  } else {
    callback();
  }
}

// 加载已保存的服务器
onMounted(() => {
  savedServers.value = getRecentServers();
  const defaultServer = getDefaultServer();
  if (defaultServer) {
    form.serverUrl = defaultServer.url;
  }
});

// 选择已保存的服务器
function handleServerSelect(serverId: string) {
  const server = savedServers.value.find(s => s.id === serverId);
  if (server) {
    form.serverUrl = server.url;
  }
}

// 测试连接
async function testConnection() {
  if (!validateServerUrl(form.serverUrl)) {
    ElMessage.error('请输入有效的服务器地址');
    return;
  }
  
  testing.value = true;
  try {
    setApiBaseUrl(form.serverUrl);
    // 简单检测：访问根路径
    const response = await fetch(form.serverUrl);
    if (response.ok) {
      ElMessage.success('连接成功');
    } else {
      ElMessage.warning('服务器响应异常');
    }
  } catch (error) {
    ElMessage.error('无法连接到服务器，请检查地址');
  } finally {
    testing.value = false;
  }
}

// 登录
async function handleLogin() {
  if (!formRef.value) return;
  
  await formRef.value.validate(async (valid) => {
    if (!valid) return;
    
    loading.value = true;
    try {
      await authStore.login(
        {
          username: form.username,
          password: form.password,
        },
        form.serverUrl
      );
      ElMessage.success('登录成功');
      router.push('/dashboard');
    } catch (error) {
      ElMessage.error('登录失败，请检查服务器地址、用户名和密码');
    } finally {
      loading.value = false;
    }
  });
}
</script>

<style scoped lang="scss">
.login-page {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  background: linear-gradient(135deg, var(--bg-secondary) 0%, var(--bg-tertiary) 100%);
}

.login-card {
  width: 420px;
}

.login-title {
  margin: 0;
  font-size: 24px;
  color: var(--color-primary);
  text-align: center;
}

.login-subtitle {
  margin: $spacing-xs 0 0;
  font-size: 14px;
  color: var(--text-secondary);
  text-align: center;
}

:deep(.el-input__wrapper) {
  padding-left: $spacing-sm;
}
</style>
```

- [ ] **Step 2: 验证类型检查**

Run: `cd web_dashboard_v2 && npm run type-check`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add web_dashboard_v2/src/views/LoginView.vue
git commit -m "feat(dashboard-v2): 登录页支持服务器地址输入和选择"
```

---

## Task 6: VNPY 后端添加 CORS 支持

**Files:**
- Modify: `vnpy_webtrader/web.py`

- [ ] **Step 1: 在 web.py 中添加 CORS 中间件**

找到 `app = FastAPI()` 之后的位置，添加：

```python
# 创建FastAPI应用
app: FastAPI = FastAPI()

# 添加 CORS 中间件（允许跨域访问）
from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许所有来源，生产环境建议限制具体域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

- [ ] **Step 2: 验证 Python 语法**

Run: `cd F:/vnpy_live && python -m py_compile vnpy_webtrader/web.py`
Expected: 无输出（无语法错误）

- [ ] **Step 3: 提交**

```bash
git add vnpy_webtrader/web.py
git commit -m "feat(webtrader): 添加 CORS 跨域支持，允许 Dashboard 跨域访问"
```

---

## Task 7: 更新 main.ts 移除硬编码 URL 初始化

**Files:**
- Modify: `web_dashboard_v2/src/main.ts`

- [ ] **Step 1: 修改 main.ts**

```typescript
// main.ts
import { createApp } from 'vue';
import ElementPlus from 'element-plus';
import * as ElementPlusIconsVue from '@element-plus/icons-vue';
import 'element-plus/dist/index.css';

import App from './App.vue';
import router from './router';
import { pinia } from './stores';
import { useAuthStore } from './stores';

import '@/assets/styles/global.scss';

const app = createApp(App);

// 注册所有图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component);
}

app.use(pinia);
app.use(router);
app.use(ElementPlus);

// 初始化：如果已登录，恢复服务器连接
const authStore = useAuthStore();
if (authStore.isLoggedIn && authStore.currentServer) {
  // 恢复 API 和 WebSocket 连接
  const { setApiBaseUrl, wsManager } = await import('@/api');
  setApiBaseUrl(authStore.currentServer.url);
  wsManager.setUrl(authStore.currentServer.wsUrl);
  wsManager.connect();
  
  // 设置 WebSocket 监听器
  const { useTradingStore, useMarketStore } = await import('@/stores');
  const tradingStore = useTradingStore();
  const marketStore = useMarketStore();
  tradingStore.setupWebSocketListeners();
  marketStore.setupWebSocketListeners();
  
  // 加载初始数据
  tradingStore.fetchAllData();
  marketStore.fetchContracts();
}

app.mount('#app');
```

- [ ] **Step 2: 验证类型检查**

Run: `cd web_dashboard_v2 && npm run type-check`
Expected: 无错误

- [ ] **Step 3: 提交**

```bash
git add web_dashboard_v2/src/main.ts
git commit -m "feat(dashboard-v2): 移除硬编码 URL，支持从 store 恢复服务器连接"
```

---

## Task 8: 可选 - 删除 .env 中的 API URL（清理）

**Files:**
- Modify: `web_dashboard_v2/.env.example`
- Modify: `web_dashboard_v2/src/env.d.ts`（可选）

- [ ] **Step 1: 更新 .env.example**

```bash
# VNPY Dashboard V2 环境变量
# 注意：API 地址现在通过登录页面动态设置，不再需要此处配置

# 可选：用于某些静态资源或特殊场景
# VITE_APP_TITLE=VNPY Pro
```

- [ ] **Step 2: 提交**

```bash
git add web_dashboard_v2/.env.example
git commit -m "chore(dashboard-v2): 移除 .env 中的 API URL 配置（改为动态设置）"
```

---

## Task 9: 最终验证

- [ ] **Step 1: 类型检查**

Run: `cd web_dashboard_v2 && npm run type-check`
Expected: 无错误

- [ ] **Step 2: 构建测试**

Run: `cd web_dashboard_v2 && npm run build`
Expected: 构建成功

- [ ] **Step 3: 提交所有更改**

```bash
git status
git add -A
git commit -m "feat(dashboard-v2): 完成动态 API URL 功能，支持多服务器管理"
```

---

## 测试步骤

1. **启动 VNPY 后端**
   ```bash
   python run_web.py
   ```

2. **启动 Dashboard**
   ```bash
   cd web_dashboard_v2
   npm run dev
   ```

3. **测试流程**
   - 访问 http://localhost:3000
   - 输入服务器地址 http://localhost:8000
   - 点击"检测"测试连接
   - 输入用户名密码登录
   - 验证登录成功并跳转到 Dashboard
   - 检查 localStorage 中是否保存了服务器配置
   - 刷新页面，验证自动恢复连接

---

## 完成标准

- [ ] 登录页面可以输入服务器地址
- [ ] 支持从已保存服务器列表选择
- [ ] 登录成功后自动保存服务器配置
- [ ] 刷新页面后自动恢复服务器连接
- [ ] VNPY 后端支持 CORS 跨域
- [ ] 类型检查无错误
- [ ] 生产构建成功
