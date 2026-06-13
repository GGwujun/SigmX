import { Suspense, lazy, type ComponentType } from "react";
import { createBrowserRouter } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";

const Home = lazy(() => import("@/pages/Home").then((m) => ({ default: m.Home })));
const Agent = lazy(() => import("@/pages/Agent").then((m) => ({ default: m.Agent })));
const RunDetail = lazy(() =>
  import("@/pages/RunDetail").then((m) => ({ default: m.RunDetail })),
);
const Compare = lazy(() =>
  import("@/pages/Compare").then((m) => ({ default: m.Compare })),
);
const Settings = lazy(() =>
  import("@/pages/Settings").then((m) => ({ default: m.Settings })),
);
const Correlation = lazy(() =>
  import("@/pages/Correlation").then((m) => ({ default: m.Correlation })),
);
const AlphaZoo = lazy(() =>
  import("@/pages/AlphaZoo").then((m) => ({ default: m.AlphaZoo })),
);
const Events = lazy(() =>
  import("@/pages/Events").then((m) => ({ default: m.Events })),
);
const PositionDecision = lazy(() =>
  import("@/pages/PositionDecision").then((m) => ({ default: m.PositionDecision })),
);
const News = lazy(() =>
  import("@/pages/News").then((m) => ({ default: m.News })),
);
const Opportunity = lazy(() =>
  import("@/pages/Opportunity").then((m) => ({ default: m.Opportunity })),
);
const LogicChain = lazy(() =>
  import("@/pages/LogicChain").then((m) => ({ default: m.LogicChain })),
);
const AlphaForge = lazy(() =>
  import("@/pages/AlphaForge").then((m) => ({ default: m.AlphaForge })),
);

function PageLoader() {
  return (
    <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
      加载中…
    </div>
  );
}

function wrap(Component: ComponentType) {
  return (
    <Suspense fallback={<PageLoader />}>
      <Component />
    </Suspense>
  );
}

export const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: "/", element: wrap(Home) },
      { path: "/agent", element: wrap(Agent) },
      { path: "/settings", element: wrap(Settings) },
      { path: "/runs/:runId", element: wrap(RunDetail) },
      { path: "/compare", element: wrap(Compare) },
      { path: "/correlation", element: wrap(Correlation) },
      { path: "/alpha-zoo", element: wrap(AlphaZoo) },
      { path: "/alpha-zoo/bench", element: wrap(AlphaZoo) },
      { path: "/alpha-zoo/compare", element: wrap(AlphaZoo) },
      { path: "/alpha-zoo/:alphaId", element: wrap(AlphaZoo) },
      { path: "/events", element: wrap(Events) },
      { path: "/position-decision", element: wrap(PositionDecision) },
      { path: "/news", element: wrap(News) },
      { path: "/opportunity", element: wrap(Opportunity) },
      { path: "/logic-chain", element: wrap(LogicChain) },
      { path: "/alpha-forge", element: wrap(AlphaForge) },
    ],
  },
]);
