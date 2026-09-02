"""Offline falsification of the HCX role-reduction proposal's server-side premise.

This package is experiment-only. It does not import from, and is not imported
by, any production runtime path. It reads the production Runtime View modules
read-only so that what it measures is the behaviour those modules already have,
and it never calls a provider, an embedding index or a database.

The premise under test is stated in
``HCX_ROLE_REDUCTION_CONTRACT_PROPOSAL_20260901.md`` section 5.1: that the
server, given only the existing Runtime View and the approved question
metadata, can account for every explicit semantic anchor and requirement frame
and then generate the RequirementOption and PlanOption candidates a model would
choose between. If it cannot, moving the accounting responsibility from HCX to
the server is not a wire simplification.
"""
