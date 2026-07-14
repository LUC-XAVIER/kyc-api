import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { AuthService } from '../../core/auth.service';
import { OnboardingService } from '../../core/onboarding.service';
import { Plan, PLANS } from '../../core/plans';
import { isValidEmail } from '../../core/validators';

/** Public landing: presents the plans; choosing one starts signup by email. */
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

  readonly plans = PLANS;
  readonly selected = signal<Plan | null>(null);
  readonly email = signal('');
  readonly error = signal('');
  readonly loading = signal(false);
  readonly sentEmail = signal('');
  readonly sentLink = signal<string | null>(null);

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.router.navigateByUrl(this.auth.homeRoute());
    }
  }

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
