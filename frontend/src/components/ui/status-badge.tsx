import { cn } from "@/lib/utils";

type Tone = "good" | "warn" | "danger" | "neutral" | "cyan";

export function StatusBadge({ label, tone = "neutral", title }: { label: string; tone?: Tone; title?: string }) {
  return (
    <span className={cn("status-badge", `status-${tone}`)} title={title}>
      <span aria-hidden="true" className="status-dot" />
      {label}
    </span>
  );
}
