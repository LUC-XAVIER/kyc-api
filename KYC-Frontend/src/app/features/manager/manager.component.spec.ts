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
    // The constructor kicks off a dashboard stats request; drain it so it
    // doesn't interfere with the per-test expectations below.
    const stats = http.match((r) => r.url.endsWith('/kyc/verifications/stats'));
    stats.forEach((r) => r.flush({}, { status: 200, statusText: 'OK' }));
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

  it('adds an agent through the modal', () => {
    const before = component.agentCount();
    component.openAddAgent();
    component.setAgentField('name', 'Test User');
    component.setAgentField('email', 't@x.cm');
    component.saveAgent();
    expect(component.agentCount()).toBe(before + 1);
    expect(component.agentModalOpen()).toBeFalse();
  });

  it('generates an API key revealed once, then revokes it', () => {
    const before = component.keys().length;
    component.generateKey();
    expect(component.keys().length).toBe(before + 1);
    const created = component.keys()[0];
    expect(created.fullKey).toBeTruthy();
    component.revokeKey(created.id);
    expect(component.keys().some((k) => k.id === created.id)).toBeFalse();
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
