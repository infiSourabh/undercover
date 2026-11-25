import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { join } from "node:path";
import { expect, test } from "@playwright/test";

function venvPython(): string {
  const win = join(process.cwd(), ".venv", "Scripts", "python.exe");
  const unix = join(process.cwd(), ".venv", "bin", "python");
  return existsSync(win) ? win : unix;
}

const APPROVE_1001 = {
  outcome: "approve",
  payout: 420,
  explanation: "The delay is covered. The payout is the claimed expenses.",
  policy_section: "3. Trip Delay",
};

const APPROVE_1002 = {
  outcome: "approve",
  payout: 1150,
  explanation: "Approved over the handler limit.",
  policy_section: "5. Baggage and Personal Effects",
};

test.describe.configure({ mode: "serial" });

test.beforeAll(() => {
  execFileSync(venvPython(), ["-m", "backend.seed"], { stdio: "inherit" });
});

test("the queue shows 25 waiting claims", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("a.claim-id")).toHaveCount(25);
  await expect(page.getByRole("link", { name: "CLM-1001" })).toBeVisible();
  await expect(page.getByText("Waiting").first()).toBeVisible();
});

test("a claim shows the story and no decision section yet", async ({
  page,
}) => {
  await page.goto("/claims/CLM-1001");
  await expect(page.getByText("Maya Patel").first()).toBeVisible();
  await expect(page.getByText(/canceled by Meridian Air/)).toBeVisible();
  await expect(page.getByText("3. Trip Delay")).toHaveCount(0);
});

test("paying an under-limit approval marks the claim decided", async ({
  page,
  request,
}) => {
  await request.post("/api/claims/CLM-1001/decision", { data: APPROVE_1001 });
  await page.goto("/claims/CLM-1001");
  await expect(
    page.getByText("The delay is covered. The payout is the claimed expenses."),
  ).toBeVisible();
  await expect(page.getByText("3. Trip Delay")).toBeVisible();
  await expect(page.getByText("$420.00").first()).toBeVisible();
  await page.getByRole("button", { name: "Pay" }).click();
  await expect(page.getByText("Decided")).toBeVisible();
});

test("an over-limit payout waits for sign-off then pays", async ({
  page,
  request,
}) => {
  await request.post("/api/claims/CLM-1002/decision", { data: APPROVE_1002 });
  await page.goto("/claims/CLM-1002");
  await expect(page.getByRole("button", { name: "Pay" })).toHaveCount(0);
  await page.getByLabel("Handler").selectOption({ label: "Dana Whitfield" });
  await page.getByRole("button", { name: "Sign off" }).click();
  await page.getByRole("button", { name: "Pay" }).click();
  await expect(page.getByText("Decided")).toBeVisible();
  await expect(page.getByText("$1,150.00").first()).toBeVisible();
});

test("the queue shows the to-do list for the current run", async ({
  page,
  request,
}) => {
  const created = await request.post("/api/runs", { data: { max_claims: 5 } });
  const run = (await created.json()) as { run_id: string };
  await request.put(`/api/runs/${run.run_id}/todos`, {
    data: {
      items: [
        { claim_id: "CLM-1001", status: "done" },
        { claim_id: "CLM-1002", status: "left_for_handler" },
      ],
    },
  });
  await page.goto("/");
  const list = page.locator(".run-list");
  await expect(list).toContainText("CLM-1001");
  await expect(list).toContainText("Done");
  await expect(list).toContainText("CLM-1002");
  await expect(list).toContainText("Left for a handler");
});

test("a claim shows the section the agent read", async ({ page, request }) => {
  await request.post("/api/claims/CLM-1003/activity", {
    data: { message: "Read policy wording: 3. Trip Delay" },
  });
  await page.goto("/claims/CLM-1003");
  await expect(
    page.getByText("Read policy wording: 3. Trip Delay"),
  ).toBeVisible();
});

test("instructions are read-only", async ({ page }) => {
  await page.goto("/instructions");
  await expect(
    page.getByRole("heading", { name: "Running the queue" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Working a claim" }),
  ).toBeVisible();
  await expect(page.getByRole("textbox")).toHaveCount(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "Working a claim" }),
  ).toBeVisible();
});

test("dark mode is the default", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("button", { name: "Light mode" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
});
