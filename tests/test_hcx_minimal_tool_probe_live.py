"""Does HCX-007 do function calling at all, through this client, right now?

Four project declarations were refused with ``40009`` before any tool was
emitted. Every one of them carried project content, so none of them can answer
the prior question: whether this model, key and client can emit a tool call for
a declaration nobody could object to.

So this probe carries no project content at all — no Runtime View, no
grouped-flat schema, no semantic references. Just the smallest function
declaration the provider's own documentation shape suggests: one object, one
string property, one required entry.

The generation parameters are held identical to the approved live call —
HCX-007, ``reasoning_effort="none"``, ``max_completion_tokens=8192``,
``max_retries=0``, the same timeout, the same forced tool choice — because
those are what a control has to keep. The message is not the live harness's
message: that one embeds the Runtime View payload, which this probe exists to
leave out. A minimal tool with a Runtime View prompt would be neither the live
request nor a control.

One call, no retry, no embedding, no execution. Opt-in twice over: the marker
and ``RUN_HCX_LIVE=1``.
"""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from pathlib import Path

import pytest

from canna.experiments.semantic_probe.provider import (
    API_KEY_ENV,
    DEFAULT_MODEL,
    classify_error,
)

pytestmark = pytest.mark.hcx_live

ROOT = Path(__file__).resolve().parents[1]

PROBE_FUNCTION_NAME = "get_weather"

# The documentation-example shape: one object, one string property, one
# required entry, one description each. Nothing about this project appears in
# it, which is the point.
MINIMAL_TOOL = {
    "type": "function",
    "function": {
        "name": PROBE_FUNCTION_NAME,
        "description": "Get the current weather for a city.",
        "parameters": {
            "type": "object",
            "properties": {
                "city": {"type": "string", "description": "The city name."},
            },
            "required": ["city"],
        },
    },
}

SYSTEM_TEXT = "Call the provided function to answer."
HUMAN_TEXT = "서울 날씨 알려줘."


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    from dotenv import load_dotenv

    load_dotenv(env_path, override=False)


def test_the_minimal_function_declaration_is_accepted_once() -> None:
    """One call. Records whether HCX-007 function calling works here at all."""
    if os.environ.get("RUN_HCX_LIVE") != "1":
        pytest.skip("set RUN_HCX_LIVE=1 to permit the one approved external call")
    _load_env()
    if not os.environ.get(API_KEY_ENV, "").strip():
        pytest.skip("HyperCLOVA X credentials are not configured")

    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_naver import ChatClovaX

    report: dict[str, object] = {
        "model": DEFAULT_MODEL,
        "tool_definition_bytes": len(
            json.dumps(MINIMAL_TOOL, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ),
        "provider_schema_acceptance": "not_called",
        "tool_emitted": "no",
        "tool_name_exact": "no",
        "arguments_parsed": "no",
        "external_call_count": 0,
        "retry_count": 0,
        "embedding_call_count": 0,
    }

    llm = ChatClovaX(
        model=DEFAULT_MODEL,
        timeout=40,
        max_retries=0,
        max_completion_tokens=8192,
        reasoning_effort="none",
    )
    bound = llm.bind_tools(
        tools=[MINIMAL_TOOL],
        tool_choice={"type": "function", "function": {"name": PROBE_FUNCTION_NAME}},
    )
    try:
        report["external_call_count"] = 1
        response = bound.invoke(
            [SystemMessage(content=SYSTEM_TEXT), HumanMessage(content=HUMAN_TEXT)]
        )
    except Exception as error:  # noqa: BLE001 - sanitized provider observation
        kind, code = classify_error(str(error))
        report["provider_schema_acceptance"] = "rejected"
        report["provider_error_kind"] = kind
        report["provider_error_code"] = code
        print("HCX_MINIMAL_TOOL_RESULT=" + json.dumps(report, ensure_ascii=False))
        pytest.fail(f"provider rejected the minimal declaration: kind={kind}, code={code}")

    report["provider_schema_acceptance"] = "accepted"
    calls = [
        call
        for call in (getattr(response, "tool_calls", None) or ())
        if isinstance(call, Mapping)
    ]
    report["tool_emitted"] = "yes" if calls else "no"
    report["tool_call_count"] = len(calls)
    if calls:
        call = calls[0]
        report["tool_name_exact"] = (
            "yes" if call.get("name") == PROBE_FUNCTION_NAME else "no"
        )
        raw = call.get("args")
        parsed = raw if isinstance(raw, Mapping) else None
        if parsed is None and isinstance(raw, str):
            try:
                loaded = json.loads(raw)
            except json.JSONDecodeError:
                loaded = None
            parsed = loaded if isinstance(loaded, Mapping) else None
        report["arguments_parsed"] = "yes" if parsed is not None else "no"
        report["argument_keys"] = sorted(parsed) if parsed is not None else []
    print("HCX_MINIMAL_TOOL_RESULT=" + json.dumps(report, ensure_ascii=False))

    assert report["external_call_count"] == 1
    assert report["retry_count"] == 0
    assert report["provider_schema_acceptance"] == "accepted"
    assert report["tool_emitted"] == "yes"
    assert report["tool_name_exact"] == "yes"
