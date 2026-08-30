"""Build a per-request Runtime View with request-scoped opaque refs.

Experiment only. The candidate catalog is data supplied by the caller, never a
constant in this module. ``ARCHITECTURE.md`` section 4 requires refs to be
minted per request so the model cannot compose or memorise a meaningful
identifier; dataset ownership therefore also travels as a minted ref.
"""

from __future__ import annotations

import random
import string
from collections.abc import Iterable, Mapping, Sequence

from .model import Candidate, RuntimeView

_REF_ALPHABET = string.ascii_lowercase + string.digits
_REF_LENGTH = 8
_CANDIDATE_GROUPS: tuple[str, ...] = ("dataset", "field", "predicate", "entity")


class RefMinter:
    """Mint collision-free opaque refs that carry no type or meaning hint."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng or random.SystemRandom()
        self._issued: set[str] = set()

    def mint(self) -> str:
        while True:
            ref = "".join(self._rng.choice(_REF_ALPHABET) for _ in range(_REF_LENGTH))
            if ref not in self._issued:
                self._issued.add(ref)
                return ref


def permutation(catalog_keys: Sequence[str], seed: int | None) -> tuple[str, ...]:
    """Return the candidate order for one request.

    ``seed is None`` keeps the authored order. Any integer seed produces a
    reproducible shuffle, so a run can be replayed from its recorded seed.
    """
    keys = list(catalog_keys)
    if seed is None:
        return tuple(keys)
    random.Random(seed).shuffle(keys)
    return tuple(keys)


class CandidateCatalog:
    """Synthetic candidate pool addressed by stable catalog keys.

    Catalog keys exist only for authoring fixtures and scoring results. They are
    never sent to the provider.
    """

    def __init__(self, entries: Sequence[Mapping[str, object]]) -> None:
        self._entries: dict[str, dict[str, object]] = {}
        for entry in entries:
            key = str(entry["catalog_key"])
            if key in self._entries:
                raise ValueError(f"duplicate catalog_key: {key}")
            self._entries[key] = dict(entry)

    @classmethod
    def from_mapping(cls, payload: Mapping[str, object]) -> CandidateCatalog:
        candidates = payload.get("candidates")
        if not isinstance(candidates, Sequence):
            raise TypeError("catalog payload requires a 'candidates' sequence")
        return cls(candidates)  # type: ignore[arg-type]

    def keys(self) -> tuple[str, ...]:
        return tuple(self._entries)

    def entry(self, catalog_key: str) -> Mapping[str, object]:
        return self._entries[catalog_key]

    def build_view(
        self,
        catalog_keys: Iterable[str],
        minter: RefMinter,
        order_seed: int | None = None,
    ) -> RuntimeView:
        """Return a Runtime View limited to the requested candidates.

        Datasets are minted first so that every other candidate can point at the
        request-scoped ref of the product family it belongs to. A field offered
        without its owning dataset is a malformed view and is rejected rather
        than silently losing its ownership.
        """
        ordered = permutation(tuple(str(key) for key in catalog_keys), order_seed)
        payloads: dict[str, dict[str, object]] = {}
        for key in ordered:
            entry = self._entries.get(key)
            if entry is None:
                raise KeyError(f"unknown catalog_key: {key}")
            payloads[key] = dict(entry)

        refs: dict[str, str] = {}
        for key, payload in payloads.items():
            if payload.get("kind") == "dataset":
                refs[key] = minter.mint()
        for key, payload in payloads.items():
            if key not in refs:
                refs[key] = minter.mint()

        grouped: dict[str, list[Candidate]] = {kind: [] for kind in _CANDIDATE_GROUPS}
        for key, payload in payloads.items():
            operations = payload.pop("allowed_operations", ())
            dataset_key = payload.get("dataset_key")
            dataset_ref: str | None = None
            if dataset_key is not None:
                dataset_ref = refs.get(str(dataset_key))
                if dataset_ref is None:
                    raise ValueError(
                        f"{key} belongs to {dataset_key} which is not in this runtime view"
                    )
            candidate = Candidate(
                ref=refs[key],
                dataset_ref=dataset_ref,
                allowed_operations=tuple(str(item) for item in operations),  # type: ignore[arg-type]
                **{name: value for name, value in payload.items()},  # type: ignore[arg-type]
            )
            if candidate.kind not in grouped:
                raise ValueError(f"unsupported candidate kind: {candidate.kind}")
            grouped[candidate.kind].append(candidate)
        return RuntimeView(
            datasets=tuple(grouped["dataset"]),
            fields=tuple(grouped["field"]),
            predicates=tuple(grouped["predicate"]),
            entities=tuple(grouped["entity"]),
            presentation_order=ordered,
        )


def rebuild_view(
    catalog: CandidateCatalog,
    ref_key_map: Mapping[str, str],
) -> RuntimeView:
    """Reconstruct the view of an archived run from its recorded ref→key map.

    Used to re-score a preserved transcript under later criteria without
    calling the provider again.
    """
    refs_by_key = {key: ref for ref, key in ref_key_map.items()}
    grouped: dict[str, list[Candidate]] = {kind: [] for kind in _CANDIDATE_GROUPS}
    order: list[str] = []
    for ref, key in ref_key_map.items():
        payload = dict(catalog.entry(key))
        order.append(key)
        operations = payload.pop("allowed_operations", ())
        dataset_key = payload.get("dataset_key")
        candidate = Candidate(
            ref=ref,
            dataset_ref=refs_by_key.get(str(dataset_key)) if dataset_key else None,
            allowed_operations=tuple(str(item) for item in operations),  # type: ignore[arg-type]
            **{name: value for name, value in payload.items()},  # type: ignore[arg-type]
        )
        grouped[candidate.kind].append(candidate)
    return RuntimeView(
        datasets=tuple(grouped["dataset"]),
        fields=tuple(grouped["field"]),
        predicates=tuple(grouped["predicate"]),
        entities=tuple(grouped["entity"]),
        presentation_order=tuple(order),
    )
