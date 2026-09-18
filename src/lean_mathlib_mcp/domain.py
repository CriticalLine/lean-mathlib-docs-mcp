"""Domain classification and intent-tag heuristics.

These are *deterministic, explainable* derivations from the module path and
declaration name. They are deliberately conservative: when evidence is weak a tag
is omitted rather than guessed, so the domain+use filter never returns false
positives that would mislead an AI caller.
"""
from __future__ import annotations

from typing import List, Optional, Tuple

from .models import Domain, UseTag

# Map the first Mathlib namespace segment to a top-level field.
_DOMAIN_MAP = {
    "Algebra": Domain.ALGEBRA,
    "Analysis": Domain.ANALYSIS,
    "NumberTheory": Domain.NUMBER_THEORY,
    "Topology": Domain.TOPOLOGY,
    "Logic": Domain.LOGIC,
    "Order": Domain.ORDER,
    "CategoryTheory": Domain.CATEGORY_THEORY,
    "GroupTheory": Domain.GROUP_THEORY,
    "MeasureTheory": Domain.MEASURE_THEORY,
    "LinearAlgebra": Domain.LINEAR_ALGEBRA,
    "Data": Domain.DATA,
    "Computability": Domain.COMPUTABILITY,
    "SetTheory": Domain.SET_THEORY,
    "Tactic": Domain.TACTIC,
}

# Subdomain hints from the second segment.
_SUBDOMAIN_HINTS = {
    "Group": "Group",
    "Ring": "Ring",
    "Field": "Field",
    "Module": "Module",
    "Algebra": "Algebra",
    "Real": "Real",
    "Complex": "Complex",
    "NNReal": "NNReal",
    "ENNReal": "ENNReal",
    "Interval": "Interval",
    "Measure": "Measure",
    "Integral": "Integral",
    "Deriv": "Derivative",
    "Asymptotics": "Asymptotics",
    "Finset": "Finset",
    "Fintype": "Fintype",
    "List": "List",
    "Set": "Set",
    "Nat": "Nat",
    "Int": "Int",
    "Rat": "Rat",
    "Prime": "Prime",
    "Padics": "PAdics",
    "BigOperators": "BigOperators",
    "Category": "Category",
    "Limits": "Limits",
}


def classify_domain(module: str) -> Tuple[Domain, Optional[str]]:
    """Return (top-level domain, subdomain) for a module/declaration path.

    Mathlib modules are namespaced as ``Mathlib.<Field>.<Subfield>...`` (or
    ``Init.<Field>...`` for the core). The first segment is the root namespace, so
    the primary field is the *second* segment.
    """
    parts = [p for p in module.split(".") if p]
    if not parts:
        return Domain.OTHER, None
    # Drop the root namespace (Mathlib / Init) to reach the first field segment.
    if parts[0] in ("Mathlib", "Init"):
        parts = parts[1:]
    if not parts:
        return Domain.OTHER, None
    top = _DOMAIN_MAP.get(parts[0], Domain.OTHER)
    sub = None
    if len(parts) >= 2:
        sub = _SUBDOMAIN_HINTS.get(parts[1])
    return top, sub


def is_mathlib(full_name: str) -> bool:
    """True if the declaration belongs to Mathlib (vs Lean core / stdlib)."""
    return full_name.startswith("Mathlib.")


# Name-suffix -> use tag heuristics. Order matters: first match wins per group.
_TAG_RULES: List[Tuple[str, UseTag]] = [
    ("_decide", UseTag.DECIDE),
    ("decide", UseTag.DECIDE),
    ("decidable", UseTag.DECIDE),
    ("_equiv", UseTag.EQUIV),
    ("equiv", UseTag.EQUIV),
    ("iso", UseTag.ISO),
    ("_iso", UseTag.ISO),
    ("_le", UseTag.UPPER_BOUND),
    ("_lt", UseTag.UPPER_BOUND),
    ("_ge", UseTag.LOWER_BOUND),
    ("_gt", UseTag.LOWER_BOUND),
    ("_lower", UseTag.LOWER_BOUND),
    ("_upper", UseTag.UPPER_BOUND),
    ("mono", UseTag.MONOTONICITY),
    ("continuous", UseTag.CONTINUITY),
    ("_mk", UseTag.CONSTRUCT),
    ("of_", UseTag.CONSTRUCT),
    ("construct", UseTag.CONSTRUCT),
    ("_simp", UseTag.SIMPLIFY),
    ("simp", UseTag.SIMPLIFY),
    ("_mem", UseTag.MEMBERSHIP),
    ("mem", UseTag.MEMBERSHIP),
    ("_characterization", UseTag.CHARACTERIZATION),
    ("characterization", UseTag.CHARACTERIZATION),
    ("rec", UseTag.RECURSIVE),
]


def derive_use_tags(full_name: str, raw_kind: str, module: str) -> List[UseTag]:
    """Heuristically derive intent tags from name + kind + module placement."""
    tags: set[UseTag] = set()
    low = full_name.lower()
    for needle, tag in _TAG_RULES:
        if needle in low:
            tags.add(tag)
    # Structurally: theorems about equations are often simplifiers / characterizations.
    if raw_kind in ("theorem", "lemma"):
        if "eq" in low and tags == set():
            tags.add(UseTag.SIMPLIFY)
    if raw_kind in ("def", "abbrev", "structure", "inductive", "opaque", "class"):
        tags.add(UseTag.CONSTRUCT)
    return sorted(tags, key=lambda t: t.value)
