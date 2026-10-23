import { useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { InspectionView } from "../api/types";
import { Icon, PriorityPill, SafetyNotice, SeverityPill, Wordmark } from "../components/ui";
import { AssemblyDiagram } from "../features/assembly/AssemblyDiagram";
import { Briefing } from "../features/incident/Technician";
import { PartCard } from "../features/inspection/PartCard";
import { fmtDateTime } from "../lib/format";
import "./inspection.css";

/** Technician's phone view, opened from the SMS link. Read-only and limited to one incident. */
export function InspectionPage() {
  const { token = "" } = useParams();
  const [view, setView] = useState<InspectionView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const cardRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api
      .inspect(token)
      .then((v) => {
        setView(v);
        setSelected(v.incident.affected_component_id);
      })
      .catch((e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [token]);

  if (error)
    return (
      <div className="mobile">
        <header className="m-top">
          <Wordmark />
        </header>
        <main className="m-main">
          <div className="notice error" role="alert">
            <Icon name="alert" />
            <span>{error}. Ask your supervisor to resend it.</span>
          </div>
        </main>
      </div>
    );
  if (!view) return <div className="mobile m-loading">Loading…</div>;

  const inc = view.incident;
  const health = Object.fromEntries(view.components.map((c) => [c.component.id, c.health ?? undefined]));
  const affected = view.components.find((c) => c.component.id === inc.affected_component_id);
  const current = view.components.find((c) => c.component.id === selected) ?? affected;
  const m = inc.maintenance;
  const wo = view.work_order;
  const pick = (id: string, scroll = false) => {
    setSelected(id);
    if (scroll) cardRef.current?.scrollIntoView({ block: "start" });
  };

  return (
    <div className="mobile">
      <header className="m-top">
        <Wordmark />
        <span className="spacer" />
        <PriorityPill tier={inc.safety.risk_tier} />
      </header>
      <main className="m-main">
        <section>
          <p className="small muted">
            <span className="mono">{view.machine_id}</span> · {view.machine_name.replace(`${view.machine_id} `, "")}
          </p>
          <h1>{affected ? `Replace ${affected.component.name.toLowerCase()}` : "Inspect machine"}</h1>
          {inc.diagnostics.hypotheses[0] && <p className="small">Likely {inc.diagnostics.hypotheses[0].name.toLowerCase()}</p>}
        </section>

        <SafetyNotice>Lock out and verify before any physical work. This page does not make the machine safe.</SafetyNotice>

        <section className="m-card">
          <AssemblyDiagram
            drawing={view.drawing}
            components={view.components.map((c) => c.component)}
            health={health}
            affectedId={inc.affected_component_id}
            selectedId={current?.component.id ?? null}
            onSelect={(id) => pick(id, true)}
          />
          <p className="xs muted center">Tap a part for details</p>
        </section>

        <div ref={cardRef} className="scroll-anchor">
          {current && <PartCard component={current.component} health={current.health} incident={inc} />}
        </div>

        {m && (
          <section className="m-card">
            <h2>Job</h2>
            <p className="small strong">{m.work_order.title.split(" — ")[0]}</p>
            <p className="xs muted">
              {m.maintenance_window ? `${m.maintenance_window.label}, ${fmtDateTime(m.maintenance_window.start)}` : "Not scheduled"} · about{" "}
              {m.work_order.estimated_duration_hours} h
            </p>
            {wo?.status === "awaiting_approval" && <p className="xs warn-text">Waiting for supervisor approval. Don't start yet.</p>}
            <ol className="m-steps small">
              {m.work_order.tasks.map((t) => (
                <li key={t.step}>{t.description}</li>
              ))}
            </ol>
          </section>
        )}

        <section className="m-card">
          <h2>All parts</h2>
          <ul className="clean m-others">
            {view.components.map(({ component: c, health: h }) => (
              <li key={c.id}>
                <button className={c.id === current?.component.id ? "active" : ""} onClick={() => pick(c.id, true)}>
                  <span className="small">
                    {c.name}
                    {c.id === inc.affected_component_id && <span className="xs warn-text"> · replace</span>}
                  </span>
                  <span className="spacer" />
                  {h?.basis === "interval_only" ? <span className="xs muted">No sensors</span> : <SeverityPill severity={h?.status ?? "normal"} />}
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="m-card">
          <Briefing load={() => api.inspectBriefing(token)} />
        </section>

        <p className="xs muted m-foot">Link expires {fmtDateTime(view.expires_at)}</p>
      </main>
    </div>
  );
}
