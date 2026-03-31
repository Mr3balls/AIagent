"use client";

import { createContext, useCallback, useEffect, useMemo, useState } from "react";
import { clearStoredToken, getStoredToken, setStoredToken } from "@/lib/auth";
import { getMe, loginUser, registerUser } from "@/lib/api";
import { AuthContextValue, LoginPayload, RegisterPayload, User } from "@/lib/types";

export const AuthContext = createContext<AuthContextValue | undefined>(undefined);

interface AuthProviderProps {
  children: React.ReactNode;
}

export function AuthProvider({ children }: AuthProviderProps) {
  const [user, setUser] = useState<User | null>(null);
  const [token, setToken] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    clearStoredToken();
    setToken(null);
    setUser(null);
  }, []);

  const refreshUser = useCallback(
    async (tokenOverride?: string) => {
      const activeToken = tokenOverride || token || getStoredToken();

      if (!activeToken) {
        throw new Error("Access token not found");
      }

      const me = await getMe(activeToken);
      setUser(me);
      setToken(activeToken);
      return me;
    },
    [token],
  );

  const login = useCallback(async (payload: LoginPayload) => {
    const response = await loginUser(payload);
    const accessToken = response.access_token;

    setStoredToken(accessToken);
    setToken(accessToken);

    const me = await getMe(accessToken);
    setUser(me);

    return me;
  }, []);

  const register = useCallback(async (payload: RegisterPayload) => {
    return registerUser(payload);
  }, []);

  useEffect(() => {
    let mounted = true;

    async function initializeAuth() {
      const storedToken = getStoredToken();

      if (!storedToken) {
        if (mounted) {
          setLoading(false);
        }
        return;
      }

      try {
        const me = await getMe(storedToken);

        if (!mounted) {
          return;
        }

        setToken(storedToken);
        setUser(me);
      } catch {
        if (!mounted) {
          return;
        }

        clearStoredToken();
        setToken(null);
        setUser(null);
      } finally {
        if (mounted) {
          setLoading(false);
        }
      }
    }

    initializeAuth();

    return () => {
      mounted = false;
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      token,
      loading,
      isAuthenticated: Boolean(user && token),
      login,
      register,
      logout,
      refreshUser,
    }),
    [user, token, loading, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}