"""Deterministic scoring of one decoded accounting result against a fixture.

Experiment only.

Scoring never looks at the question string to decide anything except whether a
recorded span really came from it. It compares ref identity, requirement kind,
requirement status, requirement multiplicity and the preserved detail slots, so
a fixture cannot force one physical plan and a passing run cannot come from
question-text memorisation.

A case passes only when one declared accounting alternative matches the returned
records one-for-one: no expected requirement missing, no extra requirement, every
requirement anchored to the part of the question it came from, and every
condition, relationship, order, limit and comparison subject preserved.
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field

from .model import QuestionSemantics, RequirementDetail, RequirementRecord, RuntimeView

UNKNOWN_REF_KEY = "<unknown-ref>"
ANY_REF_KEY = "*"
_VALUE_STRIP = re.compile(r"[\s,]")
_VALUE_UNITS = ("퍼센트", "%", "원", "년", "개월", "개", "일", "회")


def normalize_value(raw: str) -> str:
    """Reduce a literal to a comparable form without inventing meaning.

    Only whitespace, thousands separators and a trailing unit token are removed.
    Nothing is converted between scales, so "1조" and "1000000000000" stay
    different and a fixture must declare both if both are acceptable.
    """
    text = _VALUE_STRIP.sub("", raw).lower()
    changed = True
    while changed:
        changed = False
        for unit in _VALUE_UNITS:
            if len(text) > len(unit) and text.endswith(unit):
                text = text[: -len(unit)]
                changed = True
    return text


def _record_refs(record: RequirementRecord) -> tuple[str, ...]:
    """Every ref a requirement uses, whether listed directly or inside a detail.

    ``refs`` and the detail slots overlap by design, so scoring reads their
    union. A model that names the condition field only inside the condition is
    accounted the same as one that also repeats it in ``refs``.
    """
    refs = list(record.refs)
    for detail in record.details:
        refs.extend(detail.carried_refs())
    return tuple(dict.fromkeys(refs))


def _key_sets(value: object) -> tuple[frozenset[str], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(
        frozenset(str(key) for key in option)
        for option in value
        if isinstance(option, Sequence) and not isinstance(option, (str, bytes))
    )


def _strings(value: object) -> tuple[str, ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(str(item) for item in value)


@dataclass(frozen=True)
class ExpectedDetail:
    """One piece of question meaning a correct accounting must preserve."""

    slot: str
    ref_key: str = ""
    operator_alternatives: tuple[str, ...] = ()
    value_alternatives: tuple[str, ...] = ()
    value_ref_key: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> ExpectedDetail:
        return cls(
            slot=str(payload["slot"]),
            ref_key=str(payload.get("ref_key", "")),
            operator_alternatives=_strings(payload.get("operator_alternatives", [])),
            value_alternatives=_strings(payload.get("value_alternatives", [])),
            value_ref_key=str(payload.get("value_ref_key", "")),
        )

    def referenced_keys(self) -> frozenset[str]:
        return frozenset(
            key for key in (self.ref_key, self.value_ref_key) if key and key != ANY_REF_KEY
        )

    def matches(self, detail: RequirementDetail, key_by_ref: Mapping[str, str]) -> bool:
        if detail.slot != self.slot:
            return False
        observed_ref_key = key_by_ref.get(detail.ref, UNKNOWN_REF_KEY) if detail.ref else ""
        if self.ref_key != ANY_REF_KEY and observed_ref_key != self.ref_key:
            return False
        if self.operator_alternatives and detail.operator not in self.operator_alternatives:
            return False
        if self.value_ref_key:
            observed = key_by_ref.get(detail.value, UNKNOWN_REF_KEY) if detail.value else ""
            return observed == self.value_ref_key
        if self.value_alternatives:
            accepted = {normalize_value(item) for item in self.value_alternatives}
            return normalize_value(detail.value) in accepted
        return True


@dataclass(frozen=True)
class ExpectedRequirement:
    """One explicit requirement a correct accounting must contain exactly once."""

    label: str
    status: str
    kind_alternatives: tuple[str, ...] = ()
    ref_key_alternatives: tuple[frozenset[str], ...] = ()
    span_anchors: tuple[str, ...] = ()
    details: tuple[ExpectedDetail, ...] = ()
    optional_details: tuple[ExpectedDetail, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> ExpectedRequirement:
        def read_details(name: str) -> tuple[ExpectedDetail, ...]:
            raw = payload.get(name, [])
            if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
                raise TypeError(f"{name} must be a list of expected detail slots")
            return tuple(
                ExpectedDetail.from_mapping(item) for item in raw if isinstance(item, Mapping)
            )

        return cls(
            label=str(payload.get("label", "")),
            status=str(payload["status"]),
            kind_alternatives=_strings(payload.get("kind_alternatives", [])),
            ref_key_alternatives=_key_sets(payload.get("ref_key_alternatives", [])),
            span_anchors=_strings(payload.get("span_anchors", [])),
            details=read_details("details"),
            optional_details=read_details("optional_details"),
        )

    def accepted_keys(self) -> frozenset[str]:
        keys: frozenset[str] = frozenset()
        for option in self.ref_key_alternatives:
            keys |= option
        for detail in (*self.details, *self.optional_details):
            keys |= detail.referenced_keys()
        return keys

    def matches(
        self,
        record: RequirementRecord,
        key_by_ref: Mapping[str, str],
        check_details: bool,
    ) -> bool:
        if record.status != self.status:
            return False
        if self.kind_alternatives and record.kind not in self.kind_alternatives:
            return False
        ref_keys = frozenset(
            key_by_ref.get(ref, UNKNOWN_REF_KEY) for ref in _record_refs(record)
        )
        if self.ref_key_alternatives:
            if not any(option == ref_keys for option in self.ref_key_alternatives):
                return False
        elif ref_keys:
            return False
        if any(anchor not in record.text_span for anchor in self.span_anchors):
            return False
        return not check_details or self._details_match(record, key_by_ref)

    def _details_match(
        self, record: RequirementRecord, key_by_ref: Mapping[str, str]
    ) -> bool:
        """Required slots must all appear; tolerated slots may, and nothing else may.

        ``optional_details`` covers meaning the question carries but that a
        correct accounting need not spell out — an aggregation function, or a
        limit written with the metric ref attached. When such a slot is present
        it is still checked, so a wrong aggregate function or a limit on an
        unrelated candidate still fails.
        """
        remaining = list(record.details)
        for expected in self.details:
            found = next(
                (item for item in remaining if expected.matches(item, key_by_ref)), None
            )
            if found is None:
                return False
            remaining.remove(found)
        for tolerated in self.optional_details:
            found = next(
                (item for item in remaining if tolerated.matches(item, key_by_ref)), None
            )
            if found is not None:
                remaining.remove(found)
        return not remaining


@dataclass(frozen=True)
class Expectation:
    """Fixture-declared expected decision, expressed in catalog keys.

    ``requirement_sets`` holds the accountings that count as equivalent. A
    question with only one correct decomposition declares exactly one set, so a
    different requirement count fails.
    """

    target_dataset_keys: frozenset[str]
    requirement_sets: tuple[tuple[ExpectedRequirement, ...], ...]

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> Expectation:
        datasets = payload.get("target_dataset_keys", [])
        if not isinstance(datasets, Sequence) or isinstance(datasets, (str, bytes)):
            raise TypeError("expected_decision requires target_dataset_keys")
        raw_sets = payload.get("requirement_sets")
        if raw_sets is None:
            raw_sets = [payload.get("requirements", [])]
        if not isinstance(raw_sets, Sequence) or isinstance(raw_sets, (str, bytes)):
            raise TypeError("requirement_sets must be a list of accounting alternatives")
        alternatives: list[tuple[ExpectedRequirement, ...]] = []
        for option in raw_sets:
            if not isinstance(option, Sequence) or isinstance(option, (str, bytes)):
                raise TypeError("each requirement set must be a list of requirements")
            alternatives.append(
                tuple(
                    ExpectedRequirement.from_mapping(item)
                    for item in option
                    if isinstance(item, Mapping)
                )
            )
        if not alternatives or not any(alternatives):
            raise ValueError("expected_decision declares no requirement")
        return cls(
            target_dataset_keys=frozenset(str(key) for key in datasets),
            requirement_sets=tuple(alternatives),
        )

    @property
    def primary_set(self) -> tuple[ExpectedRequirement, ...]:
        return self.requirement_sets[0]

    def ref_universe(self) -> frozenset[str]:
        keys = frozenset(self.target_dataset_keys)
        for option in self.requirement_sets:
            for requirement in option:
                keys |= requirement.accepted_keys()
        return keys


@dataclass(frozen=True)
class SetOutcome:
    """Result of matching the returned records against one alternative set."""

    matched_labels: tuple[str, ...]
    missed_labels: tuple[str, ...]
    extra_requirement_ids: tuple[str, ...]
    expected_count: int
    returned_count: int

    @property
    def recall(self) -> float:
        return len(self.matched_labels) / self.expected_count if self.expected_count else 1.0

    @property
    def precision(self) -> float:
        return len(self.matched_labels) / self.returned_count if self.returned_count else 0.0

    @property
    def exact(self) -> bool:
        return not self.missed_labels and not self.extra_requirement_ids


@dataclass(frozen=True)
class Score:
    """Per-case measurement. Every field is derived, none is hand-set."""

    ref_integrity: bool
    invented_refs: tuple[str, ...]
    dataset_match: bool
    returned_dataset_keys: tuple[str, ...]
    requirement_recall: float
    requirement_precision: float
    matched_labels: tuple[str, ...]
    missed_labels: tuple[str, ...]
    extra_requirement_ids: tuple[str, ...]
    unaccounted_ref_keys: tuple[str, ...]
    spans_verbatim: bool
    spans_distinct: bool
    span_verbatim_ratio: float | None
    matched_alternative: int | None
    details_checked: bool
    case_pass: bool
    diagnostics: tuple[str, ...] = field(default_factory=tuple)

    def as_dict(self) -> dict[str, object]:
        return {
            "ref_integrity": self.ref_integrity,
            "invented_refs": list(self.invented_refs),
            "dataset_match": self.dataset_match,
            "returned_dataset_keys": list(self.returned_dataset_keys),
            "requirement_recall": self.requirement_recall,
            "requirement_precision": self.requirement_precision,
            "matched_labels": list(self.matched_labels),
            "missed_labels": list(self.missed_labels),
            "extra_requirement_ids": list(self.extra_requirement_ids),
            "unaccounted_ref_keys": list(self.unaccounted_ref_keys),
            "spans_verbatim": self.spans_verbatim,
            "spans_distinct": self.spans_distinct,
            "span_verbatim_ratio": self.span_verbatim_ratio,
            "matched_alternative": self.matched_alternative,
            "details_checked": self.details_checked,
            "case_pass": self.case_pass,
            "diagnostics": list(self.diagnostics),
        }


def _match_set(
    expected_set: Sequence[ExpectedRequirement],
    semantics: QuestionSemantics,
    key_by_ref: Mapping[str, str],
    check_details: bool,
) -> SetOutcome:
    remaining = list(semantics.requirements)
    matched: list[str] = []
    missed: list[str] = []
    for expected in expected_set:
        chosen = next(
            (item for item in remaining if expected.matches(item, key_by_ref, check_details)),
            None,
        )
        if chosen is None:
            missed.append(expected.label)
            continue
        remaining.remove(chosen)
        matched.append(expected.label)
    return SetOutcome(
        matched_labels=tuple(matched),
        missed_labels=tuple(missed),
        extra_requirement_ids=tuple(record.requirement_id for record in remaining),
        expected_count=len(expected_set),
        returned_count=len(semantics.requirements),
    )


def score_result(
    question: str,
    runtime_view: RuntimeView,
    semantics: QuestionSemantics,
    expectation: Expectation,
    *,
    check_details: bool = True,
) -> Score:
    """Score one accounting.

    ``check_details`` is lowered only when re-scoring an archived run whose wire
    format had no detail slots; a live run always checks them.
    """
    key_by_ref = runtime_view.key_by_ref()
    known_refs = runtime_view.refs()
    invented = tuple(ref for ref in semantics.all_refs() if ref not in known_refs)
    dataset_keys = tuple(
        key_by_ref.get(ref, UNKNOWN_REF_KEY) for ref in semantics.target_dataset_refs
    )
    dataset_match = frozenset(dataset_keys) == expectation.target_dataset_keys

    outcomes = [
        _match_set(option, semantics, key_by_ref, check_details)
        for option in expectation.requirement_sets
    ]
    best_index = max(
        range(len(outcomes)),
        key=lambda index: (outcomes[index].exact, outcomes[index].recall, -index),
    )
    best = outcomes[best_index]

    spans = [record.text_span for record in semantics.requirements]
    non_empty = [span for span in spans if span]
    spans_verbatim = bool(spans) and all(span and span in question for span in spans)
    span_ratio = (
        sum(1 for span in non_empty if span in question) / len(non_empty) if non_empty else None
    )
    spans_distinct = len(spans) < 2 or len(set(spans)) == len(spans)

    universe = expectation.ref_universe()
    leftover = [
        record
        for record in semantics.requirements
        if record.requirement_id in set(best.extra_requirement_ids)
    ]
    unaccounted = sorted(
        {
            key_by_ref.get(ref, UNKNOWN_REF_KEY)
            for record in leftover
            for ref in _record_refs(record)
        }
        - universe
    )

    diagnostics: list[str] = []
    if invented:
        diagnostics.append("ref not present in this request's runtime view")
    if not dataset_match:
        diagnostics.append("target dataset selection differs from the expected set")
    if best.missed_labels:
        diagnostics.append(
            "expected requirement missing, mis-typed, mis-anchored or losing a detail slot"
        )
    if best.extra_requirement_ids:
        diagnostics.append("requirement records beyond the explicit requirements")
    if not spans_verbatim:
        diagnostics.append("requirement without a verbatim span from the question")
    if not spans_distinct:
        diagnostics.append("requirements share one span instead of anchoring their own part")

    return Score(
        ref_integrity=not invented,
        invented_refs=invented,
        dataset_match=dataset_match,
        returned_dataset_keys=dataset_keys,
        requirement_recall=best.recall,
        requirement_precision=best.precision,
        matched_labels=best.matched_labels,
        missed_labels=best.missed_labels,
        extra_requirement_ids=best.extra_requirement_ids,
        unaccounted_ref_keys=tuple(unaccounted),
        spans_verbatim=spans_verbatim,
        spans_distinct=spans_distinct,
        span_verbatim_ratio=span_ratio,
        matched_alternative=best_index if best.exact else None,
        details_checked=check_details,
        case_pass=(
            not invented
            and dataset_match
            and best.exact
            and spans_verbatim
            and spans_distinct
        ),
        diagnostics=tuple(diagnostics),
    )
