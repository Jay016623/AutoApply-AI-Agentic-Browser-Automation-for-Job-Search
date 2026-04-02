import { useMemo } from 'react';

import { useAppStore } from '@/store/useAppStore';

export function useTenantQueryScope(): readonly [string, string, string] {
  const tenantId = useAppStore((s) => s.authTenantId);
  const userId = useAppStore((s) => s.authUserId);
  const role = useAppStore((s) => s.authRole);

  return useMemo(
    () => [tenantId ?? 'tenant:public', userId ?? 'user:anonymous', role ?? 'role:none'] as const,
    [tenantId, userId, role],
  );
}
