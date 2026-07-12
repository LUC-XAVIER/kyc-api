import { TestBed } from '@angular/core/testing';
import { ManagerComponent } from './manager.component';

describe('ManagerComponent', () => {
  let component: ManagerComponent;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      imports: [ManagerComponent],
    }).compileComponents();
    component = TestBed.createComponent(ManagerComponent).componentInstance;
  });

  it('starts on the dashboard', () => {
    expect(component.page()).toBe('dashboard');
  });

  it('filters the review queue by reason', () => {
    component.setReviewReason('Duplicate');
    expect(
      component.queueCases().every((c) => c.reason === 'Duplicate'),
    ).toBeTrue();
  });

  it('searches the review queue by client or name', () => {
    component.reviewSearch.set('ngo');
    const rows = component.queueCases();
    expect(rows.length).toBe(1);
    expect(rows[0].name).toContain('NGO');
  });

  it('removes the active case from the queue on resolve', () => {
    const before = component.queueCount();
    component.resolveCase();
    expect(component.queueCount()).toBe(before - 1);
  });

  it('filters history by status and resets to page 1', () => {
    component.goToPage(2);
    component.setHistoryStatus('Verified');
    expect(component.historyPage()).toBe(1);
    expect(
      component.historyFiltered().every((r) => r.status === 'Verified'),
    ).toBeTrue();
  });

  it('paginates the history view', () => {
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
