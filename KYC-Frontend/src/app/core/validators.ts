/** Client-side validation mirroring the backend (phone, PIN). */

/** Normalize a Cameroonian phone to +237 + 9 digits, or null if invalid. */
export function normalizeCmPhone(raw: string): string | null {
  let digits = raw.replace(/\D/g, '');
  if (digits.startsWith('237')) digits = digits.slice(3);
  return digits.length === 9 ? '+237' + digits : null;
}

/** A 6-8 digit numeric PIN. */
export function isValidPin(pin: string): boolean {
  return /^\d{6,8}$/.test(pin);
}

/** Very light email shape check (server is authoritative). */
export function isValidEmail(email: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.trim());
}
