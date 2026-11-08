"use client";

import { useEffect, useState } from "react";

const KEY = "cryptonova.theme";

/** Persist light/dark preference across landing + app shell. */
export function usePersistedTheme() {
  const [light, setLight] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    try {
      setLight(localStorage.getItem(KEY) === "light");
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
      localStorage.setItem(KEY, light ? "light" : "dark");
    } catch {
      /* ignore */
    }
  }, [light, ready]);

  return { light, setLight, ready } as const;
}
