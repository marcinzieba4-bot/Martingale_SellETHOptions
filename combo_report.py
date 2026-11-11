"""ETH 1b + 3b combined with the BTC session's put spread: charts and results/COMBO.md."""
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import combo as cb
from backtest import BASE_NOTIONAL, OUT
from report import INK, INK2, MUTED, SLOT, SURFACE, k, usd  # also applies the chart style

PICK = 1.0          # recommended BTC size per leg next to the $10k + $10k ETH base


def pct(x, d=0):
    return f"{x * 100:.{d}f}%"


def chart_equity(o, fname, title):
    q = o["q"]
    x = np.r_[q.sell_date.iloc[0], pd.to_datetime(q.expiry)]
    fig, ax = plt.subplots(figsize=(11, 4.6))
    series = [("eth", "ETH 1b + 3b (\\$10k + \\$10k base)", SLOT[0]),
              (("btc", PICK), f"BTC put spread ({PICK:g} BTC/leg)", SLOT[1]),
              (PICK, "Both on one account", SLOT[2])]
    ends = []
    for key, label, c in series:
        r, _ = o["runs"][key]
        y = np.r_[0, np.cumsum(r["pnl"])]
        ax.plot(x, y, color=c, lw=2.2 if key == PICK else 1.8, label=label)
        ends.append((y[-1], label, c))
    for y, label, c in ends:
        ax.annotate(k(y), (x[-1], y), xytext=(6, 0), textcoords="offset points", va="center", fontsize=9.5,
                    color=INK, weight="bold")
    ax.axhline(0, color=INK2, lw=1)
    ax.yaxis.set_major_formatter(lambda v, _: k(v))
    ax.xaxis.set_major_locator(mdates.YearLocator())
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    ax.set_ylabel("Cumulative P&L")
    ax.legend(loc="upper left", frameon=False, fontsize=9)
    ax.set_title(title, loc="left", fontsize=12, weight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=150)
    plt.close(fig)


def chart_scatter(o):
    df = o["corr"]["frame"]
    fig, ax = plt.subplots(figsize=(7.5, 5.2))
    no = df[~df.btc_trade]
    yes = df[df.btc_trade]
    ax.scatter(no.eth_pnl, no.btc_pnl, s=40, color=MUTED, edgecolor=SURFACE, lw=1.5,
               label="BTC: no trade (move under ±10%)", zorder=3)
    ax.scatter(yes.eth_pnl, yes.btc_pnl, s=55, color=SLOT[0], edgecolor=SURFACE, lw=1.5,
               label="BTC traded the spread", zorder=4)
    labels = {"2022-07": ("Jul 2022: ETH call lost, BTC spread won", (10, -4)),
              "2022-06": ("Jun 2022: the only BTC loss, ETH won", (10, -4)),
              "2022-11": ("Nov 2022 (FTX) / May 2024:\nETH lost, BTC no trade", (-10, 14))}
    for _, r in df[df.month.isin(labels)].iterrows():
        text, off = labels[r.month]
        ax.annotate(text, (r.eth_pnl, r.btc_pnl), xytext=off, textcoords="offset points", fontsize=8.5, color=INK2,
                    ha="left" if off[0] > 0 else "left")
    ax.axhline(0, color=INK2, lw=1)
    ax.axvline(0, color=INK2, lw=1)
    ax.xaxis.set_major_formatter(lambda v, _: k(v))
    ax.yaxis.set_major_formatter(lambda v, _: k(v))
    ax.set_xlabel("ETH 1b + 3b, monthly P&L")
    ax.set_ylabel("BTC put spread (1 BTC/leg), monthly P&L")
    c = o["corr"]
    ax.set_title(f"Month by month, Jan 2022 – Sep 2026 · correlation {c['corr_pnl']:+.2f}\n"
                 f"(ETH and BTC prices themselves: {c['corr_underlying']:+.2f}) · no month where both lost",
                 loc="left", fontsize=10.5, color=INK)
    ax.legend(frameon=False, fontsize=8.5, loc="lower left")
    fig.tight_layout()
    fig.savefig(OUT / "combo_scatter.png", dpi=150)
    plt.close(fig)


