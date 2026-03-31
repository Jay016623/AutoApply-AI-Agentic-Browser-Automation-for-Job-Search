import api from './api';
import type { SessionBootstrapRequest, SessionBootstrapResponse } from '@/types/session';

export async function bootstrapSession(payload: SessionBootstrapRequest): Promise<SessionBootstrapResponse> {
  const { data } = await api.post<SessionBootstrapResponse>('/admin/session/bootstrap', payload);
  return data;
}
