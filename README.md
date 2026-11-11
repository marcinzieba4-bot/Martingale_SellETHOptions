# Martingale ETH option selling: backtest

This is a backtest of selling ATM monthly ETH options on Deribit from Jan 2023 to Sep 2026. It uses
martingale sizing, where each month's size is set so the premium covers the losses since the last profitable reset.

* Variant 1: sell puts every month.
* Variant 2: sell calls every month.
* Variant 3: sell puts after an up month and calls after a down month.
* Variant 1b: puts only after an up month. Variant 2b: calls only after a down month. In both, the martingale size carries over the skipped months.
* Variant 3b: variant 3 plus a perp hedge. Short the perp below last month's low (for puts) or go long above last month's high (for calls), with the stop at the opposite extreme and re-entry allowed.
* Variant 3c: 3b with the hedge on calls only.

**Results and conclusions: [results/REPORT.md](results/REPORT.md)**

**ETH 1b + 3b combined with the BTC session's put spread (SellBTCPuts_3M): do they diversify, and the combined
stats: [results/COMBO.md](results/COMBO.md)**

**What if ETH and BTC crash together right after a rally (simulated in Apr and Dec 2024)? Calmar, drawdown and
capital needed: [results/SCENARIO.md](results/SCENARIO.md)**

**Chosen setup: 1b + 3b on one account, martingale, lean capital, with full risk statistics and a Monte Carlo of
liquidation risk: [results/PORTFOLIO.md](results/PORTFOLIO.md)**

| File | What it does |
|---|---|
| `fetch_data.py` | Downloads real Deribit data into `data/`: settlement prices, hourly ETH, funding, DVOL and ATM option trades |
| `backtest.py` | Runs the simulation, including the margin and capital checks |
| `report.py` | Runs the backtest and writes the charts and `results/REPORT.md` |
| `portfolio.py` | 1b + 3b portfolio engine: combined hourly margin, lean capital, risk statistics, block-bootstrap Monte Carlo |
| `portfolio_report.py` | Runs the portfolio and writes its charts and `results/PORTFOLIO.md` |
| `btc/fetch_btc_spread.py` | Runs the BTC session's own code (SellBTCPuts_3M) to export its recommended put spread month by month into `btc/` |
| `scenario.py`, `scenario_report.py` | Inserts a joint ETH −35% / BTC −28% crash after the 2024 rallies into the real history and re-runs everything, `results/SCENARIO.md` |
| `combo.py`, `combo_report.py` | ETH 1b + 3b + BTC put spread on one account: correlation, combined stats, joint crash stress, Monte Carlo, `results/COMBO.md` |

```bash
pip install pandas numpy matplotlib
python3 report.py
```
