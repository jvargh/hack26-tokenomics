"""Records the TokenOS demo video with Playwright.

Run:
    python -m pytest -c pytest-browser.ini tests/browser/demo_recording.py -q -s

Output (under TOKENOS_DEMO_DIR, default `_bkp/demo`):
    tokenos-demo.webm    silent screen capture, 1600x900
    demo-timings.json    per-scene start/end seconds for the voice-over
    scene-*.png          a still per scene, for thumbnails or slides

The narration for each scene is in `samples/DEMO-SCRIPT.md`. Scene durations here
are set to match that script when read at a calm pace, so the recording and the
voice-over line up without editing.

Everything recorded is produced by the running application in local mode. No model
tokens are spent and no value is faked for the camera.
"""

from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect

VIEWPORT = {"width": 1600, "height": 900}

# Seconds each scene should occupy. These are derived from the measured narration
# (`python tools/narrate_demo.py --timings-only`) so the picture paces itself to
# the words rather than the other way round. Re-derive them if the script changes.
SCENE_SECONDS = {
    "01-problem": 26,
    "02-real-work": 23,
    "03-seven-phases": 36,
    "04-the-proof": 54,
    "05-proving-it": 37,
    "06-refusing-to-lie": 30,
    "07-close": 24,
}


def demo_dir() -> Path:
    configured = os.getenv("TOKENOS_DEMO_DIR")
    root = Path(configured) if configured else Path(__file__).resolve().parents[4] / "_bkp" / "demo"
    root.mkdir(parents=True, exist_ok=True)
    return root


class Director:
    """Keeps each scene on the clock so narration matches the picture."""

    def __init__(self, page, output: Path):
        self.page = page
        self.output = output
        self.timings: list[dict] = []
        self._origin = time.monotonic()
        self._scene_start = self._origin
        self._name: str | None = None

    def start(self, name: str):
        self.close()
        self._name = name
        self._scene_start = time.monotonic()

    def close(self):
        if self._name is None:
            return
        started = self._scene_start - self._origin
        target = SCENE_SECONDS.get(self._name, 0)
        elapsed = time.monotonic() - self._scene_start
        if elapsed < target:
            self.page.wait_for_timeout(int((target - elapsed) * 1000))
        self.page.screenshot(path=str(self.output / f"scene-{self._name}.png"))
        self.timings.append(
            {
                "scene": self._name,
                "startSeconds": round(started, 2),
                "endSeconds": round(time.monotonic() - self._origin, 2),
            }
        )
        self._name = None

    def beat(self, seconds: float = 1.5):
        """A deliberate pause so a number has time to land."""
        self.page.wait_for_timeout(int(seconds * 1000))

    def highlight(self, locator, seconds: float = 1.6):
        """Scrolls something into view and pauses on it, like a presenter would."""
        try:
            locator.scroll_into_view_if_needed(timeout=4000)
        except Exception:
            return
        self.beat(seconds)


@pytest.fixture
def demo_page(browser, browser_servers):
    output = demo_dir()
    context = browser.new_context(
        viewport=VIEWPORT,
        record_video_dir=str(output),
        record_video_size=VIEWPORT,
    )
    page = context.new_page()
    page.set_default_timeout(30000)
    page.goto(browser_servers["web"], wait_until="networkidle")
    yield page
    video = page.video
    context.close()  # The file is only finalised once the context closes.
    if video:
        final = output / "tokenos-demo.webm"
        if final.exists():
            final.unlink()
        Path(video.path()).rename(final)


