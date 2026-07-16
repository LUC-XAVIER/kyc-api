/** Client-side validation mirroring the backend (phone, PIN). */

/** The national-number length behind the +237 country code. */
export const CM_PHONE_DIGITS = 9;

/** Normalize a Cameroonian phone to +237 + 9 digits, or null if invalid. */
export function normalizeCmPhone(raw: string): string | null {
  let digits = raw.replace(/\D/g, '');
  if (digits.startsWith('237')) digits = digits.slice(3);
  return digits.length === CM_PHONE_DIGITS ? '+237' + digits : null;
}

/**
 * Keep only digits, capped at the national-number length — for phone fields
 * where +237 is shown as a separate, fixed prefix. A pasted country code is
 * dropped, but only when it can't be part of the national number itself
 * (i.e. there are more digits than a national number holds).
 */
export function phoneDigits(raw: string): string {
  let digits = raw.replace(/\D/g, '');
  if (digits.length > CM_PHONE_DIGITS && digits.startsWith('237')) {
    digits = digits.slice(3);
  }
  return digits.slice(0, CM_PHONE_DIGITS);
}

/** A 6-8 digit numeric PIN. */
export function isValidPin(pin: string): boolean {
  return /^\d{6,8}$/.test(pin);
}

/** Very light email shape check (server is authoritative). */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}
