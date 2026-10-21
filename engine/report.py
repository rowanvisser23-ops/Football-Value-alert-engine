"""Builds the public record (docs/) from the ledger. No API calls."""
from __future__ import annotations

import csv
import html
import json
import math
import os

from . import config, ledger
from .rule import clv_pct, now_utc, parse_time, settle

DOCS = os.path.join(ledger.ROOT, "docs")


def merged() -> list[dict]:
    closes: dict[str, dict] = {}
    for c in ledger.read("closes.csv"):
        if parse_time(c["snapshot_utc"]) > parse_time(c["kickoff_utc"]):
            continue
        prev = closes.get(c["event_id"])
        if not prev or c["snapshot_utc"] > prev["snapshot_utc"]:
            closes[c["event_id"]] = c
    results = {r["event_id"]: r for r in ledger.read("results.csv")}
    rows = []
    for a in ledger.read("alerts.csv"):
        r = dict(a)
        price = float(a["price"])
        c = closes.get(a["event_id"])
        if c:
            fair_close = float(c[f"fair_{a['side']}"])
            r["close_snapshot_utc"] = c["snapshot_utc"]
            r["pinnacle_close"] = c[f"pin_{a['side']}"]
            r["clv_pct"] = clv_pct(price, fair_close)
        else:
            r["close_snapshot_utc"] = r["pinnacle_close"] = r["clv_pct"] = ""
        res = results.get(a["event_id"])
        if res and res["home_score"] != "" and res["away_score"] != "":
            outcome, ret = settle(a["side"], int(res["home_score"]), int(res["away_score"]), price)
            r["score"] = f"{res['home_score']}-{res['away_score']}"
            r["outcome"], r["return_units"] = outcome, ret
        else:
            r["score"] = r["outcome"] = r["return_units"] = ""
        rows.append(r)
    return rows


def stats(rows: list[dict]) -> dict:
    clv = [float(r["clv_pct"]) for r in rows if r["clv_pct"] != ""]
    ret = [float(r["return_units"]) for r in rows if r["return_units"] != ""]
    def mean(x): return sum(x) / len(x) if x else None
    def se(x):
        if len(x) < 2: return None
        m = mean(x); return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - 1) / len(x))
    return {
        "alerts": len(rows),
        "with_close": len(clv),
        "mean_clv_pct": round(mean(clv), 2) if clv else None,
        "beat_close_pct": round(100 * sum(1 for v in clv if v > 0) / len(clv), 1) if clv else None,
        "settled": len(ret),
        "profit_units": round(sum(ret), 2) if ret else 0.0,
        "roi_pct": round(100 * mean(ret), 2) if ret else None,
        "roi_se_pct": round(100 * se(ret), 2) if se(ret) is not None else None,
    }


def group(rows, key):
    out = {}
    for r in rows:
        out.setdefault(r[key], []).append(r)
    return {k: stats(v) for k, v in sorted(out.items())}


# Pass mark for rule v1-live, fixed 21 October 2026 before any alert had a closing price.
# See PASS_MARK.md. Judged only at two checkpoints, on alerts in the order they were logged.
PASS_MARK = {
    "rule_version": "v1-live",
    "stage1_n": 100, "stage1_min_clv": 1.5,
    "stage2_n": 200, "stage2_min_clv": 1.0,
    "min_beat_pct": 55.0,
    "profit_review_n": 500, "profit_review_roi": -10.0,
}


def _clv_test(clvs: list[float]) -> dict:
    n = len(clvs)
    m = sum(clvs) / n
    sd = math.sqrt(sum((v - m) ** 2 for v in clvs) / (n - 1))
    lower = m - 1.96 * sd / math.sqrt(n)
    beat = 100 * sum(1 for v in clvs if v > 0) / n
    return {"n": n, "mean_clv_pct": round(m, 2), "lower95_pct": round(lower, 2), "beat_close_pct": round(beat, 1)}


