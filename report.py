"""Run the backtest, draw the charts and write REPORT.md."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

from backtest import BASE_NOTIONAL, OUT, VARIANTS, main  # noqa: E402

COLORS = {"puts": "#2a78d6", "calls": "#eb6834", "switch": "#1baf7a"}
SHORT = {"puts": "1 · Puts", "calls": "2 · Calls", "switch": "3 · Switch"}
INK, INK2, GRID, SURFACE = "#0b0b0b", "#52514e", "#e4e3df", "#fcfcfb"

plt.rcParams.update({
    "figure.facecolor": SURFACE, "axes.facecolor": SURFACE, "savefig.facecolor": SURFACE,
    "axes.edgecolor": GRID, "axes.labelcolor": INK2, "xtick.color": INK2, "ytick.color": INK2,
    "text.color": INK, "font.size": 10, "axes.spines.top": False, "axes.spines.right": False,
    "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8, "axes.axisbelow": True,
})


def usd(x):
    return f"-${abs(x):,.0f}" if x < 0 else f"${x:,.0f}"


def k(x):
    return f"-${abs(x) / 1000:,.1f}k" if x < 0 else f"${x / 1000:,.1f}k"


def chart_equity(logs):
    fig, axes = plt.subplots(1, 2, figsize=(11, 4.2), sharey=True)
    for ax, rule, title in zip(axes, ("martingale", "fixed"), ("Martingale sizing", "Fixed size (no martingale)")):
        for v in VARIANTS:
            log = logs[(v, rule)]
            x = pd.to_datetime(log.expiry)
            ax.plot(x, log.cum_pnl, color=COLORS[v], lw=2, label=SHORT[v])
            ax.annotate(f"{SHORT[v]}  {k(log.cum_pnl.iloc[-1])}", (x.iloc[-1], log.cum_pnl.iloc[-1]),
                        xytext=(6, 0), textcoords="offset points", va="center", fontsize=9, color=INK)
        ax.axhline(0, color=INK2, lw=1)
        ax.set_title(title, loc="left", fontsize=11, color=INK)
        ax.yaxis.set_major_formatter(lambda y, _: k(y))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0].set_ylabel(f"Cumulative P&L (base trade = ${BASE_NOTIONAL:,.0f} notional)")
    axes[1].legend(loc="upper left", frameon=False)
    fig.suptitle("Cumulative P&L, Jan 2023 – Sep 2026", x=0.01, ha="left", fontsize=12, weight="bold")
    fig.tight_layout()
    fig.subplots_adjust(right=0.86)
    fig.savefig(OUT / "equity.png", dpi=150)
    plt.close(fig)


def chart_size(logs):
    fig, axes = plt.subplots(3, 1, figsize=(11, 6.5), sharex=True, sharey=True)
    for ax, v in zip(axes, VARIANTS):
        log = logs[(v, "martingale")]
        x = pd.to_datetime(log.expiry)
        ax.bar(x, log.size_x, width=22, color=COLORS[v])
        loss = log.pnl < 0
        ax.scatter(x[loss], log.size_x[loss] + 1.2, marker="v", s=18, color=INK2, zorder=3)
        ax.set_title(f"{VARIANTS[v]} · max {log.size_x.max():.1f}× base", loc="left", fontsize=10, color=INK)
        ax.set_ylabel("× base size")
    axes[0].annotate("▼ = losing month", (0.99, 0.85), xycoords="axes fraction", ha="right", fontsize=9, color=INK2)
    fig.suptitle("Position size with martingale sizing (1× = base trade)", x=0.01, ha="left", fontsize=12, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "position_size.png", dpi=150)
    plt.close(fig)


def chart_premium(prem):
    fig, ax = plt.subplots(figsize=(11, 3.6))
    x = pd.to_datetime(prem.month)
    avg = (prem.put_pct + prem.call_pct) / 2 * 100
    ax.bar(x, avg, width=22, color=COLORS["puts"])
    ax.axhline(7, color=INK, lw=1, ls="--")
    ax.annotate("7% assumption", (x.iloc[0], 7.2), fontsize=9, color=INK)
    ax.yaxis.set_major_formatter(lambda y, _: f"{y:.0f}%")
    ax.set_title("ATM 1-month ETH option premium, % of ETH price (avg of put & call, real Deribit IV)",
                 loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "premium.png", dpi=150)
    plt.close(fig)


def table(summary, rules):
    rows = ["| Variant | Sizing | Total P&L | Losing months | Max losing streak | Biggest position | Worst month | "
            "Max drawdown | Capital (margin) | Capital (margin, worst start) | Capital (no leverage, worst start) | "
            "Return/yr on worst-start capital |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in summary[summary.rule.isin(rules)].iterrows():
        rows.append(
            f"| {r.variant} | {r.rule} | **{usd(r.total_pnl)}** | {r.losing_months}/{r.months} | {r.max_loss_streak} | "
            f"{r.max_size_x:.1f}× ({usd(r.max_notional)}) | {usd(r.worst_month)} | {usd(r.max_drawdown)} | "
            f"{usd(r.capital_margin)} | **{usd(r.capital_margin_worst_start)}** | {usd(r.capital_unlevered_worst_start)} | "
            f"{r.ann_return_on_worst_start_capital:.1%} |")
    return "\n".join(rows)


def month_table(log):
    rows = ["| Month | Side | ETH start → settle | Move | IV | Premium | Size | Notional | P&L | Cum. P&L | Losses to recover |",
            "|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in log.iterrows():
        rows.append(f"| {r.month} | {r.side} | {r.spot:,.0f} → {r.settle:,.0f} | {r.eth_move:+.1%} | {r.iv:.0%} | "
                    f"{r.premium_pct:.1%} | {r.size_x:.2f}× | {usd(r.notional)} | {usd(r.pnl)} | {usd(r.cum_pnl)} | "
                    f"{usd(r.deficit_after)} |")
    return "\n".join(rows)


def write_report(q, summary, logs, prem):
    S = summary.set_index(["variant", "rule"])
    g = {v: S.loc[(VARIANTS[v], "martingale")] for v in VARIANTS}
    f = {v: S.loc[(VARIANTS[v], "fixed")] for v in VARIANTS}
    lo = {v: S.loc[(VARIANTS[v], "last_only")] for v in VARIANTS}
    both = (prem.put_pct + prem.call_pct) / 2
    by_year = prem.assign(year=prem.month.str[:4], both=both).groupby("year").agg(
        iv=("iv", "mean"), prem=("both", "mean"), lo=("both", "min"), hi=("both", "max"))
    year_rows = "\n".join(f"| {y} | {r.iv:.0%} | {r.prem:.1%} | {r.lo:.1%} – {r.hi:.1%} |" for y, r in by_year.iterrows())
    eth0, eth1 = q.spot.iloc[0], q.settle.iloc[-1]

    md = f"""# Martingale ETH option selling: backtest, Jan 2023 to Sep 2026

