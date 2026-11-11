"""What if ETH and BTC had crashed together right after a rally in 2024?

The real Jan 2023 - Sep 2026 history is used, with one month replaced by a crash:
  * ETH follows, hour by hour, its worst real month (31 Jan -> 28 Feb 2025: -35.3%), including
    that month's DVOL (implied vol spikes with the crash);
  * BTC follows its worst real month (27 May -> 24 Jun 2022: -28.0%);
  * every month after the crash is the real history, scaled down to the new lower price, so all
    later monthly moves (and the strategies' up/down and big-candle signals) are the real ones;
  * the month right after the crash sees the crash as "last month": ETH 3b sells a call, and the
    BTC strategy sees a -28% candle and sells its spread (priced from the real Deribit quotes of
    that date, as % of spot).
Crash months (both follow a rally of both coins, so 1b, 3b and BTC were all short the downside):
  Dec 2024 - after the Nov 2024 election rally (ETH +43%, BTC +42%); positions above base size
  Apr 2024 - after the March 2024 all-time-high rally (ETH +21%, BTC +37%); positions at base
Portfolio: ETH 1b + 3b (martingale, $10k + $10k base) + BTC put spread 1 BTC/leg (recovery, cap 4).
Capital: what that path needs to never hit margin (start Jan 2023), plus a cushion.
"""
import numpy as np
import pandas as pd

import combo as cb
import portfolio as pf
from backtest import load

ETH_TEMPLATE = pd.Timestamp("2025-02-28")
BTC_TEMPLATE = (pd.Timestamp("2022-05-27 08:00"), pd.Timestamp("2022-06-24 08:00"), 29032.13, 20902.87)
SCENARIOS = {"Dec 2024": pd.Timestamp("2024-12-27"), "Apr 2024": pd.Timestamp("2024-04-26")}
OHLC = ["open", "high", "low", "close"]
BTC_BASE, CUSHION = 1.0, 0.25


def eth_transform(crash_expiry, info):
    def tf(q, eth):
        q, eth = q.copy(), eth.copy()
        q[["spot", "strike", "settle"]] = q[["spot", "strike", "settle"]].astype(float)
        c = q.index[q.expiry == crash_expiry][0]
        tp = q.index[q.expiry == ETH_TEMPLATE][0]
        t0, t1 = q.sell_date[c] + pd.Timedelta(hours=8), q.expiry[c] + pd.Timedelta(hours=8)
        u0, u1 = q.sell_date[tp] + pd.Timedelta(hours=8), q.expiry[tp] + pd.Timedelta(hours=8)
        hours = eth.index[(eth.index >= t0) & (eth.index < t1)]
        tmpl = eth.loc[(eth.index >= u0) & (eth.index < u1), OHLC + ["dvol"]]
        tmpl = tmpl.iloc[:len(hours)]
        if len(tmpl) < len(hours):                       # pad a shorter template month with its last hour
            tmpl = pd.concat([tmpl, tmpl.iloc[[-1] * (len(hours) - len(tmpl))]])
        s0, ts0, ts1 = q.spot[c], q.spot[tp], q.settle[tp]
        vals = tmpl[OHLC].ffill().to_numpy() / ts0 * s0
        eth.loc[hours, OHLC] = vals
        eth.loc[hours, "dvol"] = tmpl["dvol"].ffill().to_numpy()
        crash_settle = s0 * ts1 / ts0
        f = crash_settle / q.settle[c]
        eth.loc[eth.index >= t1, OHLC] *= f
        q.loc[c, "settle"] = crash_settle
        later = q.sell_date >= q.expiry[c]
        q.loc[later, ["spot", "strike", "settle"]] *= f
        info.update(eth_f=f, eth_spot=s0, eth_settle=crash_settle, eth_low=vals[:, 2].min())
        return q, eth
    return tf


