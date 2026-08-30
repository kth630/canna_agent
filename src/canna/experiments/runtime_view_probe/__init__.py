"""Stage 1-A Runtime View retrieval probe — experiment only, not a serving contract.

This package measures the layer before the model: given a question and a
registry that owns all candidate semantics, does the bounded Runtime View
actually carry the dataset, field, predicate and entity candidates the question
needs, in a deterministic order, at a recorded size and latency?

It deliberately has no model call, no semantic query generation, no span
alignment, no compiler, no data access and no answer generation. The candidate
shapes here are a stage 1 experiment artifact; they do not modify the
``ARCHITECTURE.md`` contract, and serving code may not import this package
(``tests/test_architecture_guards.py`` enforces the boundary).
"""

EXPERIMENT_ONLY = True
STAGE = "1-A"
