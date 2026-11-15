// Production build into its own output directory so a running `next dev`
// (which owns `.next`) cannot corrupt page-data collection. See next.config.ts.
import { spawnSync } from "node:child_process";

const distDir = process.env.NEXT_DIST_DIR || ".next-build";
const result = spawnSync(process.platform === "win32" ? "npx.cmd" : "npx", ["next", "build"], {
  stdio: "inherit",
  env: { ...process.env, NEXT_DIST_DIR: distDir },
  shell: process.platform === "win32",
});
process.exit(result.status ?? 1);
