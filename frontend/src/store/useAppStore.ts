import { create } from 'zustand';

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
  authRole: string | null;

  toggleSidebar: () => void;
  setSidebarOpen: (open: boolean) => void;
  showNotification: (message: string, severity?: Notification['severity']) => void;
  clearNotification: () => void;
  setWsConnected: (connected: boolean) => void;
  setSession: (session: {
    accessToken: string;
    tenantId: string;
    userId: string;
    role: string;
  } | null) => void;
}

export const useAppStore = create<AppStoreState>((set) => ({
  sidebarOpen: false,
  notification: null,
  wsConnected: false,
  accessToken: null,
  authTenantId: null,
  authUserId: null,
  authRole: null,

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
  setSession: (session) =>
    set(
      session
        ? {
            accessToken: session.accessToken,
            authTenantId: session.tenantId,
            authUserId: session.userId,
            authRole: session.role,
          }
        : {
            accessToken: null,
            authTenantId: null,
            authUserId: null,
            authRole: null,
          },
    ),
}));
