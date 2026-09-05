"""Locks the approved user-facing workflow card copy.

These four titles and supporting strings are the approved values used on the
Describe cards, the selected-workflow panel, the one-page visual, the docs, and the
demo narration. They are asserted verbatim here so a reworded variant cannot be
reintroduced in one place and silently drift from the others.

Internal workflow IDs are deliberately asserted alongside them: the display copy may
change, the IDs and API values may not.

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_workflow_labels.py -v
"""

from __future__ import annotations

import pytest

# workflow_id -> (card title, supporting text)
APPROVED_COPY = {
    "document_review": (
        "Review documents against rules",
        "Upload records and policies. TokenOS checks what software can verify before "
        "using AI for unclear cases.",
    ),
    "software_validation": (
        "Test a code change",
        "Upload or connect a change. TokenOS runs checks first and uses AI only to "
        "investigate unresolved failures.",
    ),
    "deadline_processing": (
        "Process records by a deadline",
        "Submit a workload and due time. TokenOS completes routine records locally and "
        "reserves AI for exceptions.",
    ),
    "workflow_optimization": (
        "Optimize an existing AI workflow",
        "Connect an AI application or prior run. TokenOS finds the lowest-cost route "
        "that still meets the required quality.",
    ),
}

# Every prior variant of the four displayed titles and supporting texts. None of these
# may appear in any workflow definition again.
RETIRED_COPY = {
    "Compare AI options and prove value",
    "Review documents",
    "Validate software",
    "Meet a deadline",
    "Find false savings",
    "Compare evidence with rules",
    "Inspect and test a change",
    "Process records economically",
    "Include correction effort",
    "Analyze documents against supplied policies and produce evidence-backed findings",
    "Inspect a proposed software change, run allowed validation, and explain remaining risk",
    "Process a supplied dataset by a required time using the least expensive eligible route",
    "Compare AI routes using actual cost, quality, acceptance, and correction data",
    "Evidence-backed business decision",
    "Generate, test, and explain a change",
    "Schedule flexible work economically",
    "Include human correction cost",
}


def _definitions(api_client) -> dict:
    response = api_client.get("/api/workflows")
    assert response.status_code == 200, response.text
    return {item["workflow_id"]: item for item in response.json()["workflows"]}


def test_every_approved_workflow_is_served(api_client):
    definitions = _definitions(api_client)
    assert set(definitions) == set(APPROVED_COPY)


@pytest.mark.parametrize("workflow_id", sorted(APPROVED_COPY))
def test_card_title_matches_approved_copy(api_client, workflow_id):
    definition = _definitions(api_client)[workflow_id]
    expected_title, _ = APPROVED_COPY[workflow_id]
    assert definition["label"] == expected_title


@pytest.mark.parametrize("workflow_id", sorted(APPROVED_COPY))
def test_supporting_text_matches_approved_copy(api_client, workflow_id):
    definition = _definitions(api_client)[workflow_id]
    _, expected_supporting = APPROVED_COPY[workflow_id]
    assert definition["short_label"] == expected_supporting


@pytest.mark.parametrize("workflow_id", sorted(APPROVED_COPY))
def test_card_and_selected_panel_use_the_same_supporting_text(api_client, workflow_id):
    """The Describe card renders `short_label`; the selected-workflow panel ("Provide
    the work") renders `description`. They must be the one approved string, not two
    variants that can drift apart."""
    definition = _definitions(api_client)[workflow_id]
    assert definition["description"] == definition["short_label"]


@pytest.mark.parametrize("workflow_id", sorted(APPROVED_COPY))
def test_no_retired_copy_variant_survives(api_client, workflow_id):
    definition = _definitions(api_client)[workflow_id]
    for field in ("label", "short_label", "description"):
        assert definition[field] not in RETIRED_COPY, (
            f"{workflow_id}.{field} still uses retired copy {definition[field]!r}"
        )


@pytest.mark.parametrize("workflow_id", sorted(APPROVED_COPY))
def test_supporting_text_keeps_the_approved_character_budget(api_client, workflow_id):
    """Approved product copy, rather than an arbitrary shorter limit, is authoritative."""
    definition = _definitions(api_client)[workflow_id]
    assert len(definition["short_label"]) == len(APPROVED_COPY[workflow_id][1])


def test_internal_ids_and_api_values_are_unchanged(api_client):
    """Display copy is allowed to change; the IDs callers send are not."""
    definitions = _definitions(api_client)
    for workflow_id, definition in definitions.items():
        assert definition["workflow_id"] == workflow_id
        assert workflow_id.islower()
        assert " " not in workflow_id


def test_existing_workflow_ids_are_preserved(api_client):
    definitions = _definitions(api_client)
    assert {"document_review", "software_validation", "deadline_processing"} <= definitions.keys()
    assert "false_savings" not in definitions
