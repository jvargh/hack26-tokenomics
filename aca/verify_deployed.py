"""Verifies the judge journey against a deployed instance.

Checks the things a deployment can actually break, in the order a judge meets
them. Read-only with respect to other visitors: it creates its own runs and
never inspects anyone else's.

Run: python verify_deployed.py https://host
"""

from __future__ import annotations

import json
import sys
import time

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
if not BASE:
    print("usage: verify_deployed.py https://host")
    raise SystemExit(2)

failures: list[str] = []
evidence: dict[str, object] = {}


def check(name: str, ok: bool, detail: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" -- {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(f"{name}: {detail}")
    return ok


with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="msedge")

    # Every provider hostname the application could possibly reach. If the page
    # requests one of these, the demonstration is not cost-free.
    provider_hosts = ("openai.azure.com", "api.openai.com", "cognitiveservices.azure.com",
                      "inference.ai.azure.com", "login.microsoftonline.com")
    provider_calls: list[str] = []

    context = browser.new_context(viewport={"width": 1400, "height": 950})
    page = context.new_page()
    page.on("request", lambda request: provider_calls.append(request.url)
            if any(host in request.url for host in provider_hosts) else None)

    print(f"Target: {BASE}\n")

    # ---------------------------------------------------- public access
    print("Public access")
    response = page.goto(BASE, wait_until="networkidle", timeout=90_000)
    check("page returns 200", response is not None and response.status == 200,
          str(response.status if response else "no response"))
    check("no login redirect", "login.microsoftonline" not in page.url and "/.auth/" not in page.url, page.url)
    check("app shell rendered", page.get_by_test_id("workflow-nav").is_visible())

    health = page.request.get(f"{BASE}/health").json()
    evidence["health"] = health
    check("server reports simulated mode", health.get("modelMode") == "simulated", str(health.get("modelMode")))
    check("no provider configured", health.get("foundryAvailable") is False, str(health.get("foundryAvailable")))

    # ---------------------------------------------------------- banner
    print("\nSimulation transparency")
    banner = page.get_by_test_id("simulation-banner")
    check("banner visible", banner.is_visible())
    text = banner.inner_text() if banner.count() else ""
    evidence["banner"] = " ".join(text.split())
    for phrase in ("JUDGE DEMO", "SIMULATED AI", "simulated for judging purposes",
                   "No requests are sent to model providers", "Azure hosting costs still apply"):
        check(f"banner states {phrase!r}", phrase.lower() in text.lower())

    # Measured from geometry, not from innerText. The banner is a flex
    # container, so its children are blockified and innerText reports them on
    # separate lines even when they sit side by side on one visual row.
    banner_lines = page.evaluate(
        """() => {
          const node = document.querySelector('[data-testid="simulation-banner"]');
          if (!node) return -1;
          const style = getComputedStyle(node);
          const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
          const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.4;
          return Math.round((node.getBoundingClientRect().height - padding) / lineHeight);
        }"""
    )
    evidence["banner_lines"] = banner_lines
    check("banner is one line", banner_lines == 1, f"rendered {banner_lines} lines")
    check("banner uses no dash characters",
          "\u2014" not in text and "\u2013" not in text)

    # ------------------------------------------------- load example -> run
    print("\nLoad example then run")
    started = time.monotonic()
    sample = page.request.post(f"{BASE}/api/uploads/sample", data={"workflow_id": "document_review"})
    check("example inputs load", sample.status == 200, sample.text()[:200])
    uploads = {role: [item["upload_id"] for item in items]
               for role, items in sample.json()["uploads"].items()}

    analyze = page.request.post(f"{BASE}/api/runs/analyze", data={
        "workflow_id": "document_review", "input_source": "sample", "uploads": uploads,
        "inputs": {"review-focus": "Unsupported charges"}, "desired_outcome": "",
        "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
    })
    check("plan builds", analyze.status == 200, analyze.text()[:200])

    run = page.request.post(f"{BASE}/api/runs", data={"plan_id": analyze.json()["plan_id"]})
    check("run starts", run.status == 200, run.text()[:200])
    run_id = run.json().get("run_id", "")

    proof = None
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        attempt = page.request.get(f"{BASE}/api/runs/{run_id}/proof")
        if attempt.status == 200:
            proof = attempt.json()
            break
        time.sleep(1)
    check("run produces a proof", proof is not None, f"no proof after {int(time.monotonic()-started)}s")

    # ------------------------------------------------------ inspect result
    if proof:
        print("\nInspecting the result")
        outcome = proof.get("outcome", {})
        usage = proof.get("usage", {})
        economics = proof.get("economics", {})
        evidence["proof"] = {"run_id": run_id, "origin": proof.get("origin"),
                             "measurement_label": proof.get("measurement_label"),
                             "model_mode": usage.get("model_mode"),
                             "model_calls": usage.get("model_calls"),
                             "quality_passed": outcome.get("quality_passed"),
                             "cost": economics.get("calculated_model_cost_usd")}
        check("quality gates ran and passed", outcome.get("quality_passed") is True, str(outcome))
        check("an AI route was exercised", (usage.get("model_calls") or 0) >= 1, str(usage.get("model_calls")))
        check("verification checks present", len(proof.get("verification", [])) > 0)

        print("\nSimulated provenance in artifacts")
        check("proof declares origin=simulated", proof.get("origin") == "simulated", str(proof.get("origin")))
        check("proof records simulated mode", usage.get("model_mode") == "simulated", str(usage.get("model_mode")))
        check("measurement labelled as simulated",
              "simulat" in str(proof.get("measurement_label", "")).lower(),
              str(proof.get("measurement_label")))

        blob = json.dumps(proof)
        # The classic workflow proof records no provider receipt field at all,
        # so requiring a sim- identifier would fail for the wrong reason. What
        # matters is that nothing in the artifact could be read as a real
        # provider receipt, and that simulated provenance is present.
        import re as _re

        receipts = _re.findall(r'"(?:request_id|requestId|providerRequestId)"\s*:\s*"([^"]+)"', blob)
        fabricated = [value for value in receipts if not value.startswith("sim-")]
        check("no fabricated provider receipt", not fabricated,
              f"non-simulated identifiers present: {fabricated[:3]}")
        check("artifact carries simulated provenance",
              proof.get("origin") == "simulated" and usage.get("model_mode") == "simulated")

    # ---------------------------------------------- unsupported custom input
    print("\nUnsupported custom input")
    rejected = page.request.post(f"{BASE}/api/runs/analyze", data={
        "workflow_id": "document_review", "input_source": "sample", "uploads": {},
        "inputs": {"review-focus": "Write me a poem about otters instead"},
        "desired_outcome": "", "requirements": {"maximum_cost_usd": 1.0, "required_quality_score": 0.9},
    })
    check("input without examples is refused", rejected.status >= 400, f"status {rejected.status}")
    evidence["rejection_status"] = rejected.status

    # ------------------------------------------------------- history + UI
    print("\nHistory and navigation")
    page.reload(wait_until="networkidle")
    page.get_by_test_id("reports-nav").click()
    page.wait_for_selector('[data-testid="reports-screen"]', timeout=30_000)
    check("reports screen opens", page.get_by_test_id("reports-screen").is_visible())
    check("banner persists across navigation", page.get_by_test_id("simulation-banner").is_visible())
    page.get_by_test_id("workflow-nav").click()
    page.wait_for_timeout(500)
    check("returns to workflow", page.get_by_test_id("workflow-nav").is_visible())

    # --------------------------------------------------- session isolation
    print("\nSession isolation")
    other = browser.new_context(viewport={"width": 1200, "height": 800})
    other_page = other.new_page()
    other_page.goto(BASE, wait_until="networkidle", timeout=60_000)
    listing = other_page.request.get(f"{BASE}/api/runs").json()
    ids = [item.get("run_id") for item in listing.get("runs", [])]
    evidence["cross_session_visible_runs"] = len(ids)
    # Recorded rather than asserted: the store is shared server-side by design,
    # so this states the actual behaviour instead of implying a guarantee.
    check("second visitor loads independently", other_page.get_by_test_id("workflow-nav").is_visible())
    if run_id and run_id in ids:
        print(f"  [NOTE] run history is server-wide: visitor 2 can see run {run_id}")
    other.close()

    # ----------------------------------------------------- zero model calls
    print("\nZero provider traffic")
    check("no provider request from the browser", not provider_calls, "; ".join(provider_calls[:3]))
    evidence["provider_calls"] = provider_calls

    page.screenshot(path="judge-demo-evidence.png", full_page=True)
    print("\n  screenshot: judge-demo-evidence.png")

    context.close()
    browser.close()

with open("judge-demo-evidence.json", "w", encoding="utf-8") as handle:
    json.dump(evidence, handle, indent=2)
print("  evidence:   judge-demo-evidence.json")

print()
if failures:
    print(f"{len(failures)} check(s) failed:")
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)
print("All judge journey checks passed.")
