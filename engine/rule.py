"""Pure functions for the alert rule. No network access here, so it can be tested."""
from __future__ import annotations

from datetime import datetime, timezone

from . import config


def power_devig(odds: list[float]) -> list[float]:
    """Remove the bookmaker margin with the power method.

    Finds k so that sum((1/o)**k) == 1. Loads more margin on long shots than
    proportional removal does.
    """
    p = [1.0 / o for o in odds]
    lo, hi = 0.5, 3.0
    for _ in range(80):
        k = (lo + hi) / 2
        s = sum(x ** k for x in p)
        if s > 1:
            lo = k
        else:
            hi = k
    k = (lo + hi) / 2
    return [x ** k for x in p]


def parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def h2h_prices(event: dict) -> dict[str, dict]:
    """Return {bookmaker_key: {"prices": {"home": x, "draw": y, "away": z}, "updated": dt}}."""
    out = {}
    home, away = event["home_team"], event["away_team"]
    for bk in event.get("bookmakers", []):
        for m in bk.get("markets", []):
            if m.get("key") != "h2h":
                continue
            prices = {}
            for o in m.get("outcomes", []):
                if o["name"] == home:
                    prices["home"] = float(o["price"])
                elif o["name"] == away:
                    prices["away"] = float(o["price"])
                elif o["name"].lower() == "draw":
                    prices["draw"] = float(o["price"])
            if len(prices) == 3:
                upd = m.get("last_update") or bk.get("last_update")
                out[bk["key"]] = {"prices": prices, "updated": parse_time(upd) if upd else None}
    return out


def fair_probs(book_prices: dict) -> dict[str, float] | None:
    sharp = book_prices.get(config.SHARP_BOOK)
    if not sharp:
        return None
    sides = ["home", "draw", "away"]
    fp = power_devig([sharp["prices"][s] for s in sides])
    return dict(zip(sides, fp))


def find_alerts(event: dict, snapshot_time: datetime) -> list[dict]:
    """Apply the frozen rule to one event from an odds snapshot."""
    bp = h2h_prices(event)
    sharp = bp.get(config.SHARP_BOOK)
    if not sharp:
        return []
    if sharp["updated"] is not None:
        age = (snapshot_time - sharp["updated"]).total_seconds() / 60
        if age > config.MAX_SHARP_AGE_MIN:
            return []
    kickoff = parse_time(event["commence_time"])
    hours = (kickoff - snapshot_time).total_seconds() / 3600
    if hours <= 0 or hours > config.ALERT_HORIZON_HOURS:
        return []
    fair = fair_probs(bp)
    alerts = []
    for side in ["home", "draw", "away"]:
        best_book, best_price = None, 0.0
        for bk in config.UK_BOOKS:
            if bk in bp and bp[bk]["prices"][side] > best_price:
                best_book, best_price = bk, bp[bk]["prices"][side]
        if not best_book or best_price >= config.MAX_ODDS:
            continue
        edge = best_price * fair[side] - 1
        if edge > config.EDGE_THRESHOLD:
            alerts.append({
                "event_id": event["id"],
                "sport_key": event["sport_key"],
                "kickoff_utc": event["commence_time"],
                "home_team": event["home_team"],
                "away_team": event["away_team"],
                "side": side,
                "book": best_book,
                "price": round(best_price, 3),
                "pinnacle_price": sharp["prices"][side],
                "fair_prob": round(fair[side], 5),
                "edge_pct": round(edge * 100, 2),
            })
    return alerts


def clv_pct(alert_price: float, close_fair_prob: float) -> float:
    return round((alert_price * close_fair_prob - 1) * 100, 2)


def settle(side: str, home_score: int, away_score: int, price: float) -> tuple[str, float]:
    if home_score > away_score:
        result = "home"
    elif home_score < away_score:
        result = "away"
    else:
        result = "draw"
    return result, round(price - 1 if result == side else -1.0, 3)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
