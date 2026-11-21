import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
import { VitePWA } from "vite-plugin-pwa";

// Dev: the API runs on :8000 and is proxied under /api, so the session cookie is same-origin.
// Production: set VITE_API_URL to the API's URL (e.g. https://api.<domain>) at build time.
export default defineConfig({
  plugins: [
    react(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["icon.svg"],
      manifest: {
        name: "Lodge Front Desk",
        short_name: "Front Desk",
        description: "Rooms, check-ins and bills for the front desk",
        theme_color: "#1f4e79",
        background_color: "#f5f6f8",
        display: "standalone",
        start_url: "/",
        icons: [{ src: "icon.svg", sizes: "any", type: "image/svg+xml", purpose: "any maskable" }],
      },
      workbox: {
        // Only the app shell is cached. API calls always go to the network: money data is never stale.
        navigateFallback: "/index.html",
        navigateFallbackDenylist: [/^\/api\//],
      },
    }),
  ],
  server: {
    port: 5173,
    proxy: {
      "/api": {
        target: "http://127.0.0.1:8000",
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/api/, ""),
      },
    },
  },
});
