import type { ReactNode } from "react";

import { PageFrame } from "@/components/command-center";
import type { ModeKind } from "@/components/command-center";

type TemplateProps = {
  eyebrow?: string;
  title: string;
  description?: string;
  modes?: ModeKind[];
  actions?: ReactNode;
  toolbar?: ReactNode;
  children: ReactNode;
  className?: string;
};

function Template({
  template,
  toolbar,
  children,
  ...frame
}: TemplateProps & {
  template: "overview" | "terminal" | "ai" | "operations" | "research" | "settings";
}) {
  return (
    <PageFrame template={template} {...frame}>
      {toolbar ? <div className="flex min-w-0 flex-wrap items-center gap-2">{toolbar}</div> : null}
      {children}
    </PageFrame>
  );
}

/** KPI dashboard: header, optional toolbar, then the page body. */
export function OverviewTemplate(props: TemplateProps) {
  return <Template template="overview" {...props} />;
}

/** Chart workspace. Put symbol and timeframe controls in `toolbar`. */
export function TradingTerminalTemplate(props: TemplateProps) {
  return <Template template="terminal" {...props} />;
}

/** Conversation workspace. Pass a fill-height className from the chat page. */
export function AiWorkspaceTemplate(props: TemplateProps) {
  return <Template template="ai" {...props} />;
}

/** Supervisor and paper session console. */
export function OperationsTemplate(props: TemplateProps) {
  return <Template template="operations" {...props} />;
}

/** Strategy, news, and backtest research. */
export function ResearchTemplate(props: TemplateProps) {
  return <Template template="research" {...props} />;
}

/** Settings, exchanges, and notifications. */
export function SettingsTemplate(props: TemplateProps) {
  return <Template template="settings" {...props} />;
}
