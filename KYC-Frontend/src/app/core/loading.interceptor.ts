/** Drives the loading overlay from in-flight HTTP requests.
 *
 * The dashboard's "pages" are not routes — the sidebar flips a signal and
 * the component refetches — so a router hook alone never fires for them.
 * What every page switch *does* have in common is a request, which is what
 * this watches.
 *
 * Opt out with ``SKIP_LOADING`` for a call that owns its own progress UI
 * (the verification upload) or that runs in the background.
 */

import {
  HttpContext,
  HttpContextToken,
  HttpInterceptorFn,
} from '@angular/common/http';
import { inject } from '@angular/core';
import { finalize } from 'rxjs';

import { LoadingService } from './loading.service';

const SKIP_LOADING_TOKEN = new HttpContextToken<boolean>(() => false);

/** Context marking a request that must not raise the overlay. */
export function skipLoading(): HttpContext {
  return new HttpContext().set(SKIP_LOADING_TOKEN, true);
}

export const loadingInterceptor: HttpInterceptorFn = (req, next) => {
  if (req.context.get(SKIP_LOADING_TOKEN)) return next(req);

  const loading = inject(LoadingService);
  loading.start();
  // finalize, not tap: the overlay must lift on error and on cancellation
  // too, otherwise a failed request leaves the app covered forever.
  return next(req).pipe(finalize(() => loading.stop()));
};
