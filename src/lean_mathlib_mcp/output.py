"""Output control & rendering (spec sections 4.1 / 4.2 / 4.3 / 6).

Turns scored :class:`Candidate` rows into a paginated, granularity-rendered
:class:`SearchResult` envelope with a stable JSON schema, an estimated-token budget
trim, ready-to-reuse next-query params, and negative-result feedback.
"""
from __future__ import annotations

import json
from typing import Dict, List, Optional

from .models import EntityType, Granularity, MathlibEntity, SearchHit, SearchResult
from .search import Candidate


def _estimate_tokens(s: str) -> int:
    """Rough token estimate (~4 chars/token) for the budget guard (spec 4.3)."""
    return max(1, len(s) // 4)


def entity_to_dict(index, full_name: str, granularity: Granularity) -> Dict:
    """Serialize one entity at the requested output tier."""
    ent: Optional[MathlibEntity] = index.get_entity(full_name)
    if ent is None:
        return {"id": f"decl:{full_name}", "full_name": full_name, "error": "not_found"}

    if granularity == Granularity.TERSE:
        return {
            "id": ent.id,
            "full_name": ent.full_name,
            "entity_type": ent.entity_type.value,
            "raw_kind": ent.raw_kind,
            "module": ent.module,
            "doc_link": ent.doc_link,
        }

    if granularity == Granularity.SUMMARY:
        return {
            "id": ent.id,
            "full_name": ent.full_name,
            "entity_type": ent.entity_type.value,
            "raw_kind": ent.raw_kind,
            "module": ent.module,
            "domain": ent.domain.value,
            "subdomain": ent.subdomain,
            "use_tags": [t.value for t in ent.use_tags],
            "type_signature": ent.type_signature,
            "statement": ent.statement,
            "deprecated": ent.status.deprecated,
            "doc_link": ent.doc_link,
        }

    # COMPLETE / EXPANDED -> full normalized record
    d = ent.model_dump(exclude_none=True)
    if granularity == Granularity.COMPLETE:
        # drop the heaviest relation lists to stay compact
        rel = d.get("relations")
        if isinstance(rel, dict):
            rel.pop("dependencies", None)
            rel.pop("dependents", None)
            rel.pop("related", None)
    return d


def assemble(
    index,
    query: Dict,
    candidates: List[Candidate],
    *,
    ctl: Optional[Dict] = None,
    total_estimate: Optional[int] = None,
) -> SearchResult:
    """Build a paginated SearchResult from scored candidates."""
    ctl = ctl or {}
    gran = Granularity(ctl.get("granularity") or "summary")
    max_results = int(ctl.get("max_results") or 20)
    min_score = float(ctl.get("min_score") or 0.0)
    token_budget = int(ctl.get("token_budget") or 6000)

    # min-score gate
    scored = [c for c in candidates if c.score >= min_score]

    # cursor pagination (offset encoded as a string)
    offset = 0
    cur = ctl.get("cursor")
    if cur:
        try:
            offset = int(cur)
        except (TypeError, ValueError):
            offset = 0
    page = scored[offset : offset + max_results]

    hits: List[SearchHit] = []
    used_tokens = 0
    truncated_low = False
    for c in page:
        ent_dict = entity_to_dict(index, c.name, gran)
        js = json.dumps(ent_dict, ensure_ascii=False)
        est = _estimate_tokens(js)
        if used_tokens + est > token_budget and hits:
            truncated_low = True
            break
        used_tokens += est
        hit = SearchHit(
            entity=ent_dict,
            score=c.score,
            tier=c.tier,
            match_dimensions=[
                {"dimension": dim, "score": sc, "tier": t.value}
                for dim, sc, t in c.dimensions
            ],
            reuse_params={"full_name": c.name, "id": ent_dict.get("id")},
        )
        hits.append(hit)

    next_cursor = None
    if offset + len(page) < len(scored):
        next_cursor = str(offset + len(page))

    total = total_estimate if total_estimate is not None else len(scored)

    result = SearchResult(
        query=query,
        total_matches=total,
        returned=len(hits),
        next_cursor=next_cursor,
        truncated_low_relevance=truncated_low,
        hits=hits,
    )

    if total == 0:
        result.negative_feedback = {
            "reason": "no matching entity for the given query",
            "relax_suggestions": [
                "drop scope_modules / narrow namespace constraints",
                "try a different symbol or its LaTeX form",
                "search one level up the module hierarchy",
                "check the Mathlib version — names may have been renamed/refactored",
            ],
        }
    return result
