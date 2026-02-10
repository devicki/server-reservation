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

    if (error.response?.status === 401 && !originalRequest._retry) {
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

// ─── Auth ──────────────────────────────────────────────────
export const authAPI = {
  register: (data: { email: string; password: string; name: string }) =>
    api.post('/auth/register', data),
  login: (data: { email: string; password: string }) =>
    api.post('/auth/login', data),
  me: () => api.get('/auth/me'),
};

// ─── Resources ─────────────────────────────────────────────
export const resourcesAPI = {
  list: () => api.get('/resources/'),
  get: (id: string) => api.get(`/resources/${id}`),
  create: (data: { name: string; description?: string; capacity?: number }) =>
    api.post('/resources/', data),
  update: (id: string, data: Record<string, unknown>) =>
    api.put(`/resources/${id}`, data),
  delete: (id: string) => api.delete(`/resources/${id}`),
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
