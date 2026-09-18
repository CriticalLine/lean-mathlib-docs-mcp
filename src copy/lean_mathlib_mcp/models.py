"""Universal entity data model for the Lean Mathlib 4 knowledge base.

This module is the single source of truth for *how every retrievable entity is
represented*. All search capabilities (spec section 3) read from / filter against
these models, and all output tiers (spec section 4.1) are projections of them.

Design goals
------------
* **Stable field names.** Field names here never change across Mathlib versions.
  Version-specific volatility lives in ``version`` / ``status`` sub-objects, not in
  the shape of the record.
* **No natural-language padding.** Everything a model carries is machine-extractable
  (ids, paths, type strings, relation lists, tags). Human-readable prose is confined
  to the optional ``doc`` field sourced from upstream documentation.
* **Graceful enrichment.** Rich fields (``type_signature``, ``doc``, true
  ``dependencies``) are optional. When the active data source cannot supply them,
  they are left ``None`` and the corresponding search features degrade explicitly
  rather than failing.
"""
from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# --------------------------------------------------------------------------- #
# Enumerations
# --------------------------------------------------------------------------- #
class EntityType(str, Enum):
    """Discriminator for the kind of retrievable entity.

    The raw Lean ``kind`` string is preserved on every record (``raw_kind``) so the
    upstream taxonomy is never lost, but downstream logic branches on this stable
    enum instead of on brittle string comparisons.
    """

    DEFINITION = "definition"
    THEOREM = "theorem"
    LEMMA = "lemma"
    AXIOM = "axiom"
    CONSTANT = "constant"
    INSTANCE = "instance"
    TYPECLASS = "typeclass"
    NOTATION = "notation"
    MODULE = "module"
    STRUCTURE = "structure"
    INDUCTIVE = "inductive"
    CONSTRUCTOR = "constructor"
    CLASS = "class"
    OPAQUE = "opaque"
    ABBREV = "abbrev"
    CONVENTION = "convention"
    UNKNOWN = "unknown"


class Domain(str, Enum):
    """First-level mathematical field, derived from the module path (see domain.py)."""

    ALGEBRA = "Algebra"
    ANALYSIS = "Analysis"
    NUMBER_THEORY = "NumberTheory"
    TOPOLOGY = "Topology"
    LOGIC = "Logic"
    ORDER = "Order"
    CATEGORY_THEORY = "CategoryTheory"
    GROUP_THEORY = "GroupTheory"
    MEASURE_THEORY = "MeasureTheory"
    LINEAR_ALGEBRA = "LinearAlgebra"
    DATA = "Data"
    COMPUTABILITY = "Computability"
    SET_THEORY = "SetTheory"
    TACTIC = "Tactic"
    OTHER = "Other"


class UseTag(str, Enum):
    """Coarse intent tag used by the domain+use filter (spec 3.2).

    Tags are derived heuristically from declaration names + module placement; they
    are hints, not guarantees, and are omitted when unsupported by the data source.
    """

    SIMPLIFY = "simplify"
    DECIDE = "decide"
    CONSTRUCT = "construct"
    EQUIV = "equiv"
    LOWER_BOUND = "lower_bound"
    UPPER_BOUND = "upper_bound"
    ISO = "iso"
    RECURSIVE = "recursive"
    MONOTONICITY = "monotonicity"
    CONTINUITY = "continuity"
    MEMBERSHIP = "membership"
    CHARACTERIZATION = "characterization"


class Granularity(str, Enum):
    """Output tier requested by the caller (spec 4.1)."""

    TERSE = "terse"          # id + name + type + module + link only
    SUMMARY = "summary"      # + domain, use tags, status, one-line signature
    COMPLETE = "complete"    # full normalized record (no heavy expansions)
    EXPANDED = "expanded"    # complete + dependencies / dependents / related lists


class MaintenanceStatus(str, Enum):
    """Lifecycle status of an entity."""

    STABLE = "stable"
    DEPRECATED = "deprecated"
    WIP = "wip"
    MERGE_PENDING = "merge_pending"
    CONTROVERSIAL = "controversial"


class MatchTier(str, Enum):
    """Precision tier returned alongside a search hit (spec 6 quality guarantees)."""

    EXACT = "exact"                  # exact unification / full-name match
    UNIFIABLE = "unifiable"          # structurally normalizable
    STRUCTURAL = "structural"        # structure-similar
    FUZZY = "fuzzy"                  # lexical / fuzzy
    NONE = "none"


# --------------------------------------------------------------------------- #
# Sub-models
# --------------------------------------------------------------------------- #
class StatusInfo(BaseModel):
    """Version / lifecycle metadata (spec 2.1 status columns)."""

    model_config = ConfigDict(extra="ignore")

    introduced_version: Optional[str] = None
    maintenance: MaintenanceStatus = MaintenanceStatus.STABLE
    deprecated: bool = False
    deprecated_replaced_by: Optional[str] = None
    pr_or_commit: Optional[str] = None
    cache_key: Optional[str] = None  # stable id + version, for caller-side caching


class SourceLocation(BaseModel):
    """Pointer to the precise source location."""

    model_config = ConfigDict(extra="ignore")

    file_path: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    github_link: Optional[str] = None


