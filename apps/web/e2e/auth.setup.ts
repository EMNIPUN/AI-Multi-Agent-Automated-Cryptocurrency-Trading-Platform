import { expect, test as setup } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const AUTH_FILE = path.join(__dirname, "..", "playwright", ".auth", "user.json");

/**
 * Signs in through the real /login form with an authorized local test account
 * and stores the browser session. Credentials come only from env; nothing is
 * written to the repo except the gitignored storage state.
 */
setup("authenticate with the local test account", async ({ page }) => {
  const email = process.env.CRYPTONOVA_E2E_EMAIL;
  const password = process.env.CRYPTONOVA_E2E_PASSWORD;
  setup.skip(!email || !password, "CRYPTONOVA_E2E_EMAIL / CRYPTONOVA_E2E_PASSWORD not set");

  await page.goto("/login");
  await page.getByLabel("Email").fill(email!);
  await page.getByLabel("Password").fill(password!);
  await page.getByRole("button", { name: /sign in/i }).click();
  await expect(page).toHaveURL(/\/(orchestrator|dashboard)/, { timeout: 30_000 });
  await expect(page.getByRole("status", { name: "Global trading status" })).toBeVisible();

  fs.mkdirSync(path.dirname(AUTH_FILE), { recursive: true });
  await page.context().storageState({ path: AUTH_FILE });
});
