"""Credential-free persistence of probe requests and responses.

Experiment only.

Every record is scrubbed of any value held by a credential environment
variable before it is written, so a preserved transcript can be reviewed and
committed without leaking secrets.
"""

from __future__ import annotations

import json
import os
from collections.abc import Iterable, Mapping
from pathlib import Path

REDACTION = "<redacted>"
_MIN_SECRET_LENGTH = 8
_CREDENTIAL_NAME_SUBSTRINGS = ("key", "secret", "token", "password", "credential")
_CREDENTIAL_NAME_PARTS = ("pw", "pass")


def credential_values(environ: Mapping[str, str] | None = None) -> tuple[str, ...]:
    """Collect the environment values that must never appear in a transcript."""
    source = os.environ if environ is None else environ
    values = []
    for name, value in source.items():
        lowered = name.lower()
        parts = set(lowered.split("_"))
        looks_secret = any(token in lowered for token in _CREDENTIAL_NAME_SUBSTRINGS) or bool(
            parts & set(_CREDENTIAL_NAME_PARTS)
        )
        if not looks_secret:
            continue
        stripped = value.strip()
        if len(stripped) >= _MIN_SECRET_LENGTH:
            values.append(stripped)
    return tuple(sorted(set(values), key=len, reverse=True))


def redact(text: str, secrets: Iterable[str]) -> str:
    for secret in secrets:
        if secret and secret in text:
            text = text.replace(secret, REDACTION)
    return text


def write_records(
    path: Path,
    records: Iterable[Mapping[str, object]],
    environ: Mapping[str, str] | None = None,
) -> int:
    """Write JSONL records with credentials removed. Returns the record count."""
    secrets = credential_values(environ)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    with path.open("w", encoding="utf-8") as handle:
        for record in records:
            line = json.dumps(record, ensure_ascii=False, default=str)
            handle.write(redact(line, secrets) + "\n")
            written += 1
    return written
