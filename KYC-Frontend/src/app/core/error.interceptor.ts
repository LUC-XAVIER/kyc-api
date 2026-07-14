import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { AuthService } from './auth.service';

/**
 * On a 401 from the API, the session is stale/invalid — sign the user out
 * (which clears storage and routes to /login). Login and onboarding calls are
 * skipped so a wrong PIN shows an inline error instead of bouncing the page.
 */
export const errorInterceptor: HttpInterceptorFn = (req, next) => {
  const auth = inject(AuthService);
  return next(req).pipe(
    catchError((err: HttpErrorResponse) => {
      const isAuthFlow =
        req.url.includes('/auth/login') ||
        req.url.includes('/auth/forgot-pin') ||
        req.url.includes('/auth/reset-pin') ||
        req.url.includes('/onboarding/');
      if (err.status === 401 && !isAuthFlow && auth.isAuthenticated()) {
        auth.logout();
      }
      return throwError(() => err);
    }),
  );
};
