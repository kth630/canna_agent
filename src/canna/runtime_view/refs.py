"""Per-request opaque references.

The model must be able to name a candidate without being able to invent one, to
reuse one from another request, or to reconstruct the Registry from a
transcript. So a reference is minted per request from a random salt, carries no
recoverable trace of the semantic ID it stands for, and resolves only inside the
request that minted it.

The width is deliberate. A truncated digest is a birthday problem waiting to
happen, and a collision here would silently redirect one candidate's reference
to another candidate's meaning — the exact class of error this whole layer
exists to prevent. The digest is kept wide enough that a collision is not a
practical concern, and minting checks for one anyway rather than trusting the
arithmetic.

The kind prefix is deliberate too. It is already visible in the payload — the
candidate sits in a typed list — and having it on the reference lets the server
reject a predicate reference submitted into a field slot without a lookup.
"""

from __future__ import annotations

import hmac
import re
import secrets
from dataclasses import dataclass, field
from hashlib import sha256

KIND_DATASET = "dataset"
KIND_FIELD = "field"
KIND_PREDICATE = "predicate"
KIND_ENTITY = "entity"
KIND_CLASS = "class"

KIND_PREFIXES = {
    KIND_DATASET: "ds",
    KIND_FIELD: "fd",
    KIND_PREDICATE: "pr",
    KIND_ENTITY: "en",
    KIND_CLASS: "cl",
}

# 32 hex characters is 128 bits of the request's HMAC. Wide enough that the
# collision check below is a guard rather than a live concern.
REF_DIGITS = 32
SALT_BYTES = 32

CODE_UNKNOWN_REF = "unknown_ref"
CODE_REF_KIND_MISMATCH = "ref_kind_mismatch"


def reference_pattern(kind: str) -> str:
    """The complete wire format for one reference kind.

    Prefix and width come from the minter's own constants so the parser and
    JSON Schema cannot drift from what is actually minted.
    """
    if kind not in KIND_PREFIXES:
        raise RefError(f"unknown reference kind: {kind!r}")
    return rf"^{re.escape(KIND_PREFIXES[kind])}_[0-9a-f]{{{REF_DIGITS}}}$"


def well_formed_reference(ref: str, kind: str) -> bool:
    return re.fullmatch(reference_pattern(kind), ref) is not None


class RefError(ValueError):
    """A reference is unknown to this request or used in the wrong slot.

    The ``code`` distinguishes the two so a caller does not have to read the
    message text to tell them apart.
    """

    def __init__(self, message: str, code: str = CODE_UNKNOWN_REF) -> None:
        super().__init__(message)
        self.code = code


class RefCollisionError(RuntimeError):
    """Two distinct candidates minted the same reference in one request."""


@dataclass
class RefMinter:
    """Mints and resolves the references of exactly one request."""

    salt: bytes = field(default_factory=lambda: secrets.token_bytes(SALT_BYTES))
    _forward: dict[tuple[str, str], str] = field(default_factory=dict, init=False)
    _reverse: dict[str, tuple[str, str]] = field(default_factory=dict, init=False)

    def mint(self, kind: str, key: str) -> str:
        if kind not in KIND_PREFIXES:
            raise RefError(f"unknown reference kind: {kind!r}")
        existing = self._forward.get((kind, key))
        if existing is not None:
            return existing
        digest = hmac.new(self.salt, f"{kind}\x00{key}".encode(), sha256).hexdigest()
        ref = f"{KIND_PREFIXES[kind]}_{digest[:REF_DIGITS]}"
        claimed = self._reverse.get(ref)
        if claimed is not None and claimed != (kind, key):
            raise RefCollisionError(
                f"reference {ref!r} would name both {claimed!r} and {(kind, key)!r}"
            )
        self._forward[(kind, key)] = ref
        self._reverse[ref] = (kind, key)
        return ref

    def ref_for(self, kind: str, key: str) -> str | None:
        return self._forward.get((kind, key))

    def resolve(self, ref: str, *, expected_kind: str | None = None) -> tuple[str, str]:
        """Return ``(kind, key)`` or refuse. Unknown and cross-request are the same."""
        found = self._reverse.get(ref)
        if found is None:
            raise RefError(f"reference is not part of this request: {ref!r}")
        kind, key = found
        if expected_kind is not None and kind != expected_kind:
            raise RefError(
                f"reference {ref!r} is a {kind} reference, not {expected_kind}",
                code=CODE_REF_KIND_MISMATCH,
            )
        return kind, key

    def knows(self, ref: str) -> bool:
        return ref in self._reverse
