"""Atomic publication of build outputs.

A rebuild must never destroy a working store.  The build writes a temporary
store and a temporary catalog next to the real ones, and only after every
verification has passed and the database connection is closed are they moved
into place.  A failed build leaves the previous outputs untouched.

The store and its catalog are one generation: they are published together, and
if any file in the generation fails to move, every file already moved is rolled
back to its previous bytes.  A build id written into both artefacts lets a
reader detect a half-published generation that a crash could still leave behind.

A build lock makes a second concurrent build fail fast instead of two writers
racing for the same target.
"""

from __future__ import annotations

import os
from collections.abc import Sequence
from contextlib import contextmanager
from pathlib import Path

LOCK_SUFFIX = ".build-lock"
TEMP_PREFIX = ".building-"
# DuckDB writes a companion write-ahead log next to the database file.
COMPANION_SUFFIXES = (".wal",)


class BuildLockError(RuntimeError):
    """Another build already owns the target, so this one must not start."""


class PublishRollbackError(RuntimeError):
    """A publish failed and the previous generation could not be fully restored.

    Raised with the original publish failure as its cause, because a partially
    restored generation needs a human decision, not a silent retry.
    """


def temp_path(target: Path, token: str) -> Path:
    return target.with_name(f"{TEMP_PREFIX}{token}-{target.name}")


def discard(path: Path) -> None:
    """Remove a temporary artefact and anything the engine wrote beside it."""
    for candidate in (path, *(Path(f"{path}{suffix}") for suffix in COMPANION_SUFFIXES)):
        try:
            candidate.unlink()
        except FileNotFoundError:
            pass


def publish(temporary: Path, target: Path) -> None:
    """Move a verified temporary artefact onto its target in one step."""
    if not temporary.exists():
        raise FileNotFoundError(f"nothing to publish at {temporary}")
    for suffix in COMPANION_SUFFIXES:
        companion = Path(f"{temporary}{suffix}")
        if companion.exists():
            raise RuntimeError(
                f"{temporary.name} still has an open {suffix} companion; "
                "close the connection before publishing"
            )
    os.replace(temporary, target)
    # A stale companion of the previous target would be replayed onto the new file.
    for suffix in COMPANION_SUFFIXES:
        stale = Path(f"{target}{suffix}")
        if stale.exists():
            stale.unlink()


def publish_generation(pairs: Sequence[tuple[Path, Path]], token: str) -> None:
    """Publish several artefacts as one generation, undoing everything on failure.

    A target that existed before is moved aside and restored on failure; a target
    that did not exist before is removed again, so a first build never leaves one
    half of a generation behind.  If the undo itself fails, that is reported
    together with the original failure instead of being swallowed.
    """
    for staging, _ in pairs:
        if not staging.exists():
            raise FileNotFoundError(f"nothing to publish at {staging}")

    existed = {target: target.exists() for _, target in pairs}
    backups: list[tuple[Path, Path]] = []
    attempted: list[Path] = []
    try:
        for staging, target in pairs:
            if existed[target]:
                backup = temp_path(target, f"previous-{token}")
                discard(backup)
                os.replace(target, backup)
                backups.append((target, backup))
            attempted.append(target)
            publish(staging, target)
    except BaseException as error:
        problems = _undo(pairs, existed, backups, attempted)
        if problems:
            raise PublishRollbackError(
                "publish failed and the previous generation could not be fully restored: "
                + "; ".join(problems)
            ) from error
        raise
    for _, backup in backups:
        discard(backup)


def _undo(
    pairs: Sequence[tuple[Path, Path]],
    existed: dict[Path, bool],
    backups: Sequence[tuple[Path, Path]],
    attempted: Sequence[Path],
) -> list[str]:
    """Restore what was there and remove what was not.  Returns what could not be undone.

    Staging files that never made it onto a target are removed too, so a failed
    generation leaves no temporary, backup or half-published file behind.
    """
    problems: list[str] = []
    for target, backup in reversed(backups):
        try:
            os.replace(backup, target)
        except OSError as failure:
            problems.append(f"{target.name}: could not be restored from {backup.name} ({failure})")
    for target in reversed(attempted):
        if existed[target]:
            continue
        try:
            discard(target)
        except OSError as failure:
            problems.append(f"{target.name}: newly published file could not be removed ({failure})")
    for staging, _ in pairs:
        try:
            discard(staging)
        except OSError as failure:
            problems.append(f"{staging.name}: staging file could not be removed ({failure})")
    return problems


@contextmanager
def build_lock(target: Path):
    """Fail fast when another build holds the lock; always release our own."""
    lock = target.with_name(target.name + LOCK_SUFFIX)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        handle = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError as error:
        holder = ""
        try:
            holder = lock.read_text(encoding="utf-8").strip()
        except OSError:
            pass
        raise BuildLockError(
            f"another build holds {lock.name}"
            + (f" (recorded owner: {holder})" if holder else "")
            + "; wait for it to finish or remove the lock file if it is stale"
        ) from error
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as writer:
            writer.write(f"pid={os.getpid()}\n")
        yield lock
    finally:
        try:
            lock.unlink()
        except FileNotFoundError:
            pass
