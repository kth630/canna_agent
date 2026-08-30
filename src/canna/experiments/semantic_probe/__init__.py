"""Stage 0-A semantic grounding probe — experiment only, not a serving contract.

This package measures whether HyperCLOVA X can account for a question's explicit
requirements using nothing but request-scoped opaque refs. It deliberately has
no data access, no query execution and no answer generation.

The wire shapes in ``encodings`` are experiment variables under
``ARCHITECTURE.md`` section 4. They are not the Runtime View contract and must
not be treated as one: stage 1 owns that contract. Serving code may not import
this package (`tests/test_architecture_guards.py` enforces the boundary).
"""

EXPERIMENT_ONLY = True
STAGE = "0-A"
