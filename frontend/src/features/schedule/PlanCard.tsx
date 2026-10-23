import { useEffect, useState } from "react";
import { ops, type PhonePlan } from "../../api/ops";
import { SimTag } from "../../components/ui";
import { fmtDateTime, fmtTime } from "../../lib/format";

/** Phone page: when the job is booked, who is on it, and whether the part has arrived. */
export function PlanCard({ token }: { token: string }) {
  const [plan, setPlan] = useState<PhonePlan | null>(null);
  useEffect(() => {
    ops.plan(token).then(setPlan, () => setPlan(null));
  }, [token]);
  if (!plan || (!plan.booking && !plan.order)) return null;
  const b = plan.booking;
  const o = plan.order;
  const here = o && (o.status === "reserved" || o.status === "received" || o.status === "issued");
  return (
    <section className="m-card" aria-label="Schedule">
      <div className="row">
        <h2>Scheduled work</h2>
        <span className="spacer" />
        <SimTag title="Simulated calendar" />
      </div>
      {b ? (
        <>
          <p className="strong">
            {fmtDateTime(b.start)} to {fmtTime(b.end)}
          </p>
          <p className="small">
            {b.technician_name} · {b.status === "confirmed" ? "Confirmed" : "Held until the work order is approved"}
          </p>
          <a className="btn sm" href={ops.icsUrl(b.id)} download>
            Add to my calendar
          </a>
        </>
      ) : (
        <p className="small muted">No time is booked yet.</p>
      )}
      {o && (
        <p className="small">
          Part {o.sku}: {here ? "in the storeroom" : `arrives ${o.eta ? fmtDateTime(o.eta) : "on an unknown date"}`}
          {o.kind === "reservation" && o.storeroom ? ` (${o.storeroom})` : ""}
        </p>
      )}
    </section>
  );
}
