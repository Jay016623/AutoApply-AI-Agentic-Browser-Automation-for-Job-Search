export interface CandidateSettings {
  default_resume_template: string;
  default_cover_letter_template: string;
  target_roles: string[];
  target_locations: string[];
  remote_only: boolean;
  metadata: Record<string, unknown>;
}

export interface Candidate {
  id: string;
  tenant_id?: string | null;
  full_name: string;
  email: string;
  phone?: string | null;
  location?: string | null;
  headline?: string | null;
  is_active: boolean;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface CandidateListResponse {
  items: Candidate[];
  total: number;
}
