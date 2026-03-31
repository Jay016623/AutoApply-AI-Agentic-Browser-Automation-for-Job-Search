import api from './api';

import type { QueueDepthResponse, SystemHealthResponse } from '@/types/admin';

export async function getSystemHealth(): Promise<SystemHealthResponse> {
  const { data } = await api.get<SystemHealthResponse>('/admin/health');
  return data;
}

export async function getQueueDepths(): Promise<QueueDepthResponse> {
  const { data } = await api.get<QueueDepthResponse>('/admin/queues');
  return data;
}