def chart_tradeoff(o, label):
    t = o["table"]
    rows = [t[t.key == "eth"].iloc[0]] + [t[t.key == str(b)].iloc[0] for b in cb.BTC_BASES]
    xs = [0.0] + cb.BTC_BASES
    mc = o["mc"]
    ruin = [mc[("eth", 1.0)]["ruin"]] + [mc[(b, 1.0)]["ruin"] for b in cb.BTC_BASES]
    fig, ax = plt.subplots(figsize=(10, 4.4))
    lines = [([r.ann_ret for r in rows], "Annual return on capital", SLOT[0]),
             (ruin, "Chance of a margin call (Monte Carlo)", SLOT[1]),
             ([r.crash_pct for r in rows], "Loss if ETH −35% and BTC −28% in the same month", SLOT[2])]
    for y, lab, c in lines:
        ax.plot(xs, np.array(y) * 100, color=c, lw=2, marker="o", ms=6, label=lab)
    ax.axvline(PICK, color=INK2, lw=1, ls="--")
    ax.annotate(f"suggested: {PICK:g} BTC/leg", (PICK, 102), xytext=(4, 0), textcoords="offset points", fontsize=9,
                color=INK2)
    ax.set_xticks(xs)
    ax.xaxis.set_major_formatter(lambda v, _: "ETH only" if v == 0 else f"+{v:g} BTC")
    ax.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    ax.set_ylim(0, 110)
    ax.set_xlabel("BTC put spread size per leg, next to ETH 1b + 3b at \\$10k + \\$10k base")
    ax.legend(frameon=False, fontsize=9, loc="center right")
    ax.set_title(f"What adding BTC buys and costs ({label}), capital = worst start month",
                 loc="left", fontsize=11.5, weight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "combo_tradeoff.png", dpi=150)
    plt.close(fig)


