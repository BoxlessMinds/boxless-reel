/**
 * Auth API endpoints.
 */

import { apiClient, publicApiClient, tokenStorage } from './client';
import type {
  LoginRequest,
  TokenResponse,
  RegisterRequest,
  RegistrationMode,
  User,
  UserUpdateRequest,
} from './types';

export const authApi = {
  /**
   * Get current registration mode (public, no auth required).
   */
  getRegistrationMode: (): Promise<RegistrationMode> => {
    return publicApiClient<RegistrationMode>('/api/auth/registration-mode');
  },

  /**
   * Login with email and password.
   */
  login: async (credentials: LoginRequest): Promise<{ user: User; tokens: TokenResponse }> => {
    const tokens = await publicApiClient<TokenResponse>('/api/auth/login', {
      method: 'POST',
      body: JSON.stringify(credentials),
    });

    // Store tokens
    tokenStorage.setTokens(tokens.access_token, tokens.refresh_token);

    // Fetch user profile
    const user = await authApi.getMe();

    return { user, tokens };
  },

  /**
   * Register a new user with an invitation token.
   */
  register: async (data: RegisterRequest): Promise<User> => {
    return publicApiClient<User>('/api/auth/register', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  /**
   * Logout by revoking refresh token.
   */
  logout: async (): Promise<void> => {
    const refreshToken = tokenStorage.getRefreshToken();
    if (refreshToken) {
      try {
        await apiClient<{ message: string }>('/api/auth/logout', {
          method: 'POST',
          body: JSON.stringify({ refresh_token: refreshToken }),
        });
      } catch {
        // Ignore errors - we're logging out anyway
      }
    }
    tokenStorage.clearTokens();
  },

  /**
   * Get current user's profile.
   */
  getMe: (): Promise<User> => {
    return apiClient<User>('/api/auth/me');
  },

  /**
   * Update current user's profile.
   */
  updateProfile: (data: UserUpdateRequest): Promise<User> => {
    return apiClient<User>('/api/auth/me', {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  },

  /**
   * Check if user is authenticated (has valid token).
   */
  isAuthenticated: (): boolean => {
    return tokenStorage.hasTokens();
  },
};