def verdict(rows: list[dict]) -> dict:
    pm = PASS_MARK
    v1 = [r for r in rows if r.get("rule_version") == pm["rule_version"]]
    timed = sorted((r for r in v1 if r["clv_pct"] != ""), key=lambda r: (r["snapshot_utc"], r["alert_id"]))
    clvs = [float(r["clv_pct"]) for r in timed]
    out = {"with_close": len(clvs)}
    passes = lambda t, floor: t["mean_clv_pct"] >= floor and t["lower95_pct"] > 0 and t["beat_close_pct"] >= pm["min_beat_pct"]
    if len(clvs) < pm["stage1_n"]:
        out.update(status="collecting", text=f"Collecting: {len(clvs)} of {pm['stage1_n']} alerts with a closing price")
    else:
        t1 = _clv_test(clvs[:pm["stage1_n"]])
        out["stage1"] = t1
        if passes(t1, pm["stage1_min_clv"]):
            out.update(status="confirmed", text="Edge confirmed at 100 alerts")
        elif t1["mean_clv_pct"] <= 0:
            out.update(status="failed", text="Not confirmed at 100 alerts: mean CLV at or below zero, v1 stopped")
        elif len(clvs) < pm["stage2_n"]:
            out.update(status="continuing",
                       text=f"Inconclusive at 100 alerts; continuing: {len(clvs)} of {pm['stage2_n']}")
        else:
            t2 = _clv_test(clvs[:pm["stage2_n"]])
            out["stage2"] = t2
            if passes(t2, pm["stage2_min_clv"]):
                out.update(status="confirmed", text="Edge confirmed at 200 alerts")
            else:
                out.update(status="failed", text="Not confirmed at 200 alerts, v1 stopped")
    rets = [float(r["return_units"]) for r in v1 if r["return_units"] != ""]
    if len(rets) >= pm["profit_review_n"] and 100 * sum(rets) / len(rets) < pm["profit_review_roi"]:
        out["profit_flag"] = f"Review: ROI below {pm['profit_review_roi']:.0f}% after {len(rets)} settled alerts"
    return out


