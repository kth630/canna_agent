"""Retrieval thresholds as configuration with a recorded basis.

A similarity threshold and a top-k are empirical claims about a model and a
vocabulary, not facts about the domain. Fixing them in code from a handful of
questions would turn a guess into a product constant, so every tunable lives in
a JSON document that must state where its numbers came from.

``basis`` is the point of this module. Until an experiment has been run against
the real index, the shipped defaults declare ``provisional_untested`` and any
report built on them says so.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

CONFIG_ENV = "CANNA_RETRIEVAL_CONFIG"
DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent / "retrieval_config.json"

BASIS_UNTESTED = "provisional_untested"


class SettingsError(ValueError):
    """The retrieval configuration is unusable."""


@dataclass(frozen=True)
class RuleSettings:
    """Bounds on the rule path.

    ``min_substring_characters`` and ``substring_overlap_ratio`` bound how little of
    a registry name may still raise it as a proposal. They cannot promote
    anything: a partial match is never grounding evidence regardless of these
    numbers, so a loose setting costs recall budget, not correctness.
    """

    min_substring_characters: int = 2
    substring_overlap_ratio: float = 0.6
    max_candidates: int = 50

    def validate(self) -> None:
        if self.min_substring_characters < 1:
            raise SettingsError("rule.min_substring_characters must be at least 1")
        if not 0.0 < self.substring_overlap_ratio <= 1.0:
            raise SettingsError("rule.substring_overlap_ratio must be in (0, 1]")
        if self.max_candidates < 1:
            raise SettingsError("rule.max_candidates must be at least 1")


@dataclass(frozen=True)
class EmbeddingSettings:
    """Bounds on the embedding path.

    ``similarity_threshold`` admits a proposal; it never confirms one. The
    experiment measures recall, false-positive rate and latency across a sweep
    of this value, and only the recorded sweep may justify changing it.
    """

    similarity_threshold: float = 0.5
    top_k: int = 20

    def validate(self) -> None:
        if not -1.0 <= self.similarity_threshold <= 1.0:
            raise SettingsError("embedding.similarity_threshold must be a cosine value")
        if self.top_k < 1:
            raise SettingsError("embedding.top_k must be at least 1")


@dataclass(frozen=True)
class RetrievalSettings:
    basis: str = BASIS_UNTESTED
    recorded_at: str = ""
    note: str = ""
    rule: RuleSettings = field(default_factory=RuleSettings)
    embedding: EmbeddingSettings = field(default_factory=EmbeddingSettings)

    @property
    def experimentally_justified(self) -> bool:
        return bool(self.basis) and not self.basis.startswith("provisional")

    def validate(self) -> None:
        if not self.basis.strip():
            raise SettingsError("retrieval settings must declare a basis")
        self.rule.validate()
        self.embedding.validate()

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def from_mapping(payload: dict[str, object]) -> RetrievalSettings:
    rule = payload.get("rule") or {}
    embedding = payload.get("embedding") or {}
    if not isinstance(rule, dict) or not isinstance(embedding, dict):
        raise SettingsError("retrieval settings 'rule' and 'embedding' must be objects")
    settings = RetrievalSettings(
        basis=str(payload.get("basis", "")),
        recorded_at=str(payload.get("recorded_at", "")),
        note=str(payload.get("note", "")),
        rule=RuleSettings(**rule),
        embedding=EmbeddingSettings(**embedding),
    )
    settings.validate()
    return settings


def load_settings(path: Path | None = None) -> RetrievalSettings:
    """Read the configuration, preferring an explicit path then the env override."""
    candidate = path
    if candidate is None:
        override = os.environ.get(CONFIG_ENV, "").strip()
        candidate = Path(override) if override else DEFAULT_CONFIG_PATH
    if not candidate.is_file():
        raise SettingsError(f"retrieval configuration not found at {candidate}")
    return from_mapping(json.loads(candidate.read_text(encoding="utf-8")))


def write_settings(settings: RetrievalSettings, path: Path) -> None:
    settings.validate()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
