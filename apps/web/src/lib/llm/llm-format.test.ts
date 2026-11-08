import { describe, expect, it } from "vitest";

import { LLM_ADVISORY_LABEL, llmStateCopy, llmViewState } from "@/lib/llm/llm-format";
import { isAllowedPublicLlmGetPath, isLlmEvaluatePath } from "@/lib/security/public-llm-proxy";

describe("llm dashboard state", () => {
  it("keeps disabled, missing key, budget and empty distinct", () => {
    expect(LLM_ADVISORY_LABEL).toBe("LLM Advisory Only — Trading Decisions Unchanged");
    expect(
      llmViewState({
        loading: false,
        enabled: false,
        apiKeyConfigured: false,
        modelConfigured: false,
        error: false,
        budgetExhausted: false,
        count: 0,
      }),
    ).toBe("disabled");
    expect(
      llmViewState({
        loading: false,
        enabled: true,
        apiKeyConfigured: false,
        modelConfigured: true,
        error: false,
        budgetExhausted: false,
        count: 0,
      }),
    ).toBe("missing_key");
    expect(
      llmViewState({
        loading: false,
        enabled: true,
        apiKeyConfigured: true,
        modelConfigured: false,
        error: false,
        budgetExhausted: false,
        count: 0,
      }),
    ).toBe("missing_model");
    expect(
      llmViewState({
        loading: false,
        enabled: true,
        apiKeyConfigured: true,
        modelConfigured: true,
        error: false,
        budgetExhausted: true,
        count: 2,
      }),
    ).toBe("budget_exhausted");
    expect(
      llmViewState({
        loading: false,
        enabled: true,
        apiKeyConfigured: true,
        modelConfigured: true,
        error: false,
        budgetExhausted: false,
        count: 0,
      }),
    ).toBe("empty");
    expect(llmStateCopy("disabled")).toContain("off");
    expect(llmStateCopy("error")).toContain("No demo");
  });

  it("allows reads and does not treat evaluate as a browser GET", () => {
    expect(isAllowedPublicLlmGetPath("/api/v1/llm/status")).toBe(true);
    expect(isAllowedPublicLlmGetPath("/api/v1/llm/evaluations/lle_abc123")).toBe(true);
    expect(isAllowedPublicLlmGetPath("/api/v1/llm/evaluate")).toBe(false);
    expect(isLlmEvaluatePath("/api/v1/llm/evaluate")).toBe(true);
  });
});
