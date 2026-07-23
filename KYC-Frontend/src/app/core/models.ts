/**
 * TypeScript mirrors of the backend Pydantic schemas (app/schemas/*).
 * Keep these in sync with the API; field names match the JSON exactly.
 */

export type VerificationStatus =
  | 'VERIFIED'
  | 'PENDING'
  | 'REJECTED'
  | 'APPROVED';

export type DocumentType = 'NIC' | 'PASSPORT';
export type SubmissionMethod = 'DASHBOARD' | 'API';
export type Sex = 'M' | 'F';
export type DuplicateResolution = 'PENDING' | 'CONFIRMED' | 'DISMISSED';
export type ReviewAction = 'approve' | 'reject';
export type AgentRole = 'AGENT' | 'MANAGER' | 'ADMIN';
export type AgentStatus = 'ACTIVE' | 'DISABLED';

// ---- Verifications ----
export interface VerificationSummary {
  id: string;
  client_id: string;
  client_name: string | null;
  status: VerificationStatus;
  reject_reason: string | null;
  confidence_score: number | null;
  submission_method: SubmissionMethod;
  agent_name: string | null;
  branch_name: string | null;
  created_at: string;
  reviewed: boolean;
  review_reason: string | null;
}

export interface ExtractedData {
  full_name: string | null;
  id_number: string | null;
  date_of_birth: string | null;
  place_of_birth: string | null;
  expiry_date: string | null;
  sex: Sex | null;
  occupation: string | null;
  field_confidences: Record<string, number> | null;
}

export interface LivenessResult {
  passed: boolean;
  method: string;
  anti_spoof_score: number | null;
  landmarks_detected: boolean;
}

export interface FaceMatchResult {
  match_score: number;
  verified: boolean;
  threshold: number;
}

export interface DuplicateFlag {
  matched_client_id: string | null;
  similarity_score: number;
  resolution: DuplicateResolution;
}

/** Which captured images exist for a verification. */
export type ImageKind = 'ID_FRONT' | 'ID_BACK' | 'SELFIE';

export interface VerificationDetail extends VerificationSummary {
  processed_at: string | null;
  extracted_data: ExtractedData | null;
  liveness_result: LivenessResult | null;
  face_match_result: FaceMatchResult | null;
  duplicate_flags: DuplicateFlag[];
  available_images: ImageKind[];
}

export interface VerifyResponse {
  verification_id: string;
  client_id: string;
  status: VerificationStatus;
  confidence_score: number | null;
  reject_reason: string | null;
  quota_remaining: number;
  quota_warning: boolean;
}

// ---- Stats (manager dashboard) ----
export interface DayBucket {
  date: string;
  verified: number;
  pending: number;
  rejected: number;
}

export interface BranchBucket {
  branch: string;
  count: number;
}

export interface VerificationStats {
  period_start: string;
  period_end: string;
  total: number;
  verified: number;
  pending: number;
  rejected: number;
  by_status: Record<string, number>;
  per_day: DayBucket[];
  by_branch: BranchBucket[];
  avg_processing_seconds: number | null;
}

// ---- Review ----
export interface ReviewItem {
  id: string;
  client_id: string;
  client_name: string | null;
  status: VerificationStatus;
  reject_reason: string | null;
  confidence_score: number | null;
  agent_name: string | null;
  branch_name: string | null;
  flagged_duplicate: boolean;
  created_at: string;
}

export interface ReviewDecisionResponse {
  verification_id: string;
  status: VerificationStatus;
}

// ---- Reports ----
export interface ReportSummary {
  id: string;
  period_start: string;
  period_end: string;
  total_verifications: number;
  status_breakdown: Record<string, number> | null;
  format: 'PDF';
  generated_at: string;
}

// ---- Agents & branches ----
export interface AgentSummary {
  id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  branch_id: string | null;
  branch_name: string | null;
  role: AgentRole;
  status: AgentStatus;
}

export interface BranchSummary {
  id: string;
  name: string;
}

// ---- API keys ----
export interface ApiKeySummary {
  id: string;
  prefix: string;
  is_active: boolean;
  created_at: string;
  last_used_at: string | null;
}

export interface ApiKeyCreated {
  id: string;
  prefix: string;
  full_key: string;
  created_at: string;
}

// ---- Account ----
export interface AccountSummary {
  id: string;
  name: string;
  email: string;
  plan_name: string | null;
  verification_quota: number | null;
  current_period_usage: number;
}

// ---- Profile (/auth/me) ----
export interface AgentProfile {
  agent_id: string;
  full_name: string;
  email: string | null;
  phone: string | null;
  role: AgentRole;
  branch: string | null;
  // Null for a platform admin, who belongs to no single MFI.
  mfi_account_id: string | null;
  mfi_name: string | null;
}

// ---- Platform admin (cross-tenant) ----
export type MfiStatus = 'ACTIVE' | 'SUSPENDED' | 'PENDING';

export interface PlanBucket {
  plan: string;
  count: number;
}

export interface DayCount {
  date: string;
  count: number;
}

export interface QuotaRow {
  id: string;
  name: string;
  plan: string | null;
  usage: number;
  quota: number | null;
  pct: number;
}

export interface PlatformStats {
  total_mfis: number;
  active_mfis: number;
  suspended_mfis: number;
  pending_mfis: number;
  total_verifications: number;
  total_users: number;
  warning_count: number;
  by_plan: PlanBucket[];
  per_day: DayCount[];
  quota_rows: QuotaRow[];
}

export interface AdminMfiSummary {
  id: string;
  name: string;
  email: string;
  plan: string | null;
  status: MfiStatus;
  usage: number;
  quota: number | null;
  verifications: number;
  users: number;
  api_keys: number;
  branches: number;
  created_at: string;
}

export interface AdminApiKeySummary {
  prefix: string;
  is_active: boolean;
  last_used_at: string | null;
}

export interface AdminAgentSummary {
  id: string;
  full_name: string;
  branch: string | null;
  role: AgentRole;
  status: 'ACTIVE' | 'DISABLED';
  verifications: number;
}

export interface MfiPerformance {
  verified: number;
  pending: number;
  rejected: number;
  duplicates: number;
  avg_processing_seconds: number | null;
}

export interface AdminMfiDetail {
  id: string;
  name: string;
  email: string;
  status: MfiStatus;
  plan: string | null;
  quota: number | null;
  usage: number;
  max_branches: number | null;
  max_agents: number | null;
  api_access: boolean;
  this_month: number;
  last_month: number;
  avg_per_day: number;
  billing_cycle_start: string | null;
  created_at: string;
  api_keys: AdminApiKeySummary[];
  agents: AdminAgentSummary[];
  performance: MfiPerformance;
}
