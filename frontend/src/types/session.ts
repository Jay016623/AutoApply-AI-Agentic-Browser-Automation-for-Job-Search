export const SESSION_ROLES = ['owner', 'admin', 'operator', 'read_only'] as const;

export type SessionRole = (typeof SESSION_ROLES)[number];

export interface SessionBootstrapRequest {
  tenant_id: string;
  role: SessionRole;
}

export interface SessionBootstrapResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  tenant_id: string;
  role: SessionRole;
}

export interface AuthSession {
  accessToken: string;
  tenantId: string;
  userId: string;
  role: SessionRole;
  expiresAt: string;
}
