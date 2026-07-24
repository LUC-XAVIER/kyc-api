import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { AdminLoginComponent } from './admin-login.component';
import { AuthService } from '../../core/auth.service';

class FakeAuth {
  private _role: string | null = null;
  role = () => this._role;
  homeRoute = () => '/manager';
  login = jasmine.createSpy('login').and.callFake(() => {
    this._role = 'ADMIN';
    return of({});
  });
  setRole(r: string | null) {
    this._role = r;
  }
}

describe('AdminLoginComponent', () => {
  let component: AdminLoginComponent;
  let auth: FakeAuth;

  beforeEach(async () => {
    auth = new FakeAuth();
    await TestBed.configureTestingModule({
      imports: [AdminLoginComponent],
      providers: [provideRouter([]), { provide: AuthService, useValue: auth }],
    }).compileComponents();
    component = TestBed.createComponent(AdminLoginComponent).componentInstance;
  });

  it('requires an email and PIN before calling login', () => {
    component.submit();
    expect(component.error()).toContain('Enter your');
    expect(auth.login).not.toHaveBeenCalled();
  });

  it('submits the entered email and PIN', () => {
    component.email.set('admin@example.com');
    component.pin.set('123456');
    component.submit();
    expect(auth.login).toHaveBeenCalledWith('admin@example.com', '123456');
  });

  it('surfaces the API error message on failure', () => {
    auth.login.and.returnValue(
      throwError(() => ({ error: { error: { message: 'Invalid credentials.' } } })),
    );
    component.email.set('admin@example.com');
    component.pin.set('000000');
    component.submit();
    expect(component.error()).toContain('Invalid credentials');
    expect(component.loading()).toBeFalse();
  });
});
