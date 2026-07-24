import { DatePipe } from '@angular/common';
import {
  Component,
  OnDestroy,
  computed,
  effect,
  inject,
  signal,
} from '@angular/core';
import { DomSanitizer, SafeUrl } from '@angular/platform-browser';

import { ApiService } from '../../core/api.service';
import { AuthService, TwoFactorSetup } from '../../core/auth.service';
import { LoadingService } from '../../core/loading.service';
import {
  AdminAuditEntry,
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
  | 'audit-logs'
  | 'security';

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
  {
    section: 'ACCOUNT',
    items: [{ id: 'security', label: 'Security', glyph: '🔒' }],
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
]);

/** How each audit action string is rendered in the log. */
interface ActionMeta {
  icon: string;
  category: string;
  label: string;
}
const ACTION_META: Record<string, ActionMeta> = {
  'verification.processed': { icon: '🔎', category: 'Verification', label: 'Verification processed' },
  'review.approved': { icon: '✓', category: 'Manual review', label: 'Review approved' },
  'review.rejected': { icon: '✕', category: 'Manual review', label: 'Review rejected' },
  'report.generated': { icon: '📄', category: 'Report', label: 'Compliance report generated' },
  'mfi.suspended': { icon: '🚫', category: 'Admin action', label: 'MFI suspended' },
  'mfi.reactivated': { icon: '✅', category: 'Admin action', label: 'MFI reactivated' },
};
const AUDIT_CATEGORIES = [
  'All',
  'Admin action',
  'Manual review',
  'Verification',
  'Report',
  'System',
];

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
  'audit-logs': ['Audit Logs', 'Immutable platform-wide action trail'],
  security: ['Security', 'Protect your platform-admin account'],
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

const THEME_KEY = 'kyc_admin_theme';

/**
 * The platform-admin dashboard. A cross-tenant surface: it sees every MFI,
 * unlike the manager/agent dashboards. Same signal + setPage() shape as
 * those. Dark by default with a light-mode toggle (persisted); the choice
 * also drives the global loading splash via a class on the document root,
 * removed when this dashboard is torn down so the other surfaces stay light.
 * Overview, MFI Accounts and MFI Detail are wired to /admin/*; the
 * model-monitoring and operations sections are placeholders for now.
 */
@Component({
  selector: 'app-admin',
  imports: [DatePipe],
  templateUrl: './admin.component.html',
  styleUrl: './admin.component.scss',
  host: { '[class.theme-light]': "theme() === 'light'" },
})
export class AdminComponent implements OnDestroy {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  private readonly loading = inject(LoadingService);
  private readonly sanitizer = inject(DomSanitizer);
  readonly user = this.auth.principal;

  /** The enrolment QR (an SVG data URI) trusted for use in an <img src>. */
  readonly twoFaQr = computed<SafeUrl | null>(() => {
    const s = this.twoFaSetup();
    return s ? this.sanitizer.bypassSecurityTrustUrl(s.qr) : null;
  });

  readonly nav = NAV;
  readonly page = signal<AdminPage>('overview');

  readonly stats = signal<PlatformStats | null>(null);
  readonly mfis = signal<AdminMfiSummary[]>([]);
  readonly mfiFilter = signal<'all' | MfiStatus>('all');
  readonly detail = signal<AdminMfiDetail | null>(null);
  readonly search = signal('');
  readonly toast = signal('');
  readonly busyId = signal<string | null>(null);

  readonly auditEntries = signal<AdminAuditEntry[]>([]);
  readonly auditCategory = signal('All');
  readonly auditLimit = signal(50);
  readonly auditCategories = AUDIT_CATEGORIES;

  readonly theme = signal<'dark' | 'light'>(
    localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark',
  );

  // Two-factor (Security page) state.
  readonly twoFaEnabled = signal<boolean | null>(null);
  readonly twoFaSetup = signal<TwoFactorSetup | null>(null);
  readonly twoFaCode = signal('');
  readonly twoFaBusy = signal(false);
  readonly twoFaError = signal('');
  readonly twoFaMsg = signal('');

  constructor() {
    this.loadStats();
    this.loadMfis();
    // Reflect the theme onto the document root so the global loading splash
    // (a sibling component) can match it. Cleared in ngOnDestroy.
    effect(() => {
      const root = document.documentElement.classList;
      const dark = this.theme() === 'dark';
      root.toggle('admin-dark', dark);
      root.toggle('admin-light', !dark);
    });
  }

  toggleTheme(): void {
    this.theme.update((t) => (t === 'dark' ? 'light' : 'dark'));
    localStorage.setItem(THEME_KEY, this.theme());
  }

  ngOnDestroy(): void {
    document.documentElement.classList.remove('admin-dark', 'admin-light');
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
    if (p === 'audit-logs') this.loadAudit();
    if (p === 'security') this.loadTwoFa();
    this.loading.stop();
  }

