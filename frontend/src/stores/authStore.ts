import { create } from "zustand";
import { authApi } from "../services/api";

export interface User {
  id: string;
  email: string;
  first_name?: string;
  last_name?: string;
  role: "superadmin" | "user" | "readonly";
  plan: "free" | "pro" | "business";
  has_pdf_access: boolean;
  is_email_verified: boolean;
}

interface AuthState {
  user: User | null;
  initialized: boolean;
  setUser: (user: User | null) => void;
  init: () => Promise<void>;
  logout: () => Promise<void>;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,
  initialized: false,
  setUser: (user) => set({ user }),
  init: async () => {
    const token = localStorage.getItem("access_token");
    if (!token) { set({ initialized: true }); return; }
    try {
      const res = await authApi.getMe();
      set({ user: res.data, initialized: true });
    } catch {
      localStorage.removeItem("access_token");
      localStorage.removeItem("refresh_token");
      set({ user: null, initialized: true });
    }
  },
  logout: async () => {
    try { await authApi.logout(); } finally { set({ user: null }); }
  },
}));
