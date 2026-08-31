"""Combine three model reports only when their evaluation contracts match."""

from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime
from pathlib import Path

EXPECTED_MODELS = {"clir-sts-dolphin", "clir-emb-dolphin", "bge-m3"}


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("reports", type=Path, nargs=3)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def main() -> int:
    arguments = parse_arguments()
    payloads = [json.loads(path.read_text(encoding="utf-8")) for path in arguments.reports]
    contracts = {
        (
            payload.get("proposal_id"),
            payload.get("approval_reference"),
            payload.get("questions_sha256"),
            payload.get("report", {}).get("registry_content_hash"),
        )
        for payload in payloads
    }
    if len(contracts) != 1:
        raise ValueError("reports do not share proposal, approval, questions, and Registry hash")
    models = {payload["report"]["model"]["model"] for payload in payloads}
    if models != EXPECTED_MODELS:
        raise ValueError(f"expected exactly {sorted(EXPECTED_MODELS)}, received {sorted(models)}")

    comparison = {
        "experiment": "semantic_retrieval_three_model_comparison",
        "generated_at": datetime.now(UTC).isoformat(),
        "shared_contract": next(iter(contracts)),
        "models": {
            payload["report"]["model"]["model"]: {
                "provider_contract": payload["report"]["model"],
                "rule_only_recall": payload["report"]["rule_only_recall"],
                "ranking_metrics_without_threshold": payload["report"][
                    "ranking_metrics_without_threshold"
                ],
                "latency_ms": payload["report"]["latency_ms"],
                "threshold_basis": payload["report"]["threshold_basis"],
                "thresholds": payload["report"]["thresholds"],
                "sweep": payload["report"]["sweep"],
                "failure_analysis": payload["report"]["failure_analysis"],
            }
            for payload in payloads
        },
        "selection_status": "evidence_ready_no_model_selected_automatically",
        "question_text_in_report": False,
    }
    arguments.output.parent.mkdir(parents=True, exist_ok=True)
    arguments.output.write_text(
        json.dumps(comparison, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(f"wrote comparison: {arguments.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
