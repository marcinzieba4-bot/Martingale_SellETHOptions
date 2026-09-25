"""Portfolio 1b + 3b on one account, martingale sizing, lean capital, risk statistics.

Book A = 1b : sell an ATM put only after an up month, no hedge.
Book B = 3b : after an up month sell an ATM put, after a down month an ATM call, each with the perp
              hedge (short below last month's low / long above last month's high, stop at the
              opposite extreme, re-entry allowed).
Each book runs its own full martingale (size = base + its own unrecovered losses / premium rate).
Both books share one USD account: margin, P&L and liquidation are checked on the combined position
every hour, at both the high and the low of the hour.

"Lean capital" = the smallest starting balance that never hit Deribit maintenance margin - no
buffer on top. Returns and risk are measured on that balance.

Everything is computed per $1 of notional, so a month can be re-used in any order: that is how the
Monte Carlo (block bootstrap of the 45 real months) estimates the chance of liquidation.
"""
import numpy as np
import pandas as pd

from backtest import (BASE_NOTIONAL, IM_RATE, MIN_IM_RATE, MM_RATE, OUT, PERP_MARGIN, load, month_path,
                      streaks)

BOOKS = {  # name -> (side chooser from last month's move, sides hedged)
    "1b": (lambda up: "P" if up else None, ""),
    "3b": (lambda up: "P" if up else "C", "PC"),
}
CAPITAL_MULTIPLES = [1.0, 1.5, 2.0, 3.0, 5.0]
LIQUIDATION_COST = 0.01   # forced close: 1% of the open notional on top of closing at the hour's worst price


def month_table(q, eth):
    """Per-month, per-side, per-hedge-flag rates per $1 of notional (hourly arrays included)."""
    months = []
    for _, r in q.iterrows():
        m = {"month": r.expiry.strftime("%Y-%m"), "up": bool(r.prev_move >= 0), "spot": r.spot,
             "settle": r.settle, "eth_move": r.settle / r.spot - 1}
        for kind in ("P", "C"):
            p = month_path(eth, r, kind)
            otm = max(r.spot - r.strike, 0) if kind == "P" else max(r.strike - r.spot, 0)
            prem_net = r[f"prem_net_{kind}"]
            for hedged in (False, True):
                need, mtm = {}, {}
                for side in ("lo", "hi"):
                    s, mark = p[side], p[f"mark_{side}"]
                    h_eq = (p["h_real"] + p["h_pos"] * (s - p["h_entry"])) if hedged else 0.0
                    h_mm = PERP_MARGIN * s * np.abs(p["h_pos"]) if hedged else 0.0
                    need[side] = (MM_RATE * s + 2 * mark + h_mm - h_eq - prem_net) / r.spot
                    mtm[side] = (prem_net - mark + h_eq) / r.spot
                m[(kind, hedged)] = dict(
                    prem=prem_net / r.spot,
                    pnl=(prem_net - r[f"payoff_{kind}"] + (p["hedge_pnl"] if hedged else 0.0)) / r.spot,
                    hedge=(p["hedge_pnl"] if hedged else 0.0) / r.spot,
                    fills=p["hedge_fills"] if hedged else 0,
                    im=(max(IM_RATE - otm / r.spot, MIN_IM_RATE) * r.spot + r[f"prem_{kind}"]) / r.spot,
                    need_lo=need["lo"], need_hi=need["hi"], mtm_lo=mtm["lo"], mtm_hi=mtm["hi"])
        months.append(m)
    return months


