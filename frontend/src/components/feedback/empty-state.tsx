import type { ReactNode } from "react";
import { Inbox } from "lucide-react";

export function EmptyState({ title, description, icon }: { title: string; description: string; icon?: ReactNode }) {
  return (
    <div className="empty-state" role="status">
      <span className="empty-icon">{icon ?? <Inbox size={20} aria-hidden="true" />}</span>
      <p className="empty-title">{title}</p>
      <p className="empty-description">{description}</p>
    </div>
  );
}
