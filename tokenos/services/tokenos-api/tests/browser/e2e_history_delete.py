"""History deletion in the browser.

Run explicitly: python -m pytest -c pytest-browser.ini -v.

A recorded proof is a durable claim, so the UI must never delete one on a
single stray click. Each delete asks for confirmation first, and the row only
disappears once the server has actually removed the run.
"""

from __future__ import annotations

from playwright.sync_api import expect

DESCRIBE = {
    "workflow": "workflow_optimization", "inputSource": "sample", "mode": "measure",
    "inputs": {"workflowDescription": "An assistant sends full context for every request.",
               "sampleId": "customer_assistance"},
    "requirements": {"qualityRequirements": ["same_answer_quality"],
                     "optimizationGoal": "cost_per_accepted_outcome", "maxModelSpendUsd": 0.05,
                     "allowAdvancedEscalation": False},
}


def seed_run(page, api_url) -> str:
    response = page.request.post(f"{api_url}/api/runs", data=DESCRIBE)
    assert response.status == 200, response.text()
    return response.json()["runId"]


def open_history(page):
    page.get_by_role("button", name="History", exact=True).click()
    drawer = page.get_by_role("dialog", name="Run history", exact=True)
    expect(drawer).to_be_visible()
    return drawer


def test_deleting_one_run_asks_first_and_removes_only_that_run(page, browser_servers):
    kept = seed_run(page, browser_servers["api"])
    removed = seed_run(page, browser_servers["api"])
    page.reload(wait_until="networkidle")

    drawer = open_history(page)
    kept_row = drawer.locator("li", has_text=kept)
    removed_row = drawer.locator("li", has_text=removed)
    expect(kept_row).to_have_count(1)
    expect(removed_row).to_have_count(1)

    # Nothing is deleted until the confirmation is answered.
    drawer.get_by_role("button", name=f"Delete run {removed}", exact=True).click()
    keep = drawer.get_by_role("button", name=f"Keep run {removed}", exact=True)
    expect(keep).to_be_visible()
    expect(removed_row).to_have_count(1)

    keep.click()
    expect(drawer.get_by_role("button", name=f"Delete run {removed}", exact=True)).to_be_visible()

    drawer.get_by_role("button", name=f"Delete run {removed}", exact=True).click()
    with page.expect_response(
        lambda response: response.url.endswith(f"/api/runs/{removed}")
        and response.request.method == "DELETE"
    ) as deleted:
        drawer.get_by_role("button", name=f"Confirm delete run {removed}", exact=True).click()
    assert deleted.value.status == 200, deleted.value.text()

    expect(removed_row).to_have_count(0)
    expect(kept_row).to_have_count(1)

    # The server, not just the browser, no longer holds the run.
    history = page.request.get(f"{browser_servers['api']}/api/runs").json()["runs"]
    identifiers = [run["run_id"] for run in history]
    assert removed not in identifiers
    assert kept in identifiers


def test_clear_all_empties_the_history(page, browser_servers):
    seed_run(page, browser_servers["api"])
    seed_run(page, browser_servers["api"])
    page.reload(wait_until="networkidle")

    drawer = open_history(page)
    drawer.get_by_role("button", name="Clear all", exact=True).click()
    expect(drawer.get_by_text("Delete all", exact=False).first).to_be_visible()

    with page.expect_response(
        lambda response: response.url.endswith("/api/runs") and response.request.method == "DELETE"
    ) as cleared:
        drawer.get_by_role("button", name="Delete all", exact=True).click()
    assert cleared.value.status == 200, cleared.value.text()

    expect(drawer.get_by_text("No completed runs yet.", exact=True)).to_be_visible()
    # With nothing left to delete, the clear control is not offered.
    expect(drawer.get_by_role("button", name="Clear all", exact=True)).to_have_count(0)

    assert page.request.get(f"{browser_servers['api']}/api/runs").json()["runs"] == []
