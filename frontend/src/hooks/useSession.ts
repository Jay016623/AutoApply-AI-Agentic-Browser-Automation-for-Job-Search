import { useEffect } from 'react';
import { useQueryClient } from '@tanstack/react-query';

import { useAppStore } from '@/store/useAppStore';
import {
  bootstrapSession,
  loadStoredSession,
  persistSession,
  toAuthSession,
} from '@/services/sessionService';

export function useSessionBootstrap() {
  const queryClient = useQueryClient();
  const setSession = useAppStore((s) => s.setSession);
  const setBootstrapped = useAppStore((s) => s.setSessionBootstrapped);

  useEffect(() => {
    const stored = loadStoredSession();
    if (stored) {
      setSession(stored);
      setBootstrapped(true);
      return;
    }

    const tenantId = import.meta.env.VITE_BOOTSTRAP_TENANT_ID as string | undefined;
    const role = import.meta.env.VITE_BOOTSTRAP_ROLE as
      | 'owner'
      | 'admin'
      | 'operator'
      | 'read_only'
      | undefined;
    if (!tenantId || !role) {
      setBootstrapped(true);
      return;
    }

    void bootstrapSession({ tenant_id: tenantId, role })
      .then((resp) => {
        const normalized = toAuthSession(resp);
        setSession(normalized);
        persistSession(normalized);
      })
      .catch(() => {
        setSession(null);
      })
      .finally(() => {
        setBootstrapped(true);
      });
  }, [setSession, setBootstrapped]);

  const tenant = useAppStore((s) => s.authTenantId);
  const user = useAppStore((s) => s.authUserId);
  const role = useAppStore((s) => s.authRole);

  useEffect(() => {
    void queryClient.invalidateQueries();
  }, [queryClient, tenant, user, role]);
}
