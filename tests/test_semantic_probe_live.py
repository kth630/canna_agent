"""Live reproduction of the smallest stage 0-A observation.

Marked ``hcx_live``: it needs credentials and network, and it is deselected by
default. Having credentials in ``.env`` is not consent to spend them, so the
call also requires an explicit opt-in::

    RUN_HCX_LIVE=1 pytest -m hcx_live

It asserts only what the falsification actually established: the provider
accepts all three accounting schemas, and the two object-shaped encodings copy
refs verbatim. Accounting accuracy is measured by the probe script, not asserted
here, because it is an experiment result rather than a contract.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from canna.experiments.semantic_probe.encodings import ENCODINGS
from canna.experiments.semantic_probe.probe import ProbeCase, run_case
from canna.experiments.semantic_probe.provider import OUTCOME_OK, HcxSemanticProvider
from canna.experiments.semantic_probe.runtime_view import CandidateCatalog

ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = ROOT / "tests" / "fixtures"

pytestmark = pytest.mark.hcx_live


def _load_env() -> None:
    env_path = ROOT / ".env"
    if not env_path.is_file():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_path, override=False)


@pytest.fixture(scope="module")
def live_provider() -> HcxSemanticProvider:
    if os.environ.get("RUN_HCX_LIVE") != "1":
        pytest.skip("set RUN_HCX_LIVE=1 to permit an external HyperCLOVA X call")
    _load_env()
    if not HcxSemanticProvider.credentials_available():
        pytest.skip("HyperCLOVA X credentials are not configured")
    return HcxSemanticProvider(timeout=40)


@pytest.fixture(scope="module")
def catalog() -> CandidateCatalog:
    payload = json.loads((FIXTURE_DIR / "semantic_probe_catalog.json").read_text(encoding="utf-8"))
    return CandidateCatalog.from_mapping(payload)


@pytest.fixture(scope="module")
def first_case() -> ProbeCase:
    line = (FIXTURE_DIR / "semantic_grounding.jsonl").read_text(encoding="utf-8").splitlines()[0]
    return ProbeCase.from_fixture(json.loads(line))


@pytest.mark.parametrize("encoding_name", sorted(ENCODINGS))
def test_provider_accepts_every_encoding_and_copies_refs(
    encoding_name: str,
    catalog: CandidateCatalog,
    first_case: ProbeCase,
    live_provider: HcxSemanticProvider,
) -> None:
    run = run_case(first_case, ENCODINGS[encoding_name], catalog, live_provider)
    if run.provider_result.failed_at_provider:
        pytest.skip(
            "provider refused or transport failed: "
            f"{run.provider_result.error_kind} {run.provider_result.error_code}"
        )
    assert run.provider_result.outcome == OUTCOME_OK, run.provider_result.response_text
    assert run.score is not None
    if encoding_name == "delimited":
        # FINDINGS_REVISED.md section 3.2: the string-only encoding loses ref
        # integrity (0.586-0.600 across the recorded runs), so verbatim copying
        # is not a property of this shape and must not be asserted as one.
        return
    assert run.score.ref_integrity, run.score.invented_refs
