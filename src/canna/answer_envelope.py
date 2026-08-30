"""External response envelope of the evaluation API.

``contracts/EVALUATION_API.md`` fixes five required string fields and the
``application/json; charset=utf-8`` media type for ``GET /answer``. Those are the
only external guarantees this module owns; it knows nothing about how an answer
is produced, so every later pipeline stage returns the same envelope.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict

# contracts/EVALUATION_API.md: response media type, verbatim.
JSON_MEDIA_TYPE = "application/json; charset=utf-8"


class AnswerEnvelope(BaseModel):
    """The exact external payload of ``GET /answer``.

    ``extra="forbid"`` keeps internal diagnostics from silently widening the
    external contract; a new field would have to be agreed in the contract
    document first.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    question_id: str
    question: str
    retrieved_context: str
    think_trace: str
    answer: str


ENVELOPE_FIELDS: tuple[str, ...] = tuple(AnswerEnvelope.model_fields)
