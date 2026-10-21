/**
 * Physical product boundaries: the web and desktop apps live in fully
 * separate source trees (apps/web, apps/desktop) with no shared packages —
 * each product owns its own copy of every module and evolves it freely.
 * This suite walks the real import graph from each app entry and fails
 * when code crosses a product boundary:
 *
 *   1. A web entry import never reaches apps/desktop/** (and vice versa).
 *   2. The legacy shared trees frontend/src/ and frontend/packages/ stay
 *      deleted.
 */
import { readFileSync, existsSync, statSync } from "node:fs";
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

  it("keeps the legacy shared trees frontend/src/ and frontend/packages/ deleted", () => {
    expect(existsSync(`${FRONTEND}src`)).toBe(false);
    expect(existsSync(`${FRONTEND}packages`)).toBe(false);
  });
});
