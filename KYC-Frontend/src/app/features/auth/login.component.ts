import { Component, inject, signal } from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { HttpErrorResponse } from '@angular/common/http';

import { AuthService } from '../../core/auth.service';

type Actor = 'manager' | 'agent';

/**
 * Login for all actors. Managers see the form by default; agents switch via
 * the top-right link. Both submit to POST /auth/login; the returned role
 * decides which dashboard we land on.
 */
@Component({
  selector: 'app-login',
  imports: [RouterLink],
  templateUrl: './login.component.html',
  styleUrl: './login.component.scss',
})
export class LoginComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly route = inject(ActivatedRoute);

  readonly actor = signal<Actor>('manager');
  readonly identifier = signal('');
  readonly pin = signal('');
  readonly error = signal('');
  readonly loading = signal(false);
  readonly notice = signal('');

  constructor() {
    if (this.auth.isAuthenticated()) {
      this.router.navigateByUrl(this.auth.homeRoute());
    }
    const params = this.route.snapshot.queryParamMap;
    if (params.has('created')) {
      this.notice.set('Account created — please sign in.');
    } else if (params.has('reset')) {
      this.notice.set('Your PIN was updated — please sign in.');
    }
  }

  toggleActor(): void {
    this.actor.update((a) => (a === 'manager' ? 'agent' : 'manager'));
    this.identifier.set('');
    this.error.set('');
  }

  submit(): void {
    if (this.loading()) return;
    const identifier = this.identifier().trim();
    const pin = this.pin();
    if (!identifier || !pin) {
      const id = this.actor() === 'manager' ? 'email' : 'phone number';
      this.error.set(`Enter your ${id} and PIN.`);
      return;
    }
    this.loading.set(true);
    this.error.set('');
    this.auth.login(identifier, pin).subscribe({
      next: () => this.router.navigateByUrl(this.auth.homeRoute()),
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
    return 'Login failed. Please try again.';
  }
}
