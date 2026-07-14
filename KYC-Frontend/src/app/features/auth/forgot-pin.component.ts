import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { isValidEmail } from '../../core/validators';

/** Manager forgot-PIN: request an emailed reset link. */
@Component({
  selector: 'app-forgot-pin',
  imports: [RouterLink],
  template: `
    <div class="auth-page">
      <div class="auth-card">
        <div class="auth-card__brand">
          <div class="logo">K</div><span>KYC-API</span>
        </div>
        <h2>Forgot your PIN?</h2>
        @if (sent()) {
          <p class="sub">
            If <b>{{ lastEmail() }}</b> is a manager account, we've sent a
            reset link. Check your email.
          </p>
          @if (sentLink()) {
            <a class="ox-btn ox-btn--primary block" [href]="sentLink()">
              Dev link — reset your PIN →
            </a>
          }
          <div class="link-row"><a routerLink="/login">Back to sign in</a></div>
        } @else {
          <p class="sub">
            Enter your manager email and we'll send you a link to set a new
            PIN. (Agents: ask your manager to reset your PIN.)
          </p>
          <form (submit)="$event.preventDefault(); submit()">
            <label class="lbl">Email</label>
            <input
              class="field"
              type="email"
              placeholder="you@mfi.cm"
              [value]="email()"
              (input)="email.set($any($event.target).value)"
            />
            @if (error()) { <div class="err">{{ error() }}</div> }
            <button
              type="submit"
              class="ox-btn ox-btn--primary block"
              [disabled]="loading()"
            >
              {{ loading() ? 'Sending…' : 'Send reset link' }}
            </button>
          </form>
          <div class="link-row"><a routerLink="/login">Back to sign in</a></div>
        }
      </div>
    </div>
  `,
})
export class ForgotPinComponent {
  private readonly auth = inject(AuthService);

  readonly email = signal('');
  readonly lastEmail = signal('');
  readonly error = signal('');
  readonly loading = signal(false);
  readonly sent = signal(false);
  readonly sentLink = signal<string | null>(null);

  submit(): void {
    if (this.loading()) return;
    const email = this.email().trim();
    if (!isValidEmail(email)) {
      this.error.set('Enter a valid email address.');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.auth.forgotPin(email).subscribe({
      next: (res) => {
        this.loading.set(false);
        this.lastEmail.set(email);
        this.sentLink.set(res.reset_link);
        this.sent.set(true);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Something went wrong. Please try again.');
      },
    });
  }
}
