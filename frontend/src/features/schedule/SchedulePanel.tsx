import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { ops, type Booking, type CallView, type ScheduleProposal } from "../../api/ops";
import type { IncidentView } from "../../api/types";
import { Icon, Panel, SimTag } from "../../components/ui";
import { fmtDateTime, fmtTime } from "../../lib/format";
import "./schedule.css";

/** When GhostShift plans to do the work, who does it, and why. Held at once; confirmed only after approval. */
export function SchedulePanel({ view, refreshKey, onChanged }: { view: IncidentView; refreshKey: string; onChanged: () => void }) {
  const wo = view.work_order;
  const incidentId = view.incident.id;
  const [booking, setBooking] = useState<Booking | null>(null);
  const [proposal, setProposal] = useState<ScheduleProposal | null>(null);
  const [call, setCall] = useState<CallView | null>(null);
  const [reply, setReply] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!wo) return;
    const [b, p, cs] = await Promise.all([ops.bookings(incidentId), ops.propose(wo.id), ops.calls(incidentId)]);
    setBooking(b[0] ?? null);
    setProposal(p);
    setCall(cs[cs.length - 1] ?? null);
  }, [wo, incidentId]);

  useEffect(() => {
    load().catch((e) => setError(String(e)));
  }, [load, refreshKey]);

  if (!wo) return null;

  const act = async (fn: () => Promise<unknown>) => {
    setError(null);
    try {
      await fn();
      await load();
      onChanged();
    } catch (e) {
      const details = e instanceof ApiError ? (e.details as { reasons?: string[] } | undefined)?.reasons : undefined;
      setError(details?.length ? `${(e as ApiError).message}: ${details.join("; ")}` : e instanceof ApiError ? e.message : String(e));
    }
  };

  const confirmed = booking?.status === "confirmed";
  const others = (proposal?.alternatives ?? []).filter((a) => a.window_label);
  return (
    <Panel
      title={
        <>
          Schedule <SimTag title="Simulated calendar" />
        </>
      }
      id="schedule"
      actions={
        booking && (
          <a className="btn sm" href={ops.icsUrl(booking.id)} download>
            Add to calendar
          </a>
        )
      }
    >
      <div className="stack">
        {booking ? (
          <div className="slot">
            <div className="row">
              <Icon name="clock" />
              <span className="strong">
                {fmtDateTime(booking.start)} to {fmtTime(booking.end)}
              </span>
              <span className="spacer" />
              <span className={`tag ${confirmed ? "real" : "derived"}`}>{confirmed ? "Confirmed" : "Tentative hold"}</span>
            </div>
            <p className="small">
              {booking.technician_name} · {booking.window_label}
            </p>
            <p className="xs muted">
              {confirmed
                ? "Confirmed because the work order was approved."
                : "Held for now. It is confirmed only after the work order is approved."}
            </p>
            <details>
              <summary className="small">Why this slot</summary>
              <ul className="small bullets">
                {booking.rationale.map((r) => (
                  <li key={r}>{r}</li>
                ))}
              </ul>
            </details>
          </div>
        ) : (
          proposal?.status === "no_fit" && (
            <div className="notice small" role="alert">
              <Icon name="alert" />
              <span>{proposal.warnings.join(" ")}</span>
            </div>
          )
        )}

        {proposal && proposal.constraints.part_ready && (
          <p className="xs muted">Part arrives {fmtDateTime(proposal.constraints.part_ready)}. The job must start after that.</p>
        )}

        {others.length > 0 && (
          <details>
            <summary className="small">
              Other windows GhostShift checked ({others.length})
            </summary>
            <ul className="clean alt-list">
              {others.map((a) => (
                <li key={a.window_start} className={a.feasible ? "ok" : ""}>
                  <div className="row small">
                    <span className="strong">{a.window_label}</span>
                    <span className="spacer" />
                    <span className="xs muted">{fmtDateTime(a.window_start)}</span>
                  </div>
                  <ul className="xs muted bullets">
                    {a.reasons.map((r) => (
                      <li key={r}>{r}</li>
                    ))}
                  </ul>
                  {a.feasible && a.start && booking && (
                    <button className="btn sm" onClick={() => act(() => ops.reschedule(booking.id, a.start!))}>
                      Move here
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </details>
        )}

        {booking && (
          <div className="row">
            <button className="btn sm" onClick={() => act(() => ops.cancel(booking.id))}>
              Release slot
            </button>
          </div>
        )}
        {!booking && proposal?.status === "fits" && (
          <button className="btn sm" onClick={() => act(() => ops.hold(wo.id))}>
            Hold the best slot
          </button>
        )}
        <section aria-label="Scheduling call" className="call-box">
          <div className="row">
            <Icon name="phone" />
            <span className="small strong">Scheduling call</span>
            {call?.simulated && <SimTag title="Recorded, nobody is phoned" />}
            <span className="spacer" />
            {(!call || call.status === "completed" || call.status === "failed") && (
              <button className="btn sm" onClick={() => act(() => ops.startCall(incidentId))}>
                {call ? "Call again" : "Call to schedule"}
              </button>
            )}
          </div>
          {!call && <p className="xs muted">GhostShift phones the scheduler contact, offers the checked slots and books the one they agree to.</p>}
          {call && (
            <>
              <p className="xs muted">
                {call.to_masked} · {call.status === "queued" ? "ringing" : call.status.replace("_", " ")}
                {call.outcome ? ` · ${call.outcome.replace("_", " ")}` : ""}
                {call.confirmed ? " · slot confirmed by Autopilot" : call.outcome === "accepted" ? " · held until the work order is approved" : ""}
              </p>
              {call.error && <p className="xs warn-text">{call.error}</p>}
              <ol className="clean transcript">
                {call.transcript.map((t, i) => (
                  <li key={i} className={t.who}>
                    <span className="xs muted">{t.who === "agent" ? "GhostShift" : "Caller"}</span>
                    <span className="small">{t.text}</span>
                  </li>
                ))}
              </ol>
              {call.simulated && call.status === "in_progress" && (
                <form
                  className="row reply"
                  onSubmit={(e) => {
                    e.preventDefault();
                    const text = reply;
                    setReply("");
                    act(() => ops.say(call.id, text));
                  }}
                >
                  <input value={reply} onChange={(e) => setReply(e.target.value)} placeholder="Type the caller's reply, e.g. Saturday" aria-label="Caller's reply" />
                  <button className="btn sm" type="submit">
                    Say
                  </button>
                </form>
              )}
            </>
          )}
        </section>

        {error && (
          <div className="notice small" role="alert">
            <Icon name="alert" />
            <span>{error}</span>
          </div>
        )}
      </div>
    </Panel>
  );
}
