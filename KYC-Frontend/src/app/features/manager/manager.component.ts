import { Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LoadingService } from '../../core/loading.service';
import { PLANS } from '../../core/plans';
import { VerificationScoresComponent } from '../../shared/verification-scores.component';
import {
  AccountSummary,
  AgentSummary,
  ApiKeyCreated,
  BranchSummary,
  ImageKind,
  ReportSummary,
  ReviewItem,
  VerificationDetail,
  VerificationStats,
  VerificationSummary,
} from '../../core/models';
import {
  isValidPin,
  normalizeCmPhone,
  phoneDigits,
} from '../../core/validators';

/** ISO yyyy-mm-dd for a Date (local calendar day). */
function isoDate(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(
    d.getDate(),
  ).padStart(2, '0')}`;
}

function daysAgo(n: number): string {
  const d = new Date();
  d.setDate(d.getDate() - n);
  return isoDate(d);
}

function pct(part: number | undefined, total: number | undefined): number {
  if (!total || part == null) return 0;
  return Math.round((part / total) * 1000) / 10;
}

/** Pull the backend error message out of an HttpErrorResponse, else fallback. */
function apiMessage(err: unknown, fallback: string): string {
  const body = (err as { error?: { error?: { message?: string } } })?.error;
  return body?.error?.message ?? fallback;
}

type ManagerPage =
  | 'dashboard'
  | 'review'
  | 'history'
  | 'reports'
  | 'agents'
  | 'apikeys'
  | 'settings'
  | 'pricing';

type SettingsTab =
  | 'Subscription'
  | 'MFI profile'
  | 'Notifications'
  | 'Security'
  | 'Danger zone';

/** A key card shaped for the template (built from ApiKeySummary/Created). */
interface ApiKeyRow {
  id: string;
  prefix: string;
  created: string;
  lastUsed: string;
  active: boolean;
  copied: boolean;
  /** Present only right after creation — the one time we can show it. */
  fullKey?: string;
}

type ReviewReason = 'Duplicate' | 'Low confidence';
type HistoryStatus =
  | 'Verified'
  | 'Pending'
  | 'Rejected'
  | 'Approved';

/** A review-queue row shaped for the template (built from ReviewItem). */
interface QueueRow {
  id: string;
  initials: string;
  name: string;
  client: string;
  agent: string;
  reason: ReviewReason;
  score: string;
  submitted: string;
}

/** A history row shaped for the template (built from VerificationSummary). */
interface HistoryRow {
  /** The MFI's client reference, shown in the table. */
  id: string;
  /** The verification's own UUID — used to open its detail. */
  verificationId: string;
  name: string;
  date: string;
  branch: string;
  agent: string;
  channel: 'Dashboard' | 'API';
  status: HistoryStatus;
  score: string;
}

const HISTORY_PAGE_SIZE = 6;

/** Display order and labels for the captured images in the detail popup. */
const IMAGE_ORDER: ImageKind[] = ['ID_FRONT', 'ID_BACK', 'SELFIE'];
const IMAGE_LABELS: Record<ImageKind, string> = {
  ID_FRONT: 'ID front',
  ID_BACK: 'ID back',
  SELFIE: 'Selfie',
};

/** Smallest top-of-scale for the per-day chart, in verifications. */
const CHART_MIN_SCALE = 5;

/** Initials from a name, e.g. "FOTSO Jean" → "FJ". */
function initialsOf(name: string): string {
  return (
    name
      .trim()
      .split(/\s+/)
      .map((w) => w[0])
      .slice(0, 2)
      .join('')
      .toUpperCase() || '—'
  );
}

/** VERIFIED → Verified, for the status badge/label. */
function statusLabel(s: string): HistoryStatus {
  return (s.charAt(0) + s.slice(1).toLowerCase()) as HistoryStatus;
}

/** A 0–1 confidence as a percentage string, or an em dash. */
function scoreLabel(score: number | null): string {
  return score == null ? '—' : `${Math.round(score * 100)}%`;
}

/** "17 Jun, 14:32" from an ISO timestamp. */
function dateLabel(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  const time = d.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${date}, ${time}`;
}

