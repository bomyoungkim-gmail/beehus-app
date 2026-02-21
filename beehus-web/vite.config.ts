import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    host: "0.0.0.0",
    port: 5173,
    strictPort: true,
    watch: {
      usePolling: process.env.CHOKIDAR_USEPOLLING === "1",
      ignored: [
        "**/.git/**",
        "**/node_modules/**",
        "**/artifacts/**",
        "**/artifacts_manual_test/**",
        "**/downloads/**",
      ],
    },
    // Explicit HMR endpoint for Docker-on-Windows networking.
    hmr: {
      protocol: "ws",
      host: "localhost",
      port: 5173,
      clientPort: 5173,
      overlay: true,
    },
    cors: true,
  },
});
