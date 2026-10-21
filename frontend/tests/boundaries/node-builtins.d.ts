// Minimal ambient declarations for the Node builtins used by the boundary
// tests. The repo deliberately ships without @types/node; these cover only
// what tests/boundaries actually calls (runtime is always Node via vitest).
declare module "node:fs" {
  export function readFileSync(path: string, encoding: "utf-8"): string;
  export function existsSync(path: string): boolean;
  export interface Stats {
    isFile(): boolean;
    isDirectory(): boolean;
  }
  export function statSync(path: string): Stats;
  export interface Dirent {
    name: string;
    isDirectory(): boolean;
    isFile(): boolean;
  }
  export function readdirSync(path: string, options: { withFileTypes: true }): Dirent[];
}

declare module "node:url" {
  export function fileURLToPath(url: string | URL): string;
}

declare const process: {
  cwd(): string;
};
