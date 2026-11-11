"""Extract the BTC session's recommended strategy, month by month, for the ETH + BTC combination.

Source: the "BTC puts backtest with loss recovery" session, repo marcinzieba4-bot/SellBTCPuts_3M,
branch claude/vibrant-dijkstra-b4l7vt, script put_spread.py. Its recommended version is variant C
with a 20% wing:
  * at each Deribit monthly expiry, if BTC moved more than +/-10% over the last month (a "big candle"),
    sell the 10% OTM put and buy the 20% OTM put (same expiry), hold both to expiry, no delta hedge;
  * otherwise skip the month;
  * 0.25 BTC per leg, optional recovery: 0.25 + unrecovered loss / net credit per BTC.

This script runs that repo's own code (real Deribit quotes, its fees and hourly mark-to-market) and
writes, per 1 BTC of spread:
  btc/btc_spread_trades.csv  - one row per trade (credit, max loss, P&L at expiry)
  btc/btc_spread_hourly.csv  - hourly mark-to-market P&L of every trade
Run:  BTC_REPO=/path/to/SellBTCPuts_3M python3 btc/fetch_btc_spread.py
"""
import os
import sys
from pathlib import Path

BTC_REPO = os.environ.get("BTC_REPO", "/home/user/marcinzieba4-bot/sellbtcputs_3m")
sys.path.insert(0, BTC_REPO)

import pandas as pd  # noqa: E402

import backtest as bt  # noqa: E402  (the BTC repo's backtest.py)
import hedged_backtest as hb  # noqa: E402
import put_spread as ps  # noqa: E402
from candle_patterns import candle  # noqa: E402

HERE = Path(__file__).parent
SOLD, WING = 0.10, 0.20


def main():
    inst, px = bt.load_instruments(), bt.load_delivery_prices()
    perp, dvol, fund = hb.load_perp_1h(), hb.load_dvol_1h(), hb.load_funding_1h()
    m = hb.load_perp_1m()
    pairs = hb.cycle_expiries(inst, "1M")
    exps = [pd.Timestamp(e) for e in sorted(inst.expiry.unique())]
    prev = {b: a for a, b in zip(exps[:-1], exps[1:])}
    prev[exps[0]] = exps[0] - pd.Timedelta(days=28)
    ret = {t0: candle(m, max(prev[t0], pd.Timestamp("2021-12-01")), t0)["ret"] for t0, _ in pairs}

    rows, hourly, sel = [], [], []
    for t0, t1 in pairs:
        if abs(ret[t0]) <= ps.BIG:
            rows.append(dict(entry=t0, expiry=t1, candle_ret=ret[t0], trade=False))
            continue
        k1, q1, s0 = ps.pick_put_otm(inst, px, t0, t1, SOLD)
        k2, q2, _ = ps.pick_put_otm(inst, px, t0, t1, WING)
        cyc, path = ps.spread_cycle([(-1, k1, q1), (1, k2, q2)], s0, t0, t1, px, perp, dvol, fund, "none")
        sel.append((cyc, path))
        credit_net = cyc["prem_usd"] - cyc["fee_entry"]
        rows.append(dict(entry=t0, expiry=t1, candle_ret=ret[t0], trade=True,
                         candle="green" if ret[t0] > 0 else "red", spot_entry=s0, spot_expiry=cyc["spot_expiry"],
                         sold_strike=k1, bought_strike=k2, credit=cyc["prem_usd"], fees_entry=cyc["fee_entry"],
                         max_loss=(k1 - k2) - credit_net, pnl=cyc["pnl_per_lot"], settled=cyc["settled"]))
        hourly.append(pd.DataFrame({"entry": t0, "time": path.index, "mtm": path.values}))

    trades = pd.DataFrame(rows)
    trades.to_csv(HERE / "btc_spread_trades.csv", index=False, float_format="%.4f")
    pd.concat(hourly).to_csv(HERE / "btc_spread_hourly.csv", index=False, float_format="%.4f")

    # check against the BTC session's own summary (results/put_spread.csv, variant C 20% wing)
    for mode in ("fixed", "base+cover"):
        print(mode, ps.evaluate(sel, mode))
    ref = pd.read_csv(os.path.join(BTC_REPO, "results", "put_spread.csv"))
    print(ref[ref.variant.str.startswith("C: 20%")].to_string(index=False))


if __name__ == "__main__":
    main()
