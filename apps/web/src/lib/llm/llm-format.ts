export const LLM_ADVISORY_LABEL = "LLM Advisory Only — Trading Decisions Unchanged";

export type LlmViewState =
  | "loading"
  | "disabled"
  | "missing_key"
  | "missing_model"
  | "budget_exhausted"
  | "error"
  | "empty"
  | "ready";

export function llmViewState(input: {
  loading: boolean;
  enabled: boolean;
  apiKeyConfigured: boolean;
  modelConfigured: boolean;
  error: boolean;
  budgetExhausted: boolean;
  count: number;
}): LlmViewState {
  if (input.loading) return "loading";
  if (input.error) return "error";
  if (!input.enabled) return "disabled";
  if (!input.apiKeyConfigured) return "missing_key";
  if (!input.modelConfigured) return "missing_model";
  if (input.budgetExhausted) return "budget_exhausted";
  if (input.count === 0) return "empty";
  return "ready";
}

export function llmStateCopy(state: LlmViewState): string {
  switch (state) {
    case "loading":
      return "Loading LLM advisory status";
    case "disabled":
      return "LLM decision support is off. No model calls are made.";
    case "missing_key":
      return "OPENAI_API_KEY is not configured. No model calls are made.";
    case "missing_model":
      return "CRYPTONOVA_LLM_MODEL is not configured. No model calls are made.";
    case "budget_exhausted":
      return "Daily LLM budget is exhausted. No further model calls are made.";
    case "error":
      return "LLM status could not be loaded. No demo evaluation is shown.";
    case "empty":
      return "No LLM evaluations are stored.";
    case "ready":
      return "Stored advisory evaluations. These are not verified profitable signals.";
    default:
      return LLM_ADVISORY_LABEL;
  }
}
