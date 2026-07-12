import { TestBed } from '@angular/core/testing';
import { provideHttpClient } from '@angular/common/http';
import { provideHttpClientTesting } from '@angular/common/http/testing';
import { provideRouter } from '@angular/router';
import { AgentComponent } from './agent.component';

describe('AgentComponent', () => {
  let component: AgentComponent;

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
  });

  it('starts on New Verification with nothing captured', () => {
    expect(component.page()).toBe('new');
    expect(component.allCaptured()).toBeFalse();
  });

  it('enables verify only once all three documents are captured', () => {
    component.toggleDoc('front');
    component.toggleDoc('back');
    expect(component.allCaptured()).toBeFalse();
    component.toggleDoc('selfie');
    expect(component.allCaptured()).toBeTrue();
  });

  it('filters submissions by status', () => {
    const total = component.filtered().length;
    component.setFilter('Pending');
    expect(component.filtered().every((s) => s.status === 'Pending')).toBeTrue();
    expect(component.filtered().length).toBeLessThan(total);
  });

  it('searches submissions by id or name', () => {
    component.search.set('fotso');
    const rows = component.filtered();
    expect(rows.length).toBe(1);
    expect(rows[0].name).toContain('FOTSO');
  });
});
