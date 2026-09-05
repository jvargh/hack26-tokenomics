"""Visual-regression checks for the Step 1 mode switch, dynamic fields and card wrapping.

Run explicitly: python -m pytest -c pytest-browser.ini -v

These assert measured layout geometry from the real rendered page rather than
comparing committed pixel baselines, so they stay meaningful across machines,
fonts and DPI while still catching overflow, clipping and broken wrapping.
"""

from __future__ import annotations

import re

import pytest
from playwright.sync_api import expect

from e2e_optimization import MODE_ANALYZE, MODE_MEASURE, MODE_PROMPT, TITLE, choose_mode, screenshot

WIDE = {"width": 1440, "height": 1100}
LAPTOP = {"width": 1024, "height": 900}
NARROW = {"width": 720, "height": 1000}
MOBILE = {"width": 390, "height": 900}

MODE_TITLES = (MODE_ANALYZE, MODE_PROMPT, MODE_MEASURE)


def open_section(page):
    page.get_by_role("button", name=re.compile("^" + TITLE)).click()
    expect(page.get_by_role("heading", name="Optimize AI Prompt or Workflow", exact=True)).to_be_visible()


def mode_boxes(page):
    boxes = []
    for title in MODE_TITLES:
        locator = page.get_by_role("radio", name=re.compile("^" + re.escape(title)))
        handle = locator.element_handle()
        box = handle.evaluate(
            """(element) => {
                const card = element.closest('label, .optimization-mode, li, div');
                const rect = (card ?? element).getBoundingClientRect();
                return { top: rect.top, left: rect.left, width: rect.width, height: rect.height };
            }"""
        )
        boxes.append(box)
    return boxes


def page_overflow(page):
    return page.evaluate(
        """() => ({
            scrollWidth: document.documentElement.scrollWidth,
            clientWidth: document.documentElement.clientWidth
        })"""
    )


@pytest.mark.parametrize("viewport", [WIDE, LAPTOP, NARROW, MOBILE],
                         ids=["wide", "laptop", "narrow", "mobile"])
def test_no_horizontal_overflow_at_any_supported_width(page, viewport):
    page.set_viewport_size(viewport)
    open_section(page)
    metrics = page_overflow(page)
    assert metrics["scrollWidth"] <= metrics["clientWidth"] + 1, (
        f"Horizontal overflow at {viewport}: {metrics}"
    )


def test_mode_cards_share_a_row_when_wide_and_wrap_when_narrow(page):
    page.set_viewport_size(WIDE)
    open_section(page)
    tops = {round(box["top"]) for box in mode_boxes(page)}
    assert len(tops) == 1, f"All three mode cards should share one row when wide, got tops {tops}"

    page.set_viewport_size(MOBILE)
    open_section(page)
    wrapped = {round(box["top"]) for box in mode_boxes(page)}
    assert len(wrapped) > 1, "Mode cards must wrap onto multiple rows on a narrow viewport."


def test_mode_cards_do_not_clip_their_text(page):
    for viewport in (WIDE, LAPTOP, NARROW, MOBILE):
        page.set_viewport_size(viewport)
        open_section(page)
        for title in MODE_TITLES:
            handle = page.get_by_role(
                "radio", name=re.compile("^" + re.escape(title))
            ).element_handle()
            clipped = handle.evaluate(
                """(element) => {
                    const card = element.closest('label, .optimization-mode, li, div');
                    const target = card ?? element;
                    return {
                        overflowX: target.scrollWidth - target.clientWidth,
                        overflowY: target.scrollHeight - target.clientHeight
                    };
                }"""
            )
            assert clipped["overflowX"] <= 1, f"{title} clips horizontally at {viewport}: {clipped}"
            assert clipped["overflowY"] <= 1, f"{title} clips vertically at {viewport}: {clipped}"


def test_mode_cards_stay_equal_height_in_a_row(page):
    page.set_viewport_size(WIDE)
    open_section(page)
    heights = [round(box["height"]) for box in mode_boxes(page)]
    assert max(heights) - min(heights) <= 2, f"Mode cards should align in height, got {heights}"


def test_mode_switch_swaps_the_dynamic_work_area(page):
    page.set_viewport_size(WIDE)
    open_section(page)

    choose_mode(page, MODE_PROMPT)
    expect(page.get_by_role("heading", name="Provide the prompt", exact=True)).to_be_visible()
    expect(page.get_by_role("button", name=re.compile("^Upload workflow data"))).to_have_count(0)
    screenshot(page, "v01-mode-prompt")

    choose_mode(page, MODE_MEASURE)
    expect(page.get_by_role("heading", name="Provide an existing AI workflow", exact=True)).to_be_visible()
    expect(page.get_by_label(re.compile("^User prompt"))).to_have_count(0)
    screenshot(page, "v02-mode-measure")

    choose_mode(page, MODE_ANALYZE)
    expect(page.get_by_label(re.compile("^User prompt"))).to_have_count(0)
    screenshot(page, "v03-mode-analyze")

    # Switching back restores the prompt work area rather than leaving a blank panel.
    choose_mode(page, MODE_PROMPT)
    expect(page.get_by_role("heading", name="Provide the prompt", exact=True)).to_be_visible()


def test_conditional_prompt_fields_appear_and_disappear(page):
    page.set_viewport_size(WIDE)
    open_section(page)
    choose_mode(page, MODE_PROMPT)
    page.get_by_role("button", name=re.compile("^Paste a prompt")).click()

    expected = page.get_by_label(re.compile("^Expected result"))
    expect(expected).to_have_count(0)
    page.get_by_role("checkbox", name="Same decision or answer quality", exact=True).check()
    expect(page.get_by_label(re.compile("^Expected result"))).to_be_visible()
    page.get_by_role("checkbox", name="Same decision or answer quality", exact=True).uncheck()
    expect(page.get_by_label(re.compile("^Expected result"))).to_have_count(0)

    latency = page.get_by_label(re.compile("^Required latency target"))
    expect(latency).to_have_count(0)
    page.get_by_role("checkbox", name="Response meets a latency target", exact=True).check()
    expect(page.get_by_label(re.compile("^Required latency target"))).to_be_visible()


def test_long_prompt_text_does_not_break_the_layout(page):
    page.set_viewport_size(LAPTOP)
    open_section(page)
    choose_mode(page, MODE_PROMPT)
    page.get_by_role("button", name=re.compile("^Paste a prompt")).click()
    page.get_by_label(re.compile("^User prompt")).fill(
        "Summarise " + ("extraordinarily-long-unbroken-token-" * 40) + " for the customer."
    )
    metrics = page_overflow(page)
    assert metrics["scrollWidth"] <= metrics["clientWidth"] + 1, (
        f"A long unbroken prompt must not create horizontal overflow: {metrics}"
    )
