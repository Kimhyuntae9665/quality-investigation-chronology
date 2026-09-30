"""Real Chrome keyboard regression for the fictional P10 loopback app."""
import asyncio
from playwright.async_api import async_playwright, expect

URL = "http://127.0.0.1:19094/"


async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True, executable_path="/usr/bin/google-chrome",
            args=["--no-sandbox"])
        page = await browser.new_page(viewport={"width": 1280, "height": 800})
        await page.goto(URL, wait_until="networkidle")
        await page.locator("#principal").select_option("demo-reviewer-a")
        source = page.locator("#timeline .source-button").first
        await source.focus()
        await page.keyboard.press("Enter")
        await expect(page.locator("#source-dialog")).to_have_attribute("open", "")
        await page.keyboard.press("Escape")
        await expect(page.locator("#source-dialog")).not_to_have_attribute("open", "")
        await page.wait_for_timeout(50)
        assert await source.evaluate("(element) => document.activeElement === element")
        review = page.locator("#review-button")
        await review.focus()
        await page.keyboard.press("Enter")
        await expect(page.locator("#review-result")).to_contain_text("인계 검토 수락")
        assert await review.evaluate("(element) => document.activeElement === element")
        await browser.close()
        print("source_dialog_escape_focus=pass review_keyboard_focus=pass")


if __name__ == "__main__":
    asyncio.run(main())
