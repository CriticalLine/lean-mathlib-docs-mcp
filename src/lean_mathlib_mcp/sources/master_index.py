"""Master-index data source.

Reads the production docgen master index (``declaration-data.bmp`` — a JSON blob
served with a ``.bmp`` content-type) and normalizes it into a
:class:`~lean_mathlib_mcp.sources.SourceBundle`. The first load builds a cached,
re-parsed index so subsequent server starts are fast even with 425k+ declarations.

The master index carries identity + module/instance topology but **not** type
signatures, docs, or per-declaration dependency graphs. Those are supplied by an
optional :class:`DetailProvider` (see ``docgen_detail.py``) and degrade gracefully
when absent.
"""
from __future__ import annotations

import json
import os
import time
import urllib.request
from typing import Any, Dict, List

from . import SourceBundle
from ..config import Settings


def ensure_raw_index(settings: Settings) -> str:
    """Download the master index into ``raw_dir`` if absent; return its path."""
    raw_path = settings.resolve(settings.raw_dir)
    os.makedirs(raw_path, exist_ok=True)
    target = os.path.join(raw_path, "declaration-data.bmp")
    if os.path.exists(target) and os.path.getsize(target) > 0:
        return target
    os.makedirs(os.path.dirname(target), exist_ok=True)
    urllib.request.urlretrieve(settings.data_url, target)
    return target


def parse_bmp(path: str) -> SourceBundle:
    """Parse a raw ``declaration-data.bmp`` JSON blob into a SourceBundle."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    declarations: Dict[str, Dict[str, Any]] = {}
    for name, d in data.get("declarations", {}).items():
        declarations[name] = {
            "raw_kind": d.get("kind", "unknown"),
            "doc_link": d.get("docLink"),
        }

    modules: Dict[str, Dict[str, Any]] = {}
    for name, m in data.get("modules", {}).items():
        modules[name] = {"imported_by": list(m.get("importedBy", []))}

    return SourceBundle(
        meta={
            "source": "docgen-master-index",
            "source_path": path,
            "declaration_count": len(declarations),
            "module_count": len(modules),
            "built_at": time.time(),
        },
        declarations=declarations,
        modules=modules,
        instances=dict(data.get("instances", {})),
        instances_for=dict(data.get("instancesFor", {})),
        enriched={},
    )


def _read_index_json(path: str) -> SourceBundle:
    """Read a pre-built index JSON (may include an ``enriched`` section)."""
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    return SourceBundle(
        meta=data.get("meta", {}),
        declarations=data.get("declarations", {}),
        modules=data.get("modules", {}),
        instances=data.get("instances", {}),
        instances_for=data.get("instancesFor", {}),
        enriched=data.get("enriched", {}),
    )


def _write_index_json(bundle: SourceBundle, path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    payload = {
        "meta": bundle.meta,
        "declarations": bundle.declarations,
        "modules": bundle.modules,
        "instances": bundle.instances,
        "instancesFor": bundle.instances_for,
        "enriched": bundle.enriched,
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))


class MasterIndexSource:
    """DataSource backed by the docgen master index (with caching + sample mode)."""

    def __init__(self, settings: Settings, mode: str | None = None) -> None:
        self.settings = settings
        self.mode = (mode or settings.data_source or "auto").lower()

    def describe(self) -> str:
        return f"MasterIndexSource(mode={self.mode})"

    def load(self) -> SourceBundle:
        settings = self.settings

        if self.mode == "sample":
            return _read_index_json(settings.resolve(settings.sample_path))

        if self.mode == "built":
            built = settings.resolve(settings.built_index_path)
            if os.path.exists(built):
                return _read_index_json(built)
            # fall through to build from remote and cache

        # auto / remote: build (and cache) from the remote master index.
        built = settings.resolve(settings.built_index_path)
        if self.mode == "auto" and os.path.exists(built):
            try:
                return _read_index_json(built)
            except Exception:
                pass  # corrupt cache -> rebuild

        raw = ensure_raw_index(settings)
        bundle = parse_bmp(raw)
        try:
            _write_index_json(bundle, built)
        except OSError:
            pass  # non-fatal: cache is a startup optimization only
        return bundle