def run(months, seq, books=("1b", "3b"), base=BASE_NOTIONAL, detail=False, capital=None):
    """Run the books over the month sequence `seq` (indices into `months`).
    Returns required capital, P&L per month and, with detail=True, logs and hourly MTM equity.
    With `capital` given, the account is liquidated the first hour its equity falls below
    maintenance margin (or it cannot post margin for the next martingale step): positions are
    closed at that hour's worst price, trading stops, and `total` is what is left minus capital."""
    deficit = {b: 0.0 for b in books}
    realized, need_cap = 0.0, 0.0
    pnl_m, max_x, logs, hourly = [], {b: 0.0 for b in books}, [], []
    binding = None
    for i in seq:
        m = months[i]
        month_pnl, im_sum, notional_sum = 0.0, 0.0, 0.0
        need_lo = need_hi = mtm_lo = mtm_hi = 0.0
        for b in books:
            choose, hedge_sides = BOOKS[b]
            kind = choose(m["up"])
            if kind is None:
                if detail:
                    logs.append(dict(month=m["month"], book=b, side="-", size_x=0.0, notional=0.0, pnl=0.0,
                                     hedge_pnl=0.0, fills=0, deficit_after=deficit[b]))
                continue
            x = m[(kind, kind in hedge_sides)]
            notional = base + deficit[b] / x["prem"]
            pnl = notional * x["pnl"]
            month_pnl += pnl
            im_sum += notional * x["im"]
            notional_sum += notional
            need_lo = need_lo + notional * x["need_lo"]
            need_hi = need_hi + notional * x["need_hi"]
            mtm_lo = mtm_lo + notional * x["mtm_lo"]
            mtm_hi = mtm_hi + notional * x["mtm_hi"]
            max_x[b] = max(max_x[b], notional / base)
            deficit[b] = max(0.0, deficit[b] - pnl)
            if detail:
                logs.append(dict(month=m["month"], book=b, side="PUT" if kind == "P" else "CALL",
                                 size_x=notional / base, notional=notional, pnl=pnl,
                                 hedge_pnl=notional * x["hedge"], fills=x["fills"], deficit_after=deficit[b]))
        worst_need = max(np.max(need_lo), np.max(need_hi)) if np.ndim(need_lo) else 0.0
        if capital is not None:
            if im_sum - realized > capital:                  # cannot afford the next step
                return dict(capital=None, total=realized, ruined=True, ruin_month=len(pnl_m))
            if worst_need - realized > capital:              # margin call during the month
                hit = [np.flatnonzero(n - realized > capital) for n in (need_lo, need_hi)]
                t, side = min((h[0], j) for j, h in enumerate(hit) if len(h))
                loss = (mtm_lo, mtm_hi)[side][t] - LIQUIDATION_COST * notional_sum
                return dict(capital=None, total=realized + loss, ruined=True, ruin_month=len(pnl_m))
        if detail and np.ndim(need_lo) and worst_need - realized > need_cap:
            binding = (len(pnl_m), int(np.argmax(np.maximum(need_lo, need_hi))))
        need_cap = max(need_cap, im_sum - realized, worst_need - realized)
        if detail:
            worst_mtm = np.minimum(mtm_lo, mtm_hi) if np.ndim(mtm_lo) else np.array([0.0])
            hourly.append((realized, worst_mtm))
        realized += month_pnl
        pnl_m.append(month_pnl)
    out = dict(capital=need_cap, pnl=np.array(pnl_m), total=realized, max_x=max_x, ruined=False)
    if detail:
        out["log"] = pd.DataFrame(logs)
        out["hourly_mtm"] = hourly          # per month: (realised before it, worst open P&L each hour)
        out["binding"] = binding            # (month index, hour) where the margin need peaked
    return out


def risk_stats(res, capital, months_idx, months):
    pnl = res["pnl"]
    n = len(pnl)
    eq = capital + np.cumsum(pnl)
    eq0 = np.r_[capital, eq]
    peak = np.maximum.accumulate(eq0)
    dd = (peak - eq0) / peak
    # intramonth: hourly worst mark-to-market equity against the running peak of month-end equity
    peaks_before = peak[:-1]
    intra = max(float(((pk - (capital + rb + h)) / pk).max()) for pk, (rb, h) in zip(peaks_before, res["hourly_mtm"]))
    # time under water (months below the previous month-end peak)
    under, longest = 0, 0
    for d in dd[1:]:
        under = under + 1 if d > 1e-12 else 0
        longest = max(longest, under)
    r = pnl / capital
    down = r[r < 0]
    var95 = -np.quantile(r, 0.05)
    cvar95 = -r[r <= np.quantile(r, 0.05)].mean()
    log = res["log"]
    notional_by_month = log.groupby("month", sort=False).notional.sum()
    return {
        "Capital (lean)": capital,
        "Total P&L": res["total"],
        "Total return": res["total"] / capital,
        "Annual return (on starting capital)": (1 + res["total"] / capital) ** (12 / n) - 1,
        "Average month": r.mean(),
        "Median month": np.median(r),
        "Monthly volatility": r.std(ddof=1),
        "Sharpe (annualised, rf=0)": r.mean() / r.std(ddof=1) * np.sqrt(12),
        "Sortino (annualised)": r.mean() / np.sqrt((np.minimum(r, 0) ** 2).mean()) * np.sqrt(12),
        "Positive months": (r > 0).mean(),
        "Profit factor (gains / losses)": r[r > 0].sum() / -r[r < 0].sum(),
        "Average win / average loss": r[r > 0].mean() / -r[r < 0].mean(),
        "Best month": r.max(),
        "Worst month": r.min(),
        "VaR 95% (monthly)": var95,
        "CVaR 95% (monthly)": cvar95,
        "Max drawdown (month-end)": dd.max(),
        "Max drawdown (intramonth, hourly)": max(intra, dd.max()),
        "Calmar (annual return / max DD)": ((1 + res["total"] / capital) ** (12 / n) - 1) / max(intra, dd.max()),
        "Longest time under water (months)": longest,
        "Losing months": int((pnl < 0).sum()),
        "Max losing streak 1b / 3b": "{} / {}".format(*[streaks(log[(log.book == b) & (log.side != '-')].pnl) for b in ("1b", "3b")]),
        "Max size 1b / 3b (× base)": "{:.1f}× / {:.1f}×".format(res["max_x"]["1b"], res["max_x"]["3b"]),
        "Max combined notional": notional_by_month.max(),
        "Max notional / capital (leverage)": notional_by_month.max() / capital,
        "Largest open loss inside a month": max(float(-h.min()) for _, h in res["hourly_mtm"]) / capital,
        "_down_months": len(down),
    }


