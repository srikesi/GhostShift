import type { ComponentRulEstimate, RulEstimate, SensorAssessment } from "../api/types";

const dtf = new Intl.DateTimeFormat("en-US", {
  weekday: "short",
  month: "short",
  day: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
});
const tf = new Intl.DateTimeFormat("en-US", { hour: "2-digit", minute: "2-digit", hour12: false, timeZone: "UTC" });
const wf = new Intl.DateTimeFormat("en-US", { weekday: "short", timeZone: "UTC" });

export const fmtDateTime = (iso: string) => `${dtf.format(new Date(iso))} UTC`;
export const fmtTime = (iso: string) => tf.format(new Date(iso));
/** Axis label, e.g. "Tue 06:00". */
export const fmtTick = (iso: string) => `${wf.format(new Date(iso))} ${tf.format(new Date(iso))}`;

export function fmtNum(v: number | null | undefined, digits = 2): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "—";
  const abs = Math.abs(v);
  if (abs >= 1000) return v.toLocaleString("en-US", { maximumFractionDigits: 0 });
  if (abs >= 100) return v.toFixed(Math.max(0, digits - 2));
  if (abs >= 10) return v.toFixed(Math.max(0, digits - 1));
  return v.toFixed(digits);
}

export const fmtUsd = (v: number | null | undefined) =>
  v === null || v === undefined ? "—" : v.toLocaleString("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 });

export function fmtHours(h: number | null | undefined): string {
  if (h === null || h === undefined) return "—";
  if (h < 0) return `overdue ${fmtHours(-h)}`;
  if (h >= 48) return `${(h / 24).toFixed(h >= 240 ? 0 : 1)} d`;
  return `${h.toFixed(h < 10 ? 1 : 0)} h`;
}

export function rulRange(r: RulEstimate | ComponentRulEstimate | null | undefined): string {
  if (!r || !r.supportable || r.value_hours === null) return "Not estimated";
  if (r.value_hours === 0) return "Limit reached";
  const lo = r.lower_hours ?? r.value_hours;
  const hi = r.upper_hours;
  if (hi === null) return `${fmtHours(lo)} or more`;
  if (lo < 48 && hi < 48) return `${lo.toFixed(0)}–${hi.toFixed(0)} h`;
  if (lo >= 48 && hi >= 48) return `${(lo / 24).toFixed(1)}–${(hi / 24).toFixed(1)} d`;
  return `${fmtHours(lo)} – ${fmtHours(hi)}`;
}

export const humanize = (s: string) => s.replace(/_/g, " ");

export const roleLabel: Record<string, string> = {
  maintenance_supervisor: "Maintenance supervisor",
  operations_manager: "Operations manager",
};

/** Change of the displayed current value vs the normal (baseline) mean, e.g. "+84%". */
export function vsNormal(s: SensorAssessment): string {
  const pct = s.baseline.mean ? ((s.current_value - s.baseline.mean) / Math.abs(s.baseline.mean)) * 100 : 0;
  return `${pct >= 0 ? "+" : ""}${pct.toFixed(0)}%`;
}
