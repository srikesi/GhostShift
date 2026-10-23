import type { ActivityEvent, IncidentView } from "../../api/types";
import { Panel } from "../../components/ui";
import { fmtTick, fmtUsd } from "../../lib/format";

/** Everything that happened on this problem, and who did it: GhostShift, the auto-order policy or a person. */
export function ActivityPanel({ view }: { view: IncidentView }) {
  const events = view.activity;
  const byGhostShift = events.filter((e) => e.actor !== "person").length;
  const byPeople = events.filter((e) => e.actor === "person").length;
  const waiting = view.actions.filter((a) => a.status === "awaiting_approval" || a.status === "approved");

  return (
    <Panel
      title="What GhostShift did"
      id="activity"
      actions={
        <span className="xs muted">
          <strong className="ink">{byGhostShift}</strong> on its own · <strong className="ink">{byPeople}</strong> by people
        </span>
      }
    >
      <ol className="clean activity">
        {events.map((e) => (
          <li key={e.id}>
            <span className="mono xs muted when">{e.machine_time ? fmtTick(e.machine_time) : ""}</span>
            <Actor e={e} />
            <span className="small what">{e.text}</span>
          </li>
        ))}
        {waiting.map((a) => (
          <li key={a.id} className="waiting">
            <span className="mono xs muted when">now</span>
            <span className="actor person">You</span>
            <span className="small what">
              {a.status === "approved" ? "Send " : "Approve "}
              {a.kind === "submit_requisition"
                ? `the order for ${view.requisition?.sku ?? "the part"} (${fmtUsd(view.requisition?.estimated_cost_usd)})`
                : `work order ${a.target_id} (lockout/tagout sign-off)`}
            </span>
          </li>
        ))}
      </ol>
    </Panel>
  );
}

function Actor({ e }: { e: ActivityEvent }) {
  if (e.actor === "ghostshift") return <span className="actor ghostshift">GhostShift</span>;
  if (e.actor === "policy") return <span className="actor policy" title={e.actor_name}>Autopilot</span>;
  return <span className="actor person">{e.actor_name}</span>;
}
