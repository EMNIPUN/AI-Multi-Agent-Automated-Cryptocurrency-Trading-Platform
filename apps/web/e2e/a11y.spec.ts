import AxeBuilder from "@axe-core/playwright";
import { expect, test } from "@playwright/test";

const HAS_CREDENTIALS = Boolean(process.env.CRYPTONOVA_E2E_EMAIL && process.env.CRYPTONOVA_E2E_PASSWORD);

const ROUTES = ["/dashboard", "/orchestrator", "/agents", "/autonomy", "/markets", "/positions", "/paper", "/risk", "/backtesting", "/analytics"];

test.describe("accessibility (axe, WCAG 2.x A/AA)", () => {
  test("login page has no serious/critical violations", async ({ page }) => {
    await page.goto("/login");
    await page.getByLabel("Email").waitFor();
    const results = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"]).analyze();
    const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
    expect(serious, JSON.stringify(serious.map((v) => ({ id: v.id, nodes: v.nodes.length })), null, 2)).toEqual([]);
  });

  test.describe("authenticated routes", () => {
    test.skip(!HAS_CREDENTIALS, "CRYPTONOVA_E2E_EMAIL / CRYPTONOVA_E2E_PASSWORD not set");
    for (const route of ROUTES) {
      test(`${route} has no serious/critical violations`, async ({ page }) => {
        await page.goto(route);
        await page.getByRole("status", { name: "Global trading status" }).waitFor({ timeout: 20_000 });
        await page.waitForLoadState("networkidle").catch(() => undefined);
        const results = await new AxeBuilder({ page })
          .withTags(["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa"])
          .exclude(".react-flow") // third-party canvas; inspected manually
          .analyze();
        const serious = results.violations.filter((v) => v.impact === "serious" || v.impact === "critical");
        expect(serious, JSON.stringify(serious.map((v) => ({ id: v.id, help: v.help, nodes: v.nodes.slice(0, 3).map((n) => n.target) })), null, 2)).toEqual([]);
      });
    }
  });
});
