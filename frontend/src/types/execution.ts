export interface ExecutionAttempt {
  id: string;
  application_id: string;
  status: string;
  current_step?: string | null;
  retry_count: number;
  last_error_code?: string | null;
  manual_checkpoint_required: boolean;
  manual_checkpoint_reason?: string | null;
  created_at: string;
  updated_at: string;
}

export interface ExecutionAttemptListResponse {
  items: ExecutionAttempt[];
  total: number;
  page: number;
  page_size: number;
  has_next: boolean;
}
