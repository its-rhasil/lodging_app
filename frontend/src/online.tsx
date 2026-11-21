import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

// Offline safeguard (plan.md Day 4): when the browser is offline, a banner shows and every
// action button is disabled, so nobody believes a payment was saved when it wasn't.
const OnlineContext = createContext(true);

export function OnlineProvider({ children }: { children: ReactNode }) {
  const [online, setOnline] = useState(navigator.onLine);
  useEffect(() => {
    const up = () => setOnline(true);
    const down = () => setOnline(false);
    window.addEventListener("online", up);
    window.addEventListener("offline", down);
    return () => {
      window.removeEventListener("online", up);
      window.removeEventListener("offline", down);
    };
  }, []);
  return <OnlineContext.Provider value={online}>{children}</OnlineContext.Provider>;
}

export function useOnline(): boolean {
  return useContext(OnlineContext);
}
