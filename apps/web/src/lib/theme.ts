"use client";

import { useEffect, useState } from "react";

const THEME_KEY = "cryptonova.theme.v2";
const DENSITY_KEY = "cryptonova.density.v1";

export type Density = "comfortable" | "compact";

/** Persist light/dark preference. Defaults to light (Bybit-style readability). */
export function usePersistedTheme() {
  const [light, setLight] = useState(true);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(THEME_KEY);
      setLight(stored !== "dark");
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    document.documentElement.classList.toggle("light", light);
    document.documentElement.classList.toggle("dark", !light);
    try {
      localStorage.setItem(THEME_KEY, light ? "light" : "dark");
    } catch {
      /* ignore */
    }
  }, [light, ready]);

  return { light, setLight, ready } as const;
}

/** Persist workspace density. Defaults to comfortable. */
export function usePersistedDensity() {
  const [density, setDensity] = useState<Density>("comfortable");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      const stored = localStorage.getItem(DENSITY_KEY);
      if (stored === "compact" || stored === "comfortable") setDensity(stored);
    } catch {
      /* ignore */
    }
    setReady(true);
  }, []);

  useEffect(() => {
    if (!ready) return;
    document.documentElement.dataset.density = density;
    try {
      localStorage.setItem(DENSITY_KEY, density);
    } catch {
      /* ignore */
    }
  }, [density, ready]);

  return { density, setDensity, ready } as const;
}
