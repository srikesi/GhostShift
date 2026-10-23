import type { IncidentView } from "../../api/types";
import { Icon, Panel } from "../../components/ui";
import { fmtDateTime, fmtUsd } from "../../lib/format";

export function FixPanel({ view }: { view: IncidentView }) {
  const inc = view.incident;
  const m = inc.maintenance;
  return (
    <Panel title="Recommended fix" id="fix">
      <div className="stack">
        <p className="small">{inc.safety.recommended_response}</p>
        {m ? (
          <>
            <div className="fix-rows">
              {m.proposed_part && (
                <div className="fix-row">
                  <Icon name="box" />
                  <div>
                    <div className="small">
                      <span className="mono">{m.proposed_part.sku}</span> · {fmtUsd(m.estimated_cost_usd)}
                    </div>
                    <div className="xs muted">
                      {m.proposed_part.description}.{" "}
                      {(m.proposed_part.availability.on_hand ?? 0) > 0
                        ? `${m.proposed_part.availability.on_hand} in stock, ${m.proposed_part.availability.location}.`
                        : `Not in stock, ${m.proposed_part.availability.lead_time_days} day lead time.`}
                    </div>
                  </div>
                </div>
              )}
              {m.maintenance_window && (
                <div className="fix-row">
                  <Icon name="clock" />
                  <div>
                    <div className="small">{m.maintenance_window.label}</div>
                    <div className="xs muted">
                      {fmtDateTime(m.maintenance_window.start)} · job takes about {m.work_order.estimated_duration_hours} h
                    </div>
                  </div>
                </div>
              )}
            </div>
            <ol className="steps small">
              {m.work_order.tasks.map((t) => (
                <li key={t.step}>
                  {t.description}
                  {t.requires_qualified_person && <span className="xs muted"> (qualified staff)</span>}
                </li>
              ))}
            </ol>
            {m.warnings.map((w) => (
              <div key={w} className="notice small">
                <Icon name="alert" />
                <span>{w}</span>
              </div>
            ))}
          </>
        ) : (
          <p className="small muted">No repair plan yet. See “How Faultzy decided” below.</p>
        )}
      </div>
    </Panel>
  );
}
