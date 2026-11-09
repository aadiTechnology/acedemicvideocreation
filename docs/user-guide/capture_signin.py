"""Capture the Aadi sign-in page (the demo Identity, fictional data). Nothing is typed into the form."""
from pathlib import Path

from playwright.sync_api import sync_playwright

IMG = Path(__file__).resolve().parent / "img"
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge", headless=True)
    page = browser.new_page(viewport={"width": 1440, "height": 810})
    page.goto("https://id-demo.aadiprojecttracker.aaditechnology.com/login", wait_until="networkidle")
    page.screenshot(path=str(IMG / "30-signin.png"))
    print(page.title())
    browser.close()
