"""ETH 1b + 3b (this repo) combined with the BTC session's recommended BTC put spread.

BTC strategy (from marcinzieba4-bot/SellBTCPuts_3M, put_spread.py, variant C, 20% wing; extracted
by btc/fetch_btc_spread.py): after a month in which BTC moved more than +/-10%, sell the 10% OTM put
and buy the 20% OTM put for the next monthly expiry, no hedge; otherwise skip. Base 0.25 BTC per leg,
loss recovery (0.25 + unrecovered loss / net credit), capped at 4x the base (1 BTC at 0.25).

Both run on one USD account. ETH keeps its Deribit margin (checked hourly); the BTC spread is fully
secured (collateral = its max loss). Both expire on the same Deribit monthly dates, so every month is
one row for both.

Windows:
  2023-01 .. 2026-09  the ETH study period (45 months)
  2022-01 .. 2026-09  adds 2022 (LUNA, 3AC, FTX) as a stress test for both (57 months)
"""
import numpy as np
import pandas as pd

import portfolio as pf
from backtest import BASE_NOTIONAL, ROOT, load

BTC_DIR = ROOT / "btc"
WINDOWS = {"2023-01 – 2026-09": "2022-12-30", "2022-01 – 2026-09": "2021-12-31"}
BTC_BASES = [0.25, 0.5, 1.0, 2.0]
CAP_X = 4.0          # BTC recovery size cap, x base (the BTC session's "capped at 1 BTC" for 0.25)


def btc_months(q, eth):
    """BTC spread trade aligned to each ETH month (None = no BTC trade that month), per 1 BTC."""
    tr = pd.read_csv(BTC_DIR / "btc_spread_trades.csv", parse_dates=["entry", "expiry"])
    hr = pd.read_csv(BTC_DIR / "btc_spread_hourly.csv", parse_dates=["entry", "time"])
    tr = tr.set_index(tr.expiry.dt.normalize())
    out, info = [], []
    for _, r in q.iterrows():
        t0 = r.sell_date + pd.Timedelta(hours=8)
        t1 = r.expiry + pd.Timedelta(hours=8)
        hours = eth.index[(eth.index >= t0) & (eth.index < t1)]
        b = tr.loc[r.expiry.normalize()] if r.expiry.normalize() in tr.index else None
        assert b is not None, f"no BTC row for {r.expiry.date()}"
        assert b.entry.normalize() == r.sell_date.normalize(), "BTC and ETH cycles differ"
        info.append(dict(month=r.expiry.strftime("%Y-%m"), btc_move=b.candle_ret, btc_trade=bool(b.trade)))
        if not b.trade:
            out.append(None)
            continue
        path = hr[hr.entry == b.entry].set_index("time").mtm
        mtm = path.reindex(hours + pd.Timedelta(hours=1)).ffill().fillna(path.iloc[0]).to_numpy().copy()
        mtm[-1] = b.pnl                                   # settles at expiry
        out.append(dict(credit_net=b.credit - b.fees_entry, pnl=b.pnl, max_loss=b.max_loss, mtm=mtm,
                        spot=b.spot_entry, sold=b.sold_strike, bought=b.bought_strike, candle=b.candle))
    return out, pd.DataFrame(info)


def stats(res, capital):
    pnl = res["pnl"]
    n = len(pnl)
    eq0 = np.r_[capital, capital + np.cumsum(pnl)]
    peak = np.maximum.accumulate(eq0)
    dd = (peak - eq0) / peak
    intra = max(float(((pk - (capital + rb + h)) / pk).max()) for pk, (rb, h) in zip(peak[:-1], res["hourly_mtm"]))
    r = pnl / capital
    ann = (1 + res["total"] / capital) ** (12 / n) - 1
    q5 = np.quantile(r, 0.05)
    return {
        "capital": capital, "total": res["total"], "total_ret": res["total"] / capital, "ann_ret": ann,
        "vol_m": r.std(ddof=1), "sharpe": r.mean() / r.std(ddof=1) * np.sqrt(12),
        "sortino": r.mean() / np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(12),
        "pos_months": (r > 0).mean(), "worst_month": r.min(), "var95": -q5, "cvar95": -r[r <= q5].mean(),
        "dd_month": dd.max(), "dd_intra": max(intra, dd.max()), "calmar": ann / max(intra, dd.max()),
        "losing_months": int((pnl < 0).sum()),
    }


