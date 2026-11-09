"""Capture the user-guide screens by driving the real app with Playwright (Edge).

Prerequisites: the API (dev auth) on :8100 and the web app on :5174, both on a FRESH database.
Run from the repository root with a Python that has playwright:   python docs/user-guide/capture_guide.py
Screens are written to docs/user-guide/img/. Each click target is outlined and numbered so a viewer can follow along.
"""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import Page, sync_playwright

ROOT = Path(__file__).resolve().parent
IMG = ROOT / "img"
SAMPLE = ROOT / "sample"
URL = "http://localhost:5174/"
step_no = {"n": 0}


def mark(page: Page, target, number: int | None = None) -> None:
    """Scroll the target to the middle of the screen and outline it with a numbered badge."""
    el = target.first
    el.evaluate("e => e.scrollIntoView({block: 'center', inline: 'nearest'})")
    el.evaluate(
        """(e, n) => {
            e.dataset.guideOutline = e.style.outline || '';
            e.style.outline = '4px solid #ff5a1f'; e.style.outlineOffset = '3px';
            if (n) {
              const b = document.createElement('div'); b.className = 'guide-badge'; b.textContent = n;
              const r = e.getBoundingClientRect();
              b.style.cssText = `position:fixed;z-index:99999;left:${Math.max(4, r.left - 14)}px;top:${Math.max(4, r.top - 16)}px;`
                + 'width:30px;height:30px;border-radius:15px;background:#ff5a1f;color:#fff;font:700 16px system-ui;'
                + 'display:flex;align-items:center;justify-content:center;box-shadow:0 2px 6px rgba(0,0,0,.4)';
              document.body.appendChild(b);
            }
        }""", number)


def unmark(page: Page) -> None:
    page.evaluate("""() => {
        document.querySelectorAll('.guide-badge').forEach(b => b.remove());
        document.querySelectorAll('[data-guide-outline]').forEach(e => { e.style.outline = e.dataset.guideOutline; delete e.dataset.guideOutline; });
    }""")


def shot(page: Page, name: str, *targets) -> None:
    """Outline the targets (numbered in order), take the viewport screenshot, clear the outlines."""
    for i, t in enumerate(targets, 1):
        mark(page, t, i if len(targets) > 1 else None)
    page.wait_for_timeout(250)
    page.screenshot(path=str(IMG / f"{name}.png"))
    unmark(page)
    print("captured", name)


