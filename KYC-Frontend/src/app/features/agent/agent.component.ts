import { Component, computed, inject, signal } from '@angular/core';

import { AuthService } from '../../core/auth.service';

type AgentPage = 'new' | 'submissions' | 'profile';
type SubStatus = 'Verified' | 'Pending' | 'Rejected';
type DocKey = 'front' | 'back' | 'selfie';

interface Submission {
  id: string;
  initials: string;
  name: string;
  date: string;
  status: SubStatus;
  score: string;
  faceMatch: string;
  time: string;
}

/** Mock data — replaced by the API in the backend-integration phase. */
const SUBMISSIONS: Submission[] = [
  { id: 'CLT-00482', initials: 'JF', name: 'FOTSO Jean-Pierre', date: '17 Jun, 14:32', status: 'Verified', score: '96%', faceMatch: '0.96 — match', time: '4.2s' },
  { id: 'CLT-00481', initials: 'MN', name: 'MBARGA Nicole', date: '17 Jun, 11:14', status: 'Verified', score: '93%', faceMatch: '0.93 — match', time: '3.8s' },
  { id: 'CLT-00479', initials: 'PT', name: 'PENDA Thierry', date: '16 Jun, 15:08', status: 'Pending', score: '87%', faceMatch: '0.87 — match', time: '4.9s' },
  { id: 'CLT-00471', initials: 'SA', name: 'SIMO Alice', date: '15 Jun, 10:22', status: 'Verified', score: '91%', faceMatch: '0.91 — match', time: '4.1s' },
  { id: 'CLT-00468', initials: 'RK', name: 'RIGOBERT Kamdem', date: '14 Jun, 09:45', status: 'Rejected', score: '34%', faceMatch: '0.34 — no match', time: '5.6s' },
  { id: 'CLT-00460', initials: 'AB', name: 'ABENA Blaise', date: '13 Jun, 16:30', status: 'Verified', score: '95%', faceMatch: '0.95 — match', time: '3.5s' },
  { id: 'CLT-00455', initials: 'EN', name: 'EYENGA Nadege', date: '12 Jun, 13:11', status: 'Pending', score: '82%', faceMatch: '0.82 — match', time: '4.4s' },
];

/**
 * Agent application: New Verification, My Submissions, Profile. State is
 * held in signals; the filters, search, and derived views are computed.
 * Data is mocked locally until the backend-integration phase.
 */
@Component({
  selector: 'app-agent',
  templateUrl: './agent.component.html',
  styleUrl: './agent.component.scss',
})
export class AgentComponent {
  private readonly auth = inject(AuthService);
  readonly user = this.auth.principal;
  readonly userInitials = computed(() => {
    const name = this.user()?.full_name ?? '';
    return (
      name
        .split(/\s+/)
        .map((w) => w[0])
        .slice(0, 2)
        .join('')
        .toUpperCase() || 'A'
    );
  });

  logout(): void {
    this.auth.logout();
  }

  readonly docKeys: DocKey[] = ['front', 'back', 'selfie'];

  readonly page = signal<AgentPage>('new');
  readonly docs = signal<Record<DocKey, boolean>>({
    front: false,
    back: false,
    selfie: false,
  });
  readonly verifying = signal(false);
  readonly verified = signal(false);

  readonly filter = signal<'all' | SubStatus>('all');
  readonly search = signal('');
  readonly selectedId = signal<string | null>(SUBMISSIONS[0].id);

  readonly curPw = signal('');
  readonly newPw = signal('');
  readonly confirmPw = signal('');
  readonly pwSaved = signal(false);

  readonly allCaptured = computed(() => {
    const d = this.docs();
    return d.front && d.back && d.selfie;
  });

  readonly counts = computed(() => ({
    all: SUBMISSIONS.length,
    Verified: SUBMISSIONS.filter((s) => s.status === 'Verified').length,
    Pending: SUBMISSIONS.filter((s) => s.status === 'Pending').length,
    Rejected: SUBMISSIONS.filter((s) => s.status === 'Rejected').length,
  }));

  readonly filtered = computed(() => {
    const f = this.filter();
    const q = this.search().trim().toLowerCase();
    let rows = SUBMISSIONS;
    if (f !== 'all') rows = rows.filter((s) => s.status === f);
    if (q) {
      rows = rows.filter(
        (s) =>
          s.id.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q),
      );
    }
    return rows;
  });

  readonly selected = computed(() =>
    this.filtered().find((s) => s.id === this.selectedId()) ??
    this.filtered()[0],
  );

  readonly title = computed(() => {
    const map: Record<AgentPage, [string, string]> = {
      new: ['New KYC Verification', 'CamFinance Microfinance · Branch: Mvog-Ada'],
      submissions: ['My Submissions', 'CamFinance Microfinance · Branch: Mvog-Ada'],
      profile: ['My Profile', 'CamFinance Microfinance'],
    };
    return map[this.page()];
  });

  setPage(p: AgentPage): void {
    this.page.set(p);
    this.verified.set(false);
  }

  toggleDoc(key: DocKey): void {
    this.docs.update((d) => ({ ...d, [key]: !d[key] }));
  }

  isCaptured(key: DocKey): boolean {
    return this.docs()[key];
  }

  docLabel(key: DocKey): string {
    if (key === 'front') return 'ID card — front';
    if (key === 'back') return 'ID card — back';
    return 'Selfie';
  }

  resetForm(): void {
    this.docs.set({ front: false, back: false, selfie: false });
    this.verified.set(false);
    this.verifying.set(false);
  }

  verify(): void {
    if (!this.allCaptured() || this.verifying()) return;
    this.verifying.set(true);
    // Simulated for now; the real POST /kyc/verify lands in the API phase.
    setTimeout(() => {
      this.verifying.set(false);
      this.verified.set(true);
    }, 900);
  }

  setFilter(f: 'all' | SubStatus): void {
    this.filter.set(f);
  }

  updatePassword(): void {
    this.pwSaved.set(true);
    this.newPw.set('');
    this.confirmPw.set('');
    setTimeout(() => this.pwSaved.set(false), 2500);
  }

  badgeClass(status: string): string {
    return `ox-badge ox-badge--${status.toLowerCase()}`;
  }
}
