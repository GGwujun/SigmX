import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import path from "path";

// Purely API routes — never a browser page, always proxy to backend
const API_ONLY_PATHS = [
  "/sessions",
  "/swarm/presets",
  "/swarm/runs",
  "/settings/llm",
  "/settings/data-sources",
  "/mandate",
  "/live",
  "/upload",
  "/shadow-reports",
  "/position",   // /position/analyze, /position/snapshot/{code} — API only
];

// SPA page paths that ALSO have API endpoints at the same URL.
// Use HTML fallback: browser refresh returns index.html, JS fetch returns JSON.
const SPA_WITH_API_PATHS = [
  "/events",
  "/news",
  "/opportunity",
  "/logic-chain",
];

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_URL || "http://localhost:8899";
  const apiProxy = { target: apiTarget, changeOrigin: true };
  const apiProxyWithHtmlFallback = {
    ...apiProxy,
    bypass(req: { headers: { accept?: string } }) {
      if (req.headers.accept?.includes("text/html")) {
        return "/index.html";
      }
    },
  };

  return {
    plugins: [react()],
    resolve: {
      alias: { "@": path.resolve(__dirname, "./src") },
    },
    server: {
      port: 5899,
      proxy: {
        // API-only routes: always proxy to backend
        ...Object.fromEntries(API_ONLY_PATHS.map((p) => [p, apiProxy])),
        // SPA pages that share a URL with API: HTML fallback on browser refresh
        ...Object.fromEntries(SPA_WITH_API_PATHS.map((p) => [p, apiProxyWithHtmlFallback])),
        // SPA RunDetail page — only the two-segment ``/runs/{id}``
        // form should fall back to ``index.html`` on browser navigation.
        // ``/runs/{id}/code`` and ``/runs/{id}/pine`` are API-only and
        // must keep proxying to the backend even when Accept is text/html.
        "^/runs/[^/]+/?$": apiProxyWithHtmlFallback,
        "/runs": apiProxy,
        "/correlation": apiProxyWithHtmlFallback,
        "^/alpha(?:/|$)": apiProxy,
      },
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            "vendor-react": ["react", "react-dom", "react-router-dom"],
            "vendor-charts": ["echarts"],
          },
        },
      },
    },
  };
});
