"""
automation.py — Smart eStamp Bot
All Playwright automation logic: typing helpers, form submission, main runner.

Add new automation features here (e.g. print automation, certificate download).
Never import tkinter here — this module must stay UI-agnostic.
"""
import time
import random

from config import DEFAULT_SETTINGS, PORTAL_URL

# ── Auto-install playwright ───────────────────────────────────────────────────
import subprocess, sys

def _ensure_playwright():
    try:
        from playwright.sync_api import sync_playwright
        return sync_playwright
    except ImportError:
        print("Installing playwright...")
        subprocess.run([sys.executable, "-m", "pip", "install", "playwright", "-q"], check=True)
        subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
        from playwright.sync_api import sync_playwright
        return sync_playwright

sync_playwright = _ensure_playwright()

# ── Core delay helpers ────────────────────────────────────────────────────────
def w(a=0.1, b=0.3):
    """
    Fixed micro-delay — called inside type_like_human().
    DO NOT ADD MULTIPLIER HERE — bot-detection critical.
    """
    time.sleep(random.uniform(a, b))


# ── Human-like typing — DO NOT MODIFY ────────────────────────────────────────
def type_like_human(page, selector, text):
    """
    Types text character-by-character with random 50-120ms delays.
    Sacred — portal bot detection tracks typing cadence. Never change delays.
    """
    try:
        el = page.locator(selector).first
        el.scroll_into_view_if_needed()
        w(0.1, 0.2)
        el.click()
        w(0.1, 0.15)
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        w(0.05, 0.1)
        for ch in str(text):
            page.keyboard.type(ch)
            time.sleep(random.uniform(0.05, 0.12))   # sacred — never multiply
        w(0.1, 0.2)
        return True
    except Exception as e:
        print(f"    [!] {selector}: {e}")
        return False


def fill_fast(page, selector, text):
    """
    Fast field fill — uses page.keyboard.type() at a fixed 25ms/char.
    Fires identical DOM events to type_like_human (keydown/keypress/keyup per char)
    so portal typedCharCount and event listeners still register every keystroke.
    3-4× faster than type_like_human for long fields.
    """
    try:
        el = page.locator(selector).first
        el.scroll_into_view_if_needed()
        el.click()
        page.keyboard.press("Control+a")
        page.keyboard.press("Delete")
        page.keyboard.type(str(text), delay=25)   # 25ms/char, all events fired
        return True
    except Exception as e:
        print(f"    [!] fill_fast {selector}: {e}")
        return False