/** Rough "2 min ago" / "3h ago" / "5d ago" from an ISO timestamp. */
function relativeTime(iso: string): string {
  const secs = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (secs < 60) return 'just now';
  if (secs < 3600) return `${Math.floor(secs / 60)} min ago`;
  if (secs < 86400) return `${Math.floor(secs / 3600)}h ago`;
  return `${Math.floor(secs / 86400)}d ago`;
}

const NOTIF_DEFS = [
  { key: 'quota', title: 'Quota warning alert', desc: 'Get notified when usage reaches 80% of monthly quota' },
  { key: 'pending', title: 'New PENDING case', desc: 'Email alert when a verification requires your review' },
  { key: 'weekly', title: 'Weekly summary report', desc: 'Receive a weekly digest of verification activity' },
  { key: 'maintenance', title: 'System maintenance alerts', desc: 'Be informed of scheduled downtime or updates' },
] as const;

const SETTINGS_TABS: SettingsTab[] = [
  'Subscription', 'MFI profile', 'Notifications', 'Security', 'Danger zone',
];

/**
 * Manager application: Dashboard, Review queue, History (this slice) plus
 * Reports / Agents / API keys / Settings (next slice). Signals-based, mock
 * data until the backend-integration phase.
 */
@Component({
  selector: 'app-manager',
  imports: [VerificationScoresComponent],
  templateUrl: './manager.component.html',
  styleUrl: './manager.component.scss',
})
export class ManagerComponent {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly loading = inject(LoadingService);
  readonly user = this.auth.principal;

  constructor() {
    this.loadStats();
    this.loadAccount();
  }
  readonly userInitials = computed(() => {
    const name = this.user()?.full_name ?? '';
    return (
      name
        .split(/\s+/)
        .map((w) => w[0])
        .slice(0, 2)
        .join('')
        .toUpperCase() || 'M'
    );
  });

  logout(): void {
    this.auth.logout();
  }

  readonly page = signal<ManagerPage>('dashboard');

  // Review queue (real data)
  readonly reviewData = signal<ReviewItem[]>([]);
  readonly reviewLoading = signal(false);
  readonly reviewError = signal(false);
  readonly activeCaseId = signal<string | null>(null);
  readonly activeDetail = signal<VerificationDetail | null>(null);
  // The read-only detail popup opened from a History row (any status).
  readonly detailModalOpen = signal(false);
  // Captured images for the open popup, as object URLs (revoked on close).
  readonly detailImages = signal<{ kind: ImageKind; url: string }[]>([]);
  readonly reviewReason = signal<'all' | ReviewReason>('all');
  readonly reviewSearch = signal('');
  readonly deciding = signal(false);

  // History (real data)
  readonly historyData = signal<VerificationSummary[]>([]);
  readonly historyLoading = signal(false);
  readonly historyError = signal(false);
  readonly historyStatus = signal<'All' | HistoryStatus>('All');
  readonly historySearch = signal('');
  readonly historyPage = signal(1);

  // ---- Dashboard (real stats) ----
  readonly stats = signal<VerificationStats | null>(null);
  readonly statsLoading = signal(false);
  readonly statsError = signal(false);
  readonly dashStart = signal(daysAgo(13));
  readonly dashEnd = signal(isoDate(new Date()));

  loadStats(): void {
    this.statsLoading.set(true);
    this.statsError.set(false);
    this.api.stats(this.dashStart(), this.dashEnd()).subscribe({
      next: (s) => {
        this.stats.set(s);
        this.statsLoading.set(false);
      },
      error: () => {
        this.statsError.set(true);
        this.statsLoading.set(false);
      },
    });
  }

  readonly kpiTotal = computed(() => this.stats()?.total ?? 0);
  readonly kpiTotalLabel = computed(() =>
    this.kpiTotal().toLocaleString('en-US'),
  );
  readonly verifiedPct = computed(() =>
    pct(this.stats()?.verified, this.stats()?.total),
  );
  readonly pendingPct = computed(() =>
    pct(this.stats()?.pending, this.stats()?.total),
  );
  readonly rejectedPct = computed(() =>
    pct(this.stats()?.rejected, this.stats()?.total),
  );
  readonly avgProcessing = computed(() => {
    const s = this.stats()?.avg_processing_seconds;
    return s == null ? '—' : `${s.toFixed(1)}s`;
  });

