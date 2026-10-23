import { useState } from "react";
import { ApiError } from "../../api/client";
import type { ApproverRole, DecisionRequest, IncidentView, ProposedAction } from "../../api/types";
import { Icon, Panel, SimTag } from "../../components/ui";
import { fmtUsd, roleLabel } from "../../lib/format";

interface Props {
  view: IncidentView;
  onDecide: (actionId: string, body: DecisionRequest) => Promise<void>;
  onExecute: (actionId: string) => Promise<void>;
}

export function ApprovalsPanel({ view, onDecide, onExecute }: Props) {
  const pending = view.actions.filter((a) => a.status === "awaiting_approval").length;
  return (
    <Panel title="Approvals" id="approvals" actions={pending ? <span className="count">{pending} waiting</span> : null}>
      <div className="stack">
        {view.actions.length === 0 && <p className="small muted">Nothing needs approval yet.</p>}
        {view.actions.map((a) => (
          <ActionCard key={a.id} action={a} view={view} onDecide={onDecide} onExecute={onExecute} />
        ))}
        {view.actions.length > 0 && (
          <p className="xs muted">Approving records a decision. It does not order parts or stop the machine.</p>
        )}
      </div>
    </Panel>
  );
}

function describe(action: ProposedAction, view: IncidentView) {
  if (action.kind === "submit_requisition") {
    const r = view.requisition;
    return {
      title: r ? `Order ${r.quantity}× ${r.sku}` : "Order part",
      sub: r ? `${fmtUsd(r.estimated_cost_usd)} · ${r.description}` : "",
      send: "Send order",
      simulated: r?.simulated ?? true,
    };
  }
  const w = view.work_order;
  return {
    title: w ? `Release work order ${w.id}` : "Release work order",
    sub: w?.title ?? "",
    send: "Send to maintenance queue",
    simulated: w?.simulated ?? true,
  };
}

function ActionCard({ action, view, onDecide, onExecute }: { action: ProposedAction } & Omit<Props, "view"> & { view: IncidentView }) {
  const pendingRoles = action.approvals.filter((r) => r.decision === "pending").map((r) => r.role);
  const [role, setRole] = useState<ApproverRole | undefined>(pendingRoles[0]);
  const [name, setName] = useState("");
  const [attest, setAttest] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const activeRole = role && pendingRoles.includes(role) ? role : pendingRoles[0];
  const d = describe(action, view);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setAttest(false);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };
  const decide = (decision: "approve" | "reject") =>
    run(() =>
      onDecide(action.id, {
        role: activeRole!,
        approver_name: name.trim() || "Demo approver",
        decision,
        isolation_attestation: attest,
      }),
    );

  const decided = action.approvals.filter((r) => r.decision !== "pending");
  return (
    <article className={`action-card status-${action.status}`}>
      <div className="small strong">{d.title}</div>
      {d.sub && <div className="xs muted">{d.sub}</div>}

      {decided.length > 0 && (
        <ul className="clean decisions xs">
          {decided.map((r) => (
            <li key={r.role} className={`decision-${r.decision}`}>
              <Icon name={r.decision === "approved" ? "check" : "x"} />{" "}
              {r.automated
                ? `Approved automatically by autopilot (${r.note ?? "within policy"})`
                : `${r.decision === "approved" ? "Approved" : "Rejected"} by ${r.decided_by} (${roleLabel[r.role].toLowerCase()})`}
            </li>
          ))}
        </ul>
      )}

      {action.status === "awaiting_approval" && activeRole && (
        <div className="decision-form">
          <div className="row wrap">
            {pendingRoles.length > 1 ? (
              <select aria-label="Approving as" value={activeRole} onChange={(e) => setRole(e.target.value as ApproverRole)}>
                {pendingRoles.map((r) => (
                  <option key={r} value={r}>
                    {roleLabel[r]}
                  </option>
                ))}
              </select>
            ) : (
              <span className="xs muted">Needs: {roleLabel[activeRole].toLowerCase()}</span>
            )}
            <input aria-label="Your name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" maxLength={80} />
          </div>
          {action.requires_isolation_attestation && (
            <label className="attest small">
              <input type="checkbox" checked={attest} onChange={(e) => setAttest(e.target.checked)} />
              <span>Lockout/tagout will be done and checked by qualified staff before work starts.</span>
            </label>
          )}
          <div className="row">
            <button className="btn primary" disabled={busy} onClick={() => decide("approve")}>
              Approve
            </button>
            <button className="btn" disabled={busy} onClick={() => decide("reject")}>
              Reject
            </button>
          </div>
        </div>
      )}

      {action.status === "approved" && (
        <div className="row">
          <button className="btn primary" disabled={busy} onClick={() => run(() => onExecute(action.id))}>
            {d.send}
          </button>
          {d.simulated && <SimTag title="Nothing is sent to a real system" />}
        </div>
      )}

      {(action.status === "completed_simulated" || action.status === "completed") && (
        <div className="row xs">
          <Icon name="check" />
          <span>
            Sent · <span className="mono">{action.external_reference}</span>
          </span>
          {action.status === "completed_simulated" && <SimTag title={action.result_note ?? undefined} />}
        </div>
      )}
      {action.status === "rejected" && <div className="xs muted">Rejected. Nothing will be sent.</div>}
      {error && (
        <div className="notice error xs" role="alert">
          {error}
        </div>
      )}
    </article>
  );
}
