"""MCP server wiring (spec section 5).

Read-only, structured-JSON MCP server for the Lean Mathlib 4 knowledge base. Every
tool returns a single JSON string (universally parseable) built from the stable
schemas in :mod:`lean_mathlib_mcp.models`. There is no write / execute / mutation
path anywhere in the server — it only reads an in-memory index.
"""
from __future__ import annotations

import json
import threading
from typing import Any, Dict, List, Optional

from mcp.server.mcpserver import MCPServer

from .config import get_settings
from .errors import ErrorCode, make_error
from .index import MathlibIndex
from .models import EntityType, Granularity, MatchTier, SearchResult
from .output import assemble, entity_to_dict
from .search import Candidate, parse_controls, in_scope
from .search import context, identity, semantic
from .search.semantic import SemanticResult
from .search.scoring import score_candidate
from .sources.master_index import MasterIndexSource
from .sources.docgen_detail import DocgenDetailProvider
from .sources.notation_data import load_notations

# --------------------------------------------------------------------------- #
# Index lifecycle (lazy, thread-safe singleton)
# --------------------------------------------------------------------------- #
_INDEX: Optional[MathlibIndex] = None
_INDEX_LOCK = threading.Lock()
_INDEX_ERROR: Optional[str] = None


def build_index() -> MathlibIndex:
    """Materialize the index from the configured data source (once)."""
    global _INDEX, _INDEX_ERROR
    if _INDEX is not None:
        return _INDEX
    with _INDEX_LOCK:
        if _INDEX is not None:
            return _INDEX
        settings = get_settings()
        try:
            src = MasterIndexSource(settings)
            bundle = src.load()
            provider = DocgenDetailProvider(settings.docgen_detail_path)
            if provider.available():
                bundle.enriched.update(provider.as_bundle_enrichment())
            idx = MathlibIndex(bundle)
            idx.notations = load_notations()
            _INDEX = idx
            return _INDEX
        except Exception as exc:  # pragma: no cover - surfaced to caller as JSON error
            _INDEX_ERROR = f"{type(exc).__name__}: {exc}"
            raise


def get_index() -> MathlibIndex:
    try:
        return build_index()
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def _index_or_error() -> Dict[str, Any]:
    """Return either the index, or a structured error envelope dict."""
    try:
        return {"index": get_index()}
    except Exception as exc:
        return {
            "error": make_error(
                ErrorCode.INDEX_UNAVAILABLE,
                f"index unavailable: {exc}",
                suggested_params={"data_source": "sample", "LEAN_MATHLIB_SAMPLE": "true"},
            )
        }


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def _json(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str)


def _ctl(
    granularity=None, max_results=None, min_score=None, token_budget=None,
    scope_modules=None, exclude_modules=None, mathlib_only=None,
    exclude_deprecated=None, only_stable=None, cursor=None,
) -> Dict[str, Any]:
    return parse_controls(
        {
            "granularity": granularity,
            "max_results": max_results,
            "min_score": min_score,
            "token_budget": token_budget,
            "scope_modules": scope_modules,
            "exclude_modules": exclude_modules,
            "mathlib_only": mathlib_only,
            "exclude_deprecated": exclude_deprecated,
            "only_stable": only_stable,
            "cursor": cursor,
        }
    )


def _semantic_result(index, res: SemanticResult, query: Dict, ctl: Dict) -> Dict:
    if res.requires_enrichment:
        return make_error(
            ErrorCode.ENRICHMENT_UNAVAILABLE,
            res.note or "this search needs the docgen detail export",
            suggested_params={"docgen_detail_path": "<path to docgen JSON>"},
        )
    sr: SearchResult = assemble(index, query, res.candidates, ctl=ctl)
    return sr.model_dump(exclude_none=True)


def _name_search(index, query: str, ctl: Dict, entity_types=None, domain=None, use_tags=None) -> List[Candidate]:
    q = (query or "").strip()
    if not q:
        return []
    ql = q.lower()
    exact = index.exact_match(q)
    cands: List[Candidate] = []
    ets = {EntityType(t) for t in (entity_types or [])} or None
    tags = set(use_tags or [])
    for name in index.entity_names():
        if not in_scope(index, name, ctl):
            continue
        meta = index._meta[name]
        if ets and meta.entity_type not in ets:
            continue
        if domain and meta.domain.value != domain:
            continue
        if tags and not (tags & {t.value for t in meta.use_tags}):
            continue
        if exact and name.lower() == ql:
            cands.append(Candidate(name=name, score=1.0, tier=MatchTier.EXACT,
                                   dimensions=[("exact_name", 1.0, MatchTier.EXACT)]))
            continue
        if ql in name.lower():
            sc, tier = score_candidate(ql, name, domain=meta.domain, usage=meta.usage_frequency)
            cands.append(Candidate(name=name, score=sc, tier=tier,
                                   dimensions=[("name", sc, tier)]))
    cands.sort(key=lambda c: c.score, reverse=True)
    return cands


