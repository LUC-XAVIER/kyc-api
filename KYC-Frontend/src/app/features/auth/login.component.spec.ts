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

  it('requires an identifier and PIN before calling login', () => {
    component.submit();
    expect(component.error()).toContain('Enter your');
    expect(auth.login).not.toHaveBeenCalled();
  });

  it('submits the entered identifier and PIN', () => {
    component.identifier.set('m@mfi.cm');
    component.pin.set('123456');
    component.submit();
    expect(auth.login).toHaveBeenCalledWith('m@mfi.cm', '123456');
  });

  it('surfaces the API error message on failure', () => {
    auth.login.and.returnValue(
      throwError(() => ({
        error: { error: { message: 'Invalid credentials.' } },
      })),
    );
    component.identifier.set('m@mfi.cm');
    component.pin.set('000000');
    component.submit();
    expect(component.error()).toContain('Invalid credentials');
    expect(component.loading()).toBeFalse();
  });
});
