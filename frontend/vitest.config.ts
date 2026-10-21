import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "path";

// `@` resolves per-importer: files under apps/web map to the web src tree,
// apps/desktop to the desktop src tree. Anything else using `@/` is a
// boundary violation (packages must import via @sigmx/* aliases only).
// Plugin-returned ids are final, so extension candidates are probed here.
function appAlias() {
  const extensions = [".ts", ".tsx", ".css", ".json"];
  return {
    name: "sigmx-app-alias",
    enforce: "pre",
    resolveId(source: string, importer?: string) {
      if (!source.startsWith("@/") || !importer) return null;
      const normalized = importer.replaceAll("\\", "/");
      let appSrc: string;
      if (normalized.includes("/apps/web/")) {
        appSrc = path.resolve(__dirname, "apps/web/src");
      } else if (normalized.includes("/apps/desktop/")) {
        appSrc = path.resolve(__dirname, "apps/desktop/src");
      } else {
        throw new Error(`"@/" import outside an app: ${importer} imports ${source}`);
      }
      const base = path.join(appSrc, source.slice(2));
      for (const ext of extensions) {
        if (fs.existsSync(base + ext)) return base + ext;
      }
      return base;
    },
  };
}

export default defineConfig({
  plugins: [appAlias(), react()],
  resolve: {
    alias: {
      "@sigmx/ui": path.resolve(__dirname, "./packages/ui/src/index.ts"),
      "@sigmx/api-client": path.resolve(__dirname, "./packages/api-client/src"),
      "@sigmx/shared": path.resolve(__dirname, "./packages/shared/src"),
    },
  },
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./packages/shared/src/testing/setup.ts"],
    include: [
      "apps/*/src/**/__tests__/**/*.test.{ts,tsx}",
      "packages/*/src/**/__tests__/**/*.test.{ts,tsx}",
      "tests/**/*.test.{ts,tsx}",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: [
        "apps/*/src/lib/**",
        "apps/*/src/stores/**",
        "packages/api-client/src/**",
        "packages/shared/src/lib/**",
      ],
      exclude: ["apps/*/src/**/__tests__/**", "packages/*/src/**/__tests__/**"],
    },
    restoreMocks: true,
  },
});
