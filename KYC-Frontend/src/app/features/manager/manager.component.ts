import { Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { VerificationStats } from '../../core/models';

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

interface AgentRow {
  name: string;
  agentId: string;
  initials: string;
  branch: string;
  submissions: number;
  lastActive: string;
  active: boolean;
  rate: string;
  avgTime: string;
  email: string;
  added: string;
}

interface ApiKeyRow {
  id: number;
  name: string;
  created: string;
  lastUsed: string;
  masked: string;
  rateLimit: string;
  reqToday: number;
  thisMonth: number;
  expires: string;
  quotaPct: number;
  active: boolean;
  copied: boolean;
  fullKey?: string;
}

interface Plan {
  name: string;
  tagline: string;
  price: string;
  period: string;
  volume: string;
  popular: boolean;
  features: string[];
}

type ReviewReason = 'Duplicate' | 'Low confidence';
type HistoryStatus =
  | 'Verified'
  | 'Pending'
  | 'Rejected'
  | 'Approved';

interface QueueCase {
  id: string;
  initials: string;
  name: string;
  client: string;
  agent: string;
  reason: ReviewReason;
  score: string;
  submitted: string;
  faceMatch: string;
  ocr: string;
  dupSim: string;
  dupWarning?: string;
}

interface HistoryRow {
  id: string;
  name: string;
  date: string;
  branch: string;
  agent: string;
  channel: 'Dashboard' | 'API';
  status: HistoryStatus;
  score: string;
}

const QUEUE_CASES: QueueCase[] = [
  { id: 'CLT-00482', initials: 'JF', name: 'FOTSO Jean-Pierre', client: 'CLT-00482', agent: 'Jeanne Mbarga', reason: 'Duplicate', score: '0.94', submitted: '2 min ago', faceMatch: '0.91 — match', ocr: '0.97', dupSim: '0.94 — high', dupWarning: 'Matches existing client CLT-00119 (KAMGA Jean-Paul) registered 14 Feb 2026 at Mvog-Ada branch. Review before approving.' },
  { id: 'CLT-00481', initials: 'MN', name: 'NGO Marie', client: 'CLT-00481', agent: 'Pierre Onana', reason: 'Low confidence', score: '0.71', submitted: '18 min ago', faceMatch: '0.71 — weak', ocr: '0.82', dupSim: '0.12 — low' },
  { id: 'CLT-00479', initials: 'PT', name: 'TCHOUMI Paul', client: 'CLT-00479', agent: 'Roger Tabi', reason: 'Duplicate', score: '0.89', submitted: '1h ago', faceMatch: '0.88 — match', ocr: '0.95', dupSim: '0.89 — high', dupWarning: 'Similar to client CLT-00203 (TCHOUMI P.) registered 3 Mar 2026 at Mokolo branch. Review before approving.' },
  { id: 'CLT-00471', initials: 'SA', name: 'ABENA Sandrine', client: 'CLT-00471', agent: 'Sandrine Ekotto', reason: 'Low confidence', score: '0.68', submitted: '3h ago', faceMatch: '0.68 — weak', ocr: '0.79', dupSim: '0.08 — low' },
  { id: 'CLT-00468', initials: 'RK', name: 'KAMDEM Robert', client: 'CLT-00468', agent: 'Boris Nguele', reason: 'Duplicate', score: '0.91', submitted: '5h ago', faceMatch: '0.90 — match', ocr: '0.93', dupSim: '0.91 — high', dupWarning: 'Matches existing client CLT-00087 (KAMDEM R.) registered 2 Jan 2026 at Mvog-Ada branch. Review before approving.' },
];

const HISTORY_ROWS: HistoryRow[] = [
  { id: 'CLT-00482', name: 'FOTSO Jean-Pierre', date: '17 Jun, 14:32', branch: 'Mvog-Ada', agent: 'J. Mbarga', channel: 'Dashboard', status: 'Verified', score: '96%' },
  { id: 'CLT-00481', name: 'NGO Marie-Claire', date: '17 Jun, 11:14', branch: 'Biyem-Assi', agent: 'P. Onana', channel: 'API', status: 'Verified', score: '93%' },
  { id: 'CLT-00480', name: 'TABI Roger', date: '16 Jun, 15:08', branch: 'Mokolo', agent: 'R. Tabi', channel: 'Dashboard', status: 'Pending', score: '78%' },
  { id: 'CLT-00479', name: 'MVOGO Pauline', date: '16 Jun, 14:55', branch: 'Mvog-Ada', agent: 'J. Mbarga', channel: 'Dashboard', status: 'Verified', score: '91%' },
  { id: 'CLT-00478', name: 'EKOTTO Samuel', date: '15 Jun, 10:30', branch: 'Bafoussam', agent: 'S. Ekotto', channel: 'API', status: 'Rejected', score: '31%' },
  { id: 'CLT-00477', name: 'ATEBA Christine', date: '15 Jun, 09:18', branch: 'Biyem-Assi', agent: 'P. Onana', channel: 'Dashboard', status: 'Approved', score: '88%' },
  { id: 'CLT-00476', name: 'BEKONO Lionel', date: '14 Jun, 16:42', branch: 'Mvog-Ada', agent: 'J. Mbarga', channel: 'Dashboard', status: 'Verified', score: '94%' },
  { id: 'CLT-00475', name: 'NKODO Sylvie', date: '14 Jun, 11:05', branch: 'Mokolo', agent: 'R. Tabi', channel: 'API', status: 'Verified', score: '97%' },
];

const HISTORY_PAGE_SIZE = 6;

const AGENTS: AgentRow[] = [
  { name: 'Jeanne Mbarga', agentId: 'AGT-014', initials: 'JM', branch: 'Mvog-Ada', submissions: 142, lastActive: 'Today, 14:28', active: true, rate: '94%', avgTime: '4.3s', email: 'j.mbarga@camfinance.cm', added: '12 January 2026' },
  { name: 'Pierre Onana', agentId: 'AGT-015', initials: 'PO', branch: 'Biyem-Assi', submissions: 98, lastActive: 'Today, 11:02', active: true, rate: '92%', avgTime: '4.6s', email: 'p.onana@camfinance.cm', added: '18 January 2026' },
  { name: 'Roger Tabi', agentId: 'AGT-016', initials: 'RT', branch: 'Mokolo', submissions: 76, lastActive: 'Yesterday', active: true, rate: '90%', avgTime: '4.9s', email: 'r.tabi@camfinance.cm', added: '2 February 2026' },
  { name: 'Sandrine Ekotto', agentId: 'AGT-017', initials: 'SE', branch: 'Bafoussam', submissions: 54, lastActive: '16 Jun', active: true, rate: '89%', avgTime: '5.1s', email: 's.ekotto@camfinance.cm', added: '10 February 2026' },
  { name: 'Boris Nguele', agentId: 'AGT-018', initials: 'BN', branch: 'Mvog-Ada', submissions: 38, lastActive: '15 Jun', active: true, rate: '87%', avgTime: '5.3s', email: 'b.nguele@camfinance.cm', added: '20 February 2026' },
  { name: 'Celine Ateba', agentId: 'AGT-019', initials: 'CA', branch: 'Biyem-Assi', submissions: 21, lastActive: '14 Jun', active: false, rate: '81%', avgTime: '5.8s', email: 'c.ateba@camfinance.cm', added: '1 March 2026' },
];

const PLAN_MAX_AGENTS = 15;

const API_KEYS_DATA: ApiKeyRow[] = [
  { id: 1, name: 'Production key', created: '12 Jan 2026', lastUsed: 'today, 14:31', masked: 'kyc_live_a7f3e2b19d84c6••••••••••••••••••', rateLimit: '100 req / min', reqToday: 284, thisMonth: 847, expires: 'Never', quotaPct: 84.7, active: true, copied: false },
  { id: 2, name: 'Staging / test key', created: '20 Jan 2026', lastUsed: '10 Jun 2026', masked: 'kyc_test_b9c1d5e28f71a4••••••••••••••••••', rateLimit: '20 req / min', reqToday: 0, thisMonth: 12, expires: '31 Dec 2026', quotaPct: 1.2, active: true, copied: false },
];

const PLANS: Plan[] = [
  { name: 'Starter', tagline: 'For single-branch MFIs and pilots', price: '25,000', period: 'FCFA/mo', volume: '200 verifications / month', popular: false, features: ['Dashboard for 1 branch', 'Up to 3 agent accounts', 'Face match + liveness + OCR', 'Duplicate detection', 'Monthly compliance report', 'Email support'] },
  { name: 'Growth', tagline: 'For multi-branch MFIs', price: '65,000', period: 'FCFA/mo', volume: '1,000 verifications / month', popular: false, features: ['Dashboard for up to 5 branches', 'Up to 15 agent accounts', 'Everything in Starter', 'On-demand compliance reports', 'API access for integration', 'Priority email support'] },
  { name: 'Pro', tagline: 'For established MFI networks', price: '150,000', period: 'FCFA/mo', volume: '5,000 verifications / month', popular: true, features: ['Unlimited branches', 'Unlimited agent accounts', 'Everything in Growth', 'Custom rate limits', 'Dedicated API key with higher throughput', 'Phone + email support, 24h response', 'Quarterly model performance review'] },
  { name: 'Enterprise', tagline: 'For networks and federations', price: 'Custom', period: '', volume: '10,000+ verifications / month', popular: false, features: ['Everything in Pro', 'Volume-based custom pricing', 'Dedicated infrastructure option', 'Custom OCR tuning for partner documents', 'SLA-backed uptime guarantee', 'Dedicated account manager'] },
];

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
  templateUrl: './manager.component.html',
  styleUrl: './manager.component.scss',
})
export class ManagerComponent {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  readonly user = this.auth.principal;

