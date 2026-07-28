import { inject, Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

import { API_URL } from './config';
import { Principal } from './auth.service';

export interface StartResponse {
  status: string;
  signup_link: string | null;
}

/** Completing signup returns a session (auto-login) so the wizard can pay. */
export interface CompleteResponse extends Principal {
  email: string;
}

export interface InviteInfo {
  email: string;
  plan: string;
}

export interface CompletePayload {
  token: string;
  full_name: string;
  mfi_name: string;
  pin: string;
  phone?: string | null;
}

/** Calls the public onboarding endpoints (no auth). */
@Injectable({ providedIn: 'root' })
export class OnboardingService {
  private readonly http = inject(HttpClient);

  start(email: string, plan: string): Observable<StartResponse> {
    return this.http.post<StartResponse>(`${API_URL}/onboarding/start`, {
      email,
      plan,
    });
  }

  invite(token: string): Observable<InviteInfo> {
    return this.http.get<InviteInfo>(
      `${API_URL}/onboarding/invite/${encodeURIComponent(token)}`,
    );
  }

  complete(payload: CompletePayload): Observable<CompleteResponse> {
    return this.http.post<CompleteResponse>(
      `${API_URL}/onboarding/complete`,
      payload,
    );
  }
}
