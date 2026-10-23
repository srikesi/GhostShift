import { useState } from "react";
import { Link } from "react-router-dom";
import { SimTag } from "../../components/ui";
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
  const [picked, setPicked] = useState<string | null>(null);
  const pickedUnit = plan.units.find((u) => u.id === picked && !u.machine_id);
  const byId = new Map(machines.map((m) => [m.id, m]));
  const unit = new Map(plan.units.map((u) => [u.id, u]));
  const pct = (v: number, total: number) => `${(v / total) * 100}%`;

  return (
    <>
    <div className="plan" style={{ aspectRatio: `${plan.width} / ${plan.height}` }}>
      <svg className="plan-bg" viewBox={`0 0 ${plan.width} ${plan.height}`} aria-hidden>
        <defs>
          <pattern id="fp-floor" width="20" height="20" patternUnits="userSpaceOnUse">
            <rect width="20" height="20" className="floor-tile" />
            <path d="M20 0H0V20" className="floor-seam" />
          </pattern>
          <pattern id="fp-perf" width="20" height="20" patternUnits="userSpaceOnUse">
            <rect width="20" height="20" className="floor-tile cold" />
            <path d="M20 0H0V20" className="floor-seam" />
            <g className="floor-holes">
              {[4, 8, 12, 16].flatMap((x) => [4, 8, 12, 16].map((y) => <circle key={`${x}${y}`} cx={x} cy={y} r="0.9" />))}
            </g>
          </pattern>
          <pattern id="fp-hot" width="8" height="8" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
            <rect width="8" height="8" className="hot-bg" />
            <line x1="0" y1="0" x2="0" y2="8" className="hot-line" />
          </pattern>
          <pattern id="fp-yard" width="14" height="14" patternUnits="userSpaceOnUse">
            <rect width="14" height="14" className="yard-bg" />
            <circle cx="3" cy="4" r="0.9" className="yard-dot" />
            <circle cx="10" cy="9" r="0.9" className="yard-dot" />
            <circle cx="6" cy="12" r="0.7" className="yard-dot" />
          </pattern>
        </defs>
        <rect width={plan.width} height={plan.height} className="site-ground" />
        {plan.zones.map((z) => (
          <g key={z.id}>
            <rect x={z.x} y={z.y} width={z.w} height={z.h} fill={z.id === "plant" ? "url(#fp-yard)" : "url(#fp-floor)"} />
            <rect x={z.x} y={z.y} width={z.w} height={z.h} className={z.id === "plant" ? "fence" : "wall"} />
          </g>
        ))}
        {plan.decor.aisles.map((a) => (
          <g key={a.label + a.y}>
            <rect x={a.x} y={a.y} width={a.w} height={a.h} fill={a.kind === "cold" ? "url(#fp-perf)" : "url(#fp-hot)"} className="aisle" />
            <text x={a.x + a.w / 2} y={a.y + a.h / 2 + 4} textAnchor="middle" className="aisle-label">
              {a.label.toUpperCase()}
            </text>
          </g>
        ))}
        {plan.decor.pipes.map((p, i) => (
          <g key={i} className="pipe-run">
            <polyline points={p.points.map((q) => q.join(",")).join(" ")} className="pipe-outer" />
            <polyline points={p.points.map((q) => q.join(",")).join(" ")} className="pipe-inner" />
            {p.label && (
              <text x={p.lx} y={p.ly} className="plan-label">
                {p.label}
              </text>
            )}
          </g>
        ))}
        {plan.decor.columns.map(([x, y]) => (
          <rect key={`${x},${y}`} x={x - 5} y={y - 5} width="10" height="10" className="column" />
        ))}
        {plan.zones.map((z) => (
          <text key={z.id} x={z.x + 14} y={z.y - 6} className="zone-label">
            {z.label}
          </text>
        ))}
        {plan.labels.map((l) => (
          <text key={l.text + l.x + l.y} x={l.x} y={l.y} className="plan-label">
            {l.text}
          </text>
        ))}
        {plan.decor.doors.map((d) => (
          <g key={d.label}>
            <rect x={d.x} y={d.y} width={d.w} height={d.h} className="door-gap" />
            {d.side === "bottom" ? (
              <path d={`M${d.x} ${d.y}A${d.w} ${d.w} 0 0 1 ${d.x + d.w} ${d.y - d.w}`} className="door-swing" />
            ) : (
              <path d={`M${d.x + d.w} ${d.y}A${d.h} ${d.h} 0 0 0 ${d.x + d.w + d.h} ${d.y + d.h}`} className="door-swing" />
            )}
            <text x={d.side === "bottom" ? d.x + d.w / 2 : d.x - 6} y={d.side === "bottom" ? d.y + 16 : d.y - 6} textAnchor={d.side === "bottom" ? "middle" : "end"} className="plan-label">
              {d.label}
            </text>
          </g>
        ))}
        {plan.links.map((l) => {
          const a = unit.get(l.a);
          const b = unit.get(l.b);
          if (!a || !b) return null;
          return <Bracket key={l.a + l.b} a={a} b={b} label={l.label} />;
        })}
        {plan.decor.scale && (
          <g className="scale" transform={`translate(${plan.decor.scale.x} ${plan.decor.scale.y})`}>
            <path d={`M0 0v6H${plan.decor.scale.px}v-6`} />
            <text x="0" y="18">0</text>
            <text x={plan.decor.scale.px} y="18" textAnchor="end">{plan.decor.scale.metres} m</text>
          </g>
        )}
        {plan.decor.north && (
          <g transform={`translate(${plan.decor.north.x} ${plan.decor.north.y})`} className="north">
            <circle r="16" />
            <path d="M0 -12L5 6L0 2L-5 6Z" />
            <text y="-20" textAnchor="middle">N</text>
          </g>
        )}
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
            <button
              key={u.id}
              type="button"
              className={`tile ${u.kind} live sev-normal sim ${picked === u.id ? "picked" : ""}`}
              style={style}
              aria-pressed={picked === u.id}
              aria-label={`${u.label}: Normal. Show details`}
              onClick={() => setPicked((cur) => (cur === u.id ? null : u.id))}
            >
              <Photo name={u.photo} />
              <span className="tile-bar">
                <span className="mono tile-id">{u.label}</span>
                <span className="tile-status">
                  <i aria-hidden /> Normal
                </span>
              </span>
            </button>
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
    {pickedUnit && (
      <div className="plan-info" role="status">
        <span className="mono strong">{pickedUnit.label}</span>
        <span className="small">Normal. Running within its usual ranges.</span>
        <SimTag title="Placeholder equipment with no sensor feed in this demo" />
        <button type="button" className="btn sm ghost" onClick={() => setPicked(null)}>
          Close
        </button>
      </div>
    )}
    </>
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
