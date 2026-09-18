# lean-mathlib-mcp

A **machine-first MCP server** for structured, low-ambiguity search over the
**Lean Mathlib 4** knowledge base (definitions, theorems, lemmas, notations,
modules, instances, typeclasses, axioms).

It is a ground-up rewrite of the reference implementation
[`CriticalLine/lean-mathlib-docs-mcp`](https://github.com/CriticalLine/lean-mathlib-docs-mcp),
re-targeted from "string search for humans" to "structured semantic retrieval
for LLM agents".

## Design principles

- **Machine-first.** Every tool returns a single JSON string with a stable
  schema — directly parseable, no prose dumps.
- **Precision over fuzzy semantics.** Exact qualified name > short name +
  namespace > signature/conclusion structure > domain + intent.
- **Complete metadata.** A unified entity model covers definitions / theorems /
  lemmas / notations / modules / instances / typeclasses / axioms, with source,
  dependencies, status, and a stable id.
- **Controllable granularity.** Per-call `terse | summary | complete | expanded`,
  plus `max_results`, cursor pagination, and a soft `token_budget`.
- **Read-only, structured errors.** No write/exec path. Failures return an error
  code + corrective suggestions + negative-result feedback.

## Architecture

```txt
docgen master index declaration-data.bmp  ──►  MasterIndexSource.load()
                                                │  (neutral SourceBundle)
                                                ▼
                                      MathlibIndex  (compact secondary index + lazy entity materialization)
                                                │
        ┌───────────────┬───────────────┬───────┴────┬──────────────────┐
        ▼               ▼               ▼            ▼                  ▼
   search/identity  search/semantic  search/context  search/scoring   sources/
   (exact identity) (semantic feats) (graph context) (relevance rank) docgen_detail
        │               │               │                              (optional enrichment)
        └───────────────┴───────────────┴──────────────────────────────┘
                                                ▼
                                      output.assemble()  → SearchResult (JSON)
                                                ▼
                                      MCPServer (stdio)  → 15 @server.tool
```

- **`sources/`** — `SourceBundle` is a neutral data contract. `MasterIndexSource`
  parses the official master index; `DocgenDetailProvider` optionally supplies
  type signatures / docs / true dependency graphs (graceful degradation if absent).
- **`index.py`** — the production master index has 425k+ declarations. To avoid
  hundreds of MB of startup cost, a compact `DeclMeta` is kept per declaration for
  filtering, and the rich entity object is materialized lazily, only for returned results.
- **`search/`** — `identity` (exact identity) / `semantic` (semantic features) /
  `context` (graph context) + `scoring` (weighted ranking).
- **`output.py`** — granularity projection + cursor pagination + token-budget
  truncation + reuse params + negative feedback.
- **`server.py`** — `MCPServer("lean-mathlib-mcp")` registers 15 tools via
  `@server.tool`; `_dispatch` routes all calls (sync request/response; the batch
  tool shares the same path).

### Data sources & enrichment

The master index `declaration-data.bmp` (official docgen export) contains the
`declarations / modules / instances / instancesFor` sections, but **not** type
signatures, docs, or true dependency graphs. Those *rich features* come from an
optional docgen4 JSON export:

- Without `docgen_detail_path`, `search_by_signature` / `search_by_conclusion` /
  `search_hypothesis` / `search_proof_complexity` and the "true dependencies" of
  `expand_dependencies` return an `enrichment_unavailable` error code with a fix
  suggestion instead of garbage.
- `search_by_domain_use` / `search_declaration` / `search_by_notation` /
  `module_snapshot` and the topology fallback (module import graph) are always available.

## Installation

Requires **Python 3.11+** (`mcp>=2`, `pydantic>=2`, `pydantic-settings`).

```bash
# from a clone of this repo
python -m pip install -e .          # installs the `lean-mathlib-mcp` console script
python -m pip install -r requirements.txt   # or pin manually
```

An offline sample index (`data/sample_index.json`, ~3.4k declarations / 115
modules) ships with the repo so the tests and a quick smoke run work without
downloading anything.

## Running (stdio)

```bash
# via the installed console script
lean-mathlib-mcp

# or, without installing, via the module
LEAN_MATHLIB_DATA_SOURCE=sample python -m lean_mathlib_mcp

# or via the bundled launcher (adds src/ to sys.path automatically)
LEAN_MATHLIB_DATA_SOURCE=sample python run_server.py
```

- `LEAN_MATHLIB_DATA_SOURCE=auto` (default): use the local sample/cache if present,
  otherwise download the production index.
- `LEAN_MATHLIB_DATA_SOURCE=remote`: force-download the full production index (network required).
- `LEAN_MATHLIB_DATA_SOURCE=sample`: force the committed offline fixture (deterministic).

### Connecting from an MCP client (e.g. WorkBuddy)

Copy `mcp.example.json` to `mcp.json`, set `command` to your Python interpreter,
and trust the server in your connector manager. Example:

```json
{
  "servers": {
    "lean_mathlib_mcp": {
      "command": "python",
      "args": ["run_server.py"],
      "env": { "LEAN_MATHLIB_DATA_SOURCE": "auto" }
    }
  }
}
```

If the package is published to PyPI, `uvx lean-mathlib-mcp` works as the command.

## Configuration

All knobs are environment-overridable (prefix `LEAN_MATHLIB_`), so the server
deploys read-only with zero code changes.

| Variable | Default | Description |
| ---------- | --------- | ------------- |
| `LEAN_MATHLIB_DATA_SOURCE` | `auto` | `auto` / `sample` / `remote` |
| `LEAN_MATHLIB_DATA_URL` | docgen official URL | Production master index URL |
| `LEAN_MATHLIB_CACHE_DIR` | `data/cache` | Index cache directory |
| `LEAN_MATHLIB_RAW_DIR` | `data/raw` | Where `declaration-data.bmp` is stored |
| `LEAN_MATHLIB_SAMPLE` | `data/sample_index.json` | Offline sample path |
| `LEAN_MATHLIB_BUILT_INDEX_PATH` | `data/cache/index.json` | Built index cache |
| `LEAN_MATHLIB_DEFAULT_GRANULARITY` | `summary` | Default output granularity |
| `LEAN_MATHLIB_DEFAULT_MAX_RESULTS` | `20` | Max hits per call |
| `LEAN_MATHLIB_DEFAULT_TOKEN_BUDGET` | `6000` | Soft token cap (results truncated to fit) |
| `LEAN_MATHLIB_MAX_DEPENDENCY_DEPTH` | `3` | Dependency expansion cap |
| `LEAN_MATHLIB_MATHLIB_ONLY` | `false` | `true` excludes `Init.*` core-library basics |
| `LEAN_MATHLIB_DOCGEN_DETAIL_PATH` | (empty) | Optional docgen4 JSON export for rich features |

## Tools (15, all read-only)

> Tools marked **⚡ enrichment** return `enrichment_unavailable` when
> `LEAN_MATHLIB_DOCGEN_DETAIL_PATH` is unset.
> Shared output controls (most tools): `granularity ∈ {terse,summary,complete,expanded}`,
> `max_results`, `min_score`, `token_budget`, `scope_modules`, `exclude_modules`,
> `mathlib_only`, `exclude_deprecated`, `only_stable`, `cursor`.

### 3.1 Exact-identity search

| Tool | Key params | Description |
| ------ | ----------- | ------------- |
| `search_declaration` | `query`, `entity_types?`, `domain?`, `use_tags?` | Exact qualified-name resolution, else ranked by name precision + domain closeness + usage. Empty result carries `negative_feedback`. |
| `get_entity` | `full_name`, `granularity=complete` | One entity by exact name or stable id `decl:*`. On name collision returns `ambiguous_match` with disambiguation candidates. |
| `search_by_notation` | `symbol`, `latex?` | Resolve a notation by Unicode or LaTeX (e.g. `≤` / `\le` / `\sum`): precedence, associativity, bound entity, conflicting forms. |

### 3.2 Semantic-feature search

| Tool | Key params | Description |
| ------ | ----------- | ------------- |
| `search_by_signature` ⚡ | `arity?`, `return_type?`, `param_types?` (`_`/`*` wildcards) | Type-signature structural match, ranked exact-unify > unifiable > structural. |
| `search_by_conclusion` ⚡ | `pattern`, `symmetric?`, `monotonic?` | Match by conclusion structure (variable names ignored, operator tokens matched), e.g. `x + y = y + x`. |
| `search_by_domain_use` | `domain?`, `subdomain?`, `use_tags?`, `entity_types?` | Domain + subdomain + intent tags + entity type; core/high-frequency first. **Always available.** |
| `search_hypothesis` ⚡ | `required_typeclasses?`, `required_axioms?`, `constructive_only?`, `exclude_classical?`, `no_axiom?` | Filter theorems by premise (hypothesis) outline. |
| `search_proof_complexity` ⚡ | `max_dep_depth?`, `technique?`, `has_short_version?`, `exclude_axiom?` | Filter by proof structure / dependency depth; recommends proof-entry lemmas. |

### 3.3 Association & context search

| Tool | Key params | Description |
| ------ | ----------- | ------------- |
| `expand_dependencies` | `full_name`, `depth=2`, `exclude_stdlib?`, `only_mathlib=true`, `as_tree=true` | Recursive dependency expansion (tree/flat); enriched deps preferred, else module import-graph fallback. |
| `find_usages` | `full_name`, `direct_only?`, `transitive=true` | Impact analysis: direct/indirect dependents + modules importing its module. |
| `recommend_related` | `full_name`, `limit=15` | "What to read next": same-module core pairings, equivalents/duals, generalizations/specializations, other instances of its typeclass. |
| `module_snapshot` | `module` | Layered module overview: domain, priority tier, imports, imported-by count, intro/core/advanced exports, key instances. Suggests similar modules when not found. |

### 3.4 Service & batch

| Tool | Key params | Description |
| ------ | ----------- | ------------- |
| `search_modules` | `query`, `scope_modules?`, `max_results=50` | Find modules/namespaces by substring. |
| `index_info` | — | Index health: declaration/module counts, enrichment status, data source. |
| `batch_query` | `queries: [{tool, args}, ...]` | Run multiple queries in one round-trip; per-item errors isolated. |

## Output schema

### SearchResult

```jsonc
{
  "query": { /* echoed query params */ },
  "total_matches": 326,
  "returned": 5,
  "next_cursor": "5",            // pagination cursor; null when exhausted
  "truncated_low_relevance": false,
  "hits": [ /* SearchHit[] */ ],
  "reuse_params": { "full_name": "...", "id": "decl:..." },
  "negative_feedback": {         // present only when hits is empty
    "reason": "no matching entity for the given query",
    "relax_suggestions": [ "..." ]
  }
}
```

### SearchHit

```jsonc
{
  "entity": { /* MathlibEntity projection (per granularity) */ },
  "score": 0.95,                 // 0..1 relevance
  "tier": "exact",               // exact | structural | semantic | domain | usage
  "match_dimensions": [ { "dimension": "exact_name", "score": 1.0, "tier": "exact" } ],
  "truncated": false,
  "reuse_params": { "full_name": "...", "id": "decl:..." }
}
```

### MathlibEntity (field names are stable across Mathlib versions)

`id` · `entity_type` · `raw_kind` · `full_name` · `short_name` · `namespace` ·
`module` · `type_signature` · `statement` · `doc` · `domain` · `subdomain` ·
`use_tags` · `doc_link` · `relations` (`dependencies`/`dependents`/`equivalents`/
`generalizes`/`specializes`/`related`) · `status` (`deprecated`/`maintenance`/
`cache_key`) · `is_core` · `usage_frequency` · `enrichment_source`.

`granularity` projection:

- **terse**: `id` / `full_name` / `entity_type` / `module` / `domain`
- **summary**: + `short_name` / `doc_link` / `use_tags` / `is_core` / `usage_frequency`
- **complete**: + `type_signature` / `statement` / `subdomain` / `relations` (light)
- **expanded**: + `doc` / full `relations` / `status`

### Structured error

```jsonc
{
  "code": "enrichment_unavailable",   // see table below
  "message": "this search needs the docgen detail export",
  "fixable": true,
  "suggested_params": { "docgen_detail_path": "<path to docgen JSON>" },
  "disambiguation": [ /* on ambiguous_match */ ],
  "negative_feedback": { /* on no_match */ }
}
```

| Error code | Trigger | Caller action |
| ------------ | --------- | --------------- |
| `unknown_tool` | Unknown tool name (`fixable:false`) | Check tool name |
| `invalid_argument` | Missing required arg | Add `full_name` / `query` |
| `ambiguous_match` | Name collision | Disambiguate via `namespace`/module (see `disambiguation`) |
| `no_match` | No notation/query match | See `negative_feedback.relax_suggestions` |
| `not_found` | Entity/module missing | Use `search_declaration` |
| `index_unavailable` | Index build failed | Switch `data_source=sample` |
| `enrichment_unavailable` | Rich feature missing | Provide `docgen_detail_path` |
| `out_of_scope` | Out of range/filtered | Adjust `scope_modules` |
| `internal` | Server exception (`fixable:false`) | Report |

### Relevance ranking

`score = 0.45·name + 0.20·structure + 0.15·domain + 0.10·usage + 0.10·stability`;
tier order `exact > structural > semantic > domain > usage`. Collisions and
ambiguity are surfaced explicitly via `ambiguous_match` rather than guessed.

## Extending

- **New data source:** implement the `DataSource` / `DetailProvider` protocols in
  `sources/__init__.py`, produce a `SourceBundle`, and wire it into
  `server.build_index()`.
- **New detail provider:** subclass `DocgenDetailProvider` and feed an external
  export (signatures / proof terms) into `bundle.enriched[name]`.
- **New tool:** add an `@server.tool` function in `server.py` (prefix the function
  name with `tool_` to avoid clashing with same-named `search.*` helpers), add a
  branch in `_dispatch`, and reuse `assemble` / `make_error`.

## Testing

```bash
# unit tests (20): index, search, server wiring
python -m pytest tests/ -q

# real MCP stdio end-to-end (spawns the server subprocess over the protocol)
python tests/e2e_stdio.py
```

Build / rebuild fixtures and cache:

```bash
python -m lean_mathlib_mcp.builder sample   # slice multi-domain sample from the real master index
python -m lean_mathlib_mcp.builder build    # build the index cache
python -m lean_mathlib_mcp.builder info     # index statistics
```

## Known limitations

- Rich features (signatures / conclusions / true dependencies / proof structure)
  depend on the optional docgen4 export; without it the relevant tools return
  `enrichment_unavailable` and degrade gracefully.
- In the master index, declaration **names** have no `Mathlib.` prefix (e.g. `Add`,
  `Nat.add`); `mathlib_only` is decided by whether the **owning module** is under
  `Mathlib.*` (default `false`, i.e. core library is not filtered out).
- The production index has 425k+ declarations; the first build downloads and parses
  `declaration-data.bmp` (~67 MB), then reuses `data/cache` afterward.

## Credits

Refactored from
[`CriticalLine/lean-mathlib-docs-mcp`](https://github.com/CriticalLine/lean-mathlib-docs-mcp).
Data is sourced from the Lean community's
[Mathlib 4 docgen](https://leanprover-community.github.io/mathlib4_docs/).

## License

MIT — see [LICENSE](LICENSE).
