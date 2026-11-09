import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In development the API runs on :8100 (uvicorn app.main:app --port 8100).
export default defineConfig({
  plugins: [react()],
  server: { port: 5174, proxy: { "/api": "http://127.0.0.1:8100", "/auth": "http://127.0.0.1:8100" } },
});
