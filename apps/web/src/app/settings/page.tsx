import { EmptyState } from "@/components/shared/EmptyState";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

export default function SettingsPage() {
  return (
    <div>
      <PageHeader
        title="Settings"
        description="Profile, session, and connection health. Supabase Auth is scaffolded only."
      />
      <DataModeBanner
        mode="demo"
        notes={["No secrets in the client bundle.", "Private catalog reads remain gated."]}
      />
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Session</CardTitle>
            <CardDescription>Sign-in uses the public anon key only</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            <Badge variant="outline">Unauthenticated scaffold</Badge>
            <EmptyState
              title="No active session"
              badge="Auth"
              description="Connect Supabase Auth before this menu can show a real operator profile."
            />
          </CardContent>
        </Card>
        <Card>
          <CardHeader>
            <CardTitle>Connection health</CardTitle>
            <CardDescription>What this terminal is allowed to do</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2 text-sm">
            <div className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2">
              <span>FastAPI</span>
              <Badge variant="secondary">127.0.0.1:8000</Badge>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2">
              <span>Live SSE</span>
              <Badge variant="warning">Disabled</Badge>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2">
              <span>Ownership migration</span>
              <Badge variant="outline">Not applied</Badge>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2">
              <span>Trading HTTP</span>
              <Badge variant="danger">Off</Badge>
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
