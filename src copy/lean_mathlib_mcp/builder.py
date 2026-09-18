"""Index builder & sample-fixture generator (spec 5.1 caching / offline demo).

* ``build``       download + parse the production master index and cache a built
                  index for fast startup.
* ``sample``      extract a domain-diverse, *real* subset of the master index into
                  ``data/sample_index.json`` so the server runs fully offline and
                  deterministically. A curated set of famous declarations is enriched
                  with true type signatures / statements / dependencies so the
                  signature & dependency features are demonstrable without the full
                  docgen export.
* ``info``        print index health for the active data source.

Usage::

    python -m lean_mathlib_mcp.builder sample
    python -m lean_mathlib_mcp.builder build
    python -m lean_mathlib_mcp.builder info
"""
from __future__ import annotations

import json
import os
import sys

# Make the package importable when run as a script.
_HERE = os.path.dirname(os.path.abspath(__file__))
_SRC = os.path.dirname(_HERE)
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from .config import get_settings  # noqa: E402
from .index import _module_from_doc_link  # noqa: E402
from .sources.master_index import ensure_raw_index, parse_bmp  # noqa: E402

# Real, representative Mathlib 4 modules spanning the primary fields.
MODULES_OF_INTEREST = {
    "Mathlib.Algebra.Group.Basic",
    "Mathlib.Algebra.Group.Defs",
    "Mathlib.Algebra.Group.Pow",
    "Mathlib.Algebra.Ring.Basic",
    "Mathlib.Algebra.Ring.Defs",
    "Mathlib.Algebra.Module.Basic",
    "Mathlib.Algebra.Field.Basic",
    "Mathlib.Data.Nat.Basic",
    "Mathlib.Data.Int.Basic",
    "Mathlib.Data.Rat.Basic",
    "Mathlib.Data.Real.Basic",
    "Mathlib.Data.List.Basic",
    "Mathlib.Data.List.Append",
    "Mathlib.Data.Finset.Basic",
    "Mathlib.Data.Finset.BigOperators.Basic",
    "Mathlib.Data.Set.Basic",
    "Mathlib.Data.Fin.Basic",
    "Mathlib.Order.Basic",
    "Mathlib.Order.Lemmas",
    "Mathlib.Topology.Basic",
    "Mathlib.Analysis.NormedSpace.Basic",
    "Mathlib.Analysis.Normed.Field.Basic",
    "Mathlib.NumberTheory.Prime.Basic",
    "Mathlib.CategoryTheory.Category.Basic",
    "Mathlib.LinearAlgebra.Basic",
    "Mathlib.GroupTheory.Subgroup.Basic",
    "Mathlib.MeasureTheory.MeasureSpace.Basic",
}

# Curated true enrichment for famous declarations (real Mathlib 4 types/statements).
ENRICHED = {
    "Nat.add": {"type_signature": "ℕ → ℕ → ℕ", "doc": "Addition on the natural numbers."},
    "Nat.add_comm": {
        "type_signature": "∀ (n m : ℕ), n + m = m + n",
        "statement": "∀ (n m : ℕ), n + m = m + n",
        "dependencies": ["Nat.add"],
    },
    "Nat.add_assoc": {
        "type_signature": "∀ (n m k : ℕ), n + m + k = n + (m + k)",
        "statement": "∀ (n m k : ℕ), n + m + k = n + (m + k)",
        "dependencies": ["Nat.add"],
    },
    "Nat.mul_comm": {
        "type_signature": "∀ (n m : ℕ), n * m = m * n",
        "statement": "∀ (n m : ℕ), n * m = m * n",
        "dependencies": ["Nat.mul"],
    },
    "Nat.zero_add": {
        "type_signature": "∀ (n : ℕ), 0 + n = n",
        "statement": "∀ (n : ℕ), 0 + n = n",
        "dependencies": ["Nat.add", "Nat.zero"],
    },
    "Nat.add_zero": {
        "type_signature": "∀ (n : ℕ), n + 0 = n",
        "statement": "∀ (n : ℕ), n + 0 = n",
        "dependencies": ["Nat.add", "Nat.zero"],
    },
    "List.length": {"type_signature": "List α → ℕ", "doc": "Length of a list."},
    "List.append": {"type_signature": "List α → List α → List α", "doc": "List concatenation."},
    "List.append_assoc": {
        "type_signature": "∀ (as bs cs : List α), as ++ bs ++ cs = as ++ (bs ++ cs)",
        "statement": "∀ (as bs cs : List α), as ++ bs ++ cs = as ++ (bs ++ cs)",
        "dependencies": ["List.append"],
    },
    "Finset.sum": {
        "type_signature": "Finset ι → (ι → α) → α",
        "doc": "Sum of a function over a finite set (requires an additive monoid).",
    },
    "MulZeroClass.zero_mul": {
        "type_signature": "∀ {M : Type} [MulZeroClass M] (a : M), 0 * a = 0",
        "statement": "∀ {M : Type} [MulZeroClass M] (a : M), 0 * a = 0",
        "dependencies": ["MulZeroClass"],
    },
    "MulZeroClass.mul_zero": {
        "type_signature": "∀ {M : Type} [MulZeroClass M] (a : M), a * 0 = 0",
        "statement": "∀ {M : Type} [MulZeroClass M] (a : M), a * 0 = 0",
        "dependencies": ["MulZeroClass"],
    },
    "LE.le": {"type_signature": "α → α → Prop", "doc": "Less-than-or-equal relation."},
    "Add.add": {"type_signature": "α → α → α", "doc": "Typeclass for addition."},
    "One.one": {"type_signature": "α", "doc": "Typeclass for the multiplicative unit."},
}


