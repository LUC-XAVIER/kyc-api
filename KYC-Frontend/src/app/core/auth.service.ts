import { computed, inject, Injectable, signal } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { Observable, tap } from 'rxjs';

import { API_URL } from './config';

/** The login response — the signed-in identity, stored for the session. */
export interface Principal {
  access_token: string;
  token_type: string;
  role: 'AGENT' | 'MANAGER' | 'ADMIN';
  agent_id: string;
  full_name: string;
  mfi_account_id: string | null;
  // Set when the account has 2FA on: the password step returns a challenge
  // instead of a usable session, to be exchanged via verifyMfa().
  mfa_required?: boolean;
  mfa_token?: string | null;
}

export interface TwoFactorSetup {
  secret: string;
  otpauth_uri: string;
  qr: string;
}

const STORAGE_KEY = 'kyc_principal';
const MANAGER_ROLES = ['MANAGER', 'ADMIN'];

/**
 * Holds the authenticated session (persisted to localStorage so a refresh
 * keeps the user signed in) and talks to POST /auth/login.
 */
@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  private readonly router = inject(Router);

  private readonly _principal = signal<Principal | null>(this.restore());

  readonly principal = this._principal.asReadonly();
  readonly isAuthenticated = computed(() => this._principal() !== null);
  readonly role = computed(() => this._principal()?.role ?? null);
  readonly isManager = computed(() =>
    MANAGER_ROLES.includes(this.role() ?? ''),
  );

  get token(): string | null {
    return this._principal()?.access_token ?? null;
  }

  login(identifier: string, pin: string): Observable<Principal> {
    return this.http
      .post<Principal>(`${API_URL}/auth/login`, { identifier, pin })
      .pipe(
        tap((res) => {
          // A 2FA challenge is not a session — hold it for the second step.
          if (!res.mfa_required) this.store(res);
        }),
      );
  }

  /** Second login step: exchange the challenge + TOTP code for a session. */
  verifyMfa(mfaToken: string, code: string): Observable<Principal> {
    return this.http
      .post<Principal>(`${API_URL}/auth/login/verify`, {
        mfa_token: mfaToken,
        code,
      })
      .pipe(tap((p) => this.store(p)));
  }

  private store(principal: Principal): void {
    this._principal.set(principal);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(principal));
  }

  // ---- Two-factor management (platform admin) ----
  twoFactorStatus(): Observable<{ enabled: boolean }> {
    return this.http.get<{ enabled: boolean }>(`${API_URL}/auth/2fa`);
  }

  twoFactorSetup(): Observable<TwoFactorSetup> {
    return this.http.post<TwoFactorSetup>(`${API_URL}/auth/2fa/setup`, {});
  }

  twoFactorEnable(code: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(
      `${API_URL}/auth/2fa/enable`,
      { code },
    );
  }

  twoFactorDisable(code: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(
      `${API_URL}/auth/2fa/disable`,
      { code },
    );
  }

  logout(): void {
    // Remember the role before clearing it, so each actor lands back on the
    // sign-in it came from (the generic page defaults to the manager form).
    const role = this._principal()?.role;
    this._principal.set(null);
    localStorage.removeItem(STORAGE_KEY);
    if (role === 'ADMIN') {
      this.router.navigateByUrl('/admin/login');
    } else if (role === 'AGENT') {
      this.router.navigate(['/login'], { queryParams: { actor: 'agent' } });
    } else {
      this.router.navigateByUrl('/login');
    }
  }

  forgotPin(
    email: string,
  ): Observable<{ status: string; reset_link: string | null }> {
    return this.http.post<{ status: string; reset_link: string | null }>(
      `${API_URL}/auth/forgot-pin`,
      { email },
    );
  }

  resetPin(token: string, pin: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(
      `${API_URL}/auth/reset-pin`,
      { token, pin },
    );
  }

  changePin(
    currentPin: string,
    newPin: string,
  ): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${API_URL}/auth/change-pin`, {
      current_pin: currentPin,
      new_pin: newPin,
    });
  }

  /** The dashboard route for the current role. */
  homeRoute(): string {
    if (this.role() === 'ADMIN') return '/admin';
    return this.isManager() ? '/manager' : '/agent';
  }

  private restore(): Principal | null {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      return raw ? (JSON.parse(raw) as Principal) : null;
    } catch {
      return null;
    }
  }
}
