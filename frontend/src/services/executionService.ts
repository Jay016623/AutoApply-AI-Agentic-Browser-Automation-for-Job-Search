import api from './api';

import type { ExecutionAttemptListResponse } from '@/types/execution';

export async function getManualQueue(page = 1, pageSize = 20): Promise<ExecutionAttemptListResponse> {
  const { data } = await api.get<ExecutionAttemptListResponse>('/execution/manual-queue', {
    params: { page, page_size: pageSize },
  });
  return data;
}

export async function getRetryQueue(page = 1, pageSize = 20): Promise<ExecutionAttemptListResponse> {
  const { data } = await api.get<ExecutionAttemptListResponse>('/execution/retry-queue', {
    params: { page, page_size: pageSize },
  });
  return data;
}
