"""What ChatClovaX actually puts on the wire, captured without a network call.

Four live calls on 2026-08-31 were refused with ``40009`` before any tool was
emitted, across four different declarations. That makes the question "is our
request even shaped right?" worth answering with evidence rather than reading,
and worth keeping answered: an adapter upgrade could change the serialisation
under us and the next refusal would look like a schema problem again. What is
checked here is the request this SDK builds today -- not why the provider
refused it.

The capture is a mock httpx transport handed to the client. Nothing leaves the
process, the API key is a placeholder set by the test, and only the JSON body
is read — headers are never inspected, printed or asserted on, because the
request id and the credential live there.

The comparison point is the stage 0-A ``grouped_flat`` declaration, re-serialised
today through the currently installed SDK. It is not the raw HTTP body that was
actually sent in 0-A -- that was never preserved -- so this compares two objects
built by today's adapter, and says nothing about the SDK version, client
settings or service state in force when 0-A ran. A difference found here is one
we introduced; an absence of difference here is not proof that the historical
request was identical.

This test constructs its own client and changes nothing about how the live test
or the probe provider build theirs.
"""

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from canna.experiments.semantic_probe.encodings import ENCODINGS
from canna.runtime_view import ENVELOPE_PROPERTY, hcx_tool_definition
from canna.runtime_view.schema import FUNCTION_NAME

# The model and the generation parameters the approved live call uses. Kept
# beside the assertions rather than imported, because importing the live module
# would pull in its marker; if the live call's parameters change, this constant
# is what has to change with them.
LIVE_MODEL = "HCX-007"
LIVE_PARAMETERS: dict[str, Any] = {
    "timeout": 40,
    "max_retries": 0,
    "max_completion_tokens": 8192,
    "reasoning_effort": "none",
}
EXPECTED_PATH = "/v1/openai/chat/completions"


def _capture(monkeypatch, *, model: str, tool: dict, name: str, **parameters: Any) -> dict:
    """Build one request through the real adapter and keep only its body."""
    monkeypatch.setenv("CLOVASTUDIO_API_KEY", "offline-placeholder-not-a-key")
    from langchain_core.messages import HumanMessage, SystemMessage
    from langchain_naver import ChatClovaX

    captured: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # url and body only; headers carry the credential and the request id
        captured["url"] = httpx.URL(request.url)
        captured["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "id": "offline",
                "object": "chat.completion",
                "created": 0,
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "finish_reason": "stop",
                        "message": {"role": "assistant", "content": "ok"},
                    }
                ],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            },
        )

    llm = ChatClovaX(
        model=model,
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        **parameters,
    )
    llm.bind_tools(
        tools=[tool],
        tool_choice={"type": "function", "function": {"name": name}},
    ).invoke([SystemMessage(content="s"), HumanMessage(content="u")])
    return captured


@pytest.fixture
def live_request(monkeypatch) -> dict:
    return _capture(
        monkeypatch,
        model=LIVE_MODEL,
        tool=hcx_tool_definition(),
        name=FUNCTION_NAME,
        **LIVE_PARAMETERS,
    )


@pytest.fixture
def reserialised_0a_request(monkeypatch) -> dict:
    """The 0-A ``grouped_flat`` declaration, re-serialised by today's adapter.

    The provider accepted that declaration 93 times out of 93 in 0-A, but what
    is rebuilt here is the declaration, not the recorded request. No raw body
    from those runs was kept.
    """
    tool = ENCODINGS["grouped_flat"].tool_schema()
    return _capture(
        monkeypatch,
        model=LIVE_MODEL,
        tool=dict(tool),
        name=tool["function"]["name"],
        timeout=30,
        reasoning_effort="none",
    )


# ------------------------------------------------------------------- endpoint


def test_the_request_goes_to_the_openai_compatible_chat_completions_endpoint(
    live_request,
) -> None:
    url = live_request["url"]
    assert url.path == EXPECTED_PATH
    assert url.host.endswith("ntruss.com")
    assert not url.query


def test_the_model_is_the_one_the_call_asked_for(live_request) -> None:
    assert live_request["body"]["model"] == LIVE_MODEL


# ---------------------------------------------------------------- generation


def test_the_token_limit_is_sent_once_and_under_the_openai_compatible_name(
    live_request,
) -> None:
    body = live_request["body"]
    assert body["max_completion_tokens"] == LIVE_PARAMETERS["max_completion_tokens"]
    # sending both is a documented way to get a 400; the adapter renames rather
    # than duplicating, and this is what keeps that true
    assert "max_tokens" not in body


