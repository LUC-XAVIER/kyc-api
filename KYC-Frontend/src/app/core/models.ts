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
  status: VerificationStatus;
  reject_reason: string | null;
  confidence_score: number | null;
  created_at: string;
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

export interface VerificationDetail extends VerificationSummary {
  submission_method: SubmissionMethod;
  processed_at: string | null;
  extracted_data: ExtractedData | null;
  liveness_result: LivenessResult | null;
  face_match_result: FaceMatchResult | null;
  duplicate_flags: DuplicateFlag[];
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
  status: VerificationStatus;
  reject_reason: string | null;
  confidence_score: number | null;
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
  mfi_account_id: string;
  mfi_name: string;
}
