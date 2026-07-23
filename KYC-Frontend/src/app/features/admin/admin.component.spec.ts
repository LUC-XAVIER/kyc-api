import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { AdminComponent } from './admin.component';
import { API_URL } from '../../core/config';
import {
  AdminMfiDetail,
  AdminMfiSummary,
  PlatformStats,
} from '../../core/models';

function mfi(over: Partial<AdminMfiSummary>): AdminMfiSummary {
  return {
    id: 'm1',
    name: 'MFI One',
    email: 'one@x.cm',
    plan: 'GROWTH',
    status: 'ACTIVE',
    usage: 100,
    quota: 1000,
    verifications: 100,
    users: 4,
    api_keys: 1,
    branches: 2,
    created_at: new Date().toISOString(),
    ...over,
  };
}

const STATS: PlatformStats = {
  total_mfis: 2,
  active_mfis: 1,
  suspended_mfis: 1,
  pending_mfis: 0,
  total_verifications: 300,
  total_users: 8,
  warning_count: 1,
  by_plan: [
    { plan: 'STARTER', count: 1 },
    { plan: 'GROWTH', count: 1 },
  ],
  per_day: Array.from({ length: 14 }, (_, i) => ({
    date: `2026-07-${String(i + 1).padStart(2, '0')}`,
    count: i,
  })),
  quota_rows: [
    { id: 'm1', name: 'MFI One', plan: 'GROWTH', usage: 900, quota: 1000, pct: 90 },
  ],
};

function detail(over: Partial<AdminMfiDetail> = {}): AdminMfiDetail {
  return {
    id: 'm1',
    name: 'MFI One',
    email: 'one@x.cm',
    status: 'ACTIVE',
    plan: 'GROWTH',
    quota: 1000,
    usage: 100,
    max_branches: 5,
    max_agents: 15,
    api_access: true,
    this_month: 40,
    last_month: 60,
    avg_per_day: 2,
    billing_cycle_start: '2026-07-01',
    created_at: new Date().toISOString(),
    api_keys: [],
    agents: [],
    performance: {
      verified: 80,
      pending: 10,
      rejected: 10,
      duplicates: 3,
      avg_processing_seconds: 4.2,
    },
    ...over,
  };
}

describe('AdminComponent', () => {
  let component: AdminComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AdminComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    }).compileComponents();
    component = TestBed.createComponent(AdminComponent).componentInstance;
    http = TestBed.inject(HttpTestingController);
    // The constructor loads platform stats + the MFI list; drain both.
    http.match((r) => r.url.endsWith('/admin/stats')).forEach((r) => r.flush(STATS));
    http
      .match((r) => r.url.endsWith('/admin/mfis'))
      .forEach((r) => r.flush([mfi({}), mfi({ id: 'm2', status: 'SUSPENDED', name: 'MFI Two' })]));
  });

  it('starts on the overview with stats loaded', () => {
    expect(component.page()).toBe('overview');
    expect(component.overviewCards().length).toBe(4);
    expect(component.dayBars().length).toBe(14);
  });

  it('builds a plan donut from the plan mix', () => {
    expect(component.donut().length).toBe(2);
    expect(component.donutStyle()).toContain('conic-gradient');
  });

  it('filters the MFI table by status', () => {
    component.setFilter('SUSPENDED');
    const rows = component.rows();
    expect(rows.length).toBe(1);
    expect(rows[0].name).toBe('MFI Two');
  });

  it('searches the MFI table by name', () => {
    component.search.set('two');
    expect(component.rows().length).toBe(1);
    expect(component.rows()[0].name).toBe('MFI Two');
  });

  it('opens an MFI detail and switches page', () => {
    component.openMfi('m1');
    http.expectOne(`${API_URL}/admin/mfis/m1`).flush(detail());
    expect(component.page()).toBe('mfi-detail');
    expect(component.detail()?.name).toBe('MFI One');
    expect(component.detailPerf().length).toBe(5);
  });

  it('suspends an MFI and updates the row + toast', () => {
    component.setStatus('m1', 'SUSPENDED');
    http
      .expectOne(`${API_URL}/admin/mfis/m1/status`)
      .flush(detail({ status: 'SUSPENDED' }));
    // Constructor-style stats reload after a status change.
    http.match((r) => r.url.endsWith('/admin/stats')).forEach((r) => r.flush(STATS));
    expect(component.mfis().find((m) => m.id === 'm1')?.status).toBe('SUSPENDED');
    expect(component.toast()).toContain('suspended');
  });

  it('shows a placeholder for deferred sections', () => {
    component.setPage('system-health');
    expect(component.isDeferred()).toBeTrue();
  });

  it('loads and categorises the audit log', () => {
    component.setPage('audit-logs');
    http.expectOne((r) => r.url.endsWith('/admin/audit')).flush([
      {
        id: 'a1',
        action: 'mfi.suspended',
        actor_type: 'ADMIN',
        actor_id: 'x',
        mfi_name: 'MFI One',
        verification_id: null,
        details: null,
        timestamp: new Date().toISOString(),
      },
      {
        id: 'a2',
        action: 'review.approved',
        actor_type: 'MANAGER',
        actor_id: 'y',
        mfi_name: 'MFI Two',
        verification_id: 'v1',
        details: { reason: 'ok' },
        timestamp: new Date().toISOString(),
      },
    ]);
    expect(component.isDeferred()).toBeFalse();
    expect(component.auditRows().length).toBe(2);
    component.setAuditCategory('Admin action');
    expect(component.auditRows().length).toBe(1);
    expect(component.auditRows()[0].title).toContain('MFI One');
  });
});
