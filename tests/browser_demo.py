import asyncio
import json
import os
import subprocess
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
PW_RUNTIME = ROOT / "artifacts" / "pw-runtime"
FFMPEG_LINK = PW_RUNTIME / "ffmpeg-1011" / "ffmpeg-linux"
FFMPEG_LINK.parent.mkdir(parents=True, exist_ok=True)
if not FFMPEG_LINK.exists():
    FFMPEG_LINK.symlink_to("/usr/bin/ffmpeg")
os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(PW_RUNTIME)
from playwright.async_api import async_playwright, expect

OUT = ROOT / "artifacts" / "demo"
OUT.mkdir(parents=True, exist_ok=True)
URL = os.environ.get("P10_BASE_URL", "http://127.0.0.1:19094/")

async def main():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True, executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        context = await browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=1,
                                            record_video_dir=str(OUT / "raw-video"),
                                            record_video_size={"width": 1440, "height": 900})
        page = await context.new_page()
        await page.goto(URL, wait_until="networkidle")
        assert await page.locator("#sample-metric").inner_text() == "4/50 · 8%"
        await page.screenshot(path=str(OUT / "01-current-desktop.png"), full_page=True)
        await asyncio.sleep(0.8)
        await page.locator("#cutoff").select_option("2026-09-30T09:15:00+09:00")
        await expect(page.locator("#sample-metric")).to_have_text("5/50 · 10%")
        assert "QDOC-002" not in await page.locator("body").inner_text()
        assert "09:20 · 정정" not in await page.locator("body").inner_text()
        await page.screenshot(path=str(OUT / "02-early-cutoff.png"), full_page=True)
        await asyncio.sleep(0.8)
        await page.locator("#cutoff").select_option("2026-09-30T10:00:00+09:00")
        await expect(page.locator("#sample-metric")).to_have_text("4/50 · 8%")
        await page.locator("#corrections").evaluate("(element) => element.open = true")
        assert "QDOC-001" in await page.locator("#correction-list").inner_text()
        await page.screenshot(path=str(OUT / "03-correction-history.png"), full_page=True)
        await asyncio.sleep(0.8)
        await page.locator("#timeline .source-button").first.click()
        await page.locator("#source-text").wait_for()
        await expect(page.locator("#source-text")).to_contain_text("PKG-")
        await page.screenshot(path=str(OUT / "04-source-drawer.png"), full_page=True)
        await asyncio.sleep(0.8)
        await page.locator("#close-source").click()
        await page.locator("#principal").select_option("demo-reviewer-a")
        await page.locator("#review-button").click()
        await expect(page.locator("#review-result")).to_contain_text("인계 검토 수락")
        assert "미해결 질문 5건 포함" in await page.locator("#review-result").inner_text()
        await page.screenshot(path=str(OUT / "05-review-receipt.png"), full_page=True)
        await asyncio.sleep(0.8)
        await page.locator("#capture").select_option("QDOC-012")
        await expect(page.locator("#sample-note")).to_contain_text("상충")
        assert await page.locator("#review-button").is_enabled()
        assert await page.locator("#decision").input_value() == "returned"
        assert await page.locator('#decision option[value="accepted_for_handoff"]').evaluate("(option) => option.disabled")
        await page.screenshot(path=str(OUT / "06-conflict-block.png"), full_page=True)
        await asyncio.sleep(0.8)
        await page.locator("#capture").select_option("")
        await expect(page.locator("#sample-metric")).to_have_text("4/50 · 8%")
        delayed = []
        async def slow_source(route):
            delayed.append(1)
            await asyncio.sleep(0.5)
            await route.continue_()
        await page.route("**/api/source/*", slow_source)
        await page.locator("#timeline .source-button").first.click()
        await expect(page.locator("#source-dialog")).to_have_attribute("open", "")
        await page.evaluate("""() => {
          const select = document.querySelector('#cutoff');
          select.value = '2026-09-30T09:15:00+09:00';
          select.dispatchEvent(new Event('change', {bubbles: true}));
        }""")
        await expect(page.locator("#sample-metric")).to_have_text("5/50 · 10%")
        await asyncio.sleep(0.8)
        assert delayed
        assert not await page.locator("#source-dialog").evaluate("(element) => element.open")
        assert "5/50" in await page.locator("#sample-metric").inner_text()
        print("delayed_source_scope_switch=pass")
        await page.locator("#cutoff").select_option("2026-09-30T10:00:00+09:00")
        await expect(page.locator("#sample-metric")).to_have_text("4/50 · 8%")
        reviewed = []
        async def slow_review(route):
            reviewed.append(1)
            await asyncio.sleep(0.5)
            await route.continue_()
        await page.route("**/api/review", slow_review)
        await page.locator("#review-button").click()
        await page.locator("#cutoff").select_option("2026-09-30T09:15:00+09:00")
        await expect(page.locator("#sample-metric")).to_have_text("5/50 · 10%")
        await asyncio.sleep(0.8)
        assert reviewed
        assert "인계 검토 수락" not in await page.locator("#review-result").inner_text()
        print("delayed_review_scope_switch=pass")
        async def failed_scenarios(route):
            await asyncio.sleep(0.4)
            await route.fulfill(status=503, content_type="application/json",
                                body='{"error":"simulated_read_failure"}')
        await page.route("**/api/scenarios?*", failed_scenarios)
        await page.locator("#principal").select_option("demo-no-sites")
        assert await page.locator("#timeline").inner_text() == ""
        assert "5/50" not in await page.locator("#sample-metric").inner_text()
        await expect(page.locator("#sample-metric")).to_have_text("조회 실패")
        assert await page.locator("#timeline").inner_text() == ""
        assert await page.locator("#review-button").is_disabled()
        print("failed_scope_drops_prior_content=pass")
        video = page.video
        await context.close()
        video_path = await video.path()
        final_video = OUT / "workflow.mp4"
        result = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", video_path,
                                 "-c:v", "libx264", "-pix_fmt", "yuv420p",
                                 "-crf", "27", "-movflags", "+faststart", str(final_video)],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        mobile = await browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=1)
        phone = await mobile.new_page()
        await phone.goto(URL, wait_until="networkidle")
        assert await phone.locator("#sample-metric").inner_text() == "4/50 · 8%"
        dims = await phone.evaluate("({scroll: document.documentElement.scrollWidth, view: innerWidth})")
        assert dims["scroll"] <= dims["view"], dims
        await phone.screenshot(path=str(OUT / "07-current-mobile.png"), full_page=True)
        await mobile.close()
        await browser.close()
        print("desktop_mobile_browser=pass", json.dumps(dims))
        print("media", [(x.name, x.stat().st_size) for x in sorted(OUT.glob("*")) if x.is_file()])

asyncio.run(main())
