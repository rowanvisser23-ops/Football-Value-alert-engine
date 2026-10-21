"""Append-only CSV ledger. Rows are only ever added, never edited or removed."""
from __future__ import annotations

import csv
import gzip
import json
import os
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "ledger")
SNAP = os.path.join(ROOT, "data", "snapshots")

FIELDS = {
    "alerts.csv": ["alert_id", "event_id", "rule_version", "snapshot_utc", "kickoff_utc", "sport_key", "league",
                   "home_team", "away_team", "side", "book", "price", "pinnacle_price", "fair_prob", "edge_pct"],
    "closes.csv": ["event_id", "snapshot_utc", "kickoff_utc", "pin_home", "pin_draw", "pin_away",
                   "fair_home", "fair_draw", "fair_away"],
    "results.csv": ["event_id", "home_score", "away_score", "recorded_utc"],
    "quota.csv": ["time_utc", "endpoint", "sport_key", "cost", "remaining"],
}


def path(name: str) -> str:
    return os.path.join(LEDGER, name)


def read(name: str) -> list[dict]:
    p = path(name)
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def append(name: str, row: dict) -> None:
    os.makedirs(LEDGER, exist_ok=True)
    p = path(name)
    new = not os.path.exists(p)
    with open(p, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS[name])
        if new:
            w.writeheader()
        w.writerow({k: row.get(k, "") for k in FIELDS[name]})


def save_snapshot(kind: str, sport: str, payload, when: datetime) -> str:
    d = os.path.join(SNAP, when.strftime("%Y-%m-%d"))
    os.makedirs(d, exist_ok=True)
    fn = os.path.join(d, f"{when.strftime('%H%M%S')}_{kind}_{sport}.json.gz")
    with gzip.open(fn, "wt", encoding="utf-8") as f:
        json.dump(payload, f, separators=(",", ":"))
    return fn


def credits_used_this_month() -> int:
    month = datetime.now(timezone.utc).strftime("%Y-%m")
    total = 0
    for r in read("quota.csv"):
        if r["time_utc"].startswith(month):
            try:
                total += int(float(r["cost"] or 0))
            except ValueError:
                pass
    return total