def table(o):
    t, mc = o["table"], o["mc"]
    rows = ["| Setup | Capital needed | Total P&L | Annual return | Sharpe | Worst month | Max DD month-end / intramonth | "
            "Losing months | Chance of margin call | Chance of a loss | Joint-crash loss |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in t.iterrows():
        key = "eth" if r.key == "eth" else (float(r.key) if r.eth else None)
        m = mc.get((key, 1.0)) if key is not None else None
        name = f"**{r.config}**" if r.key in ("eth", str(PICK)) else r.config
        rows.append(
            f"| {name} | {usd(r.capital)} | {usd(r.total)} | {pct(r.ann_ret, 1)} | {r.sharpe:.2f} | {pct(r.worst_month, 1)} | "
            f"{pct(r.dd_month, 1)} / {pct(r.dd_intra, 1)} | {r.losing_months} | {pct(m['ruin']) if m else '–'} | "
            f"{pct(m['p_loss']) if m else '–'} | {pct(r.crash_pct)} ({r.crash_month}) |")
    return "\n".join(rows)


def write(o23, o22):
    def row(o, key):
        return o["table"][o["table"].key == key].iloc[0]

    e23, c23, b23 = row(o23, "eth"), row(o23, str(PICK)), row(o23, str(("btc", PICK)))
    e22, c22, b22 = row(o22, "eth"), row(o22, str(PICK)), row(o22, str(("btc", PICK)))
    m23e, m23c = o23["mc"][("eth", 1.0)], o23["mc"][(PICK, 1.0)]
    m22e, m22c = o22["mc"][("eth", 1.0)], o22["mc"][(PICK, 1.0)]
    cr23, cr22 = o23["corr"], o22["corr"]
    w22 = cr22["btc_in_eth_worst5"]
    worst_lines = "\n".join(f"| {r.month} | {usd(r.eth_pnl)} | {usd(r.btc_pnl) if r.btc_trade else 'no trade'} |"
                            for _, r in w22.iterrows())
    crash = cb.joint_crash(o22["months"], o22["bm"], o22["runs"][PICK][0], o22["runs"][PICK][1])
    cw = crash["worst"]
    btc_tr = pd.read_csv(cb.BTC_DIR / "btc_spread_trades.csv", parse_dates=["expiry"])
    btc_tr = btc_tr[btc_tr.trade & (btc_tr.expiry >= "2022-01-01")]
    md = f"""# ETH 1b + 3b combined with the BTC put spread: do they diversify?

**The two strategies, both on Deribit monthly expiries (last Friday, 08:00 UTC), on one USD account:**

* **ETH 1b + 3b (this repo):**
  * 1b: sell an ATM ETH put only after an up month.
  * 3b: after an up month sell an ATM put, after a down month an ATM call, each hedged with the perp beyond
    last month's low or high.
  * Full martingale per strategy, base $10k + $10k notional, Deribit margin checked hourly.
* **BTC put spread, the BTC session's recommended version:**
  * Source: [SellBTCPuts_3M](https://github.com/marcinzieba4-bot/SellBTCPuts_3M), branch `claude/vibrant-dijkstra-b4l7vt`,
    `put_spread.py`, variant C, 20% wing.
  * If BTC moved more than ±10% last month, sell the 10% OTM put and buy the 20% OTM put. Otherwise skip the month.
  * No hedge. Loss recovery (base + loss to recover ÷ net credit), capped at 4× the base.
  * The spread is fully secured: its collateral is its maximum loss.
  * I ran the BTC repo's own code to get it month by month (`btc/fetch_btc_spread.py`). It matches that session's
    results exactly: $3,801 fixed and $4,207 with recovery at 0.25 BTC, Jan 2022 – Nov 2026.

**Windows:**
* **Jan 2023 – Sep 2026** (45 months): the ETH study period.
* **Jan 2022 – Sep 2026** (57 months): adds 2022 (LUNA, 3AC, FTX) as a stress year. I extended the ETH data back to 2022 for this.

**Capital in this report** is the smallest balance that never hit margin **for the worst possible start month**.
I did not use the Jan-2023 start this time. BTC never lost in 2023–2026, so its early profits would make
any later start look cheaper than it is. On this basis, ETH 1b + 3b alone needs {usd(e23.capital)}, not the {usd(e23.lean_jan23)}
"lean" figure from PORTFOLIO.md.

---

## Summary: what the results mean for you

1. **Yes, they diversify each other, even though ETH and BTC prices move together.**
   * ETH and BTC monthly price moves are correlated **{cr22['corr_underlying']:+.2f}** (2022–26).
   * The two strategies' monthly P&L is correlated only **{cr23['corr_pnl']:+.2f}** (2023–26) and **{cr22['corr_pnl']:+.2f}** (2022–26).
   * There was **no month in which both lost**. BTC lost once in 57 months (Jun 2022), and that month ETH made money.
   * In ETH's 5 worst months, BTC either had no trade or made money (table below).
   * **Why:** they lose in different situations.
     * ETH loses when a month moves hard against the side it sold. Mostly that was a rally against 3b's calls (Jul 2022, May 2024),
       and once a crash against both ETH puts (FTX, Nov 2022, when BTC had no trade).
     * BTC trades only after a ±10% month and sells 10% below the price. It loses only if BTC falls more than 10% in the month after a big move.
2. **The combination is better on almost every historical measure. The worst single month stays about the same.**
   With **{PICK:g} BTC per leg** next to ETH's $10k + $10k base (4× the BTC session's 0.25 BTC):

   | | ETH alone | ETH + BTC {PICK:g} BTC/leg |
   |---|---:|---:|
   | Capital needed | {usd(e23.capital)} | {usd(c23.capital)} |
   | Annual return, 2023–26 | {pct(e23.ann_ret, 1)} | **{pct(c23.ann_ret, 1)}** |
   | Annual return, 2022–26 | {pct(e22.ann_ret, 1)} | **{pct(c22.ann_ret, 1)}** |
   | Sharpe, 2023–26 / 2022–26 | {e23.sharpe:.2f} / {e22.sharpe:.2f} | **{c23.sharpe:.2f} / {c22.sharpe:.2f}** |
   | Max drawdown, month-end, 2022–26 | {pct(e22.dd_month, 1)} | **{pct(c22.dd_month, 1)}** |
   | Max drawdown, intramonth, 2022–26 | {pct(e22.dd_intra, 1)} | **{pct(c22.dd_intra, 1)}** |
   | Chance of a margin call (Monte Carlo), 2022–26 | {pct(m22e['ruin'])} | **{pct(m22c['ruin'])}** |
   | Chance of ending with a loss (Monte Carlo), 2022–26 | {pct(m22e['p_loss'])} | **{pct(m22c['p_loss'])}** |
   | Average result (Monte Carlo), 2022–26 | {m22e['mean'] * 100:+.0f}% | **{m22c['mean'] * 100:+.0f}%** |

   * BTC adds profit ({usd(b22.total)} at {PICK:g} BTC/leg over 2022–26) without adding capital.
   * BTC's collateral peaks in months when ETH needs little, and its steady profits cushion ETH's bad months.
3. **The catch: one scenario hits all three positions at once, and it never happened in 2022–2026.**
   * After a strong **up** month, 1b sells a put, 3b sells a put, and BTC (after a green candle) sells its spread.
   * A crash in the following month would hit all three.
   * In the data, every BTC trade after a green candle won, and ETH puts after up months lost only moderately.
   * **Stress test:** apply ETH −35% and BTC −28% (the worst months of the period) to the positions actually held.
     * The worst month for this is **{cw.month}**. It would have cost ETH {usd(cw.eth_loss)} plus BTC {usd(cw.btc_loss)}.
     * That is **{pct(crash['worst_pct'])} of capital** at {PICK:g} BTC/leg, against {pct(e22.crash_pct)} for ETH alone.
     * At 2 BTC/leg it is {pct(row(o22, '2.0').crash_pct)}, which wipes out the account.
   * **That is why I suggest {PICK:g} BTC per leg and not more.** In-sample, more BTC always looks better, because BTC
     almost never lost. That reflects the sample, not a real edge.
4. **What to do:**
   * Run both on one account: ETH 1b + 3b at your base, plus the BTC spread at about **{PICK / (2 * BASE_NOTIONAL) * 100_000:.0f} BTC per leg
     for every $100k of ETH base notional** (that is {PICK:g} BTC per $10k + $10k).
   * Hold about **{usd(c23.capital)} per $10k + $10k ETH base + {PICK:g} BTC/leg**. That is about what ETH alone
     needs ({usd(e23.capital)}).
   * Watch the months that follow a strong up month in both coins. ETH sells puts and BTC sells its spread at the same time,
     so that is where the joint-crash loss sits. A sensible extra rule (not backtested): in those months, if an ETH
     strategy is already above 2× its base, trade the BTC spread at its base size only, without recovery sizing.
   * The BTC spread's own risk is capped: max loss = (sold − bought strike − net credit) × size. Its collateral
     never needs topping up during the month.

![Cumulative P&L](combo_equity_2022.png)

![Month by month](combo_scatter.png)

![Trade-off](combo_tradeoff.png)

---

## How strongly do they move together?

| | 2023–2026 | 2022–2026 |
|---|---:|---:|
| ETH vs BTC price, same month | {cr23['corr_underlying']:+.2f} | {cr22['corr_underlying']:+.2f} |
| **ETH strategy vs BTC strategy, monthly P&L** | **{cr23['corr_pnl']:+.2f}** | **{cr22['corr_pnl']:+.2f}** |
| Same, rank correlation | {cr23['corr_pnl_spearman']:+.2f} | {cr22['corr_pnl_spearman']:+.2f} |
| Same, only months when BTC traded | {cr23['corr_pnl_btc_months']:+.2f} | {cr22['corr_pnl_btc_months']:+.2f} |
| BTC trade months | {cr23['btc_trade_months']} of 45 | {cr22['btc_trade_months']} of 57 |
| ETH losing months / BTC losing months | {cr23['eth_losing']} / {cr23['btc_losing']} | {cr22['eth_losing']} / {cr22['btc_losing']} |
| **Months where both lost** | **{cr23['both_losing']}** | **{cr22['both_losing']}** |

ETH's five worst months, 2022–2026, and what BTC did:

| Month | ETH 1b + 3b | BTC spread, 1 BTC/leg |
|---|---:|---:|
{worst_lines}

---

## Full results

**Jan 2023 – Sep 2026** (the ETH study period):

{table(o23)}

**Jan 2022 – Sep 2026** (with 2022):

{table(o22)}

How to read the columns:

* **Capital needed**: the smallest starting balance that never hit Deribit maintenance margin (ETH, checked hourly)
  plus the BTC spread's max loss, for the worst start month. Annual return, Sharpe and drawdowns are on this capital.
* **Chance of margin call / of a loss**: a joint block bootstrap of the real months (3-month blocks, {o22['mc_paths']:,} paths). ETH and BTC
  are drawn from the same months, so their dependence is kept. Liquidation is modelled as in PORTFOLIO.md.
* **Joint-crash loss**: the worst month for the scenario ETH −35% and BTC −28% at the same time, applied to the positions held. ETH puts lose their worst
  historical loss per $; BTC spreads lose their full max loss. Months where ETH sold calls are not hit.
* **"BTC spread alone"** rows: the BTC strategy alone. Its capital is the largest spread collateral (Jun 2025, the widest
  wing), so a joint-crash loss of 100% means it loses exactly that collateral. A fully secured spread cannot lose more.
  It lost once (Jun 2022), so its Sharpe is high but rests on very few losses.

## BTC spread trades used (1 BTC per leg)

| Expiry | Last month's BTC move | Sold / bought strike | Net credit | Max loss | P&L |
|---|---:|---|---:|---:|---:|
""" + "\n".join(f"| {r.expiry:%Y-%m} | {r.candle_ret:+.1%} | {r.sold_strike:,.0f} / {r.bought_strike:,.0f} | "
                f"{usd(r.credit - r.fees_entry)} | {usd(r.max_loss)} | {usd(r.pnl)} |" for _, r in btc_tr.iterrows()) + f"""

## Re-running

```bash
# 1) the BTC side, from the BTC session's repo (only needed to refresh btc/*.csv)
git clone -b claude/vibrant-dijkstra-b4l7vt https://github.com/marcinzieba4-bot/SellBTCPuts_3M /path/to/btc
BTC_REPO=/path/to/btc python3 btc/fetch_btc_spread.py
# 2) the combination
python3 combo_report.py
```
"""
    (OUT / "COMBO.md").write_text(md)


if __name__ == "__main__":
    o23 = cb.analyse("2022-12-30", n_paths=4000)
    o22 = cb.analyse("2021-12-31", n_paths=4000)
    o23["mc_paths"] = o22["mc_paths"] = 4000
    for o, tag in ((o23, "2023"), (o22, "2022")):
        o["table"].to_csv(OUT / f"combo_summary_{tag}.csv", index=False, float_format="%.4f")
        o["corr"]["frame"].to_csv(OUT / f"combo_monthly_{tag}.csv", index=False, float_format="%.2f")
    chart_equity(o22, "combo_equity_2022.png", "Cumulative P&L, Jan 2022 – Sep 2026 (2022 is the stress year)")
    chart_scatter(o22)
    chart_tradeoff(o22, "Jan 2022 – Sep 2026")
    write(o23, o22)
    print("wrote", OUT / "COMBO.md")
