import type { Incident, WorkOrder } from "../../api/types";
import { Icon } from "../../components/ui";
import { fmtDateTime } from "../../lib/format";

interface Props {
  incident: Incident;
  workOrder: WorkOrder | null;
  machineLabel: string;
  componentName: string;
}

/** Step-by-step replacement guide for the technician, with a link to how-to videos. */
export function RepairGuide({ incident, workOrder, machineLabel, componentName }: Props) {
  const m = incident.maintenance;
  if (!m) return null;
  const wo = m.work_order;
  const part = m.proposed_part;
  const w = m.maintenance_window;
  // A search, not a specific video: we don't vouch for third-party content.
  const query = `${wo.title.split(" — ")[0]} ${machineLabel}`;
  const videoUrl = `https://www.youtube.com/results?search_query=${encodeURIComponent(query)}`;

  return (
    <section className="m-card guide">
      <h2>How to fix it</h2>
      <p className="small strong">{wo.title.split(" — ")[0]}</p>
      <dl className="part-facts">
        <div>
          <dt>Time</dt>
          <dd>about {wo.estimated_duration_hours} h</dd>
        </div>
        <div>
          <dt>When</dt>
          <dd>{w ? `${w.label}, ${fmtDateTime(w.start)}` : "Not scheduled yet"}</dd>
        </div>
        {part && (
          <div>
            <dt>Part</dt>
            <dd>
              <span className="mono">{part.sku}</span>
              <div className="xs muted">
                {(part.availability.on_hand ?? 0) > 0
                  ? `${part.availability.on_hand} at ${part.availability.location}`
                  : `${part.availability.lead_time_days} day lead time`}
              </div>
            </dd>
          </div>
        )}
        <div>
          <dt>Who</dt>
          <dd>{wo.required_skills.join(", ")}</dd>
        </div>
      </dl>

      {workOrder?.status === "awaiting_approval" && (
        <p className="xs warn-text">Waiting for supervisor approval. Don't start yet.</p>
      )}

      <ol className="m-steps small">
        {wo.tasks.map((t) => (
          <li key={t.step}>
            {t.description}
            {t.requires_qualified_person && <span className="xs muted"> (qualified staff)</span>}
          </li>
        ))}
      </ol>

      <a className="btn video-btn" href={videoUrl} target="_blank" rel="noreferrer">
        <Icon name="play" /> Watch how-to videos
      </a>
      <p className="xs muted">
        Opens a YouTube search for “{query}”. Videos are general guidance for the {componentName.toLowerCase()}; follow the
        OEM manual and your site procedure.
      </p>
      <p className="xs muted">References: {wo.safety_references.join(" · ")}</p>
    </section>
  );
}
