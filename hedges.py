"""Hedges for the "danger months" of ETH 1b + 3b + BTC put spread.

Danger month: ETH rose last month (1b and 3b both sell an ATM put) AND BTC had a big green candle
(the BTC strategy sells its put spread). All three are short the downside at once; a crash right
after the rally hits all of them (scenario.py). 13 of 45 months in Jan 2023 - Sep 2026.

Hedges, applied in danger months only:
  eth_put15 / eth_put20 - buy the 15% / 20% OTM ETH put (same expiry), 1 per ETH put sold, at its real
                          Deribit price (data/eth_otm_put_quotes.csv). Marked hourly with its traded
                          implied vol moved by DVOL. Its cost is taken out of the premium the
                          martingale counts on, and its payoff counts in the month's result.
  eth_delta             - daily delta hedge of the ETH puts with the perp: every day at 08:00 UTC short
                          put-delta x size (Black-Scholes, ATM IV moved by DVOL), 0.1% per fill,
                          real funding. Replaces 3b's last-month-low trigger hedge in those months.
  btc_w15               - BTC buys the 15% OTM put instead of the 20% one (narrower spread, real quotes).
  btc_skip              - no BTC trade in danger months.
"""
import numpy as np
import pandas as pd

import combo as cb
from backtest import DATA, DELIVERY_FEE_RATE, FEE_RATE, PERP_COST, PERP_MARGIN, bs, norm_cdf

VARIANTS = {
    "none": {},
    "eth_put20": dict(eth="put", mny=0.80),
    "eth_put15": dict(eth="put", mny=0.85),
    "eth_delta": dict(eth="delta"),
    "btc_w15": dict(btc="w15"),
    "btc_skip": dict(btc="skip"),
    "eth_put20+btc_w15": dict(eth="put", mny=0.80, btc="w15"),
    "eth_put15+btc_w15": dict(eth="put", mny=0.85, btc="w15"),
    "eth_put20+btc_skip": dict(eth="put", mny=0.80, btc="skip"),
    "eth_delta+btc_w15": dict(eth="delta", btc="w15"),
}
LABELS = {
    "none": "No hedge",
    "eth_put20": "ETH: buy 20% OTM put",
    "eth_put15": "ETH: buy 15% OTM put",
    "eth_delta": "ETH: daily delta hedge",
    "btc_w15": "BTC: 15% wing instead of 20%",
    "btc_skip": "BTC: skip the trade",
    "eth_put20+btc_w15": "ETH 20% put + BTC 15% wing",
    "eth_put15+btc_w15": "ETH 15% put + BTC 15% wing",
    "eth_put20+btc_skip": "ETH 20% put + skip BTC",
    "eth_delta+btc_w15": "ETH delta hedge + BTC 15% wing",
}


def danger_flags(months, bm20):
    return [bool(m["up"] and b is not None and b["candle"] == "green") for m, b in zip(months, bm20)]


def btc_base(q, eth, months, variant):
    """BTC months before any crash is applied: the 20% wing, with the variant's change in danger months."""
    bm20, _ = cb.btc_months(q, eth)
    danger = danger_flags(months, bm20)
    btc = VARIANTS[variant].get("btc")
    if btc == "w15":
        bm15, _ = cb.btc_months(q, eth, suffix="_w15")
        return [b15 if d else b for b, b15, d in zip(bm20, bm15, danger)], danger
    if btc == "skip":
        return [None if d else b for b, d in zip(bm20, danger)], danger
    return bm20, danger


def _hours(q, eth, i):
    t0 = q.sell_date.iloc[i] + pd.Timedelta(hours=8)
    t1 = q.expiry.iloc[i] + pd.Timedelta(hours=8)
    return eth.loc[(eth.index >= t0) & (eth.index < t1)], t1


def _tail_put(q, eth, i, quotes, mny):
    """Per $1 of ETH notional: hourly value (lo/hi), cost and payoff of the protective put."""
    r = q.iloc[i]
    qq = quotes[(quotes.sell_date == r.sell_date) & (quotes.moneyness == mny)]
    if len(qq):
        k_ratio, prem_rate, iv = qq.strike.iloc[0] / qq.spot.iloc[0], qq.mark_eth.iloc[0], qq.iv.iloc[0] / 100
    else:   # no trade at that strike: price it from the 15% OTM put's implied vol
        alt = quotes[(quotes.sell_date == r.sell_date)].iloc[0]
        k_ratio, iv = mny, alt.iv / 100
        prem_rate = float(bs(1.0, k_ratio, r.t_years, iv, "P"))
    k = k_ratio * r.spot
    h, t1 = _hours(q, eth, i)
    t_left = ((t1 - h.index) / pd.Timedelta(days=365)).values
    dv = h["dvol"].values / h["dvol"].values[0]
    prem = prem_rate * r.spot
    cost = prem + min(FEE_RATE * r.spot, 0.125 * prem)
    vals = {}
    for side, col in (("lo", "low"), ("hi", "high")):
        s = h[col].values
        v = np.maximum(bs(s, k, t_left, iv * dv, "P"), np.maximum(k - s, 0))
        vals[side] = v
    payoff = max(k - r.settle, 0.0)
    if payoff > 0:
        payoff -= min(DELIVERY_FEE_RATE * r.settle, 0.125 * payoff)
    for side in vals:
        vals[side][-1] = payoff
    return dict(val_lo=vals["lo"] / r.spot, val_hi=vals["hi"] / r.spot, cost=cost / r.spot, payoff=payoff / r.spot)


