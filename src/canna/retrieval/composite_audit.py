"""Re-score a stored composite report after a human gold audit, offline.

A published measurement is not corrected by quietly re-running it. The original
report keeps its numbers and its hash; this module reads that report back,
applies an audit file that says which cases had an unsound gold label, and
recomputes only what the stored candidate lists can support. No embedding call
is made, and the audit decisions live in a data file rather than in code, so no
case ID is ever branched on here.

Three audit verdicts exist:

* ``valid`` — the gold stands.
* ``invalid_gold_diagnostic`` — the whole case is unsound and is excluded from
  adjusted scoring while remaining visible as a diagnostic.
* ``invalid_gold_partial`` — one slot of the gold is unsound; the audit removes
  that slot with ``required_overrides`` and the rest of the case still scores.

Forward and inverse predicates are treated as equivalent expressions of one
required meaning, using the Registry's own ``inverse_of`` declaration.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from .composite import (
    SCORED_KINDS,
    CompositeCase,
    CompositeError,
    PreparedCase,
    _global_row,
    _path_recall,
    candidate_kind,
    registry_inverse_alternatives,
)
from .vocabulary import Vocabulary

VERDICT_VALID = "valid"
VERDICT_INVALID_ALL = "invalid_gold_diagnostic"
VERDICT_INVALID_PART = "invalid_gold_partial"
ALLOWED_VERDICTS = {VERDICT_VALID, VERDICT_INVALID_ALL, VERDICT_INVALID_PART}


def load_audit(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    verdicts = payload.get("case_audits")
    if not isinstance(verdicts, list) or not verdicts:
        raise CompositeError("the audit file must list case_audits")
    seen: set[str] = set()
    for row in verdicts:
        case_id = str(row.get("case_id", ""))
        verdict = str(row.get("verdict", ""))
        if not case_id or case_id in seen:
            raise CompositeError(f"missing or duplicate audited case_id: {case_id!r}")
        if verdict not in ALLOWED_VERDICTS:
            raise CompositeError(f"case {case_id} has an unknown audit verdict: {verdict!r}")
        if not str(row.get("reason", "")).strip():
            raise CompositeError(f"case {case_id} audit must record a reason")
        seen.add(case_id)
    return payload


def restore_prepared(
    vocabulary: Vocabulary,
    report: Mapping[str, Any],
    cases: Sequence[CompositeCase],
) -> tuple[PreparedCase, ...]:
    """Rebuild the scored state from a stored report without calling a provider.

    Only the candidate depth the report actually preserved is restored, so a
    recomputation cannot silently claim a top-k the stored artifact never held.
    """
    by_id = {case.case_id: case for case in cases}
    restored: list[PreparedCase] = []
    for row in report["case_results"]:
        case = by_id.get(row["case_id"])
        if case is None:
            raise CompositeError(f"report case {row['case_id']} is absent from the proposal")
        ranking = tuple(
            (str(item["semantic_id"]), float(item["score"])) for item in row["embedding_top20"]
        )
        kinds = {
            semantic_id: candidate_kind(vocabulary, semantic_id)
            for semantic_id, _score in ranking
        }
        for semantic_id in row["rule_candidate_ids"]:
            kinds.setdefault(semantic_id, candidate_kind(vocabulary, semantic_id))
        restored.append(
            PreparedCase(
                case=case,
                rule_ids=tuple(row["rule_candidate_ids"]),
                rule_grounding_ids=tuple(row["rule_grounding_ids"]),
                rule_truncated=int(row.get("rule_truncated", 0)),
                embedding_ranking=ranking,
                latency_ms=float(row.get("latency_ms", 0.0)),
                kinds=kinds,
            )
        )
    return tuple(restored)


def apply_audit(
    vocabulary: Vocabulary,
    prepared: Sequence[PreparedCase],
    audit: Mapping[str, Any],
    *,
    use_registry_inverse: bool = True,
) -> tuple[tuple[PreparedCase, ...], list[dict[str, Any]]]:
    """Return the cases that still score, plus a record of every adjustment."""
    verdicts = {str(row["case_id"]): row for row in audit["case_audits"]}
    kept: list[PreparedCase] = []
    ledger: list[dict[str, Any]] = []
    for item in prepared:
        row = verdicts.get(item.case.case_id)
        verdict = str(row["verdict"]) if row else VERDICT_VALID
        entry: dict[str, Any] = {
            "case_id": item.case.case_id,
            "verdict": verdict,
            "reason": str(row["reason"]) if row else "",
            "removed_required_ids": [],
            "inverse_alternatives_added": {},
            "confusable_ids_reclassified_as_equivalent": [],
        }
        if verdict == VERDICT_INVALID_ALL:
            entry["scored"] = False
            ledger.append(entry)
            continue

        overrides = (row or {}).get("required_overrides") or {}
        required = dict(item.case.required)
        for kind, values in overrides.items():
            if kind not in SCORED_KINDS:
                raise CompositeError(
                    f"case {item.case.case_id} override names unknown kind {kind!r}"
                )
            entry["removed_required_ids"] += [
                value for value in required.get(kind, ()) if value not in set(values)
            ]
            required[kind] = tuple(str(value) for value in values)

        alternatives = {key: tuple(values) for key, values in item.case.alternatives.items()}
        confusion = {key: list(values) for key, values in item.case.confusion_sets.items()}
        if use_registry_inverse:
            for semantic_id in (
                value for kind in SCORED_KINDS for value in required.get(kind, ())
            ):
                inverses = registry_inverse_alternatives(vocabulary, semantic_id)
                if not inverses:
                    continue
                merged = tuple(sorted(set(alternatives.get(semantic_id, ())) | set(inverses)))
                alternatives[semantic_id] = merged
                entry["inverse_alternatives_added"][semantic_id] = list(inverses)
                # A term that is now an accepted expression of the required
                # meaning cannot also be counted as a confusion against it.
                for category, values in confusion.items():
                    reclassified = [value for value in values if value in inverses]
                    if reclassified:
                        entry["confusable_ids_reclassified_as_equivalent"] += reclassified
                        confusion[category] = [
                            value for value in values if value not in inverses
                        ]

        entry["scored"] = True
        ledger.append(entry)
        kept.append(
            PreparedCase(
                case=CompositeCase(
                    case_id=item.case.case_id,
                    section=item.case.section,
                    question=item.case.question,
                    required=required,
                    alternatives=alternatives,
                    entity_mentions=item.case.entity_mentions,
                    confusion_sets={key: tuple(values) for key, values in confusion.items()},
                    allowed_confusable=item.case.allowed_confusable,
                    execution_expectation=item.case.execution_expectation,
                ),
                rule_ids=item.rule_ids,
                rule_grounding_ids=item.rule_grounding_ids,
                rule_truncated=item.rule_truncated,
                embedding_ranking=item.embedding_ranking,
                latency_ms=item.latency_ms,
                kinds=item.kinds,
            )
        )
    return tuple(kept), ledger


def rescore(
    vocabulary: Vocabulary,
    prepared: Sequence[PreparedCase],
    *,
    top_ks: Sequence[int],
) -> dict[str, Any]:
    ks = tuple(sorted({int(value) for value in top_ks}))
    return {
        "path_recall_by_kind": [_path_recall(prepared, k) for k in ks],
        "global_top_k": [_global_row(vocabulary, prepared, k) for k in ks],
        "top_ks": list(ks),
    }


def entity_mention_counts(prepared: Sequence[PreparedCase]) -> dict[str, int]:
    mentions = [
        (item.case.case_id, mention)
        for item in prepared
        for mention in item.case.entity_mentions
    ]
    return {
        "cases_with_entity_mention": len({case_id for case_id, _ in mentions}),
        "entity_mention_count": len(mentions),
    }


def restorable_top_k(report: Mapping[str, Any]) -> int:
    """The deepest top-k the stored candidate lists can honestly support."""
    depths = [
        min(
            len(row["embedding_top20"]) + len(row["rule_candidate_ids"]),
            len(row["embedding_top20"]),
        )
        for row in report["case_results"]
    ]
    return min(depths) if depths else 0
