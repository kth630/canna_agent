"""The keyword projection: smaller vocabulary, same content, no reach-back.

On 2026-08-31 the provider refused ``submit_semantic_query`` with API ``40009``
before emitting a tool. The keyword vocabulary was one difference from the
stage 0-A declaration it had accepted, so ``project_for_hcx`` was written to
remove it as a variable. Two further single calls showed the vocabulary was not
sufficient on its own, and the wire moved to the grouped-flat encoding — but
the projector stayed, because whatever schema is sent has to be sent in a
vocabulary a real accepted request used.

So these tests are about the projector, not about one schema. They run it over
both the nested contract and the grouped-flat wire and hold it to the same
three promises: it never touches its input, it emits only accepted keywords,
and it loses none of the content that is not a dropped keyword.

Nothing here reaches the network.
"""

from __future__ import annotations

import copy
import json
from typing import Any

import pytest

from canna.runtime_view import (
    HCX_WIRE_DROPPED_KEYWORDS,
    HCX_WIRE_KEYWORDS,
    SUBMISSION_SCHEMA,
    HcxWireError,
    hcx_tool_definition,
    hcx_wire_schema,
    keyword_vocabulary,
    project_for_hcx,
)
from canna.runtime_view.grouped_flat import GROUPED_FLAT_SCHEMA
from canna.runtime_view.hcx_wire import HCX_WIRE_EXTENSION_PREFIX

SCHEMAS = {"nested_contract": SUBMISSION_SCHEMA, "grouped_flat_wire": GROUPED_FLAT_SCHEMA}


def _containers(node: Any) -> set[int]:
    found: set[int] = set()
    if isinstance(node, dict):
        found.add(id(node))
        for value in node.values():
            found |= _containers(value)
    elif isinstance(node, list):
        found.add(id(node))
        for value in node:
            found |= _containers(value)
    return found


# ------------------------------------------------------- the input is intact


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_projecting_does_not_mutate_its_input(name: str) -> None:
    schema = SCHEMAS[name]
    before = copy.deepcopy(schema)
    projected = project_for_hcx(schema)

    projected["properties"].clear()
    projected["required"].append("nonsense")
    projected["type"] = "string"

    assert schema == before


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_the_projection_shares_no_object_with_its_input(name: str) -> None:
    """Equality is not enough: a shared sub-object is a mutation waiting to happen."""
    schema = SCHEMAS[name]
    assert not _containers(schema) & _containers(project_for_hcx(schema))
    assert project_for_hcx(schema) is not project_for_hcx(schema)


def test_the_adapter_cannot_be_used_to_reach_the_contract() -> None:
    before = copy.deepcopy(SUBMISSION_SCHEMA)
    hcx_tool_definition()["function"]["parameters"]["properties"].clear()
    assert SUBMISSION_SCHEMA == before


# ------------------------------------------------------ the wire vocabulary


def test_the_contract_carries_keywords_the_wire_must_not() -> None:
    """Otherwise every removal assertion below would pass by removing nothing."""
    neutral = keyword_vocabulary(SUBMISSION_SCHEMA)
    assert HCX_WIRE_DROPPED_KEYWORDS <= neutral
    assert any(keyword.startswith(HCX_WIRE_EXTENSION_PREFIX) for keyword in neutral)


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_a_projection_emits_only_accepted_keywords(name: str) -> None:
    projected = keyword_vocabulary(project_for_hcx(SCHEMAS[name]))
    assert projected <= HCX_WIRE_KEYWORDS
    assert not projected & HCX_WIRE_DROPPED_KEYWORDS
    assert not any(keyword.startswith(HCX_WIRE_EXTENSION_PREFIX) for keyword in projected)


def test_no_dropped_keyword_survives_as_text_anywhere_in_the_tool_definition() -> None:
    """A recursive walk can miss a place; the serialised bytes cannot."""
    serialised = json.dumps(hcx_tool_definition(), ensure_ascii=False)
    for keyword in HCX_WIRE_DROPPED_KEYWORDS:
        assert f'"{keyword}"' not in serialised, keyword
    assert f'"{HCX_WIRE_EXTENSION_PREFIX}' not in serialised


def test_the_wire_uses_only_vocabulary_a_real_accepted_request_used() -> None:
    """The kept keywords are evidence, not preference."""
    from canna.experiments.semantic_probe.encodings import GroupedFlatEncoding

    accepted = keyword_vocabulary(GroupedFlatEncoding().tool_schema())
    assert keyword_vocabulary(hcx_wire_schema()) <= accepted
    assert HCX_WIRE_KEYWORDS <= accepted
    assert not HCX_WIRE_DROPPED_KEYWORDS & accepted


# ------------------------------------------------------ the content is not lost


def _logical_shape(node: Any) -> Any:
    """The schema's own content, with the dropped keywords ignored."""
    if isinstance(node, dict):
        shape: dict[str, Any] = {}
        for keyword in ("type", "description", "additionalProperties"):
            if keyword in node:
                shape[keyword] = node[keyword]
        if "required" in node:
            shape["required"] = list(node["required"])
        if "enum" in node:
            shape["enum"] = list(node["enum"])
        if "items" in node:
            shape["items"] = _logical_shape(node["items"])
        if "properties" in node:
            shape["properties"] = {
                name: _logical_shape(child) for name, child in node["properties"].items()
            }
        return shape
    return node


@pytest.mark.parametrize("name", sorted(SCHEMAS))
def test_a_projection_loses_no_property_no_required_and_no_nesting(name: str) -> None:
    schema = SCHEMAS[name]
    assert _logical_shape(project_for_hcx(schema)) == _logical_shape(schema)


def test_the_grouped_flat_wire_is_already_written_in_the_accepted_vocabulary() -> None:
    """Authored in it and projected anyway, so the guarantee is enforced."""
    assert project_for_hcx(GROUPED_FLAT_SCHEMA) == GROUPED_FLAT_SCHEMA


# ------------------------------------------------- an unseen keyword is a decision


@pytest.mark.parametrize(
    "addition",
    [
        {"format": "uuid"},
        {"maxItems": 5},
        {"$ref": "#/$defs/other"},
        {"oneOf": [{"type": "string"}]},
    ],
)
def test_a_keyword_that_is_neither_kept_nor_dropped_refuses_to_be_projected(
    addition: dict[str, Any],
) -> None:
    grown = copy.deepcopy(GROUPED_FLAT_SCHEMA)
    grown["properties"]["requirement_records"]["items"]["properties"]["kind"].update(
        addition
    )
    with pytest.raises(HcxWireError) as raised:
        project_for_hcx(grown)
    assert next(iter(addition)) in str(raised.value)


def test_an_extension_keyword_anywhere_is_dropped_rather_than_refused() -> None:
    grown = copy.deepcopy(GROUPED_FLAT_SCHEMA)
    grown["properties"]["requirement_records"]["items"]["x-note"] = "internal"
    assert keyword_vocabulary(project_for_hcx(grown)) <= HCX_WIRE_KEYWORDS
