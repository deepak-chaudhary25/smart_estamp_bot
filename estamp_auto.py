#!/usr/bin/env python3
"""
Smart eStamp Bot — estamp_auto.py
Step 1: Copies support + threading-ready automation core (CLI mode).
Step 2: Tkinter UI (next step).
"""
import time, random, subprocess, sys
import threading
import queue as _queue
import copy
import tkinter as tk
from tkinter import ttk, messagebox

# ── Auto-install playwright ───────────────────────────────────────────────────
def _install(pkg):
    subprocess.run([sys.executable, "-m", "pip", "install", pkg, "-q"], check=True)

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    print("Installing playwright...")
    _install("playwright")
    subprocess.run([sys.executable, "-m", "playwright", "install", "chromium"], check=True)
    from playwright.sync_api import sync_playwright

# ── Default settings ──────────────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "cdp_url"    : "http://localhost:9222",
    "delay_mult" : 1.0,   # scales ws() between-step waits ONLY — never per-char delays
}

# ── CLI sample data ───────────────────────────────────────────────────────────
# purchased_by: "FIRST PARTY"  → TextField6/24 = first_party,  fpMobNo = mobile
#               "SECOND PARTY" → TextField6/24 = second_party, spMobNo = mobile
DATA = [
    {
        "article_search"   : "Affidavit",
        "purchased_by"     : "FIRST PARTY",
        "first_party"      : "RAMESH KUMAR",
        "second_party"     : "AXIS BANK LTD",
        "stamp_duty_amount": "10",
        "mobile_number"    : "9898989889",
        "copies"           : 2,
        "ref_ids"          : [],   # populated after run
    },
]

# ── Core delay helpers ────────────────────────────────────────────────────────
def w(a=0.1, b=0.3):
    """
    Fixed micro-delay — called inside type_like_human().
    DO NOT ADD MULTIPLIER HERE — bot-detection critical.
    """
    time.sleep(random.uniform(a, b))

# ── Human-like typing — DO NOT MODIFY ────────────────────────────────────────
def type_like_human(page, selector, text):
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

