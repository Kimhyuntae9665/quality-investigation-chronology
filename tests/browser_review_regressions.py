"""Actual Chrome regression for P10 review gating, history, conflict sources and mobile layout."""
import asyncio
import json
import socket
import subprocess
import time
from pathlib import Path
from playwright.async_api import async_playwright, expect

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "ui-review"
PORT = 19096
URL = "http://127.0.0.1:" + str(PORT) + "/"


def start_server():
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", PORT)) == 0:
            raise RuntimeError("browser_test_port_in_use")
    process = subprocess.Popen(
        ["python3", "-m", "quality_queue.server", "--port", str(PORT)],
        cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    for _ in range(60):
        if process.poll() is not None:
            raise RuntimeError("server_exited:" + process.stderr.read().decode()[:400])
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", PORT)) == 0:
                return process
        time.sleep(0.05)
    process.terminate()
    raise RuntimeError("server_start_timeout")


async def main():
    server = start_server()
    OUT.mkdir(parents=True, exist_ok=True)
    try:
        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=True, executable_path="/usr/bin/google-chrome",
                args=["--no-sandbox"])
            page = await browser.new_page(viewport={"width": 1440, "height": 900},
                                          accept_downloads=True)
            await page.goto(URL, wait_until="networkidle")
            await expect(page.locator("#sample-metric")).to_have_text("4/50 · 8%")
            await expect(page.locator("#review-button")).to_be_disabled()
            await page.locator("#principal").select_option("demo-reviewer-a")
            await expect(page.locator("#review-button")).to_be_enabled()
            await page.locator("#review-button").click()
            await expect(page.locator("#review-result")).to_contain_text("인계 검토 수락")
            await expect(page.locator("#review-history li")).to_have_count(1)
            await page.screenshot(path=str(OUT / "01-reviewer-history-desktop.png"), full_page=True)
            await page.reload(wait_until="networkidle")
            await expect(page.locator("#review-history li")).to_have_count(1)
            async with page.expect_download() as download_info:
                await page.locator(".export-button").first.click()
            download = await download_info.value
            export = json.loads(Path(await download.path()).read_text())
            assert export["receipt"]["decision"] == "accepted_for_handoff"
            assert export["packet"]["typed"]["sample"]["rate_percent"] == 8
            await page.locator("#review-note").fill("revised fictional review")
            await page.locator("#review-button").click()
            await expect(page.locator("#review-history li")).to_have_count(2)
            await expect(page.locator("#review-history li").first).to_contain_text("revised fictional review")
            await page.locator("#cutoff").select_option("2026-09-30T09:15:00+09:00")
            await expect(page.locator("#sample-metric")).to_have_text("5/50 · 10%")
            await expect(page.locator("#review-history li")).to_have_count(2)
            await expect(page.locator("#review-history li").first).to_contain_text("다른 조회 맥락")
            assert await page.locator(".export-button").first.is_disabled()
            await page.locator("#cutoff").select_option("2026-09-30T10:00:00+09:00")
            await expect(page.locator("#sample-metric")).to_have_text("4/50 · 8%")
            await page.locator("#capture").select_option("QDOC-012")
            await expect(page.locator("#decision")).to_have_value("returned")
            assert await page.locator('#decision option[value="accepted_for_handoff"]').evaluate("(option) => option.disabled")
            await expect(page.locator("#review-button")).to_be_enabled()
            await expect(page.locator("#conflict-box .conflict-source")).to_have_count(3)
            for sid in ("QDOC-001", "QDOC-002", "QDOC-012"):
                await page.locator("#conflict-box .conflict-source").filter(has_text=sid).get_by_role("button").click()
                await expect(page.locator("#source-meta")).to_contain_text("conflicted")
                await expect(page.locator("#source-title")).to_contain_text(sid)
                await page.locator("#close-source").click()
            precedent = page.locator(".compare-card").filter(has_text="D-020")
            await expect(precedent).to_contain_text("현재 사건의 식별자 미확인")
            assert "확인된 차이: P-100" not in await precedent.inner_text()
            await page.screenshot(path=str(OUT / "02-conflict-sources-desktop.png"), full_page=True)
            await page.locator("#review-button").click()
            await expect(page.locator("#review-result")).to_contain_text("보완 반환")
            await expect(page.locator("#review-history li")).to_have_count(3)
            async def failed_post(route):
                await route.fulfill(status=503, content_type="application/json",
                                    body='{"error":"simulated_transport_result_unknown"}')
            await page.route("**/api/review", failed_post)
            await page.locator("#review-button").click()
            await expect(page.locator("#review-result")).to_contain_text("아래 검토 이력")
            await expect(page.locator("#review-history li")).to_have_count(3)
            await page.unroute("**/api/review", failed_post)
            # A slow review for an old cutoff must release the pending guard
            # after navigation, while its old receipt stays out of the new view.
            await page.locator("#cutoff").select_option("2026-09-30T09:15:00+09:00")
            await expect(page.locator("#review-button")).to_be_enabled()
            async def delayed_review(route):
                await asyncio.sleep(0.4)
                await route.continue_()
            await page.route("**/api/review", delayed_review)
            await page.locator("#review-button").click()
            await page.locator("#cutoff").select_option("2026-09-30T10:00:00+09:00")
            await expect(page.locator("#sample-metric")).to_have_text("4/50 · 8%")
            await page.wait_for_timeout(650)
            await expect(page.locator("#review-button")).to_be_enabled()
            assert "인계 검토 수락" not in await page.locator("#review-result").inner_text()
            await page.unroute("**/api/review", delayed_review)
            await page.locator("#capture").select_option("QDOC-012")
            async def delayed_source(route):
                await asyncio.sleep(0.4)
                await route.continue_()
            await page.route("**/api/source/*", delayed_source)
            await page.locator("#conflict-box .conflict-source").first.get_by_role("button").click()
            await expect(page.locator("#source-dialog")).to_have_attribute("open", "")
            await page.evaluate("""() => {
              const select = document.querySelector('#cutoff');
              select.value = '2026-09-30T09:15:00+09:00';
              select.dispatchEvent(new Event('change', {bubbles: true}));
            }""")
            await expect(page.locator("#sample-metric")).to_have_text("5/50 · 10%")
            await page.wait_for_timeout(500)
            assert not await page.locator("#source-dialog").evaluate("(element) => element.open")
            await page.screenshot(path=str(OUT / "04-early-cutoff-after-delay.png"), full_page=True)
            await page.unroute("**/api/source/*", delayed_source)
            mobile = await browser.new_page(viewport={"width": 390, "height": 844})
            await mobile.goto(URL, wait_until="networkidle")
            await expect(mobile.locator("#sample-metric")).to_have_text("4/50 · 8%")
            await mobile.locator("#capture").select_option("QDOC-012")
            await expect(mobile.locator("#conflict-box .conflict-source")).to_have_count(3)
            dims = await mobile.evaluate("({scroll:document.documentElement.scrollWidth,view:innerWidth})")
            assert dims["scroll"] <= dims["view"], dims
            sizes = await mobile.evaluate("""() => ({
              prose: parseFloat(getComputedStyle(document.querySelector('.card p')).fontSize),
              control: parseFloat(getComputedStyle(document.querySelector('.source-button')).fontSize),
              hint: parseFloat(getComputedStyle(document.querySelector('.hint')).fontSize)
            })""")
            assert sizes["prose"] >= 14 and sizes["hint"] >= 14 and sizes["control"] >= 16, sizes
            await mobile.screenshot(path=str(OUT / "03-conflict-sources-mobile.png"), full_page=True)
            await browser.close()
            print("reviewer_accept=pass history_reload=pass export_revalidated=pass")
            print("stale_context_export_blocked=pass conflict_return=pass conflict_sources=3")
            print("changed_note_new_receipt=pass uncertain_post_history_recovery=pass delayed_source_cutoff=pass delayed_review_cutoff=pass")
            print("unknown_product_context=pass mobile_reflow", dims, "font_sizes", sizes)
            print("screenshots", [(x.name, x.stat().st_size) for x in sorted(OUT.glob("*.png"))])
    finally:
        server.terminate()
        try:
            server.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=5)


if __name__ == "__main__":
    asyncio.run(main())
