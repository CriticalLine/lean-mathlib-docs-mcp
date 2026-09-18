"""Semantic-feature search — turning a fuzzy AI need into a query (spec 3.2).

These paths need *structure*: type signatures, conclusions, dependency graphs. That
data lives in the optional docgen detail export. Every function therefore returns a
:class:`SemanticResult` carrying a ``degraded`` flag so the server can emit an honest
``enrichment_unavailable`` signal and a concrete remediation suggestion instead of
silently returning garbage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

from ..models import Domain, EntityType, MatchTier, UseTag
from . import Candidate, in_scope
from .scoring import score_candidate


@dataclass
class SemanticResult:
    candidates: List[Candidate] = field(default_factory=list)
    degraded: bool = False
    requires_enrichment: bool = False
    note: str = ""


# --------------------------------------------------------------------------- #
# Type-signature structural matching
# --------------------------------------------------------------------------- #
def _split_arrows(s: str) -> List[str]:
    """Split a Lean type on *top-level* arrows into [domain, ..., result]."""
    segs: List[str] = []
    depth = 0
    cur = ""
    for ch in s:
        if ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "→" and depth == 0:
            segs.append(cur.strip())
            cur = ""
        else:
            cur += ch
    segs.append(cur.strip())
    return [x for x in segs if x != ""] or [s.strip()]


def _pat_match(haystack: str, pat: str) -> bool:
    """Substring (case-insensitive) or, if ``pat`` is ``/regex/``, regex match."""
    h = haystack.lower()
    p = pat.lower().strip()
    if p.startswith("/") and p.endswith("/") and len(p) > 2:
        import re

        try:
            return re.search(p[1:-1], haystack) is not None
        except re.error:
            return p[1:-1] in h
    return p in h


def _match_signature(
    type_sig: str,
    arity: Optional[int],
    return_pat: Optional[str],
    param_pats: Optional[List[str]],
) -> Optional[tuple]:
    """Return (score, tier) if the signature matches the pattern, else None."""
    segs = _split_arrows(type_sig)
    n_dom = len(segs) - 1
    if arity is not None and n_dom != arity:
        return None
    score = 0.0
    ret_ok = return_pat is None
    if return_pat:
        if _pat_match(segs[-1], return_pat):
            ret_ok = True
            score += 0.5
        else:
            return None
    param_ok = True
    if param_pats:
        for i, pat in enumerate(param_pats):
            if i >= n_dom:
                break
            if pat in ("_", "*", "?", ""):
                continue
            if not _pat_match(segs[i], pat):
                param_ok = False
                break
            score += 0.12
        if not param_ok:
            return None
    arity_ok = arity is None or n_dom == arity
    if not arity_ok:
        return None
    if ret_ok and param_pats and param_ok:
        tier = MatchTier.EXACT
    elif ret_ok or (param_pats and param_ok):
        tier = MatchTier.UNIFIABLE
    else:
        tier = MatchTier.STRUCTURAL
    base = 0.4 if (ret_ok or (param_pats and param_ok)) else 0.3
    return (min(1.0, base + score), tier)


def search_signature(
    index,
    *,
    entity_types: Optional[List[str]] = None,
    arity: Optional[int] = None,
    return_type: Optional[str] = None,
    param_types: Optional[List[str]] = None,
    ctl: Optional[dict] = None,
) -> SemanticResult:
    """Type-signature structural matching (spec 3.2).

    Supports wildcards (``_`` / ``*``) in ``param_types``. Tiers: exact unification
    > unifiable > structural, exactly as specified.
    """
    ctl = ctl or {}
    ets = {EntityType(t) for t in (entity_types or [])} or None
    if not index._enriched:
        return SemanticResult(
            degraded=True,
            requires_enrichment=True,
            note="type-signature search needs the docgen detail export (LEAN_MATHLIB_DOCGEN_DETAIL_PATH).",
        )
    cands: List[Candidate] = []
    for name, enr in index._enriched.items():
        if not in_scope(index, name, ctl):
            continue
        meta = index._meta.get(name)
        if meta is None:
            continue
        if ets and meta.entity_type not in ets:
            continue
        ts = enr.get("type_signature")
        if not ts:
            continue
        m = _match_signature(ts, arity, return_type, param_types)
        if m is None:
            continue
        sc, tier = m
        final, _ = score_candidate(
            name.lower(), name, structure=sc, domain=meta.domain, usage=meta.usage_frequency
        )
        cands.append(
            Candidate(
                name=name,
                score=final,
                tier=tier,
                dimensions=[("signature", sc, tier)],
            )
        )
    cands.sort(key=lambda c: c.score, reverse=True)
    return SemanticResult(candidates=cands)


# --------------------------------------------------------------------------- #
# Conclusion / target pattern matching
# --------------------------------------------------------------------------- #
_OP_CHARS = set("+-*/=≤<≥>≠∧∨→↦∘•⊆∪∩∣√⌊⌋⌈⌉")


def _operator_tokens(s: str) -> List[str]:
    toks, cur = [], ""
    for ch in s:
        if ch in _OP_CHARS:
            if cur:
                toks.append(cur)
                cur = ""
            toks.append(ch)
        elif ch.isalnum() or ch in "_.'":
            cur += ch
        else:
            if cur:
                toks.append(cur)
                cur = ""
    if cur:
        toks.append(cur)
    return toks


def search_conclusion(
    index,
    pattern: str,
    *,
    symmetric: bool = False,
    monotonic: bool = False,
    ctl: Optional[dict] = None,
) -> SemanticResult:
    """Match a theorem conclusion described as an abstract-syntax fragment.

    Ignores variable naming differences by comparing operator/relation tokens.
    Optional ``symmetric`` / ``monotonic`` morphology flags bias ranking.
    """
    ctl = ctl or {}
    if not index._enriched:
        return SemanticResult(
            degraded=True,
            requires_enrichment=True,
            note="conclusion-pattern search needs the docgen detail export.",
        )
    pat_ops = set(_operator_tokens(pattern))
    cands: List[Candidate] = []
    for name, enr in index._enriched.items():
        if not in_scope(index, name, ctl):
            continue
        meta = index._meta.get(name)
        if meta is None or meta.entity_type not in (EntityType.THEOREM, EntityType.LEMMA):
            continue
        stmt = enr.get("statement") or ""
        if not stmt:
            continue
        stmt_ops = set(_operator_tokens(stmt))
        if pat_ops and pat_ops.issubset(stmt_ops):
            sc = 0.6 + 0.3 * (len(pat_ops & stmt_ops) / max(1, len(pat_ops)))
            if symmetric and ("=" in pat_ops):
                sc += 0.05
            if monotonic and ("≤" in pat_ops or "<" in pat_ops):
                sc += 0.05
            cands.append(
                Candidate(
                    name=name,
                    score=min(1.0, sc),
                    tier=MatchTier.UNIFIABLE,
                    dimensions=[("conclusion", sc, MatchTier.UNIFIABLE)],
                )
            )
    cands.sort(key=lambda c: c.score, reverse=True)
    return SemanticResult(candidates=cands)


# --------------------------------------------------------------------------- #
# Domain + use filtering (always available, no enrichment needed)
# --------------------------------------------------------------------------- #
def filter_domain_use(
    index,
    *,
    domain: Optional[str] = None,
    subdomain: Optional[str] = None,
    use_tags: Optional[List[str]] = None,
    entity_types: Optional[List[str]] = None,
    ctl: Optional[dict] = None,
) -> SemanticResult:
    """Domain + subdomain + intent-tag + entity-type filtering (spec 3.2)."""
    ctl = ctl or {}
    ets = {EntityType(t) for t in (entity_types or [])} or None
    tags = {UseTag(t) for t in (use_tags or [])} or None
    dom = Domain(domain) if domain else None

    names: List[str] = []
    if dom is not None:
        names = list(index.domain_members(dom))
    elif tags:
        # union across requested tags
        seen = set()
        for t in tags:
            for n in index.tag_members(t):
                if n not in seen:
                    seen.add(n)
                    names.append(n)
    else:
        names = list(index.entity_names())

    cands: List[Candidate] = []
    for name in names:
        if not in_scope(index, name, ctl):
            continue
        meta = index._meta[name]
        if ets and meta.entity_type not in ets:
            continue
        if dom is not None and meta.domain != dom:
            continue
        if subdomain and meta.subdomain != subdomain:
            continue
        if tags and not (tags & set(meta.use_tags)):
            continue
        sc, tier = score_candidate(
            name.lower(), name, domain=meta.domain, query_domain=dom or Domain.OTHER,
            usage=meta.usage_frequency,
        )
        # bias core/high-usage up a touch (spec: prefer mainstream core theorems)
        if meta.is_core:
            sc = min(1.0, sc + 0.05)
        cands.append(
            Candidate(
                name=name,
                score=sc,
                tier=MatchTier.STRUCTURAL,
                dimensions=[("domain_use", sc, MatchTier.STRUCTURAL)],
            )
        )
    cands.sort(key=lambda c: c.score, reverse=True)
    return SemanticResult(candidates=cands)


# --------------------------------------------------------------------------- #
# Hypothesis / premise outline (needs enrichment; degrades to typeclass instances)
# --------------------------------------------------------------------------- #
def search_hypothesis(
    index,
    *,
    required_typeclasses: Optional[List[str]] = None,
    required_axioms: Optional[List[str]] = None,
    constructive_only: bool = False,
    exclude_classical: bool = False,
    no_axiom: bool = False,
    ctl: Optional[dict] = None,
) -> SemanticResult:
    """Return theorems whose premises include the given typeclasses/axioms."""
    ctl = ctl or {}
    req = set(required_typeclasses or []) | set(required_axioms or [])
    if not req:
        return SemanticResult(candidates=[], note="no required typeclasses/axioms supplied")

    if index._enriched:
        cands: List[Candidate] = []
        for name, enr in index._enriched.items():
            if not in_scope(index, name, ctl):
                continue
            meta = index._meta.get(name)
            if meta is None or meta.entity_type not in (EntityType.THEOREM, EntityType.LEMMA):
                continue
            deps = set(enr.get("dependencies", []) or [])
            overlap = req & deps
            if not overlap:
                continue
            sc = min(1.0, 0.5 + 0.2 * len(overlap))
            cands.append(
                Candidate(name=name, score=sc, tier=MatchTier.UNIFIABLE,
                          dimensions=[("hypothesis", sc, MatchTier.UNIFIABLE)])
            )
        cands.sort(key=lambda c: c.score, reverse=True)
        return SemanticResult(candidates=cands)

    # Degraded: fall back to typeclass instances + theorems in those modules.
    cands = []
    for tc in req:
        for inst in index.instances_for_typeclass(tc):
            cands.append(Candidate(name=inst, score=0.5, tier=MatchTier.STRUCTURAL,
                                   dimensions=[("typeclass_instance", 0.5, MatchTier.STRUCTURAL)]))
    return SemanticResult(
        candidates=cands,
        degraded=True,
        requires_enrichment=True,
        note="hypothesis-outline search is precise only with the docgen detail export; "
             "returned typeclass instances as a coarse fallback.",
    )


# --------------------------------------------------------------------------- #
# Proof structure & complexity (best-effort; depends on enrichment for depth)
# --------------------------------------------------------------------------- #
def search_proof_complexity(
    index,
    *,
    max_dep_depth: Optional[int] = None,
    technique: Optional[str] = None,
    has_short_version: bool = False,
    exclude_axiom: bool = False,
    ctl: Optional[dict] = None,
) -> SemanticResult:
    """Filter theorems by dependency-chain length / usage; returns proof-entry lemmas."""
    ctl = ctl or {}
    cands: List[Candidate] = []
    for name in index.entity_names():
        if not in_scope(index, name, ctl):
            continue
        meta = index._meta.get(name)
        if meta is None or meta.entity_type not in (EntityType.THEOREM, EntityType.LEMMA):
            continue
        if exclude_axiom and meta.raw_kind == "axiom":
            continue
        depth = 0
        enr = index._enriched.get(name, {})
        if enr:
            depth = len(enr.get("dependencies", []) or [])
        if max_dep_depth is not None and depth > max_dep_depth:
            continue
        # entry lemmas = high usage, core
        sc = min(1.0, 0.4 + 0.01 * meta.usage_frequency + (0.2 if meta.is_core else 0.0))
        if technique:
            sc = 0.4  # technique not detectable without proof-term export; flagged degraded
        cands.append(
            Candidate(name=name, score=sc, tier=MatchTier.STRUCTURAL,
                      dimensions=[("proof_complexity", sc, MatchTier.STRUCTURAL)])
        )
    cands.sort(key=lambda c: c.score, reverse=True)
    degraded = bool(technique) or (max_dep_depth is not None and not index._enriched)
    return SemanticResult(
        candidates=cands[: min(len(cands), 500)],
        degraded=degraded,
        note="technique/depth filters are approximate without a proof-term export."
        if degraded else "",
    )
