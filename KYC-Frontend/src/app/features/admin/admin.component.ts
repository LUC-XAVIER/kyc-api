import { DatePipe } from '@angular/common';
import { Component, computed, inject, signal } from '@angular/core';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import { LoadingService } from '../../core/loading.service';
import {
  AdminMfiDetail,
  AdminMfiSummary,
  MfiStatus,
  PlatformStats,
} from '../../core/models';

type AdminPage =
  | 'overview'
  | 'mfi-accounts'
  | 'mfi-detail'
  | 'model-health'
  | 'face-matching'
  | 'anti-spoofing'
  | 'ocr-engine'
  | 'api-performance'
  | 'system-health'
  | 'audit-logs';

interface NavItem {
  id: AdminPage;
  label: string;
  glyph: string;
}
interface NavSection {
  section: string;
  items: NavItem[];
}

/** Sidebar layout — mirrors the design's four groups. */
const NAV: NavSection[] = [
  { section: 'PLATFORM', items: [{ id: 'overview', label: 'Overview', glyph: '▦' }] },
  {
    section: 'MFI MANAGEMENT',
    items: [
      { id: 'mfi-accounts', label: 'MFI Accounts', glyph: '🏦' },
      { id: 'mfi-detail', label: 'MFI Detail', glyph: '🔎' },
    ],
  },
  {
    section: 'MODEL MONITORING',
    items: [
      { id: 'model-health', label: 'Model Health', glyph: '♥' },
      { id: 'face-matching', label: 'Face Matching', glyph: '◍' },
      { id: 'anti-spoofing', label: 'Anti-Spoofing', glyph: '🛡' },
      { id: 'ocr-engine', label: 'OCR Engine', glyph: '▤' },
    ],
  },
  {
    section: 'OPERATIONS',
    items: [
      { id: 'api-performance', label: 'API Performance', glyph: '⚡' },
      { id: 'system-health', label: 'System Health', glyph: '▥' },
      { id: 'audit-logs', label: 'Audit Logs', glyph: '▧' },
    ],
  },
];

/** Pages not yet backed by real data — shown as a labelled placeholder. */
const DEFERRED = new Set<AdminPage>([
  'model-health',
  'face-matching',
  'anti-spoofing',
  'ocr-engine',
  'api-performance',
  'system-health',
  'audit-logs',
]);

const TITLES: Record<AdminPage, [string, string]> = {
  overview: ['Platform Overview', 'Every MFI on the platform, at a glance'],
  'mfi-accounts': ['MFI Accounts', 'All registered institutions'],
  'mfi-detail': ['MFI Detail', 'Account drill-down'],
  'model-health': ['Model Health', 'Coming with model monitoring'],
  'face-matching': ['Face Matching', 'Coming with model monitoring'],
  'anti-spoofing': ['Anti-Spoofing', 'Coming with model monitoring'],
  'ocr-engine': ['OCR Engine', 'Coming with model monitoring'],
  'api-performance': ['API Performance', 'Coming with operations metrics'],
  'system-health': ['System Health', 'Coming with operations metrics'],
  'audit-logs': ['Audit Logs', 'Coming soon'],
};

const PLAN_COLORS: Record<string, string> = {
  STARTER: '#e5484d',
  GROWTH: '#8b5cf6',
  PRO: '#22c55e',
  ENTERPRISE: '#3b82f6',
};

/** A pre-computed display row for one MFI in the accounts table. */
interface MfiRow {
  id: string;
  name: string;
  email: string;
  plan: string | null;
  planColor: string;
  status: MfiStatus;
  usage: number;
  quota: number | null;
  quotaPct: number;
  quotaLabel: string;
  verifications: string;
  users: number;
  apiKeys: number;
  branches: number;
  joined: string;
}

/** One slice of the plan donut. */
interface DonutSlice {
  plan: string;
  count: number;
  pct: number;
  color: string;
}

/** One bar in the daily-verifications chart. */
interface DayBar {
  h: number;
  label: string;
  tip: string;
}

function initials(name: string): string {
  return (
    name
      .split(/\s+/)
      .map((w) => w[0])
      .slice(0, 2)
      .join('')
      .toUpperCase() || '—'
  );
}

function num(n: number): string {
  return n.toLocaleString('en-US');
}

function shortDate(iso: string): string {
  return new Date(iso).toLocaleDateString('en-US', {
    month: 'short',
    year: 'numeric',
  });
}

/**
 * The Openxtech platform-admin dashboard. A cross-tenant surface: it sees
 * every MFI, unlike the manager/agent dashboards. Same signal + setPage()
 * shape as those, but keeps the design's dark theme. Overview, MFI Accounts
 * and MFI Detail are wired to /admin/*; the model-monitoring and operations
 * sections are placeholders until those metrics exist.
 */
@Component({
  selector: 'app-admin',
  imports: [DatePipe],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
})
export class AdminComponent {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly loading = inject(LoadingService);
  readonly user = this.auth.principal;

