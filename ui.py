"""
ui.py — Smart eStamp Bot
Grid-aligned inline table. Fields clearly visible. Status hidden until run.
"""
import threading, queue as _queue, copy as _copy, json, os
import tkinter as tk
from tkinter import ttk, messagebox
from config import DEFAULT_SETTINGS
from automation import run_automation

# ── Column definitions: (header, min_px, var_key or None) ────────────────────
GCOLS = [
    ("#",             28, None),
    ("Article",      112, "v_art"),
    ("First Party",  120, "v_fp"),
    ("Second Party", 120, "v_sp"),
    ("By",            48, "v_pb"),
    ("Amt",           44, "v_amt"),
    ("Cps",           44, "v_cop"),
]
# Per-field Entry width overrides (in characters)
_ENTRY_W = {"v_amt": 4, "v_cop": 4}
# Per-field text justification overrides
_ENTRY_J = {"v_amt": "center", "v_cop": "center"}
ACT_COL = len(GCOLS)   # index of Actions/Status column


class App(tk.Tk):
    BG    = "#1e1e2e"
    PANEL = "#252537"
    EBGL  = "#2d2d45"
    FG    = "#e0e0e0"
    FG2   = "#666688"
    ACCENT= "#4ecca3"
    WARN  = "#fdcb6e"
    ERR   = "#ff6b6b"
    BLUE  = "#74b9ff"
    SEL   = "#3a3a5c"
    FONT  = ("Segoe UI", 9)
    FONTB = ("Segoe UI", 9, "bold")
    FONTS = ("Segoe UI", 8)
    STC   = {"Pending":"#e0e0e0","Running":"#74b9ff","Done":"#4ecca3","Error":"#ff6b6b"}

    def __init__(self):
        super().__init__()
        self.title("eStamp Ninja")
        self.configure(bg=self.BG)
        self.resizable(True, True)
        self.minsize(740, 440)
        self.maxsize(1440, 960)
        self.geometry("900x580")
        try:
            import sys
            _base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
            _icon = tk.PhotoImage(file=os.path.join(_base, "icon.png"))
            self.iconphoto(True, _icon)
            self._icon_ref = _icon   # prevent GC
        except Exception:
            pass

        self._q         = _queue.Queue()
        self._stop_ev   = threading.Event()
        self._kill_ev   = threading.Event()
        self._thread    = None
        self._row_refs  = {}
        self.queue_data = []

        self._cdp_url    = tk.StringVar(value=DEFAULT_SETTINGS["cdp_url"])
        self._delay_mult = tk.StringVar(value=str(DEFAULT_SETTINGS["delay_mult"]))
        self._fast_fill  = tk.BooleanVar(value=DEFAULT_SETTINGS["fast_fill"])
        self._mob        = tk.StringVar()
        self._load_settings()   # populate _mob from saved settings

        self._apply_style()
        self._build_header()

        # Pack fixed-height bottom sections FIRST so they anchor to the bottom.
        # The queue (expand=True) then fills only the remaining middle space.
        self._build_stats_bar()
        self._build_log_panel()

        qf = tk.Frame(self, bg=self.BG)
        qf.pack(fill="both", expand=True, padx=6, pady=(4, 0))
        self._build_queue_panel(qf)

        self._logo_img  = self._load_logo()   # preload once
        self._empty_lbl = None
        self._update_empty_state()            # show logo on startup

        self._log("Smart eStamp Bot ready.", "ok")
        self._log("  Chrome: --remote-debugging-port=9222", "info")
        self._log("  Login → shcilestamp.com, then ▶ Run", "info")
        self.after(100, self._poll)

    # ── Styles ────────────────────────────────────────────────────────────────
    def _apply_style(self):
        s = ttk.Style(self)
        s.theme_use("clam")
        s.configure("TScrollbar", background=self.PANEL, troughcolor=self.BG,
                    borderwidth=0, arrowsize=12)
        s.configure("Green.Horizontal.TProgressbar",
                    troughcolor=self.EBGL, background=self.ACCENT, thickness=8)
        s.configure("TCombobox", fieldbackground=self.EBGL, background=self.EBGL,
                    foreground=self.FG, selectbackground=self.SEL, arrowcolor=self.FG)
        s.map("TCombobox", fieldbackground=[("readonly", self.EBGL)],
              foreground=[("readonly", self.FG)])
        self.option_add("*TCombobox*Listbox.background", self.EBGL)
        self.option_add("*TCombobox*Listbox.foreground", self.FG)
        self.option_add("*TCombobox*Listbox.selectBackground", self.SEL)

    # ── Persistent settings ───────────────────────────────────────────────────
    _SETTINGS_DIR  = os.path.join(os.path.expanduser("~"), ".estamp_ninja")
    _SETTINGS_PATH = os.path.join(_SETTINGS_DIR, "settings.json")

    def _load_settings(self):
        try:
            with open(self._SETTINGS_PATH, "r") as f:
                data = json.load(f)
            self._mob.set(data.get("mobile", ""))
        except Exception:
            pass   # first run or corrupt file — defaults apply

    def _save_settings(self):
        try:
            os.makedirs(self._SETTINGS_DIR, exist_ok=True)
            data = {"mobile": self._mob.get().strip()}
            with open(self._SETTINGS_PATH, "w") as f:
                json.dump(data, f)
        except Exception as exc:
            self._log(f"Settings save failed: {exc}", "error")

    # ── Header ────────────────────────────────────────────────────────────────
    def _build_header(self):
        hf = tk.Frame(self, bg=self.PANEL, pady=7)
        hf.pack(fill="x")

        def hbtn(text, cmd, bg, fg, state="normal"):
            b = tk.Button(hf, text=text, command=cmd, bg=bg, fg=fg,
                          font=self.FONTB, relief="flat", cursor="hand2",
                          padx=10, pady=3, bd=0, state=state)
            b.pack(side="right", padx=(0, 8))
            return b

        self._btn_set  = hbtn("⚙ Settings", self._open_settings, self.EBGL, self.FG)
        self._btn_kill = hbtn("⚡ Kill",  self._kill, self.ERR,  "#fff", "disabled")
        self._btn_stop = hbtn("⛔ Stop",  self._stop, self.WARN, self.PANEL, "disabled")
        self._btn_run  = hbtn("▶ Run",   self._run,  self.ACCENT, self.PANEL)

        # ── Mobile number widget (3 states) ──────────────────────────────────
        self._mob_frame = tk.Frame(hf, bg=self.PANEL)
        self._mob_frame.pack(side="right", padx=(0, 12))
        self._refresh_mob_widget()

    def _refresh_mob_widget(self):
        """Render the correct mobile widget state into self._mob_frame."""
        for w in self._mob_frame.winfo_children():
            w.destroy()
        number = self._mob.get().strip()
        if not number:
            # ── State 1: no number saved yet ─────────────────────────────────
            btn = tk.Label(self._mob_frame, text="+ Add Mobile",
                           bg=self.PANEL, fg=self.ACCENT, font=self.FONTB,
                           cursor="hand2")
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda e: self._mob_edit_mode())
        else:
            # ── State 2: number saved, display mode ───────────────────────────
            tk.Label(self._mob_frame, text="📱", bg=self.PANEL,
                     fg=self.FG2, font=self.FONTS).pack(side="left")
            tk.Label(self._mob_frame, text=number, bg=self.PANEL,
                     fg=self.FG, font=self.FONTB).pack(side="left", padx=(2, 6))
            edit = tk.Label(self._mob_frame, text="✎", bg=self.PANEL,
                            fg=self.FG2, font=self.FONTS, cursor="hand2")
            edit.pack(side="left")
            edit.bind("<Button-1>", lambda e: self._mob_edit_mode())

    def _mob_edit_mode(self):
        """Inline edit mode — show Entry + Save/Cancel inside mob_frame."""
        for w in self._mob_frame.winfo_children():
            w.destroy()
        _tmp = tk.StringVar(value=self._mob.get())
        entry = tk.Entry(self._mob_frame, textvariable=_tmp, width=12,
                         bg=self.EBGL, fg=self.FG, font=self.FONT,
                         relief="flat", bd=2, insertbackground=self.FG,
                         highlightthickness=1, highlightbackground=self.SEL,
                         highlightcolor=self.ACCENT)
        entry.pack(side="left", padx=(0, 4))
        entry.focus_set()
        entry.select_range(0, tk.END)

        def _save(event=None):
            self._mob.set(_tmp.get().strip())
            self._save_settings()
            self._refresh_mob_widget()

        def _cancel(event=None):
            self._refresh_mob_widget()

        entry.bind("<Return>", _save)
        entry.bind("<Escape>", _cancel)
        tk.Button(self._mob_frame, text="Save", command=_save,
                  bg=self.ACCENT, fg=self.PANEL, font=self.FONTS,
                  relief="flat", cursor="hand2", padx=6, pady=1
                  ).pack(side="left", padx=(0, 3))
        tk.Button(self._mob_frame, text="✕", command=_cancel,
                  bg=self.ERR, fg="#fff", font=self.FONTS,
                  relief="flat", cursor="hand2", padx=4, pady=1
                  ).pack(side="left")

    # ── Queue panel ───────────────────────────────────────────────────────────
    def _build_queue_panel(self, parent):
        # Use grid so header, canvas, and add-bar all share the same column 0
        # Scrollbar lives in column 1, spanning all rows — header aligns perfectly
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(2, weight=1)   # canvas row expands

        # --- Column header (row 0) ---
        hdr = tk.Frame(parent, bg=self.EBGL)
        hdr.grid(row=0, column=0, sticky="ew")
        for i, (htext, px, _) in enumerate(GCOLS):
            tk.Label(hdr, text=htext, bg=self.EBGL, fg=self.ACCENT,
                     font=("Segoe UI", 8, "bold"), anchor="center",
                     width=1).grid(row=0, column=i, sticky="ew",
                                   padx=3, pady=(4, 4))
            hdr.columnconfigure(i, minsize=px, weight=(1 if i in (2, 3) else 0))
        self._act_hdr_lbl = tk.Label(hdr, text="Action", bg=self.EBGL, fg=self.ACCENT,
                                     font=("Segoe UI", 8, "bold"), anchor="center",
                                     width=1)
        self._act_hdr_lbl.grid(row=0, column=ACT_COL, sticky="ew", padx=3,
                               pady=(4, 4))
        hdr.columnconfigure(ACT_COL, minsize=90)

        # --- Separator (row 1) ---
        tk.Frame(parent, bg=self.SEL, height=1).grid(row=1, column=0, sticky="ew")

        # --- Canvas (row 2, col 0) + Scrollbar (col 1, all rows) ---
        self._canvas = tk.Canvas(parent, bg=self.PANEL, highlightthickness=0, bd=0)
        vsb = ttk.Scrollbar(parent, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=vsb.set)
        self._canvas.grid(row=2, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, rowspan=4, sticky="ns")  # spans header → add-bar

        self._rows_frame = tk.Frame(self._canvas, bg=self.PANEL)
        self._rows_win = self._canvas.create_window(
            (0, 0), window=self._rows_frame, anchor="nw")

        for i, (_, px, _) in enumerate(GCOLS):
            self._rows_frame.columnconfigure(
                i, minsize=px, weight=(1 if i in (2, 3) else 0))
        self._rows_frame.columnconfigure(ACT_COL, minsize=90)

        self._rows_frame.bind("<Configure>",
            lambda e: self._canvas.configure(
                scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
            lambda e: self._canvas.itemconfig(self._rows_win, width=e.width))
        self._canvas.bind_all("<MouseWheel>",
            lambda e: self._canvas.yview_scroll(-1*(e.delta//120), "units"))

        # --- ⊕ Add Entry bar (row 3, col 0) ---
        ab = tk.Frame(parent, bg=self.PANEL, cursor="hand2")
        ab.grid(row=3, column=0, sticky="ew")
        tk.Frame(ab, bg=self.SEL, height=1).pack(fill="x")
        al = tk.Label(ab, text="  ⊕  Add Entry", bg=self.PANEL,
                      fg=self.ACCENT, font=self.FONTB, anchor="w",
                      cursor="hand2")
        al.pack(side="left", padx=4, pady=5)
        for w in (ab, al):
            w.bind("<Button-1>", lambda e: self._add_new_row())

    # ── Row operations ────────────────────────────────────────────────────────
    def _load_logo(self):
        """Load logo.png scaled to ~200px. No PIL needed — pure Tkinter."""
        try:
            import sys
            _base = getattr(sys, "_MEIPASS",
                            os.path.dirname(os.path.abspath(__file__)))
            raw = tk.PhotoImage(file=os.path.join(_base, "logo.png"))
            factor = max(1, raw.width() // 200)
            return raw.subsample(factor, factor)
        except Exception:
            return None

    def _update_empty_state(self):
        """Show branded logo when queue is empty; remove it when entries exist."""
        if not self.queue_data:
            if self._empty_lbl is None:
                if self._logo_img:
                    self._empty_lbl = tk.Label(
                        self._rows_frame, image=self._logo_img,
                        bg=self.PANEL)
                else:
                    self._empty_lbl = tk.Label(
                        self._rows_frame,
                        text="No entries yet\nClick \u2295 Add Entry to begin",
                        bg=self.PANEL, fg=self.FG2,
                        font=("Segoe UI", 11), justify="center")
                self._empty_lbl.grid(
                    row=0, column=0, columnspan=ACT_COL + 1, pady=40)
        else:
            if self._empty_lbl is not None:
                try:
                    self._empty_lbl.destroy()
                except Exception:
                    pass
                self._empty_lbl = None

    def _new_row_data(self):
        return {
            "v_art":    tk.StringVar(),
            "v_fp":     tk.StringVar(),
            "v_sp":     tk.StringVar(),
            "v_pb":     tk.StringVar(value="FP"),
            "v_amt":    tk.StringVar(),
            "v_cop":    tk.StringVar(value="1"),
            "v_status": tk.StringVar(value=""),
            "entries":  [],
            "act_frame": None,
            "ref_ids":  [],
        }

    def _rebuild_all_rows(self):
        """Clear and re-render all rows from queue_data."""
        self._empty_lbl = None   # widgets destroyed below
        for w in self._rows_frame.winfo_children():
            w.destroy()
        for rd in self.queue_data:
            rd["entries"]   = []
            rd["act_frame"] = None
        for i, rd in enumerate(self.queue_data):
            self._render_row(rd, i)
        self._update_empty_state()
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _render_row(self, rd, idx):
        """Place one row into _rows_frame at grid row=idx."""
        g = idx   # grid row index

        ekw = dict(bg="#363656", fg=self.FG, font=self.FONT,
                   relief="flat", bd=0, insertbackground=self.FG,
                   highlightthickness=1, highlightbackground="#3a3a5c",
                   highlightcolor=self.ACCENT)

        # Row number
        tk.Label(self._rows_frame, text=str(idx + 1), bg=self.PANEL,
                 fg=self.FG2, font=self.FONTS, anchor="center"
                 ).grid(row=g, column=0, sticky="ew", padx=3, pady=3)

        # Editable fields
        for col_i, (_, _, vkey) in enumerate(GCOLS[1:], start=1):
            if vkey == "v_pb":
                cb = ttk.Combobox(self._rows_frame, textvariable=rd["v_pb"],
                                  values=["FP", "SP"], state="readonly",
                                  font=self.FONTS, width=4)
                cb.grid(row=g, column=col_i, sticky="ew", padx=3, pady=3)
                rd["entries"].append(cb)
            else:
                w = _ENTRY_W.get(vkey)
                j = _ENTRY_J.get(vkey, "left")
                e = tk.Entry(self._rows_frame, textvariable=rd[vkey],
                             justify=j, **(dict(width=w, **ekw) if w else ekw))
                e.grid(row=g, column=col_i, sticky="ew", padx=3, pady=3)
                rd["entries"].append(e)

        # Actions / Status cell
        af = tk.Frame(self._rows_frame, bg=self.PANEL)
        af.grid(row=g, column=ACT_COL, sticky="ew", padx=3, pady=3)
        rd["act_frame"] = af
        self._build_act_idle(rd, idx, af)

    def _build_act_idle(self, rd, idx, af):
        """Actions column — idle state: ✓ Done  ×."""
        for w in af.winfo_children():
            w.destroy()
        tk.Button(af, text="✓", command=lambda: self._confirm_row(rd, idx, af),
                  bg=self.ACCENT, fg=self.PANEL, font=self.FONTB,
                  relief="flat", cursor="hand2", padx=6, pady=1
                  ).pack(side="left", padx=(0, 3))
        tk.Button(af, text="✕", command=lambda i=idx: self._delete_row(i),
                  bg=self.ERR, fg="#fff", font=self.FONTB,
                  relief="flat", cursor="hand2", padx=6, pady=1
                  ).pack(side="left")

    def _confirm_row(self, rd, idx, af):
        """✓ clicked: briefly validate and mark row as confirmed."""
        art = rd["v_art"].get().strip()
        fp  = rd["v_fp"].get().strip()
        amt = rd["v_amt"].get().strip()
        if not art or not fp or not amt.isdigit():
            messagebox.showerror(
                "Incomplete",
                f"Row {idx+1}: Article, First Party and Amount are required.",
                parent=self)
            return
        # Visual confirmation — ✓ turns green/disabled
        for w in af.winfo_children():
            w.destroy()
        tk.Label(af, text="✓ Ready", bg=self.PANEL, fg=self.ACCENT,
                 font=self.FONTB).pack(side="left", padx=(0, 4))
        tk.Button(af, text="✕", command=lambda i=idx: self._delete_row(i),
                  bg=self.ERR, fg="#fff", font=self.FONTB,
                  relief="flat", cursor="hand2", padx=6, pady=1
                  ).pack(side="left")

    def _show_act_status(self, rd, af):
        """During run: replace actions with live status label."""
        for w in af.winfo_children():
            w.destroy()
        lbl = tk.Label(af, textvariable=rd["v_status"], bg=self.PANEL,
                       fg=self.FG2, font=self.FONTB, anchor="w")
        lbl.pack(fill="x")
        rd["v_status"].trace_add("write",
            lambda *a, l=lbl, v=rd["v_status"]:
                l.config(fg=self.STC.get(v.get(), self.FG)))

    def _add_new_row(self):
        if self._running():
            return
        rd = self._new_row_data()
        self.queue_data.append(rd)
        self._update_empty_state()   # hides logo before rendering first row
        self._render_row(rd, len(self.queue_data) - 1)
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _delete_row(self, idx):
        if self._running():
            messagebox.showwarning("Running", "Cannot delete while running.", parent=self)
            return
        self.queue_data.pop(idx)
        self._row_refs = {(k if k < idx else k - 1): v
                          for k, v in self._row_refs.items() if k != idx}
        self._rebuild_all_rows()

    def _running(self):
        return bool(self._thread and self._thread.is_alive())

    # ── Run / Stop / Kill ─────────────────────────────────────────────────────
    def _run(self):
        if self._running():
            return
        if not self.queue_data:
            messagebox.showwarning("Empty", "Add at least one entry.", parent=self)
            return
        mob = self._mob.get().strip()
        if not mob.isdigit() or len(mob) != 10:
            messagebox.showerror("Mobile", "Enter a valid 10-digit mobile number.",
                                 parent=self)
            return

        data = []
        for i, rd in enumerate(self.queue_data):
            art = rd["v_art"].get().strip()
            fp  = rd["v_fp"].get().strip()
            sp  = rd["v_sp"].get().strip()
            pb  = "FIRST PARTY" if rd["v_pb"].get() == "FP" else "SECOND PARTY"
            amt = rd["v_amt"].get().strip()
            cop = rd["v_cop"].get().strip()
            if not art or not fp or not amt.isdigit():
                messagebox.showerror("Validation",
                    f"Row {i+1}: Article, First Party and Amount are required.",
                    parent=self)
                return
            try: copies = max(1, int(cop))
            except ValueError: copies = 1
            data.append({
                "article_search": art, "first_party": fp, "second_party": sp,
                "purchased_by": pb, "stamp_duty_amount": amt,
                "mobile_number": mob, "copies": copies, "ref_ids": [],
            })
            rd["v_status"].set("Pending")
            rd["ref_ids"] = []
            # Switch actions column to status display
            if rd["act_frame"]:
                self._show_act_status(rd, rd["act_frame"])

        self._row_refs.clear()
        self._stop_ev.clear()
        self._kill_ev.clear()
        self._q = _queue.Queue()
        try:
            settings = {"cdp_url":    self._cdp_url.get(),
                        "delay_mult": float(self._delay_mult.get()),
                        "fast_fill":  self._fast_fill.get()}
        except ValueError:
            settings = DEFAULT_SETTINGS.copy()

        self._thread = threading.Thread(
            target=run_automation,
            args=(_copy.deepcopy(data), settings,
                  self._q, self._stop_ev, self._kill_ev),
            daemon=True)
        self._thread.start()
        self._btn_run.config(state="disabled")
        self._btn_stop.config(state="normal")
        self._btn_kill.config(state="normal")
        self._set_inputs_state("disabled")
        self._act_hdr_lbl.config(text="Status")

    def _set_inputs_state(self, state):
        for rd in self.queue_data:
            for w in rd.get("entries", []):
                try: w.config(state=state)
                except Exception: pass
        try: self._mob_entry.config(state=state)
        except Exception: pass

    def _stop(self):
        self._stop_ev.set()
        self._log("⛔ Stop requested…", "info")

    def _kill(self):
        self._kill_ev.set()
        self._log("⚡ Kill signal sent.", "error")

    # ── Settings ──────────────────────────────────────────────────────────────
    def _open_settings(self):
        win = tk.Toplevel(self); win.title("Settings")
        win.configure(bg=self.BG); win.resizable(False, False)
        win.grab_set(); win.geometry("400x200")
        for r, (lbl, var) in enumerate([("CDP URL:", self._cdp_url),
                                         ("Delay Multiplier:", self._delay_mult)]):
            tk.Label(win, text=lbl, bg=self.BG, fg=self.FG,
                     font=self.FONT).grid(row=r, column=0, padx=14, pady=10, sticky="w")
            tk.Entry(win, textvariable=var, bg=self.EBGL, fg=self.FG, font=self.FONT,
                     relief="flat", bd=4, width=28, insertbackground=self.FG
                     ).grid(row=r, column=1, padx=(4, 14), pady=10)
        tk.Label(win, text="Fast Fill:", bg=self.BG, fg=self.FG,
                 font=self.FONT).grid(row=2, column=0, padx=14, pady=10, sticky="w")
        ff = tk.Frame(win, bg=self.BG); ff.grid(row=2, column=1, sticky="w", padx=(4, 14))
        tk.Checkbutton(ff, variable=self._fast_fill, bg=self.BG, fg=self.FG,
                       activebackground=self.BG, selectcolor=self.EBGL, font=self.FONT,
                       text="25ms/char (faster, same events fired)").pack(side="left")
        tk.Button(win, text="Save & Close", bg=self.ACCENT, fg=self.BG,
                  font=self.FONTB, relief="flat", pady=6,
                  command=win.destroy).grid(row=3, column=0, columnspan=2,
                                            padx=14, pady=10, sticky="ew")

    # ── Log strip ─────────────────────────────────────────────────────────────
    def _build_log_panel(self):
        outer = tk.Frame(self, bg=self.PANEL)
        outer.pack(fill="x", padx=6, pady=(0, 0), side="bottom")
        hdr = tk.Frame(outer, bg=self.PANEL)
        hdr.pack(fill="x", padx=4, pady=(4, 2))
        tk.Label(hdr, text="Live Log", bg=self.PANEL, fg=self.FG2,
                 font=self.FONTS).pack(side="left", padx=(2, 8))
        self._prog_lbl = tk.Label(hdr, text="0/0 done", bg=self.PANEL,
                                  fg=self.FG2, font=self.FONTS)
        self._prog_lbl.pack(side="right", padx=4)
        self._prog = ttk.Progressbar(hdr, style="Green.Horizontal.TProgressbar",
                                     orient="horizontal", mode="determinate", length=180)
        self._prog.pack(side="right", padx=(0, 8))
        tf = tk.Frame(outer, bg=self.BG)
        tf.pack(fill="x", padx=4, pady=(0, 4))
        self._log_txt = tk.Text(tf, bg="#12121e", fg=self.FG,
                                font=("Consolas", 8), state="disabled",
                                relief="flat", wrap="word", bd=0, height=5)
        self._log_txt.tag_configure("ok",    foreground=self.ACCENT)
        self._log_txt.tag_configure("error", foreground=self.ERR)
        self._log_txt.tag_configure("info",  foreground="#cdd6f4")
        vsb = ttk.Scrollbar(tf, orient="vertical", command=self._log_txt.yview)
        self._log_txt.configure(yscrollcommand=vsb.set)
        self._log_txt.pack(side="left", fill="x", expand=True)
        vsb.pack(side="left", fill="y")

    # ── Stats bar ─────────────────────────────────────────────────────────────
    def _build_stats_bar(self):
        sf = tk.Frame(self, bg=self.PANEL, pady=4)
        sf.pack(fill="x", side="bottom")
        for label, color, attr in [
            ("📊 Processed", "#c0c0d0", "_stat_total"),
            ("✅ Success",   self.ACCENT, "_stat_ok"),
            ("❌ Failed",    self.ERR,   "_stat_fail"),
            ("⏳ Remaining", self.BLUE,  "_stat_rem"),
        ]:
            cell = tk.Frame(sf, bg=self.PANEL, padx=14)
            cell.pack(side="left")
            tk.Label(cell, text=label, bg=self.PANEL, fg=self.FG2,
                     font=self.FONTS).pack(side="left")
            lbl = tk.Label(cell, text=" 0", bg=self.PANEL, fg=color,
                           font=("Segoe UI", 10, "bold"))
            lbl.pack(side="left")
            setattr(self, attr, lbl)

        # ── Right: developer credit ────────────────────────────────────────────
        brand = tk.Frame(sf, bg=self.PANEL)
        brand.pack(side="right", padx=12)

        tk.Label(brand, text="Developed by", bg=self.PANEL, fg=self.FG2,
                 font=self.FONTS).pack(side="left", padx=(0, 4))
        tk.Label(brand, text="VYRON", bg=self.PANEL, fg=self.ACCENT,
                 font=("Segoe UI", 8, "bold")).pack(side="left")

        info_btn = tk.Label(brand, text=" ⓘ", bg=self.PANEL, fg=self.FG2,
                            font=("Segoe UI", 10), cursor="hand2")
        info_btn.pack(side="left", padx=(2, 0))

        self._tip_win = None

        _INFO = [
            ("Developed by",   "VYRON  (Not Noise. Signal)"),
            ("Developer",      "Deepak Chaudhary"),
            ("Mob / WhatsApp", "7011123497"),
            ("Email",          "contactdeepak25@gmail.com"),
        ]

        def _show_tip(event):
            if self._tip_win:
                return
            tw = tk.Toplevel(self)
            self._tip_win = tw
            tw.wm_overrideredirect(True)
            tw.configure(bg=self.EBGL)
            tw.attributes("-topmost", True)
            for r, (k, v) in enumerate(_INFO):
                tk.Label(tw, text=k + " :", bg=self.EBGL, fg=self.FG2,
                         font=self.FONTS, anchor="e", width=14
                         ).grid(row=r, column=0, sticky="e", padx=(10, 2), pady=3)
                tk.Label(tw, text=v, bg=self.EBGL, fg=self.FG,
                         font=("Segoe UI", 8, "bold"), anchor="w"
                         ).grid(row=r, column=1, sticky="w", padx=(0, 14), pady=3)
            tw.update_idletasks()
            x = event.widget.winfo_rootx() - tw.winfo_width() + 24
            y = event.widget.winfo_rooty() - tw.winfo_height() - 8
            tw.geometry(f"+{x}+{y}")

        def _hide_tip(event=None):
            if self._tip_win:
                self._tip_win.destroy()
                self._tip_win = None

        def _open_about(event=None):
            _hide_tip()
            win = tk.Toplevel(self)
            win.title("About — eStamp Ninja")
            win.configure(bg=self.BG)
            win.resizable(False, False)
            win.grab_set()
            win.geometry("380x210")
            for r, (k, v) in enumerate(_INFO):
                tk.Label(win, text=k + " :", bg=self.BG, fg=self.FG2,
                         font=self.FONTS, anchor="e", width=16
                         ).grid(row=r, column=0, sticky="e", padx=(16, 4), pady=8)
                tk.Label(win, text=v, bg=self.BG, fg=self.FG,
                         font=("Segoe UI", 9, "bold"), anchor="w"
                         ).grid(row=r, column=1, sticky="w", padx=(0, 16), pady=8)
            tk.Button(win, text="Close", bg=self.ACCENT, fg=self.BG,
                      font=self.FONTB, relief="flat", pady=5, cursor="hand2",
                      command=win.destroy
                      ).grid(row=len(_INFO), column=0, columnspan=2,
                             padx=16, pady=(4, 14), sticky="ew")

        info_btn.bind("<Enter>",    _show_tip)
        info_btn.bind("<Leave>",    _hide_tip)
        info_btn.bind("<Button-1>", _open_about)

    # ── Queue poll ────────────────────────────────────────────────────────────
    def _poll(self):
        try:
            while True:
                msg = self._q.get_nowait()
                t = msg["type"]
                if   t == "log":      self._log(msg["text"], msg.get("level","info"))
                elif t == "progress": self._update_progress(
                    msg["done"], msg["total"],
                    msg.get("success",0), msg.get("failed",0))
                elif t == "status":   self._update_status(msg["row"], msg["status"])
                elif t == "ref_id":   self._update_ref(
                    msg["row"], msg["ref_id"], msg.get("label"))
                elif t == "done":     self._on_done()
        except _queue.Empty:
            pass
        finally:
            self.after(100, self._poll)

    def _log(self, msg, level="info"):
        self._log_txt.config(state="normal")
        self._log_txt.insert("end", msg + "\n", level)
        self._log_txt.see("end")
        self._log_txt.config(state="disabled")

    def _update_status(self, row, status):
        try: self.queue_data[row]["v_status"].set(status)
        except Exception: pass

    def _update_ref(self, row, ref_id, label=None):
        if row not in self._row_refs:
            self._row_refs[row] = []
        if not label:
            label = f"E{row+1}_{len(self._row_refs[row])+1}"
        self._row_refs[row].append(label)

    def _update_progress(self, done, total, success=0, failed=0):
        self._prog["maximum"] = max(total, 1)
        self._prog["value"]   = done
        self._prog_lbl.config(text=f"{done}/{total} done")
        self._stat_total.config(text=f" {done}/{total}")
        self._stat_ok.config(text=f" {success}")
        self._stat_fail.config(text=f" {failed}")
        self._stat_rem.config(text=f" {max(total - done, 0)}")

    def _on_done(self):
        self._btn_run.config(state="normal")
        self._btn_stop.config(state="disabled")
        self._btn_kill.config(state="disabled")
        self._set_inputs_state("normal")
        self._act_hdr_lbl.config(text="Action")
        self._log("\n✅ All done!", "ok")
