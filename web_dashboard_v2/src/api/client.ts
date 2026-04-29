import axios from 'axios';
import { clearToken, getToken } from '@/utils/storage';

// 统一 API 响应格式
interface ApiResponse<T> {
  success: boolean;
  data?: T;
  error?: {
    code: string;
    message: string;
  };
}

// 创建 axios 实例
export const client = axios.create({
  baseURL: '/api',  // 统一使用 /api 前缀
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

/**
 * 设置 API baseURL
 */
export function setApiBaseUrl(baseURL: string): void {
  client.defaults.baseURL = `${baseURL}/api`;
}

/**
 * 获取当前 baseURL
 */
export function getApiBaseUrl(): string | undefined {
  return client.defaults.baseURL;
}
