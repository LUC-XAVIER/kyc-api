/** The dashboards switch "pages" by flipping a signal, not by routing, so
 * a router-driven overlay never fires for them. These tests click the real
 * sidebar buttons and assert the overlay actually comes up — including on
 * the pages that fetch nothing of their own.
 */

import { provideHttpClient } from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { Type } from '@angular/core';
import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';

import { LoadingService } from '../core/loading.service';
import { AgentComponent } from './agent/agent.component';
import { ManagerComponent } from './manager/manager.component';

/** Click the sidebar button whose label matches, and settle the view. */
function clickNav(fixture: ComponentFixture<unknown>, label: string): void {
  const buttons = Array.from(
    fixture.nativeElement.querySelectorAll('button.nav-item'),
  ) as HTMLButtonElement[];
  const target = buttons.find((b) => b.textContent?.trim() === label);
  if (!target) throw new Error(`No nav item labelled "${label}"`);
  target.click();
  fixture.detectChanges();
}

describe('dashboard page transitions', () => {
  let http: HttpTestingController;
  let loading: LoadingService;

  /** Answer every in-flight request; list endpoints need an array body. */
  function drain(): void {
    http.match(() => true).forEach((req) => {
      const isList = /verifications(\?|$)|\/reviews|\/agents|\/keys/.test(
        req.request.url,
      );
      req.flush(isList ? [] : {});
    });
  }

  function setup<T>(component: Type<T>) {
    TestBed.configureTestingModule({
      imports: [component],
      providers: [
        provideHttpClient(),
        provideHttpClientTesting(),
        provideRouter([]),
      ],
    });
    http = TestBed.inject(HttpTestingController);
    loading = TestBed.inject(LoadingService);
    const fixture = TestBed.createComponent(component);
    fixture.detectChanges();
    // Drain whatever the constructor kicked off, then start from a clean slate.
    drain();
    loading.reset();
    return fixture;
  }

  afterEach(() => TestBed.resetTestingModule());

  it('raises the overlay for a manager page that fetches data', () => {
    const fixture = setup(ManagerComponent);
    clickNav(fixture, 'History');
    expect(loading.visible()).toBeTrue();
  });

  it('raises it for the manager Dashboard, which fetches nothing', () => {
    const fixture = setup(ManagerComponent);
    clickNav(fixture, 'Review queue');
    drain();
    loading.reset();

    clickNav(fixture, 'Dashboard');
    expect(loading.visible()).toBeTrue();
  });

  it('raises it for an agent page that fetches nothing', () => {
    const fixture = setup(AgentComponent);
    clickNav(fixture, 'Profile');
    expect(loading.visible()).toBeTrue();
  });
});
