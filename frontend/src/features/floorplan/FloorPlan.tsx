import { Link } from "react-router-dom";
import type { MachineSummary } from "../../api/types";
import type { FloorPlanData, PlanUnit } from "./planApi";
import "./floorplan.css";

const TIER_WORD: Record<string, string> = { routine: "Low", elevated: "Medium", high: "High", critical: "Urgent" };
const SEV_WORD: Record<string, string> = { normal: "Normal", watch: "Watch", warning: "Warning", critical: "Critical" };

/** Plain words and a style key for a machine: its open problem's priority, or else its sensor condition. */
export function statusOf(m: MachineSummary): { word: string; tone: string; problem: boolean } {
  if (m.open_incident_tier) {
    const t = m.open_incident_tier;
    return { word: TIER_WORD[t] ?? t, tone: `tier-${t}`, problem: true };
  }
  return { word: SEV_WORD[m.status] ?? m.status, tone: `sev-${m.status}`, problem: false };
}

/** Top-down plan of the site. Machines GhostShift monitors are links with their status; the rest are muted placeholders. */
export function FloorPlan({ plan, machines }: { plan: FloorPlanData; machines: MachineSummary[] }) {
  const byId = new Map(machines.map((m) => [m.id, m]));
  const unit = new Map(plan.units.map((u) => [u.id, u]));
  const pct = (v: number, total: number) => `${(v / total) * 100}%`;

  return (
    <div className="plan" style={{ aspectRatio: `${plan.width} / ${plan.height}` }}>
      <svg className="plan-bg" viewBox={`0 0 ${plan.width} ${plan.height}`} aria-hidden>
        {plan.zones.map((z) => (
          <g key={z.id}>
            <rect x={z.x} y={z.y} width={z.w} height={z.h} rx="6" className="zone" />
            <text x={z.x + 12} y={z.y + 20} className="zone-label">
              {z.label}
            </text>
          </g>
        ))}
        {plan.labels.map((l) => (
          <text key={l.text + l.x + l.y} x={l.x} y={l.y} className="plan-label">
            {l.text}
          </text>
        ))}
        {plan.links.map((l) => {
          const a = unit.get(l.a);
          const b = unit.get(l.b);
          if (!a || !b) return null;
          return <Bracket key={l.a + l.b} a={a} b={b} label={l.label} />;
        })}
      </svg>
      {plan.units.map((u) => {
        const m = u.machine_id ? byId.get(u.machine_id) : undefined;
        const style = {
          left: pct(u.x, plan.width),
          top: pct(u.y, plan.height),
          width: pct(u.w, plan.width),
          height: pct(u.h, plan.height),
        };
        if (!m) {
          return (
            <div key={u.id} className={`tile ${u.kind} idle`} style={style} title={`${u.label}: not monitored in this demo`}>
              <Photo name={u.photo} />
              <span className="tile-bar">
                <span className="mono tile-id">{u.label}</span>
              </span>
            </div>
          );
        }
        const st = statusOf(m);
        return (
          <Link
            key={u.id}
            to={`/machines/${m.id}`}
            className={`tile ${u.kind} live ${st.tone} ${st.problem ? "problem" : ""}`}
            style={style}
            aria-label={`${m.id}, ${m.display_name.replace(`${m.id} `, "")}: ${st.word}${st.problem ? " priority" : ""}. Open machine page`}
          >
            <Photo name={u.photo} />
            <span className="tile-bar">
              <span className="mono tile-id">{m.id}</span>
              <span className="tile-status">
                <i aria-hidden /> {st.word}
              </span>
            </span>
          </Link>
        );
      })}
    </div>
  );
}

function Photo({ name }: { name: string | null }) {
  return name ? <img className="tile-photo" src={`/images/${name}.jpg`} alt="" loading="lazy" /> : null;
}

/** A dashed bracket under (or beside) two units that back each other up. */
function Bracket({ a, b, label }: { a: PlanUnit; b: PlanUnit; label: string }) {
  const side = Math.abs(a.y - b.y) < 10;
  if (side) {
    const y = Math.max(a.y + a.h, b.y + b.h) + 10;
    const x1 = a.x + a.w / 2;
    const x2 = b.x + b.w / 2;
    return (
      <g className="bracket">
        <path d={`M${x1} ${y - 10}V${y}H${x2}V${y - 10}`} />
        <text x={(x1 + x2) / 2} y={y + 14} textAnchor="middle">
          {label}
        </text>
      </g>
    );
  }
  const x = Math.max(a.x + a.w, b.x + b.w) + 10;
  const y1 = a.y + a.h / 2;
  const y2 = b.y + b.h / 2;
  return (
    <g className="bracket">
      <path d={`M${x - 10} ${y1}H${x}V${y2}H${x - 10}`} />
      <text x={x - 14} y={(y1 + y2) / 2 + 4} textAnchor="end">
        {label}
      </text>
    </g>
  );
}
