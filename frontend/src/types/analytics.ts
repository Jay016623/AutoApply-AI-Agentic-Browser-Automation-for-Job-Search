/** Top-level dashboard statistics. */
export interface DashboardStats {
  total_jobs_found: number;
  total_applications: number;
  applications_pending: number;
  applications_applied: number;
  applications_interview: number;
  applications_rejected: number;
  applications_offer: number;
  avg_ats_score: number;
  total_llm_cost_usd: number;
}

/** A single stage in the application funnel. */
export interface ApplicationFunnelData {
  stage: string;
  count: number;
}

/** ATS score histogram bucket. */
export interface ATSScoreDistribution {
  range_label: string;
  count: number;
}

/** LLM provider usage aggregation. */
export interface LLMUsageStats {
  provider: string;
  model: string;
  total_requests: number;
  total_tokens: number;
  total_cost_usd: number;
  avg_latency_ms: number;
}

/** Daily activity timeline entry. */
export interface TimelineEntry {
  date: string;
  applications_created: number;
  applications_applied: number;
  jobs_found: number;
}


/** Conversion slice grouped by a business dimension. */
export interface ConversionSlice {
  key: string;
  applications_sent: number;
  response_rate: number;
  interview_rate: number;
}

/** Business outcome conversion dashboard. */
export interface ConversionDashboard {
  applications_sent: number;
  response_rate: number;
  interview_rate: number;
  per_candidate_success: ConversionSlice[];
  per_source_success: ConversionSlice[];
  per_role_success: ConversionSlice[];
}
