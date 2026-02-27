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
export interface ConfigResponse {
  max_reservation_hours: number;
  default_exclude_users: string[];
}

export const configAPI = {
  get: () => api.get<ConfigResponse>('/config'),
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
  checkPermissions: (id: string) =>
    api.post<{
      ok: boolean;
      message?: string | null;
      usermod_ok: boolean;
      pkill_ok: boolean;
      teleport_ok: boolean;
    }>(`/resources/${id}/check-permissions`),
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
export interface FeedbackCommentItem {
  id: string;
  feedback_id: string;
  user_id: string;
  user_name: string;
  content: string;
  created_at: string;
}

export interface FeedbackReactionSummary {
  like: number;
}

export interface FeedbackItem {
  id: string;
  user_id: string;
  user_name: string;
  content: string;
  created_at: string;
  comment_count: number;
  comments: FeedbackCommentItem[];
  reaction_counts: FeedbackReactionSummary;
  user_reaction: string | null;
}

export interface FeedbackListResponse {
  items: FeedbackItem[];
  total: number;
}

export const feedbackAPI = {
  list: (params?: { limit?: number; offset?: number }) =>
    api.get<FeedbackListResponse>('/feedback/', { params }),
  create: (data: { content: string }) => api.post<FeedbackItem>('/feedback/', data),
  createComment: (feedbackId: string, data: { content: string }) =>
    api.post<FeedbackCommentItem>(`/feedback/${feedbackId}/comments`, data),
  toggleReaction: (feedbackId: string) =>
    api.post<FeedbackItem>(`/feedback/${feedbackId}/reactions`),
};

// ─── Session Logs (Admin) ───────────────────────────────────
export type SessionEventType = 'activated' | 'deactivated' | 'error';

export interface SessionLogItem {
  id: string;
  reservation_id: string;
  event_type: SessionEventType;
  details: Record<string, unknown> | null;
  created_at: string;
  server_name: string | null;
  reservation_title: string | null;
  reservation_user_name: string | null;
}

export const sessionLogsAPI = {
  list: (params?: {
    reservation_id?: string;
    start_date?: string;
    end_date?: string;
    server_resource_id?: string;
    reservation_title?: string;
    user_id?: string;
    event_type?: 'activated' | 'deactivated' | 'error';
    limit?: number;
    offset?: number;
  }) => api.get<SessionLogItem[]>('/session-logs/', { params }),
};

// ─── Dashboard ─────────────────────────────────────────────
export interface GpuInfo {
  index: number;
  name: string;
  memory_total_mib: number | null;
  memory_used_mib: number | null;
  memory_free_mib: number | null;
  utilization_gpu_pct: number | null;
  temperature_gpu_c: number | null;
}

export interface ServerGpuHealth {
  server_resource_id: string;
  server_name: string;
  ok: boolean;
  error_message: string | null;
  gpus: GpuInfo[];
}

export const dashboardAPI = {
  timeline: (params: {
    start_date: string;
    end_date: string;
    server_resource_ids?: string[];
  }) => api.get('/dashboard/timeline', { params }),
  myReservations: (params?: Record<string, unknown>) =>
    api.get('/dashboard/my-reservations', { params }),
  status: () => api.get('/dashboard/status'),
  gpuHealth: (params?: { server_resource_id?: string }) =>
    api.get<{ servers: ServerGpuHealth[] }>('/dashboard/gpu-health', { params }),
};
