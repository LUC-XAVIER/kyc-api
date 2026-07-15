import {
  Component,
  computed,
  effect,
  ElementRef,
  inject,
  signal,
  viewChild,
} from '@angular/core';

import { ApiService } from '../../core/api.service';
import { AuthService } from '../../core/auth.service';
import {
  AgentProfile,
  DocumentType,
  VerificationDetail,
  VerificationSummary,
  VerifyResponse,
} from '../../core/models';
import { isValidPin } from '../../core/validators';

type AgentPage = 'new' | 'submissions' | 'profile';
type SubStatus = 'Verified' | 'Pending' | 'Rejected' | 'Approved';
type DocKey = 'front' | 'back' | 'selfie';

interface Capture {
  url: string;
  file: File;
}

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

function statusLabel(s: string): SubStatus {
  return (s.charAt(0) + s.slice(1).toLowerCase()) as SubStatus;
}

function scoreLabel(score: number | null): string {
  return score == null ? '—' : `${Math.round(score * 100)}%`;
}

function dateLabel(iso: string): string {
  const d = new Date(iso);
  const date = d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' });
  const time = d.toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  });
  return `${date}, ${time}`;
}

/**
 * Agent application: New Verification (live camera capture → POST /kyc/verify),
 * My Submissions (agent-scoped list + detail), and Profile (/auth/me +
 * change-PIN). Signals-based; talks to the real API.
 */
@Component({
  selector: 'app-agent',
  templateUrl: './agent.component.html',
  styleUrl: './agent.component.scss',
})
export class AgentComponent {
  private readonly auth = inject(AuthService);
  private readonly api = inject(ApiService);
  readonly user = this.auth.principal;
  readonly userInitials = computed(() =>
    initialsOf(this.user()?.full_name ?? 'A'),
  );

  private readonly camVideo =
    viewChild<ElementRef<HTMLVideoElement>>('cam');
  private stream: MediaStream | null = null;

  constructor() {
    this.loadSubmissions();
    this.loadProfile();
    // Attach the live camera stream once the <video> is in the DOM.
    effect(() => {
      const el = this.camVideo();
      if (el && this.stream) {
        el.nativeElement.srcObject = this.stream;
        void el.nativeElement.play().catch(() => undefined);
      }
    });
  }

  logout(): void {
    this.auth.logout();
  }

  readonly page = signal<AgentPage>('new');

  // ---- New verification ----
  readonly clientId = signal('');
  readonly docType = signal<DocumentType>('NIC');
  readonly captured = signal<Record<DocKey, Capture | null>>({
    front: null,
    back: null,
    selfie: null,
  });
  readonly verifying = signal(false);
  readonly result = signal<VerifyResponse | null>(null);
  readonly verifyError = signal('');

  // Camera modal
  readonly cameraOpen = signal<DocKey | null>(null);
  readonly cameraError = signal('');

  readonly requiredDocs = computed<DocKey[]>(() =>
    this.docType() === 'PASSPORT' ? ['front', 'selfie'] : ['front', 'back', 'selfie'],
  );

  readonly allCaptured = computed(() =>
    this.requiredDocs().every((k) => this.captured()[k] !== null),
  );

  readonly canVerify = computed(
    () => this.clientId().trim().length > 0 && this.allCaptured(),
  );

  isCaptured(key: DocKey): boolean {
    return this.captured()[key] !== null;
  }

  docLabel(key: DocKey): string {
    if (key === 'front') return 'ID card — front';
    if (key === 'back') return 'ID card — back';
    return 'Selfie';
  }

  async openCamera(key: DocKey): Promise<void> {
    this.cameraError.set('');
    const media = navigator.mediaDevices;
    if (!media?.getUserMedia) {
      this.cameraError.set('Camera not available on this device.');
      this.cameraOpen.set(key);
      return;
    }
    try {
      this.stream = await media.getUserMedia({
        video: { facingMode: key === 'selfie' ? 'user' : 'environment' },
        audio: false,
      });
      this.cameraOpen.set(key);
    } catch {
      this.cameraError.set('Could not access the camera — check permissions.');
      this.cameraOpen.set(key);
    }
  }

  /** Snapshot the current video frame into a File for the given slot. */
  capture(key: DocKey): void {
    const video = this.camVideo()?.nativeElement;
    if (!video || !this.stream) return;
    const canvas = document.createElement('canvas');
    canvas.width = video.videoWidth || 640;
    canvas.height = video.videoHeight || 480;
    canvas.getContext('2d')?.drawImage(video, 0, 0, canvas.width, canvas.height);
    canvas.toBlob(
      (blob) => {
        if (!blob) return;
        const prev = this.captured()[key];
        if (prev) URL.revokeObjectURL(prev.url);
        const file = new File([blob], `${key}.jpg`, { type: 'image/jpeg' });
        this.captured.update((c) => ({
          ...c,
          [key]: { url: URL.createObjectURL(blob), file },
        }));
        this.closeCamera();
      },
      'image/jpeg',
      0.9,
    );
  }

  closeCamera(): void {
    this.stopStream();
    this.cameraOpen.set(null);
  }

  private stopStream(): void {
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = null;
  }

  resetForm(): void {
    Object.values(this.captured()).forEach(
      (c) => c && URL.revokeObjectURL(c.url),
    );
    this.captured.set({ front: null, back: null, selfie: null });
    this.clientId.set('');
    this.result.set(null);
    this.verifyError.set('');
    this.verifying.set(false);
  }

