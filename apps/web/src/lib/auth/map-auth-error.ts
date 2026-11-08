/**
 * Map Supabase Auth errors to safe, user-facing copy. Never echo secrets.
 */

export function mapAuthError(error: { message?: string; status?: number } | null | undefined): string {
  const raw = (error?.message || "").toLowerCase();
  if (!raw) return "Authentication failed. Please try again.";

  if (raw.includes("invalid login") || raw.includes("invalid credentials")) {
    return "Email or password is incorrect.";
  }
  if (raw.includes("email not confirmed")) {
    return "Confirm your email before signing in. Check your inbox for the link.";
  }
  if (raw.includes("user already registered") || raw.includes("already been registered")) {
    return "An account with this email already exists. Sign in instead.";
  }
  if (raw.includes("password") && (raw.includes("weak") || raw.includes("least") || raw.includes("characters"))) {
    return "Password does not meet requirements (use at least 8 characters).";
  }
  if (raw.includes("rate") || raw.includes("too many")) {
    return "Too many attempts. Wait a moment and try again.";
  }
  if (raw.includes("network") || raw.includes("fetch")) {
    return "Network error. Check your connection and try again.";
  }
  if (raw.includes("signup is disabled")) {
    return "Sign-up is currently disabled for this project.";
  }
  // Generic — do not leak provider internals
  return "Authentication failed. Please try again.";
}