  readonly dashRangeLabel = computed(() => {
    const fmt = (iso: string) =>
      new Date(iso).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
      });
    return `${fmt(this.dashStart())} – ${fmt(this.dashEnd())}, ${new Date(
      this.dashEnd(),
    ).getFullYear()}`;
  });

  /** By-branch bars, widths scaled to the busiest branch. */
  readonly branches = computed(() => {
    const list = this.stats()?.by_branch ?? [];
    const max = Math.max(1, ...list.map((b) => b.count));
    return list.map((b) => ({
      name: b.branch,
      value: b.count,
      pct: (b.count / max) * 100,
    }));
  });

  readonly historyStatuses: ('All' | HistoryStatus)[] = [
    'All', 'Verified', 'Pending', 'Rejected', 'Approved',
  ];

  readonly title = computed<[string, string]>(() => {
    // Subtitles carry the logged-in MFI's own name and plan, never a
    // hardcoded one. Falls back gracefully while the account is loading.
    const org = this.account()?.name ?? 'Your institution';
    const plan = this.account()?.plan_name;
    // "GROWTH" -> " · Growth plan"; empty until the account has loaded.
    const planLabel = plan
      ? ` · ${plan.charAt(0) + plan.slice(1).toLowerCase()} plan`
      : '';
    const map: Record<ManagerPage, [string, string]> = {
      dashboard: ['Verification statistics', `${org} · All branches`],
      review: ['Pending review cases', org],
      history: ['Verification history', `${org} · All branches`],
      reports: ['Compliance reports', 'Generate COBAC-ready verification records'],
      agents: ['Agent accounts', `${org}${planLabel}`],
      apikeys: ['API keys', `${org}${planLabel}`],
      settings: ['Settings', org],
      pricing: ['Subscription plans', 'Choose the plan that fits your institution'],
    };
    return map[this.page()];
  });

  // ---- Dashboard chart geometry (from real stats) ----
  readonly dayBars = computed(() => {
    const days = this.stats()?.per_day ?? [];
    // Floor the scale at CHART_MIN_SCALE. Scaling purely to the busiest day
    // means the first-ever verification draws a full-height bar that then
    // shrinks as other days fill in — the chart appears to go backwards.
    const max = Math.max(
      CHART_MIN_SCALE,
      ...days.map((d) => d.verified + d.pending + d.rejected),
    );
    return days.map((d) => {
      const total = d.verified + d.pending + d.rejected;
      const when = new Date(d.date).toLocaleDateString('en-GB', {
        day: 'numeric',
        month: 'short',
      });
      return {
        label: String(new Date(d.date).getDate()),
        v: (d.verified / max) * 100,
        p: (d.pending / max) * 100,
        r: (d.rejected / max) * 100,
        // Shown on hover so a bare bar still reveals its exact counts.
        tip:
          `${when} — ${total} verification${total === 1 ? '' : 's'}` +
          ` (${d.verified} verified, ${d.pending} pending, ${d.rejected} rejected)`,
      };
    });
  });

  readonly donutBg = computed(() => {
    const v = this.verifiedPct();
    const p = this.pendingPct();
    const vEnd = v;
    const pEnd = v + p;
    return (
      `conic-gradient(var(--ox-green) 0% ${vEnd}%, ` +
      `var(--ox-orange) ${vEnd}% ${pEnd}%, ` +
      `var(--ox-red) ${pEnd}% 100%)`
    );
  });

  // ---- Review queue ----
  loadReviews(): void {
    this.reviewLoading.set(true);
    this.reviewError.set(false);
    this.api.listReviews().subscribe({
      next: (items) => {
        this.reviewData.set(items);
        this.reviewLoading.set(false);
        const first = this.queueCases()[0]?.id ?? null;
        if (first && !this.reviewData().some((r) => r.id === this.activeCaseId())) {
          this.selectCase(first);
        }
      },
      error: () => {
        this.reviewError.set(true);
        this.reviewLoading.set(false);
      },
    });
  }

  private toQueueRow(r: ReviewItem): QueueRow {
    const name = r.client_name ?? r.client_id;
    return {
      id: r.id,
      initials: initialsOf(name),
      name,
      client: r.client_id,
      agent: r.agent_name ?? '—',
      reason: r.flagged_duplicate ? 'Duplicate' : 'Low confidence',
      score: r.confidence_score == null ? '—' : r.confidence_score.toFixed(2),
      submitted: relativeTime(r.created_at),
    };
  }

  readonly queueCases = computed<QueueRow[]>(() => {
    const reason = this.reviewReason();
    const q = this.reviewSearch().trim().toLowerCase();
    return this.reviewData()
      .map((r) => this.toQueueRow(r))
      .filter((c) => reason === 'all' || c.reason === reason)
      .filter(
        (c) =>
          !q ||
          c.client.toLowerCase().includes(q) ||
          c.name.toLowerCase().includes(q),
      );
  });

  readonly queueCount = computed(() => this.reviewData().length);

  readonly activeCase = computed(
    () =>
      this.queueCases().find((c) => c.id === this.activeCaseId()) ??
      this.queueCases()[0],
  );

  // Detail header fields; the score breakdown itself lives in
  // <app-verification-scores>, shared with the review pane and agent view.
  readonly detailStatus = computed(() =>
    statusLabel(this.activeDetail()?.status ?? ''),
  );
  readonly detailWhen = computed(() => {
    const d = this.activeDetail();
    return d ? dateLabel(d.created_at) : '';
  });

  // ---- History ----
  loadHistory(): void {
    this.historyLoading.set(true);
    this.historyError.set(false);
    this.api.listVerifications().subscribe({
      next: (rows) => {
        this.historyData.set(rows);
        this.historyLoading.set(false);
      },
      error: () => {
        this.historyError.set(true);
        this.historyLoading.set(false);
      },
    });
  }

  readonly historyRows = computed<HistoryRow[]>(() =>
    this.historyData().map((r) => ({
      id: r.client_id,
      verificationId: r.id,
      name: r.client_name ?? '—',
      date: dateLabel(r.created_at),
      branch: r.branch_name ?? '—',
      agent: r.agent_name ?? '—',
      channel: r.submission_method === 'API' ? 'API' : 'Dashboard',
      status: statusLabel(r.status),
      score: scoreLabel(r.confidence_score),
    })),
  );

  readonly historyFiltered = computed(() => {
    const status = this.historyStatus();
    const q = this.historySearch().trim().toLowerCase();
    return this.historyRows()
      .filter((r) => status === 'All' || r.status === status)
      .filter(
        (r) =>
          !q ||
          r.id.toLowerCase().includes(q) ||
          r.name.toLowerCase().includes(q),
      );
  });

  readonly historyPageCount = computed(() =>
    Math.max(1, Math.ceil(this.historyFiltered().length / HISTORY_PAGE_SIZE)),
  );

  readonly historyPaged = computed(() => {
    const start = (this.historyPage() - 1) * HISTORY_PAGE_SIZE;
    return this.historyFiltered().slice(start, start + HISTORY_PAGE_SIZE);
  });

  readonly historyPages = computed(() =>
    Array.from({ length: this.historyPageCount() }, (_, i) => i + 1),
  );

  setPage(p: ManagerPage): void {
    this.page.set(p);
    // Bracket the switch so a page that fetches nothing (Dashboard) still
    // gets the transition. When a load does run, its request nests inside
    // this pair and the overlay stays up until the data lands.
    this.loading.start();
    if (p === 'review') this.loadReviews();
    if (p === 'history') this.loadHistory();
    if (p === 'reports') this.loadHistory();
    if (p === 'agents') this.loadAgents();
    if (p === 'apikeys') this.loadKeys();
    if (p === 'settings') this.loadAccount();
    this.loading.stop();
  }

  /** Reload the data behind the current page on demand. */
  refresh(): void {
    switch (this.page()) {
      case 'dashboard':
        this.loadStats();
        break;
      case 'review':
        this.loadReviews();
        break;
      case 'history':
        this.loadHistory();
        break;
      case 'agents':
        this.loadAgents();
        break;
      default:
        break;
    }
  }

  selectCase(id: string): void {
    this.activeCaseId.set(id);
    this.activeDetail.set(null);
    this.api.getVerification(id).subscribe({
      next: (d) => {
        if (this.activeCaseId() !== id) return;
        this.activeDetail.set(d);
        // Only the History popup renders images; the review pane doesn't.
        if (this.detailModalOpen()) this.loadDetailImages(id, d);
      },
      error: () => undefined,
    });
  }

  /** Open the read-only detail popup for a History row (any status). */
  openHistoryDetail(verificationId: string): void {
    this.selectCase(verificationId);
    this.detailModalOpen.set(true);
  }

  closeDetailModal(): void {
    this.detailModalOpen.set(false);
    this.revokeDetailImages();
    this.activeCaseId.set(null);
    this.activeDetail.set(null);
  }

  imageLabel(kind: ImageKind): string {
    return IMAGE_LABELS[kind];
  }

  /** Fetch each stored image as a blob and expose it as an object URL. */
  private loadDetailImages(id: string, detail: VerificationDetail): void {
    this.revokeDetailImages();
    const kinds = IMAGE_ORDER.filter((k) =>
      detail.available_images.includes(k),
    );
    for (const kind of kinds) {
      this.api.getVerificationImage(id, kind).subscribe({
        next: (blob) => {
          // Drop a late response for a popup that has since closed/changed.
          if (this.activeCaseId() !== id) return;
          const url = URL.createObjectURL(blob);
          this.detailImages.update((imgs) =>
            [...imgs, { kind, url }].sort(
              (a, b) =>
                IMAGE_ORDER.indexOf(a.kind) - IMAGE_ORDER.indexOf(b.kind),
            ),
          );
        },
        error: () => undefined,
      });
    }
  }

  private revokeDetailImages(): void {
    for (const img of this.detailImages()) URL.revokeObjectURL(img.url);
    this.detailImages.set([]);
  }

  /** Approve or reject the active case, then drop it from the queue. */
  resolveCase(action: 'approve' | 'reject'): void {
    const id = this.activeCaseId();
    if (!id || this.deciding()) return;
    this.deciding.set(true);
    this.api.decideReview(id, action).subscribe({
      next: () => {
        const next = this.reviewData().filter((r) => r.id !== id);
        this.reviewData.set(next);
        this.activeDetail.set(null);
        this.deciding.set(false);
        const following = this.queueCases()[0]?.id ?? null;
        this.activeCaseId.set(null);
        if (following) this.selectCase(following);
      },
      error: () => this.deciding.set(false),
    });
  }

  setReviewReason(r: 'all' | ReviewReason): void {
    this.reviewReason.set(r);
  }

  setHistoryStatus(s: 'All' | HistoryStatus): void {
    this.historyStatus.set(s);
    this.historyPage.set(1);
  }

  onHistorySearch(value: string): void {
    this.historySearch.set(value);
    this.historyPage.set(1);
  }

  goToPage(p: number): void {
    if (p >= 1 && p <= this.historyPageCount()) this.historyPage.set(p);
  }

  /** Client-side CSV export of the current (filtered) history view. */
  exportHistoryCsv(): void {
    const header = [
      'Client ID', 'Name', 'Date', 'Branch', 'Agent', 'Channel',
      'Status', 'Score',
    ];
    const lines = this.historyFiltered().map((r) =>
      [r.id, r.name, r.date, r.branch, r.agent, r.channel, r.status, r.score]
        .map((v) => `"${v}"`)
        .join(','),
    );
    const csv = [header.join(','), ...lines].join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    this.saveBlob(blob, 'verification-history.csv');
  }

  /** Trigger a browser download for a Blob. */
  private saveBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---- Reports ----
  readonly reportStart = signal(daysAgo(30));
  readonly reportEnd = signal(isoDate(new Date()));
  readonly reportGenerating = signal(false);
  readonly reportError = signal('');
  readonly generatedReport = signal<ReportSummary | null>(null);
  readonly downloading = signal(false);
  readonly reportRows = computed(() => this.historyRows().slice(0, 5));
  readonly reportGenerated = computed(() => this.generatedReport() !== null);

  readonly reportKpis = computed(() => {
    const r = this.generatedReport();
    const sb = r?.status_breakdown ?? {};
    return {
      total: r?.total_verifications ?? 0,
      verified: sb['VERIFIED'] ?? 0,
      pending: sb['PENDING'] ?? 0,
      rejected: sb['REJECTED'] ?? 0,
    };
  });

  generateReport(): void {
    if (this.reportGenerating()) return;
    this.reportGenerating.set(true);
    this.reportError.set('');
    this.generatedReport.set(null);
    this.api.generateReport(this.reportStart(), this.reportEnd()).subscribe({
      next: (r) => {
        this.generatedReport.set(r);
        this.reportGenerating.set(false);
      },
      error: () => {
        this.reportError.set('Could not generate the report.');
        this.reportGenerating.set(false);
      },
    });
  }

  /** Download the signed PDF for the just-generated report. */
  downloadReport(): void {
    const r = this.generatedReport();
    if (!r || this.downloading()) return;
    this.downloading.set(true);
    this.api.downloadReportPdf(r.id).subscribe({
      next: (blob) => {
        this.saveBlob(
          blob,
          `compliance-report-${r.period_start}_${r.period_end}.pdf`,
        );
        this.downloading.set(false);
      },
      error: () => this.downloading.set(false),
    });
  }

  // ---- Agents ----
  readonly agentData = signal<AgentSummary[]>([]);
  readonly agentsLoading = signal(false);
  readonly agentsError = signal(false);
  readonly branchList = signal<BranchSummary[]>([]);
  readonly activeAgentId = signal<string | null>(null);
  readonly agentSearch = signal('');
  readonly agentModalOpen = signal(false);
  readonly agentSaving = signal(false);
  readonly agentFormError = signal('');
  readonly agentForm = signal({
    name: '',
    phone: '',
    pin: '',
    branchId: '',
    newBranch: '',
    editingId: null as string | null,
  });

  // Reset-PIN modal
  readonly resetPinOpen = signal(false);
  readonly resetPinValue = signal('');
  readonly resetPinError = signal('');
  readonly resetPinDone = signal(false);

  loadAgents(): void {
    this.agentsLoading.set(true);
    this.agentsError.set(false);
    this.api.listAgents().subscribe({
      next: (rows) => {
        this.agentData.set(rows);
        this.agentsLoading.set(false);
        if (!this.agentData().some((a) => a.id === this.activeAgentId())) {
          this.activeAgentId.set(this.agentData()[0]?.id ?? null);
        }
      },
      error: () => {
        this.agentsError.set(true);
        this.agentsLoading.set(false);
      },
    });
    this.api.listBranches().subscribe({
      next: (b) => this.branchList.set(b),
      error: () => undefined,
    });
  }

  readonly agentList = computed(() => {
    const q = this.agentSearch().trim().toLowerCase();
    return this.agentData().filter(
      (a) =>
        !q ||
        a.full_name.toLowerCase().includes(q) ||
        (a.branch_name ?? '').toLowerCase().includes(q) ||
        (a.phone ?? '').toLowerCase().includes(q),
    );
  });
  readonly agentCount = computed(() => this.agentData().length);
  readonly activeAgent = computed(
    () =>
      this.agentData().find((a) => a.id === this.activeAgentId()) ??
      this.agentData()[0],
  );

  agentInitials(name: string): string {
    return initialsOf(name);
  }

  agentStatusLabel(status: string): 'Active' | 'Disabled' {
    return status === 'DISABLED' ? 'Disabled' : 'Active';
  }

  selectAgent(id: string): void {
    this.activeAgentId.set(id);
  }

  /** Toggle the active agent between ACTIVE and DISABLED. */
  toggleAgentActive(): void {
    const a = this.activeAgent();
    if (!a) return;
    const status = a.status === 'DISABLED' ? 'ACTIVE' : 'DISABLED';
    this.api.updateAgent(a.id, { status }).subscribe({
      next: () => this.loadAgents(),
      error: () => undefined,
    });
  }

  openAddAgent(): void {
    this.agentFormError.set('');
    this.agentForm.set({
      name: '',
      phone: '',
      pin: '',
      branchId: this.branchList()[0]?.id ?? '',
      newBranch: '',
      editingId: null,
    });
    this.agentModalOpen.set(true);
  }

  openEditAgent(): void {
    const a = this.activeAgent();
    if (!a) return;
    this.agentFormError.set('');
    this.agentForm.set({
      name: a.full_name,
      phone: a.phone ?? '',
      pin: '',
      branchId: a.branch_id ?? '',
      newBranch: '',
      editingId: a.id,
    });
    this.agentModalOpen.set(true);
  }

  closeAgentModal(): void {
    this.agentModalOpen.set(false);
  }

  setAgentField(
    field: 'name' | 'phone' | 'pin' | 'branchId' | 'newBranch',
    value: string,
  ): void {
    this.agentForm.update((f) => ({ ...f, [field]: value }));
  }

  /** Phone field holds the 9 national digits only; +237 is a fixed prefix. */
  setAgentPhone(value: string): void {
    this.agentForm.update((f) => ({ ...f, phone: phoneDigits(value) }));
  }

  saveAgent(): void {
    if (this.agentSaving()) return;
    const f = this.agentForm();
    if (!f.name.trim()) {
      this.agentFormError.set('Full name is required.');
      return;
    }
    // New agents need a valid phone + PIN; edits keep the existing ones.
    if (!f.editingId) {
      if (!normalizeCmPhone(f.phone)) {
        this.agentFormError.set('Enter a valid Cameroonian phone (+237 …).');
        return;
      }
      if (!isValidPin(f.pin)) {
        this.agentFormError.set('PIN must be 6–8 digits.');
        return;
      }
    }
    if (!f.branchId && !f.newBranch.trim()) {
      this.agentFormError.set('Choose or create a branch.');
      return;
    }
    this.agentFormError.set('');
    this.agentSaving.set(true);

    const withBranch = (branchId: string) => {
      const done = {
        next: () => {
          this.agentSaving.set(false);
          this.agentModalOpen.set(false);
          this.loadAgents();
        },
        error: (err: unknown) => {
          this.agentSaving.set(false);
          this.agentFormError.set(apiMessage(err, 'Could not save the agent.'));
        },
      };
      if (f.editingId) {
        this.api
          .updateAgent(f.editingId, {
            full_name: f.name.trim(),
            branch_id: branchId,
          })
          .subscribe(done);
      } else {
        this.api
          .createAgent({
            full_name: f.name.trim(),
            phone: normalizeCmPhone(f.phone)!,
            pin: f.pin,
            branch_id: branchId,
          })
          .subscribe(done);
      }
    };

    if (f.newBranch.trim()) {
      this.api.createBranch(f.newBranch.trim()).subscribe({
        next: (b) => withBranch(b.id),
        error: (err) => {
          this.agentSaving.set(false);
          this.agentFormError.set(
            apiMessage(err, 'Could not create the branch.'),
          );
        },
      });
    } else {
      withBranch(f.branchId);
    }
  }

  // Reset an agent's PIN (manager action).
  openResetPin(): void {
    this.resetPinValue.set('');
    this.resetPinError.set('');
    this.resetPinDone.set(false);
    this.resetPinOpen.set(true);
  }

  closeResetPin(): void {
    this.resetPinOpen.set(false);
  }

  confirmResetPin(): void {
    const a = this.activeAgent();
    if (!a) return;
    if (!isValidPin(this.resetPinValue())) {
      this.resetPinError.set('PIN must be 6–8 digits.');
      return;
    }
    this.resetPinError.set('');
    this.api.resetAgentPin(a.id, this.resetPinValue()).subscribe({
      next: () => this.resetPinDone.set(true),
      error: (err) =>
        this.resetPinError.set(apiMessage(err, 'Could not reset the PIN.')),
    });
  }

  // ---- API keys ----
  readonly keys = signal<ApiKeyRow[]>([]);
  readonly keysLoading = signal(false);
  readonly keysError = signal(false);
  readonly keyCreating = signal(false);

  private toKeyRow(k: {
    id: string;
    prefix: string;
    created_at: string;
    last_used_at?: string | null;
    is_active?: boolean;
  }): ApiKeyRow {
    return {
      id: k.id,
      prefix: k.prefix,
      created: dateLabel(k.created_at),
      lastUsed: k.last_used_at ? dateLabel(k.last_used_at) : 'never',
      active: k.is_active ?? true,
      copied: false,
    };
  }

  loadKeys(): void {
    this.keysLoading.set(true);
    this.keysError.set(false);
    this.api.listApiKeys().subscribe({
      next: (rows) => {
        this.keys.set(rows.map((k) => this.toKeyRow(k)));
        this.keysLoading.set(false);
      },
      error: () => {
        this.keysError.set(true);
        this.keysLoading.set(false);
      },
    });
  }

  generateKey(): void {
    if (this.keyCreating()) return;
    this.keyCreating.set(true);
    this.api.createApiKey().subscribe({
      next: (created: ApiKeyCreated) => {
        // Prepend the new key WITH its full value — shown once.
        const row = { ...this.toKeyRow(created), fullKey: created.full_key };
        this.keys.update((list) => [row, ...list]);
        this.keyCreating.set(false);
      },
      error: () => this.keyCreating.set(false),
    });
  }

  copyKey(id: string): void {
    const k = this.keys().find((x) => x.id === id);
    const text = k?.fullKey ?? k?.prefix ?? '';
    navigator.clipboard?.writeText(text).catch(() => undefined);
    this.keys.update((list) =>
      list.map((x) => (x.id === id ? { ...x, copied: true } : x)),
    );
    setTimeout(
      () =>
        this.keys.update((list) =>
          list.map((x) => (x.id === id ? { ...x, copied: false } : x)),
        ),
      1500,
    );
  }

  revokeKey(id: string): void {
    this.api.revokeApiKey(id).subscribe({
      next: () =>
        this.keys.update((list) => list.filter((x) => x.id !== id)),
      error: () => undefined,
    });
  }

  // ---- Settings / account ----
  readonly settingsTab = signal<SettingsTab>('Subscription');
  readonly settingsTabs = SETTINGS_TABS;
  readonly account = signal<AccountSummary | null>(null);
  readonly mfiName = signal('');
  readonly contactEmail = signal('');
  readonly accountSaving = signal(false);
  readonly accountError = signal('');
  readonly settingsSaved = signal(false);

  // Change PIN (Security tab)
  readonly curPin = signal('');
  readonly newPin = signal('');
  readonly pinError = signal('');
  readonly pinSaved = signal(false);
  readonly pinSaving = signal(false);

  readonly notifs = signal<Record<string, boolean>>({
    quota: true,
    pending: true,
    weekly: false,
    maintenance: true,
  });
  readonly notifDefs = NOTIF_DEFS;

  readonly usagePct = computed(() => {
    const a = this.account();
    return pct(a?.current_period_usage, a?.verification_quota ?? undefined);
  });

  loadAccount(): void {
    this.api.getAccount().subscribe({
      next: (a) => {
        this.account.set(a);
        this.mfiName.set(a.name);
        this.contactEmail.set(a.email);
      },
      error: () => undefined,
    });
  }

  setSettingsTab(t: SettingsTab): void {
    this.settingsTab.set(t);
  }

  saveSettings(): void {
    if (this.accountSaving()) return;
    this.accountSaving.set(true);
    this.accountError.set('');
    this.api
      .updateAccount({
        name: this.mfiName().trim(),
        email: this.contactEmail().trim(),
      })
      .subscribe({
        next: (a) => {
          this.account.set(a);
          this.accountSaving.set(false);
          this.settingsSaved.set(true);
          setTimeout(() => this.settingsSaved.set(false), 2000);
        },
        error: (err) => {
          this.accountSaving.set(false);
          this.accountError.set(apiMessage(err, 'Could not save changes.'));
        },
      });
  }

  changePin(): void {
    if (this.pinSaving()) return;
    if (!isValidPin(this.newPin())) {
      this.pinError.set('New PIN must be 6–8 digits.');
      return;
    }
    this.pinError.set('');
    this.pinSaving.set(true);
    this.auth.changePin(this.curPin(), this.newPin()).subscribe({
      next: () => {
        this.pinSaving.set(false);
        this.pinSaved.set(true);
        this.curPin.set('');
        this.newPin.set('');
        setTimeout(() => this.pinSaved.set(false), 2000);
      },
      error: (err) => {
        this.pinSaving.set(false);
        this.pinError.set(apiMessage(err, 'Could not change the PIN.'));
      },
    });
  }

  toggleNotif(key: string): void {
    this.notifs.update((n) => ({ ...n, [key]: !n[key] }));
  }

  // ---- Pricing ----
  readonly plans = PLANS;

  goPricing(): void {
    this.page.set('pricing');
  }

  backToSettings(): void {
    this.page.set('settings');
  }

  badgeClass(status: string): string {
    return `ox-badge ox-badge--${status.toLowerCase()}`;
  }
}
