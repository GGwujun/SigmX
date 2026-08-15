import { Suspense, lazy, type ComponentType } from "react";
import { Navigate, Outlet, createBrowserRouter } from "react-router-dom";
import { Layout } from "@/components/layout/Layout";
import { AccountShell } from "@/components/portal/AccountShell";
import { DisclaimerModal } from "@/components/DisclaimerModal";
import { isAdmin } from "@/lib/apiAuth";
import { isDesktopMode } from "@/lib/desktop";
import { useAuthState } from "@/hooks/useAuthState";

const Home = lazy(() => import("@/pages/Home").then((m) => ({ default: m.Home })));
const MarketDashboard = lazy(() =>
  import("@/pages/MarketDashboard").then((m) => ({ default: m.MarketDashboard })),
);
const MorningBrief = lazy(() =>
  import("@/pages/MarketStagePage").then((m) => ({ default: m.MorningBrief })),
);
const IntradayMonitor = lazy(() =>
  import("@/pages/MarketStagePage").then((m) => ({ default: m.IntradayMonitor })),
);
const TailStrategy = lazy(() =>
  import("@/pages/MarketStagePage").then((m) => ({ default: m.TailStrategy })),
);
const CloseReview = lazy(() =>
  import("@/pages/MarketStagePage").then((m) => ({ default: m.CloseReview })),
);
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
const GlobalEvents = lazy(() =>
  import("@/pages/GlobalEvents").then((m) => ({ default: m.GlobalEvents })),
);
const TrackingDashboard = lazy(() =>
  import("@/pages/TrackingDashboard").then((m) => ({ default: m.TrackingDashboard })),
);
const WatchlistSchedule = lazy(() =>
  import("@/pages/WatchlistSchedule").then((m) => ({ default: m.WatchlistSchedule })),
);
const News = lazy(() =>
  import("@/pages/News").then((m) => ({ default: m.News })),
);
const RssFeed = lazy(() =>
  import("@/pages/RssFeed").then((m) => ({ default: m.RssFeed })),
);
const Opportunity = lazy(() =>
  import("@/pages/Opportunity").then((m) => ({ default: m.Opportunity })),
);
const LogicChain = lazy(() =>
  import("@/pages/LogicChain").then((m) => ({ default: m.LogicChain })),
);
const DailyRecommendations = lazy(() =>
  import("@/pages/DailyRecommendations").then((m) => ({ default: m.DailyRecommendations })),
);
const RecommendationHistory = lazy(() =>
  import("@/pages/RecommendationHistory").then((m) => ({ default: m.RecommendationHistory })),
);
const AlphaForge = lazy(() =>
  import("@/pages/AlphaForge").then((m) => ({ default: m.AlphaForge })),
);
const FundArbitrage = lazy(() =>
  import("@/pages/FundArbitrage").then((m) => ({ default: m.FundArbitrage })),
);
const FundOpportunity = lazy(() =>
  import("@/pages/FundOpportunity").then((m) => ({ default: m.FundOpportunity })),
);
const Signals = lazy(() =>
  import("@/pages/Signals").then((m) => ({ default: m.Signals })),
);
const LoginPage = lazy(() =>
  import("@/pages/auth/LoginPage").then((m) => ({ default: m.LoginPage })),
);
const RegisterPage = lazy(() =>
  import("@/pages/auth/RegisterPage").then((m) => ({ default: m.RegisterPage })),
);
const PricingPage = lazy(() =>
  import("@/pages/public/PricingPage").then((m) => ({ default: m.PricingPage })),
);
const LandingPage = lazy(() =>
  import("@/pages/public/LandingPage").then((m) => ({ default: m.LandingPage })),
);
const PublicLayout = lazy(() =>
  import("@/components/public/PublicLayout").then((m) => ({ default: m.PublicLayout })),
);
const DataHubProductPage = lazy(() =>
  import("@/pages/public/DataHubProductPage").then((m) => ({ default: m.DataHubProductPage })),
);
const DesktopProductPage = lazy(() =>
  import("@/pages/public/DesktopProductPage").then((m) => ({ default: m.DesktopProductPage })),
);
const DownloadPage = lazy(() =>
  import("@/pages/public/DownloadPage").then((m) => ({ default: m.DownloadPage })),
);
const SampleReportPage = lazy(() =>
  import("@/pages/public/SampleReportPage").then((m) => ({ default: m.SampleReportPage })),
);
const OperationsPage = lazy(() =>
  import("@/pages/admin/OperationsPage").then((m) => ({ default: m.OperationsPage })),
);
const OrdersPage = lazy(() =>
  import("@/pages/account/OrdersPage").then((m) => ({ default: m.OrdersPage })),
);
const DataHubConsolePage = lazy(() =>
  import("@/pages/account/DataHubConsolePage").then((m) => ({ default: m.DataHubConsolePage })),
);
const CloudAccountPage = lazy(() =>
  import("@/pages/account/CloudAccountPage").then((m) => ({ default: m.CloudAccountPage })),
);
const SubscriptionPage = lazy(() =>
  import("@/pages/account/SubscriptionPage").then((m) => ({ default: m.SubscriptionPage })),
);
const CreditsPage = lazy(() =>
  import("@/pages/account/CreditsPage").then((m) => ({ default: m.CreditsPage })),
);
const DevicesPage = lazy(() =>
  import("@/pages/account/DevicesPage").then((m) => ({ default: m.DevicesPage })),
);
const Account = lazy(() =>
  import("@/pages/Account").then((m) => ({ default: m.Account })),
);
const MePage = lazy(() =>
  import("@/pages/portal/MePage").then((m) => ({ default: m.MePage })),
);
const RedeemCodes = lazy(() =>
  import("@/pages/RedeemCodes").then((m) => ({ default: m.RedeemCodes })),
);
const BigScreen = lazy(() =>
  import("@/pages/BigScreen").then((m) => ({ default: m.default })),
);
const RiskDashboard = lazy(() =>
  import("@/pages/RiskDashboard").then((m) => ({ default: m.default })),
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

/**
 * Auth guard. Validates a token exists (and refreshes the user via /auth/me).
 * If not logged in → redirect to /login. If logged in but disclaimer not yet
 * accepted → render the app behind a blocking DisclaimerModal.
 */
function RequireAuth() {
  const { authed, disclaimerAccepted, recheck, loading } = useAuthState();

  if (loading) {
    return (
      <div className="flex h-[60vh] items-center justify-center text-muted-foreground">
        加载中…
      </div>
    );
  }
  if (!authed) {
    return <Navigate to="/login" replace />;
  }
  return (
    <>
      <Outlet />
      {!disclaimerAccepted && <DisclaimerModal onAccepted={recheck} />}
    </>
  );
}

/** Admin guard. Non-admins are bounced to home. */
function RequireAdmin() {
  if (!isAdmin()) {
    return <Navigate to="/" replace />;
  }
  return <Outlet />;
}

/**
 * Desktop-only guard: the heavy workbench relies on local agent/LLM backends
 * that the web deployment doesn't run — browsers are bounced to the portal.
 */
export function DesktopOnly() {
  if (!isDesktopMode()) {
    return <Navigate to="/me" replace />;
  }
  return <Outlet />;
}

export const router = createBrowserRouter([
  // Public acquisition site — no auth guard, shared PublicLayout shell.
  {
    element: wrap(PublicLayout),
    children: [
      { path: "/", element: wrap(LandingPage) },
      { path: "/pricing", element: wrap(PricingPage) },
      { path: "/product/data-hub", element: wrap(DataHubProductPage) },
      { path: "/product/desktop", element: wrap(DesktopProductPage) },
      { path: "/download", element: wrap(DownloadPage) },
      { path: "/reports/sample/:slug", element: wrap(SampleReportPage) },
    ],
  },
  // Public auth routes — own minimal layout (no PublicLayout chrome).
  { path: "/login", element: wrap(LoginPage) },
  { path: "/register", element: wrap(RegisterPage) },
  // Light portal alias — browsers land here after login, then on to /account.
  { path: "/portal", element: <Navigate to="/me" replace /> },
  // Protected app
  {
    element: <RequireAuth />,
    children: [
      // Desktop workbench — heavy pages rely on local agent/LLM backends.
      {
        element: <DesktopOnly />,
        children: [
          {
            element: <Layout />,
            children: [
              { path: "/app", element: wrap(Home) },
              { path: "/market-dashboard", element: wrap(MarketDashboard) },
              { path: "/big-screen", element: wrap(BigScreen) },
              { path: "/morning-brief", element: wrap(MorningBrief) },
              { path: "/intraday-monitor", element: wrap(IntradayMonitor) },
              { path: "/tail-strategy", element: wrap(TailStrategy) },
              { path: "/close-review", element: wrap(CloseReview) },
              { path: "/agent", element: wrap(Agent) },
              { path: "/settings", element: wrap(Settings) },
              { path: "/runs/:runId", element: wrap(RunDetail) },
              { path: "/compare", element: wrap(Compare) },
              { path: "/correlation", element: wrap(Correlation) },
              { path: "/events", element: wrap(Events) },
              { path: "/global-events", element: wrap(GlobalEvents) },
              { path: "/tracking-dashboard", element: wrap(TrackingDashboard) },
              { path: "/watchlist-schedule", element: wrap(WatchlistSchedule) },
              { path: "/news", element: wrap(News) },
              { path: "/rss-feed", element: wrap(RssFeed) },
              { path: "/daily-recommendations", element: wrap(DailyRecommendations) },
              { path: "/recommendation-history", element: wrap(RecommendationHistory) },
              { path: "/opportunity", element: wrap(Opportunity) },
              { path: "/logic-chain", element: wrap(LogicChain) },
              { path: "/alpha-forge", element: wrap(AlphaForge) },
              { path: "/fund-arbitrage", element: wrap(FundArbitrage) },
              { path: "/fund-opportunity", element: wrap(FundOpportunity) },
              { path: "/signals", element: wrap(Signals) },
              { path: "/risk-dashboard", element: wrap(RiskDashboard) },
            ],
          },
        ],
      },
      // Shared account area — desktop keeps the workbench shell, browsers get
      // the light portal shell.
      {
        element: <AccountShell />,
        children: [
          { path: "/me", element: wrap(MePage) },
          { path: "/account", element: wrap(Account) },
          { path: "/account/subscription", element: wrap(SubscriptionPage) },
          { path: "/account/credits", element: wrap(CreditsPage) },
          { path: "/account/devices", element: wrap(DevicesPage) },
          { path: "/account/orders", element: wrap(OrdersPage) },
          { path: "/account/data-hub", element: wrap(DataHubConsolePage) },
          { path: "/account/devices/authorize", element: wrap(CloudAccountPage) },
        ],
      },
      // Admin-only routes (Factor Zoo) — wrapped in RequireAdmin.
      {
        element: <RequireAdmin />,
        children: [
          {
            element: <Layout />,
            children: [
              { path: "/alpha-zoo", element: wrap(AlphaZoo) },
              { path: "/alpha-zoo/bench", element: wrap(AlphaZoo) },
              { path: "/alpha-zoo/compare", element: wrap(AlphaZoo) },
              { path: "/alpha-zoo/:alphaId", element: wrap(AlphaZoo) },
              { path: "/redeem-codes", element: wrap(RedeemCodes) },
              { path: "/admin/operations", element: wrap(OperationsPage) },
            ],
          },
        ],
      },
    ],
  },
]);
