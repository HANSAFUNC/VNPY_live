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
