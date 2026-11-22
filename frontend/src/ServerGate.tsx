import { useEffect, useState, type ReactNode } from "react";

const BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? "/api";
const WAKE_URL = import.meta.env.VITE_WAKE_URL as string | undefined;

// "Waking server" screen (plan.md Day 4): a free-tier host can sleep and take ~30-60 s to start.
// Until /health answers, show a friendly wait screen instead of failing requests.

// ---- How this works ----
// WAKE-UP PING (the first useEffect below)
//   Render's free server sleeps after 15 minutes without visitors. A request that comes
//   through our Cloudflare proxy (/api/...) does NOT wake it: Render answers 502 at once.
//   A request sent straight to the onrender.com address DOES wake it (Render holds that
//   request ~30-60 s while the server starts).
//   So, once each time the app opens, the browser sends one request straight to
//   VITE_WAKE_URL (e.g. https://frontdeskinn-api.onrender.com/health). If the server is
//   asleep, this starts it; the health checks below then succeed once it is up.
//   If it is already awake, it is just one cheap extra request.
//
//   - mode "no-cors": the browser may send the request to another site without the API
//     allowing it (no CORS setup on the backend); we just can't read the answer, and we
//     don't need to.
//   - credentials "omit": no cookies go to onrender.com; the login cookie stays on pages.dev.
//   - cache "no-store": the browser must really send it, not reuse an old answer.
//   - .catch(() => {}): if the ping fails (offline, etc.) nothing breaks; the retry loop
//     below still runs.
//   - VITE_WAKE_URL is read at BUILD time (set in Cloudflare Pages → Settings → Variables).
//     If it isn't set (e.g. local development), no ping is sent.
// ---- end ----
export function ServerGate({ children }: { children: ReactNode }) {
  const [ready, setReady] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    if (!WAKE_URL) return;
    fetch(WAKE_URL, { mode: "no-cors", credentials: "omit", cache: "no-store" }).catch(() => {});
  }, []);

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
