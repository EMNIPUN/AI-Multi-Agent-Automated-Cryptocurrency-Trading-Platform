import { WalletBalancePanel } from "@/components/WalletBalancePanel";
import { EmptyState } from "@/components/shared/EmptyState";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";

export default function PortfolioPage() {
  return (
    <div>
      <PageHeader
        title="Portfolio"
        description="Real Bybit balances via the server-side read adapter. Allocation stays empty until a secure multi-asset snapshot exists."
      />
      <DataModeBanner
        mode="fixture"
        notes={[
          "Wallet panel uses the live API only when FastAPI wallet reads are enabled.",
          "No fabricated allocation percentages.",
        ]}
      />
      <div className="mb-4">
        <WalletBalancePanel />
      </div>
      <EmptyState
        title="Allocation unavailable"
        badge="Not invented"
        description="Spot versus derivatives breakdown appears after owned account mapping. Nothing is estimated here."
      />
    </div>
  );
}
