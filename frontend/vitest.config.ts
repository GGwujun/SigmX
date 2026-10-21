import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import path from "path";

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      "@": path.resolve(__dirname, "./src"),
      "@sigmx/ui": path.resolve(__dirname, "./packages/ui/src/index.ts"),
      "@sigmx/api-client": path.resolve(__dirname, "./packages/api-client/src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./src/tests/setup.ts"],
    include: ["src/**/__tests__/**/*.test.{ts,tsx}", "packages/*/src/**/__tests__/**/*.test.{ts,tsx}"],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: ["src/lib/**", "src/stores/**", "packages/api-client/src/**"],
      exclude: ["src/**/__tests__/**", "src/tests/**", "packages/*/src/**/__tests__/**"],
    },
    restoreMocks: true,
  },
});
