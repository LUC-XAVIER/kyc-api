import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { of, throwError } from 'rxjs';

import { LoginComponent } from './login.component';
import { AuthService } from '../../core/auth.service';

class FakeAuth {
  isAuthenticated = () => false;
  homeRoute = () => '/agent';
  login = jasmine.createSpy('login').and.returnValue(of({}));
}

describe('LoginComponent', () => {
  let component: LoginComponent;
  let auth: FakeAuth;

  beforeEach(async () => {
    auth = new FakeAuth();
    await TestBed.configureTestingModule({
      imports: [LoginComponent],
      providers: [
        provideRouter([]),
        { provide: AuthService, useValue: auth },
      ],
    }).compileComponents();
    component = TestBed.createComponent(LoginComponent).componentInstance;
  });

  it('defaults to manager and toggles to agent', () => {
    expect(component.actor()).toBe('manager');
    component.toggleActor();
    expect(component.actor()).toBe('agent');
  });

  it('requires an email and password before calling login', () => {
    component.submit();
    expect(component.error()).toContain('Enter your');
    expect(auth.login).not.toHaveBeenCalled();
  });

  it('submits the entered credentials', () => {
    component.email.set('m@mfi.cm');
    component.password.set('pw');
    component.submit();
    expect(auth.login).toHaveBeenCalledWith('m@mfi.cm', 'pw');
  });

  it('surfaces the API error message on failure', () => {
    auth.login.and.returnValue(
      throwError(() => ({
        error: { error: { message: 'Invalid email or password.' } },
      })),
    );
    component.email.set('m@mfi.cm');
    component.password.set('bad');
    component.submit();
    expect(component.error()).toContain('Invalid email');
    expect(component.loading()).toBeFalse();
  });
});
