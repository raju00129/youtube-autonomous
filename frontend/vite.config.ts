import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    host: true,
    port: 5173,
    // Allow reverse-proxied production host (Vite DNS rebinding protection).
    allowedHosts: ["youtube-auto.sigwent.com", "localhost", ".sigwent.com"],
  },
});
