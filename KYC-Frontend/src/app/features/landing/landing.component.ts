import { Component, computed, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';

import { AuthService } from '../../core/auth.service';
import { OnboardingService } from '../../core/onboarding.service';
import { Plan, PLANS } from '../../core/plans';
import { isValidEmail } from '../../core/validators';

type Page = 'home' | 'users' | 'pricing' | 'contact' | 'demo';

/** Inner SVG markup for the small icon set the landing page uses. Kept inline
 *  (no icon-font dependency) and rendered through the sanitizer bypass since
 *  every value here is a trusted constant. */
const ICON: Record<string, string> = {
  'shield-check':
    '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><polyline points="9 12 11 14 15 10"/>',
  play: '<polygon points="6 4 20 12 6 20" fill="currentColor" stroke="none"/>',
  camera:
    '<path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"/><circle cx="12" cy="13" r="4"/>',
  scan: '<path d="M3 7V5a2 2 0 0 1 2-2h2"/><path d="M17 3h2a2 2 0 0 1 2 2v2"/><path d="M21 17v2a2 2 0 0 1-2 2h-2"/><path d="M7 21H5a2 2 0 0 1-2-2v-2"/><line x1="7" y1="12" x2="17" y2="12"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/>',
  'user-check':
    '<path d="M16 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"/><circle cx="8.5" cy="7" r="4"/><polyline points="17 11 19 13 23 9"/>',
  'copy-check':
    '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  'circle-check':
    '<circle cx="12" cy="12" r="10"/><polyline points="8 12 11 15 16 9"/>',
  'face-id':
    '<path d="M4 8V6a2 2 0 0 1 2-2h2"/><path d="M16 4h2a2 2 0 0 1 2 2v2"/><path d="M20 16v2a2 2 0 0 1-2 2h-2"/><path d="M8 20H6a2 2 0 0 1-2-2v-2"/><line x1="9" y1="10" x2="9" y2="11"/><line x1="15" y1="10" x2="15" y2="11"/><path d="M9 14s1 1.5 3 1.5 3-1.5 3-1.5"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>',
  dashboard:
    '<rect x="3" y="3" width="7" height="9" rx="1"/><rect x="14" y="3" width="7" height="5" rx="1"/><rect x="14" y="12" width="7" height="9" rx="1"/><rect x="3" y="16" width="7" height="5" rx="1"/>',
  certificate:
    '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><circle cx="12" cy="15" r="2"/>',
  api: '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
  lock: '<rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/>',
  mail: '<rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="22 6 12 13 2 6"/>',
  phone:
    '<path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.09 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.36 1.9.7 2.81a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.34 1.85.57 2.81.7A2 2 0 0 1 22 16.92z"/>',
  'map-pin':
    '<path d="M21 10c0 7-9 13-9 13s-9-6-9-13a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  github:
    '<path d="M9 19c-5 1.5-5-2.5-7-3m14 6v-3.87a3.37 3.37 0 0 0-.94-2.61c3.14-.35 6.44-1.54 6.44-7A5.44 5.44 0 0 0 20 4.77 5.07 5.07 0 0 0 19.91 1S18.73.65 16 2.48a13.4 13.4 0 0 0-7 0C6.27.65 5.09 1 5.09 1A5.07 5.07 0 0 0 5 4.77a5.44 5.44 0 0 0-1.5 3.78c0 5.42 3.3 6.61 6.44 7A3.37 3.37 0 0 0 9 18.13V22"/>',
  check: '<polyline points="20 6 9 17 4 12"/>',
  plus: '<line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>',
  calendar:
    '<rect x="3" y="4" width="18" height="18" rx="2"/><line x1="16" y1="2" x2="16" y2="6"/><line x1="8" y1="2" x2="8" y2="6"/><line x1="3" y1="10" x2="21" y2="10"/>',
  'arrow-right':
    '<line x1="5" y1="12" x2="19" y2="12"/><polyline points="12 5 19 12 12 19"/>',
};

interface DemoResult {
  kyc_status: 'VERIFIED' | 'PENDING' | 'REJECTED';
  confidence_score?: number | null;
  liveness_passed?: boolean | null;
  anti_spoof_score?: number | null;
  face_match_score?: number | null;
  duplicate_found?: boolean;
  duplicate_match?: Record<string, string | number>;
  rejection_reason?: string;
  flags?: string[];
  extracted_info?: Record<string, string>;
  processing_time_ms: number;
}

const DEMO: Record<string, DemoResult> = {
  verified: {
    kyc_status: 'VERIFIED',
    confidence_score: 0.96,
    liveness_passed: true,
    anti_spoof_score: 0.94,
    face_match_score: 0.91,
    duplicate_found: false,
    extracted_info: {
      full_name: 'FOTSO Jean-Pierre',
      id_number: '118220441',
      date_of_birth: '1990-05-14',
      expiry_date: '2028-04-30',
      sex: 'M',
    },
    processing_time_ms: 4240,
  },
  pending: {
    kyc_status: 'PENDING',
    confidence_score: 0.87,
    liveness_passed: true,
    anti_spoof_score: 0.91,
    face_match_score: 0.88,
    duplicate_found: true,
    duplicate_match: { matched_client_id: 'CLT-00047', similarity_score: 0.94 },
    flags: ['DUPLICATE_DETECTED'],
    processing_time_ms: 4890,
  },
  rejected_spoof: {
    kyc_status: 'REJECTED',
    confidence_score: 0.12,
    liveness_passed: false,
    anti_spoof_score: 0.18,
    face_match_score: null,
    duplicate_found: false,
    rejection_reason: 'LIVENESS_FAILED',
    processing_time_ms: 1820,
  },
  rejected_mismatch: {
    kyc_status: 'REJECTED',
    confidence_score: 0.31,
    liveness_passed: true,
    anti_spoof_score: 0.89,
    face_match_score: 0.29,
    duplicate_found: false,
    rejection_reason: 'FACE_MISMATCH',
    processing_time_ms: 3650,
  },
  rejected_expired: {
    kyc_status: 'REJECTED',
    confidence_score: 0,
    liveness_passed: null,
    face_match_score: null,
    duplicate_found: false,
    rejection_reason: 'ID_EXPIRED',
    extracted_info: { expiry_date: '2021-03-15' },
    processing_time_ms: 980,
  },
};

/** One rendered line of the fake JSON demo response. */
interface ResultLine {
  key: string;
  val: string;
  cls: string;
  indent?: boolean;
}

/**
 * Public marketing site: hero + pipeline, features, how-it-works, FAQ, who
 * uses it, pricing (wired to the real signup flow), contact, and a sandbox
 * demo. In-page navigation via a `page` signal; nothing changes route except
 * Sign in (→ /login) and the plan signup link.
 */
@Component({
  selector: 'app-landing',
  imports: [RouterLink],
  templateUrl: './landing.component.html',
  styleUrl: './landing.component.scss',
})
export class LandingComponent {
  private readonly onboarding = inject(OnboardingService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly sanitizer = inject(DomSanitizer);

  readonly page = signal<Page>('home');
  readonly plans = PLANS;

  // ---- Signup flow (unchanged) ----
  readonly selected = signal<Plan | null>(null);
  readonly email = signal('');
  readonly error = signal('');
  readonly loading = signal(false);
  readonly sentEmail = signal('');
  readonly sentLink = signal<string | null>(null);

  // ---- Static content ----
  readonly pipeline = [
    { icon: 'camera', title: 'NIC capture', sub: 'Front · back · selfie' },
    { icon: 'scan', title: 'OCR extraction', sub: 'Name · ID · expiry' },
    { icon: 'eye', title: 'Liveness check', sub: 'Anti-spoofing' },
    { icon: 'user-check', title: 'Face matching', sub: 'ArcFace model' },
    { icon: 'copy-check', title: 'Duplicate check', sub: 'Cross-MFI FAISS' },
    { icon: 'circle-check', title: 'Verdict', sub: 'Verified · Pending · Rejected' },
  ];
  readonly features = [
    { icon: 'scan', title: 'OCR on Cameroonian NIC', desc: 'Automatically reads name, ID number, date of birth, place of birth, expiry date, and sex from the national identity card.' },
    { icon: 'face-id', title: 'ArcFace face matching', desc: "Compares the client's selfie to the photo on their NIC using the ArcFace deep learning model — 97%+ accuracy." },
    { icon: 'shield', title: 'Anti-spoofing detection', desc: "Detects printed-photo and screen-replay attacks — even via API integrations where you can't control the capture device." },
    { icon: 'copy-check', title: 'Duplicate detection', desc: 'FAISS vector similarity search across stored face embeddings catches the same person registering under multiple identities.' },
    { icon: 'dashboard', title: 'Full management dashboard', desc: 'Every subscriber gets a dashboard for agents, managers, compliance reports, statistics, and subscription usage — in every plan.' },
    { icon: 'certificate', title: 'COBAC compliance reports', desc: 'Generate audit-ready PDF reports on demand — every verification, timestamp, agent, and decision recorded and exportable.' },
    { icon: 'api', title: 'REST API integration', desc: 'MFIs with existing software call POST /kyc/verify from any application. JWT auth, rate limiting, full Swagger docs included.' },
    { icon: 'lock', title: 'Biometric data security', desc: 'Face images and embeddings are encrypted at rest. Role-based access control ensures only authorized staff can view client data.' },
  ];
  readonly stats = [
    { num: '<5s', label: 'Full pipeline time' },
    { num: '<1%', label: 'False acceptance rate' },
    { num: '97%+', label: 'Face-match accuracy' },
    { num: '100%', label: 'Open-source stack' },
  ];
  readonly steps = [
    { n: 1, title: 'Agent opens the dashboard or your own app', desc: 'Every subscribing MFI gets a web dashboard. If your MFI already has software, your developers integrate KYC-API via a single REST endpoint — POST /kyc/verify — and your agents keep using the interface they know.' },
    { n: 2, title: 'Agent captures three images on-site', desc: 'The client’s NIC front, NIC back, and a selfie — all taken live via the camera. No file upload. The client is physically present with the agent throughout.' },
    { n: 3, title: 'KYC-API runs the full verification pipeline', desc: 'In under 5 seconds: OCR extracts identity fields, liveness detection confirms a real person is present, ArcFace matches the selfie to the NIC photo, and FAISS checks for duplicate registrations across all MFIs.' },
    { n: 4, title: 'Agent and manager act on the result', desc: 'VERIFIED — client is onboarded immediately. PENDING — a duplicate flag requires the manager to review and approve or reject. REJECTED — identity check failed; the agent is told the reason.' },
  ];
  readonly faqs = [
    { q: 'Do agents need to be tech-savvy to use KYC-API?', a: 'No. The dashboard is designed for field agents in Cameroonian MFIs. The workflow is three steps: open the form, take three photos with the camera, submit. The result appears on screen within seconds.' },
    { q: 'What documents does KYC-API support?', a: "KYC-API is currently optimized for the Cameroonian National Identity Card (Carte Nationale d'Identité). The OCR extraction, expiry detection, and layout-based cropping are all tuned for its specific layout and typography." },
    { q: 'Can we integrate KYC-API into our existing software?', a: 'Yes. Growth, Pro, and Enterprise plans include API access. Your developers integrate a single endpoint — POST /kyc/verify — using an API key. Even via API, your managers still use the dashboard for reviews, statistics, and compliance reports.' },
    { q: 'How does KYC-API prevent duplicate clients across branches?', a: "Every verified client's face embedding — a 512-dimensional fingerprint — is stored in a FAISS index. When a new client registers, their embedding is compared against the index; if similarity exceeds the threshold, the case is flagged PENDING for human review." },
    { q: 'Is biometric data shared between MFIs?', a: 'Raw images and identity fields are never shared between MFIs — each MFI sees only its own client records. Only anonymized face embeddings participate in duplicate detection, and these cannot be reverse-engineered into a recognizable image.' },
    { q: 'What happens when a client is flagged as PENDING?', a: 'The manager is notified and the case appears in the review queue. They see the selfie and NIC photos plus all scores and the matched duplicate, then approve or reject — and the decision is logged for COBAC audit purposes.' },
    { q: 'How are COBAC compliance reports generated?', a: 'Managers generate a PDF report from the dashboard for any date range. It includes every verification with client ID, date, branch, agent, and final status — formatted for COBAC audit submission, downloadable immediately.' },
    { q: 'Can we upgrade our plan as our volume grows?', a: 'Yes. Upgrades take effect on your next billing cycle or immediately on confirmation. At 80% of your monthly quota your dashboard shows a warning; at 100%, new submissions pause until the cycle resets or you upgrade.' },
  ];
  readonly users = [
    { type: 'Small MFI', title: 'Single-branch cooperatives', desc: 'A small MFI in a rural commune with one branch and a few agents. No existing software — agents log directly into the dashboard. Starter plan; monthly COBAC reports for audits.' },
    { type: 'Growing MFI', title: 'Multi-branch MFIs', desc: 'An established MFI across several towns. Agents at each branch use the dashboard; the manager monitors statistics, reviews duplicate flags, and tracks all branches from one view. Growth plan.' },
    { type: 'MFI network', title: 'Regional MFI federations', desc: 'A federation managing 20+ branches across regions. Pro plan with API integration — their internal system calls KYC-API at registration, managers use the dashboard for oversight and reporting.' },
    { type: 'Fintech platform', title: 'Digital financial platforms', desc: 'A platform powering multiple MFIs integrates KYC-API via the REST API. Each client registration triggers a verification call; their platform owns the UX, KYC-API owns identity assurance.' },
    { type: 'Core banking', title: 'MFIs with existing software', desc: 'An MFI running Musoni, Mifos X, or a custom loan system integrates KYC-API with a simple API call at onboarding. Agents keep their existing app; verification happens in the background.' },
    { type: 'Enterprise', title: 'Commercial banks & large institutions', desc: 'A bank needing a dedicated identity-verification layer alongside core banking. Enterprise plan: dedicated infrastructure, SLA-backed uptime, and a dedicated account manager.' },
  ];
  readonly testimonials = [
    { quote: 'Before KYC-API, we had no way of knowing if the same person had already registered at another caisse in our network. Now every flagged duplicate goes to review immediately.', cite: '— MFI Manager, Yaoundé' },
    { quote: 'Our agents were spending 15 minutes per client on manual verification. With KYC-API it takes under a minute — and we have a digital record for COBAC.', cite: '— Operations Director, regional MFI' },
    { quote: 'Integrating KYC-API into our platform took two days. The docs are clear, the response is fast, and the compliance reporting is exactly what our MFI clients needed.', cite: '— Developer, fintech platform' },
  ];
  readonly regions = ['Yaoundé', 'Douala', 'Bafoussam', 'Garoua', 'Ngaoundéré', 'Maroua', 'Bertoua', 'Ebolowa', 'CEMAC zone'];
  readonly contactMethods = [
    { icon: 'mail', label: 'Email', value: 'zazap1731@gmail.com' },
    { icon: 'phone', label: 'Phone', value: '+237 697 49 25 91 · 677 18 60 87' },
    { icon: 'map-pin', label: 'Address', value: 'Yaoundé, Cameroon' },
    { icon: 'github', label: 'GitHub', value: 'github.com/LUC-XAVIER/kyc-api' },
  ];
  readonly demoFeatures = [
    'Live OCR field extraction from NIC',
    'Liveness and anti-spoofing score',
    'Face match score and threshold',
    'Duplicate detection result',
    'Final KYC status and confidence',
    'Full JSON API response format',
  ];
  readonly demoScenarios = [
    { value: 'verified', label: 'Happy path — returns VERIFIED' },
    { value: 'pending', label: 'Duplicate detected — returns PENDING' },
    { value: 'rejected_spoof', label: 'Spoofing attempt — returns REJECTED' },
    { value: 'rejected_mismatch', label: 'Face mismatch — returns REJECTED' },
    { value: 'rejected_expired', label: 'Expired ID card — returns REJECTED' },
  ];

  // ---- FAQ ----
  readonly openFaqs = signal<Set<string>>(new Set());
  toggleFaq(q: string): void {
    this.openFaqs.update((s) => {
      const next = new Set(s);
      if (next.has(q)) next.delete(q);
      else next.add(q);
      return next;
    });
  }

  // ---- Demo sandbox ----
  readonly scenario = signal('verified');
  readonly demoRunning = signal(false);
  readonly demoLines = signal<ResultLine[] | null>(null);

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.router.navigateByUrl(this.auth.homeRoute());
    }
  }

  icon(name: string): SafeHtml {
    const svg =
      '<svg viewBox="0 0 24 24" width="100%" height="100%" fill="none" ' +
      'stroke="currentColor" stroke-width="2" stroke-linecap="round" ' +
      `stroke-linejoin="round">${ICON[name] ?? ''}</svg>`;
    return this.sanitizer.bypassSecurityTrustHtml(svg);
  }

  setPage(p: Page): void {
    this.page.set(p);
    window.scrollTo(0, 0);
  }

  runDemo(): void {
    if (this.demoRunning()) return;
    this.demoRunning.set(true);
    this.demoLines.set(null);
    setTimeout(() => {
      this.demoLines.set(this.buildLines(DEMO[this.scenario()]));
      this.demoRunning.set(false);
    }, 1600);
  }

  private buildLines(d: DemoResult): ResultLine[] {
    const statusCls =
      d.kyc_status === 'VERIFIED'
        ? 'val-green'
        : d.kyc_status === 'PENDING'
          ? 'val-orange'
          : 'val-red';
    const lines: ResultLine[] = [
      { key: 'kyc_status', val: `"${d.kyc_status}"`, cls: statusCls },
    ];
    if (d.confidence_score != null)
      lines.push({ key: 'confidence_score', val: d.confidence_score.toFixed(2), cls: 'val' });
    if (d.liveness_passed != null)
      lines.push({ key: 'liveness_passed', val: String(d.liveness_passed), cls: d.liveness_passed ? 'val-green' : 'val-red' });
    if (d.anti_spoof_score != null)
      lines.push({ key: 'anti_spoof_score', val: d.anti_spoof_score.toFixed(2), cls: 'val' });
    if (d.face_match_score != null)
      lines.push({ key: 'face_match_score', val: d.face_match_score.toFixed(2), cls: 'val' });
    if (d.duplicate_found != null)
      lines.push({ key: 'duplicate_found', val: String(d.duplicate_found), cls: d.duplicate_found ? 'val-orange' : 'val' });
    if (d.rejection_reason)
      lines.push({ key: 'rejection_reason', val: `"${d.rejection_reason}"`, cls: 'val-red' });
    if (d.flags)
      lines.push({ key: 'flags', val: `["${d.flags.join('","')}"]`, cls: 'val-orange' });
    for (const [k, v] of Object.entries(d.extracted_info ?? {}))
      lines.push({ key: k, val: `"${v}"`, cls: 'val', indent: true });
    for (const [k, v] of Object.entries(d.duplicate_match ?? {}))
      lines.push({ key: k, val: `"${v}"`, cls: 'val-orange', indent: true });
    lines.push({ key: 'processing_time_ms', val: String(d.processing_time_ms), cls: 'val' });
    return lines;
  }

  // ---- Contact form (mailto, no backend) ----
  readonly cFirst = signal('');
  readonly cLast = signal('');
  readonly cOrg = signal('');
  readonly cEmail = signal('');
  readonly cInterest = signal('Subscribing to a plan');
  readonly cMessage = signal('');
  readonly interests = ['Subscribing to a plan', 'Requesting a demo', 'API integration question', 'Enterprise pricing', 'Other'];

  sendContact(): void {
    const body = [
      `Name: ${this.cFirst()} ${this.cLast()}`,
      `Institution: ${this.cOrg()}`,
      `Email: ${this.cEmail()}`,
      `Interest: ${this.cInterest()}`,
      '',
      this.cMessage(),
    ].join('\n');
    const href =
      `mailto:zazap1731@gmail.com?subject=${encodeURIComponent('KYC-API enquiry — ' + this.cInterest())}` +
      `&body=${encodeURIComponent(body)}`;
    window.location.href = href;
  }

  // ---- Signup flow ----
  readonly currentPlan = computed(() => this.selected());

  choose(plan: Plan): void {
    this.selected.set(plan);
    this.error.set('');
    this.sentEmail.set('');
  }

  cancel(): void {
    this.selected.set(null);
    this.email.set('');
    this.error.set('');
  }

  submit(): void {
    const plan = this.selected();
    if (!plan || this.loading()) return;
    const email = this.email().trim();
    if (!isValidEmail(email)) {
      this.error.set('Enter a valid email address.');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.onboarding.start(email, plan.key).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.sentEmail.set(email);
        this.sentLink.set(res.signup_link);
        this.selected.set(null);
        this.email.set('');
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(this.messageFor(err));
      },
    });
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.error?.error?.message) return err.error.error.message;
    if (err.status === 0) return 'Cannot reach the server.';
    return 'Something went wrong. Please try again.';
  }
}
