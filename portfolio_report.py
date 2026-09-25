"""Portfolio 1b + 3b: run, chart and write results/PORTFOLIO.md."""
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import portfolio as pf
from backtest import BASE_NOTIONAL, OUT
from report import INK, INK2, MUTED, SLOT, SURFACE, k, usd  # also applies the chart style

RED = "#e34948"


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def monthly_frame(out):
    res, lean, months = out["res"], out["lean"], out["months"]
    log = res["log"]
    rows = []
    eq_peak = lean
    for i, m in enumerate(months):
        a = log[(log.month == m["month"]) & (log.book == "1b")].iloc[0]
        b = log[(log.month == m["month"]) & (log.book == "3b")].iloc[0]
        pnl = res["pnl"][i]
        eq = lean + res["pnl"][: i + 1].sum()
        eq_peak = max(eq_peak, eq)
        rb, h = res["hourly_mtm"][i]
        rows.append(dict(month=m["month"], eth_move=m["eth_move"], last=("up" if m["up"] else "down"),
                         a_side=a.side, a_x=a.size_x, a_pnl=a.pnl, b_side=b.side, b_x=b.size_x,
                         b_hedge=b.hedge_pnl, b_fills=b.fills, b_pnl=b.pnl, pnl=pnl, ret=pnl / lean, equity=eq,
                         dd=(eq_peak - eq) / eq_peak, worst_open=float(-h.min())))
    return pd.DataFrame(rows)


def chart_equity(out, mf):
    q, lean = out["q"], out["lean"]
    fig, (ax, ax2) = plt.subplots(2, 1, figsize=(11, 6.2), sharex=True, gridspec_kw={"height_ratios": [2.2, 1]})
    # hourly worst mark-to-market equity
    peak = lean
    ts, eqh, ddh = [], [], []
    for i, (rb, h) in enumerate(out["res"]["hourly_mtm"]):
        t0 = q.sell_date.iloc[i] + pd.Timedelta(hours=8)
        t = t0 + pd.to_timedelta(np.arange(len(h)), unit="h")
        e = lean + rb + h
        ts.append(t)
        eqh.append(e)
        ddh.append(np.maximum((peak - e) / peak, 0.0))
        peak = max(peak, lean + rb + out["res"]["pnl"][i])
    ts, eqh, ddh = np.concatenate(ts), np.concatenate(eqh), np.concatenate(ddh)
    x = pd.to_datetime(q.expiry)
    ax.plot(ts, (eqh / lean - 1) * 100, color=MUTED, lw=0.8, label="Hourly, marked to market (worst price of each hour)")
    ax.plot(np.r_[q.sell_date.iloc[0], x], np.r_[0, mf.equity / lean - 1] * 100, color=SLOT[0], lw=2,
            label="Month-end (after settlement)")
    ax.axhline(0, color=INK2, lw=1)
    bi, bh = out["res"]["binding"]
    j = sum(len(h) for _, h in out["res"]["hourly_mtm"][:bi]) + bh
    ax.annotate(f"closest to a margin call ({pd.Timestamp(ts[j]):%d %b %Y}):\nequity = maintenance margin",
                (ts[j], (eqh[j] / lean - 1) * 100), xytext=(40, -6), textcoords="offset points", fontsize=8.5,
                color=INK2, arrowprops=dict(arrowstyle="-", color=INK2, lw=0.8))
    ax.yaxis.set_major_formatter(lambda y, _: f"{y:+.0f}%")
    ax.set_ylabel("Return on starting capital")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.annotate(f"+{mf.equity.iloc[-1] / lean * 100 - 100:.0f}%", (x.iloc[-1], (mf.equity.iloc[-1] / lean - 1) * 100),
                xytext=(6, 0), textcoords="offset points", va="center", fontsize=10, color=INK, weight="bold")
    ax.set_title(f"Account equity · 1b + 3b · martingale · lean capital {usd(lean)} per $10k + $10k base",
                 loc="left", fontsize=12, weight="bold", color=INK)
    ax2.fill_between(ts, -ddh * 100, 0, color=MUTED, alpha=0.5, lw=0, label="Intramonth (hourly)")
    ax2.plot(np.r_[q.sell_date.iloc[0], x], -np.r_[0, mf.dd] * 100, color=RED, lw=1.8, label="Month-end")
    ax2.yaxis.set_major_formatter(lambda y, _: f"{y:.0f}%")
    ax2.set_ylabel("Drawdown")
    ax2.legend(loc="lower left", frameon=False, fontsize=9, ncol=2)
    ax2.xaxis.set_major_locator(mdates.YearLocator())
    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    fig.savefig(OUT / "portfolio_equity.png", dpi=150)
    plt.close(fig)


