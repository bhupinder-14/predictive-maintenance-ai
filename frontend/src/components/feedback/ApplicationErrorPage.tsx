import { Link, useRouteError } from "react-router-dom";
import { ArrowLeft, RotateCw, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";

/** Safe router fallback for render and lazy-route failures. */
export function ApplicationErrorPage() {
  // Reading the router error ensures this is the route error boundary, but its
  // contents are deliberately never rendered or logged into the page.
  useRouteError();

  return (
    <main className="application-error-page" role="alert">
      <section className="application-error-card" aria-labelledby="application-error-title">
        <span className="application-error-icon"><TriangleAlert size={22} aria-hidden="true" /></span>
        <p className="panel-eyebrow">COMMAND CENTER RECOVERY</p>
        <h1 id="application-error-title">This view could not be displayed</h1>
        <p>Something unexpected interrupted this page. Reload the workspace or return to Overview to continue.</p>
        <div className="application-error-actions">
          <Button type="button" variant="secondary" onClick={() => window.location.reload()}>
            <RotateCw size={15} aria-hidden="true" /> Reload application
          </Button>
          <Link className="button button-ghost" to="/">
            <ArrowLeft size={15} aria-hidden="true" /> Return to Overview
          </Link>
        </div>
      </section>
    </main>
  );
}
