"""Mock inventory: reservation, supplier choice, purchase-order progression, issue, reorder."""

from __future__ import annotations

from .conftest import CH, CRAH, seek


def open_incident(client, cursor=216, machine=CRAH):
    return seek(client, machine, cursor)["triggered_incident_id"]


def actions(client, iid):
    v = client.get(f"/api/incidents/{iid}").json()
    return {a["kind"]: a for a in v["actions"]}, v


def approve(client, act, role="maintenance_supervisor", attest=False):
    r = client.post(f"/api/actions/{act['id']}/decision", json={
        "role": role, "approver_name": "Test", "decision": "approve", "isolation_attestation": attest})
    assert r.status_code == 200, r.text


def send_order(client, iid):
    acts, _ = actions(client, iid)
    approve(client, acts["submit_requisition"])
    r = client.post(f"/api/actions/{acts['submit_requisition']['id']}/execute")
    assert r.status_code == 200, r.text
    return r.json()


def stock(client, sku):
    return next(s for s in client.get("/api/inventory").json()["stock"] if s["sku"] == sku)


def test_no_purchase_order_until_the_order_is_sent(client):
    open_incident(client)
    assert client.get("/api/inventory/orders").json()[0]["id"] == "PO-SEED-01"  # only the seeded restock
    assert len(client.get("/api/inventory/orders").json()) == 1


def test_on_hand_stock_is_reserved_not_ordered(client):
    iid = open_incident(client)
    done = send_order(client, iid)
    po = client.get(f"/api/inventory/orders/{done['external_reference']}").json()
    assert po["kind"] == "reservation" and po["status"] == "reserved" and po["supplier_id"] is None
    s = stock(client, "GS-BRG-FAN-KIT")
    assert (s["on_hand"], s["reserved"], s["available"]) == (2, 1, 1)
    assert "Reserved" in " ".join(e["text"] for e in client.get(f"/api/incidents/{iid}").json()["activity"])


def test_out_of_stock_picks_cheapest_supplier_that_arrives_in_time(client, container):
    container.inventory._stock["GS-BRG-FAN-KIT"]["on_hand"] = 0
    iid = open_incident(client)
    po = client.get(f"/api/inventory/orders/{send_order(client, iid)['external_reference']}").json()
    # National OEM is cheapest ($226) but takes 4 days; the earliest limit is about 33 h away.
    assert po["kind"] == "supplier" and po["supplier_id"] == "SUP-LSI" and po["unit_price_usd"] == 240.0
    assert any("National OEM" in r and "after the earliest limit" in r for r in po["choice_reasons"])
    assert po["status"] == "ordered"


def test_without_a_deadline_the_cheapest_supplier_wins(client, container):
    container.inventory._stock["GS-BRG-FAN-KIT"]["on_hand"] = 0
    iid = open_incident(client)
    inc = container.store.incidents[iid]
    container.store.incidents[iid] = inc.model_copy(update={"prognostics": inc.prognostics.model_copy(update={"rul": None})})
    po = client.get(f"/api/inventory/orders/{send_order(client, iid)['external_reference']}").json()
    assert po["supplier_id"] == "SUP-NOP" and po["unit_price_usd"] == 226.0


def test_order_progresses_and_stock_arrives_on_the_clock(client, container):
    container.inventory._stock["GS-BRG-FAN-KIT"]["on_hand"] = 0
    iid = open_incident(client)
    po_id = send_order(client, iid)["external_reference"]
    seen = []
    for _ in range(4):
        client.post("/api/inventory/advance", json={"hours": 10})
        seen.append(client.get(f"/api/inventory/orders/{po_id}").json()["status"])
    assert seen[0] in ("ordered", "confirmed", "shipped") and seen[-1] == "received"
    order = ["ordered", "confirmed", "shipped", "received"]
    assert [order.index(s) for s in seen] == sorted(order.index(s) for s in seen)
    s = stock(client, "GS-BRG-FAN-KIT")
    assert (s["on_hand"], s["reserved"]) == (1, 1)  # arrived and held for this work order
    kinds = [e["kind"] for e in client.get(f"/api/incidents/{iid}").json()["activity"]]
    assert {"po_confirmed", "po_shipped", "po_received"} <= set(kinds)


