import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";
import fs from "node:fs";
import path from "path";

// `@` resolves per-importer: files under apps/web map to the web src tree,
// apps/desktop to the desktop src tree. Test files outside either app must
// not use the alias. Plugin-returned ids are final, so extension candidates
// are probed here.
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
      const candidates = [
        ...extensions.map((ext) => base + ext),
        path.join(base, "index.ts"),
        path.join(base, "index.tsx"),
      ];
      for (const candidate of candidates) {
        if (fs.existsSync(candidate) && fs.statSync(candidate).isFile()) return candidate;
      }
      return base;
    },
  };
}

export default defineConfig({
  plugins: [appAlias(), react()],
  test: {
    globals: true,
    environment: "jsdom",
    setupFiles: ["./tests/setup.ts"],
    include: [
      "apps/*/src/**/__tests__/**/*.test.{ts,tsx}",
      "tests/**/*.test.{ts,tsx}",
    ],
    coverage: {
      provider: "v8",
      reporter: ["text", "html", "lcov"],
      include: ["apps/*/src/lib/**", "apps/*/src/stores/**"],
      exclude: ["apps/*/src/**/__tests__/**"],
    },
    restoreMocks: true,
  },
});