def test_record_demo(demo_page, browser_servers):
    page = demo_page
    output = demo_dir()
    director = Director(page, output)

    # ---------------------------------------------------------------- scene 1
    director.start("01-problem")
    expect(page.get_by_role("heading", name="What do you want TokenOS to optimize?")).to_be_visible()
    director.beat(2)
    for title in ("Review documents against rules", "Test a code change",
                  "Process records by a deadline", "Optimize an existing AI workflow"):
        page.get_by_role("button", name=re.compile("^" + re.escape(title))).hover()
        director.beat(1.2)

    # ---------------------------------------------------------------- scene 2
    director.start("02-real-work")
    # The deadline workflow finishes its decision locally, so the proof screen
    # can show a real before/after comparison rather than an incomplete run.
    page.get_by_role("button", name=re.compile("^Process records by a deadline")).click()
    director.beat(1.2)
    page.get_by_role("radio", name=re.compile("^Use sample data")).check()
    director.beat(1)
    page.get_by_role("button", name="Load sample data", exact=True).click()
    director.highlight(page.locator(".phase").first, 3)

    # ---------------------------------------------------------------- scene 3
    director.start("03-seven-phases")
    with page.expect_response(
        lambda response: response.url == browser_servers["api"] + "/api/runs"
        and response.request.method == "POST"
    ) as started:
        page.get_by_role("button", name="Analyze with TokenOS", exact=True).click()
    run_id = started.value.json()["run_id"]
    # The stepper tells the story on its own; let it play.
    stepper = page.get_by_role("navigation", name="Run progress")
    director.highlight(stepper, 2)
    prove = stepper.get_by_role("button", name=re.compile("^Prove"))
    expect(prove).to_be_enabled(timeout=60000)

    # ---------------------------------------------------------------- scene 4
    director.start("04-the-proof")
    prove.click()
    expect(page.locator(".work-avoided")).to_be_visible()
    # The narration promises a before/after comparison and an amber estimate.
    # Fail the recording rather than ship a video the script does not match.
    expect(page.locator(".comparison-before:not(.is-blank)").first).to_be_visible()
    expect(page.locator(".claim-strength.is-estimate")).to_be_visible()
    director.highlight(page.locator(".work-avoided"), 5)
    for index in range(4):
        director.highlight(page.locator(".prove-cards .comparison-card").nth(index), 2.4)
    director.highlight(page.locator(".claim-strength"), 4)

    # ---------------------------------------------------------------- scene 5
    director.start("05-proving-it")
    gate = page.locator("#run-all-ai-comparison")
    director.highlight(gate, 4)
    # Shown, never clicked: this demo does not spend model tokens.
    expect(gate.get_by_role("checkbox")).not_to_be_checked()
    director.beat(3)

    # ---------------------------------------------------------------- scene 6
    director.start("06-refusing-to-lie")
    page.get_by_role("button", name="New run", exact=True).click()
    director.beat(1)
    page.get_by_role("button", name=re.compile("^Test a code change")).click()
    page.get_by_role("radio", name=re.compile("^Use sample data")).check()
    page.get_by_role("button", name="Load sample data", exact=True).click()
    director.beat(1)
    page.get_by_role("button", name="Analyze with TokenOS", exact=True).click()
    failing_prove = page.get_by_role("navigation", name="Run progress").get_by_role(
        "button", name=re.compile("^Prove")
    )
    expect(failing_prove).to_be_enabled(timeout=60000)
    failing_prove.click()
    # The narration claims every cost comparison disappears on a failed outcome.
    expect(page.locator(".claim-strength.is-none")).to_be_visible()
    expect(page.locator(".comparison-before:not(.is-blank)")).to_have_count(0)
    director.highlight(page.locator(".claim-strength"), 5)

    # ---------------------------------------------------------------- scene 7
    director.start("07-close")
    page.get_by_role("button", name="New run", exact=True).click()
    director.beat(1)
    page.get_by_role("button", name=re.compile("^Optimize an existing AI workflow")).click()
    expect(page.get_by_role("heading", name="Optimize AI Prompt or Workflow")).to_be_visible()
    director.highlight(page.get_by_role("radiogroup", name="What do you want to improve?"), 4)
    director.close()

    (output / "demo-timings.json").write_text(
        json.dumps(
            {
                "video": "tokenos-demo.webm",
                "viewport": VIEWPORT,
                "script": "samples/DEMO-SCRIPT.md",
                "note": "Recorded in local mode. No model tokens were spent.",
                "scenes": director.timings,
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    total = director.timings[-1]["endSeconds"]
    print(f"\nRecorded {len(director.timings)} scenes in {total:.0f}s")
    for scene in director.timings:
        print(f"   {scene['scene']}: {scene['startSeconds']:.1f}s to {scene['endSeconds']:.1f}s")
    print(f"Output: {output}")
