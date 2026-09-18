"""Association & context search — completing the reasoning chain (spec 3.3).

Given one entity, these return *what it depends on*, *what depends on it*, *what to
look at next*, and *the shape of its module*. Output is structured graphs / snapshots
rather than a flat hit list, because the caller's next step is usually another query
fed by these results.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Set

from ..models import EntityType


# --------------------------------------------------------------------------- #
# Dependency expansion
# --------------------------------------------------------------------------- #
def _deps_of(index, name: str, only_mathlib: bool) -> List[str]:
    enr = index._enriched.get(name, {})
    direct = list(enr.get("dependencies", []) or [])
    if not direct:
        # coarse fallback: the module this entity lives in imports these modules
        meta = index._meta.get(name)
        if meta:
            direct = [m for m in index.imports_of(meta.module)]
    if only_mathlib:
        direct = [d for d in direct if d.startswith("Mathlib.")]
    # keep only known declarations
    return [d for d in direct if d in index._meta]


def expand_dependencies(
    index,
    full_name: str,
    *,
    depth: int = 2,
    exclude_stdlib: bool = False,
    only_mathlib: bool = True,
    as_tree: bool = True,
) -> Dict:
    """Return direct/recursive dependencies up to ``depth``.

    Uses true per-declaration dependencies when enriched; otherwise falls back to
    the module import graph (coarse). ``as_tree`` yields a nested structure, else a
    flat de-duplicated list with depth annotations.
    """
    if full_name not in index._meta:
        return {"error": "not_found", "name": full_name}

    tree: Dict = {}
    flat: List[Dict] = []
    visited: Set[str] = set()

    def rec(name: str, cur_depth: int, node: Dict) -> None:
        if cur_depth > depth or name in visited:
            return
        visited.add(name)
        deps = _deps_of(index, name, only_mathlib)
        node["dependencies"] = []
        for d in deps:
            child = {"name": d, "depth": cur_depth}
            meta = index._meta.get(d)
            if meta:
                child["entity_type"] = meta.entity_type.value
                child["module"] = meta.module
            node["dependencies"].append(child)
            flat.append(child)
            rec(d, cur_depth + 1, child)

    root = {"name": full_name, "depth": 0}
    meta = index._meta.get(full_name)
    if meta:
        root["entity_type"] = meta.entity_type.value
        root["module"] = meta.module
    rec(full_name, 1, root)

    if as_tree:
        return {"root": root, "total_nodes": len(visited), "mode": "tree",
                "source": "enriched" if index._enriched else "module-import-graph"}
    return {"root": {"name": full_name}, "flat": flat, "total_nodes": len(visited),
            "mode": "flat", "source": "enriched" if index._enriched else "module-import-graph"}


# --------------------------------------------------------------------------- #
# Usage / reference backtracking
# --------------------------------------------------------------------------- #
def find_usages(
    index,
    full_name: str,
    *,
    direct_only: bool = False,
    transitive: bool = True,
) -> Dict:
    """Return declarations / modules that reference ``full_name``.

    ``direct`` = declarations whose enriched dependency list contains the name;
    ``impact_modules`` = modules that import the owning module (coarse blast radius).
    """
    if full_name not in index._meta:
        return {"error": "not_found", "name": full_name}

    direct: List[str] = []
    if index._enriched:
        for name, enr in index._enriched.items():
            if full_name in (enr.get("dependencies", []) or []):
                direct.append(name)
    indirect = list(direct)
    if transitive and not direct_only:
        # one level of indirection: things depending on the direct users
        seen = set(direct)
        for d in list(direct):
            for name, enr in index._enriched.items():
                if name in seen:
                    continue
                if d in (enr.get("dependencies", []) or []):
                    indirect.append(name)
                    seen.add(name)

    meta = index._meta[full_name]
    impact_modules = index.imported_by_of(meta.module)
    return {
        "target": full_name,
        "direct": direct,
        "indirect": list(set(indirect)) if transitive else None,
        "impact_modules": impact_modules,
        "direct_count": len(direct),
        "impact_module_count": len(impact_modules),
        "source": "enriched" if index._enriched else "module-import-graph",
    }


# --------------------------------------------------------------------------- #
# Proximity / recommendation
# --------------------------------------------------------------------------- #
def recommend_related(index, full_name: str, *, limit: int = 15) -> Dict:
    """Return high-association items: same-module pairings, duals, generalizations."""
    if full_name not in index._meta:
        return {"error": "not_found", "name": full_name}
    meta = index._meta[full_name]
    enr = index._enriched.get(full_name, {})

    same_module = [
        n for n in index.module_members(meta.module)
        if n != full_name and index._meta[n].usage_frequency >= 1
    ]
    # prefer core + high-usage same-module items
    same_module.sort(key=lambda n: index._meta[n].usage_frequency, reverse=True)
    same_module = same_module[:limit]

    duals, generalizations, specializations, related = [], [], [], []
    if enr:
        duals = list(enr.get("equivalents", []) or [])
        generalizations = list(enr.get("generalizes", []) or [])
        specializations = list(enr.get("specializes", []) or [])
        related = list(enr.get("related", []) or [])

    # if this name is a typeclass, recommend its other instances
    other_instances: List[str] = []
    tc = index.instance_to_typeclass.get(full_name)
    if meta.entity_type == EntityType.TYPECLASS or full_name in index.instances_for:
        other_instances = index.instances_for_typeclass(full_name)[:limit]

    return {
        "target": full_name,
        "same_module_core": same_module,
        "equivalents": duals,
        "generalizations": generalizations,
        "specializations": specializations,
        "related": related,
        "other_instances_of_typeclass": other_instances,
    }


# --------------------------------------------------------------------------- #
# Module snapshot
# --------------------------------------------------------------------------- #
def module_snapshot(index, module: str) -> Dict:
    """Return a layered snapshot of a module for quick AI orientation (spec 3.3)."""
    m = index.get_module(module)
    if m is None:
        return {"error": "not_found", "module": module}
    members = index.module_members(module)
    # split exported by priority tier (usage / core)
    intro, core, advanced = [], [], []
    for n in members:
        meta = index._meta[n]
        if meta.usage_frequency >= 10 or meta.is_core:
            core.append(n)
        elif meta.usage_frequency >= 1:
            advanced.append(n)
        else:
            intro.append(n)
    # key instances: typeclasses defined in this module -> their instances
    key_instances: Dict[str, List[str]] = {}
    for n in members:
        if index._meta[n].entity_type == EntityType.TYPECLASS:
            key_instances[n] = index.instances_for_typeclass(n)
    return {
        "module": module,
        "domain": m.domain.value,
        "priority_tier": m.priority_tier,
        "imports": m.imports,
        "imported_by_count": len(m.imported_by),
        "exported_total": len(members),
        "tiers": {
            "intro": intro[:30],
            "core": core[:40],
            "advanced": advanced[:30],
        },
        "key_instances": key_instances,
        "doc_link": m.doc_link,
    }
