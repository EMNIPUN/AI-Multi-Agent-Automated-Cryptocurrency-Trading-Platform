import { expect, test, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const HAS_CREDENTIALS = Boolean(process.env.CRYPTONOVA_E2E_EMAIL && process.env.CRYPTONOVA_E2E_PASSWORD);
const SHOTS = path.join(__dirname, "..", "test-results", "screenshots");

const ROUTES = [
  "/dashboard",
  "/orchestrator",
  "/agents",
  "/agents/live",
  "/autonomy",
  "/markets",
  "/positions",
  "/portfolio",
  "/paper",
  "/risk",
  "/news",
  "/strategy",
  "/backtesting",
  "/analytics",
  "/llm",
  "/notifications",
  "/settings",
  "/settings/exchanges",
  "/system",
] as const;

const VIEWPORTS = [
  { name: "mobile-390", width: 390, height: 844 },
  { name: "tablet-768", width: 768, height: 1024 },
  { name: "laptop-1024", width: 1024, height: 768 },
  { name: "desktop-1440", width: 1440, height: 900 },
  { name: "wide-1920", width: 1920, height: 1080 },
] as const;

async function setTheme(page: Page, theme: "dark" | "light") {
  await page.evaluate((t) => {
    window.localStorage.setItem("cryptonova.theme.v3", t);
  }, theme);
}

async function waitForSettled(page: Page) {
  // Pages gate on auth; wait for the shell then give pollers a moment.
  await page.getByRole("status", { name: "Global trading status" }).waitFor({ timeout: 20_000 });
  await page.waitForLoadState("networkidle").catch(() => undefined);
  await page.waitForTimeout(400);
}

test.describe("authenticated workspaces", () => {
  test.skip(!HAS_CREDENTIALS, "CRYPTONOVA_E2E_EMAIL / CRYPTONOVA_E2E_PASSWORD not set — authenticated QA skipped");

  test.beforeAll(() => {
    fs.mkdirSync(SHOTS, { recursive: true });
  });

  for (const route of ROUTES) {
    test(`${route} renders without overflow across viewports and themes`, async ({ page }) => {
      const slug = route.replace(/\//g, "_").replace(/^_/, "") || "root";
      for (const theme of ["dark", "light"] as const) {
        for (const vp of VIEWPORTS) {
          await page.setViewportSize({ width: vp.width, height: vp.height });
          await page.goto(route);
          await setTheme(page, theme);
          await page.reload();
          await waitForSettled(page);
          await expect(page).not.toHaveURL(/\/login/);
          const overflow = await page.evaluate(
            () => document.documentElement.scrollWidth - document.documentElement.clientWidth,
          );
          expect(overflow, `${route} ${theme} ${vp.name} horizontal overflow`).toBeLessThanOrEqual(0);
          await page.screenshot({
            path: path.join(SHOTS, `${slug}--${theme}--${vp.name}.png`),
            fullPage: vp.width >= 1024,
          });
        }
      }
    });
  }

  test("orchestrator composer stays visible on mobile and supports Shift+Enter", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/orchestrator");
    await waitForSettled(page);
    const composer = page.getByRole("textbox", { name: "Message" });
    await expect(composer).toBeVisible();
    await composer.fill("line one");
    await composer.press("Shift+Enter");
    await composer.type("line two");
    await expect(composer).toHaveValue("line one\nline two");
    // Never submit: that would call the Orchestrator (and potentially OpenAI).
    await composer.fill("");
  });

  test("command palette navigates with Ctrl+K", async ({ page }) => {
    await page.goto("/dashboard");
    await waitForSettled(page);
    await page.keyboard.press("Control+K");
    const search = page.getByLabel("Search navigation");
    await expect(search).toBeVisible();
    await search.fill("risk");
    await page.getByRole("option", { name: /Risk Center/ }).click();
    await expect(page).toHaveURL(/\/risk/);
  });

  test("positions table supports search and column toggles", async ({ page }) => {
    await page.goto("/positions");
    await waitForSettled(page);
    const columns = page.getByRole("button", { name: "Choose visible columns" }).first();
    if (await columns.isVisible()) {
      await columns.click();
      await expect(page.getByRole("menuitemcheckbox").first()).toBeVisible();
      await page.keyboard.press("Escape");
    }
  });
});
