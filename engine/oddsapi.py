"""Minimal client for The Odds API v4. Standard library only."""
from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request

from . import config, ledger
from .rule import now_utc


class QuotaExceeded(Exception):
    pass


def _key() -> str:
    key = os.environ.get("ODDS_API_KEY", "").strip()
    if not key:
        raise SystemExit("ODDS_API_KEY is not set (add it as a GitHub Actions secret).")
    return key


def _get(path: str, params: dict, sport: str, endpoint: str):
    q = dict(params)
    q["apiKey"] = _key()
    url = f"{config.API_BASE}{path}?{urllib.parse.urlencode(q)}"
    req = urllib.request.Request(url, headers={"User-Agent": "value-alert-engine/1"})
    with urllib.request.urlopen(req, timeout=30) as r:
        body = json.loads(r.read().decode())
        last = r.headers.get("x-requests-last")
        remaining = r.headers.get("x-requests-remaining")
    ledger.append("quota.csv", {
        "time_utc": now_utc().isoformat(timespec="seconds"),
        "endpoint": endpoint,
        "sport_key": sport,
        "cost": last if last is not None else "",
        "remaining": remaining if remaining is not None else "",
    })
    return body


def guard(cost: int = 1) -> None:
    used = ledger.credits_used_this_month()
    if used + cost > config.MONTHLY_CREDIT_LIMIT:
        raise QuotaExceeded(f"Monthly credit guard reached ({used} used).")


def events(sport: str, frm=None, to=None) -> list[dict]:
    """Fixture list. Costs no credits."""
    p = {"dateFormat": "iso"}
    if frm:
        p["commenceTimeFrom"] = frm.strftime("%Y-%m-%dT%H:%M:%SZ")
    if to:
        p["commenceTimeTo"] = to.strftime("%Y-%m-%dT%H:%M:%SZ")
    return _get(f"/sports/{sport}/events", p, sport, "events")


def odds(sport: str, frm=None, to=None, event_ids=None) -> list[dict]:
    """h2h odds for Pinnacle + the UK books (10 bookmakers = 1 credit)."""
    guard(1)
    p = {
        "bookmakers": ",".join([config.SHARP_BOOK] + config.UK_BOOKS),
        "markets": "h2h",
        "oddsFormat": "decimal",
        "dateFormat": "iso",
    }
    if frm:
        p["commenceTimeFrom"] = frm.strftime("%Y-%m-%dT%H:%M:%SZ")
    if to:
        p["commenceTimeTo"] = to.strftime("%Y-%m-%dT%H:%M:%SZ")
    if event_ids:
        p["eventIds"] = ",".join(event_ids)
    return _get(f"/sports/{sport}/odds", p, sport, "odds")


def scores(sport: str, days_from: int = 3) -> list[dict]:
    """Completed results for the last `days_from` days (2 credits)."""
    guard(2)
    return _get(f"/sports/{sport}/scores", {"daysFrom": days_from, "dateFormat": "iso"}, sport, "scores")
