"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./api";
import * as endpoints from "./endpoints";
import type { User } from "./types";

interface AuthContextValue {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;

    async function hydrate() {
      if (!getAccessToken()) {
        setIsLoading(false);
        return;
      }
      try {
        const currentUser = await endpoints.getCurrentUser();
        if (!cancelled) setUser(currentUser);
      } catch {
        clearTokens();
      } finally {
        if (!cancelled) setIsLoading(false);
      }
    }

    hydrate();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const tokens = await endpoints.login(email, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    const currentUser = await endpoints.getCurrentUser();
    setUser(currentUser);
  }, []);

  const register = useCallback(async (email: string, password: string) => {
    await endpoints.register(email, password);
    const tokens = await endpoints.login(email, password);
    setTokens(tokens.access_token, tokens.refresh_token);
    const currentUser = await endpoints.getCurrentUser();
    setUser(currentUser);
  }, []);

  const logout = useCallback(async () => {
    const refreshToken = getRefreshToken();
    if (refreshToken) {
      try {
        await endpoints.logout(refreshToken);
      } catch {
        // best-effort — clear local tokens regardless
      }
    }
    clearTokens();
    setUser(null);
  }, []);

  return (
    <AuthContext.Provider value={{ user, isLoading, login, register, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within an AuthProvider");
  return ctx;
}
