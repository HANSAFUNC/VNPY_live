import axios from 'axios';
import type { LoginRequest, LoginResponse } from '@/types';

export const authApi = {
  login(data: LoginRequest): Promise<LoginResponse> {
    const formData = new URLSearchParams();
    formData.append('username', data.username);
    formData.append('password', data.password);

    // 登录接口走 /api/token -> Vite 代理 -> /token
    return axios.post('/api/token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    }).then(res => res.data);
  },
};
