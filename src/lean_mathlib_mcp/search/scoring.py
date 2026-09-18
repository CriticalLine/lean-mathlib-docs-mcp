"""Relevance scoring (spec section 6 quality guarantees).

Ranking priority, exactly as specified:
    name-match precision  ->  structure-match degree  ->  domain closeness
    ->  community usage frequency  ->  maintenance stability.

Each component is normalized to 0..1 and the weighted combination is returned
alongside the *best* match tier so callers can filter on precision if they wish.
"""
from __future__ import annotations

from typing import List, Tuple

from ..domain import is_mathlib
from ..models import Domain, MatchTier

# Weights sum to 1.0; order encodes the spec's priority.
_W_NAME = 0.45
_W_STRUCT = 0.20
_W_DOMAIN = 0.15
_W_USAGE = 0.10
_W_STABILITY = 0.10


def _name_score(query_lower: str, name_lower: str) -> Tuple[float, MatchTier]:
    """Lexical name precision. Returns (score, tier)."""
    if name_lower == query_lower:
        return 1.0, MatchTier.EXACT
    # exact short-name match (last dotted segment)
    short = name_lower.rsplit(".", 1)[-1]
    if short == query_lower:
        return 0.85, MatchTier.STRUCTURAL
    # full name contains the query as a segment
    if query_lower in name_lower.split("."):
        return 0.7, MatchTier.STRUCTURAL
    # substring anywhere
    if query_lower in name_lower:
        ratio = len(query_lower) / max(1, len(name_lower))
        return min(0.6, 0.25 + ratio * 0.5), MatchTier.FUZZY
    return 0.0, MatchTier.NONE


def _domain_closeness(a: Domain, b: Domain) -> float:
    if a == b:
        return 1.0
    if a == Domain.OTHER or b == Domain.OTHER:
        return 0.3
    return 0.0


def _usage_proxy(freq: int) -> float:
    return min(1.0, freq / 40.0)


def _stability(deprecated: bool) -> float:
    return 0.3 if deprecated else 1.0


def score_candidate(
    query_lower: str,
    name: str,
    *,
    structure: float = 0.0,
    domain: Domain = Domain.OTHER,
    query_domain: Domain = Domain.OTHER,
    usage: int = 0,
    deprecated: bool = False,
) -> Tuple[float, MatchTier]:
    """Combine all ranking components into a final 0..1 score and best tier."""
    name_s, name_tier = _name_score(query_lower, name.lower())
    dom_s = _domain_closeness(domain, query_domain)
    usage_s = _usage_proxy(usage)
    stab_s = _stability(deprecated)

    total = (
        _W_NAME * name_s
        + _W_STRUCT * structure
        + _W_DOMAIN * dom_s
        + _W_USAGE * usage_s
        + _W_STABILITY * stab_s
    )
    # best tier across contributing dimensions
    tier = name_tier
    if structure >= 0.99 and tier != MatchTier.EXACT:
        tier = MatchTier.EXACT if name_tier == MatchTier.EXACT else MatchTier.UNIFIABLE
    elif structure >= 0.6 and tier in (MatchTier.FUZZY, MatchTier.NONE):
        tier = MatchTier.STRUCTURAL
    return round(total, 4), tier


def rank_and_sort(
    candidates: List,  # List[Candidate]
) -> List:
    candidates.sort(key=lambda c: c.score, reverse=True)
    return candidates
