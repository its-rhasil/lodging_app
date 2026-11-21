// Cloudflare Pages Function: forwards every /api/* request to the API server (Render).
// The browser only ever talks to <name>.pages.dev, so the session cookie is first-party.

// ---- How this works ----
// WHERE THIS RUNS
//   Not in the browser and not on Render: on Cloudflare's servers, as part of the Pages site.
//   Cloudflare maps files in frontend/functions/ to URLs. The file name "[[path]].ts" inside
//   "api/" means: run for /api and for everything below it (/api/stays/12, /api/auth/me, ...).
//   Everything else (/, /stays/12, icons, JS files) is still served as the built static app.
//
// WHY IT EXISTS
//   Without it, the app would be at <name>.pages.dev and the API at <api>.onrender.com:
//   two different sites. The login cookie would then be a "third-party" cookie, which iPhones
//   (Safari) block, so login would silently fail there. Through this proxy, the browser sends
//   everything to pages.dev; the cookie belongs to pages.dev, and no CORS setup is needed.
//   The frontend already calls "/api/..." (src/api.ts, BASE = "/api"), so no app code changes.
//
// HOW IT WORKS, LINE BY LINE (onRequest below)
//   1. Cloudflare calls onRequest({ request, env }) for each /api request.
//      env holds the settings typed in the Pages dashboard; we need one: API_ORIGIN,
//      e.g. "https://lodge-api.onrender.com". If it's missing we answer 500 with a clear
//      message in the same {code, message} shape the backend uses, so the app shows it.
//   2. Build the target URL: drop the leading "/api" and keep the query string.
//      /api/stays?status=active  ->  https://lodge-api.onrender.com/stays?status=active
//      (The backend has no /api prefix; in development Vite's proxy strips it the same way,
//      see vite.config.ts.)
//   3. Copy the browser's headers (Cookie, Content-Type, X-Request-ID, User-Agent, ...).
//      - Remove "Host": it says pages.dev; the request to Render must carry Render's own host,
//        which fetch() fills in from the target URL.
//      - Set "X-Forwarded-For" to the visitor's real IP, which Cloudflare gives us in
//        "CF-Connecting-IP". Otherwise Render would see Cloudflare's IP, and the audit log
//        (audit_events.ip) would record that instead of the staff device's IP. On Render,
//        uvicorn runs with --proxy-headers so request.client becomes this IP
//        (app/core/request_context.py, get_request_meta).
//        Note: someone calling the onrender.com address directly could fake this header.
//        The IP in the audit log is informational only; nothing is allowed or denied by it.
//   4. Send the request on with the same method and body. The body (small JSON) is read in
//      full first, then sent unchanged. GET and HEAD must not carry a body at all, so for
//      them we pass none (fetch() throws if a GET is given one, even an empty one).
//   5. Return Render's response as it is: status, body and headers, including "Set-Cookie"
//      on login/logout. The cookie has no Domain attribute (app/core/cookies.py), so the
//      browser stores it for pages.dev, the address it actually talked to.
//
// WHAT IT DOES NOT DO
//   No caching (money data must never be stale), no auth checks (the backend does those),
//   no changes to the request or response body.
//
// TYPES: the types below are written by hand (Context, Env) instead of installing
// @cloudflare/workers-types, to avoid a new dependency. Request/Response/Headers/URL are
// standard web types. Cloudflare compiles this file itself when it deploys the site.
// ---- end ----

type Env = { API_ORIGIN?: string };
type Context = { request: Request; env: Env };

export async function onRequest({ request, env }: Context): Promise<Response> {
  if (!env.API_ORIGIN) {
    return Response.json(
      { code: "proxy_not_configured", message: "The server address is not set up (API_ORIGIN).", details: null },
      { status: 500 },
    );
  }

  const url = new URL(request.url);
  const path = url.pathname.replace(/^\/api/, "") || "/";
  const target = new URL(path + url.search, env.API_ORIGIN);

  const headers = new Headers(request.headers);
  headers.delete("Host");
  const clientIp = request.headers.get("CF-Connecting-IP");
  if (clientIp) {
    headers.set("X-Forwarded-For", clientIp);
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  return fetch(target, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
  });
}
