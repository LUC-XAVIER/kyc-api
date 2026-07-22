import {
  ChangeDetectionStrategy,
  Component,
  computed,
  input,
  signal,
} from '@angular/core';

import { VerificationDetail } from '../core/models';

function pct(score: number | null | undefined): string {
  return score == null ? '—' : `${Math.round(score * 100)}%`;
}

/**
 * Read-only score breakdown for one verification, in pipeline order
 * (OCR → liveness → face match → duplicate) with the overall score and an
 * optional reveal of the OCR-extracted client fields. Shared by the manager
 * review pane, the manager History popup, and the agent submission detail so
 * the three stay identical.
 */
@Component({
  selector: 'app-verification-scores',
  changeDetection: ChangeDetectionStrategy.OnPush,
  templateUrl: './verification-scores.component.html',
  styleUrl: './verification-scores.component.scss',
})
export class VerificationScoresComponent {
  readonly detail = input<VerificationDetail | null>(null);
  readonly ocrOpen = signal(false);

  readonly overall = computed(() => pct(this.detail()?.confidence_score));

  readonly faceMatch = computed(() => {
    const fm = this.detail()?.face_match_result;
    if (!fm) return '—';
    return `${fm.match_score.toFixed(2)} — ${fm.verified ? 'match' : 'weak'}`;
  });

  readonly liveness = computed(() => {
    const lv = this.detail()?.liveness_result;
    return lv ? (lv.passed ? 'Passed' : 'Failed') : '—';
  });

  readonly ocr = computed(() => {
    const conf = this.detail()?.extracted_data?.field_confidences;
    if (!conf) return '—';
    const vals = Object.values(conf).filter((v) => typeof v === 'number');
    if (!vals.length) return '—';
    return (vals.reduce((a, b) => a + b, 0) / vals.length).toFixed(2);
  });

  readonly dup = computed(() => {
    const detail = this.detail();
    const flags = detail?.duplicate_flags ?? [];
    if (!flags.length) {
      // The duplicate check runs after face matching on a clean pass. A
      // face-match record means it ran and found nothing — not "—" (never ran).
      const checked = detail?.face_match_result != null;
      return { sim: checked ? 'No match' : '—', warning: '' };
    }
    const top = flags.reduce((a, b) =>
      b.similarity_score > a.similarity_score ? b : a,
    );
    const level = top.similarity_score >= 0.7 ? 'high' : 'low';
    const warning = top.matched_client_id
      ? `Matches existing client ${top.matched_client_id}. Review before approving.`
      : '';
    return { sim: `${top.similarity_score.toFixed(2)} — ${level}`, warning };
  });

  readonly ocrFields = computed(() => {
    const e = this.detail()?.extracted_data;
    if (!e) return [] as { label: string; value: string }[];
    const rows: { label: string; value: string }[] = [];
    const add = (label: string, value: string | null) => {
      if (value) rows.push({ label, value });
    };
    add('Full name', e.full_name);
    add('ID number', e.id_number);
    add('Date of birth', e.date_of_birth);
    add('Place of birth', e.place_of_birth);
    add('Sex', e.sex);
    add('Occupation', e.occupation);
    add('Expiry date', e.expiry_date);
    return rows;
  });

  /** LIVENESS_FAILED → "Liveness failed". */
  rejectLabel(reason: string): string {
    const text = reason.replace(/_/g, ' ').toLowerCase();
    return text.charAt(0).toUpperCase() + text.slice(1);
  }
}