def btc_scenario(q, eth, crash_expiry, info):
    """BTC spread months for the scenario (per 1 BTC), built from the real ones."""
    bm, _ = cb.btc_months(q, eth)
    perp = pd.read_csv(cb.BTC_DIR / "btc_perp_1h.csv", parse_dates=["t"]).set_index("t")["close"]
    quotes = pd.read_csv(cb.BTC_DIR / "btc_put_quotes.csv", parse_dates=["entry"])
    trades = pd.read_csv(cb.BTC_DIR / "btc_spread_trades.csv", parse_dates=["entry", "expiry"])
    u0, u1, ts0, ts1 = BTC_TEMPLATE
    c = int(np.flatnonzero(q.expiry == crash_expiry)[0])
    real = trades[trades.expiry.dt.normalize() == crash_expiry].iloc[0]
    s0 = real.spot_entry
    crash_settle = s0 * ts1 / ts0
    f = crash_settle / real.spot_expiry
    info.update(btc_f=f, btc_spot=s0, btc_settle=crash_settle)

    def hours_of(i):
        t0 = q.sell_date[i] + pd.Timedelta(hours=8)
        t1 = q.expiry[i] + pd.Timedelta(hours=8)
        return eth.index[(eth.index >= t0) & (eth.index < t1)]

    def spread_mtm(path, k1, k2, credit_net):           # value at intrinsic (time value ignored)
        return credit_net - np.clip(k1 - path, 0, k1 - k2)

    out = []
    for i, b in enumerate(bm):
        if i < c:
            out.append(b)
        elif i == c:                                     # the crash month: the real trade, crashed path
            h = hours_of(i)
            tmpl = perp.reindex(u0 + pd.Timedelta(hours=1) + (h - h[0])).ffill().to_numpy()
            path = s0 * tmpl / ts0
            m = dict(b)
            m["mtm"] = spread_mtm(path, b["sold"], b["bought"], b["credit_net"])
            m["pnl"] = b["credit_net"] - min(max(b["sold"] - crash_settle, 0), b["sold"] - b["bought"]) \
                - 2 * 0.00015 * crash_settle
            m["mtm"][-1] = m["pnl"]
            info.update(btc_low=path.min())
            out.append(m)
        elif i == c + 1 and b is None:                   # a -28% candle: BTC now sells its spread
            t0 = q.sell_date[i] + pd.Timedelta(hours=8)
            qq = quotes[quotes.entry == t0]
            qq = qq[qq.expiry_code == qq.expiry_code.value_counts().index[0]] if len(qq) else qq
            spot_real = float(qq["index"].median())
            q1 = qq.iloc[(qq.strike - 0.9 * spot_real).abs().argsort()[:1]].iloc[0]
            q2 = qq.iloc[(qq.strike - 0.8 * spot_real).abs().argsort()[:1]].iloc[0]
            spot = spot_real * f
            k1, k2 = q1.strike / spot_real * spot, q2.strike / spot_real * spot
            p1, p2 = q1.premium_usd / spot_real * spot, q2.premium_usd / spot_real * spot
            credit_net = p1 - p2 - min(0.0003 * spot, 0.125 * p1) - min(0.0003 * spot, 0.125 * p2)
            h = hours_of(i)
            path = perp.reindex(h + pd.Timedelta(hours=1)).ffill().to_numpy() * f
            settle = path[-1]
            pnl = credit_net - min(max(k1 - settle, 0), k1 - k2)
            mtm = spread_mtm(path, k1, k2, credit_net)
            mtm[-1] = pnl
            out.append(dict(credit_net=credit_net, pnl=pnl, max_loss=(k1 - k2) - credit_net, mtm=mtm, spot=spot,
                            sold=k1, bought=k2, candle="red"))
            info.update(btc_new_trade=dict(sold=k1, bought=k2, credit=credit_net, pnl=pnl))
        elif b is None:
            out.append(None)
        else:                                            # later months: the real trade at the lower price
            m = dict(b)
            for key in ("credit_net", "pnl", "max_loss", "spot", "sold", "bought"):
                m[key] = b[key] * f
            m["mtm"] = b["mtm"] * f
            out.append(m)
    return out


def recovery_months(pnl, crash_i, capital):
    eq = capital + np.cumsum(pnl)
    peak = max(capital, eq[:crash_i].max()) if crash_i else capital
    after = np.flatnonzero(eq[crash_i:] >= peak)
    return int(after[0]) if len(after) else None


def run_scenario(name, first_sale="2022-12-30", eth_cap=None, btc_cap_x=4.0):
    info = {}
    if name is None:
        q, eth = load(first_sale)
    else:
        q, eth = load(first_sale, transform=eth_transform(SCENARIOS[name], info))
    months = pf.month_table(q, eth)
    if name is None:
        bm, _ = cb.btc_months(q, eth)
        crash_i = None
    else:
        bm = btc_scenario(q, eth, SCENARIOS[name], info)
        crash_i = int(np.flatnonzero(q.expiry == SCENARIOS[name])[0])
    seq = list(range(len(months)))
    res = {"both": pf.run(months, seq, detail=True, btc=dict(months=bm, base=BTC_BASE, cap=BTC_BASE * btc_cap_x),
                          eth_cap=eth_cap),
           "eth": pf.run(months, seq, detail=True, eth_cap=eth_cap)}
    return dict(name=name, q=q, eth=eth, months=months, bm=bm, res=res, crash_i=crash_i, info=info)


def summary(sc, which="both", capital=None, cushion=CUSHION):
    r = sc["res"][which]
    cap = capital if capital is not None else r["capital"] * (1 + cushion)
    st = cb.stats(r, cap)
    st["calmar_month_end"] = st["ann_ret"] / st["dd_month"] if st["dd_month"] else np.nan
    st["required"] = r["capital"]
    if sc["crash_i"] is not None:
        i = sc["crash_i"]
        log = r["log"]
        g = log[log.month == sc["months"][i]["month"]]
        st["crash_loss"] = r["pnl"][i]
        st["crash_parts"] = {b: float(g[g.book == b].pnl.sum()) for b in g.book.unique()}
        st["recovery"] = recovery_months(r["pnl"], i, cap)
        st["max_size"] = r["max_x"]
    return st


if __name__ == "__main__":
    base = run_scenario(None)
    for name in SCENARIOS:
        sc = run_scenario(name)
        print("=" * 10, name, sc["info"])
        for which in ("both", "eth"):
            s = summary(sc, which)
            print(which, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})
    for which in ("both", "eth"):
        s = summary(base, which)
        print("no crash", which, {k: (round(v, 3) if isinstance(v, float) else v) for k, v in s.items()})
