import axios from 'axios';
import type { InternalAxiosRequestConfig } from 'axios';

import type { ApiError } from '@/types/api';
import { useAppStore } from '@/store/useAppStore';

/** Pre-configured Axios instance pointing at the backend API. */
const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30_000,
});

function applyAuthContext(config: InternalAxiosRequestConfig): InternalAxiosRequestConfig {
  const session = useAppStore.getState();

  config.headers = config.headers ?? {};
  config.headers['X-Trace-Id'] = crypto.randomUUID();

  if (session.accessToken) {
    config.headers['Authorization'] = `Bearer ${session.accessToken}`;
  }
  if (session.authTenantId) {
    config.headers['X-Tenant-Id'] = session.authTenantId;
  }
  if (session.authUserId) {
    config.headers['X-User-Id'] = session.authUserId;
  }
  if (session.authRole) {
    config.headers['X-Role'] = session.authRole;
  }

  // Dev bootstrap fallback for first token mint.
  if (!session.accessToken && import.meta.env.VITE_BOOTSTRAP_USER_ID) {
    config.headers['X-User-Id'] = import.meta.env.VITE_BOOTSTRAP_USER_ID;
  }

  return config;
}

api.interceptors.request.use(applyAuthContext);

/** Normalize error responses into a consistent ApiError shape. */
api.interceptors.response.use(
  (response) => response,
  (error: unknown) => {
    if (axios.isAxiosError(error) && error.response) {
      const data = error.response.data as Record<string, unknown>;
      const apiError: ApiError = {
        detail: typeof data['detail'] === 'string' ? data['detail'] : 'An unexpected error occurred',
        status_code: error.response.status,
        trace_id: typeof data['trace_id'] === 'string' ? data['trace_id'] : undefined,
      };
      return Promise.reject(apiError);
    }
    const fallback: ApiError = {
      detail: 'Network error. Please check your connection.',
      status_code: 0,
    };
    return Promise.reject(fallback);
  },
);

export default api;
