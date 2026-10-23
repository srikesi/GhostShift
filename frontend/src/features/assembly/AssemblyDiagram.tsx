import type { KeyboardEvent } from "react";
import type { Component, ComponentHealth, Severity } from "../../api/types";
import { DRAWINGS } from "./drawings";
import "./assembly.css";

interface Props {
  drawing: string;
  components: Component[];
  health: Record<string, ComponentHealth | undefined>;
  affectedId: string | null;
  selectedId: string | null;
  onSelect?: (componentId: string) => void;
}

export function AssemblyDiagram({ drawing, components, health, affectedId, selectedId, onSelect }: Props) {
  const def = DRAWINGS[drawing];
  if (!def) return <GenericAssembly {...{ components, health, affectedId, selectedId, onSelect }} />;

  const affected = components.find((c) => c.id === affectedId);
  const affectedPart = affected ? def.parts[affected.visualization_id] : undefined;

  return (
    <svg
      className="assembly"
      viewBox={def.viewBox}
      role="group"
      aria-label={`Assembly schematic${affected ? `; affected component ${affected.name}` : ""}`}
    >
      <defs>
        <marker id="arrow" viewBox="0 0 8 8" refX="7" refY="4" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M0 0 8 4 0 8z" fill="var(--ink-4)" />
        </marker>
      </defs>
      <g className="structure" aria-hidden>
        {def.structure}
      </g>
      {components.map((c, i) => {
        const part = def.parts[c.visualization_id];
        if (!part) return null;
        const status: Severity = health[c.id]?.status ?? "normal";
        const cls = [
          "part",
          `status-${status}`,
          c.id === affectedId ? "affected" : "",
          c.id === selectedId ? "selected" : "",
          health[c.id]?.basis === "interval_only" ? "uninstrumented" : "",
        ].join(" ");
        const select = () => onSelect?.(c.id);
        return (
          <g
            key={c.id}
            id={c.visualization_id}
            data-component={c.id}
            className={cls}
            tabIndex={onSelect ? 0 : -1}
            role={onSelect ? "button" : "img"}
            aria-pressed={onSelect ? c.id === selectedId : undefined}
            aria-label={`${i + 1}. ${c.name}: ${status}`}
            onClick={select}
            onKeyDown={(e: KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                select();
              }
            }}
          >
            <title>{`${c.name} — ${status}`}</title>
            <g className="shape">{part.shape}</g>
            <g className="marker" transform={`translate(${part.anchor[0]} ${part.anchor[1]})`}>
              {c.id === affectedId && <circle r="13" className="halo" />}
              <circle r="7.5" />
              <text dy="3.2">{i + 1}</text>
            </g>
          </g>
        );
      })}
      {affected && affectedPart && <Callout part={affectedPart} label={truncate(affected.name, 26)} />}
    </svg>
  );
}

const BOX_W = 148;
const BOX_H = 24;

function Callout({ part, label }: { part: { anchor: [number, number]; callout: [number, number] }; label: string }) {
  const [ax, ay] = part.anchor;
  const [bx, by] = part.callout;
  // Leave the box from the side facing the anchor.
  const sx = ax > bx + BOX_W ? bx + BOX_W : ax < bx ? bx : Math.min(Math.max(ax, bx + 8), bx + BOX_W - 8);
  const sy = ax > bx + BOX_W || ax < bx ? by + BOX_H / 2 : ay > by ? by + BOX_H : by;
  const d = Math.hypot(ax - sx, ay - sy) || 1;
  const ex = ax - ((ax - sx) / d) * 9;
  const ey = ay - ((ay - sy) / d) * 9;
  return (
    <g className="callout" aria-hidden>
      <path d={`M${sx} ${sy}L${ex} ${ey}`} />
      <rect x={bx} y={by} width={BOX_W} height={BOX_H} rx="3" />
      <text x={bx + 8} y={by + 16}>
        {label}
      </text>
    </g>
  );
}

function truncate(s: string, n: number) {
  return s.length > n ? `${s.slice(0, n - 1)}…` : s;
}

/** Fallback for machines without a drawing (e.g. dataset adapters) or no SVG support. */
function GenericAssembly({ components, health, affectedId, selectedId, onSelect }: Omit<Props, "drawing">) {
  return (
    <ul className="generic-assembly clean" aria-label="Components">
      {components.map((c, i) => {
        const status = health[c.id]?.status ?? "normal";
        return (
          <li key={c.id}>
            <button
              className={`gen-part status-${status} ${c.id === affectedId ? "affected" : ""} ${c.id === selectedId ? "selected" : ""}`}
              onClick={() => onSelect?.(c.id)}
            >
              <span className="mono xs">{i + 1}</span> {c.name}
            </button>
          </li>
        );
      })}
    </ul>
  );
}
