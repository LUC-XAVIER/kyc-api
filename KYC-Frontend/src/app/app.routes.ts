import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  { path: '', pathMatch: 'full', redirectTo: 'login' },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'agent',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/agent/agent.component').then(
        (m) => m.AgentComponent,
      ),
  },
  {
    path: 'manager',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/manager/manager.component').then(
        (m) => m.ManagerComponent,
      ),
  },
  { path: '**', redirectTo: 'login' },
];
