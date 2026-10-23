from .conftest import CH, CRAH


def test_floorplan_marks_monitored_machines_and_links_pairs(client):
    p = client.get("/api/floorplan").json()
    ids = {u["id"]: u for u in p["units"]}
    assert ids[CRAH]["machine_id"] == CRAH and ids[CH]["machine_id"] == CH
    assert ids["MF-08"]["machine_id"] is None and ids["C1"]["machine_id"] is None
    assert {(l["a"], l["b"]) for l in p["links"]} == {("MF-07", "MF-08"), ("CH-02", "CH-03")}
    assert all(l["a"] in ids and l["b"] in ids for l in p["links"])
