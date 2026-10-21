import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";

import { ErrorBoundary } from "@sigmx/shared/components/common/ErrorBoundary";
import { SSEProvider } from "@sigmx/shared/lib/sseProvider";
import { desktopRouter } from "@/router/desktopRouter";
import "highlight.js/styles/github-dark-dimmed.min.css";
import "@sigmx/shared/index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode><ErrorBoundary><SSEProvider><RouterProvider router={desktopRouter} /><Toaster position="bottom-right" richColors closeButton /></SSEProvider></ErrorBoundary></StrictMode>,
);
