/**
 * Physical product boundaries: the web and desktop apps live in separate
 * source trees (apps/web, apps/desktop) over shared packages. This suite
 * walks the real import graph from each app entry and fails when code
 * crosses a product boundary:
 *
 *   1. A web entry import never reaches apps/desktop/** (and vice versa).
 *   2. Nothing under packages/** resolves into apps/**.
 *   3. Package sources never use the `@/` alias (apps-only).
 *   4. The legacy shared tree frontend/src/ stays deleted.
 */
import { readFileSync, existsSync, readdirSync, statSync } from "node:fs";
import { describe, expect, it } from "vitest";

// Vitest always runs with cwd = frontend/ (npm scripts live there); jsdom
// rewrites import.meta.url to a non-file URL, so cwd is the stable anchor.
const FRONTEND = process.cwd().replace(/\\/g, "/") + "/";

const EXTENSION_CANDIDATES = ["", ".ts", ".tsx", ".css", ".json", "/index.ts", "/index.tsx"];

function normalize(id: string): string {
  return id.replace(/\\/g, "/").replace(/\/\.\//g, "/");
}

function resolveFile(base: string): string | null {
  for (const ext of EXTENSION_CANDIDATES) {
    const candidate = base + ext;
    if (existsSync(candidate) && statSync(candidate).isFile()) return candidate;
  }
  return null;
}

function resolveSpecifier(specifier: string, importer: string): string | null {
  if (specifier === "@sigmx/ui") {
    return resolveFile(`${FRONTEND}packages/ui/src/index`);
  }
  if (specifier.startsWith("@sigmx/")) {
    const [, pkg, ...rest] = specifier.split("/");
    return resolveFile(`${FRONTEND}packages/${pkg}/src/${rest.join("/")}`);
  }
  if (specifier.startsWith("@/")) {
    const importerDir = importer.slice(0, importer.lastIndexOf("/") + 1);
    const base = importerDir + specifier.slice(2);
    return resolveFile(base);
  }
  if (specifier.startsWith(".")) {
    const importerDir = importer.slice(0, importer.lastIndexOf("/") + 1);
    return resolveFile(normalize(importerDir + specifier));
  }
  return null; // external package (react, echarts, …)
}

function extractSpecifiers(source: string): string[] {
  const specifiers: string[] = [];
  const patterns = [
    /\bfrom\s+["']([^"']+)["']/g,
    /\bimport\(\s*["']([^"']+)["']\s*\)/g,
    /(?:^|\n)\s*import\s+["']([^"']+)["']/g,
  ];
  for (const pattern of patterns) {
    for (const match of source.matchAll(pattern)) specifiers.push(match[1]);
  }
  return specifiers;
}

function collectReachable(entry: string): Set<string> {
  const reachable = new Set<string>();
  const queue = [entry];
  while (queue.length > 0) {
    const file = queue.pop() as string;
    if (reachable.has(file)) continue;
    reachable.add(file);
    for (const specifier of extractSpecifiers(readFileSync(file, "utf-8"))) {
      const resolved = resolveSpecifier(specifier, file);
      if (resolved && !reachable.has(resolved)) queue.push(resolved);
    }
  }
  return reachable;
}

function walkSourceFiles(dir: string): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(dir, { withFileTypes: true })) {
    const full = `${dir}/${entry.name}`;
    if (entry.isDirectory()) {
      if (entry.name === "__tests__") continue;
      files.push(...walkSourceFiles(full));
    } else if (/\.(ts|tsx)$/.test(entry.name)) {
      files.push(full);
    }
  }
  return files;
}

describe("physical product boundaries", () => {
  const webEntry = `${FRONTEND}apps/web/src/main.tsx`;
  const desktopEntry = `${FRONTEND}apps/desktop/src/main.tsx`;

  it("ships both app entries", () => {
    expect(existsSync(webEntry)).toBe(true);
    expect(existsSync(desktopEntry)).toBe(true);
  });

  it("keeps the web import graph out of apps/desktop", () => {
    const leaks = [...collectReachable(webEntry)].filter((f) =>
      f.startsWith(`${FRONTEND}apps/desktop/`),
    );
    expect(leaks).toEqual([]);
  });

  it("keeps the desktop import graph out of apps/web", () => {
    const leaks = [...collectReachable(desktopEntry)].filter((f) =>
      f.startsWith(`${FRONTEND}apps/web/`),
    );
    expect(leaks).toEqual([]);
  });

  it("never resolves a packages/** import into apps/**", () => {
    const offenders: string[] = [];
    for (const pkg of ["ui", "api-client", "shared"]) {
      for (const file of walkSourceFiles(`${FRONTEND}packages/${pkg}/src`)) {
        for (const specifier of extractSpecifiers(readFileSync(file, "utf-8"))) {
          const resolved = resolveSpecifier(specifier, file);
          if (resolved?.startsWith(`${FRONTEND}apps/`)) offenders.push(`${file} → ${specifier}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the `@/` alias out of packages/**", () => {
    const offenders: string[] = [];
    for (const pkg of ["ui", "api-client", "shared"]) {
      for (const file of walkSourceFiles(`${FRONTEND}packages/${pkg}/src`)) {
        if (/["']@\//.test(readFileSync(file, "utf-8"))) offenders.push(file);
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the legacy shared tree frontend/src/ deleted", () => {
    expect(existsSync(`${FRONTEND}src`)).toBe(false);
  });
});