def main() -> None:
    IMG.mkdir(exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 810})
        page.goto(URL)
        page.wait_for_selector("text=No lessons yet")

        # ---- 1. Set up the academic structure ---------------------------------------------------------------
        shot(page, "01-home", page.get_by_role("button", name="Structure"))
        page.get_by_role("button", name="Structure").click()
        classes = page.locator(".card", has=page.get_by_role("heading", name="Classes"))
        shot(page, "02-structure", classes.get_by_placeholder("Class 7"), classes.get_by_role("button", name="Add"))
        classes.get_by_placeholder("Class 7").fill("Class 7")
        classes.get_by_role("button", name="Add").click()
        page.wait_for_selector("li:has-text('Class 7')")
        shot(page, "03-class-added", classes.locator("li").first)

        tree = page.locator(".card", has=page.get_by_role("heading", name="Subjects, chapters, topics"))
        tree.locator("select").nth(0).select_option(label="Class 7")
        tree.get_by_placeholder("Science").fill("Science")
        shot(page, "04-subject", tree.locator("select").nth(0), tree.get_by_placeholder("Science"), tree.get_by_role("button", name="Add subject"))
        tree.get_by_role("button", name="Add subject").click()
        page.wait_for_timeout(400)
        tree.locator("select").nth(1).select_option(label="Science")
        tree.locator("input").nth(1).fill("1")
        tree.get_by_placeholder("Nutrition in Plants").fill("Nutrition in Plants")
        shot(page, "05-chapter", tree.locator("select").nth(1), tree.locator("input").nth(1), tree.get_by_placeholder("Nutrition in Plants"), tree.get_by_role("button", name="Add chapter"))
        tree.get_by_role("button", name="Add chapter").click()
        page.wait_for_timeout(400)
        tree.locator("select").nth(2).select_option(index=1)
        tree.get_by_placeholder("Photosynthesis").fill("Photosynthesis")
        shot(page, "06-topic", tree.locator("select").nth(2), tree.get_by_placeholder("Photosynthesis"), tree.get_by_role("button", name="Add topic"))
        tree.get_by_role("button", name="Add topic").click()
        page.wait_for_timeout(400)

        # ---- 2. Create a lesson with language versions ------------------------------------------------------
        page.get_by_role("button", name="Lessons").click()
        form = page.locator(".card", has=page.get_by_role("heading", name="New lesson"))
        form.locator("select").nth(0).select_option(label="Class 7")
        form.locator("select").nth(1).select_option(label="Science")
        form.locator("select").nth(2).select_option(index=1)
        form.locator("select").nth(3).select_option(label="Photosynthesis")
        shot(page, "07-lesson-where", *[form.locator("select").nth(i) for i in range(4)])
        form.locator("input[type=text], input:not([type])").first.fill("How plants make food")
        form.locator("input[type=number]").fill("5")
        form.get_by_label("Hindi").check()
        form.get_by_label("Marathi").check()
        form.locator("textarea").nth(1).fill("Explain photosynthesis\nName the raw materials and the products")
        shot(page, "08-lesson-details", form.locator("input[type=text], input:not([type])").first, form.locator("input[type=number]"),
             form.locator("fieldset"), form.get_by_role("button", name="Create lesson"))
        form.get_by_role("button", name="Create lesson").click()
        page.wait_for_selector("tr.pick")
        shot(page, "09-lesson-created", page.locator("tr.pick").first)
        page.locator("tr.pick").first.click()
        shot(page, "10-lesson-open", page.get_by_text("Open a language version").locator(".."))

        # ---- 3. Prompt, import, fix errors ------------------------------------------------------------------
        page.get_by_role("button", name="English (draft)").click()
        page.wait_for_selector("text=1. Get the content")
        shot(page, "11-version-panel", page.get_by_role("button", name="Show ChatGPT prompt"))
        page.get_by_role("button", name="Show ChatGPT prompt").click()
        page.wait_for_selector("textarea[readonly]")
        shot(page, "12-prompt", page.locator("textarea[readonly]"))
        page.get_by_role("button", name="Hide prompt").click()
        chooser = page.locator("input[type=file]")
        chooser.set_input_files(str(SAMPLE / "lesson_with_errors.csv"))
        page.get_by_role("button", name="Check only").click()
        page.wait_for_selector("[role=alert] li")
        shot(page, "13-import-errors", page.locator("ul[role=alert]"))
        chooser.set_input_files([str(SAMPLE / "lesson.csv"), str(SAMPLE / "lesson_plan.json")])
        shot(page, "14-choose-files", chooser, page.get_by_role("button", name="Check only"), page.get_by_role("button", name="Import", exact=True))
        page.get_by_role("button", name="Check only").click()
        page.wait_for_selector("text=Looks good")
        shot(page, "15-check-ok", page.get_by_text("Looks good"))
        page.get_by_role("button", name="Import", exact=True).click()
        page.wait_for_selector("text=3. Review the content")
        shot(page, "16-imported", page.get_by_role("heading", name="3. Review the content"))

        # ---- 4. Review and approve --------------------------------------------------------------------------
        send = page.get_by_role("button", name="Send for review")
        shot(page, "17-send-review", send)
        send.click()
        page.wait_for_selector("button:has-text('Approve')")
        note = page.get_by_label("Note (required for changes or rejection)")
        note.fill("Content checked against the textbook.")
        shot(page, "18-decision", note, page.get_by_role("button", name="Approve"), page.get_by_role("button", name="Request changes"))
        page.get_by_role("button", name="Approve").click()
        page.wait_for_selector("text=History")
        page.evaluate("window.scrollTo(0, 0)")
        shot(page, "19-approved", page.locator(".chip.approved").first)
        shot(page, "20-history", page.get_by_role("heading", name="History"))
        page.evaluate("window.scrollTo(0, 0)")
        shot(page, "21-all-languages", page.locator("tr.pick").first)
        browser.close()


if __name__ == "__main__":
    main()
