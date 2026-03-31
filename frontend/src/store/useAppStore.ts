import { create } from 'zustand';

import type { AuthSession, SessionRole } from '@/types/session';

interface Notification {
  id: string;
  message: string;
  severity: 'success' | 'error' | 'warning' | 'info';
}

interface AppStoreState {
  /** Whether the sidebar drawer is open (mobile). */
  sidebarOpen: boolean;
  /** Active notification for the global snackbar. */
  notification: Notification | null;
  /** Whether the backend WebSocket is connected. */
  wsConnected: boolean;
  accessToken: string | null;
  authTenantId: string | null;
  authUserId: string | null;
  authRole: SessionRole | null;
  sessionExpiresAt: string | null;
  sessionBootstrapped: boolean;

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  showNotification: (message: string, severity?: Notification['severity']) => void;
  clearNotification: () => void;
  setWsConnected: (connected: boolean) => void;
  setSessionBootstrapped: (ready: boolean) => void;
  setSession: (session: AuthSession | null) => void;
}

export const useAppStore = create<AppStoreState>((set) => ({
  sidebarOpen: false,
  notification: null,
  wsConnected: false,
  accessToken: null,
  authTenantId: null,
  authUserId: null,
  authRole: null,
  sessionExpiresAt: null,
  sessionBootstrapped: false,

  toggleSidebar: () => set((state) => ({ sidebarOpen: !state.sidebarOpen })),
  setSidebarOpen: (open) => set({ sidebarOpen: open }),

  showNotification: (message, severity = 'info') =>
    set({
      notification: {
        id: crypto.randomUUID(),
        message,
        severity,
      },
    }),

  clearNotification: () => set({ notification: null }),
  setWsConnected: (connected) => set({ wsConnected: connected }),
  setSessionBootstrapped: (ready) => set({ sessionBootstrapped: ready }),
  setSession: (session) =>
    set(
      session
        ? {
            accessToken: session.accessToken,
            authTenantId: session.tenantId,
            authUserId: session.userId,
            authRole: session.role,
            sessionExpiresAt: session.expiresAt,
          }
        : {
            accessToken: null,
            authTenantId: null,
            authUserId: null,
            authRole: null,
            sessionExpiresAt: null,
          },
    ),
}));
