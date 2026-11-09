import { describe, expect, it } from "vitest";

import { commandChangesExecutionMode, isPaperSupervisorCommand } from "@/lib/orchestrator/commands";

describe("orchestrator commands", () => {
  it("allows only paper supervisor commands", () => {
    expect(isPaperSupervisorCommand("start")).toBe(true);
    expect(isPaperSupervisorCommand("halt")).toBe(true);
    expect(isPaperSupervisorCommand("live")).toBe(false);
  });

  it("does not let chat change the execution mode", () => {
    expect(commandChangesExecutionMode("start")).toBe(false);
    expect(commandChangesExecutionMode("halt")).toBe(false);
  });
});
