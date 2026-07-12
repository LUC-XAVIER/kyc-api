import { Routes } from '@angular/router';

export const routes: Routes = [
  { path: '', redirectTo: 'agent', pathMatch: 'full' },
  {
    path: 'agent',
    loadComponent: () =>
      import('./features/agent/agent.component').then(
        (m) => m.AgentComponent,
      ),
  },
  {
    path: 'manager',
    loadComponent: () =>
      import('./features/manager/manager.component').then(
        (m) => m.ManagerComponent,
      ),
  },
  { path: '**', redirectTo: 'agent' },
];
