import { Routes } from '@angular/router';

import { authGuard } from './core/auth.guard';

export const routes: Routes = [
  {
    path: '',
    pathMatch: 'full',
    loadComponent: () =>
      import('./features/landing/landing.component').then(
        (m) => m.LandingComponent,
      ),
  },
  {
    path: 'login',
    loadComponent: () =>
      import('./features/auth/login.component').then((m) => m.LoginComponent),
  },
  {
    path: 'signup',
    loadComponent: () =>
      import('./features/auth/signup.component').then(
        (m) => m.SignupComponent,
      ),
  },
  {
    path: 'forgot-pin',
    loadComponent: () =>
      import('./features/auth/forgot-pin.component').then(
        (m) => m.ForgotPinComponent,
      ),
  },
  {
    path: 'reset-pin',
    loadComponent: () =>
      import('./features/auth/reset-pin.component').then(
        (m) => m.ResetPinComponent,
      ),
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
  {
    path: 'admin',
    canActivate: [authGuard],
    loadComponent: () =>
      import('./features/admin/admin.component').then(
        (m) => m.AdminComponent,
      ),
  },
  { path: '**', redirectTo: '' },
];
