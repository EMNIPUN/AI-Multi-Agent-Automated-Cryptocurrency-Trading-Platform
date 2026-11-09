import { redirect } from "next/navigation";

/** Overview removed — Orchestrator is the control center. */
export default function DashboardPage() {
  redirect("/orchestrator");
}
