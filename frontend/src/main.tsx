import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router-dom";
import { Toaster } from "sonner";
import { ErrorBoundary } from "./components/common/ErrorBoundary";
import { SSEProvider } from "./lib/sseProvider";
import { router } from "./router";
import "highlight.js/styles/github-dark-dimmed.min.css";
import "./index.css";

const root = document.getElementById("root")!;
if (root.querySelector("[data-sigmx-server-rendered]")) root.replaceChildren();

createRoot(root).render(
  <StrictMode>
    <ErrorBoundary>
      <SSEProvider>
        <RouterProvider router={router} />
        <Toaster position="bottom-right" richColors closeButton duration={3500} />
      </SSEProvider>
    </ErrorBoundary>
  </StrictMode>
);
