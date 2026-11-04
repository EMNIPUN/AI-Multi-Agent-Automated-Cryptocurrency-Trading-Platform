import { EmptyState } from "@/components/shared/EmptyState";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";

export default function BacktestingPage() {
  return (
    <div>
      <PageHeader
        title="Backtesting"
        description="Historical strategy replay. No results are shown until a real backtest run exists."
      />
      <DataModeBanner
        mode="unavailable"
        notes={["Backtest engine is not connected.", "Win rate and equity curves are not invented here."]}
      />
      <EmptyState
        title="No backtest runs"
        badge="Coming soon"
        description="This page will list completed runs, sample size, and fee-aware results only after the engine writes them."
      />
    </div>
  );
}
