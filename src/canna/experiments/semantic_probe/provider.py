"""HyperCLOVA X boundary for the requirement-accounting call.

Experiment only.

Two failure families must never be merged (stage 0-A judgement rule):

* ``provider`` — the external service refused the request or the transport
  failed. Nothing can be concluded about the model's semantic judgement.
* ``model`` — the service answered but the answer is unusable as a semantic
  accounting result.
"""

from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from time import perf_counter

from .encodings import FUNCTION_NAME, Encoding
from .model import RuntimeView
from .prompt import SYSTEM_INSTRUCTIONS, build_payload, render_payload

# Official provider contract values, not data or answer content.
DEFAULT_MODEL = "HCX-007"
API_KEY_ENV = "CLOVASTUDIO_API_KEY"

_ERROR_CODE_PATTERN = re.compile(r"\b(\d{5})\b")
_TRANSPORT_TOKENS = ("connection", "timeout", "timed out", "read error", "ssl")

OUTCOME_OK = "ok"
OUTCOME_PROVIDER_ERROR = "provider_error"
OUTCOME_MODEL_NO_TOOL_CALL = "model_no_tool_call"
OUTCOME_MODEL_INVALID_ARGUMENTS = "model_invalid_arguments"
PROVIDER_OUTCOMES = frozenset({OUTCOME_PROVIDER_ERROR})
MODEL_OUTCOMES = frozenset({OUTCOME_MODEL_NO_TOOL_CALL, OUTCOME_MODEL_INVALID_ARGUMENTS})


@dataclass(frozen=True)
class ProviderResult:
    """One completed attempt at the accounting call."""

    outcome: str
    latency_ms: float
    request_bytes: int
    attempts: int
    arguments: Mapping[str, object] | None = None
    raw_tool_calls: Sequence[Mapping[str, object]] = field(default_factory=tuple)
    response_text: str = ""
    error_kind: str = ""
    error_code: str = ""
    error_message: str = ""

    @property
    def failed_at_provider(self) -> bool:
        return self.outcome in PROVIDER_OUTCOMES

    @property
    def failed_at_model(self) -> bool:
        return self.outcome in MODEL_OUTCOMES


def classify_error(message: str) -> tuple[str, str]:
    """Split a provider exception into (error_kind, error_code)."""
    lowered = message.lower()
    match = _ERROR_CODE_PATTERN.search(message)
    code = match.group(1) if match else ""
    if any(token in lowered for token in _TRANSPORT_TOKENS) and not code:
        return "transport", ""
    if code:
        return "api", code
    return "unknown", ""


def _coerce_arguments(raw: object) -> Mapping[str, object] | None:
    if isinstance(raw, Mapping):
        return raw
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if isinstance(parsed, Mapping):
            return parsed
    return None


def _tool_calls(response: object) -> list[Mapping[str, object]]:
    calls = getattr(response, "tool_calls", None) or []
    return [call for call in calls if isinstance(call, Mapping)]


class HcxSemanticProvider:
    """Invoke one forced accounting function call and time it."""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        timeout: int = 30,
        transport_retries: int = 1,
        chat_factory: object | None = None,
    ) -> None:
        self.model = model
        self.timeout = timeout
        self.transport_retries = transport_retries
        self._chat_factory = chat_factory

    @staticmethod
    def credentials_available() -> bool:
        return bool(os.environ.get(API_KEY_ENV, "").strip())

    def _build_chat(self, tool_schema: Mapping[str, object]):
        if self._chat_factory is not None:
            return self._chat_factory(self.model, self.timeout, tool_schema)
        from langchain_naver import ChatClovaX

        llm = ChatClovaX(model=self.model, timeout=self.timeout, reasoning_effort="none")
        return llm.bind_tools(
            tools=[dict(tool_schema)],
            tool_choice={"type": "function", "function": {"name": FUNCTION_NAME}},
        )

    def call(self, question: str, runtime_view: RuntimeView, encoding: Encoding) -> ProviderResult:
        from langchain_core.messages import HumanMessage, SystemMessage

        payload = build_payload(question, runtime_view, encoding)
        rendered = render_payload(payload)
        request_bytes = len(rendered.encode("utf-8"))
        messages = [
            SystemMessage(content=SYSTEM_INSTRUCTIONS),
            HumanMessage(content=rendered),
        ]
        attempts = 0
        started = perf_counter()
        while True:
            attempts += 1
            try:
                bound = self._build_chat(encoding.tool_schema())
                response = bound.invoke(messages)
            except Exception as error:  # noqa: BLE001 - provider failures are an observation
                message = str(error)
                kind, code = classify_error(message)
                if kind == "transport" and attempts <= self.transport_retries:
                    continue
                return ProviderResult(
                    outcome=OUTCOME_PROVIDER_ERROR,
                    latency_ms=(perf_counter() - started) * 1000,
                    request_bytes=request_bytes,
                    attempts=attempts,
                    error_kind=kind,
                    error_code=code,
                    error_message=message,
                )
            latency_ms = (perf_counter() - started) * 1000
            calls = _tool_calls(response)
            text = str(getattr(response, "content", "") or "")
            if not calls:
                return ProviderResult(
                    outcome=OUTCOME_MODEL_NO_TOOL_CALL,
                    latency_ms=latency_ms,
                    request_bytes=request_bytes,
                    attempts=attempts,
                    response_text=text,
                )
            arguments = _coerce_arguments(calls[0].get("args"))
            if arguments is None:
                return ProviderResult(
                    outcome=OUTCOME_MODEL_INVALID_ARGUMENTS,
                    latency_ms=latency_ms,
                    request_bytes=request_bytes,
                    attempts=attempts,
                    raw_tool_calls=tuple(calls),
                    response_text=text,
                )
            return ProviderResult(
                outcome=OUTCOME_OK,
                latency_ms=latency_ms,
                request_bytes=request_bytes,
                attempts=attempts,
                arguments=arguments,
                raw_tool_calls=tuple(calls),
                response_text=text,
            )