def chart_monthly(mf):
    fig, ax = plt.subplots(figsize=(11, 3.8))
    x = pd.to_datetime(mf.month)
    ax.bar(x, mf.ret * 100, width=22, color=[SLOT[0] if r >= 0 else RED for r in mf.ret])
    for i in (mf.ret.idxmax(), mf.ret.idxmin()):
        r = mf.ret[i]
        ax.annotate(f"{mf.month[i]}  {r * 100:+.0f}%", (x[i], r * 100), xytext=(8, -4 if r > 0 else 0),
                    textcoords="offset points", ha="left", fontsize=8.5, color=INK2)
    ax.axhline(0, color=INK2, lw=1)
    ax.yaxis.set_major_formatter(lambda y, _: f"{y:+.0f}%")
    ax.set_title("Monthly return on starting capital (both books together)", loc="left", fontsize=12,
                 weight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "portfolio_monthly.png", dpi=150)
    plt.close(fig)


def chart_ruin(out):
    mc = out["mc"]
    mult = pf.CAPITAL_MULTIPLES
    fig, (a1, a2) = plt.subplots(1, 2, figsize=(11.5, 4.3))
    series = [((45, 3), "margin call within 45 months", SLOT[0], "ruin"),
              ((120, 3), "margin call within 10 years", SLOT[1], "ruin")]
    for key, label, c, _ in series:
        y = [mc[key]["ruin"][m] * 100 for m in mult]
        a1.plot(mult, y, color=c, lw=2, marker="o", ms=5, label=label)
    y = [mc[(45, 3)]["outcome"][m]["p_loss"] * 100 for m in mult]
    a1.plot(mult, y, color=SLOT[2], lw=2, marker="o", ms=5, label="ending 45 months with a loss")
    a1.set_xlabel("Capital, × lean capital")
    a1.set_ylabel("Probability")
    a1.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    a1.set_ylim(0, 100)
    a1.legend(frameon=False, fontsize=9)
    a1.set_title("Risk vs capital (block bootstrap, 3-month blocks)", loc="left", fontsize=11, color=INK)
    for key, label, c in (("mean", "average result", SLOT[0]), ("median", "median result", SLOT[1])):
        y = [mc[(45, 3)]["outcome"][m][key] * 100 for m in mult]
        a2.plot(mult, y, color=c, lw=2, marker="o", ms=5, label=label)
    y = [mc[(45, 3)]["outcome"][m]["p5"] * 100 for m in mult]
    a2.plot(mult, y, color=SLOT[2], lw=2, marker="o", ms=5, label="bad case (5th percentile)")
    a2.axhline(0, color=INK2, lw=1)
    a2.set_xlabel("Capital, × lean capital")
    a2.set_ylabel("45-month result, % of capital")
    a2.yaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%")
    a2.legend(frameon=False, fontsize=9)
    a2.set_title("Result after 45 months, liquidations included", loc="left", fontsize=11, color=INK)
    for ax in (a1, a2):
        ax.set_xticks(mult)
        ax.xaxis.set_major_formatter(lambda v, _: f"{v:g}×")
    fig.suptitle("Monte Carlo: the 45 real months reshuffled 20,000 times", x=0.01, ha="left", fontsize=12,
                 weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "portfolio_ruin.png", dpi=150)
    plt.close(fig)


def chart_capital_dist(out):
    caps = out["mc"][(45, 3)]["caps"] / out["lean"]
    fig, ax = plt.subplots(figsize=(11, 3.6))
    bins = np.logspace(np.log10(max(caps.min(), 0.1)), np.log10(caps.max()), 60)
    ax.hist(caps, bins=bins, color=SLOT[0], edgecolor=SURFACE, linewidth=0.5)
    ax.set_xscale("log")
    for m, lab, yf in ((1, "lean (real history)", 0.92), (out["worst_start"] / out["lean"], "worst start month", 0.78)):
        ax.axvline(m, color=INK, lw=1, ls="--")
        ax.annotate(lab, (m, ax.get_ylim()[1] * yf), xytext=(4, 0), textcoords="offset points", fontsize=9, color=INK)
    ax.set_xlim(0.1, 200)
    ax.xaxis.set_major_formatter(lambda v, _: f"{v:g}×")
    ax.set_xlabel("Capital the martingale needed on that path, × lean capital (log scale)")
    ax.set_ylabel("Paths")
    ax.set_title("How much capital 20,000 reshuffled 45-month histories needed", loc="left", fontsize=12,
                 weight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "portfolio_capital_needed.png", dpi=150)
    plt.close(fig)


