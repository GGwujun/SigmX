import { lazy } from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { Layout } from "@/components/layout/Layout";
import { AccountShell } from "@/components/portal/AccountShell";
import { RequireAuth, wrap } from "@/router/sharedGuards";

const Home = lazy(() => import("@/pages/Home").then(m => ({ default: m.Home })));
const Agent = lazy(() => import("@/pages/Agent").then(m => ({ default: m.Agent })));
const MarketDashboard = lazy(() => import("@/pages/MarketDashboard").then(m => ({ default: m.MarketDashboard })));
const AlphaForge = lazy(() => import("@/pages/AlphaForge").then(m => ({ default: m.AlphaForge })));
const TrackingDashboard = lazy(() => import("@/pages/TrackingDashboard").then(m => ({ default: m.TrackingDashboard })));
const RunDetail = lazy(() => import("@/pages/RunDetail").then(m => ({ default: m.RunDetail })));
const HarnessRunsPage = lazy(() => import("@/pages/HarnessRunsPage").then(m => ({ default: m.HarnessRunsPage })));
const Settings = lazy(() => import("@/pages/Settings").then(m => ({ default: m.Settings })));
const BigScreen = lazy(() => import("@/pages/BigScreen"));
const MarketStage = lazy(() => import("@/pages/MarketStagePage").then(m => ({ default: m.MorningBrief })));
const Compare = lazy(() => import("@/pages/Compare").then(m => ({ default: m.Compare })));
const Correlation = lazy(() => import("@/pages/Correlation").then(m => ({ default: m.Correlation })));
const Events = lazy(() => import("@/pages/Events").then(m => ({ default: m.Events })));
const GlobalEvents = lazy(() => import("@/pages/GlobalEvents").then(m => ({ default: m.GlobalEvents })));
const WatchlistSchedule = lazy(() => import("@/pages/WatchlistSchedule").then(m => ({ default: m.WatchlistSchedule })));
const News = lazy(() => import("@/pages/News").then(m => ({ default: m.News })));
const RssFeed = lazy(() => import("@/pages/RssFeed").then(m => ({ default: m.RssFeed })));
const DailyRecommendations = lazy(() => import("@/pages/DailyRecommendations").then(m => ({ default: m.DailyRecommendations })));
const RecommendationHistory = lazy(() => import("@/pages/RecommendationHistory").then(m => ({ default: m.RecommendationHistory })));
const Opportunity = lazy(() => import("@/pages/Opportunity").then(m => ({ default: m.Opportunity })));
const LogicChain = lazy(() => import("@/pages/LogicChain").then(m => ({ default: m.LogicChain })));
const FundArbitrage = lazy(() => import("@/pages/FundArbitrage").then(m => ({ default: m.FundArbitrage })));
const FundOpportunity = lazy(() => import("@/pages/FundOpportunity").then(m => ({ default: m.FundOpportunity })));
const Signals = lazy(() => import("@/pages/Signals").then(m => ({ default: m.Signals })));
const RiskDashboard = lazy(() => import("@/pages/RiskDashboard"));
const LoginPage = lazy(() => import("@/pages/auth/LoginPage").then(m => ({ default: m.LoginPage })));
const MePage = lazy(() => import("@/pages/portal/MePage").then(m => ({ default: m.MePage })));
const Account = lazy(() => import("@/pages/Account").then(m => ({ default: m.Account })));
const SubscriptionPage = lazy(() => import("@/pages/account/SubscriptionPage").then(m => ({ default: m.SubscriptionPage })));
const CreditsPage = lazy(() => import("@/pages/account/CreditsPage").then(m => ({ default: m.CreditsPage })));
const DevicesPage = lazy(() => import("@/pages/account/DevicesPage").then(m => ({ default: m.DevicesPage })));
const OrdersPage = lazy(() => import("@/pages/account/OrdersPage").then(m => ({ default: m.OrdersPage })));
const DataHubConsolePage = lazy(() => import("@/pages/account/DataHubConsolePage").then(m => ({ default: m.DataHubConsolePage })));
const CloudAccountPage = lazy(() => import("@/pages/account/CloudAccountPage").then(m => ({ default: m.CloudAccountPage })));

function DesktopAssets() {
  return <div className="p-6"><h1 className="text-xl font-semibold">本地资产</h1><p className="mt-2 text-sm text-muted-foreground">管理本地数据集、研究文件、报告与缓存版本。</p></div>;
}

export const desktopRouter = createBrowserRouter([
  { path: "/login", element: wrap(LoginPage) },
  { element: <RequireAuth />, children: [
    { element: <Layout />, children: [
      { path: "/", element: <Navigate to="/app" replace /> },
      { path: "/app", element: wrap(Home) },
      { path: "/research", element: wrap(Agent) },
      { path: "/market", element: wrap(MarketDashboard) },
      { path: "/quant", element: wrap(AlphaForge) },
      { path: "/tracking", element: wrap(TrackingDashboard) },
      { path: "/runs", element: wrap(HarnessRunsPage) },
      { path: "/runs/:runId", element: wrap(RunDetail) },
      { path: "/assets", element: <DesktopAssets /> },
      { path: "/cloud", element: <Navigate to="/me" replace /> },
      { path: "/settings", element: wrap(Settings) },
      { path: "/market-dashboard", element: wrap(MarketDashboard) },
      { path: "/big-screen", element: wrap(BigScreen) },
      { path: "/morning-brief", element: wrap(MarketStage) },
      { path: "/agent", element: wrap(Agent) },
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
    ] },
    { element: <AccountShell />, children: [
      { path: "/me", element: wrap(MePage) },
      { path: "/account", element: wrap(Account) },
      { path: "/account/subscription", element: wrap(SubscriptionPage) },
      { path: "/account/credits", element: wrap(CreditsPage) },
      { path: "/account/devices", element: wrap(DevicesPage) },
      { path: "/account/orders", element: wrap(OrdersPage) },
      { path: "/account/data-hub", element: wrap(DataHubConsolePage) },
      { path: "/account/devices/authorize", element: wrap(CloudAccountPage) },
    ] },
  ] },
  { path: "*", element: <Navigate to="/app" replace /> },
]);
