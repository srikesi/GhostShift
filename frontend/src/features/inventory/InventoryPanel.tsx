import { useCallback, useEffect, useState } from "react";
import { ApiError } from "../../api/client";
import { ops, type InventoryView, type POStatus, type PurchaseOrder } from "../../api/ops";
import { Panel, SimTag } from "../../components/ui";
import { fmtDateTime, fmtUsd } from "../../lib/format";
import "./inventory.css";

const STEPS: { id: POStatus; label: string }[] = [
  { id: "ordered", label: "Ordered" },
  { id: "confirmed", label: "Confirmed" },
  { id: "shipped", label: "Shipped" },
  { id: "received", label: "Received" },
];

/** Stock in the storerooms, purchase orders and what to reorder. Everything here is simulated. */
export function InventoryPanel({ refreshKey, highlightSku }: { refreshKey: string; highlightSku?: string | null }) {
  const [inv, setInv] = useState<InventoryView | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => ops.inventory().then(setInv), []);
  useEffect(() => {
    load().then(() => setError(null), (e) => setError(e instanceof ApiError ? e.message : String(e)));
  }, [load, refreshKey]);

  const skip = async (hours: number) => {
    setBusy(true);
    try {
      setInv(await ops.advance(hours));
    } catch (e) {
      setError(e instanceof ApiError ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const open = inv?.open_orders.filter((o) => o.status !== "issued" && o.status !== "cancelled") ?? [];
  const done = inv?.open_orders.filter((o) => o.status === "issued") ?? [];
  return (
    <Panel
      title={
        <>
          Inventory <SimTag title="Simulated stock, suppliers and orders. Nothing is ordered from a real vendor." />
        </>
      }
      id="inventory"
      actions={
        <button className="btn sm" disabled={busy} onClick={() => skip(24)} title="Moves the supply clock forward so orders can arrive">
          Skip ahead 1 day
        </button>
      }
    >
      {error && <p className="small muted">{error}</p>}
      {inv && (
        <div className="stack">
          {inv.as_of && <p className="xs muted">Supply clock: {fmtDateTime(inv.as_of)}</p>}
          <div className="table-scroll">
            <table className="inv-table">
              <thead>
                <tr>
                  <th>Part</th>
                  <th>Storeroom</th>
                  <th className="num">On hand</th>
                  <th className="num">Held</th>
                  <th className="num">Min</th>
                </tr>
              </thead>
              <tbody>
                {inv.stock.map((s) => (
                  <tr key={s.sku + s.storeroom} className={s.sku === highlightSku ? "hl" : ""}>
                    <td>
                      <span className="mono small">{s.sku}</span>
                      <span className="xs muted block">{s.description}</span>
                    </td>
                    <td className="small">{s.storeroom}</td>
                    <td className="num">{s.on_hand}</td>
                    <td className="num">{s.reserved || "–"}</td>
                    <td className="num">
                      {s.min || "–"}
                      {s.below_min && <span className="tag warn low">Low</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <section aria-label="Orders">
            <h3 className="eyebrow">Orders</h3>
            {open.length === 0 && <p className="small muted">No open orders.</p>}
            <ul className="clean orders">
              {open.map((o) => (
                <Order key={o.id} o={o} />
              ))}
              {done.map((o) => (
                <Order key={o.id} o={o} />
              ))}
            </ul>
          </section>

          {inv.reorder_suggestions.length > 0 && (
            <section aria-label="Reorder suggestions">
              <h3 className="eyebrow">Reorder suggestions</h3>
              <ul className="clean orders">
                {inv.reorder_suggestions.map((r) => (
                  <li key={r.sku} className="order">
                    <div className="row small">
                      <span className="mono">{r.sku}</span>
                      <span className="spacer" />
                      <span className="tag warn">Suggested</span>
                    </div>
                    <p className="xs muted">
                      {r.reason}. Order {r.suggested_qty}
                      {r.supplier_name ? ` from ${r.supplier_name} for about ${fmtUsd(r.estimated_cost_usd)}, ${r.lead_days} d` : ""}. A person decides.
                    </p>
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}
    </Panel>
  );
}

function Order({ o }: { o: PurchaseOrder }) {
  const reached = new Map(o.timeline.filter((t) => !t.planned).map((t) => [t.status, t]));
  const planned = new Map(o.timeline.filter((t) => t.planned).map((t) => [t.status, t]));
  return (
    <li className="order">
      <div className="row small">
        <span className="mono strong">{o.id}</span>
        <span className="small">
          {o.quantity} × <span className="mono">{o.sku}</span>
        </span>
        <span className="spacer" />
        <span className={`tag ${o.status === "received" || o.status === "issued" ? "real" : "derived"}`}>{label(o)}</span>
      </div>
      <p className="xs muted">
        {o.kind === "reservation"
          ? `Held from ${o.storeroom}. No supplier order needed.`
          : `${o.supplier_name} · ${fmtUsd(o.total_usd)} · ${o.status === "received" || o.status === "issued" ? "arrived" : `arrives ${o.eta ? fmtDateTime(o.eta) : "unknown"}`}`}
      </p>
      {o.kind === "supplier" && (
        <ol className="po-steps" aria-label="Order progress">
          {STEPS.map((s) => {
            const at = reached.get(s.id) ?? planned.get(s.id);
            return (
              <li key={s.id} className={reached.has(s.id) ? "done" : ""} title={at ? `${at.note}, ${fmtDateTime(at.at)}` : undefined}>
                <span className="dot" aria-hidden />
                <span className="xs">{s.label}</span>
                {at && <span className="xs muted">{fmtDateTime(at.at).replace(" UTC", "")}</span>}
              </li>
            );
          })}
        </ol>
      )}
      {o.choice_reasons.length > 0 && (
        <details>
          <summary className="xs">Why this supplier</summary>
          <ul className="xs muted bullets">
            {o.choice_reasons.map((r) => (
              <li key={r}>{r}</li>
            ))}
          </ul>
        </details>
      )}
    </li>
  );
}

function label(o: PurchaseOrder): string {
  const map: Record<POStatus, string> = {
    reserved: "Reserved",
    ordered: "Ordered",
    confirmed: "Confirmed",
    shipped: "Shipped",
    received: "Received",
    issued: "Used on work order",
    cancelled: "Cancelled",
  };
  return map[o.status];
}
