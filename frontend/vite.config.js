import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    setupFiles: "./src/tests/setup.js",
  },
  server: {
    port: 5173,
    fs: {
      allow: [
        ".",
        path.resolve(__dirname, ".."),
      ],
    },
    proxy: {
      "/data/staging": {
        target: "http://localhost:8000",
        changeOrigin: true,
        rewrite: (p) => p,
      },
    },
  },
});
