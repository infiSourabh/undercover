import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { queueClaim } from "./testFixtures";
import type { QueueRun } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  document.documentElement.removeAttribute("data-theme");
});

function renderApp(path = "/") {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function jsonResponse(data: unknown, status = 200): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      status,
      headers: { "Content-Type": "application/json" },
    }),
  );
}

const currentRun: QueueRun = {
  run_id: "run-1",
  max_claims: 5,
  summary: null,
  items: [
    { claim_id: "CLM-1001", status: "todo" },
    { claim_id: "CLM-1002", status: "left_for_handler" },
  ],
};

it("shows the queue with a waiting claim", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/runs/current")) return jsonResponse("missing", 404);
      return jsonResponse([queueClaim]);
    }),
  );
  renderApp("/");
  expect(await screen.findByText("CLM-1001")).toBeDefined();
  expect(screen.getByText("Maya Patel")).toBeDefined();
  expect(screen.getByText("Waiting")).toBeDefined();
  expect(screen.getByText(/Jun 24, 2026/)).toBeDefined();
  expect(screen.getByText("Not decided")).toBeDefined();
});

it("shows the to-do list for the current run", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/runs/current")) return jsonResponse(currentRun);
      return jsonResponse([queueClaim]);
    }),
  );
  renderApp("/");
  expect(await screen.findByText("To do")).toBeDefined();
  expect(screen.getByText("Left for a handler")).toBeDefined();
  expect(screen.getByText("Up to 5 claims")).toBeDefined();
  expect(screen.getAllByText("CLM-1001").length).toBeGreaterThan(0);
  expect(screen.getByText("CLM-1002")).toBeDefined();
});

it("shows no run yet when the queue has not started", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/runs/current")) return jsonResponse("missing", 404);
      return jsonResponse([]);
    }),
  );
  renderApp("/");
  expect(await screen.findByText("No run yet")).toBeDefined();
});

it("starts in dark mode and toggles to light", () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.includes("/runs/current")) return jsonResponse("missing", 404);
      return jsonResponse([]);
    }),
  );
  renderApp("/");
  expect(document.documentElement.getAttribute("data-theme")).toBe("dark");
  fireEvent.click(screen.getByRole("button", { name: "Light mode" }));
  expect(document.documentElement.getAttribute("data-theme")).toBe("light");
});