# --------------------------------------------------------------------------- #
# Dispatch (shared by call_tool and batch_query)
# --------------------------------------------------------------------------- #
def _dispatch(tool: str, args: Dict[str, Any]) -> Dict[str, Any]:
    r = _index_or_error()
    if "error" in r:
        return r["error"]
    index = r["index"]
    ctl = _ctl(
        granularity=args.get("granularity"),
        max_results=args.get("max_results"),
        min_score=args.get("min_score"),
        token_budget=args.get("token_budget"),
        scope_modules=args.get("scope_modules"),
        exclude_modules=args.get("exclude_modules"),
        mathlib_only=args.get("mathlib_only"),
        exclude_deprecated=args.get("exclude_deprecated"),
        only_stable=args.get("only_stable"),
        cursor=args.get("cursor"),
    )

    if tool == "search_declaration":
        cands = _name_search(
            index, args.get("query", ""),
            ctl, args.get("entity_types"), args.get("domain"), args.get("use_tags"),
        )
        sr = assemble(index, {k: args.get(k) for k in ("query", "entity_types", "domain", "use_tags") if k in args}, cands, ctl=ctl)
        return sr.model_dump(exclude_none=True)

    if tool == "get_entity":
        return _get_entity(index, args.get("full_name", ""), ctl)

    if tool == "search_by_signature":
        res = semantic.search_signature(
            index,
            entity_types=args.get("entity_types"),
            arity=args.get("arity"),
            return_type=args.get("return_type"),
            param_types=args.get("param_types"),
            ctl=ctl,
        )
        return _semantic_result(index, res, args, ctl)

    if tool == "search_by_notation":
        hits = identity.search_notation(index.notations, args.get("symbol", ""), args.get("latex"))
        if not hits:
            return make_error(
                ErrorCode.NO_MATCH, "no notation matches the given symbol/latex",
                negative_feedback={
                    "reason": "no matching notation",
                    "relax_suggestions": [
                        "try the LaTeX form (e.g. \\le, \\sum, \\circ)",
                        "try a different unicode variant of the symbol",
                        "check the Mathlib version for renamed notations",
                    ],
                },
            )
        out = [h.model_dump(exclude_none=True) for h in hits]
        # attach the bound entity if present in the index
        for o in out:
            bt = o.get("binds_to")
            if bt and bt in index._meta:
                o["bound_entity"] = entity_to_dict(index, bt, Granularity.TERSE)
        return {"query": {k: args.get(k) for k in ("symbol", "latex") if k in args},
                "total_matches": len(out), "notations": out}

    if tool == "search_by_domain_use":
        res = semantic.filter_domain_use(
            index,
            domain=args.get("domain"),
            subdomain=args.get("subdomain"),
            use_tags=args.get("use_tags"),
            entity_types=args.get("entity_types"),
            ctl=ctl,
        )
        return _semantic_result(index, res, args, ctl)

    if tool == "search_by_conclusion":
        res = semantic.search_conclusion(
            index, args.get("pattern", ""),
            symmetric=bool(args.get("symmetric")),
            monotonic=bool(args.get("monotonic")),
            ctl=ctl,
        )
        return _semantic_result(index, res, args, ctl)

    if tool == "search_hypothesis":
        res = semantic.search_hypothesis(
            index,
            required_typeclasses=args.get("required_typeclasses"),
            required_axioms=args.get("required_axioms"),
            constructive_only=bool(args.get("constructive_only")),
            exclude_classical=bool(args.get("exclude_classical")),
            no_axiom=bool(args.get("no_axiom")),
            ctl=ctl,
        )
        return _semantic_result(index, res, args, ctl)

    if tool == "search_proof_complexity":
        res = semantic.search_proof_complexity(
            index,
            max_dep_depth=args.get("max_dep_depth"),
            technique=args.get("technique"),
            has_short_version=bool(args.get("has_short_version")),
            exclude_axiom=bool(args.get("exclude_axiom")),
            ctl=ctl,
        )
        return _semantic_result(index, res, args, ctl)

    if tool == "expand_dependencies":
        return context.expand_dependencies(
            index, args.get("full_name", ""),
            depth=int(args.get("depth", 2)),
            exclude_stdlib=bool(args.get("exclude_stdlib")),
            only_mathlib=bool(args.get("only_mathlib", True)),
            as_tree=bool(args.get("as_tree", True)),
        )

    if tool == "find_usages":
        return context.find_usages(
            index, args.get("full_name", ""),
            direct_only=bool(args.get("direct_only")),
            transitive=bool(args.get("transitive", True)),
        )

    if tool == "recommend_related":
        return context.recommend_related(index, args.get("full_name", ""), limit=int(args.get("limit", 15)))

    if tool == "module_snapshot":
        snap = context.module_snapshot(index, args.get("module", ""))
        if "error" in snap:
            # suggest similarly-named modules
            q = args.get("module", "").lower()
            sugg = [m for m in index.modules if q in m.lower()][:10]
            return make_error(
                ErrorCode.NOT_FOUND, f"module not found: {args.get('module')}",
                suggested_params={"similar_modules": sugg},
            )
        return snap

    if tool == "search_modules":
        q = (args.get("query") or "").lower()
        scope = args.get("scope_modules")
        hits = []
        for name, m in index.modules.items():
            if q and q not in name.lower():
                continue
            if scope and not any(name.startswith(s) for s in scope):
                continue
            hits.append(m.model_dump(exclude_none=True))
        hits.sort(key=lambda h: h["full_name"])
        limit = int(args.get("max_results") or 50)
        return {"query": args.get("query"), "total_matches": len(hits),
                "returned": min(limit, len(hits)), "modules": hits[:limit]}

    if tool == "index_info":
        return {"summary": index.summary(), "notations_loaded": len(index.notations),
                "source": index.meta_src.get("source")}

    if tool == "batch_query":
        return _batch(args.get("queries", []))

    return make_error(ErrorCode.UNKNOWN_TOOL, f"unknown tool: {tool}", fixable=False)


