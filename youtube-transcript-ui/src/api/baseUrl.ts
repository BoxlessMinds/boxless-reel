/**
 * Base address for API requests.
 *
 * By default this is empty, so the browser calls `/api/...` on the same origin
 * that served the web interface: nginx forwards it to the API in Docker, and the
 * Vite proxy forwards it in development. Set `VITE_API_URL` only when the web
 * interface is served from a different address than the API.
 */

const configuredApiUrl = (import.meta.env.VITE_API_URL ?? '').trim();

export const API_BASE_URL = configuredApiUrl.replace(/\/+$/, '');