  readonly nav = NAV;
  readonly page = signal<AdminPage>('overview');

  readonly stats = signal<PlatformStats | null>(null);
  readonly mfis = signal<AdminMfiSummary[]>([]);
  readonly mfiFilter = signal<'all' | MfiStatus>('all');
  readonly detail = signal<AdminMfiDetail | null>(null);
  readonly search = signal('');
  readonly toast = signal('');
  readonly busyId = signal<string | null>(null);

  constructor() {
    this.loadStats();
    this.loadMfis();
  }

  readonly userInitials = computed(() => initials(this.user()?.full_name ?? 'A'));

  readonly title = computed<[string, string]>(() => {
    if (this.page() === 'mfi-detail' && this.detail()) {
      return [`MFI — ${this.detail()!.name}`, this.detail()!.email];
    }
    return TITLES[this.page()];
  });

  readonly isDeferred = computed(() => DEFERRED.has(this.page()));

  // ---- Navigation ----
  setPage(p: AdminPage): void {
    if (p === 'mfi-detail' && !this.detail()) p = 'mfi-accounts';
    this.page.set(p);
    this.loading.start();
    if (p === 'overview') this.loadStats();
    if (p === 'mfi-accounts') this.loadMfis();
    this.loading.stop();
  }

  isActive(id: AdminPage): boolean {
    return this.page() === id;
  }

  refresh(): void {
    if (this.page() === 'overview') this.loadStats();
    else if (this.page() === 'mfi-accounts') this.loadMfis();
    else if (this.page() === 'mfi-detail' && this.detail())
      this.openMfi(this.detail()!.id);
  }

  logout(): void {
    this.auth.logout();
  }

  // ---- Data loading ----
  loadStats(): void {
    this.api.getPlatformStats().subscribe({
      next: (s) => this.stats.set(s),
      error: () => undefined,
    });
  }

  loadMfis(): void {
    this.api.listAdminMfis().subscribe({
      next: (m) => this.mfis.set(m),
      error: () => undefined,
    });
  }

