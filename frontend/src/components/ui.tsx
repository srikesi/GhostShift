import {
  AlertTriangle,
  Check,
  ChevronsRight,
  Clock,
  ExternalLink,
  Package,
  Pause,
  Play,
  RotateCcw,
  ShieldAlert,
  SkipForward,
  Smartphone,
  StepForward,
  Volume2,
  Wrench,
  X,
  type LucideIcon,
} from "lucide-react";
import type { ReactNode } from "react";
import type { ProviderInfo, RiskTier, Severity, StageStatus } from "../api/types";

const SEV_LABEL: Record<Severity, string> = { normal: "Normal", watch: "Watch", warning: "Warning", critical: "Critical" };

export function SeverityPill({ severity, label }: { severity: Severity; label?: string }) {
  return (
    <span className={`pill sev-${severity}`}>
      <span className="dot" aria-hidden />
      {label ?? SEV_LABEL[severity]}
    </span>
  );
}

const PRIORITY: Record<RiskTier, string> = { routine: "Low", elevated: "Medium", high: "High", critical: "Urgent" };

/** Incident urgency, from the safety supervisor's tier. */
export function PriorityPill({ tier, short = false }: { tier: RiskTier; short?: boolean }) {
  return (
    <span className={`pill tier-${tier}`} title={`${PRIORITY[tier]} priority`}>
      {PRIORITY[tier]}
      {!short && " priority"}
    </span>
  );
}

/** Marks output that only exists in the simulation (SMS, orders, stock). */
export function SimTag({ title = "Simulated in this demo" }: { title?: string }) {
  return (
    <span className="tag" title={title}>
      Simulated
    </span>
  );
}

/** Shown only when a real provider was involved, or when it failed. Built-in rules show nothing. */
export function ProviderNote({ provider, status }: { provider: ProviderInfo; status?: StageStatus }) {
  if (status === "provider_failure" || status === "invalid_result")
    return <span className="tag fail" title={`${provider.name}: ${status}`}>{provider.real ? `${provider.name} failed` : "Failed"}</span>;
  if (status === "deterministic_fallback")
    return <span className="tag warn" title="The live service was unavailable, so the built-in version was used">Fallback</span>;
  if (provider.real) return <span className="tag real" title={provider.model_id ?? provider.name}>Live · {provider.name}</span>;
  return null;
}

export function Panel({
  title,
  actions,
  children,
  className = "",
  bodyClass = "panel-body",
  id,
}: {
  title: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClass?: string;
  id?: string;
}) {
  return (
    <section className={`panel ${className}`} aria-labelledby={id ? `${id}-title` : undefined}>
      <header className="panel-head">
        <h2 id={id ? `${id}-title` : undefined}>{title}</h2>
        <span className="spacer" />
        {actions}
      </header>
      <div className={bodyClass}>{children}</div>
    </section>
  );
}

export function SafetyNotice({ children }: { children: ReactNode }) {
  return (
    <div className="notice safety" role="note">
      <Icon name="shield" />
      <div>{children}</div>
    </div>
  );
}

const ICONS = {
  play: Play,
  pause: Pause,
  step: StepForward,
  reset: RotateCcw,
  jump: SkipForward,
  end: ChevronsRight,
  alert: AlertTriangle,
  shield: ShieldAlert,
  check: Check,
  x: X,
  phone: Smartphone,
  external: ExternalLink,
  wrench: Wrench,
  box: Package,
  clock: Clock,
  speaker: Volume2,
} satisfies Record<string, LucideIcon>;

export function Icon({ name, title }: { name: keyof typeof ICONS; title?: string }) {
  const C = ICONS[name];
  return <C size={15} strokeWidth={1.75} aria-hidden={title ? undefined : true} aria-label={title} />;
}

export function Wordmark({ compact = false }: { compact?: boolean }) {
  return (
    <span className="wordmark" aria-label="Faultzy">
      <svg viewBox="0 0 24 24" width="22" height="22" aria-hidden>
        <rect width="24" height="24" rx="5" fill="var(--on-graphite)" />
        <path d="M7 6h10v3H10.5v2.2H16v3h-5.5V18H7z" fill="var(--graphite)" />
        <rect x="14.5" y="15" width="3" height="3" fill="var(--amber)" />
      </svg>
      {!compact && <span>Faultzy</span>}
    </span>
  );
}