  constructor() {
    this.loadStats();
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

  // Review queue
  readonly queueIds = signal<string[]>(QUEUE_CASES.map((c) => c.id));
  readonly activeCaseId = signal<string | null>(QUEUE_CASES[0].id);
  readonly reviewReason = signal<'all' | ReviewReason>('all');
  readonly reviewSearch = signal('');

  // History
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
    const map: Record<ManagerPage, [string, string]> = {
      dashboard: ['Verification statistics', 'CamFinance Microfinance · All branches'],
      review: ['Pending review cases', 'CamFinance Microfinance'],
      history: ['Verification history', 'CamFinance Microfinance · All branches'],
      reports: ['Compliance reports', 'Generate COBAC-ready verification records'],
      agents: ['Agent accounts', 'CamFinance Microfinance · Growth plan'],
      apikeys: ['API keys', 'CamFinance Microfinance · Growth plan'],
      settings: ['Settings', 'CamFinance Microfinance'],
      pricing: ['Subscription plans', 'Choose the plan that fits your institution'],
    };
    return map[this.page()];
  });

  // ---- Dashboard chart geometry (from real stats) ----
  readonly dayBars = computed(() => {
    const days = this.stats()?.per_day ?? [];
    const max = Math.max(
      1,
      ...days.map((d) => d.verified + d.pending + d.rejected),
    );
    return days.map((d) => ({
      label: String(new Date(d.date).getDate()),
      v: (d.verified / max) * 100,
      p: (d.pending / max) * 100,
      r: (d.rejected / max) * 100,
    }));
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
  readonly queueCases = computed(() => {
    const reason = this.reviewReason();
    const q = this.reviewSearch().trim().toLowerCase();
    return this.queueIds()
      .map((id) => QUEUE_CASES.find((c) => c.id === id)!)
      .filter((c) => reason === 'all' || c.reason === reason)
      .filter(
        (c) =>
          !q ||
          c.client.toLowerCase().includes(q) ||
          c.name.toLowerCase().includes(q),
      );
  });

  readonly queueCount = computed(() => this.queueIds().length);

  readonly activeCase = computed(
    () =>
      this.queueCases().find((c) => c.id === this.activeCaseId()) ??
      this.queueCases()[0],
  );

  // ---- History ----
  readonly historyFiltered = computed(() => {
    const status = this.historyStatus();
    const q = this.historySearch().trim().toLowerCase();
    return HISTORY_ROWS.filter(
      (r) => status === 'All' || r.status === status,
    ).filter(
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
  }

  selectCase(id: string): void {
    this.activeCaseId.set(id);
  }

  resolveCase(): void {
    const id = this.activeCaseId();
    const next = this.queueIds().filter((q) => q !== id);
    this.queueIds.set(next);
    this.activeCaseId.set(next[0] ?? null);
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
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'verification-history.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---- Reports ----
  readonly reportStart = signal('2026-06-01');
  readonly reportEnd = signal('2026-06-17');
  readonly reportBranch = signal('All branches');
  readonly reportStatus = signal('All statuses');
  readonly reportGenerating = signal(false);
  readonly reportGenerated = signal(false);
  readonly reportRows = HISTORY_ROWS.slice(0, 5);

  generateReport(): void {
    if (this.reportGenerating()) return;
    this.reportGenerating.set(true);
    this.reportGenerated.set(false);
    // Simulated; the real POST /kyc/reports lands in the API phase.
    setTimeout(() => {
      this.reportGenerating.set(false);
      this.reportGenerated.set(true);
    }, 900);
  }

  /** Local-phase download; the signed PDF comes from the API later. */
  downloadReport(): void {
    const text =
      `KYC Compliance Report\n` +
      `Period: ${this.reportStart()} to ${this.reportEnd()}\n` +
      `Branch: ${this.reportBranch()} · Status: ${this.reportStatus()}\n\n` +
      `Total verifications: 1284\nVerified: 1174\nPending: 74\nRejected: 36\n`;
    const blob = new Blob([text], { type: 'text/plain;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'compliance-report.txt';
    a.click();
    URL.revokeObjectURL(url);
  }

  // ---- Agents ----
  readonly agents = signal<AgentRow[]>(AGENTS.map((a) => ({ ...a })));
  readonly activeAgentId = signal<string | null>(AGENTS[0].agentId);
  readonly agentSearch = signal('');
  readonly agentModalOpen = signal(false);
  readonly agentForm = signal({
    name: '',
    email: '',
    branch: '',
    editingId: null as string | null,
  });
  readonly planMaxAgents = PLAN_MAX_AGENTS;

  readonly agentList = computed(() => {
    const q = this.agentSearch().trim().toLowerCase();
    return this.agents()
      .filter(
        (a) =>
          !q ||
          a.name.toLowerCase().includes(q) ||
          a.branch.toLowerCase().includes(q),
      )
      .map((a) => ({ ...a, status: this.agentStatus(a) }));
  });
  readonly agentCount = computed(() => this.agents().length);
  readonly activeAgent = computed(
    () =>
      this.agents().find((a) => a.agentId === this.activeAgentId()) ??
      this.agents()[0],
  );
  readonly atAgentLimit = computed(
    () => this.agents().length >= PLAN_MAX_AGENTS,
  );

  agentStatus(a: AgentRow): 'Active' | 'Inactive' | 'Disabled' {
    if (!a.active) return 'Disabled';
    return a.submissions < 25 ? 'Inactive' : 'Active';
  }

  selectAgent(id: string): void {
    this.activeAgentId.set(id);
  }

  toggleAgentActive(): void {
    const id = this.activeAgentId();
    this.agents.update((list) =>
      list.map((a) => (a.agentId === id ? { ...a, active: !a.active } : a)),
    );
  }

  openAddAgent(): void {
    this.agentForm.set({ name: '', email: '', branch: '', editingId: null });
    this.agentModalOpen.set(true);
  }

  openEditAgent(): void {
    const a = this.activeAgent();
    if (!a) return;
    this.agentForm.set({
      name: a.name,
      email: a.email,
      branch: a.branch,
      editingId: a.agentId,
    });
    this.agentModalOpen.set(true);
  }

  closeAgentModal(): void {
    this.agentModalOpen.set(false);
  }

  setAgentField(field: 'name' | 'email' | 'branch', value: string): void {
    this.agentForm.update((f) => ({ ...f, [field]: value }));
  }

  saveAgent(): void {
    const f = this.agentForm();
    if (!f.name.trim() || !f.email.trim()) return;
    const initials = f.name
      .trim()
      .split(/\s+/)
      .map((w) => w[0])
      .slice(0, 2)
      .join('')
      .toUpperCase();

    if (f.editingId) {
      this.agents.update((list) =>
        list.map((a) =>
          a.agentId === f.editingId
            ? { ...a, name: f.name, email: f.email, branch: f.branch, initials }
            : a,
        ),
      );
    } else {
      if (this.atAgentLimit()) {
        this.agentModalOpen.set(false);
        return;
      }
      const next: AgentRow = {
        name: f.name,
        email: f.email,
        branch: f.branch || '—',
        agentId: 'AGT-0' + (14 + this.agents().length + 1),
        initials,
        submissions: 0,
        lastActive: 'Just now',
        active: true,
        rate: '—',
        avgTime: '—',
        added: 'Today',
      };
      this.agents.update((list) => [...list, next]);
      this.activeAgentId.set(next.agentId);
    }
    this.agentModalOpen.set(false);
  }

  // ---- API keys ----
  readonly keys = signal<ApiKeyRow[]>(API_KEYS_DATA.map((k) => ({ ...k })));
  private keySeq = 100;

  generateKey(): void {
    const rand = () => Math.random().toString(36).slice(2);
    const full = 'kyc_live_' + (rand() + rand()).slice(0, 32);
    const key: ApiKeyRow = {
      id: ++this.keySeq,
      name: 'New API key',
      created: 'Just now',
      lastUsed: 'never',
      masked: full.slice(0, 20) + '••••••••••••••••••',
      rateLimit: '100 req / min',
      reqToday: 0,
      thisMonth: 0,
      expires: 'Never',
      quotaPct: 0,
      active: true,
      copied: false,
      fullKey: full,
    };
    this.keys.update((list) => [key, ...list]);
  }

  copyKey(id: number): void {
    const k = this.keys().find((x) => x.id === id);
    const text = k?.fullKey ?? k?.masked ?? '';
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

  rotateKey(id: number): void {
    const rand = Math.random().toString(36).slice(2, 10);
    this.keys.update((list) =>
      list.map((x) =>
        x.id === id
          ? {
              ...x,
              masked: 'kyc_live_' + rand + '••••••••••••••••••',
              lastUsed: 'never',
              created: 'Just now',
            }
          : x,
      ),
    );
  }

  revokeKey(id: number): void {
    this.keys.update((list) => list.filter((x) => x.id !== id));
  }

  // ---- Settings ----
  readonly settingsTab = signal<SettingsTab>('Subscription');
  readonly settingsTabs = SETTINGS_TABS;
  readonly mfiName = signal('CamFinance Microfinance');
  readonly contactEmail = signal('contact@camfinance.cm');
  readonly phone = signal('+237 6 99 00 11 22');
  readonly settingsSaved = signal(false);
  readonly notifs = signal<Record<string, boolean>>({
    quota: true,
    pending: true,
    weekly: false,
    maintenance: true,
  });
  readonly notifDefs = NOTIF_DEFS;

  setSettingsTab(t: SettingsTab): void {
    this.settingsTab.set(t);
  }

  saveSettings(): void {
    this.settingsSaved.set(true);
    setTimeout(() => this.settingsSaved.set(false), 2000);
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
