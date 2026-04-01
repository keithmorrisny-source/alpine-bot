"""
foretees.py — Playwright automation for Alpine Country Club's ForeTees portal.
Handles Golf tee times, Tennis courts, and Dining reservations.
"""
import asyncio
import os
import re
from typing import List, Dict, Any, Optional
from playwright.async_api import async_playwright, Page, BrowserContext

# ── Club-specific ForeTees URLs ──────────────────────────────────────────────────────────────
GOLF_BASE   = "https://ccapp.foretees.com/v5/alpinecc_golf_m24"
TENNIS_BASE = "https://ccapp.foretees.com/v5/alpinecc_flxrez12_m24"
DINING_BASE = "https://ccapp.foretees.com/v5/alpinecc_dining_m24"

SESSION_FILE = os.path.join(os.path.dirname(__file__), "session.json")


class ForeTees:
    def __init__(self, username: str, password: str):
        self.username = username
        self.password = password
        self._playwright = None
        self._browser = None
        self._context = None

    async def __aenter__(self):
        await self.start()
        return self

    async def __aexit__(self, *args):
        await self.stop()

    async def start(self):
        self._playwright = await async_playwright().start()
        self._browser = await self._playwright.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"]
        )
        storage = SESSION_FILE if os.path.exists(SESSION_FILE) else None
        self._context = await self._browser.new_context(
            storage_state=storage,
            viewport={"width": 1280, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
        )

    async def stop(self):
        if self._context:
            await self._context.close()
        if self._browser:
            await self._browser.close()
        if self._playwright:
            await self._playwright.stop()

    # ── Internal helpers ────────────────────────────────────────────────────────────────────────

    async def _new_page(self) -> Page:
        return await self._context.new_page()

    async def _ensure_logged_in(self, page: Page, base_url: str) -> bool:
        """Navigate to the section and log in if needed. Returns True on success."""
        await page.goto(f"{base_url}/Member_select", wait_until="networkidle", timeout=30000)

        if await page.locator("text=Welcome").count() > 0:
            return True

        try:
            await page.wait_for_selector('input[type="password"]', timeout=8000)

            uid_sel = 'input[name="member_id"], input[name="username"], input[name="user_id"], input[type="text"]:first-of-type'
            await page.locator(uid_sel).first.fill(self.username)
            await page.locator('input[type="password"]').fill(self.password)

            await page.locator(
                'input[type="submit"], button[type="submit"], '
                'button:has-text("Login"), button:has-text("Sign In"), '
                'input[value="Login"]'
            ).first.click()
            await page.wait_for_load_state("networkidle", timeout=20000)

            await self._context.storage_state(path=SESSION_FILE)

            return await page.locator("text=Welcome").count() > 0

        except Exception as exc:
            print(f"[ForeTees] Login error: {exc}")
            return False

    async def _save_session(self):
        """Save the current browser session to disk."""
        if self._context:
            await self._context.storage_state(path=SESSION_FILE)

    # ── Golf ─────────────────────────────────────────────────────────────────────────────────────

    async def get_tee_times(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Return available tee times for the given date.
        date_str: MM/DD/YYYY  (e.g. "04/05/2026")
        Returns: [{"time": "9:00 AM", "fb": "F", "open_spots": 4}, ...]
        """
        page = await self._new_page()
        try:
            await self._ensure_logged_in(page, GOLF_BASE)
            await page.goto(
                f"{GOLF_BASE}/Member_sheet?calDate={date_str}&course=&displayOpt=0",
                wait_until="networkidle",
                timeout=30000,
            )

            time_links = await page.locator('a[href="#"]').all()
            available: List[Dict[str, Any]] = []

            for link in time_links:
                text = (await link.text_content() or "").strip()
                if not re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)$", text, re.IGNORECASE):
                    continue

                row_data = await link.evaluate("""el => {
                    const row = el.closest('tr');
                    if (!row) return [];
                    return Array.from(row.querySelectorAll('td')).map(td => td.innerText.trim());
                }""")

                fb = row_data[1] if len(row_data) > 1 else ""
                open_spots = 4
                if row_data:
                    m = re.search(r"(\d+)\s*Open", " ".join(row_data))
                    if m:
                        open_spots = int(m.group(1))

                available.append({"time": text, "fb": fb, "open_spots": open_spots})

            return available

        finally:
            await page.close()

    async def book_tee_time(self, date_str: str, time_str: str) -> Dict[str, Any]:
        """
        Book a tee time for the member (Player 1 is pre-filled as Keith Morris).
        date_str: MM/DD/YYYY  |  time_str: e.g. "9:30 AM"
        """
        page = await self._new_page()
        try:
            await self._ensure_logged_in(page, GOLF_BASE)
            await page.goto(
                f"{GOLF_BASE}/Member_sheet?calDate={date_str}&course=&displayOpt=0",
                wait_until="networkidle",
                timeout=30000,
            )

            time_link = page.locator(f'a[href="#"]:has-text("{time_str}")').first
            if await time_link.count() == 0:
                return {"success": False, "message": f"⚠️ {time_str} is no longer available."}

            await time_link.click()
            await page.wait_for_load_state("networkidle", timeout=20000)

            submit = page.locator(
                'button:has-text("Submit Request"), '
                'input[value="Submit Request"], '
                'a:has-text("Submit Request")'
            ).first
            if await submit.count() == 0:
                return {"success": False, "message": "⚠️ Booking form not found. Please try again."}

            await submit.click()
            await page.wait_for_load_state("networkidle", timeout=20000)
            await self._save_session()

            page_text = (await page.text_content("body") or "").lower()
            if any(w in page_text for w in ["confirmed", "success", "thank", "submitted"]):
                return {"success": True, "message": f"✅ Tee time booked: *{time_str}* on {date_str}."}

            return {"success": True, "message": f"✅ Request submitted for *{time_str}* on {date_str}."}

        except Exception as exc:
            return {"success": False, "message": f"⚠️ Error booking tee time: {exc}"}
        finally:
            await page.close()

    # ── Tennis ───────────────────────────────────────────────────────────────────────────────────

    async def get_tennis_courts(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Return available tennis court slots for the given date.
        Returns: [{"time": "9:00 AM", "court": "Court 1", "href": "..."}, ...]
        """
        page = await self._new_page()
        try:
            await self._ensure_logged_in(page, TENNIS_BASE)

            await page.goto(f"{TENNIS_BASE}/Member_gensheets", wait_until="networkidle", timeout=30000)

            date_input = page.locator('input[type="text"]').first
            await date_input.triple_click()
            await date_input.fill(date_str)
            await date_input.press("Tab")
            await page.wait_for_load_state("networkidle", timeout=15000)

            available: List[Dict[str, Any]] = []
            rows = await page.locator("table tr").all()

            for row in rows:
                cells = await row.locator("td").all()
                if not cells:
                    continue
                time_text = (await cells[0].text_content() or "").strip()
                if not re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)$", time_text, re.IGNORECASE):
                    continue

                for court_idx, cell in enumerate(cells[1:], start=1):
                    link = cell.locator("a").first
                    if await link.count() > 0:
                        href = await link.get_attribute("href") or ""
                        available.append({
                            "time": time_text,
                            "court": f"Court {court_idx}",
                            "href": href,
                        })

            return available

        finally:
            await page.close()

    async def book_tennis_court(
        self,
        date_str: str,
        time_str: str,
        court_num: int = 1,
        duration_min: int = 60,
    ) -> Dict[str, Any]:
        """Book a tennis court slot."""
        page = await self._new_page()
        try:
            await self._ensure_logged_in(page, TENNIS_BASE)
            await page.goto(f"{TENNIS_BASE}/Member_gensheets", wait_until="networkidle", timeout=30000)

            date_input = page.locator('input[type="text"]').first
            await date_input.triple_click()
            await date_input.fill(date_str)
            await date_input.press("Tab")
            await page.wait_for_load_state("networkidle", timeout=15000)

            rows = await page.locator("table tr").all()
            clicked = False
            for row in rows:
                cells = await row.locator("td").all()
                if not cells:
                    continue
                time_text = (await cells[0].text_content() or "").strip()
                if time_text.upper() != time_str.upper():
                    continue
                target_cell_idx = court_num
                target_cell = cells[target_cell_idx] if len(cells) > target_cell_idx else None
                if target_cell:
                    link = target_cell.locator("a").first
                    if await link.count() > 0:
                        await link.click()
                        clicked = True
                        break
                for cell in cells[1:]:
                    lnk = cell.locator("a").first
                    if await lnk.count() > 0:
                        await lnk.click()
                        clicked = True
                        break
                if clicked:
                    break

            if not clicked:
                return {"success": False, "message": f"⚠️ No available court found at {time_str} on {date_str}."}

            await page.wait_for_load_state("networkidle", timeout=15000)

            dur_btn = page.locator(f'button:has-text("{duration_min} min")').first
            if await dur_btn.count() > 0:
                await dur_btn.click()
                await page.wait_for_load_state("networkidle", timeout=10000)

            submit = page.locator('button:has-text("Submit Request")').first
            if await submit.count() == 0:
                return {"success": False, "message": "⚠️ Booking form not found for tennis."}
            await submit.click()
            await page.wait_for_load_state("networkidle", timeout=20000)
            await self._save_session()

            return {"success": True, "message": f"✅ Tennis court booked: *{time_str}* ({duration_min} min) on {date_str}."}

        except Exception as exc:
            return {"success": False, "message": f"⚠️ Error booking tennis: {exc}"}
        finally:
            await page.close()

    # ── Dining ───────────────────────────────────────────────────────────────────────────────────

    async def get_dining_slots(self, date_str: str) -> List[Dict[str, Any]]:
        """
        Return available dining times for the given date.
        Returns: [{"location": "Bar", "time": "6:00 PM"}, ...]
        """
        page = await self._new_page()
        try:
            await self._ensure_logged_in(page, DINING_BASE)
            await page.goto(f"{DINING_BASE}/Dining_slot_v2?action=new", wait_until="networkidle", timeout=30000)

            date_input = page.locator('input[type="text"]').first
            await date_input.triple_click()
            await date_input.fill(date_str)
            await date_input.press("Tab")
            await page.wait_for_load_state("networkidle", timeout=15000)

            available: List[Dict[str, Any]] = []

            location_radios = await page.locator('input[type="radio"]').all()
            for radio in location_radios:
                radio_id = await radio.get_attribute("id") or ""
                label = page.locator(f'label[for="{radio_id}"]')
                label_text = (await label.text_content() or "").strip() if await label.count() > 0 else ""

                parent_text = await radio.evaluate("""el => {
                    const row = el.closest('tr') || el.parentElement;
                    return row ? row.innerText : '';
                }""")
                if "Closed" in parent_text:
                    continue

                await radio.click()
                await page.wait_for_timeout(500)

                time_sel = page.locator('select').first
                if await time_sel.count() > 0:
                    options = await time_sel.locator("option").all()
                    for opt in options:
                        t = (await opt.text_content() or "").strip()
                        if t:
                            available.append({"location": label_text or "Dining Room", "time": t})

            return available

        finally:
            await page.close()

    async def book_dining(
        self,
        date_str: str,
        time_str: str,
        party_size: int = 2,
        location: str = "",
    ) -> Dict[str, Any]:
        """Book a dining reservation."""
        page = await self._new_page()
        try:
            await self._ensure_logged_in(page, DINING_BASE)
            await page.goto(f"{DINING_BASE}/Dining_slot_v2?action=new", wait_until="networkidle", timeout=30000)

            date_input = page.locator('input[type="text"]').first
            await date_input.triple_click()
            await date_input.fill(date_str)
            await date_input.press("Tab")
            await page.wait_for_load_state("networkidle", timeout=15000)

            radios = await page.locator('input[type="radio"]').all()
            for radio in radios:
                parent_text = await radio.evaluate("""el => {
                    const row = el.closest('tr') || el.parentElement;
                    return row ? row.innerText : '';
                }""")
                if "Closed" in parent_text:
                    continue
                if location and location.lower() not in parent_text.lower():
                    continue
                await radio.click()
                await page.wait_for_timeout(500)
                break

            time_sel = page.locator('select').first
            if await time_sel.count() > 0:
                await time_sel.select_option(label=time_str)

            party_sel = page.locator('select').nth(1)
            if await party_sel.count() > 0:
                await party_sel.select_option(str(party_size))

            await page.locator(
                'button:has-text("Continue"), input[value="Continue"]'
            ).first.click()
            await page.wait_for_load_state("networkidle", timeout=15000)

            submit = page.locator(
                'button:has-text("Submit"), input[value="Submit"], '
                'button:has-text("Confirm")'
            ).first
            if await submit.count() > 0:
                await submit.click()
                await page.wait_for_load_state("networkidle", timeout=20000)

            await self._save_session()
            return {
                "success": True,
                "message": f"✅ Dining reservation for *{party_size}* at *{time_str}* on {date_str}.",
            }

        except Exception as exc:
            return {"success": False, "message": f"⚠️ Error booking dining: {exc}"}
        finally:
            await page.close()
