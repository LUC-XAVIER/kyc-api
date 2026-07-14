import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { InviteInfo, OnboardingService } from '../../core/onboarding.service';
import { isValidPin, normalizeCmPhone } from '../../core/validators';

/** Manager signup, reached from the emailed link (?token=). Email pre-filled. */
@Component({
  selector: 'app-signup',
  imports: [RouterLink],
  templateUrl: './signup.component.html',
  styleUrl: './signup.component.scss',
})
export class SignupComponent {
  private readonly route = inject(ActivatedRoute);
  private readonly onboarding = inject(OnboardingService);
  private readonly router = inject(Router);

  readonly token = signal<string | null>(null);
  readonly invite = signal<InviteInfo | null>(null);
  readonly invalidLink = signal(false);

  readonly fullName = signal('');
  readonly mfiName = signal('');
  readonly phone = signal('');
  readonly pin = signal('');
  readonly confirm = signal('');
  readonly error = signal('');
  readonly loading = signal(false);

  constructor() {
    const token = this.route.snapshot.queryParamMap.get('token');
    if (!token) {
      this.invalidLink.set(true);
      return;
    }
    this.token.set(token);
    this.onboarding.invite(token).subscribe({
      next: (info) => this.invite.set(info),
      error: () => this.invalidLink.set(true),
    });
  }

  submit(): void {
    if (this.loading()) return;
    if (!this.fullName().trim() || !this.mfiName().trim()) {
      this.error.set('Enter your name and institution name.');
      return;
    }
    if (!isValidPin(this.pin())) {
      this.error.set('PIN must be 6 to 8 digits.');
      return;
    }
    if (this.pin() !== this.confirm()) {
      this.error.set('The PINs do not match.');
      return;
    }
    const phone = this.phone().trim();
    if (phone && !normalizeCmPhone(phone)) {
      this.error.set('Enter a valid phone (+237 and 9 digits).');
      return;
    }

    this.loading.set(true);
    this.error.set('');
    this.onboarding
      .complete({
        token: this.token()!,
        full_name: this.fullName().trim(),
        mfi_name: this.mfiName().trim(),
        pin: this.pin(),
        phone: phone || null,
      })
      .subscribe({
        next: () =>
          this.router.navigate(['/login'], {
            queryParams: { created: '1' },
          }),
        error: (err: HttpErrorResponse) => {
          this.loading.set(false);
          this.error.set(
            err.error?.error?.message ??
              (err.status === 0
                ? 'Cannot reach the server.'
                : 'Signup failed. Please try again.'),
          );
        },
      });
  }
}
