"""Frozen settings for the value-alert engine.

RULE VERSION v1-live, frozen 2026-10-21. Do not edit these values without
changing RULE_VERSION and recording the change in the README and the Drive
Session Log. Every alert is written with the rule version that produced it.
"""

RULE_VERSION = "v1-live"

# Leagues covered by The Odds API that showed the edge in Test 3.
SPORTS = {
    "soccer_efl_champ": "Championship",
    "soccer_england_league1": "League One",
    "soccer_england_league2": "League Two",
    "soccer_italy_serie_b": "Serie B",
    "soccer_spain_segunda_division": "Segunda Division",
    "soccer_belgium_first_div": "Belgian Pro League",
}

# Sharp reference used for the fair price.
SHARP_BOOK = "pinnacle"

# UK-licensed bookmakers whose prices can trigger an alert.
# Pinnacle + 9 UK books = 10 bookmakers = 1 credit per odds call.
UK_BOOKS = [
    "williamhill",
    "betvictor",
    "ladbrokes_uk",
    "coral",
    "skybet",
    "paddypower",
    "betfred_uk",
    "betway",
    "unibet_uk",
]

# Alert rule (from Beat the Odds Test 3, best-of-UK-books version).
EDGE_THRESHOLD = 0.02      # UK price must beat the fair price by more than 2%
MAX_ODDS = 4.0             # only prices below 4.0
MAX_SHARP_AGE_MIN = 90     # ignore a Pinnacle price older than this at snapshot time
ALERT_HORIZON_HOURS = 100  # alert only on matches starting within this many hours

# Closing snapshot: taken by the half-hourly run for matches kicking off in
# (CLOSE_MIN_AHEAD, CLOSE_MAX_AHEAD] minutes.
CLOSE_MIN_AHEAD = 2
CLOSE_MAX_AHEAD = 38

# Monthly credit budget guard (free tier is 500).
MONTHLY_CREDIT_LIMIT = 480

API_BASE = "https://api.the-odds-api.com/v4"
