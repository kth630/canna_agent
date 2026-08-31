"""Project the logical submission schema onto what HCX has actually accepted.

The server's contract and the provider's tolerance are two different things,
and the 2026-08-31 probe showed they are not the same thing here: the provider
refused ``submit_semantic_query`` with API error ``40009`` before any tool was
emitted, while the stage 0-A ``record_question_semantics`` declaration — same
OpenAI-style function envelope, same forced ``tool_choice``, same nested
objects and arrays, same ``additionalProperties: false`` — had been accepted
repeatedly. What the two declarations do not share is JSON Schema vocabulary:
the new one carries ``$schema``, ``$id``, ``title``, an ``x-`` extension,
``pattern``, ``minLength`` and ``minItems``; the accepted one carries none of
them.

So this module isolates that one variable. It is a projection, not a second
definition: it reads ``SUBMISSION_SCHEMA`` and emits a new object built only
from the keywords that a real accepted request used. Nothing is projected back.
The server keeps enforcing the whole contract — the complete reference format,
non-empty spans, at least one requirement, closed objects, typed slots — in the
parser, which never sees the wire form. Dropping ``pattern`` from what the
model is shown does not make a malformed reference acceptable; it only stops
the provider being asked to understand a keyword it may not.

The projection is deliberately strict about its own inputs. A keyword that is
neither kept nor listed as dropped raises, because a schema that grows a new
keyword must be a decision someone makes, not a field that quietly vanishes on
the wire or quietly reaches a provider that has already rejected one request.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

__all__ = [
    "HCX_WIRE_DROPPED_KEYWORDS",
    "HCX_WIRE_EXTENSION_PREFIX",
    "HCX_WIRE_KEYWORDS",
    "HcxWireError",
    "keyword_vocabulary",
    "project_for_hcx",
]

# Every keyword that appears in the stage 0-A declaration the provider did
# accept (``src/canna/experiments/semantic_probe/encodings.py``,
# ``NestedEncoding.tool_schema``). Nothing here is a guess about what HCX
# supports in general; it is the vocabulary of a request that actually worked.
HCX_WIRE_KEYWORDS = frozenset(
    {
        "type",
        "properties",
        "required",
        "items",
        "enum",
        "description",
        "additionalProperties",
    }
)

# Present in the rejected declaration and absent from the accepted one. These
# are dropped from the wire form only; the parser enforces what they say.
HCX_WIRE_DROPPED_KEYWORDS = frozenset(
    {
        "$schema",
        "$id",
        "title",
        "pattern",
        "minLength",
        "minItems",
    }
)

# Contract annotations travel with the server's own definition, not to a
# provider that has to parse them.
HCX_WIRE_EXTENSION_PREFIX = "x-"


class HcxWireError(ValueError):
    """The schema contains something this projection will not decide alone."""


def _dropped(keyword: str) -> bool:
    return keyword in HCX_WIRE_DROPPED_KEYWORDS or keyword.startswith(
        HCX_WIRE_EXTENSION_PREFIX
    )


def _strings(value: Any, *, keyword: str, path: str) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        raise HcxWireError(f"{path}.{keyword} must be a list")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise HcxWireError(f"{path}.{keyword} must contain only strings")
        out.append(item)
    return out


def _node(node: Any, path: str) -> dict[str, Any]:
    """One schema object, rebuilt from scratch in the accepted vocabulary."""
    if not isinstance(node, Mapping):
        raise HcxWireError(f"{path} is not a schema object")
    projected: dict[str, Any] = {}
    for keyword, value in node.items():
        if not isinstance(keyword, str):
            raise HcxWireError(f"{path} has a non-string keyword")
        if _dropped(keyword):
            continue
        if keyword not in HCX_WIRE_KEYWORDS:
            raise HcxWireError(
                f"{path}.{keyword} is neither kept on the HCX wire nor listed as "
                "dropped; decide which before sending it to a provider"
            )
        projected[keyword] = _value(keyword, value, path)
    return projected


def _value(keyword: str, value: Any, path: str) -> Any:
    if keyword == "properties":
        if not isinstance(value, Mapping):
            raise HcxWireError(f"{path}.properties must be an object")
        return {
            str(name): _node(child, f"{path}.properties.{name}")
            for name, child in value.items()
        }
    if keyword == "items":
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            return [_node(child, f"{path}.items[{index}]") for index, child in enumerate(value)]
        return _node(value, f"{path}.items")
    if keyword == "additionalProperties":
        if isinstance(value, bool):
            return value
        return _node(value, f"{path}.additionalProperties")
    if keyword in {"required", "enum"}:
        return _strings(value, keyword=keyword, path=path)
    if keyword in {"type", "description"}:
        if not isinstance(value, str):
            raise HcxWireError(f"{path}.{keyword} must be text")
        return value
    raise HcxWireError(f"{path}.{keyword} has no projection rule")  # pragma: no cover


def project_for_hcx(schema: Mapping[str, Any]) -> dict[str, Any]:
    """Return a deep copy of ``schema`` in the vocabulary HCX has accepted.

    The result shares no object with the input, so a provider adapter cannot
    reach back into the server's contract.
    """
    return _node(schema, "$")


def keyword_vocabulary(node: Any) -> frozenset[str]:
    """Every schema keyword used anywhere in ``node``.

    Property names are not keywords: the map under ``properties`` is data the
    contract names, so it is descended into but not collected.
    """
    found: set[str] = set()
    if isinstance(node, Mapping):
        for keyword, value in node.items():
            found.add(str(keyword))
            if keyword == "properties" and isinstance(value, Mapping):
                for child in value.values():
                    found |= keyword_vocabulary(child)
            else:
                found |= keyword_vocabulary(value)
    elif isinstance(node, Sequence) and not isinstance(node, str | bytes):
        for child in node:
            found |= keyword_vocabulary(child)
    return frozenset(found)