  isActive(id: AdminPage): boolean {
    return this.page() === id;
  }

  refresh(): void {
    if (this.page() === 'overview') this.loadStats();
    else if (this.page() === 'mfi-accounts') this.loadMfis();
    else if (this.page() === 'audit-logs') this.loadAudit();
    else if (this.page() === 'security') this.loadTwoFa();
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

  loadAudit(): void {
    this.api.listAdminAudit(this.auditLimit()).subscribe({
      next: (e) => this.auditEntries.set(e),
      error: () => undefined,
    });
  }

  // ---- Two-factor auth ----
  loadTwoFa(): void {
    this.twoFaSetup.set(null);
    this.twoFaCode.set('');
    this.twoFaError.set('');
    this.twoFaMsg.set('');
    this.auth.twoFactorStatus().subscribe({
      next: (s) => this.twoFaEnabled.set(s.enabled),
      error: () => this.twoFaEnabled.set(null),
    });
  }

  startTwoFaSetup(): void {
    this.twoFaBusy.set(true);
    this.twoFaError.set('');
    this.auth.twoFactorSetup().subscribe({
      next: (s) => {
        this.twoFaBusy.set(false);
        this.twoFaSetup.set(s);
      },
      error: (e) => {
        this.twoFaBusy.set(false);
        this.twoFaError.set(this.errMsg(e, 'Could not start setup.'));
      },
    });
  }

  confirmTwoFa(): void {
    const code = this.twoFaCode().trim();
    if (!code) {
      this.twoFaError.set('Enter the code from your authenticator.');
      return;
    }
    this.twoFaBusy.set(true);
    this.twoFaError.set('');
    this.auth.twoFactorEnable(code).subscribe({
      next: () => {
        this.twoFaBusy.set(false);
        this.twoFaSetup.set(null);
        this.twoFaCode.set('');
        this.twoFaEnabled.set(true);
        this.twoFaMsg.set('Two-factor authentication is now on.');
      },
      error: (e) => {
        this.twoFaBusy.set(false);
        this.twoFaError.set(this.errMsg(e, 'That code was not accepted.'));
      },
    });
  }

  disableTwoFa(): void {
    const code = this.twoFaCode().trim();
    if (!code) {
      this.twoFaError.set('Enter a current code to turn 2FA off.');
      return;
    }
    this.twoFaBusy.set(true);
    this.twoFaError.set('');
    this.auth.twoFactorDisable(code).subscribe({
      next: () => {
        this.twoFaBusy.set(false);
        this.twoFaCode.set('');
        this.twoFaEnabled.set(false);
        this.twoFaMsg.set('Two-factor authentication is now off.');
      },
      error: (e) => {
        this.twoFaBusy.set(false);
        this.twoFaError.set(this.errMsg(e, 'That code was not accepted.'));
      },
    });
  }

  cancelTwoFaSetup(): void {
    this.twoFaSetup.set(null);
    this.twoFaCode.set('');
    this.twoFaError.set('');
  }

  private errMsg(err: unknown, fallback: string): string {
    const body = (err as { error?: { error?: { message?: string } } })?.error;
    return body?.error?.message ?? fallback;
  }

  setAuditCategory(c: string): void {
    this.auditCategory.set(c);
  }

  loadMoreAudit(): void {
    this.auditLimit.update((n) => Math.min(n + 50, 200));
    this.loadAudit();
  }

  readonly auditRows = computed(() => {
    const cat = this.auditCategory();
    return this.auditEntries()
      .map((e) => {
        const meta = ACTION_META[e.action] ?? {
          icon: '•',
          category: 'System',
          label: e.action,
        };
        const reason =
          e.details && typeof e.details['reason'] === 'string'
            ? (e.details['reason'] as string)
            : null;
        return {
          id: e.id,
          icon: meta.icon,
          category: meta.category,
          title: e.mfi_name ? `${meta.label} — ${e.mfi_name}` : meta.label,
          meta: [
            e.actor_type,
            reason ? `reason: ${reason}` : null,
            e.actor_id ? `actor ${e.actor_id.slice(0, 8)}` : null,
          ]
            .filter(Boolean)
            .join(' · '),
          time: new Date(e.timestamp).toLocaleString('en-US', {
            month: 'short',
            day: 'numeric',
            hour: '2-digit',
            minute: '2-digit',
          }),
        };
      })
      .filter((r) => cat === 'All' || r.category === cat);
  });

  readonly auditCounts = computed(() => {
    const rows = this.auditEntries().map(
      (e) => ACTION_META[e.action]?.category ?? 'System',
    );
    const of = (c: string) => rows.filter((r) => r === c).length;
    return {
      total: rows.length,
      admin: of('Admin action'),
      review: of('Manual review'),
    };
  });

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
