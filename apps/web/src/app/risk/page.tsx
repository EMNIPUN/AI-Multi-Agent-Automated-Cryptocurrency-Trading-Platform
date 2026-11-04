import { EmptyState } from "@/components/shared/EmptyState";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";

export default function RiskPage() {
  return (
    <div>
      <PageHeader
        title="Risk"
        description="Daily loss, halt state, exposure, and blocked actions. Authoritative risk stays in local SQLite."
      />
      <DataModeBanner
        mode="unavailable"
        notes={["Private risk reads stay off until ownership is verified."]}
      />
      <EmptyState
        title="Risk snapshot unavailable"
        badge="Fail closed"
        description="No HALTED banner is invented. Durable halt state remains on the trading engine, not in the browser."
      />
    </div>
  );
}
