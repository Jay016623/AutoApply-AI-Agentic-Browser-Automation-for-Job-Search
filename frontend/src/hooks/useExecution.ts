import { useQuery } from '@tanstack/react-query';

import * as executionService from '@/services/executionService';
import { useTenantQueryScope } from '@/hooks/useTenantQueryScope';
import { useAppStore } from '@/store/useAppStore';
import { canAccess } from '@/services/authz';

export function useManualQueue(page = 1, pageSize = 20) {
  const scope = useTenantQueryScope();
  const role = useAppStore((s) => s.authRole);
  return useQuery({
    queryKey: [...scope, 'execution', 'manual_queue', page, pageSize],
    queryFn: () => executionService.getManualQueue(page, pageSize),
    enabled: canAccess(role, 'operator'),
    refetchInterval: 15_000,
  });
}

export function useRetryQueue(page = 1, pageSize = 20) {
  const scope = useTenantQueryScope();
  const role = useAppStore((s) => s.authRole);
  return useQuery({
    queryKey: [...scope, 'execution', 'retry_queue', page, pageSize],
    queryFn: () => executionService.getRetryQueue(page, pageSize),
    enabled: canAccess(role, 'operator'),
    refetchInterval: 15_000,
  });
}
