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
        <!-- 服务器地址输入 -->
        <el-form-item prop="serverUrl">
          <el-input
            v-model="form.serverUrl"
            placeholder="服务器地址 (如: http://localhost:8000)"
            :prefix-icon="OfficeBuilding"
            size="large"
          >
            <template #append>
              <el-dropdown v-if="recentServers.length > 0" @command="handleSelectServer">
                <el-button :icon="ArrowDown" />
                <template #dropdown>
                  <el-dropdown-menu>
                    <el-dropdown-item
                      v-for="server in recentServers"
                      :key="server.id"
                      :command="server"
                    >
                      {{ server.name }}
                    </el-dropdown-item>
                  </el-dropdown-menu>
                </template>
              </el-dropdown>
            </template>
          </el-input>
        </el-form-item>

        <el-form-item prop="username">
          <el-input
            v-model="form.username"
            placeholder="用户名"
            :prefix-icon="User"
            size="large"
          />
        </el-form-item>

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

        <el-form-item>
          <el-button
            type="primary"
            size="large"
            :loading="loading"
            @click="handleLogin"
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
import { User, Lock, OfficeBuilding, ArrowDown } from '@element-plus/icons-vue';
import { ElMessage } from 'element-plus';
import type { FormInstance, FormRules } from 'element-plus';
import { useAuthStore } from '@/stores';
import { getRecentServers, getDefaultServer, validateServerUrl } from '@/utils/servers';
import type { ServerConfig } from '@/types';

const router = useRouter();
const authStore = useAuthStore();

const formRef = ref<FormInstance>();
const loading = ref(false);
const recentServers = ref<ServerConfig[]>([]);

const form = reactive({
  serverUrl: '',
  username: '',
  password: '',
});

const rules: FormRules = {
  serverUrl: [
    { required: true, message: '请输入服务器地址', trigger: 'blur' },
    {
      validator: (_rule: unknown, value: string, callback: (error?: Error) => void) => {
        if (!value) {
          callback(new Error('请输入服务器地址'));
          return;
        }
        if (!validateServerUrl(value)) {
          callback(new Error('地址格式错误，应为 http://host:port 或 https://host:port'));
          return;
        }
        callback();
      },
      trigger: 'blur',
    },
  ],
  username: [{ required: true, message: '请输入用户名', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }],
};

// 加载最近使用的服务器
onMounted(() => {
  recentServers.value = getRecentServers();
  const defaultServer = getDefaultServer();
  if (defaultServer) {
    form.serverUrl = defaultServer.url;
  } else {
    // 使用当前页面 host 作为默认值
    const currentHost = window.location.host || 'localhost:8000';
    form.serverUrl = `http://${currentHost}`;
  }
});

// 选择历史服务器
function handleSelectServer(server: ServerConfig) {
  form.serverUrl = server.url;
}

async function handleLogin() {
  if (!formRef.value) return;

  try {
    await formRef.value.validate();
  } catch {
    return;
  }

  // 移除末尾的斜杠
  const serverUrl = form.serverUrl.replace(/\/$/, '');

  loading.value = true;
  try {
    await authStore.login(
      {
        username: form.username,
        password: form.password,
      },
      serverUrl
    );
    ElMessage.success('登录成功');
    router.push('/dashboard');
  } catch {
    ElMessage.error('登录失败，请检查服务器地址、用户名和密码');
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped lang="scss">
.login-page {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--el-fill-color-light);
}

.login-card {
  width: 400px;

  :deep(.el-card__header) {
    text-align: center;
    padding: 30px 20px;
  }

  :deep(.el-form) {
    padding: 10px 0;
  }

  :deep(.el-button--primary) {
    width: 100%;
  }
}

.login-title {
  margin: 0 0 8px;
  font-size: 28px;
  font-weight: 600;
  color: var(--el-color-primary);
}

.login-subtitle {
  margin: 0;
  font-size: 14px;
  color: var(--el-text-color-secondary);
}
</style>
