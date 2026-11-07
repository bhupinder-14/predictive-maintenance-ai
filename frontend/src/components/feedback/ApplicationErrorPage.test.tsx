import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, describe, expect, it } from "vitest";
import { ApplicationErrorPage } from "./ApplicationErrorPage";

function BrokenPage(): never {
  throw new Error("private stack path and secret");
}

function renderRouter(route: { path: string; element?: ReactNode; lazy?: () => Promise<never> }) {
  const router = createMemoryRouter([
    { path: "/", element: <h1>Overview recovered</h1> },
    { ...route, errorElement: <ApplicationErrorPage /> },
  ], { initialEntries: [route.path] });
  return render(<RouterProvider router={router} />);
}

describe("ApplicationErrorPage", () => {
  afterEach(() => cleanup());

  it("shows a branded safe fallback when a route component throws", async () => {
    renderRouter({ path: "/broken", element: <BrokenPage /> });
    expect(await screen.findByRole("heading", { name: "This view could not be displayed" })).toBeInTheDocument();
    expect(screen.queryByText(/private stack path and secret/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Reload application/ })).toBeInTheDocument();
  });

  it("catches a lazy route loading failure and provides navigation recovery", async () => {
    renderRouter({ path: "/lazy", lazy: async () => { throw new Error("chunk path secret"); } });
    expect(await screen.findByRole("heading", { name: "This view could not be displayed" })).toBeInTheDocument();
    expect(screen.queryByText(/chunk path secret/)).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("link", { name: "Return to Overview" }));
    expect(await screen.findByRole("heading", { name: "Overview recovered" })).toBeInTheDocument();
  });

  it("leaves a normal page unaffected", async () => {
    const router = createMemoryRouter([
      { path: "/", element: <h1>Normal page</h1>, errorElement: <ApplicationErrorPage /> },
    ], { initialEntries: ["/"] });
    render(<RouterProvider router={router} />);
    expect(await screen.findByRole("heading", { name: "Normal page" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "This view could not be displayed" })).not.toBeInTheDocument();
  });
});
