import { Component, computed, signal } from '@angular/core';

type ManagerPage =
  | 'dashboard'
  | 'review'
  | 'history'
  | 'reports'
  | 'agents'
  | 'apikeys'
  | 'settings';

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

const DAY_DATA = [
  { label: '4', v: 60, p: 8, r: 6 }, { label: '5', v: 72, p: 6, r: 5 },
  { label: '6', v: 52, p: 9, r: 7 }, { label: '7', v: 82, p: 7, r: 5 },
  { label: '8', v: 65, p: 8, r: 6 }, { label: '9', v: 78, p: 6, r: 5 },
  { label: '10', v: 56, p: 9, r: 7 }, { label: '11', v: 83, p: 5, r: 4 },
  { label: '12', v: 76, p: 6, r: 5 }, { label: '13', v: 70, p: 8, r: 6 },
  { label: '14', v: 60, p: 7, r: 6 }, { label: '15', v: 80, p: 6, r: 4 },
  { label: '16', v: 68, p: 8, r: 6 }, { label: '17', v: 79, p: 6, r: 5 },
];

const BRANCHES = [
  { name: 'Mvog-Ada', value: 412, pct: 100 },
  { name: 'Biyem-Assi', value: 331, pct: 80 },
  { name: 'Mokolo', value: 271, pct: 66 },
  { name: 'Bafoussam', value: 210, pct: 51 },
];

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

  readonly branches = BRANCHES;
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
    };
    return map[this.page()];
  });

  // ---- Dashboard chart geometry ----
  readonly dayBars = computed(() => {
    const max = Math.max(...DAY_DATA.map((d) => d.v + d.p + d.r));
    return DAY_DATA.map((d) => ({
      label: d.label,
      v: (d.v / max) * 100,
      p: (d.p / max) * 100,
      r: (d.r / max) * 100,
    }));
  });

  readonly donutBg =
    'conic-gradient(var(--ox-green) 0% 91.4%, var(--ox-orange) 91.4% ' +
    '97.2%, var(--ox-red) 97.2% 100%)';

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

  badgeClass(status: string): string {
    return `ox-badge ox-badge--${status.toLowerCase()}`;
  }
}
