#!/usr/bin/env python3
"""
keygen.py — eStamp Ninja License Key Generator
================================================
PRIVATE TOOL — For VYRON developer use only.
Never distribute this file with client builds.

Usage:
    py keygen.py
"""

from datetime import date, datetime
from cryptography.fernet import Fernet

# ── Master key — MUST match license_core.py → _MASTER_KEY exactly ────────────
# Generate once:  python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key())"
# Paste the output here AND in license_core.py
_MASTER_KEY = b"jUTjIKfzKaIiZxIf5A8hD8WoIsWdDU-JtAae_zQeO04="

_LOG_FILE = "clients_log.txt"


def generate_key(hwid: str, expiry_str: str) -> str:
    """
    Encrypt: HWID + EXPIRY + CREATED into a Fernet token.
    NOTE: ACTIVATION is added by the client app on first run.
    """
    f = Fernet(_MASTER_KEY)
    today = date.today().strftime("%Y%m%d")
    payload = f"HWID:{hwid.upper()}|EXPIRY:{expiry_str}|CREATED:{today}"
    return f.encrypt(payload.encode()).decode()


def _save_log(hwid: str, expiry_str: str, days: int) -> None:
    today = date.today().strftime("%Y%m%d")
    entry = f"{hwid.upper()} | {expiry_str} | {today} | {days} days\n"
    with open(_LOG_FILE, "a", encoding="utf-8") as fh:
        fh.write(entry)
    print(f"✅ Client record appended to {_LOG_FILE}")


def main() -> None:
    print("=" * 52)
    print("  🥷 eStamp Ninja — License Key Generator")
    print("     VYRON  (Not Noise. Signal)")
    print("=" * 52)
    print()

    hwid = input("Client Machine ID (HWID) : ").strip().upper()
    if not hwid:
        print("❌ Machine ID cannot be empty.")
        return

    expiry_input = input("Expiry Date (YYYYMMDD)    : ").strip()
    try:
        expiry = datetime.strptime(expiry_input, "%Y%m%d").date()
    except ValueError:
        print("❌ Invalid date. Format must be YYYYMMDD (e.g. 20250901).")
        return

    days = (expiry - date.today()).days
    if days <= 0:
        print("❌ Expiry date must be in the future.")
        return

    key = generate_key(hwid, expiry_input)

    print()
    print("─" * 52)
    print(f"  Machine ID  : {hwid}")
    print(f"  Expiry      : {expiry.strftime('%d %b %Y')}  ({days} days)")
    print(f"  Generated   : {date.today().strftime('%d %b %Y')}")
    print("─" * 52)
    print()
    print("LICENSE KEY:")
    print(key)
    print()

    _save_log(hwid, expiry_input, days)

    # Also save key to a text file for easy copy-paste
    out_file = f"key_{hwid[:8]}_{expiry_input}.txt"
    with open(out_file, "w") as fh:
        fh.write(key)
    print(f"✅ Key also saved to: {out_file}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
    input("\nPress Enter to exit...")
