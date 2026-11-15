import { defineConfig, devices } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

/**
 * CryptoNova browser verification.
 *
 * - `unauthenticated` project: public pages and auth-gated redirects; no account needed.
 * - `setup` + `authenticated` projects: sign in through the real /login form with an
 *   authorized local test account and store the session in `playwright/.auth/user.json`
 *   (gitignored). Credentials come from `CRYPTONOVA_E2E_EMAIL` / `CRYPTONOVA_E2E_PASSWORD`
 *   in the process env or in `apps/web/.env.e2e.local` (gitignored by `.env*.local`).
 *   Without them the authenticated project is skipped and reported as such.
 *
 * The suite never sends Orchestrator chat messages (OpenAI spend), never issues
 * supervisor commands, and never touches live approvals.
 */
function loadLocalEnv() {
  const file = path.join(__dirname, ".env.e2e.local");
  if (!fs.existsSync(file)) return;
  for (const raw of fs.readFileSync(file, "utf8").split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const eq = line.indexOf("=");
    if (eq <= 0) continue;
    const key = line.slice(0, eq).trim();
    const value = line.slice(eq + 1).trim().replace(/^["']|["']$/g, "");
    if (!(key in process.env)) process.env[key] = value;
  }
}
loadLocalEnv();

const BASE_URL = process.env.CRYPTONOVA_E2E_BASE_URL || "http://localhost:3000";
const HAS_CREDENTIALS = Boolean(process.env.CRYPTONOVA_E2E_EMAIL && process.env.CRYPTONOVA_E2E_PASSWORD);

export default defineConfig({
  testDir: "./e2e",
  outputDir: "./test-results",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 90_000,
  expect: { timeout: 10_000 },
  reporter: [["list"], ["html", { open: "never", outputFolder: "playwright-report" }]],
  use: {
    baseURL: BASE_URL,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
    video: "off",
    colorScheme: "dark",
  },
  projects: [
    {
      name: "unauthenticated",
      testMatch: /public\.spec\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "setup",
      testMatch: /auth\.setup\.ts/,
      use: { ...devices["Desktop Chrome"] },
    },
    {
      name: "authenticated",
      testMatch: /(workspaces|a11y)\.spec\.ts/,
      dependencies: HAS_CREDENTIALS ? ["setup"] : [],
      use: {
        ...devices["Desktop Chrome"],
        storageState: HAS_CREDENTIALS ? "playwright/.auth/user.json" : undefined,
      },
    },
  ],
});
