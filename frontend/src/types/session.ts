export interface SessionBootstrapRequest {
  tenant_id: string;
  role: string;
}

export interface SessionBootstrapResponse {
  access_token: string;
  token_type: string;
  expires_in: number;
  user_id: string;
  tenant_id: string;
  role: string;
}
