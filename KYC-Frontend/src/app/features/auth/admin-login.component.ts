import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { AuthService } from '../../core/auth.service';

/**
 * Dedicated platform-admin sign-in (`/admin/login`) — a dark, admin-branded
 * entrance the admin can bookmark, distinct from the MFI-facing `/login`.
 * It posts to the same `/auth/login`; on success the admin lands on `/admin`
 * and any non-admin is sent to their own dashboard instead.
 *
 * Note: this is a convenience entrance, not a security boundary — a separate
 * URL is not a secret. Real hardening (a strong password, TOTP 2FA) belongs
 * on the account itself.
 */
@Component({
  selector: 'app-admin-login',
  imports: [],
  templateUrl: './admin-login.component.html',
  styleUrl: './admin-login.component.scss',
})
export class AdminLoginComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);

  readonly email = signal('');
  readonly pin = signal('');
  readonly error = signal('');
  readonly loading = signal(false);

  constructor() {
    if (this.auth.role() === 'ADMIN') {
      this.router.navigateByUrl('/admin');
    }
  }

  submit(): void {
    if (this.loading()) return;
    const email = this.email().trim();
    const pin = this.pin();
    if (!email || !pin) {
      this.error.set('Enter your email and PIN.');
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.auth.login(email, pin).subscribe({
      next: () => {
        if (this.auth.role() !== 'ADMIN') {
          // A non-admin used the admin door; send them where they belong.
          this.router.navigateByUrl(this.auth.homeRoute());
          return;
        }
        this.router.navigateByUrl('/admin');
      },
      error: (err: HttpErrorResponse) => {
        this.loading.set(false);
        this.error.set(this.messageFor(err));
      },
    });
  }

  private messageFor(err: HttpErrorResponse): string {
    if (err.error?.error?.message) return err.error.error.message;
    if (err.status === 0) {
      return 'Cannot reach the server. Is the API running?';
    }
    return 'Sign-in failed. Please try again.';
  }
}