# ── Single submission cycle ───────────────────────────────────────────────────
def _submit_one(page, d, delay_mult, msg_queue, kill_event):
    """
    One full form-fill → save → read Ref ID → Done cycle.
    Returns ref_id string.  Raises RuntimeError on KILL.

    ws() = between-step scaled waits (delay_mult applied here ONLY).
    w()  = untouched — used inside type_like_human internals.
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

    # STEP 1 ── Create Submission ──────────────────────────────────────────────
    _q("  [1] Create Submission...")
    chk()
    page.locator("a[href*='LoadStampDuty']").first.click()
    page.wait_for_load_state("domcontentloaded")
    ws(0.8, 1.2)

    # STEP 2 ── Article search + select + Next ────────────────────────────────
    _q(f"  [2] Article: {d['article_search']}")
    chk()
    try:
        search_box = page.locator("input[placeholder*='Filter']").first
        search_box.wait_for(timeout=3000)
    except Exception:
        search_box = page.locator("input[type='text']").first

    search_box.click()
    ws(0.2, 0.3)
    for ch in d["article_search"]:
        page.keyboard.type(ch)
        time.sleep(random.uniform(0.06, 0.12))

    time.sleep(0.5)   # let dropdown filter — intentionally NOT scaled

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
            ws(0.2, 0.3)
            selected = True
            break

    if not selected:
        _q("     ⚠ No matching article option found!")

    ws(0.2, 0.3)
    chk()
    page.locator("input[name='pNext']").first.click()
    page.wait_for_load_state("domcontentloaded")
    ws(1.0, 1.5)

    # STEP 3 ── Form fill ─────────────────────────────────────────────────────
    _q("  [3] Form fill...")
    chk()

    # TextField6Mand → Purchased By
    type_like_human(page, "#TextField6Mand", purchased_by_name)
    _q(f"     ✓ Purchased By: {purchased_by_name}")

    # TextField11Mand → First Party
    # Portal JS firstPartyAsSdPaidBy() may auto-copy to TextField24 on blur.
    # We re-fill TextField24 explicitly after, so order is critical.
    type_like_human(page, "#TextField11Mand", d["first_party"])
    _q(f"     ✓ First Party: {d['first_party']}")

    # TextField18Mand → Second Party — ALWAYS clear + fill (never skip)
    type_like_human(page, "#TextField18Mand", d["second_party"])
    _q(f"     ✓ Second Party: {d['second_party']}")

    # TextField24Mand → Stamp Duty Paid By — filled AFTER TextField11 blur
    type_like_human(page, "#TextField24Mand", stamp_duty_paid_by)
    _q(f"     ✓ Paid By: {stamp_duty_paid_by}")

    # TextField28Mand → Stamp Duty Amount
    type_like_human(page, "#TextField28Mand", d["stamp_duty_amount"])
    _q(f"     ✓ Amount: {d['stamp_duty_amount']}")

    # Tab → triggers amount validation popup (if any)
    ws(0.2, 0.3)
    page.keyboard.press("Tab")
    ws(1.0, 1.5)

    # Mobile routing — fpMobNo / spMobNo (maxlength=10 each)
    chk()
    if fp_mobile:
        _q(f"     First Party Mobile: {fp_mobile}")
        try:
            ml = page.locator("#fpMobNo").first
            ml.scroll_into_view_if_needed()
            ws(0.2, 0.3)
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

    ws(0.3, 0.5)

    # STEP 4 ── Save ──────────────────────────────────────────────────────────
    _q("  [4] Save...")
    chk()
    page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
    ws(0.3, 0.5)
    page.locator("input[name='pSave']").first.click()
    ws(2.0, 3.0)
    page.wait_for_load_state("domcontentloaded")
    ws(0.5, 1.0)

    # STEP 5 ── Read Reference ID ─────────────────────────────────────────────
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
        ws(0.8, 1.2)
    except Exception:
        try:
            page.locator("input[name='pBack']").first.click()
            page.wait_for_load_state("domcontentloaded")
            ws(0.8, 1.2)
        except Exception:
            _q("     [!] Done/Back button not found — navigate manually.", "error")

    return ref_id

# ── Main automation loop ──────────────────────────────────────────────────────
def run_automation(data, settings, msg_queue, stop_event, kill_event):
    """
    Automation runner — designed to be called in a daemon thread by the UI,
    or directly from main() for CLI use.

    data:        list of entry dicts (copies, ref_ids fields included)
    settings:    dict — cdp_url, delay_mult
    msg_queue:   queue.Queue for UI/CLI communication
    stop_event:  threading.Event — clean stop (finish current copy, then stop)
    kill_event:  threading.Event — instant stop (emergency)

    Queue message types:
      {"type": "log",      "text": str, "level": "ok"|"error"|"info"}
      {"type": "progress", "done": int, "total": int}
      {"type": "status",   "row": int,  "status": "Running"|"Done"|"Error"}
      {"type": "ref_id",   "row": int,  "ref_id": str}
      {"type": "done"}
    """
    cdp_url    = settings.get("cdp_url",    "http://localhost:9222")
    delay_mult = settings.get("delay_mult", 1.0)

    def log(msg, level="info"):
        msg_queue.put({"type": "log", "text": msg, "level": level})

    total_subs = sum(d.get("copies", 1) for d in data)
    done_subs  = 0
    msg_queue.put({"type": "progress", "done": 0, "total": total_subs})

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
            page.goto("https://shcilestamp.com/eStampIndia/submission/"
                      "SubmissionServlet?rDoAction=LoadStampDuty")
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

                # Stop = clean stop — finish current ENTRY then stop
                # (we let this copy run, break after entry loop)

                log(f"  COPY {copy_num}/{copies}...")

                try:
                    ref_id = _submit_one(page, d, delay_mult, msg_queue, kill_event)
                    ref_ids.append(ref_id if ref_id else "NO_REF")
                    done_subs += 1
                    msg_queue.put({"type": "ref_id",   "row": row_idx, "ref_id": ref_id})
                    msg_queue.put({"type": "progress",  "done": done_subs, "total": total_subs})
                    log(f"  COPY {copy_num}/{copies} ✅ Ref: {ref_id}", "ok")

                except RuntimeError:
                    # KILL was triggered inside _submit_one
                    log(f"  COPY {copy_num}/{copies} ⚡ KILLED.", "error")
                    ref_ids.append("KILLED")
                    break

                except Exception as err:
                    # Q4 Option A: skip failed copy, continue remaining copies
                    log(f"  COPY {copy_num}/{copies} ❌ FAILED: {err}", "error")
                    ref_ids.append("FAILED")
                    try:
                        page.screenshot(path=f"error_r{row_idx+1}_c{copy_num}.png")
                        log(f"  Screenshot saved: error_r{row_idx+1}_c{copy_num}.png")
                    except Exception:
                        pass
                    done_subs += 1
                    msg_queue.put({"type": "progress", "done": done_subs, "total": total_subs})
                    # Continue to next copy

                # Gap between copies (not after the last one)
                if copy_num < copies and not kill_event.is_set():
                    time.sleep(2 * delay_mult)

            # ── Store ref_ids back into entry dict ────────────────────────────
            d["ref_ids"] = ref_ids
            all_refs     = ", ".join(ref_ids)
            has_error    = any(r in ("FAILED", "KILLED", "NO_REF") for r in ref_ids)

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

# ─────────────────────────────────────────────────────────────────────────────
# STEP 2 — Tkinter GUI
# ─────────────────────────────────────────────────────────────────────────────
class App(tk.Tk):
    # ── Theme constants ───────────────────────────────────────────────────────
    BG    = "#1e1e2e"
    FG    = "#e0e0e0"
    ACCENT= "#4ecca3"
    PANEL = "#252537"
    EBGL  = "#313145"   # entry/widget background
    FONT  = ("Segoe UI", 10)
    FONTB = ("Segoe UI", 10, "bold")
    FONTH = ("Segoe UI", 11, "bold")
    STC   = {"Pending": "#e0e0e0", "Running": "#74b9ff",
             "Done": "#4ecca3",  "Error": "#ff6b6b"}

    def __init__(self):
        super().__init__()
        self.title("Smart eStamp Bot")
        self.configure(bg=self.BG)
        self.minsize(1100, 680)

        # shared state
        self._q         = _queue.Queue()
        self._stop_ev   = threading.Event()
        self._kill_ev   = threading.Event()
        self._thread    = None
        self._row_refs  = {}          # row_idx → [ref_id, ...]
        self.queue_data = []          # list of entry dicts
        self._cdp_url    = tk.StringVar(value=DEFAULT_SETTINGS["cdp_url"])
        self._delay_mult = tk.StringVar(value=str(DEFAULT_SETTINGS["delay_mult"]))

        self._apply_style()

        # ── 3-panel layout ────────────────────────────────────────────────────
        pane = tk.PanedWindow(self, orient="horizontal", bg=self.BG,
                              sashwidth=5, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=6, pady=(6, 0))

        lf = tk.LabelFrame(pane, text=" New Entry ", bg=self.PANEL, fg=self.ACCENT,
                           font=self.FONTB, bd=1, relief="groove")
        cf = tk.LabelFrame(pane, text=" Queue ",     bg=self.PANEL, fg=self.ACCENT,
                           font=self.FONTB, bd=1, relief="groove")
        rf = tk.LabelFrame(pane, text=" Live Log ",  bg=self.PANEL, fg=self.ACCENT,
                           font=self.FONTB, bd=1, relief="groove")

        pane.add(lf, minsize=240, width=265)
        pane.add(cf, minsize=400)
        pane.add(rf, minsize=260, width=310)

        self._build_left(lf)
        self._build_center(cf)
        self._build_right(rf)
        self._build_bottom()

        # startup hints
        self._log("Smart eStamp Bot ready.", "ok")
        self._log("1. Start Chrome:", "info")
        self._log("   chrome.exe --remote-debugging-port=9222 --user-data-dir=C:\\chrome-debug", "info")
        self._log("2. Login at shcilestamp.com", "info")
        self._log("3. Add entries → click ▶ Run", "info")

        self.after(100, self._poll)

    # ── ttk Style ─────────────────────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("Treeview", background=self.PANEL, foreground=self.FG,
                    fieldbackground=self.PANEL, rowheight=26,
                    font=("Segoe UI", 9))
        s.configure("Treeview.Heading", background=self.EBGL,
                    foreground=self.ACCENT, font=("Segoe UI", 9, "bold"),
                    relief="flat")
        s.map("Treeview", background=[("selected", "#3a3a5c")],
              foreground=[("selected", self.FG)])
        s.configure("TScrollbar", background=self.PANEL,
                    troughcolor=self.BG, borderwidth=0, arrowsize=14)
        s.configure("Green.Horizontal.TProgressbar",
                    troughcolor=self.EBGL, background=self.ACCENT, thickness=10)
        s.configure("TCombobox", fieldbackground=self.EBGL,
                    background=self.EBGL, foreground=self.FG,
                    selectbackground="#3a3a5c", arrowcolor=self.FG)
        s.map("TCombobox",
              fieldbackground=[("readonly", self.EBGL)],
              foreground=[("readonly", self.FG)])
        self.option_add("*TCombobox*Listbox.background", self.EBGL)
        self.option_add("*TCombobox*Listbox.foreground", self.FG)
        self.option_add("*TCombobox*Listbox.selectBackground", "#3a3a5c")

    # ── Widget helpers ────────────────────────────────────────────────────────
    def _lbl(self, p, text, row):
        tk.Label(p, text=text, bg=self.PANEL, fg=self.FG,
                 font=self.FONT, anchor="w").grid(
            row=row, column=0, sticky="w", padx=(10, 4), pady=4)

    def _ent(self, p, row):
        v = tk.StringVar()
        e = tk.Entry(p, textvariable=v, bg=self.EBGL, fg=self.FG,
                     font=self.FONT, relief="flat", bd=4,
                     insertbackground=self.FG, width=22)
        e.grid(row=row, column=1, sticky="ew", padx=(4, 10), pady=4)
        return v

    def _mkbtn(self, parent, text, cmd, bg="#444460", fg=None, state="normal"):
        return tk.Button(parent, text=text, command=cmd,
                         bg=bg, fg=fg or self.FG, font=self.FONTB,
                         relief="flat", cursor="hand2",
                         padx=14, pady=6, state=state)

    # ── Left panel — entry form ───────────────────────────────────────────────
    def _build_left(self, p):
        p.columnconfigure(1, weight=1)
        self._lbl(p, "Article", 0);       self._art = self._ent(p, 0)
        self._lbl(p, "First Party", 1);   self._fp  = self._ent(p, 1)
        self._lbl(p, "Second Party", 2);  self._sp  = self._ent(p, 2)

        self._lbl(p, "Purchased By", 3)
        self._pb = ttk.Combobox(p, values=["FIRST PARTY", "SECOND PARTY"],
                                state="readonly", font=self.FONT, width=20)
        self._pb.set("FIRST PARTY")
        self._pb.grid(row=3, column=1, sticky="ew", padx=(4, 10), pady=4)

        self._lbl(p, "Amount (₹)", 4);    self._amt = self._ent(p, 4)
        self._lbl(p, "Mobile", 5);        self._mob = self._ent(p, 5)
        self._lbl(p, "Copies", 6);        self._cop = self._ent(p, 6)
        self._cop.set("1")

        tk.Button(p, text="+ Add Entry", bg=self.ACCENT, fg=self.BG,
                  font=self.FONTB, relief="flat", cursor="hand2",
                  pady=8, command=self._add_entry).grid(
            row=7, column=0, columnspan=2, sticky="ew", padx=10, pady=(14, 6))

    # ── Center panel — queue Treeview ─────────────────────────────────────────
    def _build_center(self, p):
        COLS   = ("#","Article","First Party","Purchased By",
                  "Amount","Mobile","Copies","Status","Ref IDs")
        WIDTHS = (32, 88, 120, 100, 60, 95, 50, 78, 180)

        frm = tk.Frame(p, bg=self.PANEL)
        frm.pack(fill="both", expand=True, padx=6, pady=(4, 0))

        self.tree = ttk.Treeview(frm, columns=COLS, show="headings",
                                 selectmode="browse")
        for col, w in zip(COLS, WIDTHS):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=w, minwidth=max(w-20,30),
                             stretch=(col == "Ref IDs"))

        for tag, color in self.STC.items():
            self.tree.tag_configure(tag, foreground=color)

        vsb = ttk.Scrollbar(frm, orient="vertical",   command=self.tree.yview)
        hsb = ttk.Scrollbar(frm, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        self.tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frm.rowconfigure(0, weight=1)
        frm.columnconfigure(0, weight=1)

        bf = tk.Frame(p, bg=self.PANEL)
        bf.pack(fill="x", padx=6, pady=(4, 6))
        self._mkbtn(bf, "🗑 Remove Selected", self._remove_selected).pack(side="left", padx=(0,6))
        self._mkbtn(bf, "🧹 Clear All",        self._clear_all).pack(side="left")

    # ── Right panel — log + progress ──────────────────────────────────────────
    def _build_right(self, p):
        frm = tk.Frame(p, bg=self.PANEL)
        frm.pack(fill="both", expand=True, padx=6, pady=(4, 0))

        self._log_txt = tk.Text(frm, bg="#12121e", fg=self.FG,
                                font=("Consolas", 9), state="disabled",
                                relief="flat", wrap="word", bd=0, width=34)
        self._log_txt.tag_configure("ok",    foreground=self.ACCENT)
        self._log_txt.tag_configure("error", foreground="#ff6b6b")
        self._log_txt.tag_configure("info",  foreground="#cdd6f4")

        vsb = ttk.Scrollbar(frm, orient="vertical", command=self._log_txt.yview)
        self._log_txt.configure(yscrollcommand=vsb.set)
        self._log_txt.pack(side="left", fill="both", expand=True)
        vsb.pack(side="left", fill="y")

        self._prog_lbl = tk.Label(p, text="0/0 submissions done",
                                  bg=self.PANEL, fg=self.FG, font=self.FONT)
        self._prog_lbl.pack(side="bottom", anchor="w", padx=10, pady=(0, 4))
        self._prog = ttk.Progressbar(p, style="Green.Horizontal.TProgressbar",
                                     orient="horizontal", mode="determinate")
        self._prog.pack(side="bottom", fill="x", padx=6, pady=(0, 2))

    # ── Bottom toolbar ────────────────────────────────────────────────────────
    def _build_bottom(self):
        bf = tk.Frame(self, bg=self.BG, pady=6)
        bf.pack(fill="x", padx=6)
        self._btn_run  = self._mkbtn(bf, "▶ Run",       self._run,  self.ACCENT, fg=self.BG)
        self._btn_stop = self._mkbtn(bf, "⛔ Stop",      self._stop, "#fdcb6e",  fg=self.BG, state="disabled")
        self._btn_kill = self._mkbtn(bf, "⚡ Kill",      self._kill, "#ff6b6b",  fg="white",  state="disabled")
        self._btn_set  = self._mkbtn(bf, "⚙ Settings",  self._open_settings)
        for b in (self._btn_run, self._btn_stop, self._btn_kill, self._btn_set):
            b.pack(side="left", padx=(0, 6))

    # ── Add entry ─────────────────────────────────────────────────────────────
    def _add_entry(self):
        art = self._art.get().strip()
        fp  = self._fp.get().strip()
        sp  = self._sp.get().strip()
        pb  = self._pb.get().strip()
        amt = self._amt.get().strip()
        mob = self._mob.get().strip()
        cop = self._cop.get().strip()

        errs = []
        if not art:                            errs.append("Article is required.")
        if not fp:                             errs.append("First Party is required.")
        if not sp:                             errs.append("Second Party is required.")
        if not amt.isdigit():                  errs.append("Amount must be a number.")
        if not mob.isdigit() or len(mob)!=10:  errs.append("Mobile must be exactly 10 digits.")
        try:
            copies = int(cop)
            if copies < 1: raise ValueError
        except ValueError:
            errs.append("Copies must be a positive integer.")
            copies = 1
        if errs:
            messagebox.showerror("Validation Error", "\n".join(errs), parent=self)
            return

        row = len(self.queue_data)
        entry = {
            "article_search":    art, "purchased_by":      pb,
            "first_party":       fp,  "second_party":       sp,
            "stamp_duty_amount": amt, "mobile_number":      mob,
            "copies":            copies, "ref_ids":          [],
        }
        self.queue_data.append(entry)
        self.tree.insert("", "end", iid=str(row),
                         values=(row+1, art, fp, pb, amt, mob, copies, "Pending", ""),
                         tags=("Pending",))
        # clear form fields (keep Purchased By selection)
        for v in (self._art, self._fp, self._sp, self._amt, self._mob):
            v.set("")
        self._cop.set("1")

    # ── Remove / Clear ────────────────────────────────────────────────────────
    def _remove_selected(self):
        sel = self.tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        # Snapshot remaining entries (excluding removed)
        remaining = [(self.tree.item(iid, "values"), self.tree.item(iid, "tags"))
                     for iid in self.tree.get_children() if iid != sel[0]]
        # Rebuild queue_data without removed entry
        self.queue_data.pop(idx)
        # Rebuild Treeview with correct sequential iids
        self.tree.delete(*self.tree.get_children())
        for new_i, (vals, tags) in enumerate(remaining):
            v2 = list(vals); v2[0] = new_i + 1
            self.tree.insert("", "end", iid=str(new_i), values=v2, tags=tags)

    def _clear_all(self):
        if not self.queue_data:
            return
        if messagebox.askyesno("Clear All", "Remove all entries from queue?", parent=self):
            self.tree.delete(*self.tree.get_children())
            self.queue_data.clear()
            self._row_refs.clear()

    # ── Run / Stop / Kill / Settings ──────────────────────────────────────────
    def _run(self):
        if self._thread and self._thread.is_alive():
            return
        if not self.queue_data:
            messagebox.showwarning("Empty Queue", "Add at least one entry first.", parent=self)
            return

        # reset all rows to Pending
        self._row_refs.clear()
        for i in range(len(self.queue_data)):
            vals = list(self.tree.item(str(i), "values"))
            vals[7] = "Pending"; vals[8] = ""
            self.tree.item(str(i), values=vals, tags=("Pending",))
            self.queue_data[i]["ref_ids"] = []

        self._stop_ev.clear()
        self._kill_ev.clear()
        self._q = _queue.Queue()

        try:
            settings = {"cdp_url":    self._cdp_url.get(),
                        "delay_mult": float(self._delay_mult.get())}
        except ValueError:
            settings = DEFAULT_SETTINGS.copy()

        self._thread = threading.Thread(
            target=run_automation,
            args=(copy.deepcopy(self.queue_data), settings,
                  self._q, self._stop_ev, self._kill_ev),
            daemon=True)
        self._thread.start()

        self._btn_run.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._btn_kill.config(state="normal")

    def _stop(self):
        self._stop_ev.set()
        self._log("⛔ Stop requested — finishing current copy…", "info")

    def _kill(self):
        self._kill_ev.set()
        self._log("⚡ Kill signal sent — stopping NOW.", "error")

    def _open_settings(self):
        win = tk.Toplevel(self)
        win.title("Settings")
        win.configure(bg=self.BG)
        win.resizable(False, False)
        win.grab_set()
        win.geometry("380x160")

        for r, (lbl, var) in enumerate([("CDP URL:",        self._cdp_url),
                                         ("Delay Multiplier:", self._delay_mult)]):
            tk.Label(win, text=lbl, bg=self.BG, fg=self.FG,
                     font=self.FONT).grid(row=r, column=0, padx=14, pady=12, sticky="w")
            tk.Entry(win, textvariable=var, bg=self.EBGL, fg=self.FG, font=self.FONT,
                     relief="flat", bd=4, width=28,
                     insertbackground=self.FG).grid(row=r, column=1, padx=(4,14), pady=12)

        tk.Button(win, text="Save & Close", bg=self.ACCENT, fg=self.BG,
                  font=self.FONTB, relief="flat", pady=6,
                  command=win.destroy).grid(row=2, column=0, columnspan=2,
                                            padx=14, pady=8, sticky="ew")

    # ── Queue polling (runs on UI thread via after()) ──────────────────────────
    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                t   = msg["type"]
                if   t == "log":       self._log(msg["text"], msg.get("level", "info"))
                elif t == "progress":  self._update_progress(msg["done"], msg["total"])
                elif t == "status":    self._update_status(msg["row"], msg["status"])
                elif t == "ref_id":    self._update_ref(msg["row"], msg["ref_id"])
                elif t == "done":      self._on_done()
        except _queue.Empty:
            pass
        finally:
            self.after(100, self._poll)

    # ── Log helper ────────────────────────────────────────────────────────────
    def _log(self, msg, level="info"):
        self._log_txt.config(state="normal")
        self._log_txt.insert("end", msg + "\n", level)
        self._log_txt.see("end")
        self._log_txt.config(state="disabled")

    # ── Queue message handlers ────────────────────────────────────────────────
    def _update_status(self, row, status):
        iid = str(row)
        try:
            vals    = list(self.tree.item(iid, "values"))
            vals[7] = status
            self.tree.item(iid, values=vals, tags=(status,))
        except Exception:
            pass

    def _update_ref(self, row, ref_id):
        if row not in self._row_refs:
            self._row_refs[row] = []
        self._row_refs[row].append(ref_id)
        iid = str(row)
        try:
            vals    = list(self.tree.item(iid, "values"))
            vals[8] = ", ".join(self._row_refs[row])
            self.tree.item(iid, values=vals)
        except Exception:
            pass

    def _update_progress(self, done, total):
        self._prog["maximum"] = max(total, 1)
        self._prog["value"]   = done
        self._prog_lbl.config(text=f"{done}/{total} submissions done")

    def _on_done(self):
        self._btn_run.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._btn_kill.config(state="disabled")
        self._log("\n✅ All done!", "ok")


# ── Launch ────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    App().mainloop()