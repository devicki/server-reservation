import axios from 'axios';

const api = axios.create({
  baseURL: '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
});

// Request interceptor to add auth token
api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor for token refresh
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;
    if (!originalRequest) return Promise.reject(error);

    const isLoginOrRegister =
      originalRequest?.url?.includes('/auth/login') ||
      originalRequest?.url?.includes('/auth/register');

    // 로그인/회원가입 실패(401)는 그대로 reject → 화면에서 에러 메시지 표시
    if (error.response?.status === 401 && !originalRequest._retry && !isLoginOrRegister) {
      originalRequest._retry = true;

      const refreshToken = localStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const res = await axios.post('/api/v1/auth/refresh', {
            refresh_token: refreshToken,
          });
          const { access_token, refresh_token: newRefresh } = res.data;
          localStorage.setItem('access_token', access_token);
          localStorage.setItem('refresh_token', newRefresh);
          originalRequest.headers.Authorization = `Bearer ${access_token}`;
          return api(originalRequest);
        } catch {
          localStorage.removeItem('access_token');
          localStorage.removeItem('refresh_token');
          window.location.href = '/login';
        }
      } else {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

export default api;

// ─── Config (public) ───────────────────────────────────────
export const configAPI = {
  get: () => api.get<{ max_reservation_hours: number }>('/config'),
};

// ─── Auth ──────────────────────────────────────────────────
export const authAPI = {
  register: (data: { email: string; password: string; name: string }) =>
    api.post('/auth/register', data),
  login: (data: { email: string; password: string }) =>
    api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
};

// ─── Users (Admin) ──────────────────────────────────────────
export const usersAPI = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get('/users/', { params }),
  update: (id: string, data: { role?: 'user' | 'admin'; is_active?: boolean }) =>
    api.patch(`/users/${id}`, data),
};

// ─── Resources ─────────────────────────────────────────────
export interface ResourceItem {
  id: string;
  name: string;
  description: string | null;
  capacity: number | null;
  is_active: boolean;
  host: string | null;
  ssh_port: number;
  ssh_username: string | null;
  ssh_private_key?: string | null;
  account_exclusions: string | null;
  created_at: string;
  updated_at: string;
}

export const resourcesAPI = {
  list: (params?: { is_active?: boolean; include_inactive?: boolean }) =>
    api.get<{ items: ResourceItem[]; total: number }>('/resources/', { params }),
  get: (id: string) => api.get<ResourceItem>(`/resources/${id}`),
  create: (data: {
    name: string;
    description?: string;
    capacity?: number;
    host?: string;
    ssh_port?: number;
    ssh_username?: string;
    ssh_private_key?: string;
    account_exclusions?: string;
  }) => api.post('/resources/', data),
  update: (
    id: string,
    data: {
      name?: string;
      description?: string;
      capacity?: number;
      is_active?: boolean;
      host?: string;
      ssh_port?: number;
      ssh_username?: string;
      ssh_private_key?: string;
      account_exclusions?: string | null;
    }
  ) => api.put(`/resources/${id}`, data),
  delete: (id: string) => api.delete(`/resources/${id}`),
  testConnection: (id: string) =>
    api.post<{ ok: boolean; message: string; stdout?: string; stderr?: string }>(
      `/resources/${id}/test-connection`
    ),
  getRemoteUsers: (id: string) =>
    api.get<{ items: { username: string }[] }>(`/resources/${id}/remote-users`),
};

// ─── Reservations ──────────────────────────────────────────
export const reservationsAPI = {
  list: (params?: Record<string, unknown>) =>
    api.get('/reservations/', { params }),
  get: (id: string) => api.get(`/reservations/${id}`),
  create: (data: {
    server_resource_id: string;
    title: string;
    description?: string;
    account_name?: string;
    start_at: string;
    end_at: string;
  }) => api.post('/reservations/', data),
  update: (id: string, data: Record<string, unknown>) =>
    api.put(`/reservations/${id}`, data),
  cancel: (id: string) => api.delete(`/reservations/${id}`),
  checkAvailability: (params: {
    server_resource_id: string;
    start_at: string;
    end_at: string;
  }) => api.get('/reservations/check-availability', { params }),
};

// ─── Feedback (시스템 개선 의견) ─────────────────────────────
export const feedbackAPI = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get('/feedback/', { params }),
  create: (data: { content: string }) => api.post('/feedback/', data),
};

// ─── Dashboard ─────────────────────────────────────────────
export const dashboardAPI = {
  timeline: (params: {
    start_date: string;
    end_date: string;
    server_resource_ids?: string[];
  }) => api.get('/dashboard/timeline', { params }),
  myReservations: (params?: Record<string, unknown>) =>
    api.get('/dashboard/my-reservations', { params }),
  status: () => api.get('/dashboard/status'),
};
