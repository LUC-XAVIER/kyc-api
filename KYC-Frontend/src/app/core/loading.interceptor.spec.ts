import {
  HttpClient,
  provideHttpClient,
  withInterceptors,
} from '@angular/common/http';
import {
  HttpTestingController,
  provideHttpClientTesting,
} from '@angular/common/http/testing';
import { TestBed, fakeAsync, tick } from '@angular/core/testing';

import { loadingInterceptor, skipLoading } from './loading.interceptor';
import { LoadingService } from './loading.service';

describe('loading overlay', () => {
  let http: HttpClient;
  let mock: HttpTestingController;
  let loading: LoadingService;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideHttpClient(withInterceptors([loadingInterceptor])),
        provideHttpClientTesting(),
      ],
    });
    http = TestBed.inject(HttpClient);
    mock = TestBed.inject(HttpTestingController);
    loading = TestBed.inject(LoadingService);
  });

  afterEach(() => mock.verify());

  it('shows immediately, so a fast local response is still seen', () => {
    http.get('/api/v1/kyc/verifications').subscribe();
    expect(loading.visible()).toBe(true);
    mock.expectOne('/api/v1/kyc/verifications').flush([]);
  });

  it('stays up for the minimum, then lifts', fakeAsync(() => {
    http.get('/x').subscribe();
    mock.expectOne('/x').flush({});

    tick(400);
    expect(loading.visible()).toBe(true); // still inside the minimum
    tick(100);
    expect(loading.visible()).toBe(false);
  }));

  it('waits for the last of several overlapping requests', fakeAsync(() => {
    http.get('/a').subscribe();
    http.get('/b').subscribe();
    mock.expectOne('/a').flush({});

    tick(500);
    expect(loading.visible()).toBe(true); // /b is still in flight

    mock.expectOne('/b').flush({});
    tick(500);
    expect(loading.visible()).toBe(false);
  }));

  it('lifts on error rather than covering the app forever', fakeAsync(() => {
    http.get('/boom').subscribe({ error: () => undefined });
    mock.expectOne('/boom').flush(null, { status: 500, statusText: 'X' });

    tick(500);
    expect(loading.visible()).toBe(false);
  }));

  it('does not raise the overlay for a skipLoading request', () => {
    http.post('/api/v1/kyc/verify', null, { context: skipLoading() })
      .subscribe();
    expect(loading.visible()).toBe(false);
    mock.expectOne('/api/v1/kyc/verify').flush({});
  });

  it('cancels a pending hide when new work starts', fakeAsync(() => {
    http.get('/first').subscribe();
    mock.expectOne('/first').flush({});

    tick(300); // hide is scheduled but not yet fired
    http.get('/second').subscribe();
    tick(300); // the original hide would have fired by now
    expect(loading.visible()).toBe(true);

    mock.expectOne('/second').flush({});
    tick(500);
    expect(loading.visible()).toBe(false);
  }));
});
