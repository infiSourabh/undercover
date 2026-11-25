import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { claim1001, claim1002, handlers } from "./testFixtures";
import type { Claim } from "./types";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

function jsonResponse(data: unknown): Promise<Response> {
  return Promise.resolve(
    new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" },
    }),
  );
}

function urlOf(input: RequestInfo | URL): string {
  if (typeof input === "string") return input;
  if (input instanceof URL) return input.href;
  return input.url;
}

function renderClaim(claimId: string) {
  return render(
    <MemoryRouter initialEntries={[`/claims/${claimId}`]}>
      <App />
    </MemoryRouter>,
  );
}

it("shows the claim story, payout and activity in order", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/activity")) {
        return jsonResponse([
          { message: "Read the claim, the policy, and the claim history" },
          { message: "Read claims manual: 10. Meals without receipts" },
          { message: "Approved $420.00." },
        ]);
      }
      if (url.includes("/handlers")) return jsonResponse(handlers);
      return jsonResponse(claim1001);
    }),
  );
  renderClaim("CLM-1001");
  expect(await screen.findByText(/flight home from Rome/i)).toBeDefined();
  expect(screen.getAllByText("$420.00").length).toBeGreaterThan(0);
  expect(
    screen.getByText(
      "The delay is covered. The payout is the claimed expenses.",
    ),
  ).toBeDefined();
  const lines = [...document.querySelectorAll(".activity li")].map(
    (line) => line.textContent,
  );
  expect(lines[0]).toBe("Read the claim, the policy, and the claim history");
  expect(lines[1]).toBe("Read claims manual: 10. Meals without receipts");
  expect(lines[2]).toBe("Approved $420.00.");
  expect(screen.getByRole("heading", { name: "Agent at work" })).toBeDefined();
  expect(screen.getByText("Jun 24, 2026")).toBeDefined();
  expect(screen.getByText("3. Trip Delay")).toBeDefined();
});

it("shows an empty decision before the agent has worked", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL) => {
      const url = urlOf(input);
      if (url.endsWith("/activity")) return jsonResponse([]);
      if (url.includes("/handlers")) return jsonResponse(handlers);
      return jsonResponse({
        ...claim1001,
        status: "waiting",
        decision: null,
      });
    }),
  );
  renderClaim("CLM-1001");
  expect(await screen.findByText(/No decision yet/)).toBeDefined();
  expect(
    screen.getByText("The agent has not started this claim."),
  ).toBeDefined();
  expect(screen.getAllByText("Not decided").length).toBeGreaterThan(0);
  expect(screen.queryByText("3. Trip Delay")).toBeNull();
});

it("shows sign off on an over-limit claim and pay after sign-off", async () => {
  let current: Claim = claim1002;
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = urlOf(input);
      const method = init?.method ?? "GET";
      if (method === "POST" && url.includes("sign-off")) {
        current = {
          ...claim1002,
          sign_off: { handler_id: "HND-01", handler_name: "Dana Whitfield" },
        };
        return jsonResponse(current);
      }
      if (url.endsWith("/activity")) return jsonResponse([]);
      if (url.includes("/handlers")) return jsonResponse(handlers);
      return jsonResponse(current);
    }),
  );
  renderClaim("CLM-1002");
  expect(await screen.findByRole("button", { name: "Sign off" })).toBeDefined();
  expect(screen.queryByRole("button", { name: "Pay" })).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: "Sign off" }));
  expect(await screen.findByRole("button", { name: "Pay" })).toBeDefined();
});
