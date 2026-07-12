import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { AuthService } from './auth.service';

const PRINCIPAL = {
  access_token: 't',
  token_type: 'bearer',
  role: 'MANAGER',
  agent_id: 'a',
  full_name: 'Eric Ngono',
  mfi_account_id: 'x',
};

describe('AuthService', () => {
  let service: AuthService;
  let http: HttpTestingController;

  beforeEach(() => {
    localStorage.clear();
    TestBed.configureTestingModule({
      providers: [
        AuthService,
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    service = TestBed.inject(AuthService);
    http = TestBed.inject(HttpTestingController);
  });

  afterEach(() => http.verify());

  it('starts unauthenticated', () => {
    expect(service.isAuthenticated()).toBeFalse();
    expect(service.token).toBeNull();
  });

  it('stores the principal and token on login', () => {
    service.login('m@mfi.cm', '123456').subscribe();
    const req = http.expectOne((r) => r.url.endsWith('/auth/login'));
    expect(req.request.body).toEqual({
      identifier: 'm@mfi.cm',
      pin: '123456',
    });
    req.flush(PRINCIPAL);

    expect(service.isAuthenticated()).toBeTrue();
    expect(service.isManager()).toBeTrue();
    expect(service.token).toBe('t');
    expect(service.homeRoute()).toBe('/manager');
  });

  it('clears the session on logout', () => {
    service.login('m@mfi.cm', 'pw').subscribe();
    http.expectOne((r) => r.url.endsWith('/auth/login')).flush(PRINCIPAL);
    service.logout();
    expect(service.isAuthenticated()).toBeFalse();
  });
});
