/**
 * Base path of the KYC-API backend.
 *
 * Relative on purpose: the browser calls the same host it loaded the app
 * from, and the reverse proxy routes /api to the backend. In production that
 * host is the real domain; in `ng serve` the dev proxy (proxy.conf.json)
 * forwards /api to localhost:8000. Nothing to swap per environment.
 */
export const API_URL = '/api/v1';
