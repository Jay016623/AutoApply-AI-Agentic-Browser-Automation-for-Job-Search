import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

import { useTenantQueryScope } from '@/hooks/useTenantQueryScope';
import * as appService from '@/services/applicationService';
import type {
  ApplicationCreate,
  ApplicationBatchCreate,
  ApplicationStatusUpdate,
} from '@/types/application';

const APPS_KEY = ['applications'] as const;

/** Fetch paginated application listings. */
export function useApplications(page = 1, pageSize = 20, status?: string) {
  const scope = useTenantQueryScope();
  return useQuery({
    queryKey: [...scope, ...APPS_KEY, 'list', page, pageSize, status],
    queryFn: () => appService.listApplications(page, pageSize, status),
  });
}

/** Fetch a single application by ID. */
export function useApplication(appId: string | undefined) {
  const scope = useTenantQueryScope();
  return useQuery({
    queryKey: [...scope, ...APPS_KEY, 'detail', appId],
    queryFn: () => appService.getApplication(appId!),
    enabled: !!appId,
  });
}

/** Create a single application. */
export function useCreateApplication() {
  const queryClient = useQueryClient();
  const scope = useTenantQueryScope();
  return useMutation({
    mutationFn: (data: ApplicationCreate) => appService.createApplication(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...scope, ...APPS_KEY] });
    },
  });
}

/** Batch create applications. */
export function useBatchCreateApplications() {
  const queryClient = useQueryClient();
  const scope = useTenantQueryScope();
  return useMutation({
    mutationFn: (data: ApplicationBatchCreate) => appService.batchCreateApplications(data),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...scope, ...APPS_KEY] });
    },
  });
}

/** Approve a pending application. */
export function useApproveApplication() {
  const queryClient = useQueryClient();
  const scope = useTenantQueryScope();
  return useMutation({
    mutationFn: (appId: string) => appService.approveApplication(appId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...scope, ...APPS_KEY] });
    },
  });
}

/** Update an application's status. */
export function useUpdateApplicationStatus() {
  const queryClient = useQueryClient();
  const scope = useTenantQueryScope();
  return useMutation({
    mutationFn: ({ appId, update }: { appId: string; update: ApplicationStatusUpdate }) =>
      appService.updateApplicationStatus(appId, update),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: [...scope, ...APPS_KEY] });
    },
  });
}
