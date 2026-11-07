import type { ReactNode } from "react";

export function Tooltip({ content, children }: { content: string; children: ReactNode }) {
  return (
    <span className="tooltip-wrap" tabIndex={0} aria-label={content}>
      {children}
      <span className="tooltip-content" role="tooltip">{content}</span>
    </span>
  );
}