def _get_entity(index, full_name: str, ctl: Dict) -> Dict:
    if not full_name:
        return make_error(ErrorCode.INVALID_ARGUMENT, "full_name is required")
    matches = index.exact_match(full_name)
    if len(matches) > 1:
        cands = [
            {"full_name": m, "entity_type": index._meta[m].entity_type.value,
             "module": index._meta[m].module, "domain": index._meta[m].domain.value}
            for m in matches
        ]
        return make_error(
            ErrorCode.AMBIGUOUS_MATCH,
            "multiple entities share this name; disambiguate by namespace/module",
            disambiguation=cands,
            suggested_params={"namespace": "<parent module prefix>"},
        )
    if len(matches) == 1:
        gran = Granularity(ctl.get("granularity") or "complete")
        return entity_to_dict(index, matches[0], gran)
    if full_name.startswith("decl:"):
        name = full_name[5:]
        if name in index._meta:
            return entity_to_dict(index, name, Granularity(ctl.get("granularity") or "complete"))
    return make_error(
        ErrorCode.NOT_FOUND, f"entity not found: {full_name}",
        suggested_params={"tool": "search_declaration", "query": full_name},
    )


def _batch(queries: List[Dict[str, Any]]) -> Dict:
    results = []
    errors = []
    for item in queries:
        try:
            tool = item.get("tool")
            args = item.get("args", {})
            payload = _dispatch(tool, args)
            results.append(SearchResult(**_coerce(payload)) if _looks_like_result(payload) else payload)
        except Exception as exc:
            errors.append({"tool": item.get("tool"), "error": str(exc)})
    return {"count": len(results), "results": results, "errors": errors}


def _looks_like_result(payload: Dict) -> bool:
    return isinstance(payload, Dict) and "hits" in payload and "query" in payload


def _coerce(payload: Dict) -> Dict:
    return payload


# --------------------------------------------------------------------------- #
# Server definition
# --------------------------------------------------------------------------- #
server = MCPServer("lean-mathlib-mcp")


@server.tool(
    name="search_declaration",
    description=(
        "Precise + fuzzy name search over Mathlib 4 declarations (definitions, "
        "theorems, lemmas, instances, typeclasses, axioms). If the query is an exact "
        "qualified name it resolves exactly; otherwise it ranks by name precision, "
        "domain closeness, and usage. Supports domain / use-tag / entity-type filters "
        "and all output controls (granularity, pagination, token budget)."
    ),
)
def search_declaration(
    query: str,
    entity_types: Optional[List[str]] = None,
    domain: Optional[str] = None,
    use_tags: Optional[List[str]] = None,
    granularity: str = "summary",
    max_results: int = 20,
    min_score: float = 0.0,
    token_budget: int = 6000,
    scope_modules: Optional[List[str]] = None,
    exclude_modules: Optional[List[str]] = None,
    mathlib_only: bool = False,
    exclude_deprecated: bool = False,
    only_stable: bool = False,
    cursor: Optional[str] = None,
) -> str:
    return _json(_dispatch("search_declaration", {k: v for k, v in locals().items() if v is not None or k in ("query",)}))