# ── Single submission cycle ───────────────────────────────────────────────────
def _submit_one(page, d, delay_mult, msg_queue, kill_event, skip_nav=False, fast_fill=False):
    """
    One full form-fill → save → read Ref ID → Done cycle.
    Returns (ref_id, True).  Raises RuntimeError on KILL.
    skip_nav=True   → skip navigation (Done already lands on article page).
    fast_fill=True  → use fill_fast() 25ms/char instead of type_like_human().
    """

    def ws(a, b):
        """Scaled wait — between automation steps only."""
        if kill_event.is_set():
            raise RuntimeError("KILL signal received")
        time.sleep(random.uniform(a * delay_mult, b * delay_mult))

    def _q(msg, level="info"):
        msg_queue.put({"type": "log", "text": msg, "level": level})

    def chk():
        if kill_event.is_set():
            raise RuntimeError("KILL signal received")

    # Choose fill function based on fast_fill setting
    fill_fn = fill_fast if fast_fill else type_like_human

    # ── Derive purchased_by logic ─────────────────────────────────────────────
    pb_mode = d["purchased_by"].upper().strip()
    if pb_mode == "FIRST PARTY":
        purchased_by_name  = d["first_party"]
        stamp_duty_paid_by = d["first_party"]
        fp_mobile          = d["mobile_number"]
        sp_mobile          = None
    elif pb_mode == "SECOND PARTY":
        purchased_by_name  = d["second_party"]
        stamp_duty_paid_by = d["second_party"]
        fp_mobile          = None
        sp_mobile          = d["mobile_number"]
    else:
        purchased_by_name  = pb_mode
        stamp_duty_paid_by = pb_mode
        fp_mobile          = d["mobile_number"]
        sp_mobile          = None
        _q(f"⚠ Unknown purchased_by '{pb_mode}', using raw value.")

    # STEP 1 ── Navigate to article selection ──────────────────────────────────
    # Done button (frmSubmit(2)) already posts to LoadStampDuty, so after the
    # first submission we are already on the article page — skip the click.
    chk()
    if skip_nav:
        _q("  [1] Already on article page ✓ (skipping navigation)")
        ws(0.1, 0.2)
    else:
        _q("  [1] Create Submission...")
        page.locator("a[href*='LoadStampDuty']").first.click()
        page.wait_for_load_state("domcontentloaded")
        ws(0.3, 0.5)

    # STEP 2 ── Article search + select + Next ─────────────────────────────────
    _q(f"  [2] Article: {d['article_search']}")
    chk()
    try:
        search_box = page.locator("input[placeholder*='Filter']").first
        search_box.wait_for(timeout=3000)
    except Exception:
        search_box = page.locator("input[type='text']").first

    search_box.click()
    ws(0.1, 0.15)
    for ch in d["article_search"]:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.04, 0.08))   # article search box, not form page

    time.sleep(0.10)   # let dropdown filter

    selected = False
    for sel_el in page.locator("select").all():
        chk()
        opts       = sel_el.locator("option").all()
        valid_opts = []
        for opt in opts:
            v = (opt.get_attribute("value") or "").strip()
            t = opt.inner_text().strip()
            if v and "Select" not in t and t != "":
                valid_opts.append((v, t))
        if valid_opts:
            best = next(((v, t) for v, t in valid_opts
                         if d["article_search"].lower() in t.lower()), valid_opts[0])
            sel_el.select_option(value=best[0])
            _q(f"     ✓ Selected: {best[1]}")
            ws(0.1, 0.2)
            selected = True
            break

    if not selected:
        _q("     ⚠ No matching article option found!")

    ws(0.1, 0.15)
    chk()
    page.locator("input[name='pNext']").first.click()
    page.wait_for_load_state("domcontentloaded")
    ws(0.4, 0.6)

    # STEP 3 ── Form fill ──────────────────────────────────────────────────────
    _q("  [3] Form fill...")
    chk()

    # TextField6Mand → Purchased By
    fill_fn(page, "#TextField6Mand", purchased_by_name)
    _q(f"     ✓ Purchased By: {purchased_by_name}")

    # TextField11Mand → First Party
    fill_fn(page, "#TextField11Mand", d["first_party"])
    _q(f"     ✓ First Party: {d['first_party']}")

    # TextField18Mand → Second Party — fill only if provided, skip if blank
    if d.get("second_party", "").strip():
        fill_fn(page, "#TextField18Mand", d["second_party"])
        _q(f"     ✓ Second Party: {d['second_party']}")
    else:
        _q("     ↷ Second Party: skipped (not provided)")

    # TextField24Mand → Stamp Duty Paid By — filled AFTER TextField11 blur
    fill_fn(page, "#TextField24Mand", stamp_duty_paid_by)
    _q(f"     ✓ Paid By: {stamp_duty_paid_by}")

    # TextField28Mand → Stamp Duty Amount
    fill_fn(page, "#TextField28Mand", d["stamp_duty_amount"])
    _q(f"     ✓ Amount: {d['stamp_duty_amount']}")

    # Tab → triggers amount validation popup (if any)
    ws(0.1, 0.15)
    page.keyboard.press("Tab")
    ws(0.4, 0.6)

    # Mobile routing — fpMobNo / spMobNo (maxlength=10 each)
    chk()
    if fp_mobile:
        _q(f"     First Party Mobile: {fp_mobile}")
        try:
            ml = page.locator("#fpMobNo").first
            ml.scroll_into_view_if_needed()
            ws(0.1, 0.15)
            ml.click()
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            w(0.1, 0.15)
            for ch in fp_mobile:
                page.keyboard.type(ch)
                time.sleep(random.uniform(0.06, 0.12))
            _q("     ✓ First Party Mobile filled!")
        except Exception as e:
            _q(f"     [!] First Party Mobile error: {e}", "error")

    if sp_mobile:
        _q(f"     Second Party Mobile: {sp_mobile}")
        try:
            ml = page.locator("#spMobNo").first
            ml.scroll_into_view_if_needed()
            ws(0.2, 0.3)
            ml.click()
            page.keyboard.press("Control+a")
            page.keyboard.press("Delete")
            w(0.1, 0.15)
            for ch in sp_mobile:
                page.keyboard.type(ch)
                time.sleep(random.uniform(0.06, 0.12))
            _q("     ✓ Second Party Mobile filled!")
        except Exception as e:
            _q(f"     [!] Second Party Mobile error: {e}", "error")

    ws(0.1, 0.2)

    # STEP 4 ── Save ───────────────────────────────────────────────────────────
    _q("  [4] Save...")
    chk()
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    ws(0.15, 0.25)
    page.locator("input[name='pSave']").first.click()
    # Wait for the after-save page: look for the Ref ID bold element
    try:
        page.locator("td.txt-body b").first.wait_for(timeout=12000)
    except Exception:
        page.wait_for_load_state("domcontentloaded")
    ws(0.2, 0.3)

    # STEP 5 ── Read Reference ID ──────────────────────────────────────────────
    _q("  [5] Reading Ref ID...")
    ref_id = ""
    try:
        ref_id = page.locator("td.txt-body b").first.inner_text().strip()
        _q(f"     ✅ Ref ID: {ref_id}", "ok")
    except Exception:
        _q("     [!] Could not read Ref ID.", "error")

    # Click Done — after_save_page has 4 name='pNext' buttons:
    #   1. Print This Page   2. Proceed to Generate Certificate
    #   3. Done (frmSubmit(2)) 4. Preview Submission
    # value*='Done' is the only safe unique selector here.
    chk()
    try:
        page.locator("input[value*='Done']").first.click()
        page.wait_for_load_state("domcontentloaded")
        ws(0.2, 0.35)   # Done posts to LoadStampDuty — article page loads fast
    except Exception:
        try:
            page.locator("input[name='pBack']").first.click()
            page.wait_for_load_state("domcontentloaded")
            ws(0.2, 0.35)
        except Exception:
            _q("     [!] Done/Back button not found — navigate manually.", "error")

    # After Done we are already on the article selection page (LoadStampDuty)
    return ref_id, True


