"""Captures the history drawer with its delete controls, for visual review.

Run explicitly: python -m pytest -c pytest-browser.ini tests/browser/capture_history.py
"""

from __future__ import annotations

import os
from pathlib import Path

from playwright.sync_api import expect

from e2e_history_delete import DESCRIBE, open_history


def test_capture_history_drawer(page, browser_servers):
    for _ in range(3):
        response = page.request.post(f"{browser_servers['api']}/api/runs", data=DESCRIBE)
        assert response.status == 200, response.text()
    page.reload(wait_until="networkidle")

    directory = Path(os.getenv("TOKENOS_SCREENSHOT_DIR", "screenshots"))
    directory.mkdir(parents=True, exist_ok=True)

    drawer = open_history(page)
    drawer.screenshot(path=str(directory / "history-delete-dark.png"))

    first = drawer.locator("li").first
    first.get_by_role("button", name="Delete run", exact=False).click()
    expect(first.get_by_role("button", name="Keep run", exact=False)).to_be_visible()
    drawer.screenshot(path=str(directory / "history-delete-confirm.png"))

    first.get_by_role("button", name="Keep run", exact=False).click()
    drawer.get_by_role("button", name="Clear all", exact=True).click()
    drawer.screenshot(path=str(directory / "history-delete-clear-all.png"))
