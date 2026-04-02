import api from './api';

import type {
  AuthSession,
  SessionBootstrapRequest,
  SessionBootstrapResponse,
  SessionRole,
} from '@/types/session';

const SESSION_STORAGE_KEY = 'autoapply.session.v1';

function isValidRole(role: unknown): role is SessionRole {
  return role === 'owner' || role === 'admin' || role === 'operator' || role === 'read_only';
}

export function toAuthSession(payload: SessionBootstrapResponse): AuthSession {
  return {
    accessToken: payload.access_token,
    tenantId: payload.tenant_id,
    userId: payload.user_id,
    role: payload.role,
    expiresAt: new Date(Date.now() + payload.expires_in * 1000).toISOString(),
  };
}

export function loadStoredSession(): AuthSession | null {
  const raw = localStorage.getItem(SESSION_STORAGE_KEY);
  if (!raw) {
    return null;
  }
  try {
    const parsed = JSON.parse(raw) as Partial<AuthSession>;
    if (
      typeof parsed.accessToken !== 'string' ||
      typeof parsed.tenantId !== 'string' ||
      typeof parsed.userId !== 'string' ||
      !isValidRole(parsed.role) ||
      typeof parsed.expiresAt !== 'string'
    ) {
      return null;
    }
    if (new Date(parsed.expiresAt).getTime() <= Date.now()) {
      localStorage.removeItem(SESSION_STORAGE_KEY);
      return null;
    }
    return parsed as AuthSession;
  } catch {
    return null;
  }
}

export function persistSession(session: AuthSession | null): void {
  if (!session) {
    localStorage.removeItem(SESSION_STORAGE_KEY);
    return;
  }
  localStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(session));
}

export async function bootstrapSession(payload: SessionBootstrapRequest): Promise<SessionBootstrapResponse> {
  const { data } = await api.post<SessionBootstrapResponse>('/admin/session/bootstrap', payload);
  return data;
}
