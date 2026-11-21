import { useEffect, useState, type ReactNode } from "react";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";

// "Waking server" screen (plan.md Day 4): a free-tier host can sleep and take ~30-60 s to start.
// Until /health answers, show a friendly wait screen instead of failing requests.
export function ServerGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    const check = async () => {
      try {
        const res = await fetch(BASE + "/health", { credentials: "include" });
        if (res.ok && !cancelled) {
          setReady(true);
          return;
        }
      } catch {
        // not up yet
      }
      if (!cancelled) setTimeout(() => setAttempt((n) => n + 1), 3000);
    };
    check();
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  if (ready) return <>{children}</>;
  return (
    <div className="center-screen">
      <div className="spinner" />
      <h2>Waking the server…</h2>
      <p className="muted">
        {attempt === 0 ? "Connecting." : "This can take up to a minute after a quiet period."}
      </p>
    </div>
  );
}
