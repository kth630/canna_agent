"""Three wire encodings of one logical requirement-accounting contract.

Experiment only — these shapes are not the Runtime View contract.

``ARCHITECTURE.md`` section 4 fixes the logical information a semantic query
must preserve (requirement records with source spans, refs, filters and
relationship filters, order, limit, unresolved status) and leaves the wire
encoding to experiment. If a provider rejects nested objects, the fallback must
still keep span, ref, detail and status grouped by a repeated
``requirement_id`` rather than splitting them into independent parallel arrays.

All three encodings carry the same detail vocabulary, so a shape comparison
measures the shape and not a difference in what was asked for.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from .model import (
    AGGREGATE_FUNCTIONS,
    CONDITION_OPERATORS,
    DETAIL_SLOTS,
    REQUIREMENT_KINDS,
    REQUIREMENT_STATUSES,
    SORT_DIRECTIONS,
    TRAVERSALS,
    QuestionSemantics,
    RequirementDetail,
    RequirementRecord,
)

FUNCTION_NAME = "record_question_semantics"
FUNCTION_DESCRIPTION = (
    "질문의 명시 요구를 Runtime View가 제공한 ref만으로 회계한다. "
    "물리 table, column, SQL, JOIN, 상품 ID 목록을 만들지 않는다."
)
LINE_SEPARATOR = "|"
DETAIL_OPERATOR_VOCABULARY = tuple(
    dict.fromkeys(CONDITION_OPERATORS + TRAVERSALS + AGGREGATE_FUNCTIONS + SORT_DIRECTIONS)
)
_DETAIL_GUIDE = (
    "slot별 의미: "
    "condition은 ref=조건 대상 field ref, operator=비교 방식, value=비교 값. "
    "relationship은 ref=predicate ref, operator=관계 방향, value=질문이 지목한 entity ref. "
    "aggregation은 ref=집계 대상 field ref, operator=집계 함수. "
    "order는 ref=정렬 기준 field ref, operator=정렬 방향. "
    "limit은 value=요청한 개수. "
    "comparison_subject는 ref=비교 대상 entity ref."
)


class Encoding(Protocol):
    name: str

    def tool_schema(self) -> dict[str, object]: ...

    def decode(self, arguments: Mapping[str, object]) -> QuestionSemantics: ...

    def shape_hint(self) -> dict[str, object]: ...


def _string_array(description: str) -> dict[str, object]:
    return {"type": "array", "items": {"type": "string"}, "description": description}


def _text(values: object) -> tuple[str, ...]:
    if isinstance(values, str):
        return (values,)
    if isinstance(values, Sequence):
        return tuple(str(item) for item in values)
    return ()


def _records(value: object) -> tuple[Mapping[str, object], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return ()
    return tuple(item for item in value if isinstance(item, Mapping))


def _ordered_unique(values: Sequence[str]) -> tuple[str, ...]:
    """Drop blanks: an empty ref slot means "no ref", not an unknown ref.

    A required ``ref`` string is how the flat encodings say a requirement has no
    candidate, so an empty value must not be scored as an invented ref.
    """
    seen: dict[str, None] = {}
    for value in values:
        if value.strip():
            seen.setdefault(value.strip(), None)
    return tuple(seen)


def _detail_properties() -> dict[str, object]:
    return {
        "slot": {"type": "string", "enum": list(DETAIL_SLOTS)},
        "ref": {"type": "string"},
        "operator": {"type": "string", "enum": list(DETAIL_OPERATOR_VOCABULARY)},
        "value": {"type": "string"},
    }


def _detail_from_mapping(record: Mapping[str, object]) -> RequirementDetail | None:
    slot = str(record.get("slot", "")).strip()
    if not slot:
        return None
    return RequirementDetail(
        slot=slot,
        ref=str(record.get("ref", "")).strip(),
        operator=str(record.get("operator", "")).strip(),
        value=str(record.get("value", "")).strip(),
    )


def _detail_from_line(line: str) -> tuple[str, RequirementDetail] | None:
    parts = [part.strip() for part in line.split(LINE_SEPARATOR)]
    if len(parts) < 3 or parts[0].upper() != "DET":
        return None
    padded = parts + [""] * (6 - len(parts))
    return padded[1], RequirementDetail(
        slot=padded[2], ref=padded[3], operator=padded[4], value=padded[5]
    )


def _requirement(
    requirement_id: str,
    text_span: str,
    kind: str,
    status: str,
    refs: Sequence[str],
    details: Sequence[RequirementDetail],
    note: str = "",
) -> RequirementRecord:
    return RequirementRecord(
        requirement_id=requirement_id,
        text_span=text_span,
        kind=kind,
        status=status,
        refs=_ordered_unique(list(refs)),
        details=tuple(details),
        note=note,
    )


class NestedEncoding:
    """Requirement objects that carry their own ref and detail arrays."""

    name = "nested"

    def tool_schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": FUNCTION_NAME,
                "description": FUNCTION_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["target_dataset_refs", "requirements"],
                    "properties": {
                        "target_dataset_refs": _string_array("질문 대상 상품군의 dataset ref 목록"),
                        "requirements": {
                            "type": "array",
                            "description": "질문에 실제로 표현된 요구 하나당 record 하나",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": [
                                    "requirement_id",
                                    "text_span",
                                    "kind",
                                    "status",
                                    "refs",
                                    "details",
                                ],
                                "properties": {
                                    "requirement_id": {"type": "string"},
                                    "text_span": {
                                        "type": "string",
                                        "description": "질문 원문에서 그대로 잘라 낸 구간",
                                    },
                                    "kind": {"type": "string", "enum": list(REQUIREMENT_KINDS)},
                                    "status": {
                                        "type": "string",
                                        "enum": list(REQUIREMENT_STATUSES),
                                    },
                                    "refs": _string_array(
                                        "이 요구에 필요한 field/predicate/entity ref"
                                    ),
                                    "details": {
                                        "type": "array",
                                        "description": _DETAIL_GUIDE,
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "required": ["slot"],
                                            "properties": _detail_properties(),
                                        },
                                    },
                                    "note": {"type": "string"},
                                },
                            },
                        },
                    },
                },
            },
        }

    def decode(self, arguments: Mapping[str, object]) -> QuestionSemantics:
        requirements = []
        for record in _records(arguments.get("requirements")):
            details = [
                detail
                for detail in (
                    _detail_from_mapping(item) for item in _records(record.get("details"))
                )
                if detail is not None
            ]
            requirements.append(
                _requirement(
                    str(record.get("requirement_id", "")),
                    str(record.get("text_span", "")),
                    str(record.get("kind", "")),
                    str(record.get("status", "")),
                    _text(record.get("refs")),
                    details,
                    str(record.get("note", "")),
                )
            )
        return QuestionSemantics(
            target_dataset_refs=_ordered_unique(_text(arguments.get("target_dataset_refs"))),
            requirements=tuple(requirements),
        )

    def shape_hint(self) -> dict[str, object]:
        return {
            "target_dataset_refs": ["<dataset ref>"],
            "requirements": [
                {
                    "requirement_id": "r1",
                    "text_span": "<질문 원문 구간>",
                    "kind": "<요구 종류>",
                    "status": "<mapped 또는 unresolved 또는 ambiguous>",
                    "refs": ["<ref>"],
                    "details": [{"slot": "<slot>", "ref": "", "operator": "", "value": ""}],
                    "note": "<판단 근거>",
                }
            ],
        }


class GroupedFlatEncoding:
    """Flat record arrays joined by a repeated ``requirement_id``."""

    name = "grouped_flat"

    def tool_schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": FUNCTION_NAME,
                "description": FUNCTION_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "target_dataset_refs",
                        "requirement_records",
                        "ref_records",
                        "detail_records",
                    ],
                    "properties": {
                        "target_dataset_refs": _string_array("질문 대상 상품군의 dataset ref 목록"),
                        "requirement_records": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["requirement_id", "text_span", "kind", "status"],
                                "properties": {
                                    "requirement_id": {"type": "string"},
                                    "text_span": {"type": "string"},
                                    "kind": {"type": "string", "enum": list(REQUIREMENT_KINDS)},
                                    "status": {
                                        "type": "string",
                                        "enum": list(REQUIREMENT_STATUSES),
                                    },
                                    "note": {"type": "string"},
                                },
                            },
                        },
                        "ref_records": {
                            "type": "array",
                            "description": "requirement_id를 반복해 요구와 ref를 묶는다",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["requirement_id", "ref"],
                                "properties": {
                                    "requirement_id": {"type": "string"},
                                    "ref": {"type": "string"},
                                },
                            },
                        },
                        "detail_records": {
                            "type": "array",
                            "description": "requirement_id를 반복해 요구의 세부 의미를 묶는다. "
                            + _DETAIL_GUIDE,
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "required": ["requirement_id", "slot"],
                                "properties": {
                                    "requirement_id": {"type": "string"},
                                    **_detail_properties(),
                                },
                            },
                        },
                    },
                },
            },
        }

    def decode(self, arguments: Mapping[str, object]) -> QuestionSemantics:
        refs_by_requirement: dict[str, list[str]] = {}
        for record in _records(arguments.get("ref_records")):
            requirement_id = str(record.get("requirement_id", ""))
            refs_by_requirement.setdefault(requirement_id, []).append(str(record.get("ref", "")))
        details_by_requirement: dict[str, list[RequirementDetail]] = {}
        for record in _records(arguments.get("detail_records")):
            detail = _detail_from_mapping(record)
            if detail is None:
                continue
            requirement_id = str(record.get("requirement_id", ""))
            details_by_requirement.setdefault(requirement_id, []).append(detail)
        requirements = []
        for record in _records(arguments.get("requirement_records")):
            requirement_id = str(record.get("requirement_id", ""))
            requirements.append(
                _requirement(
                    requirement_id,
                    str(record.get("text_span", "")),
                    str(record.get("kind", "")),
                    str(record.get("status", "")),
                    refs_by_requirement.get(requirement_id, []),
                    details_by_requirement.get(requirement_id, []),
                    str(record.get("note", "")),
                )
            )
        return QuestionSemantics(
            target_dataset_refs=_ordered_unique(_text(arguments.get("target_dataset_refs"))),
            requirements=tuple(requirements),
        )

    def shape_hint(self) -> dict[str, object]:
        return {
            "target_dataset_refs": ["<dataset ref>"],
            "requirement_records": [
                {
                    "requirement_id": "r1",
                    "text_span": "<질문 원문 구간>",
                    "kind": "<요구 종류>",
                    "status": "<mapped 또는 unresolved 또는 ambiguous>",
                    "note": "<판단 근거>",
                }
            ],
            "ref_records": [{"requirement_id": "r1", "ref": "<ref>"}],
            "detail_records": [
                {"requirement_id": "r1", "slot": "<slot>", "ref": "", "operator": "", "value": ""}
            ],
        }


class DelimitedEncoding:
    """String-only arrays whose lines repeat ``requirement_id`` to keep grouping."""

    name = "delimited"

    def tool_schema(self) -> dict[str, object]:
        return {
            "type": "function",
            "function": {
                "name": FUNCTION_NAME,
                "description": FUNCTION_DESCRIPTION,
                "parameters": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "target_dataset_refs",
                        "requirement_lines",
                        "ref_lines",
                        "detail_lines",
                    ],
                    "properties": {
                        "target_dataset_refs": _string_array("질문 대상 상품군의 dataset ref 목록"),
                        "requirement_lines": _string_array(
                            "REQ|requirement_id|kind|status|text_span 형식의 줄. "
                            f"kind는 {', '.join(REQUIREMENT_KINDS)} 중 하나, "
                            f"status는 {', '.join(REQUIREMENT_STATUSES)} 중 하나만 쓴다."
                        ),
                        "ref_lines": _string_array(
                            "REF|requirement_id|ref 형식의 줄. ref가 없는 요구는 줄을 만들지 않는다."
                        ),
                        "detail_lines": _string_array(
                            "DET|requirement_id|slot|ref|operator|value 형식의 줄. "
                            f"slot은 {', '.join(DETAIL_SLOTS)} 중 하나, "
                            f"operator는 {', '.join(DETAIL_OPERATOR_VOCABULARY)} 중 하나만 쓴다. "
                            + _DETAIL_GUIDE
                        ),
                    },
                },
            },
        }

    def decode(self, arguments: Mapping[str, object]) -> QuestionSemantics:
        refs_by_requirement: dict[str, list[str]] = {}
        for line in _text(arguments.get("ref_lines")):
            parts = [part.strip() for part in line.split(LINE_SEPARATOR)]
            if len(parts) < 3 or parts[0].upper() != "REF":
                continue
            refs_by_requirement.setdefault(parts[1], []).append(parts[2])
        details_by_requirement: dict[str, list[RequirementDetail]] = {}
        for line in _text(arguments.get("detail_lines")):
            parsed = _detail_from_line(line)
            if parsed is None:
                continue
            requirement_id, detail = parsed
            details_by_requirement.setdefault(requirement_id, []).append(detail)
        requirements = []
        for line in _text(arguments.get("requirement_lines")):
            parts = [part.strip() for part in line.split(LINE_SEPARATOR)]
            if len(parts) < 4 or parts[0].upper() != "REQ":
                continue
            requirement_id = parts[1]
            requirements.append(
                _requirement(
                    requirement_id,
                    LINE_SEPARATOR.join(parts[4:]) if len(parts) > 4 else "",
                    parts[2],
                    parts[3],
                    refs_by_requirement.get(requirement_id, []),
                    details_by_requirement.get(requirement_id, []),
                )
            )
        return QuestionSemantics(
            target_dataset_refs=_ordered_unique(_text(arguments.get("target_dataset_refs"))),
            requirements=tuple(requirements),
        )

    def shape_hint(self) -> dict[str, object]:
        return {
            "target_dataset_refs": ["<dataset ref>"],
            "requirement_lines": [
                f"REQ|r1|{REQUIREMENT_KINDS[0]}|{REQUIREMENT_STATUSES[0]}|<질문 원문 구간>"
            ],
            "ref_lines": ["REF|r1|<ref>"],
            "detail_lines": [f"DET|r1|{DETAIL_SLOTS[0]}|<ref>|<operator>|<value>"],
        }


ENCODINGS: dict[str, Encoding] = {
    encoding.name: encoding
    for encoding in (NestedEncoding(), GroupedFlatEncoding(), DelimitedEncoding())
}
