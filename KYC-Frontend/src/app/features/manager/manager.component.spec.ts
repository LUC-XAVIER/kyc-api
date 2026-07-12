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
});