def stats_table(out):
    stats = out["stats"]
    mult = pf.CAPITAL_MULTIPLES
    fmt = {
        "Capital (lean)": lambda v: usd(v),
        "Total P&L": lambda v: usd(v),
        "Max combined notional": lambda v: usd(v),
        "Max notional / capital (leverage)": lambda v: f"{v:.1f}×",
        "Sharpe (annualised, rf=0)": lambda v: f"{v:.2f}",
        "Sortino (annualised)": lambda v: f"{v:.2f}",
        "Calmar (annual return / max DD)": lambda v: f"{v:.2f}",
        "Profit factor (gains / losses)": lambda v: f"{v:.2f}",
        "Average win / average loss": lambda v: f"{v:.2f}",
        "Longest time under water (months)": lambda v: f"{v}",
        "Losing months": lambda v: f"{v} of 45",
    }
    rename = {"Capital (lean)": "Starting capital"}
    head = "| Risk statistic | " + " | ".join(f"**{m:g}× lean**" if m == 1 else f"{m:g}× lean" for m in mult) + " |"
    rows = [head, "|---|" + "---:|" * len(mult)]
    for key in stats[1.0]:
        if key.startswith("_"):
            continue
        cells = []
        for m in mult:
            v = stats[m][key]
            cells.append(v if isinstance(v, str) else fmt.get(key, lambda z: pct(z, 1))(v))
        rows.append(f"| {rename.get(key, key)} | " + " | ".join(cells) + " |")
    return "\n".join(rows)


def mc_table(out):
    mc, mult = out["mc"], pf.CAPITAL_MULTIPLES
    head = "| Monte Carlo (45 months, 3-month blocks) | " + " | ".join(f"{m:g}× lean" for m in mult) + " |"
    rows = [head, "|---|" + "---:|" * len(mult)]
    m45 = mc[(45, 3)]
    rows.append("| Starting capital per $10k + $10k base | " + " | ".join(usd(out["lean"] * m) for m in mult) + " |")
    rows.append("| **Chance of a margin call (liquidation)** | " + " | ".join(f"**{pct(m45['ruin'][m])}**" for m in mult) + " |")
    rows.append("| Chance of ending with a loss | " + " | ".join(pct(m45["outcome"][m]["p_loss"]) for m in mult) + " |")
    rows.append("| Average result | " + " | ".join(f"{m45['outcome'][m]['mean'] * 100:+.0f}%" for m in mult) + " |")
    rows.append("| Median result | " + " | ".join(f"{m45['outcome'][m]['median'] * 100:+.0f}%" for m in mult) + " |")
    rows.append("| Bad case (5th percentile) | " + " | ".join(f"{m45['outcome'][m]['p5'] * 100:+.0f}%" for m in mult) + " |")
    rows.append("| Average result of the paths that got liquidated | " + " | ".join(
        f"{m45['outcome'][m]['loss_if_ruined'] * 100:+.0f}%" for m in mult) + " |")
    for (h, b), label in (((45, 1), "Margin call, 1-month blocks (no streaks kept)"),
                          ((45, 6), "Margin call, 6-month blocks (long streaks kept)"),
                          ((120, 3), "Margin call within 10 years (3-month blocks)")):
        rows.append(f"| {label} | " + " | ".join(pct(mc[(h, b)]["ruin"][m]) for m in mult) + " |")
    return "\n".join(rows)


