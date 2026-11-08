/** Client types for exchange binding management (no secrets). */

export type ExchangeBindingPublic = {
  id: string;
  provider: string;
  environment: string;
  status: string;
  display_label: string;
  credential_ref_alias: string;
  last_verified_at: string | null;
  created_at: string;
  updated_at: string;
  persistence: string;
  is_live_exchange_connection: boolean;
  activation_blocked_reason: string | null;
  verification_status?: string;
  verification_simulated?: boolean;
  verification_message?: string | null;
  exchange_account_fingerprint?: string | null;
};

export type ExchangeBindingListResponse = {
  items: ExchangeBindingPublic[];
  private_data_reads_enabled: boolean;
  binding_persistence_enabled: boolean;
  auth_e2e_verified: boolean;
  mainnet_activation_locked: boolean;
};

export function statusBadgeVariant(
  status: string,
): "secondary" | "success" | "warning" | "danger" | "outline" {
  switch (status) {
    case "active":
      return "success";
    case "pending":
      return "warning";
    case "revoked":
      return "outline";
    case "error":
      return "danger";
    default:
      return "secondary";
  }
}
