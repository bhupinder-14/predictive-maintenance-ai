import { Activity, CircleAlert, CircleOff, LoaderCircle } from "lucide-react";
import { useBackendStatus } from "@/hooks/useBackendStatus";
import { StatusBadge } from "@/components/ui/status-badge";

export function ConnectionIndicator() {
  const state = useBackendStatus();
  if (state.kind === "checking") return <StatusBadge label="Checking API" tone="neutral" />;
  if (state.kind === "unreachable") return <StatusBadge label="API unreachable" tone="danger" title={state.error?.message} />;
  if (state.kind === "readiness-error") return <StatusBadge label="Readiness check failed" tone="danger" title={state.error.message} />;
  if (state.kind === "not-ready") return <StatusBadge label="API reachable · not ready" tone="warn" />;
  return <StatusBadge label="System operational" tone="good" />;
}

export function ConnectionIcon({ kind }: { kind: "checking" | "ready" | "not-ready" | "readiness-error" | "unreachable" }) {
  const Icon = kind === "checking" ? LoaderCircle : kind === "ready" ? Activity : kind === "not-ready" || kind === "readiness-error" ? CircleAlert : CircleOff;
  return <Icon size={16} aria-hidden="true" className={kind === "checking" ? "animate-spin" : undefined} />;
}
