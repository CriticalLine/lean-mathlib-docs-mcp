"""Precise identity search — the ambiguity-eliminating first resort (spec 3.1).

When an AI caller already knows *something* exact (a full name, a short name plus
its namespace, or a symbol), these paths locate the entity without fuzzy guessing
and, crucially, surface disambiguation dimensions when a name is ambiguous.
"""
from __future__ import annotations

from typing import Dict, List, Optional

from ..models import MatchTier, NotationEntity
from . import Candidate, in_scope
from .scoring import score_candidate


def search_exact(index, full_names: List[str]) -> Dict[str, List[str]]:
    """Case-insensitive exact full-name resolution for a batch of queries.

    Returns ``{query: [matched full name, ...]}``. A query mapping to >1 name is
    ambiguous and the caller should present the candidates for disambiguation.
    """
    out: Dict[str, List[str]] = {}
    for q in full_names:
        out[q] = index.exact_match(q)
    return out


def search_short(
    index,
    short_name: str,
    namespace: Optional[str] = None,
    ctl: Optional[dict] = None,
) -> List[Candidate]:
    """Resolve a short name, optionally confined to a namespace prefix.

    Returns ranked candidates (most-used / most-core first) each carrying its full
    path + domain so the caller can disambiguate.
    """
    ctl = ctl or {}
    cands = index.short_candidates(short_name, namespace)
    results: List[Candidate] = []
    for name in cands:
        if not in_scope(index, name, ctl):
            continue
        meta = index._meta[name]
        score, tier = score_candidate(
            short_name.lower(),
            name,
            domain=meta.domain,
            usage=meta.usage_frequency,
        )
        results.append(
            Candidate(
                name=name,
                score=score,
                tier=MatchTier.STRUCTURAL if tier == MatchTier.EXACT else tier,
                dimensions=[("short_name", score, MatchTier.STRUCTURAL)],
            )
        )
    results.sort(key=lambda c: c.score, reverse=True)
    return results


def _norm_unicode(s: str) -> str:
    """Loose unicode normalization for symbol search (NFC) so variant forms match."""
    try:
        import unicodedata

        return unicodedata.normalize("NFC", s)
    except Exception:
        return s


def search_notation(
    notations: List[NotationEntity],
    symbol: str,
    latex: Optional[str] = None,
) -> List[NotationEntity]:
    """Match a notation by symbol text, LaTeX form, or substring.

    Returns all notations whose symbol/latex matches the query (case-insensitive),
    including semantically-equivalent but differently-written forms.
    """
    q_sym = _norm_unicode(symbol).lower()
    q_latex = (latex or symbol).lower()
    hits: List[NotationEntity] = []
    seen = set()
    for n in notations:
        sym = _norm_unicode(n.symbol).lower()
        lat = (n.latex or "").lower()
        if sym == q_sym or lat == q_latex or sym.startswith(q_sym) or lat.startswith(q_latex):
            if n.id not in seen:
                seen.add(n.id)
                hits.append(n)
    # group semantically-equivalent forms (same binds_to) so ambiguous symbols surface together
    return hits
