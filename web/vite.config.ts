import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: { "/api": "http://127.0.0.1:8787" },
  },
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes("/node_modules/three/")) return "three";
          if (id.includes("/node_modules/minisearch/") || id.includes("/node_modules/culori/")) {
            return "catalog-vendor";
          }
          return undefined;
        },
      },
    },
  },
  test: {
    environment: "jsdom",
  },
});