@server.tool(
    name="get_entity",
    description=(
        "Return one fully-resolved entity (definition/theorem/module/...) by exact "
        "qualified name or stable id. Disambiguates when a name is shared. Choose the "
        "output granularity: terse | summary | complete | expanded."
    ),
)
def get_entity(
    full_name: str,
    granularity: str = "complete",
    mathlib_only: bool = False,
) -> str:
    return _json(_dispatch("get_entity", {k: v for k, v in locals().items()}))


@server.tool(
    name="search_by_signature",
    description=(
        "Type-signature structural matching. Give an arity and/or a return-type "
        "pattern and/or ordered param-type patterns (use '_' or '*' as wildcards). "
        "Returns theorems/definitions/instances ranked by exact-unification > "
        "unifiable > structural. Requires the docgen detail export for type data."
    ),
)
def search_by_signature(
    arity: Optional[int] = None,
    return_type: Optional[str] = None,
    param_types: Optional[List[str]] = None,
    entity_types: Optional[List[str]] = None,
    granularity: str = "summary",
    max_results: int = 20,
    min_score: float = 0.0,
    token_budget: int = 6000,
    scope_modules: Optional[List[str]] = None,
    exclude_modules: Optional[List[str]] = None,
    mathlib_only: bool = False,
    cursor: Optional[str] = None,
) -> str:
    return _json(_dispatch("search_by_signature", {k: v for k, v in locals().items() if v is not None}))


@server.tool(
    name="search_by_notation",
    description=(
        "Resolve a Mathlib notation/symbol by its Unicode text or LaTeX form "
        "(e.g. symbol='≤', latex='\\le', or '\\sum'). Returns the notation record(s) "
        "with precedence, associativity, bound entity, and conflicting forms. "
        "Distinguishes the same symbol across domains."
    ),
)
def search_by_notation(symbol: str, latex: Optional[str] = None) -> str:
    return _json(_dispatch("search_by_notation", {k: v for k, v in locals().items() if v is not None}))


@server.tool(
    name="search_by_domain_use",
    description=(
        "Domain + subdomain + intent-tag + entity-type filtering (e.g. domain="
        "'Algebra', use_tags=['simplify','equiv']). Returns the category's core/"
        "high-frequency theorems first. Always available without enrichment."
    ),
)
def search_by_domain_use(
    domain: Optional[str] = None,
    subdomain: Optional[str] = None,
    use_tags: Optional[List[str]] = None,
    entity_types: Optional[List[str]] = None,
    granularity: str = "summary",
    max_results: int = 20,
    min_score: float = 0.0,
    token_budget: int = 6000,
    scope_modules: Optional[List[str]] = None,
    exclude_modules: Optional[List[str]] = None,
    mathlib_only: bool = False,
    cursor: Optional[str] = None,
) -> str:
    return _json(_dispatch("search_by_domain_use", {k: v for k, v in locals().items() if v is not None}))


@server.tool(
    name="search_by_conclusion",
    description=(
        "Match a theorem by the structure of its conclusion, expressed as an abstract "
        "syntax fragment (e.g. 'x + y = y + x'). Variable names are ignored; operator/"
        "relation tokens are matched. Optional symmetric/monotonic morphology flags. "
        "Requires the docgen detail export."
    ),
)
def search_by_conclusion(
    pattern: str,
    symmetric: bool = False,
    monotonic: bool = False,
    granularity: str = "summary",
    max_results: int = 20,
    min_score: float = 0.0,
    token_budget: int = 6000,
    scope_modules: Optional[List[str]] = None,
    exclude_modules: Optional[List[str]] = None,
    mathlib_only: bool = False,
    cursor: Optional[str] = None,
) -> str:
    return _json(_dispatch("search_by_conclusion", {k: v for k, v in locals().items() if v is not None}))


