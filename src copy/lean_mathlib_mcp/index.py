"""In-memory normalized index over the Mathlib 4 knowledge base.

The index is the single read model consumed by every search capability. It is
built once from a :class:`SourceBundle` and then queried read-only.

Performance note
----------------
The production master index has 425k+ declarations. Materializing a full
:class:`~lean_mathlib_mcp.models.MathlibEntity` for each would cost hundreds of MB
and seconds of startup. Instead we keep a compact ``DeclMeta`` tuple per
declaration for filtering, and construct the rich entity object lazily, only for
results that are actually returned.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Tuple

from .domain import classify_domain, derive_use_tags, is_mathlib
from .models import (
    Domain,
    EntityType,
    MaintenanceStatus,
    MathlibEntity,
    ModuleEntity,
    RelationBlock,
    StatusInfo,
    UseTag,
)
from .sources import SourceBundle

_KIND_MAP = {
    "def": EntityType.DEFINITION,
    "theorem": EntityType.THEOREM,
    "lemma": EntityType.LEMMA,
    "axiom": EntityType.AXIOM,
    "opaque": EntityType.CONSTANT,
    "structure": EntityType.STRUCTURE,
    "inductive": EntityType.INDUCTIVE,
    "ctor": EntityType.CONSTRUCTOR,
    "class": EntityType.TYPECLASS,
    "instance": EntityType.INSTANCE,
    "abbrev": EntityType.ABBREV,
    "constant": EntityType.CONSTANT,
}


@dataclass
class DeclMeta:
    """Compact, filter-friendly metadata for one declaration."""

    entity_type: EntityType
    raw_kind: str
    module: str
    domain: Domain
    subdomain: Optional[str]
    use_tags: Tuple[UseTag, ...]
    is_core: bool
    usage_frequency: int
    has_enrichment: bool
    is_mathlib: bool = True  # True if the owning module is under the Mathlib namespace


def _module_from_doc_link(doc_link: Optional[str]) -> str:
    """Derive the owning module from a docgen ``docLink`` like
    ``./Mathlib/NumberTheory/ADEInequality.html#Foo`` -> ``Mathlib.NumberTheory.ADEInequality``."""
    if not doc_link:
        return ""
    path = doc_link.split("#", 1)[0]
    if path.startswith("./"):
        path = path[2:]
    if path.endswith(".html"):
        path = path[: -len(".html")]
    return path.replace("/", ".")


