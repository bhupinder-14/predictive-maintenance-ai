import type { ReactNode } from "react";
import { StatusBadge } from "@/components/ui/status-badge";

export function PageHeader({ eyebrow, title, description, badge, actions }: {
  eyebrow: string;
  title: string;
  description: string;
  badge?: string;
  actions?: ReactNode;
}) {
  return (
    <div className="page-header">
      <div>
        <div className="page-eyebrow"><span className="eyebrow-rule" />{eyebrow}</div>
        <div className="page-title-row"><h1>{title}</h1>{badge && <StatusBadge label={badge} tone="cyan" />}</div>
        <p className="page-description">{description}</p>
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  );
}