Every month, on Deribit's monthly expiry (the last Friday, 08:00 UTC), the strategy sells the
at-the-money ETH option that expires one month later. It is held to expiry and settled at
Deribit's real delivery price.

* **Variant 1: puts.** Sell an ATM put every month.
* **Variant 2: calls.** Sell an ATM call every month.
* **Variant 3: switch.** If ETH rose last month, sell a put. If it fell, sell a call.
* **Martingale sizing.** After a losing month, the next position is made large enough that its premium
  covers the losses still to be recovered, plus the normal premium. Once those losses are recovered,
  the size goes back to the base size.

All dollar figures are for a **base trade of ${BASE_NOTIONAL:,.0f} ETH notional** (about $650–700 of premium
a month). Every figure scales linearly: for a $50k base trade, multiply by 5.

Period: 45 monthly trades, from the Jan-2023 expiry (sold 30 Dec 2022) to the Sep-2026 expiry (25 Sep 2026).
ETH went from ${eth0:,.0f} to ${eth1:,.0f}.

---

## Summary: what the results mean for you

1. **The 7% premium only holds on average in high-volatility years.** An ATM one-month ETH option paid
   **{both.mean():.1%} on average** (median {both.median():.1%}). Only **{(both >= 0.07).mean():.0%} of months paid 7% or more**.
   In calm periods it fell to **{both.min():.1%}** (2023: {by_year.loc['2023', 'prem']:.1%} on average). Plan on about 6.5%, not 7%,
   and on 3–4% when implied vol is near 30%.
2. **Variant 1 (puts) is the only one that works without a martingale.** Fixed-size puts made {usd(f['puts'].total_pnl)}.
   Fixed-size calls lost {usd(abs(f['calls'].total_pnl))} and the fixed-size switch broke even ({usd(f['switch'].total_pnl)}). ETH rallies of +20% to +48% in a month
   hurt call sellers much more than the crashes hurt put sellers.
