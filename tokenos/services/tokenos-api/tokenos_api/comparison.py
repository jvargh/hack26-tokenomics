"""The contract both routes must honour for a cost comparison to be valid.

A saving is only meaningful when the governed route and the all-AI baseline were
asked for the same thing under the same constraints. If the baseline were allowed a
looser schema, a shorter answer, or no citation requirement, it would look cheaper
for reasons that have nothing to do with routing.

Both paths therefore pin the same values here, and both proofs record this block so a
reviewer can confirm the comparison was fair rather than taking it on trust.
"""

from __future__ import annotations

# Bump when the prompt text or the required output shape changes, so two proofs
# produced by different builds are never compared as though they matched.
PROMPT_VERSION = "2026-01-review-v1"
OUTPUT_SCHEMA_VERSION = "findings.v1"

# Identical ceiling on both routes. Without this the baseline could be throttled into
# looking cheap simply by being cut short.
MAX_OUTPUT_TOKENS = 900

CITATION_REQUIREMENT = (
    "Every finding must name a supplied document and cite a policy section present in "
    "the supplied text. Amounts must exist in the extracted source text."
)

# The deterministic gates applied to whatever each route produces.
QUALITY_CHECKS = ("findings_grounded", "amounts_verified", "citations_present")

# Every comparison state a client can observe. Kept as a single enum so the UI never
# has to infer status from a combination of booleans.
STATUS_NOT_REQUESTED = "not_requested"
STATUS_RUNNING = "running"
STATUS_ELIGIBLE_SAVING = "eligible_saving"
STATUS_NO_SAVING = "no_saving"
STATUS_INVALID_COMPARISON = "invalid_comparison"
STATUS_BASELINE_FAILED = "baseline_failed"
STATUS_UNAVAILABLE = "unavailable"


def contract(test_set: str | None = None) -> dict:
    """The block recorded in both proofs."""
    return {
        "prompt_version": PROMPT_VERSION,
        "output_schema_version": OUTPUT_SCHEMA_VERSION,
        "max_output_tokens": MAX_OUTPUT_TOKENS,
        "citation_requirement": CITATION_REQUIREMENT,
        "quality_checks": list(QUALITY_CHECKS),
        "test_set": test_set,
        "note": (
            "Both routes were given the same inputs, the same output schema, the same "
            "citation requirement, the same maximum output length, and the same quality "
            "checks. A comparison is only valid when these match."
        ),
    }


def test_set_id(uploads: list) -> str:
    """A stable identifier for the exact inputs a run was given."""
    names = sorted(getattr(upload, "name", str(upload)) for upload in uploads)
    return f"{len(names)} file(s): " + ", ".join(names)


def matches(left: dict | None, right: dict | None) -> bool:
    """True when two proofs were produced under a comparable contract."""
    if not left or not right:
        return False
    keys = ("prompt_version", "output_schema_version", "max_output_tokens", "test_set")
    return all(left.get(key) == right.get(key) for key in keys)
