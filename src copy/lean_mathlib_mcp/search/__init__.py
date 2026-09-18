"""Search capability package (spec section 3).

Every search path returns :class:`Candidate` rows (a name + relevance evidence).
The output layer turns candidates into paginated, granularity-rendered
:class:`SearchHit` / :class:`SearchResult` envelopes. Keeping search results as
plain candidates decouples ranking from presentation and makes batching trivial.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Tuple

from ..models import MatchTier


@dataclass
class Candidate:
    """One unscored-yet-ranked match produced by a search path."""

    name: str
    score: float
    tier: MatchTier
    dimensions: List[Tuple[str, float, MatchTier]] = field(default_factory=list)


# Query-control fields shared by every tool (spec 4.3).
CONTROL_KEYS = (
    "granularity",
    "max_results",
    "min_score",
    "token_budget",
    "scope_modules",       # restrict to these modules/namespaces
    "exclude_modules",
    "mathlib_only",
    "exclude_deprecated",
    "only_stable",         # merged/stable only
    "cursor",
)


def parse_controls(args: dict) -> dict:
    """Extract and normalize the shared control parameters from a tool call."""
    ctl = {}
    for k in CONTROL_KEYS:
        if k in args and args[k] is not None:
            ctl[k] = args[k]
    ctl.setdefault("granularity", None)
    ctl.setdefault("max_results", None)
    ctl.setdefault("min_score", 0.0)
    ctl.setdefault("token_budget", None)
    ctl.setdefault("scope_modules", None)
    ctl.setdefault("exclude_modules", None)
    ctl.setdefault("mathlib_only", None)
    ctl.setdefault("exclude_deprecated", None)
    ctl.setdefault("only_stable", None)
    ctl.setdefault("cursor", None)
    return ctl


def in_scope(index, name: str, ctl: dict) -> bool:
    """Apply scope / exclusion / mathlib-only / deprecated filters (spec 4.3)."""
    meta = index._meta.get(name)
    if meta is None:
        return False
    if ctl.get("mathlib_only"):
        if not meta.is_mathlib:
            return False
    scope = ctl.get("scope_modules")
    if scope:
        if not any(name.startswith(s) or meta.module.startswith(s) for s in scope):
            return False
    excl = ctl.get("exclude_modules")
    if excl:
        if any(name.startswith(s) or meta.module.startswith(s) for s in excl):
            return False
    if ctl.get("exclude_deprecated") and meta.has_enrichment:
        enr = index._enriched.get(name, {})
        if enr.get("deprecated"):
            return False
    if ctl.get("only_stable") and meta.entity_type.value == "unknown":
        return False
    return True
