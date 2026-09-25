"""Martingale monthly ETH option-selling backtest (Jan 2023 - Sep 2026).

Every month, on Deribit's monthly expiry (last Friday, 08:00 UTC) we sell the at-the-money
option that expires on the next monthly expiry. Premium comes from the real Deribit implied
vol traded at that moment; settlement uses Deribit's real delivery price.

Variants
  1  PUTS   - always sell the ATM put
  2  CALLS  - always sell the ATM call
  3  SWITCH - last month ETH went up -> sell puts, went down -> sell calls

Sizing rules
  fixed       - always the base size (no martingale; the reference)
  martingale  - size = base + (unrecovered losses) / premium-per-unit. A winning month pays the
                normal premium *plus* everything lost since the last reset; the size goes back to
                base as soon as the losses are recovered.
  last_only   - literal version: size = base + (last month's loss) / premium-per-unit. Resets
                after any profitable month even if older losses were not fully recovered.

Capital (all in USD, stablecoin-collateralised account)
  margin      - Deribit standard margin: open needs 15% of notional + option mark, maintenance
                is 7.5% + mark. Checked every hour against the worst ETH print of the hour.
                = minimum starting balance that would never have been liquidated.
  unlevered   - 1x notional set aside for every open option (cash-secured put / fully funded call)
  drawdown    - deepest fall of the cumulative P&L (money actually lost at the worst point)
"""
import math
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).parent
DATA, OUT = ROOT / "data", ROOT / "results"

BASE_NOTIONAL = 10_000.0      # USD notional of the base trade; every $ result scales linearly
FEE_RATE = 0.0003             # Deribit option fee: 0.03% of underlying, capped at 12.5% of premium
DELIVERY_FEE_RATE = 0.00015   # 0.015% of underlying on ITM settlement, same cap
SLIPPAGE = 0.01               # sell 1% below the mid/mark premium
IM_RATE, MIN_IM_RATE, MM_RATE = 0.15, 0.10, 0.075
FIRST_SALE = "2022-12-30"     # the Dec-2022 expiry: sells the option that covers January 2023


def norm_cdf(x):
    return 0.5 * (1.0 + np.vectorize(math.erf)(np.asarray(x) / math.sqrt(2.0)))


def bs(s, k, t, vol, kind):
    s, t, vol = np.asarray(s, float), np.maximum(np.asarray(t, float), 1e-9), np.asarray(vol, float)
    sd = vol * np.sqrt(t)
    d1 = (np.log(s / k) + 0.5 * sd ** 2) / sd
    d2 = d1 - sd
    if kind == "C":
        return s * norm_cdf(d1) - k * norm_cdf(d2)
    return k * norm_cdf(-d2) - s * norm_cdf(-d1)


def load():
    q = pd.read_csv(DATA / "atm_quotes.csv", parse_dates=["sell_date", "expiry"])
    px = pd.read_csv(DATA / "delivery_prices.csv", parse_dates=["date"]).set_index("date")["price"]
    eth = pd.read_csv(DATA / "eth_hourly.csv", parse_dates=["time"]).set_index("time").tz_localize(None)
    dvol = pd.read_csv(DATA / "dvol_hourly.csv", parse_dates=["time"]).set_index("time")["close"].tz_localize(None)
    eth["dvol"] = dvol.reindex(eth.index).ffill() / 100
    q["settle"] = q.expiry.map(px)
    q["t_years"] = (q.expiry - q.sell_date).dt.days / 365.0
    q["iv"] = q.iv_median / 100
    for kind in ("P", "C"):
        prem = bs(q.spot, q.strike, q.t_years, q.iv, kind)
        fee = np.minimum(FEE_RATE * q.spot, 0.125 * prem)
        q[f"prem_{kind}"] = prem                                   # fair premium per 1 ETH (USD)
        q[f"prem_net_{kind}"] = prem * (1 - SLIPPAGE) - fee         # what we actually keep
        payoff = np.maximum(q.settle - q.strike, 0) if kind == "C" else np.maximum(q.strike - q.settle, 0)
        dfee = np.where(payoff > 0, np.minimum(DELIVERY_FEE_RATE * q.settle, 0.125 * payoff), 0)
        q[f"payoff_{kind}"] = payoff + dfee
    q["prev_move"] = q.spot / q.spot.shift(1) - 1          # ETH move over the month that just ended
    q = q[q.sell_date >= FIRST_SALE].reset_index(drop=True)
    return q, eth


_PATHS = {}


def month_path(eth, row, kind):
    """Hourly worst-case ETH price and option mark (per 1 ETH) while the option is open."""
    key = (row.sell_date, kind)
    if key not in _PATHS:
        _PATHS[key] = _month_path(eth, row, kind)
    return _PATHS[key]


def _month_path(eth, row, kind):
    t0 = row.sell_date + pd.Timedelta(hours=8)
    t1 = row.expiry + pd.Timedelta(hours=8)
    h = eth.loc[(eth.index >= t0) & (eth.index < t1)]
    s = h["low"] if kind == "P" else h["high"]
    t_left = ((t1 - h.index) / pd.Timedelta(days=365)).values
    mark = bs(s.values, row.strike, t_left, h["dvol"].values, kind)
    # intrinsic floor: the market never marks below intrinsic
    intrinsic = np.maximum(row.strike - s.values, 0) if kind == "P" else np.maximum(s.values - row.strike, 0)
    return s.values, np.maximum(mark, intrinsic)