def _delta_hedge(q, eth, i):
    """Per $1 of ETH notional of a short ATM put: daily (08:00 UTC) delta hedge with the perp."""
    r = q.iloc[i]
    h, t1 = _hours(q, eth, i)
    t_left = np.maximum(((t1 - h.index) / pd.Timedelta(days=365)).values, 1e-9)
    vol = r.iv * h["dvol"].values / h["dvol"].values[0]
    o = h["open"].values
    sd = vol * np.sqrt(t_left)
    d1 = (np.log(o / r.strike) + 0.5 * sd ** 2) / sd
    short_put_delta = 1 - norm_cdf(d1)              # long exposure of a short put = -(N(d1) - 1)
    pos, cash, fees, fund = 0.0, 0.0, 0.0, 0.0
    pos_a, cash_a = np.zeros(len(h)), np.zeros(len(h))
    for j in range(len(h)):
        if j == 0 or h.index[j].hour == 8:
            target = -short_put_delta[j]               # short perp
            d = target - pos
            cash -= d * o[j]
            fees += abs(d) * o[j] * PERP_COST
            pos = target
        fund -= pos * h["funding"].values[j] * h["close"].values[j]
        pos_a[j], cash_a[j] = pos, cash - fees + fund
    final = cash - fees + fund + pos * r.settle - abs(pos) * r.settle * PERP_COST
    out = {}
    for side, col in (("lo", "low"), ("hi", "high")):
        s = h[col].values
        eq = cash_a + pos_a * s
        eq[-1] = final
        out[f"eq_{side}"] = eq / r.spot
        out[f"mm_{side}"] = PERP_MARGIN * s * np.abs(pos_a) / r.spot
    out["pnl"] = final / r.spot
    out["pos0"] = abs(pos_a[0])
    return out


def apply_eth(months, q, eth, variant, danger):
    """Return a copy of `months` with the variant's ETH hedge in danger months."""
    v = VARIANTS[variant]
    if "eth" not in v:
        return months
    quotes = pd.read_csv(DATA / "eth_otm_put_quotes.csv", parse_dates=["sell_date"])
    out = []
    for i, m in enumerate(months):
        if not danger[i]:
            out.append(m)
            continue
        m = dict(m)
        if v["eth"] == "put":
            tp = _tail_put(q, eth, i, quotes, v["mny"])
            for hedged in (False, True):
                x = dict(m[("P", hedged)])
                net = {s: tp[f"val_{s}"] - tp["cost"] for s in ("lo", "hi")}
                x.update(prem=x["prem"] - tp["cost"], pnl=x["pnl"] + tp["payoff"] - tp["cost"],
                         hedge=x["hedge"] + tp["payoff"] - tp["cost"], im=x["im"] + tp["cost"],
                         need_lo=x["need_lo"] - net["lo"], need_hi=x["need_hi"] - net["hi"],
                         mtm_lo=x["mtm_lo"] + net["lo"], mtm_hi=x["mtm_hi"] + net["hi"])
                m[("P", hedged)] = x
        else:   # daily delta hedge on top of the unhedged put, for both books
            dh = _delta_hedge(q, eth, i)
            base = m[("P", False)]
            x = dict(base)
            x.update(pnl=base["pnl"] + dh["pnl"], hedge=dh["pnl"], fills=0,
                     im=base["im"] + PERP_MARGIN * dh["pos0"],
                     need_lo=base["need_lo"] + dh["mm_lo"] - dh["eq_lo"],
                     need_hi=base["need_hi"] + dh["mm_hi"] - dh["eq_hi"],
                     mtm_lo=base["mtm_lo"] + dh["eq_lo"], mtm_hi=base["mtm_hi"] + dh["eq_hi"])
            m[("P", False)] = x
            m[("P", True)] = x
        out.append(m)
    return out
