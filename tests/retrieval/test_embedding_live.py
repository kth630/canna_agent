"""Opt-in CLOVA embedding/index compatibility probe.

Ordinary unit runs never call the network.  Run explicitly with both the marker
and the guard environment variable::

    $env:RUN_CLOVA_EMBEDDING_LIVE='1'
    uv run pytest tests/retrieval/test_embedding_live.py -m embedding_live -s -q
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from canna.retrieval.embedding import (
    API_KEY_ENV,
    ClovaStudioEmbeddings,
    load_dotenv_if_present,
)
from canna.retrieval.index import assert_usable, load_index
from canna.retrieval.vocabulary import ROLE_LABEL, load_vocabulary

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.embedding_live


def test_live_query_vector_is_compatible_with_the_local_registry_index() -> None:
    if os.environ.get("RUN_CLOVA_EMBEDDING_LIVE") != "1":
        pytest.skip("set RUN_CLOVA_EMBEDDING_LIVE=1 to permit an external API call")
    load_dotenv_if_present(ROOT)
    if not os.environ.get(API_KEY_ENV, "").strip():
        pytest.fail(f"{API_KEY_ENV} is required for the requested live probe")

    vocabulary = load_vocabulary()
    index = load_index()
    provider = ClovaStudioEmbeddings()
    assert_usable(index, vocabulary, provider.identity)
    query = next(entry for entry in index.entries if entry.role == ROLE_LABEL)
    vector = provider.embed([query.text])[0]
    scored = index.search(vector, top_k=5, threshold=-1.0)

    assert len(vector) == provider.identity.dimension
    assert query.semantic_id in {item.entry.semantic_id for item in scored}
    assert provider.usage.calls == 1
    print(
        json.dumps(
            {
                "status": "ok",
                "model": provider.identity.model,
                "dimension": len(vector),
                "query_role": query.role,
                "returned_semantic_ids": [item.entry.semantic_id for item in scored],
                "usage": provider.usage.to_dict(),
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
