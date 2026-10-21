# Pass mark for rule v1-live

Fixed on 21 October 2026, before any alert had a closing price or a result. This file is committed to the public repository so the date can be checked. It will not be changed for v1-live. A new rule version gets a new pass mark, written before its first alert.

## What is judged

Closing-line value (CLV): the alert price against Pinnacle's last price before kick-off, with the margin removed by the power method. CLV is the test because it settles quickly. Profit is too noisy to decide anything at this sample size: at average odds near 2.7, one bet swings profit by more than a unit, so a 3% ROI takes thousands of bets to show.

Only alerts logged under rule v1-live count, taken in the order they were logged. Alerts without a closing price (for example a missed check) are left out and the next alert takes their place.

## Checkpoints

The record is judged only at these two points, not continuously.

**Checkpoint 1: the first 100 alerts with a closing price**

- **Edge confirmed** if all three hold:
  - mean CLV is at least +1.5%;
  - the lower end of its 95% confidence interval is above 0%;
  - at least 55% of alerts beat the closing price.
- **Stopped** if mean CLV is 0% or below.
- **Inconclusive** otherwise: carry on to checkpoint 2.

**Checkpoint 2 (only if checkpoint 1 was inconclusive): the first 200 alerts with a closing price**

- **Edge confirmed** if:
  - mean CLV is at least +1.0%;
  - the lower 95% bound is above 0%;
  - at least 55% beat the close.
- **Stopped** otherwise.

"Stopped" means v1-live is not a proven edge. The engine can keep running for information, but nothing is sold or staked on it, and any successor rule starts its own record from zero.

## Profit check

Profit and ROI are reported throughout but do not decide the verdict. One safeguard applies: if ROI is below −10% after 500 settled alerts, the record is flagged for review even if CLV has passed, because that would mean the closing price is not a good guide for these markets.

## Why these numbers

- Per-alert CLV in the historical data (English leagues, 2015/16 to 2024/25, same devig method, odds below 4, edge above 2%) has a standard deviation of about 7.2 percentage points.
- With that spread, the standard error of the mean is about 0.72 points at 100 alerts and 0.51 at 200.
- Simulated with that spread:

| True mean CLV | Confirmed | Stopped |
|---|---|---|
| 0% (no edge) | about 2% at checkpoint 1 | about half at checkpoint 1 |
| +2% | about 73% at checkpoint 1 | under 1% |
| +3% (the historical Test 3 figure) | about 98% at checkpoint 1 | — |

- A true edge of +1% is marginal and mostly not confirmed. That is deliberate: after the cost of bookmaker restrictions, an edge that small is unlikely to be worth selling.

The verdict is computed by `engine/report.py` (`PASS_MARK` and `verdict()`) and shown on the record page.
