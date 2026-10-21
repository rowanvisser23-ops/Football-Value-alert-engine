"""End-to-end test with a fake API. Run: python -m unittest discover tests"""
import os
import shutil
import tempfile
import unittest
from datetime import timedelta
from unittest import mock

from engine import config, ledger, oddsapi, report, rule, run


def event(eid, ko, pin, books, sport="soccer_england_league2", home="Home FC", away="Away FC", upd=None):
    def market(p):
        return [{"key": "h2h", "last_update": upd, "outcomes": [
            {"name": home, "price": p[0]}, {"name": away, "price": p[2]}, {"name": "Draw", "price": p[1]}]}]
    bks = [{"key": "pinnacle", "markets": market(pin)}] + [{"key": k, "markets": market(v)} for k, v in books.items()]
    return {"id": eid, "sport_key": sport, "commence_time": ko, "home_team": home, "away_team": away, "bookmakers": bks}


class T(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        for mod in (ledger,):
            mod.LEDGER = os.path.join(self.tmp, "ledger"); mod.SNAP = os.path.join(self.tmp, "snap")
        report.DOCS = os.path.join(self.tmp, "docs")
        os.environ["ODDS_API_KEY"] = "test"

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_devig_sums_to_one(self):
        p = rule.power_devig([2.0, 3.4, 4.0])
        self.assertAlmostEqual(sum(p), 1.0, places=6)
        self.assertLess(p[2], (1/4.0) / (1/2.0 + 1/3.4 + 1/4.0))  # long shot loses more margin than proportional

    def test_full_cycle(self):
        t0 = rule.now_utc()
        ko = (t0 + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        upd = t0.strftime("%Y-%m-%dT%H:%M:%SZ")
        # Pinnacle 2.00/3.50/4.00; William Hill 2.15 on home -> edge ~ +5%; 4.6 away above MAX_ODDS (ignored)
        ev = event("e1", ko, [2.00, 3.50, 4.00], {"williamhill": [2.15, 3.40, 4.6], "skybet": [2.05, 3.45, 3.9]}, upd=upd)
        ev_close = event("e1", ko, [1.95, 3.55, 4.20], {"williamhill": [2.0, 3.4, 4.0]}, upd=upd)
        calls = []

        def fake_get(path, params, sport, endpoint):
            calls.append((endpoint, sport))
            ledger.append("quota.csv", {"time_utc": rule.now_utc().isoformat(), "endpoint": endpoint,
                                        "sport_key": sport, "cost": 1, "remaining": 499})
            if endpoint == "odds" and sport == "soccer_england_league2":
                return [ev_close] if "eventIds" in params else [ev]
            if endpoint == "scores" and sport == "soccer_england_league2":
                return [{"id": "e1", "completed": True, "home_team": "Home FC", "away_team": "Away FC",
                         "scores": [{"name": "Home FC", "score": "2"}, {"name": "Away FC", "score": "1"}]}]
            return []

        with mock.patch.object(oddsapi, "_get", side_effect=fake_get):
            run.cmd_alerts()
            alerts = ledger.read("alerts.csv")
            self.assertEqual(len(alerts), 1)
            self.assertEqual(alerts[0]["side"], "home")
            self.assertEqual(alerts[0]["book"], "williamhill")
            run.cmd_alerts()  # second run must not duplicate
            self.assertEqual(len(ledger.read("alerts.csv")), 1)
            # move clock to 20 minutes before kick-off
            with mock.patch.object(run, "now_utc", return_value=t0 + timedelta(hours=29, minutes=40)):
                run.cmd_close()
            self.assertEqual(len(ledger.read("closes.csv")), 1)
            with mock.patch.object(run, "now_utc", return_value=t0 + timedelta(hours=34)):
                run.cmd_scores()
            self.assertEqual(len(ledger.read("results.csv")), 1)
        rows = report.merged()
        self.assertEqual(rows[0]["return_units"], 1.15)
        fair_close = rule.power_devig([1.95, 3.55, 4.20])[0]
        self.assertAlmostEqual(rows[0]["clv_pct"], round((2.15 * fair_close - 1) * 100, 2))
        report.build()
        self.assertTrue(os.path.exists(os.path.join(report.DOCS, "index.html")))
        s = report.stats(rows)
        self.assertEqual(s["settled"], 1)

    def test_stale_pinnacle_ignored(self):
        t0 = rule.now_utc()
        ko = (t0 + timedelta(hours=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old = (t0 - timedelta(hours=5)).strftime("%Y-%m-%dT%H:%M:%SZ")
        ev = event("e2", ko, [2.0, 3.5, 4.0], {"williamhill": [2.3, 3.4, 3.8]}, upd=old)
        self.assertEqual(rule.find_alerts(ev, t0), [])


if __name__ == "__main__":
    unittest.main()
