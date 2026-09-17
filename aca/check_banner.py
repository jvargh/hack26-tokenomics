"""Measures the deployed banner: how many rendered lines, and no dashes.

Checks geometry rather than source text, because "one line" is a property of
what the browser actually draws at a given width, not of the markup.
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = (sys.argv[1] if len(sys.argv) > 1 else "").rstrip("/")
if not BASE:
    print("usage: check_banner.py https://host")
    raise SystemExit(2)

SELECTOR = '[data-testid="simulation-banner"]'

METRICS = """
() => {
  const node = document.querySelector('[data-testid="simulation-banner"]');
  if (!node) return null;
  const style = getComputedStyle(node);
  const rect = node.getBoundingClientRect();
  const padding = parseFloat(style.paddingTop) + parseFloat(style.paddingBottom);
  const lineHeight = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.4;

  // Cluster text rectangles by vertical position rather than counting them.
  // The banner is a flex container, so its children are blockified: each span
  // yields its own rectangle and innerText puts them on separate lines even
  // when they sit side by side on one visual row. Baseline alignment also
  // shifts their tops by a pixel or two. Grouping tops within half a
  // line-height measures what a reader actually sees.
  const range = document.createRange();
  range.selectNodeContents(node);
  const tops = [];
  for (const box of range.getClientRects()) {
    if (box.height <= 0) continue;
    if (!tops.some((top) => Math.abs(top - box.top) < lineHeight * 0.5)) {
      tops.push(box.top);
    }
  }
  return {
    height: rect.height,
    padding: padding,
    lineHeight: lineHeight,
    visualLines: tops.length,
    // Independent cross-check: content box divided by line height.
    linesByHeight: Math.round((rect.height - padding) / lineHeight),
    text: node.innerText.replace(/\\s+/g, ' ').trim()
  };
}
"""

failures = []

with sync_playwright() as playwright:
    browser = playwright.chromium.launch(channel="msedge")
    for width in (1600, 1440, 1280, 1024):
        page = browser.new_page(viewport={"width": width, "height": 900})
        page.goto(BASE, wait_until="networkidle", timeout=90_000)
        page.wait_for_selector(SELECTOR, timeout=30_000)
        data = page.evaluate(METRICS)

        text = data["text"]
        lines = data["visualLines"]
        dashes = [c for c in ("\u2014", "\u2013") if c in text]

        # Both measures must agree that it is one line, so a quirk in either
        # one cannot produce a false pass.
        ok = lines == 1 and data["linesByHeight"] == 1
        status = "PASS" if ok else "FAIL"
        print(f"  [{status}] {width}px: {lines} visual line(s), "
              f"{data['linesByHeight']} by height, {data['height']:.0f}px tall")
        if not ok:
            failures.append(
                f"{width}px rendered {lines} visual / {data['linesByHeight']} by height"
            )
        if dashes:
            print(f"  [FAIL] {width}px: dash character present")
            failures.append(f"{width}px contains {dashes}")

        if width == 1440:
            print(f"\n  text: {text}\n")
            page.screenshot(path="banner-check.png", clip={"x": 0, "y": 0, "width": width, "height": 150})
        page.close()
    browser.close()

print()
if failures:
    for failure in failures:
        print(f"  - {failure}")
    raise SystemExit(1)
print("Banner renders on one line at every checked width, with no dash characters.")
