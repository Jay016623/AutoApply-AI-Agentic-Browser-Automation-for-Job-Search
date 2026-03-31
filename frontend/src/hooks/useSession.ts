import { useEffect } from 'react';
import { useAppStore } from '@/store/useAppStore';
import { bootstrapSession } from '@/services/sessionService';

export function useSessionBootstrap() {
  const setSession = useAppStore((s) => s.setSession);

  useEffect(() => {
    const tenantId = import.meta.env.VITE_BOOTSTRAP_TENANT_ID as string | undefined;
    const role = import.meta.env.VITE_BOOTSTRAP_ROLE as string | undefined;
    if (!tenantId || !role) {
      return;
    }

    void bootstrapSession({ tenant_id: tenantId, role })
      .then((resp) => {
        setSession({
          accessToken: resp.access_token,
          tenantId: resp.tenant_id,
          userId: resp.user_id,
          role: resp.role,
        });
      })
      .catch(() => {
        // No-op: backend may have strict auth bootstrap disabled.
      });
  }, [setSession]);
}
