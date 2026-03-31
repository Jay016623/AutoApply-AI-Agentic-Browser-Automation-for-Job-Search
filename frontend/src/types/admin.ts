export interface SystemHealthResponse {
  api: string;
  redis: string;
  workflow_v2_enabled: boolean;
  tenant_enforcement: boolean;
}

export interface QueueDepthResponse {
  apply: number;
  apply_dead_letter: number;
  scrape: number;
  generate: number;
}
