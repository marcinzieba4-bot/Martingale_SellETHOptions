# Martingale ETH option selling: backtest

This is a backtest of selling ATM monthly ETH options on Deribit from Jan 2023 to Sep 2026. It uses
martingale sizing, where each month's size is set so the premium covers the losses since the last profitable reset.

* Variant 1: sell puts every month.
* Variant 2: sell calls every month.
* Variant 3: sell puts after an up month and calls after a down month.

**Results and conclusions: [results/REPORT.md](results/REPORT.md)**

| File | What it does |
|---|---|
| `fetch_data.py` | Downloads real Deribit data into `data/`: settlement prices, hourly ETH, DVOL and ATM option trades |
| `backtest.py` | Runs the simulation, including the margin and capital checks |
| `report.py` | Runs the backtest and writes the charts and `results/REPORT.md` |

```bash
pip install pandas numpy matplotlib
python3 report.py
```