def run_cfg(months, bm, seq, eth_on=True, btc_base=None, detail=True, capital=None):
    btc = dict(months=bm, base=btc_base, cap=btc_base * CAP_X) if btc_base else None
    return pf.run(months, seq, books=("1b", "3b") if eth_on else (), detail=detail, capital=capital, btc=btc)


def correlation(months, bm, info, res_eth, res_btc):
    """Scale-free dependence between the two strategies, month by month."""
    df = info.copy()
    df["eth_move"] = [m["eth_move"] for m in months]
    df["eth_pnl"], df["btc_pnl"] = res_eth["pnl"], res_btc["pnl"]
    both = df[df.btc_trade]
    worst_eth = df.nsmallest(5, "eth_pnl")
    return dict(
        frame=df,
        corr_pnl=df.eth_pnl.corr(df.btc_pnl), corr_pnl_spearman=df.eth_pnl.corr(df.btc_pnl, method="spearman"),
        corr_pnl_btc_months=both.eth_pnl.corr(both.btc_pnl),
        corr_underlying=df.eth_move.corr(df.btc_move.shift(-1)),   # same month: BTC move of the cycle traded
        btc_trade_months=int(df.btc_trade.sum()), eth_losing=int((df.eth_pnl < 0).sum()),
        btc_losing=int((df.btc_pnl < 0).sum()), both_losing=int(((df.eth_pnl < 0) & (df.btc_pnl < 0)).sum()),
        btc_in_eth_worst5=worst_eth[["month", "eth_pnl", "btc_pnl", "btc_trade"]],
    )


def bootstrap(months, bm, n_paths, horizon, block, cfgs, seed=11):
    """Joint block bootstrap: the same resampled months for ETH and BTC, so their dependence is kept.
    cfgs: name -> (eth_on, btc_base, capital). Returns P(margin call), mean and median result, P(loss)."""
    rng = np.random.default_rng(seed)
    n = len(months)
    out = {k: dict(ruin=0, res=[]) for k in cfgs}
    for _ in range(n_paths):
        seq = []
        while len(seq) < horizon:
            s = rng.integers(n)
            seq += [(s + j) % n for j in range(block)]
        seq = seq[:horizon]
        for name, (eth_on, btc_base, cap) in cfgs.items():
            r = run_cfg(months, bm, seq, eth_on, btc_base, detail=False)
            if r["capital"] > cap:
                out[name]["ruin"] += 1
                r = run_cfg(months, bm, seq, eth_on, btc_base, detail=False, capital=cap)
            out[name]["res"].append(r["total"] / cap)
    return {k: dict(ruin=v["ruin"] / n_paths, mean=float(np.mean(v["res"])), median=float(np.median(v["res"])),
                    p_loss=float((np.array(v["res"]) < 0).mean()), p5=float(np.percentile(v["res"], 5)))
            for k, v in out.items()}


def worst_start_capital(months, bm, eth_on, btc_base):
    """Smallest balance that never hit margin, for the worst of all possible start months."""
    n = len(months)
    return max(run_cfg(months, bm, list(range(k, n)), eth_on, btc_base, detail=False)["capital"] for k in range(n))


