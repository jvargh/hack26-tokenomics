"""Post-deploy smoke test against the live Container App.

Deliberately read-only: it does not start a workflow, because the deployed app
runs in `foundry` mode where every run spends real tokens on the owner's
subscription. It checks that the shipped bundle renders, navigates and lays out
correctly, which is what the deployment itself can break.

Run: python tests/browser/smoke_deployed.py
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "https://tokenos-hack26.yellowwater-54592620.eastus.azurecontainerapps.io"

failures: list[str] = []


def check(name: str, condition: bool, detail: str = "") -> None:
    status = "PASS" if condition else "FAIL"
    print(f"  [{status}] {name}" + (f" -- {detail}" if detail and not condition else ""))
    if not condition:
        failures.append(f"{name}: {detail}")


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 1280, "height": 900})

    console_errors: list[str] = []

    def record_console(message) -> None:
        """The browser requests /favicon.ico unprompted and no favicon has ever
        shipped, so that 404 is a cosmetic default rather than an application
        failure. Filtering it keeps this check meaningful instead of permanently
        red."""
        if message.type != "error":
            return
        source = (message.location or {}).get("url", "")
        if "favicon" in source.lower() or "favicon" in message.text.lower():
            return
        console_errors.append(f"{message.text} [{source}]")

    page.on("console", record_console)
    page.on("pageerror", lambda error: console_errors.append(str(error)))

    failed_requests: list[str] = []
    page.on(
        "response",
        lambda response: failed_requests.append(f"{response.status} {response.url}")
        if response.status >= 400 and "favicon" not in response.url
        else None,
    )

    print("Workflow screen")
    page.goto(BASE, wait_until="networkidle", timeout=60_000)
    check("app shell renders", page.get_by_test_id("workflow-nav").is_visible())
    check("reports nav present", page.get_by_test_id("reports-nav").is_visible())

    print("Reports screen")
    page.get_by_test_id("reports-nav").click()
    page.wait_for_selector('[data-testid="reports-screen"]', timeout=30_000)
    body = page.locator("body").inner_text()

    check("reports screen renders", page.get_by_test_id("reports-screen").is_visible())
    check(
        "no development fixture in production",
        "development reporting fixture" not in body,
        "production build fell back to the bundled dev fixture",
    )

    empty = page.get_by_test_id("reports-empty").count() > 0
    print(f"  (state: {'empty - no runs recorded yet' if empty else 'populated'})")

    if not empty:
        overflow = page.evaluate(
            """() => {
              const problems = [];
              document.querySelectorAll('.reports .metric-number').forEach((node) => {
                const holder = node.closest('.kpi-card, td, .panel');
                if (!holder) return;
                const v = node.getBoundingClientRect();
                const b = holder.getBoundingClientRect();
                const s = getComputedStyle(holder);
                const right = b.right - (parseFloat(s.paddingRight) || 0);
                if (v.right > right + 1) problems.push(node.textContent.trim());
              });
              return problems;
            }"""
        )
        check("no figure overflows its card", not overflow, str(overflow))

    sideways = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    check("page does not scroll sideways", sideways <= 1, f"{sideways}px")

    print("Narrow viewport")
    page.set_viewport_size({"width": 820, "height": 1000})
    page.wait_for_timeout(400)
    sideways_narrow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    check("no sideways scroll at 820px", sideways_narrow <= 1, f"{sideways_narrow}px")

    print("Navigation back")
    page.set_viewport_size({"width": 1280, "height": 900})
    page.get_by_test_id("workflow-nav").click()
    page.wait_for_timeout(400)
    check("returns to workflow", page.get_by_test_id("workflow-nav").is_visible())

    check("no console errors", not console_errors, "; ".join(console_errors[:3]))
    check("no failed requests", not failed_requests, "; ".join(failed_requests[:3]))

    browser.close()

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for failure in failures:
        print(f"  - {failure}")
    sys.exit(1)
print("All deployment smoke checks passed.")
