import Link from "next/link";

import { DataModeBanner } from "@/components/shared/DataModeBanner";
import { PageHeader } from "@/components/shared/PageHeader";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const AGENTS = [
  {
    name: "EMA/RSI Agent",
    status: "Implemented",
    detail: "Confirmed-candle EMA/RSI loop in Python agent/",
    href: "/agents/live",
    ready: true,
  },
  {
    name: "SMC Agent",
    status: "Coming Soon",
    detail: "Smart-money concepts package not implemented",
    href: null,
    ready: false,
  },
  {
    name: "Coordinator",
    status: "Coming Soon",
    detail: "Multi-agent coordinator not implemented",
    href: null,
    ready: false,
  },
];

export default function AgentsPage() {
  return (
    <div>
      <PageHeader
        title="Agents"
        description="Directory of trading agents. Only EMA/RSI is implemented today."
      />
      <DataModeBanner mode="demo" notes={["No fabricated multi-agent activity"]} />
      <div className="grid gap-4 md:grid-cols-3">
        {AGENTS.map((a) => (
          <Card key={a.name}>
            <CardHeader>
              <CardTitle className="text-base">{a.name}</CardTitle>
              <CardDescription>{a.detail}</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Badge variant={a.ready ? "success" : "secondary"}>{a.status}</Badge>
              {a.href ? (
                <Button asChild size="sm">
                  <Link href={a.href}>Open live center</Link>
                </Button>
              ) : (
                <Button size="sm" disabled>
                  Coming soon
                </Button>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