# ── Main automation loop ──────────────────────────────────────────────────────
def run_automation(data, settings, msg_queue, stop_event, kill_event):
    """
    Automation runner — called in a daemon thread by the UI.

    data:        list of entry dicts (copies, ref_ids fields included)
    settings:    dict — cdp_url, delay_mult, fast_fill
    msg_queue:   queue.Queue for UI communication
    stop_event:  threading.Event — clean stop (finish current entry, then stop)
    kill_event:  threading.Event — instant stop (emergency)

    Queue message types:
      {"type": "log",      "text": str, "level": "ok"|"error"|"info"}
      {"type": "progress", "done": int, "total": int, "success": int, "failed": int}
      {"type": "status",   "row": int,  "status": "Running"|"Done"|"Error"}
      {"type": "ref_id",   "row": int,  "ref_id": str, "label": str}
      {"type": "done"}
    """
    cdp_url    = settings.get("cdp_url",    DEFAULT_SETTINGS["cdp_url"])
    delay_mult = settings.get("delay_mult", DEFAULT_SETTINGS["delay_mult"])
    fast_fill  = settings.get("fast_fill",  DEFAULT_SETTINGS["fast_fill"])

    def log(msg, level="info"):
        msg_queue.put({"type": "log", "text": msg, "level": level})

    total_subs   = sum(d.get("copies", 1) for d in data)
    done_subs    = 0
    success_subs = 0
    failed_subs  = 0
    msg_queue.put({"type": "progress", "done": 0, "total": total_subs,
                   "success": 0, "failed": 0})

    with sync_playwright() as p:
        # ── Connect to Chrome via CDP ─────────────────────────────────────────
        try:
            browser = p.chromium.connect_over_cdp(cdp_url)
            log("✅ Chrome connected!", "ok")
        except Exception as e:
            log(f"❌ Cannot connect to Chrome: {e}", "error")
            log("  Start Chrome with: chrome.exe --remote-debugging-port=9222 "
                "--user-data-dir=C:\\chrome-debug", "info")
            msg_queue.put({"type": "done"})
            return

        ctx = browser.contexts[0]

        # ── Anti-detection init script — DO NOT REMOVE ────────────────────────
        ctx.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
            window.chrome = {runtime: {}};
        """)

        # ── Find eStamp tab ───────────────────────────────────────────────────
        pages = ctx.pages
        page  = None
        for pg in pages:
            if "shcilestamp" in pg.url or "eStampIndia" in pg.url:
                page = pg
                log("✅ eStamp tab found!", "ok")
                break
        if not page:
            page = pages[0] if pages else ctx.new_page()
            page.goto(PORTAL_URL)
            page.wait_for_load_state("domcontentloaded")

        page.bring_to_front()
        time.sleep(random.uniform(0.5 * delay_mult, 1.0 * delay_mult))

        # ── Dialog handler — registered OUTSIDE loop (critical bug-fix) ───────
        def ok_popup(dialog):
            log(f"     POPUP: {dialog.message[:60]} → OK")
            time.sleep(random.uniform(0.2 * delay_mult, 0.4 * delay_mult))
            dialog.accept()
        page.on("dialog", ok_popup)

        # ── Entry loop ────────────────────────────────────────────────────────
        skip_nav = False   # becomes True after first successful Done click
        for row_idx, d in enumerate(data):
            if kill_event.is_set() or stop_event.is_set():
                log("⛔ Stopped before processing entry.", "error")
                break

            copies  = d.get("copies", 1)
            ref_ids = []

            log(f"\n{'='*55}")
            log(f"  ENTRY {row_idx+1}/{len(data)}: {d['first_party']}  ×{copies} copies")
            log(f"{'='*55}")

            msg_queue.put({"type": "status", "row": row_idx, "status": "Running"})

            # ── Copy loop ─────────────────────────────────────────────────────
            for copy_num in range(1, copies + 1):

                # Kill = immediate stop
                if kill_event.is_set():
                    log("⚡ KILL — stopping immediately.", "error")
                    ref_ids.append("KILLED")
                    break

                log(f"  COPY {copy_num}/{copies}...")

                try:
                    ref_id, skip_nav = _submit_one(
                        page, d, delay_mult, msg_queue, kill_event,
                        skip_nav, fast_fill)
                    ref_ids.append(ref_id if ref_id else "NO_REF")
                    done_subs    += 1
                    success_subs += 1
                    lbl = f"E{row_idx+1}_{copy_num}"
                    msg_queue.put({"type": "ref_id",  "row": row_idx,
                                   "ref_id": ref_id, "label": lbl})
                    msg_queue.put({"type": "progress", "done": done_subs,
                                   "total": total_subs, "success": success_subs,
                                   "failed": failed_subs})

                except RuntimeError:
                    log(f"  COPY {copy_num}/{copies} ⚡ KILLED.", "error")
                    ref_ids.append("KILLED")
                    done_subs   += 1
                    failed_subs += 1
                    msg_queue.put({"type": "progress", "done": done_subs,
                                   "total": total_subs, "success": success_subs,
                                   "failed": failed_subs})
                    break

                except Exception as err:
                    # Skip failed copy, continue remaining copies
                    log(f"  COPY {copy_num}/{copies} ❌ FAILED: {err}", "error")
                    ref_ids.append("FAILED")
                    skip_nav = False   # reset — unknown page state after error
                    try:
                        page.screenshot(path=f"error_r{row_idx+1}_c{copy_num}.png")
                        log(f"  Screenshot saved: error_r{row_idx+1}_c{copy_num}.png")
                    except Exception:
                        pass
                    done_subs   += 1
                    failed_subs += 1
                    msg_queue.put({"type": "progress", "done": done_subs,
                                   "total": total_subs, "success": success_subs,
                                   "failed": failed_subs})

                # Brief gap between copies
                if copy_num < copies and not kill_event.is_set():
                    time.sleep(0.5 * delay_mult)

            # ── Store ref_ids back into entry dict ────────────────────────────
            d["ref_ids"] = ref_ids
            labeled   = [
                f"E{row_idx+1}_{i+1}" if r not in ("FAILED", "KILLED", "NO_REF")
                else f"E{row_idx+1}_{i+1}:{r}"
                for i, r in enumerate(ref_ids)
            ]
            all_refs  = ", ".join(labeled)
            has_error = any(r in ("FAILED", "KILLED", "NO_REF") for r in ref_ids)

            final_status = "Error" if has_error else "Done"
            msg_queue.put({"type": "status", "row": row_idx, "status": final_status})
            log(f"  All Ref IDs: {all_refs}",
                "error" if has_error else "ok")

            # Respect stop after finishing the current entry
            if stop_event.is_set() or kill_event.is_set():
                log("⛔ Stopping after current entry.", "info")
                break

        log("\n" + "="*55)
        log("  ✅ AUTOMATION COMPLETE!", "ok")
        log("="*55)
        msg_queue.put({"type": "done"})
