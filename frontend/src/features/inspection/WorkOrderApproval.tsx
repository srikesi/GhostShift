import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { phone, type PhoneWorkOrder } from "../../api/ops";
import { Icon } from "../../components/ui";

const ROLE_LABEL: Record<string, string> = { maintenance_supervisor: "Maintenance supervisor", operations_manager: "Operations manager" };

/** Phone page: approve (or reject) the work order, then release it. Same checks as the dashboard. */
export function WorkOrderApproval({ token, onChanged }: { token: string; onChanged?: () => void }) {
  const [data, setData] = useState<PhoneWorkOrder | null>(null);
  const [name, setName] = useState("");
  const [role, setRole] = useState<string | null>(null);
  const [attest, setAttest] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(() => phone.workOrder(token).then(setData, () => setData(null)), [token]);
  useEffect(() => {
    load();
  }, [load]);

  if (!data) return null;
  const act = data.action;
  const pending = act.approvals.filter((a) => a.decision === "pending").map((a) => a.role);
  const activeRole = role && pending.includes(role as never) ? role : (pending[0] ?? null);

  const run = async (fn: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    try {
      await fn();
      await load();
      onChanged?.();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="m-card" aria-label="Work order approval">
      <h2>Work order approval</h2>
      {data.title && <p className="small strong">{data.title}</p>}
      <ul className="clean wo-approvals">
        {act.approvals.map((a) => (
          <li key={a.role} className="small">
            <span>{ROLE_LABEL[a.role] ?? a.role}</span>
            <span className="spacer" />
            <span className={a.decision === "approved" ? "conn-live" : a.decision === "rejected" ? "warn-text" : "muted"}>
              {a.decision === "pending" ? "Waiting" : a.decision === "approved" ? `Approved by ${a.decided_by}` : `Rejected by ${a.decided_by}`}
            </span>
          </li>
        ))}
      </ul>

      {act.status === "awaiting_approval" && activeRole && (
        <div className="m-form">
          {pending.length > 1 && (
            <select aria-label="Approving as" value={activeRole} onChange={(e) => setRole(e.target.value)}>
              {pending.map((r) => (
                <option key={r} value={r}>
                  {ROLE_LABEL[r] ?? r}
                </option>
              ))}
            </select>
          )}
          <input aria-label="Your name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" maxLength={80} autoComplete="name" />
          {act.requires_isolation_attestation && (
            <label className="attest small">
              <input type="checkbox" checked={attest} onChange={(e) => setAttest(e.target.checked)} />
              <span>Lockout/tagout will be done and checked by qualified staff before work starts.</span>
            </label>
          )}
          <p className="xs muted">Approving records a decision. It does not stop or make the machine safe.</p>
          <div className="row">
            <button
              className="btn primary"
              disabled={busy || name.trim().length < 2}
              onClick={() => run(() => phone.decide(token, { role: activeRole, approver_name: name.trim(), decision: "approve", isolation_attestation: attest }))}
            >
              Approve
            </button>
            <button
              className="btn"
              disabled={busy || name.trim().length < 2}
              onClick={() => run(() => phone.decide(token, { role: activeRole, approver_name: name.trim(), decision: "reject", isolation_attestation: false }))}
            >
              Reject
            </button>
          </div>
        </div>
      )}

      {act.status === "approved" && (
        <div className="m-form">
          <input aria-label="Your name" value={name} onChange={(e) => setName(e.target.value)} placeholder="Your name" maxLength={80} autoComplete="name" />
          <button className="btn primary" disabled={busy || name.trim().length < 2} onClick={() => run(() => phone.release(token, name.trim()))}>
            Release work order
          </button>
        </div>
      )}
      {(act.status === "completed" || act.status === "completed_simulated") && (
        <p className="small">
          <Icon name="check" /> Released · <span className="mono">{act.external_reference}</span>
        </p>
      )}
      {act.status === "rejected" && <p className="small muted">Rejected. The work order will not be released.</p>}
      {error && (
        <div className="notice error xs" role="alert">
          {error}
        </div>
      )}
    </section>
  );
}
