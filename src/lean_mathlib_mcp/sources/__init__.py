"""Data-source abstractions.

A data source turns some upstream artifact (the docgen master index, a pre-built
index, a docgen4 JSON export, ...) into a :class:`SourceBundle` — the neutral,
fully-normalized shape that :class:`~lean_mathlib_mcp.index.MathlibIndex` consumes.

Keeping this boundary explicit is what makes the server *extensible*: a new data
source (e.g. a local ``lake`` docgen export, a private mirror) is a single class
implementing :class:`DataSource`, with no changes to search or output code.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, runtime_checkable


@dataclass
class SourceBundle:
    """Neutral normalized payload consumed by the index builder.

    Fields
    ------
    meta:
        Provenance (source url, build time, mathlib version, counts).
    declarations:
        ``full_name -> {"raw_kind": str, "doc_link": str}``
    modules:
        ``module -> {"imported_by": [module, ...]}``
    instances:
        ``head_symbol -> [instance full_name, ...]``
    instances_for:
        ``typeclass -> [instance full_name, ...]``
    enriched:
        ``full_name -> {type_signature, doc, statement, dependencies,
        dependents, ...}`` — optional rich detail from a DetailProvider.
    """

    meta: Dict[str, Any] = field(default_factory=dict)
    declarations: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    modules: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    instances: Dict[str, List[str]] = field(default_factory=dict)
    instances_for: Dict[str, List[str]] = field(default_factory=dict)
    enriched: Dict[str, Dict[str, Any]] = field(default_factory=dict)


@runtime_checkable
class DataSource(Protocol):
    def load(self) -> SourceBundle:
        """Materialize the source into a :class:`SourceBundle`."""
        ...

    def describe(self) -> str:
        """Human/agent-readable provenance string."""
        ...


@runtime_checkable
class DetailProvider(Protocol):
    def get_detail(self, full_name: str) -> Optional[Dict[str, Any]]:
        """Return enriched fields for one declaration, or ``None`` if unknown."""
        ...

    def as_bundle_enrichment(self) -> Dict[str, Dict[str, Any]]:
        """Return the full ``full_name -> detail`` mapping (may be empty)."""
        ...
