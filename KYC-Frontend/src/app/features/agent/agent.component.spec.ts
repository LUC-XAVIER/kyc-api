import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';

import { AgentComponent } from './agent.component';
import { API_URL } from '../../core/config';
import { VerificationSummary } from '../../core/models';

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

function cap() {
  return { url: 'blob:x', file: new File(['x'], 'x.jpg') };
}

describe('AgentComponent', () => {
  let component: AgentComponent;
  let http: HttpTestingController;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [AgentComponent],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    }).compileComponents();
    component = TestBed.createComponent(AgentComponent).componentInstance;
    http = TestBed.inject(HttpTestingController);
    // Drain the /auth/me request the constructor fires.
    http.match((r) => r.url.endsWith('/auth/me')).forEach((r) => r.flush({}));
  });

  it('starts on New Verification with nothing captured', () => {
    expect(component.page()).toBe('new');
    expect(component.allCaptured()).toBeFalse();
    expect(component.canVerify()).toBeFalse();
  });

  it('enables verify only once all NIC documents + client ID are set', () => {
    component.captured.set({ front: cap(), back: cap(), selfie: null });
    expect(component.allCaptured()).toBeFalse();
    component.captured.set({ front: cap(), back: cap(), selfie: cap() });
    expect(component.allCaptured()).toBeTrue();
    expect(component.canVerify()).toBeFalse(); // no client ID yet
    component.clientId.set('CLT-9');
    expect(component.canVerify()).toBeTrue();
  });

  it('does not require the ID back for a passport', () => {
    component.docType.set('PASSPORT');
    component.captured.set({ front: cap(), back: null, selfie: cap() });
    expect(component.allCaptured()).toBeTrue();
  });

  it('filters submissions by status', () => {
    http.expectOne(`${API_URL}/kyc/verifications`).flush([
      summary({ id: '1', status: 'VERIFIED' }),
      summary({ id: '2', status: 'PENDING' }),
      summary({ id: '3', status: 'REJECTED' }),
    ]);
    component.setFilter('Pending');
    expect(
      component.filtered().every((s) => s.status === 'Pending'),
    ).toBeTrue();
    expect(component.filtered().length).toBe(1);
  });

  it('searches submissions by id or name', () => {
    http.expectOne(`${API_URL}/kyc/verifications`).flush([
      summary({ id: '1', client_name: 'FOTSO Jean' }),
      summary({ id: '2', client_name: 'NGO Marie' }),
    ]);
    component.search.set('fotso');
    const rows = component.filtered();
    expect(rows.length).toBe(1);
    expect(rows[0].name).toContain('FOTSO');
  });
});
