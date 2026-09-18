"""Offline smoke test: drives every tool through _dispatch in sample mode."""
import os
import sys
import json
from pathlib import Path

# sample mode + src on path
os.environ["LEAN_MATHLIB_DATA_SOURCE"] = "sample"
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from lean_mathlib_mcp import server  # noqa: E402


def run(tool, **args):
    return server._dispatch(tool, args)


def main():
    print("=== index_info ===")
    print(json.dumps(run("index_info"), ensure_ascii=False)[:300])

    print("\n=== search_declaration 'add' (mathlib_only) ===")
    r = run("search_declaration", query="add", max_results=5)
    print("total", r["total_matches"], "returned", r["returned"])
    for h in r["hits"][:5]:
        print(" ", h["entity"]["full_name"], round(h["score"], 3), h["tier"])

    print("\n=== get_entity Nat.add_comm (complete) ===")
    e = run("get_entity", full_name="Nat.add_comm", granularity="complete")
    print(json.dumps(e, ensure_ascii=False)[:400])

    print("\n=== search_by_notation '≤' ===")
    n = run("search_by_notation", symbol="≤")
    print("matches", n.get("total_matches"), [x["symbol"] for x in n.get("notations", [])][:3])

    print("\n=== search_by_domain_use domain=Algebra use_tags=[simplify] ===")
    d = run("search_by_domain_use", domain="Algebra", use_tags=["simplify"], max_results=3)
    print("total", d["total_matches"], "returned", d["returned"])

    print("\n=== search_by_signature arity=2 return_type='ℕ' (needs enrichment) ===")
    s = run("search_by_signature", arity=2, return_type="ℕ", max_results=5)
    print("keys:", list(s.keys())[:4], "| degraded?" , "code" in s)

    print("\n=== expand_dependencies Nat.add_comm depth=2 ===")
    ed = run("expand_dependencies", full_name="Nat.add_comm", depth=2)
    print("total_nodes", ed.get("total_nodes"), "source", ed.get("source"))

    print("\n=== find_usages Nat.add ===")
    fu = run("find_usages", full_name="Nat.add")
    print("direct", fu.get("direct_count"), "impact_modules", fu.get("impact_module_count"))

    print("\n=== recommend_related Nat.add_comm ===")
    rr = run("recommend_related", full_name="Nat.add_comm")
    print("same_module_core count", len(rr.get("same_module_core", [])))

    print("\n=== module_snapshot Mathlib.Data.Nat.Basic ===")
    ms = run("module_snapshot", module="Mathlib.Data.Nat.Basic")
    print("exported_total", ms.get("exported_total"), "tiers", {k: len(v) for k, v in ms.get("tiers", {}).items()})

    print("\n=== search_modules 'Group' ===")
    sm = run("search_modules", query="Group", max_results=5)
    print("modules", [m["full_name"] for m in sm.get("modules", [])][:5])

    print("\n=== batch_query ===")
    b = run("batch_query", queries=[
        {"tool": "search_declaration", "args": {"query": "mul", "max_results": 2}},
        {"tool": "get_entity", "args": {"full_name": "Nat.mul_comm"}},
    ])
    print("count", b["count"], "errors", b["errors"])

    print("\nALL SMOKE CHECKS RAN OK")


if __name__ == "__main__":
    main()
