import { useLayoutEffect, useMemo, useRef, useState } from "react";
import type { SensorAssessment, SensorDefinition, TelemetryPoint } from "../../api/types";
import { fmtDateTime, fmtNum, fmtTick, vsNormal } from "../../lib/format";

interface Props {
  sensor: SensorDefinition;
  points: TelemetryPoint[];
  length: number;
  assessment?: SensorAssessment;
}

const H = 124;
const M = { l: 38, r: 58, t: 10, b: 24 };

function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [w, setW] = useState(560);
  useLayoutEffect(() => {
    if (!ref.current) return;
    setW(Math.max(260, ref.current.clientWidth - 16)); // measure now; the observer may fire late
    const ro = new ResizeObserver(([e]) => setW(Math.max(260, e.contentRect.width)));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, w] as const;
}

export function SensorChart({ sensor, points, length, assessment }: Props) {
  const [ref, W] = useWidth<HTMLDivElement>();
  const [hover, setHover] = useState<number | null>(null);
  const pw = W - M.l - M.r;
  const ph = H - M.t - M.b;

  const series = useMemo(
    () => points.filter((p) => p.values[sensor.id] !== null && p.values[sensor.id] !== undefined),
    [points, sensor.id],
  );
  const values = series.map((p) => p.values[sensor.id] as number);

  const { lo, hi, limits } = useMemo(() => {
    let lo = Math.min(...values);
    let hi = Math.max(...values);
    if (assessment) {
      lo = Math.min(lo, assessment.baseline.mean - 3 * assessment.baseline.std);
      hi = Math.max(hi, assessment.baseline.mean + 3 * assessment.baseline.std);
    }
    const span0 = hi - lo || 1;
    const limits: { kind: "alert" | "danger"; v: number; inView: boolean }[] = [];
    for (const kind of ["alert", "danger"] as const) {
      const v = sensor.limits?.[kind];
      if (v === null || v === undefined) continue;
      const inView = v >= lo - 0.6 * span0 && v <= hi + 0.6 * span0;
      if (inView) {
        lo = Math.min(lo, v);
        hi = Math.max(hi, v);
      }
      limits.push({ kind, v, inView });
    }
    const pad = (hi - lo || 1) * 0.08;
    return { lo: lo - pad, hi: hi + pad, limits };
  }, [values, assessment, sensor.limits]);

  if (!series.length) return null;

  const x = (i: number) => M.l + (i / Math.max(1, length - 1)) * pw;
  const y = (v: number) => M.t + (1 - (v - lo) / (hi - lo)) * ph;
  const path = series.map((p, k) => `${k ? "L" : "M"}${x(p.index).toFixed(1)} ${y(values[k]).toFixed(1)}`).join("");
  const last = series[series.length - 1];
  const lastV = values[values.length - 1];
  const ticks = [lo + (hi - lo) * 0.15, (lo + hi) / 2, hi - (hi - lo) * 0.15];
  const tickStep = (48 / Math.max(1, length - 1)) * pw >= 64 ? 48 : 96;
  const timeTicks = Array.from({ length: Math.ceil(length / tickStep) }, (_, k) => k * tickStep);
  const hoverPt = hover !== null ? series.reduce((a, b) => (Math.abs(b.index - hover) < Math.abs(a.index - hover) ? b : a)) : null;
  const t0 = new Date(points[0].timestamp).getTime();
  const dt = points.length > 1 ? new Date(points[1].timestamp).getTime() - t0 : 900_000;
  const nearEdge = x(last.index) > M.l + pw - 40;

  const abnormal = assessment?.anomalous;

  return (
    <figure className={`sensor-chart ${abnormal ? `flag-${assessment!.severity}` : ""}`} ref={ref}>
      <figcaption>
        <span className="name">{sensor.name.split(" (")[0]}</span>
        <span className="unit">{sensor.unit}</span>
        {sensor.role === "context" && <span className="muted xs">· reference</span>}
        <span className="spacer" />
        {abnormal && assessment!.role === "health" && (
          <span className={`change sev-text-${assessment!.severity}`}>{vsNormal(assessment!)} vs normal</span>
        )}
      </figcaption>
      <svg
        width={W}
        height={H}
        role="img"
        aria-label={
          assessment
            ? `${sensor.name}: now ${fmtNum(assessment.current_value)} ${sensor.unit}, normal ${fmtNum(assessment.baseline.mean)}`
            : sensor.name
        }
        onMouseMove={(e) => {
          const r = (e.currentTarget as SVGSVGElement).getBoundingClientRect();
          const i = Math.round(((e.clientX - r.left - M.l) / pw) * (length - 1));
          setHover(i >= 0 && i <= last.index ? i : null);
        }}
        onMouseLeave={() => setHover(null)}
      >
        <rect x={x(last.index)} y={M.t} width={x(length - 1) - x(last.index)} height={ph} className="future-zone" />
        {assessment && (
          <rect
            x={M.l}
            width={pw}
            y={y(assessment.baseline.mean + 3 * assessment.baseline.std)}
            height={Math.max(1, y(assessment.baseline.mean - 3 * assessment.baseline.std) - y(assessment.baseline.mean + 3 * assessment.baseline.std))}
            className="band"
          />
        )}
        {ticks.map((t) => (
          <text key={t} x={M.l - 6} y={y(t) + 3} className="axis" textAnchor="end">
            {fmtNum(t, 2)}
          </text>
        ))}
        {timeTicks.map((i) => (
          <text key={i} x={x(i)} y={H - 6} className="axis" textAnchor={i === 0 ? "start" : "middle"}>
            {fmtTick(new Date(t0 + i * dt).toISOString())}
          </text>
        ))}
        {limits.map((l) =>
          l.inView ? (
            <g key={l.kind} className={`limit ${l.kind}`}>
              <line x1={M.l} x2={M.l + pw} y1={y(l.v)} y2={y(l.v)} />
              <text x={M.l + pw + 5} y={y(l.v) + 3}>
                {l.kind} {fmtNum(l.v, 1)}
              </text>
            </g>
          ) : (
            <text key={l.kind} x={M.l + pw + 5} y={l.kind === "danger" ? M.t + 4 : M.t + 14} className={`limit-off ${l.kind}`}>
              <title>{`${l.kind} limit ${l.v} ${sensor.unit} (off scale)`}</title>
              {l.kind} {fmtNum(l.v, 1)}↑
            </text>
          ),
        )}
        <path d={path} className="series" />
        <circle cx={x(last.index)} cy={y(lastV)} r="3" className="head" />
        <text
          x={nearEdge ? x(last.index) - 6 : x(last.index) + 6}
          y={y(lastV) < M.t + 18 ? y(lastV) + 14 : y(lastV) - 6}
          textAnchor={nearEdge ? "end" : "start"}
          className="head-label"
        >
          {fmtNum(lastV)}
        </text>
        {hoverPt && (
          <g className="hover">
            <line x1={x(hoverPt.index)} x2={x(hoverPt.index)} y1={M.t} y2={M.t + ph} />
            <circle cx={x(hoverPt.index)} cy={y(hoverPt.values[sensor.id] as number)} r="3" />
          </g>
        )}
      </svg>
      <div className="readout xs mono">
        {hoverPt
          ? `${fmtDateTime(hoverPt.timestamp)} · ${fmtNum(hoverPt.values[sensor.id])} ${sensor.unit}`
          : assessment && abnormal
            ? `normal ${fmtNum(assessment.baseline.mean)} ${sensor.unit}`
            : " "}
      </div>
    </figure>
  );
}