3. **The martingale raised profits here, but only by taking on very large exposures.** It does not change the
   odds. It trades many small losses for rare, very large ones. Profits rose to {usd(g['puts'].total_pnl)} (puts), {usd(g['calls'].total_pnl)} (calls) and {usd(g['switch'].total_pnl)} (switch).
   To get there, the position had to grow to **{g['puts'].max_size_x:.1f}×**, **{g['calls'].max_size_x:.1f}×** and **{g['switch'].max_size_x:.1f}×**
   the base size. The longest losing streak in all three variants was only {g['puts'].max_loss_streak:.0f} months. One more losing
   month at the peak size would have cost about {k(g['puts'].stress_worst_month_on_max_size)}, {k(g['calls'].stress_worst_month_on_max_size)}
   and {k(g['switch'].stress_worst_month_on_max_size)}, based on the worst month seen for each side.
4. **Capital needed**, taking the worst possible start month and never being liquidated (Deribit margin, checked every hour):
   * **Puts: about {k(g['puts'].capital_margin_worst_start)}** ({g['puts'].capital_margin_worst_start / BASE_NOTIONAL:.1f}× the base notional).
     Fully cash-secured, with no leverage: {k(g['puts'].capital_unlevered_worst_start)}.
   * **Calls: about {k(g['calls'].capital_margin_worst_start)}** ({g['calls'].capital_margin_worst_start / BASE_NOTIONAL:.1f}×). With no leverage: {k(g['calls'].capital_unlevered_worst_start)}.
     It also **finished Sep 2026 with {usd(g['calls'].ends_with_open_deficit)} of losses not yet recovered**, holding a {logs[('calls','martingale')].size_x.iloc[-1]:.0f}× position.
   * **Switch: about {k(g['switch'].capital_margin_worst_start)}** ({g['switch'].capital_margin_worst_start / BASE_NOTIONAL:.1f}×). With no leverage: {k(g['switch'].capital_unlevered_worst_start)}.
   * Keep a buffer of **2–3× these figures**. A losing streak one month longer than any in 2023–2026
     would roughly triple the position again (each loss of about 20% against about 7% of premium multiplies the size by about 3).
5. **What to do:**
   * Sell **puts**, not calls.
   * Prefer the **"cover last month only"** rule. For puts it needs **{k(lo['puts'].capital_margin_worst_start)}** instead of
     {k(g['puts'].capital_margin_worst_start)} of capital and still made {usd(lo['puts'].total_pnl)}. It is the best return on capital in this test:
     {lo['puts'].ann_return_on_worst_start_capital:.0%}/yr, against {g['puts'].ann_return_on_worst_start_capital:.0%}/yr for the full martingale
     and {f['puts'].ann_return_on_worst_start_capital:.0%}/yr for fixed size.
   * **Cap the multiplier** at about 3–4×, so a longer streak cannot wipe out the account.
   * Size the base trade from your capital. For example, **$100k of capital supports a base trade of about
     {k(100_000 / g['puts'].capital_margin_worst_start * BASE_NOTIONAL)} notional with martingale puts**, or about
     {k(100_000 / lo['puts'].capital_margin_worst_start * BASE_NOTIONAL)} with the cover-last-month rule.

![Cumulative P&L](equity.png)

![Position size](position_size.png)

---

## 1. Checking the 7% premium

The premium is priced with Black-Scholes at the **actual Deribit implied vol traded on the ATM strike** of the
next monthly expiry, in the first trades after 08:00 UTC on each roll day (median 4 minutes after the roll).
This modelled premium matches Deribit's own mark price closely (correlation 0.92 for puts, 0.95 for calls). It also
matches a cross-check using the DVOL index (average {prem.dvol_bs_pct.mean():.1%}).

| Year | Avg. implied vol | Avg. ATM premium (1 month) | Range |
|---|---:|---:|---:|
{year_rows}
| **All** | {prem.iv.mean():.0%} | **{both.mean():.1%}** | {both.min():.1%} – {both.max():.1%} |

![Premium](premium.png)

Rule of thumb: ATM premium ≈ 0.4 × IV × √(1/12), which is about **IV ÷ 8.7**.
IV 60% → 6.9%, IV 70% → 8%, IV 35% → 4%.

## 2. Results, all variants

The sizing rules:

