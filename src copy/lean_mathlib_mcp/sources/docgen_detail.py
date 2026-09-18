"""Pluggable rich-detail provider (spec 2.1 enrichment columns).

The docgen master index has no type signatures, docs, or per-declaration
dependency graphs. This provider supplies them from a docgen4 JSON export of the
shape::

    {
      "<Full.Name>": {
        "type_signature": "∀ (n : ℕ), ℕ",
        "doc": "optional upstream doc string",
        "statement": "add_comm n m : n + m = m + n",
        "dependencies": ["Mathlib.Alpha", "Mathlib.Beta"],
        "dependents": ["Mathlib.Gamma"]
      },
      ...
    }

It is *optional*: when no path is configured the server still runs, and the
features that need these fields degrade explicitly (see search/scoring). This is
the single extension point for wiring a local ``lake`` docgen build or a private
mirror without touching any search or output code.
"""
from __future__ import annotations

import json
import os
from typing import Any, Dict, Optional


class DocgenDetailProvider:
    """DetailProvider reading a docgen4-style JSON export."""

    def __init__(self, path: Optional[str]) -> None:
        self.path = path
        self._data: Dict[str, Dict[str, Any]] = {}
        if path:
            resolved = os.path.abspath(path)
            if os.path.exists(resolved):
                with open(resolved, "r", encoding="utf-8") as fh:
                    self._data = json.load(fh)

    def available(self) -> bool:
        return bool(self._data)

    def get_detail(self, full_name: str) -> Optional[Dict[str, Any]]:
        return self._data.get(full_name)

    def as_bundle_enrichment(self) -> Dict[str, Dict[str, Any]]:
        return self._data
