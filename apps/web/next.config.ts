import type { NextConfig } from "next";

/**
 * `NEXT_DIST_DIR` lets a production build write to its own output directory
 * (e.g. `.next-build`) while `next dev` is still serving from `.next`.
 * Both processes writing to `.next` at once corrupts page-data collection.
 */
const distDir = process.env.NEXT_DIST_DIR?.trim() || ".next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  distDir,
};

export default nextConfig;
