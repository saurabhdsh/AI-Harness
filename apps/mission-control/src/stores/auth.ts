import { create } from "zustand";
import { api, getStoredUser, getToken, setStoredUser, setToken } from "../lib/api";
import type { AuthUser, TokenResponse } from "../lib/types";

type AuthState = {
  user: AuthUser | null;
  booted: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  hydrate: () => void;
};

export const useAuth = create<AuthState>((set) => ({
  user: null,
  booted: false,
  login: async (email, password) => {
    const data = await api<TokenResponse>("/api/v1/auth/login", {
      method: "POST",
      body: JSON.stringify({ email: email.trim(), password }),
    });
    setToken(data.access_token);
    const user: AuthUser = {
      id: data.user_id,
      email: data.email,
      role: "ADMIN",
      tenantId: data.tenant_id,
    };
    setStoredUser(user);
    set({ user });
  },
  logout: () => {
    setToken(null);
    setStoredUser(null);
    set({ user: null });
  },
  hydrate: () => {
    const token = getToken();
    const user = getStoredUser<AuthUser>();
    if (token && user) set({ user, booted: true });
    else {
      setToken(null);
      setStoredUser(null);
      set({ user: null, booted: true });
    }
  },
}));