def test_releasing_the_work_order_issues_the_part_and_suggests_a_reorder(client):
    iid = open_incident(client)
    send_order(client, iid)
    acts, _ = actions(client, iid)
    approve(client, acts["dispatch_work_order"], attest=True)
    r = client.post(f"/api/actions/{acts['dispatch_work_order']['id']}/execute")
    assert r.status_code == 200, r.text
    s = stock(client, "GS-BRG-FAN-KIT")
    assert (s["on_hand"], s["reserved"], s["below_min"]) == (1, 0, True)
    sug = client.get("/api/inventory/reorder-suggestions").json()
    assert [x["sku"] for x in sug] == ["GS-BRG-FAN-KIT"] and sug[0]["suggested_qty"] == 4
    po = client.get("/api/inventory/orders", params={"incident_id": iid}).json()[0]
    assert po["status"] == "issued"
    texts = " ".join(e["text"] for e in client.get(f"/api/incidents/{iid}").json()["activity"])
    assert "Issued 1 × GS-BRG-FAN-KIT" in texts and "reorder suggested" in texts


def test_part_ordered_from_supplier_is_issued_when_it_arrives_after_release(client, container):
    container.inventory._stock["GS-BRG-FAN-KIT"]["on_hand"] = 0
    iid = open_incident(client)
    po_id = send_order(client, iid)["external_reference"]
    acts, _ = actions(client, iid)
    approve(client, acts["dispatch_work_order"], attest=True)
    client.post(f"/api/actions/{acts['dispatch_work_order']['id']}/execute")
    assert client.get(f"/api/inventory/orders/{po_id}").json()["status"] != "issued"
    client.post("/api/inventory/advance", json={"hours": 72})
    assert client.get(f"/api/inventory/orders/{po_id}").json()["status"] == "issued"
    assert stock(client, "GS-BRG-FAN-KIT")["on_hand"] == 0


def test_seed_restock_order_is_received_on_the_clock(client):
    before = stock(client, "GS-FLT-M8-SET")["on_hand"]
    client.post("/api/inventory/advance", json={"hours": 24 * 10})
    assert stock(client, "GS-FLT-M8-SET")["on_hand"] == before + 6
    assert client.get("/api/inventory/orders/PO-SEED-01").json()["status"] == "received"


def test_autopilot_order_creates_a_purchase_order(client):
    client.put("/api/autonomy", json={"level": "autopilot"})
    iid = open_incident(client)
    po = client.get("/api/inventory/orders", params={"incident_id": iid}).json()
    assert len(po) == 1 and po[0]["id"].startswith("SIM-PO-")
    assert client.get(f"/api/incidents/{iid}").json()["requisition"]["external_reference"] == po[0]["id"]


def test_catalog_availability_follows_live_stock(client, container):
    container.inventory._stock["GS-BRG-FAN-KIT"]["on_hand"] = 0
    v = client.get(f"/api/incidents/{open_incident(client)}").json()
    assert v["incident"]["maintenance"]["proposed_part"]["availability"]["on_hand"] == 0


def test_reset_restores_stock_and_orders(client):
    iid = open_incident(client)
    send_order(client, iid)
    client.post("/api/demo/reset")
    s = stock(client, "GS-BRG-FAN-KIT")
    assert (s["on_hand"], s["reserved"]) == (2, 0)
    assert [o["id"] for o in client.get("/api/inventory/orders").json()] == ["PO-SEED-01"]


def test_fixture_stock_matches_parts_catalog(container):
    for part in container.parts._parts:
        row = container.inventory.stock_for(part.sku)
        assert row is not None and row["on_hand"] == part.availability.on_hand, part.sku
