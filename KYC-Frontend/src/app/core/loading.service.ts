/** Tracks whether the branded loading overlay should be on screen.
 *
 * Reference-counted: several requests can overlap (a page switch often
 * fires more than one), and the overlay lifts only when the last one
 * finishes. Once shown it stays for at least ``MIN_VISIBLE_MS`` so a fast
 * response — every response, against a local API — still reads as a
 * deliberate transition rather than a flicker.
 */

import { Injectable, signal } from '@angular/core';

const MIN_VISIBLE_MS = 450;

@Injectable({ providedIn: 'root' })
export class LoadingService {
  /** True while the overlay should be rendered. */
  readonly visible = signal(false);

  private hideTimer: ReturnType<typeof setTimeout> | null = null;
  private shownAt = 0;
  private depth = 0;

  /** Mark one loading operation as started. */
  start(): void {
    this.depth += 1;
    // A new operation during the minimum-visible tail must cancel the
    // pending hide, or the overlay drops while work is still running.
    this.cancelHide();
    if (this.visible()) return;
    this.shownAt = Date.now();
    this.visible.set(true);
  }

  /** Mark one loading operation as finished. */
  stop(): void {
    this.depth = Math.max(0, this.depth - 1);
    if (this.depth > 0 || !this.visible()) return;

    const remaining = MIN_VISIBLE_MS - (Date.now() - this.shownAt);
    if (remaining <= 0) {
      this.visible.set(false);
      return;
    }
    this.hideTimer = setTimeout(() => {
      this.hideTimer = null;
      this.visible.set(false);
    }, remaining);
  }

  /** Drop the overlay immediately, whatever is pending (used on logout). */
  reset(): void {
    this.cancelHide();
    this.depth = 0;
    this.visible.set(false);
  }

  private cancelHide(): void {
    if (this.hideTimer === null) return;
    clearTimeout(this.hideTimer);
    this.hideTimer = null;
  }
}
