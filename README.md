# Value Alert Engine

A free, automated engine that logs football price alerts with a timestamp before kick-off and checks each one against the closing price afterwards. The public commit history of this repository is the proof that no alert has been added, changed or removed after the event.

Information only. It does not place bets. 18+. BeGambleAware.org.

## The rule (v1-live, frozen 21 October 2026)

- **Fair price**: Pinnacle's 1X2 odds with the margin removed by the power method.
- **Alert**: the best price among William Hill, BetVictor, Ladbrokes, Coral, Sky Bet, Paddy Power, Betfred, Betway and Unibet is more than 2% above the fair price, at odds below 4.0, for a match starting within 100 hours. Pinnacle's price must be under 90 minutes old.
- **Leagues**: Championship, League One, League Two, Serie B, Segunda División, Belgian Pro League.
- **Scored by**: closing-line value (CLV), the alert price against Pinnacle's last price before kick-off with the margin removed the same way; and return on a 1-unit stake.

Basis: Football Betting Research, Beat the Odds Test 3 (2015/16–2024/25 historical data). The live bookmaker set differs from the historical test (no Bet365 or bwin, more UK books), so this is a genuinely new forward test.

The pass mark that decides whether the edge is real was fixed before any result was known: see [PASS_MARK.md](PASS_MARK.md).

Changing any value in `engine/config.py` requires a new `RULE_VERSION`. Old alerts keep the version that produced them.

## Schedule (UTC)

| When | What | Credits |
|---|---|---|
| Friday and Tuesday 10:00 | Alert snapshot of all six leagues | up to 6 |
| Every 30 min, 10:00–21:30 | Closing price for alerted matches starting within the hour | 1 per league with a match due |
| Daily 05:30 | Results for alerted matches | 2 per league with a result due |

Expected use is about 250–400 credits a month, inside The Odds API's free 500. A guard stops calls at 480 credits a month.

## Files

- `ledger/alerts.csv`, `closes.csv`, `results.csv`, `quota.csv`: append-only records.
- `data/snapshots/`: raw API responses behind every alert and close.
- `docs/`: the public record page (`index.html`), `alerts.csv` and `summary.json`, rebuilt on every run.

## Set-up

1. Get a free key at https://the-odds-api.com.
2. In this repository: Settings → Secrets and variables → Actions → New repository secret, name `ODDS_API_KEY`.
3. Settings → Pages → Deploy from a branch → `main`, folder `/docs`.
4. Actions tab → enable workflows. To test straight away, run the workflow manually with mode `alerts`.

## Local test

```
python -m unittest discover tests
```
