/**
 * Authentication context for managing user state.
 */

import {
  createContext,
  useContext,
  useEffect,
  useState,
  useCallback,
  type ReactNode,
} from 'react';
import { useNavigate } from 'react-router-dom';
import { authApi } from '@/api/auth';
import { tokenStorage, setAuthFailureCallback } from '@/api/client';
import type { User, LoginRequest, RegisterRequest, UserUpdateRequest } from '@/api/types';

interface AuthContextValue {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  isAdmin: boolean;
  login: (credentials: LoginRequest) => Promise<void>;
  register: (data: RegisterRequest) => Promise<void>;
  logout: () => Promise<void>;
  updateProfile: (data: UserUpdateRequest) => Promise<User>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

interface AuthProviderProps {
  children: ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const navigate = useNavigate();

  // Handle auth failure (called by API client on 401)
  const handleAuthFailure = useCallback(() => {
    setUser(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  // Set up auth failure callback
  useEffect(() => {
    setAuthFailureCallback(handleAuthFailure);
    return () => setAuthFailureCallback(() => {});
  }, [handleAuthFailure]);

  // Check for existing auth on mount
  useEffect(() => {
    const checkAuth = async () => {
      if (tokenStorage.hasTokens()) {
        try {
          const currentUser = await authApi.getMe();
          setUser(currentUser);
        } catch {
          // Token invalid - clear it
          tokenStorage.clearTokens();
        }
      }
      setIsLoading(false);
    };

    checkAuth();
  }, []);

  const login = useCallback(async (credentials: LoginRequest) => {
    const { user: loggedInUser } = await authApi.login(credentials);
    setUser(loggedInUser);
  }, []);

  const register = useCallback(async (data: RegisterRequest) => {
    await authApi.register(data);
    // Don't auto-login after registration - let them log in manually
  }, []);

  const logout = useCallback(async () => {
    await authApi.logout();
    setUser(null);
    navigate('/login', { replace: true });
  }, [navigate]);

  const updateProfile = useCallback(async (data: UserUpdateRequest) => {
    const updatedUser = await authApi.updateProfile(data);
    setUser(updatedUser);
    return updatedUser;
  }, []);

  const refreshUser = useCallback(async () => {
    if (tokenStorage.hasTokens()) {
      const currentUser = await authApi.getMe();
      setUser(currentUser);
    }
  }, []);

  const value: AuthContextValue = {
    user,
    isAuthenticated: !!user,
    isLoading,
    isAdmin: user?.role === 'admin',
    login,
    register,
    logout,
    updateProfile,
    refreshUser,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
