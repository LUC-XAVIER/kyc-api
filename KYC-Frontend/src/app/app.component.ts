import { Component } from '@angular/core';
import { RouterOutlet } from '@angular/router';

/** Root shell — routing only; the active role comes from the login session. */
@Component({
  selector: 'app-root',
  imports: [RouterOutlet],
  template: '<router-outlet />',
})
export class AppComponent {}
