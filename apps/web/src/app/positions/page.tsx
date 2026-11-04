import { EmptyState } from "@/components/shared/EmptyState";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";

export default function PositionsPage() {
  return (
    <div>
      <PageHeader
        title="Positions & orders"
        description="Read-only positions, open orders, and fills. Cancel and place controls are not part of this UI."
      />
      <DataModeBanner
        mode="unavailable"
        notes={["Live position APIs stay gated.", "ACCEPTED does not mean FILLED."]}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <EmptyState
          title="No open positions"
          badge="Unavailable"
          description="A live snapshot is not connected. This panel will not invent exposure."
        />
        <EmptyState
          title="No open orders"
          badge="Unavailable"
          description="Order history and partial fills appear only from a verified read adapter."
        />
      </div>
    </div>
  );
}
