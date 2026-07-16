import { isValidPin, normalizeCmPhone, phoneDigits } from './validators';

describe('phoneDigits', () => {
  it('keeps only digits', () => {
    expect(phoneDigits('6 99-00.11/22')).toBe('699001122');
  });

  it('caps at the 9-digit national number', () => {
    expect(phoneDigits('6990011229999')).toBe('699001122');
  });

  it('drops a pasted +237 country code', () => {
    expect(phoneDigits('+237 699 00 11 22')).toBe('699001122');
    expect(phoneDigits('237699001122')).toBe('699001122');
  });

  it('keeps a national number that itself starts with 237', () => {
    // 9 digits already — the leading 237 is part of the number, not a code.
    expect(phoneDigits('237001122')).toBe('237001122');
  });

  it('ignores letters', () => {
    expect(phoneDigits('abc699001122def')).toBe('699001122');
  });
});

describe('normalizeCmPhone', () => {
  it('accepts 9 bare digits', () => {
    expect(normalizeCmPhone('699001122')).toBe('+237699001122');
  });

  it('accepts an already-prefixed number', () => {
    expect(normalizeCmPhone('+237 699 00 11 22')).toBe('+237699001122');
  });

  it('rejects the wrong length', () => {
    expect(normalizeCmPhone('69900')).toBeNull();
    expect(normalizeCmPhone('6990011223')).toBeNull();
  });
});

describe('isValidPin', () => {
  it('accepts 6 to 8 digits', () => {
    expect(isValidPin('123456')).toBeTrue();
    expect(isValidPin('12345678')).toBeTrue();
  });

  it('rejects short, long, or non-numeric PINs', () => {
    expect(isValidPin('12345')).toBeFalse();
    expect(isValidPin('123456789')).toBeFalse();
    expect(isValidPin('12345a')).toBeFalse();
  });
});