def build_sample(settings, cap_per_module: int = 300) -> str:
    raw = ensure_raw_index(settings)
    bundle = parse_bmp(raw)
    print(f"parsed master index: {len(bundle.declarations)} declarations")

    # Modules we definitely want, including the home modules of curated enrichments.
    interest = set(MODULES_OF_INTEREST)
    for k in ENRICHED:
        if k in bundle.declarations:
            mod = _module_from_doc_link(bundle.declarations[k].get("doc_link")) or k.rsplit(".", 1)[0]
            interest.add(mod)

    # 1) slice declarations per module of interest
    chosen: list[str] = []
    per_mod: dict[str, list[str]] = {}
    for name, d in bundle.declarations.items():
        mod = _module_from_doc_link(d.get("doc_link")) or name.rsplit(".", 1)[0]
        if mod in interest:
            lst = per_mod.setdefault(mod, [])
            if len(lst) < cap_per_module:
                lst.append(name)
    for lst in per_mod.values():
        chosen.extend(lst)

    sample_decl = {n: bundle.declarations[n] for n in chosen}

    # 1b) force-include the curated enriched declarations even if their module hit the cap
    for k in ENRICHED:
        if k in bundle.declarations and k not in sample_decl:
            sample_decl[k] = bundle.declarations[k]

    # 2) modules: selected + their real imports (inverted imported_by)
    mods: dict[str, dict] = {}
    for m in interest:
        if m in bundle.modules:
            mods[m] = bundle.modules[m]
    for m in list(mods.keys()):
        imps = [x for x, d in bundle.modules.items() if m in d.get("imported_by", [])]
        for x in imps:
            mods.setdefault(x, bundle.modules[x])

    # 3) instances / instancesFor touching the sample
    sample_set = set(sample_decl)
    inst_out = {
        k: v for k, v in bundle.instances.items() if k in sample_set or any(i in sample_set for i in v[:3])
    }
    inf_out = {
        k: v for k, v in bundle.instances_for.items()
        if k in sample_set or any(i in sample_set for i in v[:3])
    }

    # 4) enrichment (curated true detail)
    enriched = {k: v for k, v in ENRICHED.items() if k in sample_set}

    payload = {
        "meta": {
            "source": "sample",
            "built_from": "declaration-data.bmp",
            "mathlib_version": "4.latest",
            "declaration_count": len(sample_decl),
            "module_count": len(mods),
            "enriched_count": len(enriched),
        },
        "declarations": sample_decl,
        "modules": mods,
        "instances": inst_out,
        "instancesFor": inf_out,
        "enriched": enriched,
    }
    out = settings.resolve(settings.sample_path)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"wrote sample fixture -> {out} ({len(sample_decl)} decls, {len(mods)} modules)")
    return out


def build_index_cache(settings) -> str:
    from .sources.master_index import MasterIndexSource

    src = MasterIndexSource(settings, mode="remote")
    bundle = src.load()  # triggers download + cache
    print("built/cached index:", settings.resolve(settings.built_index_path))
    return settings.resolve(settings.built_index_path)


def info(settings) -> None:
    from .index import MathlibIndex
    from .sources.master_index import MasterIndexSource

    bundle = MasterIndexSource(settings).load()
    idx = MathlibIndex(bundle)
    idx.notations = []  # notations not needed for health
    print(json.dumps(idx.summary(), ensure_ascii=False, indent=2))


def main(argv: list[str]) -> None:
    settings = get_settings()
    cmd = (argv[1] if len(argv) > 1 else "info").lower()
    if cmd == "sample":
        build_sample(settings)
    elif cmd == "build":
        build_index_cache(settings)
    elif cmd == "info":
        info(settings)
    else:
        print("usage: builder.py [sample|build|info]")
        raise SystemExit(2)


if __name__ == "__main__":
    main(sys.argv)
