"""Captures the redesigned Prove screen from a real local run (no model spend).

Run:  python -m pytest -c pytest-browser.ini tests/browser/capture_prove.py -q
with TOKENOS_SCREENSHOT_DIR set to an output directory.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from playwright.sync_api import expect

from e2e_prove_comparison import complete_run, incomplete_run
from e2e_handoff_sweep import CODE_CHANGE, run_sample_workflow


def _shot(page, name):
    directory = os.getenv("TOKENOS_SCREENSHOT_DIR")
    if not directory:
        pytest.skip("Set TOKENOS_SCREENSHOT_DIR to capture screenshots.")
    destination = Path(directory)
    destination.mkdir(parents=True, exist_ok=True)
    hero = page.locator(".phase")
    hero.screenshot(path=str(destination / f"{name}.png"))


def test_capture_estimate_state(page, browser_servers):
    complete_run(page, browser_servers)
    page.locator(".work-avoided").scroll_into_view_if_needed()
    _shot(page, "prove-estimate")


def test_capture_incomplete_state(page, browser_servers):
    incomplete_run(page, browser_servers)
    page.locator(".work-avoided").scroll_into_view_if_needed()
    _shot(page, "prove-incomplete")


def test_capture_failed_state(page, browser_servers):
    """The code-change sample fails a real test, exercising the no-claim state."""
    run_sample_workflow(page, browser_servers, CODE_CHANGE)
    page.locator(".claim-strength").scroll_into_view_if_needed()
    _shot(page, "prove-failed")
