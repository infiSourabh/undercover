import { cleanup, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router";
import { afterEach, expect, it, vi } from "vitest";
import { App } from "./App";
import { claimInstructions, queueInstructions } from "./testFixtures";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});

it("shows the instructions with no text field", async () => {
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          queue: queueInstructions,
          claim: claimInstructions,
        }),
        {
          headers: { "Content-Type": "application/json" },
        },
      ),
    ),
  );
  render(
    <MemoryRouter initialEntries={["/instructions"]}>
      <App />
    </MemoryRouter>,
  );
  expect(
    await screen.findByRole("heading", { name: "Running the queue" }),
  ).toBeDefined();
  expect(
    screen.getByRole("heading", { name: "Working a claim" }),
  ).toBeDefined();
  expect(screen.getByText(/at most \{cap\} claims/)).toBeDefined();
  expect(
    screen.getByText(/Read a section before you rely on it/),
  ).toBeDefined();
  expect(screen.queryByRole("textbox")).toBeNull();
});
