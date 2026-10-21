"""Entry point.

python -m engine.run alerts   # Friday/Tuesday snapshot: find and log new alerts
python -m engine.run close    # half-hourly: closing prices for alerted matches about to start
python -m engine.run scores   # daily: results for alerted matches
python -m engine.run report   # rebuild docs/ from the ledger (no API calls)
"""
from __future__ import annotations

import sys
from datetime import timedelta

from . import config, ledger, oddsapi, report
from .rule import find_alerts, h2h_prices, fair_probs, now_utc, parse_time


def cmd_alerts() -> None:
    t = now_utc()
    seen = {r["alert_id"] for r in ledger.read("alerts.csv")}
    new = 0
    for sport, league in config.SPORTS.items():
        try:
            data = oddsapi.odds(sport, frm=t, to=t + timedelta(hours=config.ALERT_HORIZON_HOURS))
        except oddsapi.QuotaExceeded as e:
            print(e); break
        if not data:
            continue
        ledger.save_snapshot("alerts", sport, data, t)
        for ev in data:
            for a in find_alerts(ev, t):
                aid = f"{a['event_id']}:{a['side']}"
                if aid in seen:
                    continue
                a.update({"alert_id": aid, "rule_version": config.RULE_VERSION,
                          "snapshot_utc": t.isoformat(timespec="seconds"), "league": league})
                ledger.append("alerts.csv", a)
                seen.add(aid); new += 1
    print(f"alerts: {new} new")


def cmd_close() -> None:
    t = now_utc()
    alerts = ledger.read("alerts.csv")
    closes = ledger.read("closes.csv")
    last_close = {}
    for c in closes:
        last_close[c["event_id"]] = max(last_close.get(c["event_id"], ""), c["snapshot_utc"])
    due: dict[str, set] = {}
    for a in alerts:
        ko = parse_time(a["kickoff_utc"])
        mins = (ko - t).total_seconds() / 60
        if config.CLOSE_MIN_AHEAD < mins <= 65:
            prev = last_close.get(a["event_id"])
            if prev and (t - parse_time(prev)).total_seconds() / 60 < 25:
                continue
            due.setdefault(a["sport_key"], set()).add(a["event_id"])
    for sport, ids in due.items():
        try:
            data = oddsapi.odds(sport, event_ids=sorted(ids))
        except oddsapi.QuotaExceeded as e:
            print(e); break
        if not data:
            continue
        ledger.save_snapshot("close", sport, data, t)
        for ev in data:
            bp = h2h_prices(ev)
            fp = fair_probs(bp)
            if not fp:
                continue
            pin = bp[config.SHARP_BOOK]["prices"]
            ledger.append("closes.csv", {
                "event_id": ev["id"], "snapshot_utc": t.isoformat(timespec="seconds"),
                "kickoff_utc": ev["commence_time"],
                "pin_home": pin["home"], "pin_draw": pin["draw"], "pin_away": pin["away"],
                "fair_home": round(fp["home"], 5), "fair_draw": round(fp["draw"], 5), "fair_away": round(fp["away"], 5),
            })
    print(f"close: {sum(len(v) for v in due.values())} events checked")


def cmd_scores() -> None:
    t = now_utc()
    done = {r["event_id"] for r in ledger.read("results.csv")}
    need: dict[str, set] = {}
    for a in ledger.read("alerts.csv"):
        ko = parse_time(a["kickoff_utc"])
        hrs = (t - ko).total_seconds() / 3600
        if 2.5 < hrs < 72 and a["event_id"] not in done:
            need.setdefault(a["sport_key"], set()).add(a["event_id"])
    for sport, ids in need.items():
        try:
            data = oddsapi.scores(sport, 3)
        except oddsapi.QuotaExceeded as e:
            print(e); break
        for ev in data:
            if ev["id"] in ids and ev.get("completed") and ev.get("scores"):
                s = {x["name"]: int(x["score"]) for x in ev["scores"]}
                ledger.append("results.csv", {
                    "event_id": ev["id"], "home_score": s.get(ev["home_team"]),
                    "away_score": s.get(ev["away_team"]),
                    "recorded_utc": t.isoformat(timespec="seconds"),
                })
                done.add(ev["id"])
    print(f"scores: {sum(len(v) for v in need.values())} events looked up")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "report"
    if cmd == "alerts":
        cmd_alerts()
    elif cmd == "close":
        cmd_close()
    elif cmd == "scores":
        cmd_scores()
    elif cmd != "report":
        raise SystemExit(f"unknown command {cmd}")
    report.build()


if __name__ == "__main__":
    main()
