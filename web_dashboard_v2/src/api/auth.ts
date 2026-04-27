import { client } from './client';
import type { LoginRequest, LoginResponse } from '@/types';

export const authApi = {
  login(data: LoginRequest): Promise<LoginResponse> {
    const formData = new URLSearchParams();
    formData.append('username', data.username);
    formData.append('password', data.password);

    return client.post('/token', formData, {
      headers: {
        'Content-Type': 'application/x-www-form-urlencoded',
      },
    });
  },
};
