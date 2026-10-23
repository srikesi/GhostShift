import type { IncidentView } from "../../api/types";
import { ProviderNote } from "../../components/ui";
import { humanize } from "../../lib/format";

/** Everything an engineer might want to audit, kept out of the way by default. */
export function DetailsPanel({ view }: { view: IncidentView }) {
  const inc = view.incident;
  const hyp = inc.diagnostics.hypotheses[0];
  const p = inc.prognostics;
  const run = view.latest_run;
  return (
    <details className="panel details-panel">
      <summary>How GhostShift decided</summary>
      <div className="panel-body stack small">
        {hyp && (
          <section>
            <h3>Fault pattern</h3>
            <p className="muted">
              {hyp.name} ({Math.round(hyp.confidence * 100)}% of the rule matched).
            </p>
            <ul className="clean mono xs conditions">
              {hyp.matched_conditions.map((c) => (
                <li key={c}>✓ {c}</li>
              ))}
              {hyp.unmatched_conditions.map((c) => (
                <li key={c} className="muted">
                  – {c}
                </li>
              ))}
              {hyp.contradicting_conditions.map((c) => (
                <li key={c} className="warn-text">
                  ✕ {c}
                </li>
              ))}
            </ul>
          </section>
        )}
        <section>
          <h3>Priority</h3>
          <ul className="bullets muted">
            {inc.safety.rationale.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3>Time-to-limit estimate</h3>
          <p className="muted">
            Straight-line trend of the last 6 hours, extended to the danger limit. The range covers the uncertainty in that
            trend.{p.rul && !p.rul.supportable ? ` ${p.rul.confidence_note}` : ""}
          </p>
          <ul className="bullets muted">
            {p.limitations.map((l) => (
              <li key={l}>{l}</li>
            ))}
          </ul>
        </section>
        <section>
          <h3>Safety</h3>
          <ul className="bullets muted">
            {inc.safety.safety_notices.map((n) => (
              <li key={n}>{n}</li>
            ))}
          </ul>
        </section>
        {run && (
          <section>
            <h3>Steps</h3>
            <ol className="clean trace">
              {run.stages.map((s, i) => (
                <li key={`${s.name}-${i}`} className={`stage ${s.status}`}>
                  <span className="dot" aria-hidden />
                  <span>{humanize(s.name)}</span>
                  {s.status !== "success" && <span className="xs muted">{humanize(s.status)}</span>}
                  <span className="spacer" />
                  <ProviderNote provider={s.provider} status={s.status} />
                  <span className="mono xs muted">{s.duration_ms.toFixed(1)} ms</span>
                  {(s.error || s.fallback_reason) && (
                    <span className="detail xs">{[s.fallback_reason, s.error].filter(Boolean).join(" — ")}</span>
                  )}
                </li>
              ))}
            </ol>
          </section>
        )}
      </div>
    </details>
  );
}