class RelationBlock(BaseModel):
    """Explicit relation lists supplied by an enriched data source.

    When the active source cannot resolve these, the lists stay empty and the
    context-search features fall back to the module import graph instead.
    """

    model_config = ConfigDict(extra="ignore")

    dependencies: List[str] = Field(default_factory=list)   # full names this depends on
    dependents: List[str] = Field(default_factory=list)     # full names that depend on this
    equivalents: List[str] = Field(default_factory=list)    # renamed / refactored equivalents
    generalizes: List[str] = Field(default_factory=list)    # broader results
    specializes: List[str] = Field(default_factory=list)    # special cases
    related: List[str] = Field(default_factory=list)        # proximity / recommended


# --------------------------------------------------------------------------- #
# Primary entity record
# --------------------------------------------------------------------------- #
class MathlibEntity(BaseModel):
    """The normalized record for a single Mathlib 4 declaration / constant.

    This is the universal projection used by every search path. Not all fields are
    populated for every entity; unpopulated optional fields are ``None``/empty and
    rendered away in terse tiers.
    """

    model_config = ConfigDict(extra="ignore")

    # --- identity (spec 2.1 core identity fields) ------------------------- #
    id: str                                   # stable id, e.g. "decl:Mathlib.Algebra.Group.Defs"
    entity_type: EntityType
    raw_kind: str                             # original Lean kind string
    full_name: str                            # fully qualified name
    short_name: str                           # last segment after the final dot
    namespace: str                            # everything before the final dot

    # --- semantics (spec 2.1 semantic fields) ----------------------------- #
    module: str                               # module / file the entity lives in
    type_signature: Optional[str] = None      # Lean type, when available
    statement: Optional[str] = None           # theorem/lemma conclusion as abstract syntax (str)
    doc: Optional[str] = None                 # upstream doc string (natural language, optional)
    domain: Domain = Domain.OTHER
    subdomain: Optional[str] = None
    use_tags: List[UseTag] = Field(default_factory=list)

    # --- links ------------------------------------------------------------ #
    doc_link: Optional[str] = None            # relative doc page
    source: SourceLocation = Field(default_factory=SourceLocation)

    # --- relations / status (spec 2.1 relation + status columns) ---------- #
    relations: RelationBlock = Field(default_factory=RelationBlock)
    status: StatusInfo = Field(default_factory=StatusInfo)

    # --- provenance / quality --------------------------------------------- #
    is_core: bool = False                     # heuristic: widely used / imported
    usage_frequency: int = 0                  # heuristic usage proxy
    enrichment_source: Optional[str] = None   # which source supplied rich fields


class ModuleEntity(BaseModel):
    """A Mathlib 4 module / namespace (spec 2.1 Module/Namespace row)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    entity_type: EntityType = EntityType.MODULE
    full_name: str
    alias: Optional[str] = None
    imported_by: List[str] = Field(default_factory=list)   # modules that import this
    imports: List[str] = Field(default_factory=list)      # modules this imports
    exported: List[str] = Field(default_factory=list)     # exported declaration full names
    domain: Domain = Domain.OTHER
    priority_tier: str = "core"              # "intro" | "core" | "advanced"
    doc_link: Optional[str] = None
    visibility: str = "public"               # public | internal


class NotationEntity(BaseModel):
    """A Mathlib 4 notation / symbol (spec 2.1 Notation/Symbol row).

    Populated by the notation provider; absent entries are simply not returned.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    entity_type: EntityType = EntityType.NOTATION
    symbol: str                              # rendered symbol text / unicode
    latex: Optional[str] = None              # latex form
    precedence: Optional[int] = None
    associativity: Optional[str] = None      # left | right | none
    binds_to: Optional[str] = None           # full name of the bound entity
    type_constraint: Optional[str] = None
    syntax_category: Optional[str] = None
    contexts: List[str] = Field(default_factory=list)   # modules / domains where it applies
    conflicts_with: List[str] = Field(default_factory=list)
    introduced_version: Optional[str] = None
    deprecated: bool = False
    replaced_by: Optional[str] = None


# --------------------------------------------------------------------------- #
# Search output envelopes (spec 4.2)
# --------------------------------------------------------------------------- #
class MatchDimension(BaseModel):
    """Why a hit matched, with a normalized 0..1 contribution."""

    model_config = ConfigDict(extra="ignore")

    dimension: str
    score: float
    tier: MatchTier = MatchTier.FUZZY


class SearchHit(BaseModel):
    """One result row: the entity (at requested granularity) + match evidence."""

    model_config = ConfigDict(extra="ignore")

    entity: Dict                        # serialized at the requested granularity
    score: float                        # aggregate relevance 0..1
    tier: MatchTier
    match_dimensions: List[MatchDimension] = Field(default_factory=list)
    truncated: bool = False             # True if field pruning hit token budget
    reuse_params: Dict = Field(default_factory=dict)  # ready-to-reuse next query params


class SearchResult(BaseModel):
    """Paginated, cursor-addressable result envelope returned by every search tool."""

    model_config = ConfigDict(extra="ignore")

    query: Dict                              # the normalized query that produced this
    total_matches: int                       # estimated total matching the query
    returned: int
    next_cursor: Optional[str] = None        # opaque cursor for the next page
    truncated_low_relevance: bool = False    # tail dropped by budget/depth
    hits: List[SearchHit] = Field(default_factory=list)
    disambiguation: Optional[Dict] = None    # populated on ambiguous exact matches
    negative_feedback: Optional[Dict] = None # populated when total_matches == 0


class BatchResult(BaseModel):
    """Container for batched queries (spec 5.1) — one SearchResult per sub-query."""

    model_config = ConfigDict(extra="ignore")

    count: int
    results: List[SearchResult] = Field(default_factory=list)
    errors: List[Dict] = Field(default_factory=list)  # per-item structured errors
