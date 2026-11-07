import { AlertTriangle, RotateCw } from "lucide-react";
import { Button } from "@/components/ui/button";

export function ErrorState({ title, description, onRetry }: { title: string; description: string; onRetry?: () => void }) {
  return (
    <div className="error-state" role="alert">
      <AlertTriangle size={20} aria-hidden="true" />
      <div>
        <p className="empty-title">{title}</p>
        <p className="empty-description">{description}</p>
      </div>
      {onRetry && <Button onClick={onRetry}><RotateCw size={15} />Retry</Button>}
    </div>
  );
}