def test_reasoning_effort_and_thinking_effort_reach_the_wire_as_one_field(
    monkeypatch,
) -> None:
    """``thinking={'effort': x}`` and ``reasoning_effort=x`` are the same request.

    The adapter converts the first into the second before the client is built,
    so there is one wire spelling and no way to send a conflicting pair.
    """
    as_effort = _capture(
        monkeypatch,
        model=LIVE_MODEL,
        tool=hcx_tool_definition(),
        name=FUNCTION_NAME,
        reasoning_effort="none",
    )["body"]
    as_thinking = _capture(
        monkeypatch,
        model=LIVE_MODEL,
        tool=hcx_tool_definition(),
        name=FUNCTION_NAME,
        thinking={"effort": "none"},
    )["body"]
    assert as_effort["reasoning_effort"] == "none"
    assert as_thinking["reasoning_effort"] == "none"
    assert "thinking" not in as_effort
    assert "thinking" not in as_thinking


# --------------------------------------------------------------------- tools


def test_the_tool_is_sent_in_the_openai_function_envelope(live_request) -> None:
    body = live_request["body"]
    assert len(body["tools"]) == 1
    tool = body["tools"][0]
    assert tool["type"] == "function"
    assert set(tool["function"]) == {"name", "description", "parameters"}
    assert tool["function"]["name"] == FUNCTION_NAME
    assert tool["function"]["parameters"]["type"] == "object"
    assert tool["function"]["parameters"]["required"] == [ENVELOPE_PROPERTY]


def test_the_tool_choice_forces_the_tool_that_was_sent(live_request) -> None:
    body = live_request["body"]
    assert body["tool_choice"] == {
        "type": "function",
        "function": {"name": FUNCTION_NAME},
    }
    assert body["tool_choice"]["function"]["name"] == body["tools"][0]["function"]["name"]


def test_the_request_is_not_streaming(live_request) -> None:
    assert live_request["body"]["stream"] is False


# ------------------- both declarations serialise to the same envelope today


def test_both_declarations_serialise_to_the_same_envelope_under_this_sdk(
    live_request, reserialised_0a_request
) -> None:
    """Today's adapter builds the same envelope for both declarations.

    That narrows where a difference can live: under this SDK, it is not in the
    endpoint or the envelope. It does not establish what the 0-A requests
    looked like on the wire, and it does not make the declaration's content the
    only remaining variable in the refusals -- the service state is not
    observable from here at all.
    """
    ours, other = live_request["body"], reserialised_0a_request["body"]
    assert live_request["url"].path == reserialised_0a_request["url"].path

    # same envelope keys, apart from the token limit we add
    assert set(ours) - set(other) == {"max_completion_tokens"}
    assert set(other) - set(ours) == set()

    for key in ("model", "reasoning_effort", "stream"):
        assert ours[key] == other[key]
    for body in (ours, other):
        assert body["tools"][0]["type"] == "function"
        assert set(body["tools"][0]["function"]) == {"name", "description", "parameters"}
        assert set(body["tool_choice"]) == {"type", "function"}


def test_the_bridge_declaration_is_smaller_and_plainer_than_the_0a_one(
    live_request, reserialised_0a_request
) -> None:
    """Two measurements, and only those two.

    After the 2026-08-31 bridge, our declaration is one object with one required
    string: it serialises smaller than the 0-A declaration and uses a subset of
    its JSON Schema vocabulary, because the grouped-flat structure now travels
    inside the string instead of beside it. That is a shape relationship, not a
    prediction about acceptance.
    """

    def keywords(node: Any, found: set[str] | None = None) -> set[str]:
        found = set() if found is None else found
        if isinstance(node, dict):
            for key, value in node.items():
                found.add(key)
                if key == "properties":
                    for child in value.values():
                        keywords(child, found)
                else:
                    keywords(value, found)
        elif isinstance(node, list):
            for child in node:
                keywords(child, found)
        return found

    ours = live_request["body"]["tools"][0]["function"]["parameters"]
    other = reserialised_0a_request["body"]["tools"][0]["function"]["parameters"]

    # a subset of the 0-A vocabulary: no enum, no additionalProperties, no nesting
    assert keywords(ours) < keywords(other)
    assert ours["type"] == other["type"] == "object"
    # far below the 0-A declaration rather than several times its size
    ours_bytes = len(json.dumps(ours, ensure_ascii=False).encode("utf-8"))
    other_bytes = len(json.dumps(other, ensure_ascii=False).encode("utf-8"))
    assert ours_bytes < other_bytes
    # the declarations are otherwise unlike each other, which this does not measure
    assert (
        live_request["body"]["tools"][0]["function"]["name"]
        != reserialised_0a_request["body"]["tools"][0]["function"]["name"]
    )


def test_the_capture_never_looks_at_headers(live_request) -> None:
    """The credential and the request id live in headers; nothing reads them."""
    assert set(live_request) == {"url", "body"}
    serialised = json.dumps(live_request["body"], ensure_ascii=False)
    assert "offline-placeholder-not-a-key" not in serialised
    assert "authorization" not in serialised.lower()
