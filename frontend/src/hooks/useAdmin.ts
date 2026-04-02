import { useQuery } from '@tanstack/react-query';

import * as adminService from '@/services/adminService';
import { useTenantQueryScope } from '@/hooks/useTenantQueryScope';
import { useAppStore } from '@/store/useAppStore';
import { canAccess } from '@/services/authz';

export function useSystemHealth() {
  const scope = useTenantQueryScope();
  const role = useAppStore((s) => s.authRole);
  return useQuery({
    queryKey: [...scope, 'admin', 'health'],
    queryFn: () => adminService.getSystemHealth(),
    enabled: canAccess(role, 'operator'),
    refetchInterval: 30_000,
  });
}

export function useQueueDepths() {
  const scope = useTenantQueryScope();
  const role = useAppStore((s) => s.authRole);
  return useQuery({
    queryKey: [...scope, 'admin', 'queues'],
    queryFn: () => adminService.getQueueDepths(),
    enabled: canAccess(role, 'operator'),
    refetchInterval: 15_000,
  });
}
