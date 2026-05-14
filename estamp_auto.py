#!/usr/bin/env python3
"""
estamp_auto.py — Smart eStamp Bot  (entry point)
Run with: py estamp_auto.py

Project structure:
  config.py      — settings & constants
  automation.py  — Playwright automation engine
  ui.py          — Tkinter GUI (App class)
  estamp_auto.py — this file (launch only)
"""
import subprocess, sys


def ensure_playwright():
    """
    Check that playwright and its chromium browser are available.
    If not, install them and notify the user via stdout.

    Works in both dev mode (Python) and as a PyInstaller .exe bundle.
    """
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            p.chromium.executable_path   # raises if chromium not installed
        return   # all good — silent pass
    except Exception:
        pass     # fall through to install

    print("⏳ First time setup in progress...")
    print("   Installing Chromium browser — please wait 2-3 minutes")

    if getattr(sys, "frozen", False):
        # ── Running as PyInstaller .exe ──────────────────────────────────────
        # playwright Python package IS bundled; only the browser binary is missing.
        # Call playwright's own CLI entry-point directly — no pip/Python needed.
        try:
            from playwright.__main__ import main as _pw_main
            _old_argv = sys.argv[:]
            sys.argv = ["playwright", "install", "chromium"]
            try:
                _pw_main()
            except SystemExit:
                pass        # playwright exits with 0 on success; swallow it
            finally:
                sys.argv = _old_argv
        except Exception as exc:
            print(f"⚠️  Auto-install failed: {exc}")
            print("   Please run manually: playwright install chromium")
            return
    else:
        # ── Running in dev mode with Python ──────────────────────────────────
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "playwright"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        subprocess.run(
            [sys.executable, "-m", "playwright", "install", "chromium"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )

    print("✅ Setup complete! Starting app...")




from ui import App

# ── License state (set by check_license, read by __main__) ───────────────────
_LICENSE_DAYS_LEFT: "int | None" = None


def check_license() -> None:
    """
    Full license validation. Blocks until:
      - Valid license confirmed (sets _LICENSE_DAYS_LEFT, returns), or
      - User exits / fatal error (sys.exit).

    Call AFTER ensure_playwright(), BEFORE App().
    """
    global _LICENSE_DAYS_LEFT
    from license_core import (
        get_hwid, get_lic_path, get_real_date,
        decrypt_token, encrypt_and_save,
        show_activation_ui,
        internet_error_and_exit, tamper_error_and_exit,
        InvalidToken,
    )
    from datetime import datetime
    import os, tkinter as tk
    from tkinter import messagebox

    hwid     = get_hwid()
    lic_path = get_lic_path()

    # ── Try loading existing license ──────────────────────────────────────────
    existing = None
    if os.path.exists(lic_path):
        try:
            with open(lic_path) as fh:
                existing = decrypt_token(fh.read())
        except Exception:
            existing = None            # corrupt → treat as no license

    # ── No valid license on disk → activation loop ───────────────────────────
    if existing is None:
        prefill, err = "", ""
        while True:
            action = show_activation_ui(hwid, prefill=prefill, error=err)
            if action[0] == "exit":
                sys.exit(0)

            key_str = action[1]
            try:
                data = decrypt_token(key_str)
            except InvalidToken:
                prefill, err = key_str, "❌ Invalid license key — please check and try again."
                continue
            except Exception:
                prefill, err = key_str, "❌ Corrupt license key."
                continue

            if data.get("HWID", "").upper() != hwid:
                prefill = key_str
                err = (f"❌ This key was issued for a different machine.\n"
                       f"   Your Machine ID: {hwid}")
                continue

            real_date = get_real_date()
            if real_date is None:
                internet_error_and_exit()

            expiry = datetime.strptime(data["EXPIRY"], "%Y%m%d").date()
            if real_date > expiry:
                prefill = key_str
                err = f"❌ Key expired on {expiry.strftime('%d %b %Y')}."
                continue

            act_str = real_date.strftime("%Y%m%d")
            encrypt_and_save(hwid, data["EXPIRY"],
                             data.get("CREATED", act_str), act_str)
            days_left = (expiry - real_date).days
            _LICENSE_DAYS_LEFT = days_left

            r = tk.Tk(); r.withdraw()
            messagebox.showinfo(
                "Activated!",
                f"✅ License activated successfully!\n\n{days_left} days remaining.",
                parent=r)
            r.destroy()
            return

    # ── Existing license — validate ───────────────────────────────────────────
    data = existing

    # 1. HWID mismatch
    if data.get("HWID", "").upper() != hwid:
        os.remove(lic_path)
        action = show_activation_ui(
            hwid, error="❌ License is bound to a different machine.")
        if action[0] == "exit":
            sys.exit(0)
        check_license(); return          # restart flow with clean state

    # 2. Internet time (mandatory — never trust system clock)
    real_date = get_real_date()
    if real_date is None:
        internet_error_and_exit()

    # 3. Anti-tamper: real_time must be ≥ activation_date
    act_str = data.get("ACTIVATION", "")
    if act_str:
        try:
            if real_date < datetime.strptime(act_str, "%Y%m%d").date():
                tamper_error_and_exit()
        except ValueError:
            tamper_error_and_exit()

    # 4. Expiry check
    expiry    = datetime.strptime(data["EXPIRY"], "%Y%m%d").date()
    days_left = (expiry - real_date).days

    if days_left < 0:
        os.remove(lic_path)
        action = show_activation_ui(
            hwid,
            error=f"❌ License expired on {expiry.strftime('%d %b %Y')}. "
                  f"Contact VYRON for renewal.")
        if action[0] == "exit":
            sys.exit(0)
        check_license(); return

    _LICENSE_DAYS_LEFT = days_left


if __name__ == "__main__":
    ensure_playwright()   # must be first
    check_license()       # blocks until licensed or exit

    app = App()

    # Update title bar with license countdown
    if _LICENSE_DAYS_LEFT is not None:
        if _LICENSE_DAYS_LEFT > 7:
            app.title(f"eStamp Ninja 🥷 | License: {_LICENSE_DAYS_LEFT} days left")
        else:
            app.title(f"eStamp Ninja 🥷 | ⚠️ {_LICENSE_DAYS_LEFT} days left — Renew Now")

    app.mainloop()