def stress_loss(months, log):
    """Loss if the worst month ever seen for each side (as each book trades it) hit the peak size."""
    worst = {}
    for kind in ("P", "C"):
        for hedged in (False, True):
            worst[(kind, hedged)] = -min(m[(kind, hedged)]["pnl"] for m in months)
    by_month = []
    for month, g in log[log.side != "-"].groupby("month", sort=False):
        loss = 0.0
        for _, r in g.iterrows():
            kind = "P" if r.side == "PUT" else "C"
            loss += r.notional * worst[(kind, r.book == "3b")]
        by_month.append(loss)
    return max(by_month), worst


def bootstrap(months, n_paths, horizon, block, lean, multiples=CAPITAL_MULTIPLES, seed=7):
    """Block bootstrap of the real months. Returns, per path, the capital the martingale would have
    needed, its P&L with unlimited capital, and for each capital level the outcome with liquidation."""
    rng = np.random.default_rng(seed)
    n = len(months)
    caps, totals, maxx = np.empty(n_paths), np.empty(n_paths), np.empty(n_paths)
    outcome = {m: np.empty(n_paths) for m in multiples}
    for k in range(n_paths):
        seq = []
        while len(seq) < horizon:
            s = rng.integers(n)
            seq += [(s + j) % n for j in range(block)]
        seq = seq[:horizon]
        res = run(months, seq)
        caps[k], totals[k] = res["capital"], res["total"]
        maxx[k] = max(res["max_x"].values())
        for m in multiples:   # only paths that needed more than this capital get liquidated
            outcome[m][k] = res["total"] if res["capital"] <= lean * m else run(months, seq, capital=lean * m)["total"]
    return caps, totals, maxx, outcome


def main(n_paths=20000):
    q, eth = load()
    months = month_table(q, eth)
    hist = list(range(len(months)))
    res = run(months, hist, detail=True)
    lean = res["capital"]
    worst_start = max(run(months, hist[k:])["capital"] for k in range(len(hist)))
    stats = {m: risk_stats(res, lean * m, hist, months) for m in CAPITAL_MULTIPLES}
    stress, worst_rates = stress_loss(months, res["log"])

    # single books for comparison
    singles = {}
    for books in (("1b",), ("3b",)):
        r1 = run(months, hist, books=books, detail=True)
        singles[books[0]] = (r1["capital"], r1["total"])

    mc = {}
    for horizon, block, paths in ((45, 3, n_paths), (45, 1, n_paths // 2), (45, 6, n_paths // 2), (120, 3, n_paths // 2)):
        caps, totals, maxx, outcome = bootstrap(months, paths, horizon, block, lean)
        mc[(horizon, block)] = dict(
            paths=paths,
            ruin={m: float((caps > lean * m).mean()) for m in CAPITAL_MULTIPLES},
            ruin_ws=float((caps > worst_start).mean()),
            p_loss_unlimited=float((totals < 0).mean()),
            ret_pct={p: float(np.percentile(totals, p)) / lean for p in (5, 25, 50, 75, 95)},
            cap_pct={p: float(np.percentile(caps, p)) / lean for p in (50, 75, 90, 95, 99)},
            maxx_pct={p: float(np.percentile(maxx, p)) for p in (50, 95, 99)},
            outcome={m: dict(mean=float(o.mean()) / (lean * m), median=float(np.median(o)) / (lean * m),
                             p5=float(np.percentile(o, 5)) / (lean * m), p_loss=float((o < 0).mean()),
                             loss_if_ruined=float(o[caps > lean * m].mean()) / (lean * m) if (caps > lean * m).any() else 0.0)
                     for m, o in outcome.items()},
            caps=caps, totals=totals)
    return dict(q=q, months=months, res=res, lean=lean, worst_start=worst_start, stats=stats, stress=stress,
                worst_rates=worst_rates, singles=singles, mc=mc)


if __name__ == "__main__":
    out = main()
    print("lean", out["lean"], "worst start", out["worst_start"], "stress", out["stress"])
    print("singles", out["singles"])
    s = pd.DataFrame(out["stats"]).drop(index="_down_months")
    print(s.to_string())
    for key, v in out["mc"].items():
        print(key, {k: v[k] for k in ("ruin", "ruin_ws", "p_loss_unlimited", "ret_pct", "cap_pct", "maxx_pct")})
        for m, o in v["outcome"].items():
            print("   ", m, {a: round(b, 3) for a, b in o.items()})
