"""
license_core.py — eStamp Ninja License Engine
----------------------------------------------
Handles: HWID generation, Fernet encryption, internet time, activation UI,
         anti-tamper, expiry validation.

PRIVATE — Do not distribute with client builds.
The master key below must match keygen.py exactly.
"""

import hashlib, os, platform, sys, uuid
import tkinter as tk
from datetime import date, datetime
from tkinter import messagebox

from cryptography.fernet import Fernet, InvalidToken

# ── Master Fernet key ─────────────────────────────────────────────────────────
# Generate once with:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key())"
# Paste the SAME key in keygen.py → _MASTER_KEY
_MASTER_KEY = b"jUTjIKfzKaIiZxIf5A8hD8WoIsWdDU-JtAae_zQeO04="

# ── Theme (matches app) ───────────────────────────────────────────────────────
_T = {
    "BG":     "#1e1e2e",
    "PANEL":  "#252537",
    "EBGL":   "#363656",
    "ACCENT": "#00e5a0",
    "ERR":    "#f38ba8",
    "FG":     "#cdd6f4",
    "FG2":    "#6c7086",
    "WARN":   "#f9a825",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def get_hwid() -> str:
    """Stable hardware ID: SHA-256 of UUID + hostname + processor, first 24 chars."""
    raw = f"{uuid.getnode()}{platform.node()}{platform.processor()}"
    return hashlib.sha256(raw.encode()).hexdigest()[:24].upper()


def get_lic_path() -> str:
    """License file sits next to the exe (packaged) or script (dev)."""
    base = (os.path.dirname(sys.executable)
            if getattr(sys, "frozen", False)
            else os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, ".ninja_lic")


def get_real_date() -> "date | None":
    """
    Fetch real UTC/IST date from internet time APIs.
    Returns date object, or None if both APIs fail.
    """
    import urllib.request, json as _json

    endpoints = [
        (
            "http://worldtimeapi.org/api/ip",
            lambda d: datetime.fromisoformat(d["datetime"]).date(),
        ),
        (
            "http://timeapi.io/api/time/current/zone?timeZone=Asia/Kolkata",
            lambda d: datetime.fromisoformat(
                d["dateTime"].split(".")[0].replace("Z", "")
            ).date(),
        ),
    ]
    for url, parser in endpoints:
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                return parser(_json.loads(r.read()))
        except Exception:
            continue
    return None


def decrypt_token(token_str: str) -> dict:
    """Decrypt license token → dict with keys: HWID, EXPIRY, CREATED, ACTIVATION."""
    f = Fernet(_MASTER_KEY)
    raw = f.decrypt(token_str.strip().encode()).decode()
    return dict(item.split(":", 1) for item in raw.split("|"))


def encrypt_and_save(hwid: str, expiry_str: str,
                     created_str: str, activation_str: str) -> None:
    """Write activated .ninja_lic to disk."""
    f = Fernet(_MASTER_KEY)
    payload = (f"HWID:{hwid}|EXPIRY:{expiry_str}"
               f"|CREATED:{created_str}|ACTIVATION:{activation_str}")
    with open(get_lic_path(), "w") as fh:
        fh.write(f.encrypt(payload.encode()).decode())


# ─────────────────────────────────────────────────────────────────────────────
# Error dialogs (standalone Tk windows — app not yet started)
# ─────────────────────────────────────────────────────────────────────────────

def _fatal(title: str, msg: str) -> None:
    r = tk.Tk(); r.withdraw()
    messagebox.showerror(title, msg, parent=r)
    r.destroy()
    sys.exit(1)


def internet_error_and_exit():
    _fatal(
        "Internet Required",
        "Internet connection is required to verify your license.\n\n"
        "Please reconnect and try again.",
    )


def tamper_error_and_exit():
    try:
        os.remove(get_lic_path())
    except Exception:
        pass
    _fatal(
        "Tampered License Detected",
        "A tampered or restored license file was detected and removed.\n\n"
        "Please contact VYRON support to obtain a new key.",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Activation UI
# ─────────────────────────────────────────────────────────────────────────────

def show_activation_ui(hwid: str, prefill: str = "",
                       error: str = "") -> tuple:
    """
    Blocking activation window.
    Returns ("activate", key_str) or ("exit",).
    """
    result = [("exit",)]

    root = tk.Tk()
    root.title("eStamp Ninja — Activation")
    root.configure(bg=_T["BG"])
    root.resizable(False, False)
    W, H = 520, 360
    root.update_idletasks()
    x = (root.winfo_screenwidth()  - W) // 2
    y = (root.winfo_screenheight() - H) // 2
    root.geometry(f"{W}x{H}+{x}+{y}")
    root.protocol("WM_DELETE_WINDOW", lambda: (result.__setitem__(0, ("exit",)), root.destroy()))

    # ── Header ────────────────────────────────────────────────────────────────
    tk.Label(root, text="🥷 eStamp Ninja", bg=_T["BG"], fg=_T["ACCENT"],
             font=("Segoe UI", 15, "bold")).pack(pady=(22, 2))
    tk.Label(root, text="License Activation Required", bg=_T["BG"], fg=_T["FG2"],
             font=("Segoe UI", 9)).pack()
    tk.Frame(root, bg=_T["EBGL"], height=1).pack(fill="x", pady=(12, 0))

    body = tk.Frame(root, bg=_T["BG"])
    body.pack(padx=30, fill="x", pady=10)

    # Machine ID
    tk.Label(body, text="Your Machine ID  (send this to get your key):",
             bg=_T["BG"], fg=_T["FG2"], font=("Segoe UI", 8)).pack(anchor="w")

    id_row = tk.Frame(body, bg=_T["EBGL"], padx=8, pady=6)
    id_row.pack(fill="x", pady=(3, 14))

    tk.Label(id_row, text=hwid, bg=_T["EBGL"], fg=_T["ACCENT"],
             font=("Courier", 12, "bold")).pack(side="left")

    def _copy():
        root.clipboard_clear(); root.clipboard_append(hwid)
        copy_lbl.config(text="Copied ✓")
        root.after(1500, lambda: copy_lbl.config(text="Copy"))

    copy_lbl = tk.Label(id_row, text="Copy", bg=_T["ACCENT"], fg=_T["BG"],
                        font=("Segoe UI", 7, "bold"), cursor="hand2", padx=6, pady=2)
    copy_lbl.pack(side="right")
    copy_lbl.bind("<Button-1>", lambda e: _copy())

    # Key entry
    tk.Label(body, text="License Key:", bg=_T["BG"], fg=_T["FG2"],
             font=("Segoe UI", 8)).pack(anchor="w")
    key_var = tk.StringVar(value=prefill)
    key_ent = tk.Entry(body, textvariable=key_var, bg=_T["EBGL"], fg=_T["FG"],
                       font=("Consolas", 8), relief="flat", bd=4,
                       insertbackground=_T["FG"], width=62)
    key_ent.pack(fill="x", pady=(3, 4))
    key_ent.focus_set()

    # Status
    status_var = tk.StringVar(value=error)
    tk.Label(body, textvariable=status_var, bg=_T["BG"], fg=_T["ERR"],
             font=("Segoe UI", 8), wraplength=456, justify="left").pack(anchor="w")

    # Buttons
    btn_row = tk.Frame(root, bg=_T["BG"])
    btn_row.pack(padx=30, fill="x", pady=(4, 20))

    def _activate(event=None):
        k = key_var.get().strip()
        if not k:
            status_var.set("⚠  Please paste your license key.")
            return
        result[0] = ("activate", k)
        root.destroy()

    key_ent.bind("<Return>", _activate)

    tk.Button(btn_row, text="✓  Activate", command=_activate,
              bg=_T["ACCENT"], fg=_T["BG"], font=("Segoe UI", 9, "bold"),
              relief="flat", cursor="hand2", padx=18, pady=6).pack(side="left", padx=(0, 8))
    tk.Button(btn_row, text="Exit", command=root.destroy,
              bg=_T["PANEL"], fg=_T["FG2"], font=("Segoe UI", 9),
              relief="flat", cursor="hand2", padx=18, pady=6).pack(side="left")

    root.mainloop()
    return result[0]
