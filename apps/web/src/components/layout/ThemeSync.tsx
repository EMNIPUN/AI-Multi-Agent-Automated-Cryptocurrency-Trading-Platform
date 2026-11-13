"use client";

import { usePersistedDensity, usePersistedTheme } from "@/lib/theme";

/** Applies the stored theme on every route, including marketing and auth. */
export function ThemeSync() {
  usePersistedTheme();
  usePersistedDensity();
  return null;
}
