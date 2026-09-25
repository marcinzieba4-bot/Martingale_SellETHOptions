"""Martingale monthly ETH option-selling backtest (Jan 2023 - Sep 2026).

Every month, on Deribit's monthly expiry (last Friday, 08:00 UTC) we sell the at-the-money
option that expires on the next monthly expiry. Premium comes from the real Deribit implied
vol traded at that moment; settlement uses Deribit's real delivery price.

Variants ("last month" = the expiry-to-expiry cycle that just ended)
  1  PUTS          - always sell the ATM put
  2  CALLS         - always sell the ATM call
  3  SWITCH        - last month ETH went up -> sell a put, went down -> sell a call
  1b PUTS_UP       - sell a put only after an up month; otherwise stay flat
  2b CALLS_DOWN    - sell a call only after a down month; otherwise stay flat
                     (in 1b/2b the losses still to recover - and so the size - carry over skipped
                     months to the next month we are allowed to trade)
  3b SWITCH_HEDGED - 3 plus a perp hedge. Short put: if ETH trades below last month's low, short
                     the perp (same size as the option); stop it out if ETH trades above last
                     month's high; re-enter every time the low is broken again. Short call: long
                     perp above last month's high, stop below last month's low. Any open hedge is
                     closed at expiry together with the option.
  1c / 2c          - 1b / 2b with the same hedge
  3c               - 3b with the hedge on calls only (puts unhedged) - suggested after seeing 1c/2c

Sizing rules (the month's result includes the hedge P&L)
  fixed       - always the base size (no martingale; the reference)
  martingale  - size = base + (unrecovered losses) / premium-per-unit. A winning month pays the
                normal premium *plus* everything lost since the last reset; the size goes back to
                base as soon as the losses are recovered.
  last_only   - literal version: size = base + (last traded month's loss) / premium-per-unit.
                Resets after any profitable month even if older losses were not fully recovered.

Capital (all in USD, stablecoin-collateralised account)
  margin      - Deribit standard margin: an option needs 15% of notional + mark to open, 7.5% + mark
                to stay open; the perp hedge needs 2% of notional. Checked every hour at both the
                high and the low of the hour = minimum starting balance never liquidated.
  unlevered   - 1x notional set aside for every open option (cash-secured put / fully funded call)
                plus any running hedge loss
  drawdown    - deepest fall of the cumulative P&L (money actually lost at the worst point)
  safe        - margin capital for the worst start month + the loss if the worst month ever seen for
                that side (all months, with/without hedge) hit the biggest position once more
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
PERP_COST = 0.001             # perp taker fee 0.05% + 0.05% stop slippage, per fill
PERP_MARGIN = 0.02            # margin held against the perp hedge (Deribit futures IM ~2%)
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
    fund = pd.read_csv(DATA / "funding_hourly.csv", parse_dates=["time"]).set_index("time")["interest_1h"].tz_localize(None)
    fund.index = fund.index - pd.Timedelta(hours=1)            # stamped at the end of the hour it covers
    eth["funding"] = fund.reindex(eth.index).fillna(0.0)
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
    # high / low of the month that just ended (previous expiry 08:00 -> this sale 08:00)
    t = q.sell_date + pd.Timedelta(hours=8)
    q["prev_low"] = [eth.low[(eth.index >= a) & (eth.index < b)].min() for a, b in zip(t.shift(1), t)]
    q["prev_high"] = [eth.high[(eth.index >= a) & (eth.index < b)].max() for a, b in zip(t.shift(1), t)]
    q = q[q.sell_date >= FIRST_SALE].reset_index(drop=True)
    return q, eth


_PATHS = {}


def month_path(eth, row, kind):
    """Per-1-ETH hourly path while the option is open (cached): prices, option marks and hedge state."""
    key = (row.sell_date, kind)
    if key not in _PATHS:
        _PATHS[key] = _month_path(eth, row, kind)
    return _PATHS[key]


def _month_path(eth, row, kind):
    t0 = row.sell_date + pd.Timedelta(hours=8)
    t1 = row.expiry + pd.Timedelta(hours=8)
    h = eth.loc[(eth.index >= t0) & (eth.index < t1)]
    t_left = ((t1 - h.index) / pd.Timedelta(days=365)).values
    out = {"lo": h["low"].values, "hi": h["high"].values}
    for side in ("lo", "hi"):
        s = out[side]
        mark = bs(s, row.strike, t_left, h["dvol"].values, kind)
        intrinsic = np.maximum(row.strike - s, 0) if kind == "P" else np.maximum(s - row.strike, 0)
        out[f"mark_{side}"] = np.maximum(mark, intrinsic)   # the market never marks below intrinsic
    out.update(_hedge_path(h, kind, row.prev_low, row.prev_high, row.settle))
    return out


def _hedge_path(h, kind, low_prev, high_prev, settle):
    """Perp hedge for 1 ETH of short option. Put: short below last month's low, stop above last
    month's high. Call: long above last month's high, stop below last month's low. Re-enters on
    every new break; closed at expiry at the settlement price. Pays/receives real hourly funding."""
    pos, entry, realized, fills = 0, 0.0, 0.0, 0
    pos_a, entry_a, real_a = [], [], []
    for o, hi, lo, c, f in zip(h["open"].values, h["high"].values, h["low"].values, h["close"].values,
                               h["funding"].values):
        if pos == 0:
            if kind == "P" and lo <= low_prev:
                pos, entry = -1, min(o, low_prev)       # gap below the trigger fills at the open
            elif kind == "C" and hi >= high_prev:
                pos, entry = 1, max(o, high_prev)
            if pos:
                realized -= PERP_COST * entry
                fills += 1
        elif kind == "P" and hi >= high_prev:
            x = max(o, high_prev)
            realized += pos * (x - entry) - PERP_COST * x
            pos = 0
        elif kind == "C" and lo <= low_prev:
            x = min(o, low_prev)
            realized += pos * (x - entry) - PERP_COST * x
            pos = 0
        realized -= pos * f * c                          # positive funding: longs pay shorts
        pos_a.append(pos)
        entry_a.append(entry)
        real_a.append(realized)
    if pos:
        realized += pos * (settle - entry) - PERP_COST * settle
    return {"h_pos": np.array(pos_a), "h_entry": np.array(entry_a), "h_real": np.array(real_a),
            "hedge_pnl": realized, "hedge_fills": fills, "hedge_open_at_expiry": pos != 0}


def _switch(r):
    return "P" if r.prev_move >= 0 else "C"


def _puts_up(r):
    return "P" if r.prev_move >= 0 else None


def _calls_down(r):
    return "C" if r.prev_move < 0 else None


# key -> (label, which option to sell this month (None = stay flat), sides that get the perp hedge)
VARIANTS = {
    "puts": ("1 - Sell PUTS every month", lambda r: "P", ""),
    "calls": ("2 - Sell CALLS every month", lambda r: "C", ""),
    "switch": ("3 - Up->PUTS / Down->CALLS", _switch, ""),
    "puts_up": ("1b - PUTS only after an up month", _puts_up, ""),
    "calls_down": ("2b - CALLS only after a down month", _calls_down, ""),
    "switch_hedged": ("3b - Up->PUTS / Down->CALLS + perp hedge", _switch, "PC"),
    "puts_up_hedged": ("1c - 1b + perp hedge", _puts_up, "P"),
    "calls_down_hedged": ("2c - 2b + perp hedge", _calls_down, "C"),
    "switch_call_hedge": ("3c - 3b but hedge the CALLS only", _switch, "C"),
}
RULES = ["martingale", "last_only", "fixed"]


def simulate(q, eth, variant, rule, start=0):
    _, choose, hedge_sides = VARIANTS[variant]
    rows, deficit, last_loss, realized = [], 0.0, 0.0, 0.0
    need_margin = need_unlev = 0.0
    for i in range(start, len(q)):
        r = q.iloc[i]
        kind = choose(r)
        base = dict(month=r.expiry.strftime("%Y-%m"), sell_date=r.sell_date.date(), expiry=r.expiry.date(),
                    spot=r.spot, settle=r.settle, eth_move=r.settle / r.spot - 1, prev_move=r.prev_move,
                    prev_low=r.prev_low, prev_high=r.prev_high, iv=r.iv)
        if kind is None:   # not allowed to trade this month: flat, sizing state carries over
            rows.append(dict(base, side="-", strike=np.nan, premium_pct=np.nan, size_eth=0.0, notional=0.0,
                             size_x=0.0, premium=0.0, payoff=0.0, option_pnl=0.0, hedge_fills=0, hedge_pnl=0.0,
                             pnl=0.0, cum_pnl=realized, deficit_after=deficit, worst_intramonth_loss=0.0))
            continue
        hedged = kind in hedge_sides
        prem_unit = r[f"prem_net_{kind}"]
        base_units = BASE_NOTIONAL / r.spot
        to_cover = {"fixed": 0.0, "martingale": deficit, "last_only": last_loss}[rule]
        units = base_units + to_cover / prem_unit
        premium = units * prem_unit
        option_pnl = premium - units * r[f"payoff_{kind}"]
        p = month_path(eth, r, kind)
        hedge_pnl = units * p["hedge_pnl"] if hedged else 0.0
        pnl = option_pnl + hedge_pnl

        # capital checks: opening margin, hourly maintenance margin (at the hour's high and low),
        # unlevered collateral
        otm = max(r.spot - r.strike, 0) if kind == "P" else max(r.strike - r.spot, 0)
        im = units * (max(IM_RATE - otm / r.spot, MIN_IM_RATE) * r.spot + r[f"prem_{kind}"])
        worst_need = worst_hedge_loss = -np.inf
        worst_loss = 0.0
        for side in ("lo", "hi"):
            s, mark = p[side], p[f"mark_{side}"]
            h_eq = h_mm = 0.0
            if hedged:
                h_eq = units * (p["h_real"] + p["h_pos"] * (s - p["h_entry"]))
                h_mm = units * PERP_MARGIN * s * np.abs(p["h_pos"])
                worst_hedge_loss = max(worst_hedge_loss, float((-h_eq).max()))
            need = units * (MM_RATE * s + 2 * mark) + h_mm - h_eq - premium   # MM + unrealised loss
            worst_need = max(worst_need, float(need.max()))
            worst_loss = max(worst_loss, float((units * mark - premium - h_eq).max()))
        need_margin = max(need_margin, im - realized, worst_need - realized)
        collateral = units * (r.strike if kind == "P" else r.spot) + max(worst_hedge_loss, 0.0)
        need_unlev = max(need_unlev, collateral - realized)

        realized += pnl
        deficit = max(0.0, deficit - pnl)
        last_loss = max(0.0, -pnl)
        rows.append(dict(
            base, side="PUT" if kind == "P" else "CALL", strike=r.strike, premium_pct=r[f"prem_{kind}"] / r.spot,
            size_eth=units, notional=units * r.spot, size_x=units / base_units, premium=premium,
            payoff=units * r[f"payoff_{kind}"], option_pnl=option_pnl,
            hedge_fills=p["hedge_fills"] if hedged else 0, hedge_pnl=hedge_pnl, pnl=pnl, cum_pnl=realized,
            deficit_after=deficit, worst_intramonth_loss=worst_loss,
        ))
    log = pd.DataFrame(rows)
    return log, max(need_margin, 0.0), max(need_unlev, 0.0)


def streaks(pnl):
    best = cur = 0
    for x in pnl:
        cur = cur + 1 if x < 0 else 0
        best = max(best, cur)
    return best


def worst_loss_rates(q, eth, hedge_sides):
    """Worst single-month loss per $1 of notional seen in the sample for each side, over *all*
    months (not only the ones a variant traded) - used for the 'one more bad month' stress."""
    out = {}
    for kind, side in (("P", "PUT"), ("C", "CALL")):
        loss = q[f"payoff_{kind}"] - q[f"prem_net_{kind}"]
        if kind in hedge_sides:
            loss = loss - np.array([month_path(eth, r, kind)["hedge_pnl"] for _, r in q.iterrows()])
        out[side] = float((loss / q.spot).max())
    return out


def summarize(log, need_margin, need_unlev, worst_rates):
    eq = log.cum_pnl
    dd = float((eq.cummax().clip(lower=0) - eq).max())
    traded = log[log.side != "-"]
    # stress: the biggest position of each side hit by the worst month ever seen for that side
    stress = max(traded[traded.side == side].notional.max() * rate for side, rate in worst_rates.items()
                 if (traded.side == side).any())
    return dict(
        months=len(log), months_traded=len(traded), losing_months=int((traded.pnl < 0).sum()),
        max_loss_streak=streaks(traded.pnl), total_pnl=eq.iloc[-1], avg_month_pnl=traded.pnl.mean(),
        max_drawdown=dd, worst_month=traded.pnl.min(), max_size_x=traded.size_x.max(),
        max_notional=traded.notional.max(), hedge_fills=int(traded.hedge_fills.sum()),
        hedge_pnl=traded.hedge_pnl.sum(), capital_margin=need_margin, capital_unlevered=need_unlev,
        return_on_margin_capital=eq.iloc[-1] / need_margin if need_margin else np.nan,
        ann_return_on_margin_capital=(1 + eq.iloc[-1] / need_margin) ** (12 / len(log)) - 1 if need_margin else np.nan,
        ends_with_open_deficit=log.deficit_after.iloc[-1],
        stress_worst_month_on_max_size=stress,
    )


def main():
    OUT.mkdir(exist_ok=True)
    q, eth = load()
    summary, logs = [], {}
    for v, (label, _, hedge_sides) in VARIANTS.items():
        for rule in RULES:
            log, nm, nu = simulate(q, eth, v, rule)
            logs[(v, rule)] = log
            log.to_csv(OUT / f"trades_{v}_{rule}.csv", index=False, float_format="%.4f")
            s = summarize(log, nm, nu, worst_loss_rates(q, eth, hedge_sides))
            # robustness: the same strategy started in every possible month -> worst capital need
            starts = [simulate(q, eth, v, rule, start=k)[1:] for k in range(len(q))]
            s["capital_margin_worst_start"] = max(x[0] for x in starts)
            s["capital_unlevered_worst_start"] = max(x[1] for x in starts)
            s["ann_return_on_worst_start_capital"] = (
                (1 + s["total_pnl"] / s["capital_margin_worst_start"]) ** (12 / s["months"]) - 1)
            # what to actually hold: survive the worst start AND one more worst-ever month at peak size
            s["safe_capital"] = s["capital_margin_worst_start"] + s["stress_worst_month_on_max_size"]
            s["ann_return_on_safe_capital"] = (1 + s["total_pnl"] / s["safe_capital"]) ** (12 / s["months"]) - 1
            summary.append(dict(key=v, variant=label, rule=rule, **s))
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
    pd.set_option("display.width", 250, "display.max_columns", 40)
    q, summary, logs, prem = main()
    cols = ["variant", "rule", "months_traded", "losing_months", "max_loss_streak", "total_pnl", "max_drawdown",
            "worst_month", "max_size_x", "hedge_fills", "hedge_pnl", "capital_margin", "capital_margin_worst_start",
            "capital_unlevered_worst_start", "ann_return_on_worst_start_capital", "ends_with_open_deficit",
            "stress_worst_month_on_max_size"]
    print(summary[cols].round(2).to_string())