@server.tool(
    name="search_hypothesis",
    description=(
        "Return theorems whose premises include the given typeclasses/axioms (a "
        "hypothesis outline). Supports constructive_only / exclude_classical / "
        "no_axiom constraints. Precise with the docgen detail export; otherwise "
        "falls back to typeclass instances."
    ),
)
def tool_search_hypothesis(
    required_typeclasses: Optional[List[str]] = None,
    required_axioms: Optional[List[str]] = None,
    constructive_only: bool = False,
    exclude_classical: bool = False,
    no_axiom: bool = False,
    granularity: str = "summary",
    max_results: int = 20,
    min_score: float = 0.0,
    token_budget: int = 6000,
    scope_modules: Optional[List[str]] = None,
    exclude_modules: Optional[List[str]] = None,
    mathlib_only: bool = False,
    cursor: Optional[str] = None,
) -> str:
    return _json(_dispatch("search_hypothesis", {k: v for k, v in locals().items() if v is not None}))


@server.tool(
    name="search_proof_complexity",
    description=(
        "Filter theorems by proof structure: dependency-chain depth (max_dep_depth), "
        "exclude_axiom, technique hint. Returns recommended proof-entry lemmas ranked "
        "by usage. Depth/technique are approximate without a proof-term export."
    ),
)
def search_proof_complexity(
    max_dep_depth: Optional[int] = None,
    technique: Optional[str] = None,
    has_short_version: bool = False,
    exclude_axiom: bool = False,
    granularity: str = "summary",
    max_results: int = 20,
    min_score: float = 0.0,
    token_budget: int = 6000,
    scope_modules: Optional[List[str]] = None,
    exclude_modules: Optional[List[str]] = None,
    mathlib_only: bool = False,
    cursor: Optional[str] = None,
) -> str:
    return _json(_dispatch("search_proof_complexity", {k: v for k, v in locals().items() if v is not None}))


@server.tool(
    name="expand_dependencies",
    description=(
        "Given an entity, return its direct/recursive dependencies up to a depth limit, "
        "as a tree or flat list. Uses true per-declaration deps when enriched, else the "
        "module import graph. Supports only_mathlib / exclude_stdlib."
    ),
)
def tool_expand_dependencies(
    full_name: str,
    depth: int = 2,
    exclude_stdlib: bool = False,
    only_mathlib: bool = True,
    as_tree: bool = True,
) -> str:
    return _json(_dispatch("expand_dependencies", {k: v for k, v in locals().items()}))


@server.tool(
    name="find_usages",
    description=(
        "Given an entity, return what directly/indirectly references it (impact "
        "analysis). Includes direct dependents and the modules that import its module."
    ),
)
def find_usages(full_name: str, direct_only: bool = False, transitive: bool = True) -> str:
    return _json(_dispatch("find_usages", {k: v for k, v in locals().items()}))


@server.tool(
    name="recommend_related",
    description=(
        "Given an entity, return high-association items: same-module core pairings, "
        "equivalents/duals, generalizations/specializations, and other instances of its "
        "typeclass — the usual 'what to look at next' set."
    ),
)
def tool_recommend_related(full_name: str, limit: int = 15) -> str:
    return _json(_dispatch("recommend_related", {k: v for k, v in locals().items()}))


@server.tool(
    name="module_snapshot",
    description=(
        "Return a layered snapshot of a module: domain, priority tier, imports, "
        "imported-by count, exported declarations split into intro/core/advanced tiers, "
        "and key typeclass instances. For fast AI orientation."
    ),
)
def tool_module_snapshot(module: str) -> str:
    return _json(_dispatch("module_snapshot", {k: v for k, v in locals().items()}))


@server.tool(
    name="search_modules",
    description="Find Mathlib modules/namespaces by substring, with optional scope filter.",
)
def search_modules(
    query: str,
    scope_modules: Optional[List[str]] = None,
    max_results: int = 50,
) -> str:
    return _json(_dispatch("search_modules", {k: v for k, v in locals().items() if v is not None}))


@server.tool(
    name="index_info",
    description="Return index health: declaration/module counts, enrichment status, data source.",
)
def index_info() -> str:
    return _json(_dispatch("index_info", {}))


@server.tool(
    name="batch_query",
    description=(
        "Run multiple queries in one round-trip to cut latency (spec 5.1). Pass "
        "queries as a list of {tool, args} objects; results are returned in order with "
        "per-item errors isolated."
    ),
)
def batch_query(queries: List[Dict[str, Any]]) -> str:
    return _json(_dispatch("batch_query", {"queries": queries}))


def main() -> None:
    """Entrypoint: run the MCP server over stdio (read-only JSON service)."""
    server.run(transport="stdio")


if __name__ == "__main__":
    main()
