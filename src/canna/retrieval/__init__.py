"""Candidate retrieval over the Semantic Registry.

Two paths, one approved vocabulary: rule-based matching over stable semantic
ids, labels, approved aliases and definitions, and cosine similarity over an
embedding index of the same text. Both produce candidates. Neither confirms a
meaning, compiles a query or executes anything.
"""

from .candidates import (
    STATUS_AMBIGUOUS,
    STATUS_CANDIDATES,
    STATUS_UNRESOLVED,
    CandidateSource,
    RetrievalCandidate,
    RetrievalResult,
)
from .retriever import Retriever, build_retriever
from .settings import RetrievalSettings, load_settings
from .vocabulary import Vocabulary, load_vocabulary

__all__ = [
    "STATUS_AMBIGUOUS",
    "STATUS_CANDIDATES",
    "STATUS_UNRESOLVED",
    "CandidateSource",
    "RetrievalCandidate",
    "RetrievalResult",
    "RetrievalSettings",
    "Retriever",
    "Vocabulary",
    "build_retriever",
    "load_settings",
    "load_vocabulary",
]
