import { Component, inject } from '@angular/core';
import {
  NavigationCancel,
  NavigationEnd,
  NavigationError,
  NavigationStart,
  Router,
  RouterOutlet,
} from '@angular/router';

import { LoadingService } from './core/loading.service';
import { LoadingOverlayComponent } from './shared/loading-overlay.component';

/** Root shell — routing only; the active role comes from the login session. */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet, LoadingOverlayComponent],
  template: '<app-loading-overlay /><router-outlet />',
})
export class AppComponent {
  private readonly loading = inject(LoadingService);

  constructor() {
    // Every route here is lazy-loaded, so a first visit to the dashboard
    // downloads a chunk and waits on the auth guard with nothing on screen.
    // Bracket the navigation so the branded splash covers that gap.
    inject(Router).events.subscribe((event) => {
      if (event instanceof NavigationStart) {
        this.loading.start();
      } else if (
        event instanceof NavigationEnd ||
        event instanceof NavigationCancel ||
        event instanceof NavigationError
      ) {
        this.loading.stop();
      }
    });
  }
}