class MathlibIndex:
    def __init__(self, bundle: SourceBundle) -> None:
        self.meta_src: Dict = bundle.meta
        self._decl: Dict[str, Dict[str, object]] = {}
        self._enriched: Dict[str, Dict[str, object]] = bundle.enriched
        self._meta: Dict[str, DeclMeta] = {}
        self.modules: Dict[str, ModuleEntity] = {}
        self.instances: Dict[str, List[str]] = bundle.instances
        self.instances_for: Dict[str, List[str]] = bundle.instances_for
        self.instance_to_typeclass: Dict[str, str] = {}
        self.notations: List = []  # populated by the loader (NotationEntity list)

        # secondary indexes
        self._by_lower: Dict[str, List[str]] = {}      # lowercased full name -> names
        self._by_short: Dict[str, List[str]] = {}      # short name -> names
        self._by_domain: Dict[Domain, List[str]] = {}
        self._by_tag: Dict[UseTag, List[str]] = {}
        self._module_members: Dict[str, List[str]] = {}

        self._build(bundle)

    # ------------------------------------------------------------------ #
    # Build
    # ------------------------------------------------------------------ #
    def _build(self, bundle: SourceBundle) -> None:
        # instance -> typeclass map
        for tc, insts in self.instances_for.items():
            for inst in insts:
                self.instance_to_typeclass[inst] = tc

        for name, d in bundle.declarations.items():
            raw_kind = str(d.get("raw_kind", "unknown"))
            doc_link = d.get("doc_link")
            module = _module_from_doc_link(doc_link) or name.rsplit(".", 1)[0]
            entity_type = _KIND_MAP.get(raw_kind, EntityType.UNKNOWN)
            domain, subdomain = classify_domain(module)
            tags = tuple(derive_use_tags(name, raw_kind, module))
            enr = self._enriched.get(name, {}) or {}
            usage = len(self.instances_for.get(name, []))
            is_core = usage > 0 or name.startswith("Mathlib.Data") and raw_kind in (
                "def",
                "structure",
                "class",
            )
            self._decl[name] = {"raw_kind": raw_kind, "doc_link": doc_link}
            self._meta[name] = DeclMeta(
                entity_type=entity_type,
                raw_kind=raw_kind,
                module=module,
                domain=domain,
                subdomain=subdomain,
                use_tags=tags,
                is_core=is_core,
                usage_frequency=usage,
                has_enrichment=bool(enr),
                is_mathlib=module.startswith("Mathlib."),
            )
            low = name.lower()
            self._by_lower.setdefault(low, []).append(name)
            short = name.rsplit(".", 1)[-1]
            self._by_short.setdefault(short, []).append(name)
            self._by_domain.setdefault(domain, []).append(name)
            for t in tags:
                self._by_tag.setdefault(t, []).append(name)
            self._module_members.setdefault(module, []).append(name)

        self._build_modules(bundle)

    def _build_modules(self, bundle: SourceBundle) -> None:
        imported_by: Dict[str, List[str]] = {
            m: list(d.get("imported_by", [])) for m, d in bundle.modules.items()
        }
        # invert to imports
        imports: Dict[str, List[str]] = {}
        for m, importers in imported_by.items():
            for imp in importers:
                imports.setdefault(imp, []).append(m)
        for m, importers in imported_by.items():
            domain, _ = classify_domain(m)
            n = len(importers)
            if n >= 500 or m in ("Mathlib",):
                tier = "intro"
            elif n >= 30:
                tier = "core"
            else:
                tier = "advanced"
            self.modules[m] = ModuleEntity(
                id=f"mod:{m}",
                full_name=m,
                imported_by=importers,
                imports=sorted(set(imports.get(m, []))),
                exported=self._module_members.get(m, []),
                domain=domain,
                priority_tier=tier,
                doc_link=f"./{m.replace('.', '/')}.html",
            )

    # ------------------------------------------------------------------ #
    # Identity / lookup
    # ------------------------------------------------------------------ #
    def entity_names(self) -> Iterable[str]:
        return self._decl.keys()

    def get_entity(self, full_name: str) -> Optional[MathlibEntity]:
        meta = self._meta.get(full_name)
        if meta is None:
            return None
        enr = self._enriched.get(full_name, {}) or {}
        short = full_name.rsplit(".", 1)[-1]
        namespace = full_name.rsplit(".", 1)[0] if "." in full_name else ""
        rel = RelationBlock(
            dependencies=list(enr.get("dependencies", []) or []),
            dependents=list(enr.get("dependents", []) or []),
            equivalents=list(enr.get("equivalents", []) or []),
            generalizes=list(enr.get("generalizes", []) or []),
            specializes=list(enr.get("specializes", []) or []),
            related=list(enr.get("related", []) or []),
        )
        tc = self.instance_to_typeclass.get(full_name)
        if meta.entity_type == EntityType.INSTANCE and tc:
            rel.dependencies = rel.dependencies or [tc]
        status = StatusInfo(
            deprecated=bool(enr.get("deprecated", False)),
            deprecated_replaced_by=enr.get("deprecated_replaced_by"),
            maintenance=(
                MaintenanceStatus.DEPRECATED
                if enr.get("deprecated")
                else MaintenanceStatus.STABLE
            ),
            cache_key=f"decl:{full_name}:{self.meta_src.get('mathlib_version', 'live')}",
        )
        return MathlibEntity(
            id=f"decl:{full_name}",
            entity_type=meta.entity_type,
            raw_kind=meta.raw_kind,
            full_name=full_name,
            short_name=short,
            namespace=namespace,
            module=meta.module,
            type_signature=enr.get("type_signature"),
            statement=enr.get("statement"),
            doc=enr.get("doc"),
            domain=meta.domain,
            subdomain=meta.subdomain,
            use_tags=list(meta.use_tags),
            doc_link=self._decl[full_name].get("doc_link"),
            relations=rel,
            status=status,
            is_core=meta.is_core,
            usage_frequency=meta.usage_frequency,
            enrichment_source=("docgen-detail" if meta.has_enrichment else "master-index"),
        )

    def get_module(self, name: str) -> Optional[ModuleEntity]:
        return self.modules.get(name)

    def exact_match(self, full_name: str) -> List[str]:
        """Case-insensitive exact full-name match; returns 0..n names."""
        return list(self._by_lower.get(full_name.lower(), []))

    def short_candidates(self, short_name: str, namespace: Optional[str] = None) -> List[str]:
        """Resolve a short name, optionally confined to a namespace prefix."""
        cands = self._by_short.get(short_name, [])
        if namespace:
            ns_low = namespace.lower()
            cands = [c for c in cands if c.lower().startswith(ns_low)]
        return cands

    # ------------------------------------------------------------------ #
    # Topology
    # ------------------------------------------------------------------ #
    def module_members(self, module: str) -> List[str]:
        return list(self._module_members.get(module, []))

    def imports_of(self, module: str) -> List[str]:
        m = self.modules.get(module)
        return list(m.imports) if m else []

    def imported_by_of(self, module: str) -> List[str]:
        m = self.modules.get(module)
        return list(m.imported_by) if m else []

    def instances_for_typeclass(self, typeclass: str) -> List[str]:
        return list(self.instances_for.get(typeclass, []))

    def instances_with_head(self, head_symbol: str) -> List[str]:
        return list(self.instances.get(head_symbol, []))

    def domain_members(self, domain: Domain) -> List[str]:
        return list(self._by_domain.get(domain, []))

    def tag_members(self, tag: UseTag) -> List[str]:
        return list(self._by_tag.get(tag, []))

    def count(self) -> int:
        return len(self._decl)

    def module_count(self) -> int:
        return len(self.modules)

    # ------------------------------------------------------------------ #
    # Stats for reporting / health
    # ------------------------------------------------------------------ #
    def summary(self) -> Dict[str, object]:
        return {
            "declarations": len(self._decl),
            "modules": len(self.modules),
            "instances": sum(len(v) for v in self.instances_for.values()),
            "enriched": len(self._enriched),
            "source": self.meta_src.get("source", "unknown"),
            "mathlib_version": self.meta_src.get("mathlib_version", "live"),
        }
