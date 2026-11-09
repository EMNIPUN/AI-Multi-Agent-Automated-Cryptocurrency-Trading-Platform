"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";

import { useAuth } from "@/components/auth/AuthProvider";
import { PageFrame } from "@/components/command-center";
import { EmptyState } from "@/components/shared/EmptyState";
import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { usePersistedDensity, usePersistedTheme } from "@/lib/theme";

export default function SettingsPage() {
  const { user, session, configured, signOut, ready } = useAuth();
  const router = useRouter();
  const { light, setLight } = usePersistedTheme();
  const { density, setDensity } = usePersistedDensity();

  async function onSignOut() {
    await signOut();
    router.replace("/login");
  }

  return (
    <PageFrame
      title="Settings"
      description="Appearance, session, and connection health. Frontend settings never bypass backend gates."
      modes={["readonly", "live"]}
    >
      <DataModeBanner
        mode="demo"
        notes={[
          "No secrets in the client bundle.",
          "Private catalog reads remain gated (PRIVATE_DATA_READS_ENABLED=false).",
        ]}
      />
      <Card className="mb-4">
        <CardHeader>
          <CardTitle>Appearance</CardTitle>
          <CardDescription>Theme and workspace density (local only)</CardDescription>
        </CardHeader>
        <CardContent className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant={light ? "brand" : "outline"}
            size="sm"
            className="rounded-full"
            onClick={() => setLight(true)}
          >
            Light
          </Button>
          <Button
            type="button"
            variant={!light ? "brand" : "outline"}
            size="sm"
            className="rounded-full"
            onClick={() => setLight(false)}
          >
            Dark
          </Button>
          <Button
            type="button"
            variant={density === "comfortable" ? "brand" : "outline"}
            size="sm"
            className="rounded-full"
            onClick={() => setDensity("comfortable")}
          >
            Comfortable
          </Button>
          <Button
            type="button"
            variant={density === "compact" ? "brand" : "outline"}
            size="sm"
            className="rounded-full"
            onClick={() => setDensity("compact")}
          >
            Compact
          </Button>
        </CardContent>
      </Card>
      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Session</CardTitle>
            <CardDescription>Supabase Auth via publishable key only</CardDescription>
          </CardHeader>
          <CardContent className="space-y-3">
            {!ready ? (
              <Badge variant="outline">Checking…</Badge>
            ) : !configured ? (
              <EmptyState
                title="Auth not configured"
                badge="Auth"
                description="Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY."
              />
            ) : user ? (
              <>
                <div className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2 text-sm">
                  <span>Status</span>
                  <Badge variant="secondary">Signed in</Badge>
                </div>
                <div className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  <p className="text-xs text-muted-foreground">Email</p>
                  <p className="truncate font-medium">{user.email}</p>
                </div>
                <div className="rounded-lg border border-border/70 px-3 py-2 text-sm">
                  <p className="text-xs text-muted-foreground">User id</p>
                  <p className="truncate font-mono text-xs">{user.id}</p>
                </div>
                <div className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2 text-sm">
                  <span>Access token</span>
                  <Badge variant="outline">{session ? "Present (not shown)" : "None"}</Badge>
                </div>
                <Button variant="outline" onClick={() => void onSignOut()}>
                  Sign out
                </Button>
              </>
            ) : (
              <>
                <Badge variant="outline">Signed out</Badge>
                <EmptyState
                  title="No active session"
                  badge="Auth"
                  description="Sign in to attach a verified Supabase identity to this terminal."
                />
                <Button asChild>
                  <Link href="/login">Sign in</Link>
                </Button>
              </>
            )}
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
              <span>Private wallet reads</span>
              <Badge variant="warning">Kill switch off</Badge>
            </div>
            <div className="flex items-center justify-between rounded-lg border border-border/70 px-3 py-2">
              <span>Trading HTTP</span>
              <Badge variant="danger">Off</Badge>
            </div>
            <p className="pt-2 text-xs text-muted-foreground">
              Browser session checks never authorize private API data. FastAPI verifies JWTs
              independently.
            </p>
            <Button asChild variant="outline" className="mt-2 w-full sm:w-auto">
              <Link href="/settings/exchanges">Manage exchange accounts</Link>
            </Button>
            <Button asChild variant="ghost" className="mt-2 w-full sm:w-auto">
              <Link href="/system">Open System Health</Link>
            </Button>
          </CardContent>
        </Card>
      </div>
    </PageFrame>
  );
}
