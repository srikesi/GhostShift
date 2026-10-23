import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend, so the browser never
// needs backend credentials or a separate origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Hostnames a phone can open: sslip.io maps 172-24-127-47.sslip.io to the LAN IP (WhatsApp only
    // makes links with a real domain tappable); trycloudflare.com is for quick public tunnels.
    allowedHosts: [".sslip.io", ".trycloudflare.com"],
    proxy: {
      "/api": { target: process.env.GHOSTSHIFT_API_URL ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