def log_table(mf):
    rows = ["| Month | ETH | Last month | 1b trade | 1b P&L | 3b trade | 3b hedge | 3b P&L | Month P&L | Return | Equity | Drawdown | Worst open loss |",
            "|---|---:|---|---|---:|---|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in mf.iterrows():
        a = f"PUT {r.a_x:.2f}×" if r.a_side != "-" else "–"
        b = f"{r.b_side} {r.b_x:.2f}×"
        h = f"{usd(r.b_hedge)} ({int(r.b_fills)})" if r.b_fills else "–"
        rows.append(f"| {r.month} | {r.eth_move:+.1%} | {r.last} | {a} | {usd(r.a_pnl) if r.a_side != '-' else '–'} | {b} | "
                    f"{h} | {usd(r.b_pnl)} | {usd(r.pnl)} | {r.ret * 100:+.1f}% | {usd(r.equity)} | {r.dd * 100:.1f}% | "
                    f"{usd(r.worst_open)} |")
    return "\n".join(rows)


def write(out, mf):
    lean, ws, st = out["lean"], out["worst_start"], out["stats"][1.0]
    m45, m120 = out["mc"][(45, 3)], out["mc"][(120, 3)]
    o1, o2 = m45["outcome"][1.0], m45["outcome"][2.0]
    per100 = 100_000 / lean * BASE_NOTIONAL
    s1b, s3b = out["singles"]["1b"], out["singles"]["3b"]
    worst = mf.loc[mf.ret.idxmin()]
    deepest = mf.loc[mf.dd.idxmax()]
    md = f"""# Portfolio 1b + 3b: martingale on lean capital, with risk statistics

**Setup:** one USD account (stablecoin collateral) running two strategies at the same time. Each strategy has
its own martingale.

* **1b:** sell an ATM ETH put only after an up month, with no hedge.
* **3b:** after an up month sell an ATM put, after a down month sell an ATM call. Each is hedged with the perp:
  short below last month's low (for a put) or long above last month's high (for a call). The stop is at the opposite extreme,
  and the hedge re-enters on every new break.
* **Martingale:** each strategy sizes its next trade as base + (its own losses still to recover) ÷ premium. It goes back
  to base once those losses are recovered. The two strategies do not share losses.
* **Base trade:** ${BASE_NOTIONAL:,.0f} of ETH notional per strategy. Every $ figure scales linearly.
* **Lean capital:** the **least money the account needed**. It is the smallest starting balance that never fell below
  Deribit maintenance margin, checked every hour at the hour's high and low, for both strategies together.
  There is no safety buffer. All returns and risk figures below are measured on this balance, unless a column says otherwise.
* **Data:** real Deribit data from Jan 2023 to Sep 2026 (45 monthly expiries), including option IV, perp prices, funding and fees.

---

## Summary: what the results mean for you

1. **Lean capital is {usd(lean)} per $10k + $10k of base trades.** With **$100k, each strategy trades a base of about
   {k(per100)} notional.** Both strategies together need less than 3b alone ({usd(s3b[0])}), because 1b's early profits
   act as a cushion.
2. **Historical result on lean capital: {usd(st['Total P&L'])}, which is {pct(st['Total return'])} in 45 months, or about
   {pct(st['Annual return (on starting capital)'])}/yr.**
   * {pct(st['Positive months'])} of months were profitable.
   * Sharpe {st['Sharpe (annualised, rf=0)']:.2f}, Sortino {st['Sortino (annualised)']:.2f}, profit factor {st['Profit factor (gains / losses)']:.1f}.
   * 1b alone made {usd(s1b[1])} and 3b alone made {usd(s3b[1])}.
3. **The risk at lean capital, from the real path:**
   * Worst month: **{pct(st['Worst month'], 1)}** ({worst.month}).
   * VaR 95%: {pct(st['VaR 95% (monthly)'], 1)} a month. CVaR 95%: {pct(st['CVaR 95% (monthly)'], 1)}.
   * Max drawdown: **{pct(st['Max drawdown (month-end)'], 1)}** on month-end equity ({deepest.month}), and **{pct(st['Max drawdown (intramonth, hourly)'], 1)}**
     intramonth at the worst hour.
   * Positions reached **{st['Max notional / capital (leverage)']:.1f}× the capital** in notional ({st['Max size 1b / 3b (× base)']} base size for 1b / 3b).
   * The longest time under water was {st['Longest time under water (months)']} months.
   * **By construction, the account touched maintenance margin once.** One more bad hour would have meant liquidation.
4. **Monte Carlo on the martingale's tail risk.** I reshuffled the 45 real months in 3-month blocks, 20,000 times:
   * **At lean capital, {pct(m45['ruin'][1.0])} of paths hit a margin call within 45 months.** Over 10 years it is {pct(m120['ruin'][1.0])}.
     In those paths, the martingale needed more money than the real history did.
   * A margin call does not wipe out the account. Liquidated paths had made profits before, so on average they ended
     at {o1['loss_if_ruined'] * 100:+.0f}% of capital. Including them, lean capital returned **{o1['mean'] * 100:+.0f}% on average**
     (median {o1['median'] * 100:+.0f}%) over 45 months.
     **{pct(o1['p_loss'])} of paths ended with a loss.** The bad case (5th percentile) was {o1['p5'] * 100:+.0f}%.
   * **With 2× lean capital** ({usd(lean * 2)}), the margin-call chance drops to {pct(m45['ruin'][2.0])}, and the chance of a loss to {pct(o2['p_loss'])}.
     The average return falls to {o2['mean'] * 100:+.0f}%.
   * If the martingale had unlimited capital, it would end in profit in {pct(1 - m45['p_loss_unlimited'], 1)} of paths. But the capital needed
     has a fat tail: the median path needed {m45['cap_pct'][50]:.1f}× lean, 10% of paths needed {m45['cap_pct'][90]:.1f}×,
     and 1% needed {m45['cap_pct'][99]:.0f}×. The largest multiplier was {m45['maxx_pct'][95]:.0f}× in 5% of paths and {m45['maxx_pct'][99]:.0f}× in 1%.
5. **How to run it lean without being liquidated:**
   * Keep **a second lean-sized amount off the exchange as a top-up reserve** (about {usd(lean)} per $10k + $10k base).
     Move it in only when a margin call comes. That is the 2× column. About {pct(m45['ruin'][1.0])} of paths would use the reserve,
     and {pct(m45['ruin'][2.0])} would need more than both amounts together.
   * Starting at a bad moment needs more capital. The worst start month in history needed {usd(ws)} ({ws / lean:.1f}× lean).
   * The biggest danger is a run of losing calls in a strong rally, like May–Jul 2025, where 3b's size grows fastest.
     If 3b's multiplier goes above {out['res']['max_x']['3b']:.0f}×, you are outside anything the real history produced. That is the moment
     to add capital or stop the martingale.

![Equity and drawdown](portfolio_equity.png)

![Monthly returns](portfolio_monthly.png)

---

## Risk statistics on the real path

The first column is lean capital. The other columns show the same trades on more capital, for comparison. The Sharpe
ratio stays the same, while leverage, drawdown and return scale down.

{stats_table(out)}

Definitions:

* Monthly figures are P&L divided by starting capital. Sizes do not compound, so returns are not reinvested.
* The intramonth drawdown uses the hourly marked-to-market equity, at the worst price of each hour, against the previous
  month-end peak.
* "Largest open loss inside a month" is the worst unrealised loss on the open positions at any hour.

## Monte Carlo: chance of liquidation and final result

{mc_table(out)}

![Risk vs capital](portfolio_ruin.png)

![Capital needed](portfolio_capital_needed.png)

How the Monte Carlo works:

* Each path draws months from the real 45 in blocks of 3 consecutive months, keeping some of the real losing streaks.
* Every month keeps its own real price path, implied vol, hedge fills and "last month up/down" signal.
* Both strategies run their martingales on the path.
* **A margin call is the first hour the combined equity falls below Deribit maintenance margin**, or when the next
  martingale step cannot be opened. At that point, everything is closed at that hour's worst price, minus a 1% liquidation cost, and trading stops.
* Blocks of 1 month (no streaks) and 6 months (long streaks) are shown as the plausible range.
* The month-to-month clustering of real markets is only partly captured, so treat these figures as estimates, not precise odds.

---

## Month by month (lean capital {usd(lean)})

{log_table(mf)}

"Worst open loss" is the largest unrealised loss on both strategies at any hour of that month.
The data is also in `results/portfolio_monthly.csv`.

## Re-running

```bash
python3 portfolio_report.py   # about 3 minutes, mostly the Monte Carlo
```

To change the base size, liquidation cost or capital multiples, edit `portfolio.py`.
"""
    (OUT / "PORTFOLIO.md").write_text(md)


if __name__ == "__main__":
    out = pf.main()
    mf = monthly_frame(out)
    mf.to_csv(OUT / "portfolio_monthly.csv", index=False, float_format="%.4f")
    stats = pd.DataFrame(out["stats"]).drop(index="_down_months")
    stats.to_csv(OUT / "portfolio_risk_stats.csv")
    chart_equity(out, mf)
    chart_monthly(mf)
    chart_ruin(out)
    chart_capital_dist(out)
    write(out, mf)
    print("wrote", OUT / "PORTFOLIO.md")
