"""Server configuration.

All knobs are environment-overridable so the server can be deployed read-only with
zero code changes. Safe defaults are chosen for an AI-agent caller: structured JSON
output, conservative token budgets, and Mathlib-only scope by default.
"""
from __future__ import annotations

import os
from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEAN_MATHLIB_", case_sensitive=False)

    # --- data source ----------------------------------------------------- #
    # "auto": use sample fixture if present and small, else download/built index.
    # "sample": force the committed sample fixture (offline, deterministic).
    # "remote": force download of the full production index from DATA_URL.
    data_source: str = "auto"

    # Upstream docgen master index (the production data source).
    data_url: str = (
        "https://leanprover-community.github.io/mathlib4_docs/"
        "declarations/declaration-data.bmp"
    )
    # Local paths (resolved relative to this file's project root when relative).
    cache_dir: str = "data/cache"
    raw_dir: str = "data/raw"
    sample_path: str = "data/sample_index.json"
    built_index_path: str = "data/cache/index.json"

    # --- behaviour ------------------------------------------------------- #
    default_granularity: str = "summary"
    default_max_results: int = 20
    default_token_budget: int = 6000        # soft cap on total output tokens per call
    max_dependency_depth: int = 3
    exclude_deprecated_by_default: bool = False
    mathlib_only: bool = False              # when True, exclude Lean core / stdlib basics
    request_timeout: int = 60

    # --- enrichment ------------------------------------------------------ #
    # Optional path to a docgen4 JSON export supplying type signatures / docs /
    # true dependency graphs. When unset, rich fields degrade gracefully.
    docgen_detail_path: Optional[str] = None

    @property
    def project_root(self) -> str:
        # src/lean_mathlib_mcp/config.py -> project root is three levels up.
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def resolve(self, path: str) -> str:
        return path if os.path.isabs(path) else os.path.join(self.project_root, path)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
