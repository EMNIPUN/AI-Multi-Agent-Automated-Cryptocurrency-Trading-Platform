"use client";

import { createContext, useContext, type ReactNode } from "react";

import { usePolledResource, type PolledResource } from "@/hooks/use-polled-resource";
import { fetchExecutionState, type ExecutionState } from "@/lib/api/execution-state";

const Ctx = createContext<PolledResource<ExecutionState> | null>(null);

/**
 * One shared subscription for runtime execution facts (status bar, footer,
 * dashboard, system page). Mount once in the workspace shell so pages do not
 * each poll the same four endpoints.
 */
export function ExecutionStateProvider({
  children,
  intervalMs = 30_000,
  enabled = true,
}: {
  children: ReactNode;
  intervalMs?: number;
  enabled?: boolean;
}) {
  const resource = usePolledResource(fetchExecutionState, { intervalMs, enabled });
  return <Ctx.Provider value={resource}>{children}</Ctx.Provider>;
}

const FALLBACK: PolledResource<ExecutionState> = {
  data: null,
  error: null,
  loading: true,
  refreshing: false,
  updatedAt: null,
  refresh: async () => {},
};

export function useExecutionState(): PolledResource<ExecutionState> {
  return useContext(Ctx) ?? FALLBACK;
}
