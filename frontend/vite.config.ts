import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// During development the Vite server proxies API calls to Django, so the
// browser talks to a single origin and no CORS configuration is needed.
const backend = process.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8000";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: true },
      "/admin": { target: backend, changeOrigin: true },
      "/static": { target: backend, changeOrigin: true },
    },
  },
  build: { target: "es2020", sourcemap: false },
});
