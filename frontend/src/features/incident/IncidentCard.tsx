import type { IncidentView } from "../../api/types";
import { PriorityPill, ProviderNote } from "../../components/ui";
import { fmtDateTime, rulRange } from "../../lib/format";

export function IncidentCard({ view }: { view: IncidentView }) {
  const inc = view.incident;
  const m = inc.maintenance;
  const w = m?.maintenance_window;
  const part = m?.proposed_part;
  const inStock = (part?.availability.on_hand ?? 0) > 0;
  return (
    <section className={`panel incident-card edge-${inc.safety.risk_tier}`} aria-labelledby="inc-title">
      <div className="panel-body stack">
        <div className="row">
          <PriorityPill tier={inc.safety.risk_tier} />
          <span className="spacer" />
          <ProviderNote provider={inc.narrative_provider} status={inc.narrative_status} />
          <span className="mono xs muted">{inc.id}</span>
        </div>
        <h2 id="inc-title" className="headline">
          {inc.narrative.headline}
        </h2>
        {inc.narrative_provider.real && <p className="small">{inc.narrative.summary}</p>}
        <dl className="facts">
          <div>
            <dt>Time to danger limit</dt>
            <dd className="mono">{rulRange(inc.prognostics.rul)}</dd>
          </div>
          <div>
            <dt>Next downtime</dt>
            <dd className={w?.before_rul_lower_bound === false ? "warn-text" : ""}>{w ? fmtDateTime(w.start) : "None fits"}</dd>
          </div>
          <div>
            <dt>Part</dt>
            <dd>
              {part ? (
                <>
                  <span className="mono">{part.sku}</span>
                  <span className={`xs ${inStock ? "muted" : "warn-text"}`}>
                    {" "}
                    {inStock ? "in stock" : `${part.availability.lead_time_days} d lead time`}
                  </span>
                </>
              ) : (
                "—"
              )}
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
