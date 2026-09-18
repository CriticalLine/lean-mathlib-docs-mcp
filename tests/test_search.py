"""Search capability tests (spec sections 3.1 - 3.3)."""
from lean_mathlib_mcp import server


def _dispatch(tool, **args):
    return server._dispatch(tool, args)


def test_search_declaration_exact():
    r = _dispatch("search_declaration", query="Add", max_results=3)
    assert r["total_matches"] >= 1
    assert r["hits"][0]["entity"]["full_name"] == "Add"
    assert r["hits"][0]["tier"] == "exact"


def test_get_entity_not_found_is_structured_error():
    r = _dispatch("get_entity", full_name="Does.Not.Exist.At.All")
    assert r["code"] == "not_found"
    assert r["fixable"] is True
    assert "suggested_params" in r


def test_search_by_notation():
    r = _dispatch("search_by_notation", symbol="≤")
    assert r["total_matches"] >= 1
    assert any(n["symbol"] == "≤" for n in r["notations"])


def test_search_by_domain_use_algebra():
    r = _dispatch("search_by_domain_use", domain="Algebra", max_results=5)
    assert r["total_matches"] > 0
    assert r["returned"] <= 5


def test_search_by_signature_uses_enrichment():
    r = _dispatch("search_by_signature", arity=2, return_type="ℕ", max_results=10)
    # Nat.add / Nat.mul have type `ℕ → ℕ → ℕ` in the sample enrichment.
    names = [h["entity"]["full_name"] for h in r["hits"]]
    assert "Nat.add" in names


def test_search_by_signature_degrades_without_enrichment(monkeypatch):
    # Force an empty enrichment to confirm graceful degradation signal.
    import lean_mathlib_mcp.server as srv

    monkeypatch.setattr(srv.get_index(), "_enriched", {})
    r = _dispatch("search_by_signature", arity=2, return_type="ℕ")
    assert r["code"] == "enrichment_unavailable"


def test_expand_dependencies():
    r = _dispatch("expand_dependencies", full_name="Nat.add_comm", depth=2,
                  only_mathlib=False)
    assert r["source"] in ("enriched", "module-import-graph")
    assert "root" in r
    # Nat.add_comm depends on Nat.add (core, excluded under only_mathlib=True).
    assert r["total_nodes"] >= 1


def test_find_usages():
    r = _dispatch("find_usages", full_name="Nat.add")
    assert "direct" in r
    assert "impact_modules" in r


def test_recommend_related():
    r = _dispatch("recommend_related", full_name="Nat.add_comm")
    assert r["target"] == "Nat.add_comm"
    assert "same_module_core" in r


def test_module_snapshot_unknown_module_errors():
    r = _dispatch("module_snapshot", module="Nope.Nope")
    assert r["code"] == "not_found"


def test_search_modules():
    r = _dispatch("search_modules", query="Group", max_results=5)
    assert r["total_matches"] > 0
    assert all("Group" in m["full_name"] for m in r["modules"])


def test_batch_query():
    r = _dispatch("batch_query", queries=[
        {"tool": "search_declaration", "args": {"query": "mul", "max_results": 2}},
        {"tool": "get_entity", "args": {"full_name": "Nat.mul_comm"}},
    ])
    assert r["count"] == 2
    assert r["errors"] == []
