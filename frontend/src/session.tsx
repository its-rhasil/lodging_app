import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { api } from "./api";
import { setLocaleSettings } from "./format";
import type { Me, Settings } from "./types";

type SessionValue = {
  me: Me | null;
  settings: Settings | null;
  loading: boolean;
  can: (permission: string) => boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  reloadSettings: () => Promise<void>;
};

const SessionContext = createContext<SessionValue | null>(null);

export function SessionProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<Me | null>(null);
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loading, setLoading] = useState(true);

  const reloadSettings = useCallback(async () => {
    const s = await api.get<Settings>("/settings");
    setLocaleSettings(s.timezone, s.currency);
    setSettings(s);
  }, []);

  const loadSession = useCallback(async () => {
    try {
      setMe(await api.get<Me>("/auth/me"));
      await reloadSettings();
    } catch {
      setMe(null);
    } finally {
      setLoading(false);
    }
  }, [reloadSettings]);

  useEffect(() => {
    loadSession();
    const onExpired = () => setMe(null);
    window.addEventListener("session-expired", onExpired);
    return () => window.removeEventListener("session-expired", onExpired);
  }, [loadSession]);

  const login = async (email: string, password: string) => {
    setMe(await api.post<Me>("/auth/login", { email, password }));
    await reloadSettings();
  };

  const logout = async () => {
    await api.post("/auth/logout").catch(() => undefined);
    setMe(null);
  };

  const can = (permission: string) => !!me?.permissions.includes(permission);

  return (
    <SessionContext.Provider value={{ me, settings, loading, can, login, logout, reloadSettings }}>
      {children}
    </SessionContext.Provider>
  );
}

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (!value) throw new Error("useSession outside SessionProvider");
  return value;
}
