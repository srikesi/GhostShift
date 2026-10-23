import { useEffect, useMemo, useState } from "react";
import { ApiError } from "../../api/client";
import { ops, type CalendarEvent, type CalendarView } from "../../api/ops";
import { Panel, SimTag } from "../../components/ui";
import { fmtDateTime, fmtTime } from "../../lib/format";
import "./schedule.css";

const DAY_MS = 86_400_000;
const dayFmt = new Intl.DateTimeFormat("en-US", { weekday: "short", day: "numeric", timeZone: "UTC" });

interface Lane {
  id: string;
  label: string;
  sub?: string;
  events: CalendarEvent[];
  shifts: { start: string; end: string }[];
}

/** One week, one row per person or unit: planned windows, existing jobs and the slot GhostShift is holding. */
export function WeekCalendar({ machineId, now, refreshKey }: { machineId: string; now: string | null; refreshKey: string }) {
  const [view, setView] = useState<CalendarView | null>(null);
  const [startDay, setStartDay] = useState<string | undefined>(undefined);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ops
      .calendar(startDay)
      .then((v) => {
        setView(v);
        setError(null);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [startDay, refreshKey]);

  const lanes = useMemo<Lane[]>(() => {
    if (!view) return [];
    const partner = view.redundancy.find((r) => r.unit === machineId)?.partner;
    const mine = view.events.filter((e) => e.machine_id === machineId);
    const out: Lane[] = [{ id: "unit", label: machineId, sub: "windows and holds", events: mine, shifts: [] }];
    if (partner) {
      out.push({
        id: "partner",
        label: partner,
        sub: "must stay running",
        events: view.events.filter((e) => e.machine_id === partner),
        shifts: [],
      });
    }
    for (const t of view.technicians) {
      out.push({
        id: t.id,
        label: t.name,
        sub: t.skills.includes("Refrigeration (qualified)") ? "refrigeration" : t.skills.includes("Electrical (qualified)") ? "electrical" : "general",
        events: view.events.filter((e) => e.technician_id === t.id),
        shifts: view.shifts.filter((s) => s.technician_id === t.id),
      });
    }
    return out;
  }, [view, machineId]);

  const start = view ? new Date(view.start).getTime() : 0;
  const end = view ? new Date(view.end).getTime() : 0;
  const span = Math.max(end - start, DAY_MS);
  const pct = (iso: string) => Math.min(100, Math.max(0, ((new Date(iso).getTime() - start) / span) * 100));
  const days = view ? Array.from({ length: Math.round(span / DAY_MS) }, (_, i) => new Date(start + i * DAY_MS)) : [];
  const shift = (dir: number) => view && setStartDay(new Date(start + dir * 7 * DAY_MS).toISOString());

  return (
    <Panel
      title={
        <>
          Calendar <SimTag title="Simulated roster and bookings. No real calendar is connected." />
        </>
      }
      id="calendar"
      actions={
        <span className="cal-nav">
          <button className="btn sm" onClick={() => shift(-1)} aria-label="Previous week">
            ‹
          </button>
          <button className="btn sm" onClick={() => shift(1)} aria-label="Next week">
            ›
          </button>
        </span>
      }
    >
      {error && <p className="small muted">{error}</p>}
      {view && (
        <>
          <div className="cal-scroll">
            <div className="cal" style={{ ["--days" as string]: days.length }}>
              <div className="cal-row cal-head">
                <div className="cal-label" />
                <div className="cal-track">
                  {days.map((d) => (
                    <span key={d.getTime()} className="cal-day">
                      {dayFmt.format(d)}
                    </span>
                  ))}
                </div>
              </div>
              {lanes.map((lane) => (
                <div key={lane.id} className="cal-row">
                  <div className="cal-label">
                    <span className="small strong">{lane.label}</span>
                    <span className="xs muted">{lane.sub}</span>
                  </div>
                  <div className="cal-track" role="list" aria-label={`${lane.label} schedule`}>
                    {lane.shifts.map((s, i) => (
                      <span
                        key={i}
                        className="cal-shift"
                        style={{ left: `${pct(s.start)}%`, width: `${pct(s.end) - pct(s.start)}%` }}
                        title={`On shift ${fmtTime(s.start)} to ${fmtTime(s.end)} UTC`}
                      />
                    ))}
                    {lane.events.map((e) => (
                      <span
                        key={e.id + lane.id}
                        role="listitem"
                        className={`cal-event ${e.kind} ${e.status}`}
                        style={{ left: `${pct(e.start)}%`, width: `max(${pct(e.end) - pct(e.start)}%, 6px)` }}
                        title={`${e.title}\n${fmtDateTime(e.start)} to ${fmtTime(e.end)}${e.status !== "planned" ? `\n${e.status}` : ""}`}
                      >
                        <span className="cal-event-text">{e.title}</span>
                      </span>
                    ))}
                    {now && new Date(now).getTime() >= start && new Date(now).getTime() <= end && (
                      <span className="cal-now" style={{ left: `${pct(now)}%` }} aria-hidden />
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
          <ul className="cal-legend xs muted clean">
            <li>
              <i className="sw window" /> Planned maintenance window
            </li>
            <li>
              <i className="sw job" /> Existing job
            </li>
            <li>
              <i className="sw hold" /> Held slot (tentative)
            </li>
            <li>
              <i className="sw booked" /> Confirmed
            </li>
            <li>
              <i className="sw shift" /> On shift
            </li>
          </ul>
        </>
      )}
    </Panel>
  );
}
