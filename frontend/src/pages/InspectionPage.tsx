import { lazy, Suspense, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { api, ApiError } from "../api/client";
import type { InspectionView } from "../api/types";
import { Icon, PriorityPill, SafetyNotice, SeverityPill, Wordmark } from "../components/ui";
import { AssemblyDiagram } from "../features/assembly/AssemblyDiagram";
import { Briefing } from "../features/incident/Technician";
import { PartCard } from "../features/inspection/PartCard";
import { RepairGuide } from "../features/inspection/RepairGuide";
import { MachineThumb } from "../features/machine/MachinePhoto";
import { MODELS } from "../features/model3d/models";
import { WorkOrderApproval } from "../features/inspection/WorkOrderApproval";
import { PlanCard } from "../features/schedule/PlanCard";
import { fmtDateTime } from "../lib/format";
import "./inspection.css";

// three.js is only loaded on this page, and only when the 3D view is shown.
const Machine3D = lazy(() => import("../features/model3d/Machine3D"));

/** Technician's phone view, opened from the SMS link. Read-only and limited to one incident. */
export function InspectionPage() {
  const { token = "" } = useParams();
  const [view, setView] = useState<InspectionView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<string | null>(null);
  const [view3d, setView3d] = useState(true);
  const [no3d, setNo3d] = useState(false);
  const cardRef = useRef<HTMLDivElement>(null);
  const [planKey, setPlanKey] = useState(0); // reload the schedule card after an approval confirms the slot

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
  const wo = view.work_order;
  // "Replace", "Clean", "Inspect": the first word of the work-order title.
  const verb = inc.maintenance?.work_order.title.split(" ")[0] ?? "Inspect";
  const has3d = !no3d && view.drawing in MODELS;
  const show3d = has3d && view3d;
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
          <h1>{inc.maintenance ? inc.maintenance.work_order.title.split(" — ")[0] : `Inspect ${affected?.component.name.toLowerCase() ?? "equipment"}`}</h1>
          {inc.diagnostics.hypotheses[0] && <p className="small">Likely {inc.diagnostics.hypotheses[0].name.toLowerCase()}</p>}
        </section>

        <MachineThumb drawing={view.drawing} wide />

        <PlanCard key={planKey} token={token} />

        <WorkOrderApproval token={token} onChanged={() => setPlanKey((k) => k + 1)} />

        <SafetyNotice>Lock out and verify before any physical work. This page does not make the machine safe.</SafetyNotice>

        <section className="m-card">
          {has3d && (
            <div className="row">
              <span className="xs muted">{show3d ? "Drag to turn, pinch to zoom, tap a part" : "Tap a part for details"}</span>
              <span className="spacer" />
              <div className="view-toggle" role="group" aria-label="Model view">
                <button aria-pressed={show3d} onClick={() => setView3d(true)}>
                  3D
                </button>
                <button aria-pressed={!show3d} onClick={() => setView3d(false)}>
                  2D
                </button>
              </div>
            </div>
          )}
          {show3d ? (
            <Suspense fallback={<div className="machine3d" />}>
              <Machine3D
                drawing={view.drawing}
                components={view.components.map((c) => c.component)}
                health={health}
                affectedId={inc.affected_component_id}
                selectedId={current?.component.id ?? null}
                onSelect={(id) => pick(id)}
                onUnsupported={() => setNo3d(true)}
                actionVerb={verb}
              />
            </Suspense>
          ) : (
            <AssemblyDiagram
              drawing={view.drawing}
              components={view.components.map((c) => c.component)}
              health={health}
              affectedId={inc.affected_component_id}
              selectedId={current?.component.id ?? null}
              onSelect={(id) => pick(id)}
            />
          )}
          {!has3d && <p className="xs muted center">Tap a part for details</p>}
        </section>

        <div ref={cardRef} className="scroll-anchor">
          {current && <PartCard component={current.component} health={current.health} incident={inc} />}
        </div>

        {affected && (
          <RepairGuide
            incident={inc}
            workOrder={wo}
            machineLabel={view.machine_name.replace(`${view.machine_id} `, "")}
            componentName={affected.component.name}
          />
        )}

        <section className="m-card">
          <h2>All parts</h2>
          <ul className="clean m-others">
            {view.components.map(({ component: c, health: h }) => (
              <li key={c.id}>
                <button className={c.id === current?.component.id ? "active" : ""} onClick={() => pick(c.id, true)}>
                  <span className="small">
                    {c.name}
                    {c.id === inc.affected_component_id && <span className="xs warn-text"> · {verb.toLowerCase()}</span>}
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