def simulate(q, eth, variant, rule, start=0):
    rows, deficit, last_loss, realized = [], 0.0, 0.0, 0.0
    need_margin = need_unlev = 0.0
    for i in range(start, len(q)):
        r = q.iloc[i]
        if variant == "puts":
            kind = "P"
        elif variant == "calls":
            kind = "C"
        else:
            kind = "P" if r.prev_move >= 0 else "C"
        prem_unit = r[f"prem_net_{kind}"]
        base_units = BASE_NOTIONAL / r.spot
        if rule == "fixed":
            to_cover = 0.0
        elif rule == "martingale":
            to_cover = deficit
        else:
            to_cover = last_loss
        units = base_units + to_cover / prem_unit
        premium = units * prem_unit
        pnl = premium - units * r[f"payoff_{kind}"]

        # capital checks: opening margin, hourly maintenance margin, unlevered collateral
        s_path, mark_path = month_path(eth, r, kind)
        otm = max(r.spot - r.strike, 0) if kind == "P" else max(r.strike - r.spot, 0)
        im = units * (max(IM_RATE - otm / r.spot, MIN_IM_RATE) * r.spot + r[f"prem_{kind}"])
        mm_need = units * (MM_RATE * s_path + 2 * mark_path) - premium   # MM + unrealised loss
        need_margin = max(need_margin, im - realized, float(mm_need.max()) - realized)
        collateral = units * (r.strike if kind == "P" else r.spot)
        need_unlev = max(need_unlev, collateral - realized)

        realized += pnl
        deficit = max(0.0, deficit - pnl)
        last_loss = max(0.0, -pnl)
        rows.append(dict(
            month=r.expiry.strftime("%Y-%m"), sell_date=r.sell_date.date(), expiry=r.expiry.date(),
            side="PUT" if kind == "P" else "CALL", spot=r.spot, strike=r.strike, settle=r.settle,
            eth_move=r.settle / r.spot - 1, iv=r.iv, premium_pct=r[f"prem_{kind}"] / r.spot,
            size_eth=units, notional=units * r.spot, size_x=units / base_units, premium=premium,
            payoff=units * r[f"payoff_{kind}"], pnl=pnl, cum_pnl=realized, deficit_after=deficit,
            worst_intramonth_loss=float((units * mark_path - premium).max()),
        ))
    log = pd.DataFrame(rows)
    return log, max(need_margin, 0.0), max(need_unlev, 0.0)


def streaks(pnl):
    best = cur = 0
    for x in pnl:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


# worst monthly loss per $1 of notional seen in the sample, per side (ETH -35% / +48% months)
def worst_loss_rate(log):
    return (-(log.pnl / log.notional)).groupby(log.side).max().to_dict()


def summarize(log, need_margin, need_unlev, worst_rates):
    eq = log.cum_pnl
    dd = float((eq.cummax().clip(lower=0) - eq).max())
    # stress: the biggest position of each side hit by the worst month ever seen for that side
    stress = max(log[log.side == side].notional.max() * rate for side, rate in worst_rates.items()
                 if (log.side == side).any())
    return dict(
        months=len(log), losing_months=int((log.pnl < 0).sum()), max_loss_streak=streaks(log.pnl),
        total_pnl=eq.iloc[-1], avg_month_pnl=log.pnl.mean(), max_drawdown=dd,
        worst_month=log.pnl.min(), max_size_x=log.size_x.max(), max_notional=log.notional.max(),
        capital_margin=need_margin, capital_unlevered=need_unlev,
        return_on_margin_capital=eq.iloc[-1] / need_margin if need_margin else np.nan,
        ann_return_on_margin_capital=(1 + eq.iloc[-1] / need_margin) ** (12 / len(log)) - 1 if need_margin else np.nan,
        ends_with_open_deficit=log.deficit_after.iloc[-1],
        stress_worst_month_on_max_size=stress,
    )


VARIANTS = {"puts": "1 - Sell PUTS", "calls": "2 - Sell CALLS", "switch": "3 - Up->PUTS / Down->CALLS"}
RULES = ["martingale", "last_only", "fixed"]


def main():
    OUT.mkdir(exist_ok=True)
    q, eth = load()
    summary, logs = [], {}
    fixed_rates = {}
    for v in ("puts", "calls"):
        fixed_rates.update(worst_loss_rate(simulate(q, eth, v, "fixed")[0]))
    for v in VARIANTS:
        for rule in RULES:
            log, nm, nu = simulate(q, eth, v, rule)
            logs[(v, rule)] = log
            log.to_csv(OUT / f"trades_{v}_{rule}.csv", index=False, float_format="%.4f")
            s = summarize(log, nm, nu, fixed_rates)
            # robustness: the same strategy started in every possible month -> worst capital need
            starts = [simulate(q, eth, v, rule, start=k)[1:] for k in range(len(q))]
            s["capital_margin_worst_start"] = max(x[0] for x in starts)
            s["capital_unlevered_worst_start"] = max(x[1] for x in starts)
            s["ann_return_on_worst_start_capital"] = (
                (1 + s["total_pnl"] / s["capital_margin_worst_start"]) ** (12 / s["months"]) - 1)
            summary.append(dict(variant=VARIANTS[v], rule=rule, **s))
    summary = pd.DataFrame(summary)
    summary.to_csv(OUT / "summary.csv", index=False, float_format="%.2f")

    prem = pd.DataFrame(dict(
        month=q.expiry.dt.strftime("%Y-%m"), iv=q.iv, put_pct=q.prem_P / q.spot, call_pct=q.prem_C / q.spot,
        put_mark_pct=q.put_mark_eth, call_mark_pct=q.call_mark_eth,
        dvol_bs_pct=bs(q.spot, q.strike, q.t_years, eth["dvol"].reindex(q.sell_date + pd.Timedelta(hours=8)).values, "P") / q.spot,
    ))
    prem.to_csv(OUT / "premium_check.csv", index=False, float_format="%.4f")
    return q, summary, logs, prem


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 30)
    q, summary, logs, prem = main()
    print(summary.round(2).to_string())
    print(prem.describe().round(4))
