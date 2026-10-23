import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The dev server proxies /api to the FastAPI backend, so the browser never
// needs backend credentials or a separate origin.
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: process.env.FAULTZY_API_URL ?? "http://127.0.0.1:8000", changeOrigin: true },
    },
  },
});
