import type { Component, ComponentHealth } from "../../api/types";
import { SeverityPill } from "../../components/ui";
import { fmtHours, rulRange } from "../../lib/format";

interface Props {
  components: Component[];
  health: Record<string, ComponentHealth | undefined>;
  affectedId: string | null;
  selectedId: string | null;
  onSelect?: (id: string) => void;
}

export function ComponentHealthTable({ components, health, affectedId, selectedId, onSelect }: Props) {
  return (
    <table className="data components">
      <thead>
        <tr>
          <th className="n">#</th>
          <th>Part</th>
          <th>Condition</th>
          <th title="Estimated from the sensor trend, only when a part is deviating">Time to limit</th>
          <th title="From the maintenance schedule">Service due</th>
        </tr>
      </thead>
      <tbody>
        {components.map((c, i) => {
          const h = health[c.id];
          const due = h?.remaining_service_interval.value_hours ?? null;
          return (
            <tr
              key={c.id}
              className={`${onSelect ? "clickable" : ""} ${c.id === selectedId ? "selected" : ""} ${c.id === affectedId ? "affected" : ""}`}
              onClick={() => onSelect?.(c.id)}
              aria-selected={onSelect ? c.id === selectedId : undefined}
            >
              <td className="n mono xs">{i + 1}</td>
              <td>
                <div className="part-name">{c.name}</div>
                {h && h.status !== "normal" && <div className="xs muted">{h.summary}</div>}
              </td>
              <td>
                {h?.basis === "interval_only" ? (
                  <span className="xs muted" title="This part has no sensors">No sensors</span>
                ) : (
                  <SeverityPill severity={h?.status ?? "normal"} />
                )}
              </td>
              <td className="mono xs" title={h?.rul?.basis_note}>
                {h?.rul?.supportable ? <span className="strong">{rulRange(h.rul)}</span> : <span className="muted">—</span>}
              </td>
              <td className={`mono xs ${due !== null && due < 0 ? "warn-text" : ""}`}>{fmtHours(due)}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}