  verify(): void {
    if (!this.canVerify() || this.verifying()) return;
    const cap = this.captured();
    const fd = new FormData();
    fd.append('client_id', this.clientId().trim());
    fd.append('document_type', this.docType());
    fd.append('id_front', cap.front!.file);
    fd.append('selfie', cap.selfie!.file);
    if (this.docType() === 'NIC' && cap.back) {
      fd.append('id_back', cap.back.file);
    }
    this.verifying.set(true);
    this.verifyError.set('');
    this.result.set(null);
    this.api.verify(fd).subscribe({
      next: (r) => {
        this.result.set(r);
        this.verifying.set(false);
        this.loadSubmissions();
      },
      error: (err) => {
        this.verifying.set(false);
        const body = (err as { error?: { error?: { message?: string } } })
          ?.error;
        this.verifyError.set(
          body?.error?.message ?? 'Verification failed — please try again.',
        );
      },
    });
  }

  scorePct(score: number | null): string {
    return scoreLabel(score);
  }

  // ---- My submissions ----
  readonly subData = signal<VerificationSummary[]>([]);
  readonly subsLoading = signal(false);
  readonly subsError = signal(false);
  readonly filter = signal<'all' | SubStatus>('all');
  readonly search = signal('');
  readonly selectedId = signal<string | null>(null);
  readonly selectedDetail = signal<VerificationDetail | null>(null);

  loadSubmissions(): void {
    this.subsLoading.set(true);
    this.subsError.set(false);
    this.api.listVerifications().subscribe({
      next: (rows) => {
        this.subData.set(rows);
        this.subsLoading.set(false);
        if (!this.subData().some((s) => s.id === this.selectedId())) {
          this.selectedId.set(this.subData()[0]?.id ?? null);
        }
      },
      error: () => {
        this.subsError.set(true);
        this.subsLoading.set(false);
      },
    });
  }

  readonly rows = computed(() =>
    this.subData().map((s) => ({
      id: s.id,
      client: s.client_id,
      name: s.client_name ?? s.client_id,
      initials: initialsOf(s.client_name ?? s.client_id),
      date: dateLabel(s.created_at),
      status: statusLabel(s.status),
      score: scoreLabel(s.confidence_score),
    })),
  );

  readonly counts = computed(() => {
    const r = this.rows();
    return {
      all: r.length,
      Verified: r.filter((s) => s.status === 'Verified').length,
      Pending: r.filter((s) => s.status === 'Pending').length,
      Rejected: r.filter((s) => s.status === 'Rejected').length,
    };
  });

  readonly filtered = computed(() => {
    const f = this.filter();
    const q = this.search().trim().toLowerCase();
    return this.rows()
      .filter((s) => f === 'all' || s.status === f)
      .filter(
        (s) =>
          !q ||
          s.client.toLowerCase().includes(q) ||
          s.name.toLowerCase().includes(q),
      );
  });

  readonly selected = computed(
    () =>
      this.filtered().find((s) => s.id === this.selectedId()) ??
      this.filtered()[0],
  );

  readonly detailFaceMatch = computed(() => {
    const fm = this.selectedDetail()?.face_match_result;
    if (!fm) return '—';
    return `${fm.match_score.toFixed(2)} — ${fm.verified ? 'match' : 'no match'}`;
  });
  readonly detailLiveness = computed(() => {
    const lv = this.selectedDetail()?.liveness_result;
    return lv ? (lv.passed ? 'Passed' : 'Failed') : '—';
  });

  selectSubmission(id: string): void {
    this.selectedId.set(id);
    this.selectedDetail.set(null);
    this.api.getVerification(id).subscribe({
      next: (d) => {
        if (this.selectedId() === id) this.selectedDetail.set(d);
      },
      error: () => undefined,
    });
  }

  setFilter(f: 'all' | SubStatus): void {
    this.filter.set(f);
  }

  // ---- Profile ----
  readonly profile = signal<AgentProfile | null>(null);
  readonly curPin = signal('');
  readonly newPin = signal('');
  readonly confirmPin = signal('');
  readonly pinError = signal('');
  readonly pinSaved = signal(false);
  readonly pinSaving = signal(false);

  readonly profileStats = computed(() => {
    const r = this.rows();
    const total = r.length;
    const verified = r.filter(
      (s) => s.status === 'Verified' || s.status === 'Approved',
    ).length;
    const pending = r.filter((s) => s.status === 'Pending').length;
    return {
      total,
      rate: total ? `${Math.round((verified / total) * 100)}%` : '—',
      pending,
    };
  });

  loadProfile(): void {
    this.api.me().subscribe({
      next: (p) => this.profile.set(p),
      error: () => undefined,
    });
  }

  updatePin(): void {
    if (this.pinSaving()) return;
    if (!isValidPin(this.newPin())) {
      this.pinError.set('New PIN must be 6–8 digits.');
      return;
    }
    if (this.newPin() !== this.confirmPin()) {
      this.pinError.set('PINs do not match.');
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
        this.confirmPin.set('');
        setTimeout(() => this.pinSaved.set(false), 2500);
      },
      error: (err) => {
        this.pinSaving.set(false);
        const body = (err as { error?: { error?: { message?: string } } })
          ?.error;
        this.pinError.set(body?.error?.message ?? 'Could not change the PIN.');
      },
    });
  }

  readonly title = computed<[string, string]>(() => {
    const branch = this.profile()?.branch
      ? ` · Branch: ${this.profile()!.branch}`
      : '';
    const mfi = this.profile()?.mfi_name ?? '';
    const map: Record<AgentPage, [string, string]> = {
      new: ['New KYC Verification', mfi + branch],
      submissions: ['My Submissions', mfi + branch],
      profile: ['My Profile', mfi],
    };
    return map[this.page()];
  });

  setPage(p: AgentPage): void {
    this.page.set(p);
    this.result.set(null);
    if (p === 'submissions') this.loadSubmissions();
  }

  badgeClass(status: string): string {
    return `ox-badge ox-badge--${status.toLowerCase()}`;
  }
}
