import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { AuthService } from '../../core/auth.service';
import { isValidPin } from '../../core/validators';

/** Set a new PIN from an emailed reset link (?token=). */
@Component({
  selector: 'app-reset-pin',
  imports: [RouterLink],
  template: `
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-card__brand">
          <div class="logo">K</div><span>KYC-API</span>
        </div>
        @if (invalidLink()) {
          <h2>Link not valid</h2>
          <p class="sub">This reset link is invalid or has expired.</p>
          <a class="ox-btn ox-btn--primary block" routerLink="/forgot-pin">
            Request a new link
          </a>
        } @else {
          <h2>Set a new PIN</h2>
          <p class="sub">Choose a new 6-8 digit PIN for your account.</p>
          <form (submit)="$event.preventDefault(); submit()">
            <label class="lbl">New PIN</label>
            <input
              class="field"
              type="password"
              inputmode="numeric"
              [value]="pin()"
              (input)="pin.set($any($event.target).value)"
            />
            <label class="lbl">Confirm PIN</label>
            <input
              class="field"
              type="password"
              inputmode="numeric"
              [value]="confirm()"
              (input)="confirm.set($any($event.target).value)"
            />
            @if (error()) { <div class="err">{{ error() }}</div> }
            <button
              type="submit"
              class="ox-btn ox-btn--primary block"
              [disabled]="loading()"
            >
              {{ loading() ? 'Saving…' : 'Set new PIN' }}
            </button>
          </form>
        }
      </div>
    </div>
  `,
})
export class ResetPinComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly token = signal<string | null>(null);
  readonly invalidLink = signal(false);
  readonly pin = signal('');
  readonly confirm = signal('');
  readonly error = signal('');
  readonly loading = signal(false);

  constructor() {
    const token = this.route.snapshot.queryParamMap.get('token');
    if (!token) this.invalidLink.set(true);
    else this.token.set(token);
  }

  submit(): void {
    if (this.loading()) return;
    if (!isValidPin(this.pin())) {
      this.error.set('PIN must be 6 to 8 digits.');
      return;
    }
    if (this.pin() !== this.confirm()) {
      this.error.set('The PINs do not match.');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.auth.resetPin(this.token()!, this.pin()).subscribe({
      next: () =>
        this.router.navigate(['/login'], {
          queryParams: { reset: '1' },
        }),
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(
          err.error?.error?.message ??
            'Could not reset your PIN. The link may have expired.',
        );
      },
    });
  }
}
