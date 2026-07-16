import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { ManagerComponent } from './manager.component';
import { API_URL } from '../../core/config';
import { ReviewItem, VerificationSummary } from '../../core/models';

function review(over: Partial<ReviewItem>): ReviewItem {
  return {
    id: 'v1',
    client_id: 'CLT-1',
    client_name: 'Test Client',
    status: 'PENDING',
    reject_reason: null,
    confidence_score: 0.7,
    agent_name: 'Agent A',
    branch_name: 'Central',
    flagged_duplicate: false,
    created_at: new Date().toISOString(),
    ...over,
  };
}

function summary(over: Partial<VerificationSummary>): VerificationSummary {
  return {
    id: 'v1',
    client_id: 'CLT-1',
    client_name: 'Test Client',
    status: 'VERIFIED',
    reject_reason: null,
    confidence_score: 0.9,
    submission_method: 'DASHBOARD',
    agent_name: 'Agent A',
    branch_name: 'Central',
    created_at: new Date().toISOString(),
    ...over,
  };
}

describe('ManagerComponent', () => {
  let component: ManagerComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ManagerComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    }).compileComponents();
    component = TestBed.createComponent(ManagerComponent).componentInstance;
    http = TestBed.inject(HttpTestingController);
    // The constructor kicks off dashboard stats + account requests; drain them
    // so they don't interfere with the per-test expectations below.
    http
      .match(
        (r) =>
          r.url.endsWith('/kyc/verifications/stats') ||
          r.url.endsWith('/account'),
      )
      .forEach((r) => r.flush({}, { status: 200, statusText: 'OK' }));
  });

  it('starts on the dashboard', () => {
    expect(component.page()).toBe('dashboard');
  });

  it('filters the review queue by reason', () => {
    component.loadReviews();
    http.expectOne(`${API_URL}/kyc/reviews`).flush([
      review({ id: 'a', flagged_duplicate: true }),
      review({ id: 'b', flagged_duplicate: false }),
    ]);
    component.setReviewReason('Duplicate');
    expect(component.queueCases().every((c) => c.reason === 'Duplicate')).toBeTrue();
    expect(component.queueCases().length).toBe(1);
  });

  it('searches the review queue by client or name', () => {
    component.loadReviews();
    http.expectOne(`${API_URL}/kyc/reviews`).flush([
      review({ id: 'a', client_name: 'NGO Marie' }),
      review({ id: 'b', client_name: 'FOTSO Jean' }),
    ]);
    component.reviewSearch.set('ngo');
    const rows = component.queueCases();
    expect(rows.length).toBe(1);
    expect(rows[0].name).toContain('NGO');
  });

  it('removes the active case from the queue on approve', () => {
    component.loadReviews();
    http.expectOne(`${API_URL}/kyc/reviews`).flush([
      review({ id: 'a' }),
      review({ id: 'b' }),
    ]);
    const before = component.queueCount();
    component.resolveCase('approve');
    http
      .expectOne(`${API_URL}/kyc/reviews/a/decision`)
      .flush({ verification_id: 'a', status: 'APPROVED' });
    expect(component.queueCount()).toBe(before - 1);
  });

  it('filters history by status and resets to page 1', () => {
    component.loadHistory();
    http.expectOne(`${API_URL}/kyc/verifications`).flush([
      summary({ id: '1', status: 'VERIFIED' }),
      summary({ id: '2', status: 'REJECTED' }),
    ]);
    component.setHistoryStatus('Verified');
    expect(component.historyPage()).toBe(1);
    expect(
      component.historyFiltered().every((r) => r.status === 'Verified'),
    ).toBeTrue();
  });

  it('paginates the history view', () => {
    component.loadHistory();
    const rows = Array.from({ length: 8 }, (_, i) =>
      summary({ id: `v${i}`, client_id: `CLT-${i}` }),
    );
    http.expectOne(`${API_URL}/kyc/verifications`).flush(rows);
    expect(component.historyPageCount()).toBe(2);
    expect(component.historyPaged().length).toBe(6);
    component.goToPage(2);
    expect(component.historyPaged().length).toBe(2);
  });

  it('exports the history as CSV without error', () => {
    spyOn(URL, 'createObjectURL').and.returnValue('blob:x');
    spyOn(URL, 'revokeObjectURL');
    expect(() => component.exportHistoryCsv()).not.toThrow();
  });

  it('creates an agent through the modal', () => {
    component.loadAgents();
    http.expectOne(`${API_URL}/agents`).flush([]);
    http.expectOne(`${API_URL}/branches`).flush([{ id: 'b1', name: 'Central' }]);

    component.openAddAgent();
    component.setAgentField('name', 'Test User');
    component.setAgentField('phone', '+237699001122');
    component.setAgentField('pin', '123456');
    component.setAgentField('branchId', 'b1');
    component.saveAgent();

    const created = {
      id: 'a1',
      full_name: 'Test User',
      email: null,
      phone: '+237699001122',
      branch_id: 'b1',
      branch_name: 'Central',
      role: 'AGENT',
      status: 'ACTIVE',
    };
    http.expectOne(`${API_URL}/agents`).flush(created); // POST
    // Success reloads the list + branches.
    http.expectOne(`${API_URL}/agents`).flush([created]);
    http.expectOne(`${API_URL}/branches`).flush([{ id: 'b1', name: 'Central' }]);

    expect(component.agentModalOpen()).toBeFalse();
    expect(component.agentCount()).toBe(1);
  });

  it('rejects an agent with an invalid phone', () => {
    component.openAddAgent();
    component.setAgentField('name', 'Bad Phone');
    component.setAgentField('phone', '123');
    component.setAgentField('pin', '123456');
    component.setAgentField('branchId', 'b1');
    component.saveAgent();
    http.expectNone(`${API_URL}/agents`);
    expect(component.agentFormError()).toContain('phone');
  });

  it('generates an API key revealed once, then revokes it', () => {
    component.loadKeys();
    http.expectOne(`${API_URL}/api-keys`).flush([]);
    component.generateKey();
    http.expectOne(`${API_URL}/api-keys`).flush({
      id: 'k1',
      prefix: 'kyc_live_abc',
      full_key: 'kyc_live_abcSECRET',
      created_at: new Date().toISOString(),
    });
    expect(component.keys().length).toBe(1);
    expect(component.keys()[0].fullKey).toBe('kyc_live_abcSECRET');

    component.revokeKey('k1');
    http.expectOne(`${API_URL}/api-keys/k1`).flush({
      id: 'k1',
      prefix: 'kyc_live_abc',
      is_active: false,
      created_at: new Date().toISOString(),
      last_used_at: null,
    });
    expect(component.keys().some((k) => k.id === 'k1')).toBeFalse();
  });

  it('switches settings tabs and navigates to/from pricing', () => {
    component.setSettingsTab('Notifications');
    expect(component.settingsTab()).toBe('Notifications');
    component.goPricing();
    expect(component.page()).toBe('pricing');
    component.backToSettings();
    expect(component.page()).toBe('settings');
  });

  it('toggles a notification preference', () => {
    const before = component.notifs()['weekly'];
    component.toggleNotif('weekly');
    expect(component.notifs()['weekly']).toBe(!before);
  });
});
