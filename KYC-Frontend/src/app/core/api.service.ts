import { inject, Injectable } from '@angular/core';
import { HttpClient, HttpParams } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_URL } from './config';
import { skipLoading } from './loading.interceptor';
import {
  AccountSummary,
  AdminAuditEntry,
  AdminMfiDetail,
  AdminMfiSummary,
  AgentProfile,
  AgentSummary,
  ApiKeyCreated,
  ApiKeySummary,
  BranchSummary,
  MfiStatus,
  PlatformStats,
  ReportSummary,
  ReviewDecisionResponse,
  ReviewItem,
  VerificationDetail,
  VerificationStats,
  VerificationSummary,
  VerifyResponse,
} from './models';

/**
 * Thin typed wrapper over the KYC-API backend. One method per endpoint;
 * every screen talks to the API through this service so URLs, params and
 * response shapes live in one place. Auth headers are added by the
 * interceptor, so callers never pass a token.
 */
@Injectable({ providedIn: 'root' })
export class ApiService {
  private readonly http = inject(HttpClient);
  private readonly base = API_URL;

  // ---- Verifications & history ----
  listVerifications(status?: string): Observable<VerificationSummary[]> {
    let params = new HttpParams();
    if (status) params = params.set('status', status);
    return this.http.get<VerificationSummary[]>(
      `${this.base}/kyc/verifications`,
      { params },
    );
  }

  getVerification(id: string): Observable<VerificationDetail> {
    return this.http.get<VerificationDetail>(
      `${this.base}/kyc/verifications/${id}`,
    );
  }

  /** One captured image (front/back/selfie) as a blob, auth-scoped. */
  getVerificationImage(id: string, kind: string): Observable<Blob> {
    // Skip the global overlay — the images pop into the already-open popup.
    return this.http.get(
      `${this.base}/kyc/verifications/${id}/images/${kind}`,
      { responseType: 'blob', context: skipLoading() },
    );
  }

  stats(
    start: string,
    end: string,
    branch?: string,
  ): Observable<VerificationStats> {
    let params = new HttpParams().set('start', start).set('end', end);
    if (branch) params = params.set('branch', branch);
    return this.http.get<VerificationStats>(
      `${this.base}/kyc/verifications/stats`,
      { params },
    );
  }

  // ---- Verify (agent capture) ----
  verify(form: FormData): Observable<VerifyResponse> {
    // Runs the whole ML pipeline — tens of seconds. The agent screen shows
    // its own progress for it, so keep the global overlay out of the way.
    return this.http.post<VerifyResponse>(`${this.base}/kyc/verify`, form, {
      context: skipLoading(),
    });
  }

  // ---- Profile ----
  me(): Observable<AgentProfile> {
    return this.http.get<AgentProfile>(`${this.base}/auth/me`);
  }

  // ---- Review queue ----
  listReviews(): Observable<ReviewItem[]> {
    return this.http.get<ReviewItem[]>(`${this.base}/kyc/reviews`);
  }

  decideReview(
    id: string,
    action: 'approve' | 'reject',
    reason?: string,
  ): Observable<ReviewDecisionResponse> {
    return this.http.post<ReviewDecisionResponse>(
      `${this.base}/kyc/reviews/${id}/decision`,
      { action, reason: reason ?? null },
    );
  }

  // ---- Reports ----
  listReports(): Observable<ReportSummary[]> {
    return this.http.get<ReportSummary[]>(`${this.base}/kyc/reports`);
  }

  generateReport(
    period_start: string,
    period_end: string,
  ): Observable<ReportSummary> {
    return this.http.post<ReportSummary>(`${this.base}/kyc/reports`, {
      period_start,
      period_end,
    });
  }

  downloadReportPdf(id: string): Observable<Blob> {
    return this.http.get(`${this.base}/kyc/reports/${id}/pdf`, {
      responseType: 'blob',
    });
  }

  // ---- Agents ----
  listAgents(): Observable<AgentSummary[]> {
    return this.http.get<AgentSummary[]>(`${this.base}/agents`);
  }

  createAgent(payload: {
    full_name: string;
    phone: string;
    pin: string;
    branch_id: string;
  }): Observable<AgentSummary> {
    return this.http.post<AgentSummary>(`${this.base}/agents`, payload);
  }

  updateAgent(
    id: string,
    payload: {
      full_name?: string;
      branch_id?: string;
      status?: 'ACTIVE' | 'DISABLED';
    },
  ): Observable<AgentSummary> {
    return this.http.patch<AgentSummary>(`${this.base}/agents/${id}`, payload);
  }

  resetAgentPin(id: string, pin: string): Observable<AgentSummary> {
    return this.http.post<AgentSummary>(`${this.base}/agents/${id}/reset-pin`, {
      pin,
    });
  }

  // ---- Branches ----
  listBranches(): Observable<BranchSummary[]> {
    return this.http.get<BranchSummary[]>(`${this.base}/branches`);
  }

  createBranch(name: string): Observable<BranchSummary> {
    return this.http.post<BranchSummary>(`${this.base}/branches`, { name });
  }

  // ---- API keys ----
  listApiKeys(): Observable<ApiKeySummary[]> {
    return this.http.get<ApiKeySummary[]>(`${this.base}/api-keys`);
  }

  createApiKey(): Observable<ApiKeyCreated> {
    return this.http.post<ApiKeyCreated>(`${this.base}/api-keys`, {});
  }

  revokeApiKey(id: string): Observable<ApiKeySummary> {
    return this.http.delete<ApiKeySummary>(`${this.base}/api-keys/${id}`);
  }

  // ---- Account ----
  getAccount(): Observable<AccountSummary> {
    return this.http.get<AccountSummary>(`${this.base}/account`);
  }

  updateAccount(payload: {
    name?: string;
    email?: string;
  }): Observable<AccountSummary> {
    return this.http.patch<AccountSummary>(`${this.base}/account`, payload);
  }

  // ---- Platform admin (cross-tenant) ----
  getPlatformStats(): Observable<PlatformStats> {
    return this.http.get<PlatformStats>(`${this.base}/admin/stats`);
  }

  listAdminMfis(): Observable<AdminMfiSummary[]> {
    return this.http.get<AdminMfiSummary[]>(`${this.base}/admin/mfis`);
  }

  getAdminMfi(id: string): Observable<AdminMfiDetail> {
    return this.http.get<AdminMfiDetail>(`${this.base}/admin/mfis/${id}`);
  }

  setMfiStatus(id: string, status: MfiStatus): Observable<AdminMfiDetail> {
    return this.http.patch<AdminMfiDetail>(
      `${this.base}/admin/mfis/${id}/status`,
      { status },
    );
  }

  listAdminAudit(limit = 50, offset = 0): Observable<AdminAuditEntry[]> {
    const params = new HttpParams()
      .set('limit', limit)
      .set('offset', offset);
    return this.http.get<AdminAuditEntry[]>(`${this.base}/admin/audit`, {
      params,
    });
  }
}
