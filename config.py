"""
config.py — Smart eStamp Bot
Global settings and constants. Import this everywhere instead of hard-coding values.
"""

# ── Default runtime settings ──────────────────────────────────────────────────
DEFAULT_SETTINGS = {
    "cdp_url"    : "http://localhost:9222",
    "delay_mult" : 1.0,    # scales ws() between-step waits ONLY
    "fast_fill"  : True,   # True  = 25ms/char (3-4× faster, all keyboard events fired)
                           # False = type_like_human() 50-120ms/char (maximum stealth)
}

# ── Portal constants ──────────────────────────────────────────────────────────
PORTAL_URL = (
    "https://shcilestamp.com/eStampIndia/submission/"
    "SubmissionServlet?rDoAction=LoadStampDuty"
)
