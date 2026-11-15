import { expect, test } from "@playwright/test";

const PROTECTED = ["/dashboard", "/orchestrator", "/markets", "/positions", "/autonomy", "/risk"];

test.describe("public surfaces", () => {
  test("marketing page renders without the workspace shell", async ({ page }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/CryptoNova/);
    await expect(page.getByRole("status", { name: "Global trading status" })).toHaveCount(0);
  });

  test("login form is usable and has no horizontal overflow at 390px", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto("/login");
    await expect(page.getByLabel("Email")).toBeVisible();
    await expect(page.getByLabel("Password")).toBeVisible();
    await expect(page.getByRole("button", { name: /sign in/i })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow).toBeLessThanOrEqual(0);
  });

  for (const route of PROTECTED) {
    test(`${route} redirects to /login when signed out`, async ({ page }) => {
      await page.goto(route);
      await expect(page).toHaveURL(new RegExp(`/login\\?next=${encodeURIComponent(route).replace(/%2F/g, "%2F")}`), { timeout: 20_000 });
    });
  }
});
