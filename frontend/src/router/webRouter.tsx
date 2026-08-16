import { lazy } from "react";
import { Navigate, createBrowserRouter } from "react-router-dom";

import { AccountShell } from "@/components/portal/AccountShell";
import { RequireAdmin, RequireAuth, wrap } from "@/router/sharedGuards";

const PublicLayout = lazy(() => import("@/components/public/PublicLayout").then(m => ({ default: m.PublicLayout })));
const LandingPage = lazy(() => import("@/pages/public/LandingPage").then(m => ({ default: m.LandingPage })));
const PricingPage = lazy(() => import("@/pages/public/PricingPage").then(m => ({ default: m.PricingPage })));
const DataHubProductPage = lazy(() => import("@/pages/public/DataHubProductPage").then(m => ({ default: m.DataHubProductPage })));
const DesktopProductPage = lazy(() => import("@/pages/public/DesktopProductPage").then(m => ({ default: m.DesktopProductPage })));
const DownloadPage = lazy(() => import("@/pages/public/DownloadPage").then(m => ({ default: m.DownloadPage })));
const SampleReportPage = lazy(() => import("@/pages/public/SampleReportPage").then(m => ({ default: m.SampleReportPage })));
const PublicSearchPage = lazy(() => import("@/pages/public/PublicSearchPage").then(m => ({ default: m.PublicSearchPage })));
const PublicInstrumentPage = lazy(() => import("@/pages/public/PublicInstrumentPage").then(m => ({ default: m.PublicInstrumentPage })));
const PublicReportPage = lazy(() => import("@/pages/public/PublicReportPage").then(m => ({ default: m.PublicReportPage })));
const DataHubDocsPage = lazy(() => import("@/pages/public/DataHubDocsPage").then(m => ({ default: m.DataHubDocsPage })));
const LoginPage = lazy(() => import("@/pages/auth/LoginPage").then(m => ({ default: m.LoginPage })));
const RegisterPage = lazy(() => import("@/pages/auth/RegisterPage").then(m => ({ default: m.RegisterPage })));
const MePage = lazy(() => import("@/pages/portal/MePage").then(m => ({ default: m.MePage })));
const Account = lazy(() => import("@/pages/Account").then(m => ({ default: m.Account })));
const SubscriptionPage = lazy(() => import("@/pages/account/SubscriptionPage").then(m => ({ default: m.SubscriptionPage })));
const CreditsPage = lazy(() => import("@/pages/account/CreditsPage").then(m => ({ default: m.CreditsPage })));
const DevicesPage = lazy(() => import("@/pages/account/DevicesPage").then(m => ({ default: m.DevicesPage })));
const OrdersPage = lazy(() => import("@/pages/account/OrdersPage").then(m => ({ default: m.OrdersPage })));
const DataHubConsolePage = lazy(() => import("@/pages/account/DataHubConsolePage").then(m => ({ default: m.DataHubConsolePage })));
const CloudAccountPage = lazy(() => import("@/pages/account/CloudAccountPage").then(m => ({ default: m.CloudAccountPage })));
const OperationsPage = lazy(() => import("@/pages/admin/OperationsPage").then(m => ({ default: m.OperationsPage })));

export const webRouter = createBrowserRouter([
  { element: wrap(PublicLayout), children: [
    { path: "/", element: wrap(LandingPage) },
    { path: "/pricing", element: wrap(PricingPage) },
    { path: "/product/data-hub", element: wrap(DataHubProductPage) },
    { path: "/product/desktop", element: wrap(DesktopProductPage) },
    { path: "/download", element: wrap(DownloadPage) },
    { path: "/reports/sample/:slug", element: wrap(SampleReportPage) },
    { path: "/query/:id", element: wrap(PublicSearchPage) },
    { path: "/stock/:code", element: wrap(() => <PublicInstrumentPage kind="stock" />) },
    { path: "/fund/:code", element: wrap(() => <PublicInstrumentPage kind="fund" />) },
    { path: "/research/:slug", element: wrap(PublicReportPage) },
    { path: "/docs/data-hub/*", element: wrap(DataHubDocsPage) },
  ] },
  { path: "/login", element: wrap(LoginPage) },
  { path: "/register", element: wrap(RegisterPage) },
  { path: "/portal", element: <Navigate to="/me" replace /> },
  { element: <RequireAuth />, children: [
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
    { element: <RequireAdmin />, children: [{ path: "/admin/operations", element: wrap(OperationsPage) }] },
  ] },
  { path: "*", element: <Navigate to="/" replace /> },
]);