def joint_crash(months, bm, res, capital, eth_on=True):
    """Stress: the crash that never came - ETH -35% and BTC -28% in the same month (both worst monthly
    falls of 2022-2026), applied to the positions actually open in every month where ETH sold puts.
    ETH puts lose their worst historical loss per $ notional (1b unhedged, 3b hedged); a -28% BTC
    month is below the 20% OTM wing, so the spread loses its full max loss."""
    worst = {(k, h): -min(m[(k, h)]["pnl"] for m in months) for k in ("P", "C") for h in (False, True)}
    log = res["log"]
    rows = []
    for i, m in enumerate(months):
        g = log[log.month == m["month"]]
        eth_loss = 0.0
        if eth_on:
            for _, r in g[g.book.isin(["1b", "3b"]) & (g.side == "PUT")].iterrows():
                eth_loss += r.notional * worst[("P", r.book == "3b")]
        b = g[(g.book == "btc") & (g.side == "SPREAD")]
        btc_loss = float((b.size_btc * bm[i]["max_loss"]).sum()) if len(b) and bm[i] is not None else 0.0
        if eth_loss or btc_loss:
            rows.append(dict(month=m["month"], eth_loss=eth_loss, btc_loss=btc_loss, total=eth_loss + btc_loss))
    df = pd.DataFrame(rows)
    top = df.loc[df.total.idxmax()]
    base_month = df[(df.eth_loss > 0) & (df.btc_loss > 0)]
    typical = base_month.total.median() if len(base_month) else np.nan
    return dict(worst=top, worst_pct=top.total / capital, typical_pct=typical / capital,
                months_both=int(len(base_month)), worst_rates=worst)


def analyse(first_sale, n_paths=3000, bases=BTC_BASES):
    q, eth = load(first_sale)
    months = pf.month_table(q, eth)
    bm, info = btc_months(q, eth)
    seq = list(range(len(months)))
    out = dict(q=q, months=months, bm=bm, info=info, seq=seq)
    eth_res = run_cfg(months, bm, seq, True, None)
    btc1 = run_cfg(months, bm, seq, False, 1.0)                 # per 1 BTC per leg (scale-free checks)
    out["corr"] = correlation(months, bm, info, eth_res, btc1)
    out["runs"], rows = {}, []
    configs = [("eth", "ETH 1b + 3b alone", True, None)]
    for b in bases:
        configs += [(("btc", b), f"BTC spread alone, {b:g} BTC/leg", False, b),
                    (b, f"ETH + BTC {b:g} BTC/leg", True, b)]
    for key, label, eth_on, b in configs:
        r = run_cfg(months, bm, seq, eth_on, b)
        cap = worst_start_capital(months, bm, eth_on, b)
        out["runs"][key] = (r, cap)
        crash = joint_crash(months, bm, r, cap, eth_on)
        rows.append(dict(key=str(key), config=label, btc_base=b or 0.0, eth=eth_on,
                         max_btc=r["max_x"].get("btc", 0.0) * (b or 0.0), lean_jan23=r["capital"],
                         crash_pct=crash["worst_pct"], crash_month=crash["worst"].month, **stats(r, cap)))
    out["table"] = pd.DataFrame(rows)
    # Monte Carlo (joint block bootstrap): ETH alone vs ETH + BTC, each on its own worst-start capital
    cfgs = {("eth", 1.0): (True, None, out["runs"]["eth"][1])}
    for b in bases:
        cfgs[(b, 1.0)] = (True, b, out["runs"][b][1])
    out["mc"] = bootstrap(months, bm, n_paths, len(months), 3, cfgs)
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 250, "display.max_columns", 40)
    for label, fs in WINDOWS.items():
        o = analyse(fs, n_paths=500)
        print("=" * 20, label)
        cols = ["config", "max_btc", "lean_jan23", "capital", "total", "ann_ret", "sharpe", "worst_month", "dd_month",
                "dd_intra", "calmar", "losing_months", "crash_pct", "crash_month"]
        print(o["table"][cols].round(3).to_string())
        c = o["corr"]
        print({k: (round(v, 3) if isinstance(v, float) else v) for k, v in c.items() if k not in ("frame", "btc_in_eth_worst5")})
        print(c["btc_in_eth_worst5"].round(1).to_string())
        for k, v in o["mc"].items():
            print(k, {a: round(x, 3) for a, x in v.items()})