* **martingale**: size = base + (all unrecovered losses) ÷ premium per unit. It resets only after everything is recovered.
* **last_only**: the literal reading, "cover last month's loss". Size = base + (last month's loss) ÷ premium per unit.
  It resets after any profitable month.
* **fixed**: always the base size. This is the reference.

{table(summary, ['martingale', 'last_only', 'fixed'])}

How to read the capital columns:

* **Capital (margin)**: the smallest USD balance, starting in Jan 2023, that would never have been liquidated
  under Deribit standard margin. Opening a trade needs 15% of notional plus the option mark. The maintenance
  margin is 7.5% plus the mark. The position is marked to market every hour at that hour's worst ETH price.
* **Capital (margin, worst start)**: the same check, run for every possible start month from Jan 2023 to Sep 2026.
  The figure shown is the highest. **This is the number to plan with.** Starting in Jan 2023 was lucky, because
  early profits built a cushion.
* **Capital (no leverage)**: 1× notional held against every open option, like a cash-secured put.
* **Return/yr**: total P&L as an annualised return on the worst-start margin capital.

## 3. Month-by-month logs (martingale sizing)

<details><summary>Variant 1: sell puts</summary>

{month_table(logs[('puts', 'martingale')])}

</details>

<details><summary>Variant 2: sell calls</summary>

{month_table(logs[('calls', 'martingale')])}

</details>

<details><summary>Variant 3: up → puts, down → calls</summary>

{month_table(logs[('switch', 'martingale')])}

</details>

The logs for all 9 variant and rule combinations are in `results/trades_<variant>_<rule>.csv`.

## 4. Where it went wrong or nearly did

* **Puts:** Feb–Apr 2025 had 3 losses in a row. ETH fell from $3,250 to $1,770, and the size grew to
  {logs[('puts','martingale')].size_x.max():.1f}× before the May-2025 rally recovered everything. Jun 2026 (ETH -21%)
  was the largest single loss, {usd(g['puts'].worst_month)}.
* **Calls:** every strong rally caused a streak: Oct–Dec 2023, Feb–Mar 2024, and Jul–Aug 2025 (+48%, then +21%).
  The size reached 17.7× in Sep 2025. Aug and Sep 2026 (+32%, +7%) left the strategy with {usd(g['calls'].ends_with_open_deficit)}
  still to recover.
* **Switch:** the direction signal was wrong at the worst moment. After ETH fell in Apr 2025 it sold calls
  into the +48% rally of May 2025, and again into Jul 2025. That pushed the size to **{g['switch'].max_size_x:.0f}×
  ({usd(g['switch'].max_notional)} notional) in Aug 2025.** If that month had been as bad as the worst put month in the
  sample (ETH -35%), it would have lost about {k(g['switch'].stress_worst_month_on_max_size)}.

## 5. Assumptions

* **Data:** all from Deribit's public API (`fetch_data.py`, cached in `data/`): daily ETH delivery (settlement) prices,
  hourly ETH-PERPETUAL prices, hourly DVOL, and real option trades on every roll day.
* **Strike:** the listed strike nearest to the ETH price at 08:00 UTC. The premium is the fair value at the traded IV,
  **minus 1% slippage and Deribit fees**: 0.03% of the underlying to open, and 0.015% at settlement if the option
  expires in the money.
* **P&L:** measured in USD, with a stablecoin-collateralised account (like Deribit's USDC-margined options).
  With coin-margined (ETH) collateral, a put seller loses twice when ETH falls, so the capital needs are higher.
* **Success:** a month counts as successful if its P&L is ≥ 0. For example, a put that expired slightly in the money
  but for less than the premium is still a success.
* **Direction signal (variant 3):** the ETH move between the two previous expiries. For the first trade, Dec 2022
  was +0.4%, so it sold a put.
* **Not included:** early assignment (Deribit options are European), funding cost or interest on idle cash, and
  taxes. The intramonth option mark uses DVOL, which is an ATM vol, so skew is ignored.

## Re-running

```bash
pip install pandas numpy matplotlib
python3 fetch_data.py   # optional: refreshes data/ from Deribit
python3 report.py       # backtest, charts and this report
```

To change the base size, slippage or margin rates, edit the constants at the top of `backtest.py`.
"""
    (OUT / "REPORT.md").write_text(md)


if __name__ == "__main__":
    q, summary, logs, prem = main()
    chart_equity(logs)
    chart_size(logs)
    chart_premium(prem)
    write_report(q, summary, logs, prem)
    print("wrote", OUT / "REPORT.md")
