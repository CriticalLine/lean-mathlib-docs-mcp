"""Index integrity tests."""
from lean_mathlib_mcp import server
from lean_mathlib_mcp.models import EntityType

IDX = server.get_index()


def test_index_populated():
    assert IDX.count() > 1000
    assert IDX.module_count() > 50
    assert len(IDX.notations) > 20


def test_get_entity_resolves_record():
    e = IDX.get_entity("Nat.add_comm")
    assert e is not None
    assert e.entity_type == EntityType.THEOREM
    assert e.type_signature is not None  # enriched in sample


def test_domain_classification():
    e = IDX.get_entity("Nat.add_comm")
    # Nat.add_comm lives in Init.Data.Nat.Basic -> classified via the Data field.
    from lean_mathlib_mcp.models import Domain

    assert isinstance(e.domain, Domain)


def test_notation_lookup():
    from lean_mathlib_mcp.search.identity import search_notation

    hits = search_notation(IDX.notations, "≤")
    assert any(h.symbol == "≤" for h in hits)


def test_module_members_and_snapshot():
    snap = server._dispatch("module_snapshot", {"module": "Mathlib.Algebra.Group.Basic"})
    assert "exported_total" in snap
    assert snap["exported_total"] > 0
