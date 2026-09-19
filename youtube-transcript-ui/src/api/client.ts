/**
 * API client with error handling and authentication for the YouTube Transcript API.
 */

const API_BASE_URL = import.meta.env.VITE_API_URL || 'http://127.0.0.1:8001';

// Token storage keys
const ACCESS_TOKEN_KEY = 'access_token';
const REFRESH_TOKEN_KEY = 'refresh_token';

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// Token storage helpers
export const tokenStorage = {
  getAccessToken: (): string | null => localStorage.getItem(ACCESS_TOKEN_KEY),
  getRefreshToken: (): string | null => localStorage.getItem(REFRESH_TOKEN_KEY),
  setTokens: (accessToken: string, refreshToken: string): void => {
    localStorage.setItem(ACCESS_TOKEN_KEY, accessToken);
    localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
  },
  clearTokens: (): void => {
    localStorage.removeItem(ACCESS_TOKEN_KEY);
    localStorage.removeItem(REFRESH_TOKEN_KEY);
  },
  hasTokens: (): boolean => {
    return !!localStorage.getItem(ACCESS_TOKEN_KEY);
  },
};

// Callback for handling auth failures (set by AuthContext)
let onAuthFailure: (() => void) | null = null;

export function setAuthFailureCallback(callback: () => void): void {
  onAuthFailure = callback;
}

/**
 * API client with authentication support.
 * Automatically adds Authorization header if token is available.
 * Handles 401 responses by triggering auth failure callback.
 */
export async function apiClient<T>(
  endpoint: string,
  options: RequestInit = {},
  skipAuth: boolean = false
): Promise<T> {
  const url = `${API_BASE_URL}${endpoint}`;

  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options.headers as Record<string, string>),
  };

  // Add authorization header if token exists and auth is not skipped
  if (!skipAuth) {
    const token = tokenStorage.getAccessToken();
    if (token) {
      headers['Authorization'] = `Bearer ${token}`;
    }
  }

  const config: RequestInit = {
    ...options,
    headers,
  };

  let response: Response;
  try {
    response = await fetch(url, config);
  } catch {
    throw new ApiError(0, 'Connection failed. Is the API running?');
  }

  // Handle 401 Unauthorized
  if (response.status === 401 && !skipAuth) {
    // Try to refresh the token
    const refreshed = await tryRefreshToken();
    if (refreshed) {
      // Retry the request with new token
      const newToken = tokenStorage.getAccessToken();
      if (newToken) {
        headers['Authorization'] = `Bearer ${newToken}`;
        const retryConfig: RequestInit = { ...options, headers };
        const retryResponse = await fetch(url, retryConfig);
        if (retryResponse.ok) {
          if (retryResponse.status === 204) {
            return {} as T;
          }
          return retryResponse.json();
        }
      }
    }

    // Refresh failed or retry failed - trigger auth failure
    tokenStorage.clearTokens();
    if (onAuthFailure) {
      onAuthFailure();
    }
    throw new ApiError(401, 'Session expired. Please log in again.');
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: 'Unknown error' }));
    throw new ApiError(response.status, error.detail || `HTTP ${response.status}`);
  }

  // Handle 204 No Content
  if (response.status === 204) {
    return {} as T;
  }

  return response.json();
}

/**
 * Try to refresh the access token using the refresh token.
 */
async function tryRefreshToken(): Promise<boolean> {
  const refreshToken = tokenStorage.getRefreshToken();
  if (!refreshToken) {
    return false;
  }

  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh_token: refreshToken }),
    });

    if (response.ok) {
      const data = await response.json();
      tokenStorage.setTokens(data.access_token, data.refresh_token);
      return true;
    }
  } catch {
    // Refresh failed
  }

  return false;
}

/**
 * API client for unauthenticated requests.
 */
export async function publicApiClient<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  return apiClient<T>(endpoint, options, true);
}
