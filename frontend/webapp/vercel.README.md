# Vercel deploy notes

1. In `vercel.json`, replace `https://YOUR-RENDER-SERVICE.onrender.com` with your Render (or other) API host. The browser only talks to your Vercel origin; `/api/*` is proxied server-side so refresh cookies stay first-party.
2. Set production `VITE_API_URL` to empty (see `.env.production.example`) so the SPA calls relative `/api/…` on the same host.
3. If the API uses a **custom domain** instead of the placeholder host, update the rewrite `destination` and add that origin to `Content-Security-Policy` `connect-src` in `vercel.json`. The API must allow CORS from your Vercel site only if the browser ever calls it directly; with same-origin `/api` rewrites, CORS is usually unnecessary for app traffic.