def build() -> None:
    os.makedirs(DOCS, exist_ok=True)
    rows = merged()
    summary = {
        "built_utc": now_utc().isoformat(timespec="seconds"),
        "rule_version": config.RULE_VERSION,
        "rule": {
            "sharp_book": config.SHARP_BOOK, "uk_books": config.UK_BOOKS,
            "edge_threshold_pct": config.EDGE_THRESHOLD * 100, "max_odds": config.MAX_ODDS,
            "leagues": list(config.SPORTS.values()),
        },
        "overall": stats(rows),
        "verdict": verdict(rows),
        "pass_mark": PASS_MARK,
        "by_league": group(rows, "league"),
        "by_book": group(rows, "book"),
        "credits_used_this_month": ledger.credits_used_this_month(),
    }
    with open(os.path.join(DOCS, "summary.json"), "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2)
    cols = ["snapshot_utc", "kickoff_utc", "league", "home_team", "away_team", "side", "book", "price",
            "pinnacle_price", "edge_pct", "pinnacle_close", "clv_pct", "score", "return_units", "rule_version", "alert_id"]
    with open(os.path.join(DOCS, "alerts.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)
    with open(os.path.join(DOCS, "index.html"), "w", encoding="utf-8") as f:
        f.write(render(summary, rows))


def _fmt(v, suffix=""):
    return "–" if v is None or v == "" else f"{v}{suffix}"


def render(s: dict, rows: list[dict]) -> str:
    o = s["overall"]
    def table(groups, label):
        trs = "".join(
            f"<tr><td>{html.escape(k)}</td><td>{g['alerts']}</td><td>{_fmt(g['mean_clv_pct'],'%')}</td>"
            f"<td>{_fmt(g['beat_close_pct'],'%')}</td><td>{g['settled']}</td><td>{_fmt(g['roi_pct'],'%')}</td></tr>"
            for k, g in groups.items())
        return (f"<table><thead><tr><th>{label}</th><th>Alerts</th><th>Mean CLV</th><th>Beat close</th>"
                f"<th>Settled</th><th>ROI</th></tr></thead><tbody>{trs or '<tr><td colspan=6>No alerts yet</td></tr>'}</tbody></table>")
    recent = sorted(rows, key=lambda r: r["snapshot_utc"], reverse=True)[:200]
    side_name = {"home": "Home", "draw": "Draw", "away": "Away"}
    trs = "".join(
        f"<tr><td>{html.escape(r['snapshot_utc'][:16].replace('T',' '))}</td><td>{html.escape(r['kickoff_utc'][:16].replace('T',' '))}</td>"
        f"<td>{html.escape(r['league'])}</td><td>{html.escape(r['home_team'])} v {html.escape(r['away_team'])}</td>"
        f"<td>{side_name.get(r['side'], r['side'])}</td><td>{html.escape(r['book'])}</td><td>{r['price']}</td>"
        f"<td>{r['edge_pct']}%</td><td>{_fmt(r['pinnacle_close'])}</td><td>{_fmt(r['clv_pct'],'%')}</td>"
        f"<td>{_fmt(r['score'])}</td><td>{_fmt(r['return_units'])}</td></tr>"
        for r in recent)
    return f"""<!doctype html><html lang="en-GB"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Value Alert Record</title>
<style>
:root{{--bg:#f7f6f2;--fg:#1d1d1b;--muted:#6b6a65;--line:#dcdad3;--card:#fff;--accent:#1f6f50}}
@media (prefers-color-scheme:dark){{:root{{--bg:#151614;--fg:#ecebe6;--muted:#a3a29c;--line:#30312d;--card:#1d1e1b;--accent:#6fc39c}}}}
body{{margin:0;background:var(--bg);color:var(--fg);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}}
main{{max-width:1100px;margin:0 auto;padding:24px 16px 64px}}
h1{{font-size:26px;margin:0 0 4px}} h2{{font-size:18px;margin:32px 0 8px}}
.muted{{color:var(--muted)}} .kpis{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:20px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.kpi b{{display:block;font-size:24px;color:var(--accent)}} .scroll{{overflow-x:auto}}
table{{border-collapse:collapse;width:100%;background:var(--card);font-size:13.5px}}
th,td{{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;white-space:nowrap}}
th{{font-weight:600}} code{{font-size:13px}}
</style></head><body><main>
<h1>Value Alert Record</h1>
<p class="muted">Every alert is logged with a timestamp before kick-off and committed to this public repository; the commit history is the proof that nothing has been changed afterwards. Rule {html.escape(s['rule_version'])}. Last updated {html.escape(s['built_utc'][:16].replace('T',' '))} UTC.</p>
<div class="kpis">
<div class="kpi"><span class="muted">Alerts</span><b>{o['alerts']}</b></div>
<div class="kpi"><span class="muted">Mean CLV</span><b>{_fmt(o['mean_clv_pct'],'%')}</b></div>
<div class="kpi"><span class="muted">Beat the close</span><b>{_fmt(o['beat_close_pct'],'%')}</b></div>
<div class="kpi"><span class="muted">Profit (1-unit stakes)</span><b>{o['profit_units']}</b></div>
<div class="kpi"><span class="muted">ROI</span><b>{_fmt(o['roi_pct'],'%')}</b></div>
</div>
<h2>Verdict</h2>
<p><b>{html.escape(s['verdict']['text'])}</b>{('<br>' + html.escape(s['verdict']['profit_flag'])) if s['verdict'].get('profit_flag') else ''}</p>
<p class="muted">Pass mark, fixed on 21 October 2026 before any result was known (<a href="https://github.com/rowanvisser23-ops/Football-Value-alert-engine/blob/main/PASS_MARK.md">PASS_MARK.md</a>). Judged at the first 100 alerts with a closing price: confirmed if mean CLV is at least +1.5%, its 95% lower bound is above zero and at least 55% beat the close; stopped if mean CLV is zero or below; otherwise judged again at 200, needing mean CLV of at least +1.0% with the same other two tests. Profit is reported but does not decide the verdict.</p>
<h2>The rule</h2>
<p>Fair price = Pinnacle's odds with the margin removed (power method). An alert is logged when the best price among {html.escape(', '.join(s['rule']['uk_books']))} is more than {s['rule']['edge_threshold_pct']:.0f}% above the fair price, at odds below {s['rule']['max_odds']}. Leagues: {html.escape(', '.join(s['rule']['leagues']))}. CLV compares the alert price with Pinnacle's last price before kick-off, margin removed the same way.</p>
<h2>By league</h2><div class="scroll">{table(s['by_league'], 'League')}</div>
<h2>By bookmaker</h2><div class="scroll">{table(s['by_book'], 'Bookmaker')}</div>
<h2>Alerts (latest 200)</h2><div class="scroll"><table><thead><tr><th>Logged (UTC)</th><th>Kick-off (UTC)</th><th>League</th><th>Match</th><th>Pick</th><th>Book</th><th>Price</th><th>Edge</th><th>Pinnacle close</th><th>CLV</th><th>Score</th><th>Return</th></tr></thead><tbody>{trs or '<tr><td colspan=12>No alerts yet</td></tr>'}</tbody></table></div>
<p class="muted">Full record: <a href="alerts.csv">alerts.csv</a> · <a href="summary.json">summary.json</a>. Information only, not betting advice. 18+. BeGambleAware.org</p>
</main></body></html>"""
