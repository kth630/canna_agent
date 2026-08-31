"""Build the Semantic Registry embedding index against Naver CLOVA Studio.

Usage::

    python scripts/build_retrieval_index.py
    python scripts/build_retrieval_index.py --model clir-sts-dolphin
    python scripts/build_retrieval_index.py --price-per-1k-tokens 0.0

The script reads ``CLOVASTUDIO_API_KEY`` from the environment (``.env`` is read
for local runs) and never prints or writes it. Without a credential, or on any
API failure, the build fails and leaves the previous index untouched — it does
not substitute vectors of its own so that a run can be reported as successful.

Cost is reported only when a rate is supplied with ``--price-per-1k-tokens``.
No published price is assumed on the operator's behalf; token counts are always
recorded.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from canna.retrieval.embedding import (
    DEFAULT_MODEL,
    ClovaStudioEmbeddings,
    CredentialsMissing,
    load_dotenv_if_present,
    model_profile,
)
from canna.retrieval.index import (
    IndexError_,
    assert_usable,
    build_index,
    comparison_index_path,
    load_index,
    write_index,
)
from canna.retrieval.vocabulary import load_vocabulary


def parse_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, default=None)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="manifest path; defaults to a model-isolated directory",
    )
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument(
        "--min-interval",
        type=float,
        default=0.6,
        help="minimum seconds between API calls; the endpoint rate-limits a "
        "several-hundred-call build without pacing",
    )
    parser.add_argument("--price-per-1k-tokens", type=float, default=None)
    parser.add_argument(
        "--force",
        action="store_true",
        help="rebuild even when the existing index already matches this registry state",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse_arguments(argv)
    load_dotenv_if_present(ROOT)
    profile = model_profile(arguments.model)
    output = arguments.output or comparison_index_path(arguments.model)

    vocabulary = load_vocabulary(arguments.registry)
    forms = vocabulary.embeddable_forms()
    print(f"registry      : {vocabulary.source_path}")
    print(f"content hash  : {vocabulary.content_hash}")
    print(f"terms         : {len(vocabulary)}")
    print(f"searchable    : {len(vocabulary) - len(vocabulary.unsearchable_ids())}")
    print(f"surface forms : {len(forms)}")
    print(
        f"model         : {profile.model} ({profile.dimension}d, "
        f"{profile.distance_metric}, {profile.service_contract})"
    )
    print(f"output        : {output}")

    provider = ClovaStudioEmbeddings(
        model=arguments.model,
        timeout=arguments.timeout,
        min_interval_seconds=arguments.min_interval,
    )

    if not arguments.force and output.is_file():
        try:
            existing = load_index(output)
            assert_usable(existing, vocabulary, provider.identity)
        except (IndexError_, OSError, ValueError, TypeError, KeyError):
            existing = None
        if existing is not None:
            print(
                "\nindex already matches this registry hash and provider contract; "
                "pass --force to rebuild"
            )
            return 0

    if not ClovaStudioEmbeddings.credentials_available():
        raise CredentialsMissing(
            "CLOVASTUDIO_API_KEY is not set; refusing to build an index without a "
            "live embedding provider"
        )

    print(f"\nembedding {len(forms)} surface forms ...")
    manifest, entries, vectors = build_index(
        vocabulary, provider, unit_price_per_1k_tokens=arguments.price_per_1k_tokens
    )
    path = write_index(manifest, entries, vectors, output)

    usage = manifest["usage"]
    print(f"\nwrote {path}")
    print(f"entries       : {manifest['entry_count']} {manifest['entries_by_role']}")
    print(f"api calls     : {usage['calls']}")
    print(f"total tokens  : {usage['total_tokens']} (reported={usage['tokens_reported_by_provider']})")
    print(f"api elapsed   : {usage['elapsed_ms']:.0f} ms")
    print(f"throttled     : {usage['throttled_ms']:.0f} ms")
    print(f"rate retries  : {usage['rate_limit_retries']}")
    print(f"estimated cost: {usage['estimated_cost']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
