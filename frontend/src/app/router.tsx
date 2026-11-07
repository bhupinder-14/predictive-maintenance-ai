import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppShell } from "@/components/layout/AppShell";
import { ApplicationErrorPage } from "@/components/feedback/ApplicationErrorPage";

function LoadingWorkspace() {
  return <div className="app-loading" role="status" aria-live="polite">Loading operations workspace…</div>;
}

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppShell />,
    HydrateFallback: LoadingWorkspace,
    errorElement: <ApplicationErrorPage />,
    children: [
      { index: true, lazy: async () => { const module = await import("@/pages/OverviewPage"); return { Component: module.OverviewPage }; } },
      { path: "equipment", lazy: async () => { const module = await import("@/pages/EquipmentPage"); return { Component: module.EquipmentPage }; } },
      { path: "equipment/:equipmentId", lazy: async () => { const module = await import("@/pages/EquipmentProfilePage"); return { Component: module.EquipmentProfilePage }; } },
      { path: "prediction-lab", lazy: async () => { const module = await import("@/pages/PredictionLabPage"); return { Component: module.PredictionLabPage }; } },
      { path: "prediction-history", lazy: async () => { const module = await import("@/pages/PredictionHistoryPage"); return { Component: module.PredictionHistoryPage }; } },
      { path: "drift", lazy: async () => { const module = await import("@/pages/DriftMonitoringPage"); return { Component: module.DriftMonitoringPage }; } },
      { path: "system", lazy: async () => { const module = await import("@/pages/SystemHealthPage"); return { Component: module.SystemHealthPage }; } },
      { path: "*", element: <Navigate to="/" replace /> },
    ],
  },
], {
  future: { v7_relativeSplatPath: true },
});