  openMfi(id: string): void {
    this.loading.start();
    this.api.getAdminMfi(id).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.page.set('mfi-detail');
        this.loading.stop();
      },
      error: () => this.loading.stop(),
    });
  }

  backToAccounts(): void {
    this.page.set('mfi-accounts');
  }

  setStatus(id: string, status: MfiStatus): void {
    this.busyId.set(id);
    this.api.setMfiStatus(id, status).subscribe({
      next: (d) => {
        this.busyId.set(null);
        this.detail.set(d);
        // Keep the table in sync without a full reload.
        this.mfis.update((rows) =>
          rows.map((r) => (r.id === id ? { ...r, status } : r)),
        );
        this.showToast(
          `${d.name} ${status === 'SUSPENDED' ? 'suspended' : 'reactivated'}.`,
        );
        this.loadStats();
      },
      error: () => this.busyId.set(null),
    });
  }

  private toastTimer: ReturnType<typeof setTimeout> | undefined;
  showToast(msg: string): void {
    this.toast.set(msg);
    clearTimeout(this.toastTimer);
    this.toastTimer = setTimeout(() => this.toast.set(''), 2800);
  }

  // ---- Overview derived ----
  readonly overviewCards = computed(() => {
    const s = this.stats();
    if (!s) return [];
    return [
      { label: 'ACTIVE MFIS', value: num(s.active_mfis), sub: `${s.total_mfis} total`, color: '' },
      { label: 'TOTAL VERIFICATIONS', value: num(s.total_verifications), sub: 'All time', color: '' },
      { label: 'STAFF ACCOUNTS', value: num(s.total_users), sub: 'Across all MFIs', color: '' },
      {
        label: 'QUOTA WARNINGS',
        value: num(s.warning_count),
        sub: s.warning_count ? 'Approaching limits' : 'All within limits',
        color: s.warning_count ? '#f5a524' : '',
      },
    ];
  });

  readonly dayBars = computed<DayBar[]>(() => {
    const days = this.stats()?.per_day ?? [];
    const max = Math.max(5, ...days.map((d) => d.count));
    return days.map((d) => ({
      h: Math.round((d.count / max) * 150),
      label: new Date(d.date).getDate().toString(),
      tip: `${d.count} on ${new Date(d.date).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}`,
    }));
  });

  readonly donut = computed<DonutSlice[]>(() => {
    const buckets = this.stats()?.by_plan ?? [];
    const total = buckets.reduce((a, b) => a + b.count, 0) || 1;
    return buckets.map((b) => ({
      plan: b.plan,
      count: b.count,
      pct: Math.round((b.count / total) * 100),
      color: PLAN_COLORS[b.plan] ?? '#8b5cf6',
    }));
  });

  /** CSS conic-gradient painting the donut from the plan slices. */
  readonly donutStyle = computed(() => {
    const slices = this.donut();
    if (!slices.length) return 'background:#2a3040';
    let acc = 0;
    const stops = slices.map((s) => {
      const from = acc;
      acc += s.pct;
      return `${s.color} ${from}% ${acc}%`;
    });
    return `background:conic-gradient(${stops.join(',')})`;
  });

  readonly quotaRows = computed(() =>
    (this.stats()?.quota_rows ?? []).map((q) => ({
      ...q,
      color: q.pct >= 100 ? '#e5484d' : q.pct >= 80 ? '#f5a524' : '#22c55e',
      band: q.pct >= 100 ? 'Critical' : q.pct >= 80 ? 'Warning' : 'OK',
    })),
  );

  // ---- MFI Accounts derived ----
  readonly accountCards = computed(() => {
    const s = this.stats();
    const rows = this.mfis();
    return [
      { label: 'TOTAL MFIS', value: num(rows.length), color: '' },
      { label: 'ACTIVE', value: num(s?.active_mfis ?? rows.filter((r) => r.status === 'ACTIVE').length), color: '#22c55e' },
      { label: 'SUSPENDED', value: num(s?.suspended_mfis ?? rows.filter((r) => r.status === 'SUSPENDED').length), color: '#e5484d' },
      { label: 'QUOTA WARNINGS', value: num(s?.warning_count ?? 0), color: '#f5a524' },
    ];
  });

  readonly filters = computed(() => {
    const rows = this.mfis();
    const count = (st: MfiStatus) => rows.filter((r) => r.status === st).length;
    return [
      { id: 'all' as const, label: `All (${rows.length})` },
      { id: 'ACTIVE' as const, label: `Active (${count('ACTIVE')})` },
      { id: 'PENDING' as const, label: `Pending (${count('PENDING')})` },
      { id: 'SUSPENDED' as const, label: `Suspended (${count('SUSPENDED')})` },
    ];
  });

  setFilter(f: 'all' | MfiStatus): void {
    this.mfiFilter.set(f);
  }

  readonly rows = computed<MfiRow[]>(() => {
    const filter = this.mfiFilter();
    const q = this.search().trim().toLowerCase();
    return this.mfis()
      .filter((m) => filter === 'all' || m.status === filter)
      .filter(
        (m) =>
          !q ||
          m.name.toLowerCase().includes(q) ||
          m.email.toLowerCase().includes(q),
      )
      .slice()
      .sort((a, b) => b.usage - a.usage)
      .map((m) => {
        const pct = m.quota ? Math.round((m.usage / m.quota) * 100) : 0;
        return {
          id: m.id,
          name: m.name,
          email: m.email,
          plan: m.plan,
          planColor: m.plan ? PLAN_COLORS[m.plan] ?? '#8b5cf6' : '#8b5cf6',
          status: m.status,
          usage: m.usage,
          quota: m.quota,
          quotaPct: Math.min(pct, 100),
          quotaLabel: m.quota ? `${num(m.usage)} / ${num(m.quota)}` : '—',
          verifications: num(m.verifications),
          users: m.users,
          apiKeys: m.api_keys,
          branches: m.branches,
          joined: shortDate(m.created_at),
        };
      });
  });

  statusColor(s: MfiStatus): string {
    return s === 'ACTIVE'
      ? '#22c55e'
      : s === 'SUSPENDED'
        ? '#e5484d'
        : '#f5a524';
  }

  // ---- MFI Detail derived ----
  readonly detailInitials = computed(() =>
    initials(this.detail()?.name ?? ''),
  );

  readonly detailUsedPct = computed(() => {
    const d = this.detail();
    if (!d?.quota) return 0;
    return Math.min(Math.round((d.usage / d.quota) * 100), 100);
  });

  readonly detailPlanLine = computed(() => {
    const d = this.detail();
    if (!d) return '';
    const parts = [
      d.quota ? `${num(d.quota)} verifications / cycle` : 'Unlimited verifications',
      d.max_branches != null ? `${d.max_branches} branches` : 'unlimited branches',
      d.max_agents != null ? `${d.max_agents} agents` : 'unlimited agents',
      d.api_access ? 'API access' : 'no API access',
    ];
    return parts.join(' · ');
  });

  readonly detailPerf = computed(() => {
    const p = this.detail()?.performance;
    if (!p) return [];
    const total = p.verified + p.pending + p.rejected || 1;
    const rate = (n: number) => `${Math.round((n / total) * 100)}%`;
    return [
      { label: 'Verified', value: `${num(p.verified)} · ${rate(p.verified)}`, color: '#22c55e' },
      { label: 'Pending', value: `${num(p.pending)} · ${rate(p.pending)}`, color: '#f5a524' },
      { label: 'Rejected', value: `${num(p.rejected)} · ${rate(p.rejected)}`, color: '#e5484d' },
      { label: 'Duplicate flags', value: num(p.duplicates), color: '#f5a524' },
      {
        label: 'Avg. processing time',
        value: p.avg_processing_seconds != null ? `${p.avg_processing_seconds}s` : '—',
        color: '#22c55e',
      },
    ];
  });

  agentInitials(name: string): string {
    return initials(name);
  }
}
