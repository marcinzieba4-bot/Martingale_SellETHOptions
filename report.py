"""Run the backtest, draw the charts and write REPORT.md."""
import matplotlib

matplotlib.use("Agg")
import matplotlib.dates as mdates  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from backtest import BASE_NOTIONAL, OUT, VARIANTS, load, main, month_path  # noqa: E402

# categorical slots 1-4 of the reference palette, fixed per series
SLOT = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]
ORIGINAL = ["puts", "calls", "switch"]
NEW = ["puts_up", "calls_down", "switch_hedged", "switch_call_hedge"]
COLORS = {"puts": SLOT[0], "calls": SLOT[1], "switch": SLOT[2],
          "puts_up": SLOT[0], "calls_down": SLOT[1], "switch_hedged": SLOT[2], "switch_call_hedge": SLOT[3]}
SHORT = {"puts": "1 · Puts", "calls": "2 · Calls", "switch": "3 · Switch",
         "puts_up": "1b · Puts after up", "calls_down": "2b · Calls after down",
         "switch_hedged": "3b · Switch + hedge", "switch_call_hedge": "3c · Switch + call hedge",
         "puts_up_hedged": "1c · 1b + hedge", "calls_down_hedged": "2c · 2b + hedge"}
CODE = {"puts": "1", "calls": "2", "switch": "3", "puts_up": "1b", "calls_down": "2b", "switch_hedged": "3b",
        "puts_up_hedged": "1c", "calls_down_hedged": "2c", "switch_call_hedge": "3c"}
INK, INK2, MUTED, GRID, SURFACE = "#0b0b0b", "#52514e", "#a3a29d", "#e4e3df", "#fcfcfb"

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


def spread_labels(ys, gap):
    """Nudge end-of-line label positions apart so they never overlap."""
    order = np.argsort(ys)
    out = np.array(ys, float)
    for a, b in zip(order[:-1], order[1:]):
        out[b] = max(out[b], out[a] + gap)
    return out


def chart_equity(logs, keys, fname, title):
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.4), sharey=True)
    for ax, rule, sub in zip(axes, ("martingale", "fixed"), ("Martingale sizing", "Fixed size (no martingale)")):
        ends = []
        for v in keys:
            log = logs[(v, rule)]
            x = pd.to_datetime(log.expiry)
            ax.plot(x, log.cum_pnl, color=COLORS[v], lw=2, label=SHORT[v])
            ends.append((x.iloc[-1], log.cum_pnl.iloc[-1], v))
        lo, hi = ax.get_ylim()
        ys = spread_labels([e[1] for e in ends], gap=(hi - lo) * 0.055)
        for (x_end, y_end, v), y_lab in zip(ends, ys):
            ax.annotate(f"{CODE[v]}  {k(y_end)}", (x_end, y_end), xytext=(x_end + pd.Timedelta(days=25), y_lab),
                        va="center", fontsize=9, color=INK)
        ax.axhline(0, color=INK2, lw=1)
        ax.set_title(sub, loc="left", fontsize=11, color=INK)
        ax.yaxis.set_major_formatter(lambda y, _: k(y))
        ax.xaxis.set_major_locator(mdates.YearLocator())
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    axes[0].set_ylabel(f"Cumulative P&L (base trade = ${BASE_NOTIONAL:,.0f} notional)")
    axes[1].legend(loc="lower left", frameon=False, fontsize=9)
    fig.suptitle(title, x=0.01, ha="left", fontsize=12, weight="bold")
    fig.tight_layout()
    fig.subplots_adjust(right=0.9, wspace=0.18)
    fig.savefig(OUT / fname, dpi=150)
    plt.close(fig)


def chart_size(logs, keys, fname):
    fig, axes = plt.subplots(len(keys), 1, figsize=(11, 1.9 * len(keys) + 0.8), sharex=True, sharey=True)
    for ax, v in zip(axes, keys):
        log = logs[(v, "martingale")]
        x = pd.to_datetime(log.expiry)
        ax.bar(x, log.size_x, width=22, color=COLORS[v])
        loss = log.pnl < 0
        ax.scatter(x[loss], log.size_x[loss] + 1.5, marker="v", s=18, color=INK2, zorder=3)
        ax.set_title(f"{VARIANTS[v][0]} · max {log.size_x.max():.1f}× base", loc="left", fontsize=10, color=INK)
        ax.set_ylabel("× base")
    axes[0].annotate("▼ = losing month · no bar = no trade", (0.99, 0.85), xycoords="axes fraction", ha="right",
                     fontsize=9, color=INK2)
    fig.suptitle("Position size with martingale sizing (1× = base trade)", x=0.01, ha="left", fontsize=12,
                 weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / fname, dpi=150)
    plt.close(fig)


def chart_capital(summary):
    """Profit vs safe capital: every rule with martingale sizing (filled) + the two best at fixed size (hollow)."""
    best = {"puts_up", "switch_call_hedge"}
    pts = [(v, "martingale") for v in summary.key.unique()] + [(v, "fixed") for v in sorted(best)]
    s = summary.set_index(["key", "rule"])
    offsets = {("switch", "martingale"): (8, -12), ("puts_up", "fixed"): (8, -12), ("puts", "martingale"): (8, -13),
               ("switch_call_hedge", "fixed"): (8, -12), ("calls_down_hedged", "martingale"): (8, -12)}
    fig, ax = plt.subplots(figsize=(10.5, 5))
    for v, rule in pts:
        r = s.loc[(v, rule)]
        c = SLOT[0] if v in best else MUTED
        ax.scatter(r.safe_capital, r.total_pnl, s=70, zorder=3, linewidth=2,
                   color=c if rule == "martingale" else SURFACE, edgecolor=SURFACE if rule == "martingale" else c)
        tag = "" if rule == "martingale" else ", fixed size"
        ax.annotate(f"{SHORT[v]}{tag}  ({r.ann_return_on_safe_capital:.0%}/yr)", (r.safe_capital, r.total_pnl),
                    xytext=offsets.get((v, rule), (8, 4)), textcoords="offset points", fontsize=9,
                    color=INK if v in best else INK2)
    ax.set_xscale("log")
    ax.set_xticks([5e3, 1e4, 2e4, 5e4, 1e5, 2e5])
    ax.xaxis.set_major_formatter(lambda x, _: k(x))
    ax.yaxis.set_major_formatter(lambda y, _: k(y))
    ax.set_xlim(4.5e3, 8e5)
    ax.set_xlabel("Safe capital per $10k base trade (worst start + one more worst month), log scale")
    ax.set_ylabel("Total P&L, Jan 2023 – Sep 2026")
    ax.set_title("Profit vs capital needed · filled = martingale, hollow = fixed size · top-left is best",
                 loc="left", fontsize=12, weight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "capital_vs_profit.png", dpi=150)
    plt.close(fig)


def chart_hedge_examples(q, eth):
    """Two real months: a call hedge that saved the trade, and a put hedge that got whipsawed."""
    cases = [("2024-11", "C", "Nov-2024 call · breakout above last month's high → long perp"),
             ("2023-03", "P", "Mar-2023 put · break below last month's low → short perp, stopped at high")]
    fig, axes = plt.subplots(1, 2, figsize=(11.5, 4.2))
    for ax, (month, kind, title) in zip(axes, cases):
        r = q[q.expiry.dt.strftime("%Y-%m") == month].iloc[0]
        t0, t1 = r.sell_date + pd.Timedelta(hours=8), r.expiry + pd.Timedelta(hours=8)
        h = eth.loc[(eth.index >= t0) & (eth.index < t1)]
        p = month_path(eth, r, kind)
        ax.plot(h.index, h.close, color=SLOT[0], lw=1.5)
        for level, name in ((r.strike, "strike"), (r.prev_high, "last month's high"), (r.prev_low, "last month's low")):
            ax.axhline(level, color=INK2, lw=1, ls="--" if name == "strike" else ":")
            ax.annotate(f"{name} {level:,.0f}", (h.index[0], level), xytext=(0, 3), textcoords="offset points",
                        fontsize=8, color=INK2, bbox=dict(boxstyle="square,pad=0.1", fc=SURFACE, ec="none", alpha=0.6))
        pos = p["h_pos"]
        changes = np.flatnonzero(np.diff(np.r_[0, pos]) != 0)
        for j in changes:
            opened = pos[j] != 0
            y = p["h_entry"][j] if opened else (r.prev_high if kind == "P" else r.prev_low)
            ax.scatter(h.index[j], y, s=60, zorder=4, color=SLOT[1] if opened else INK,
                       marker=("v" if kind == "P" else "^") if opened else "x")
        base_units = BASE_NOTIONAL / r.spot
        opt = base_units * (r[f"prem_net_{kind}"] - r[f"payoff_{kind}"])
        hed = base_units * p["hedge_pnl"]
        ax.set_title(f"{title}\noption {usd(opt)} · hedge {usd(hed)} · month {usd(opt + hed)} (1× size)",
                     loc="left", fontsize=9.5, color=INK)
        ax.xaxis.set_major_locator(mdates.DayLocator(bymonthday=[1, 8, 15, 22]))
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%d %b"))
        ax.yaxis.set_major_formatter(lambda y, _: f"${y:,.0f}")
    fig.suptitle("How the perp hedge behaves (▲▼ = hedge opened, × = stopped out)", x=0.01, ha="left",
                 fontsize=12, weight="bold")
    fig.tight_layout()
    fig.savefig(OUT / "hedge_examples.png", dpi=150)
    plt.close(fig)


def chart_premium(prem):
    fig, ax = plt.subplots(figsize=(11, 3.6))
    x = pd.to_datetime(prem.month)
    avg = (prem.put_pct + prem.call_pct) / 2 * 100
    ax.bar(x, avg, width=22, color=SLOT[0])
    ax.axhline(7, color=INK, lw=1, ls="--")
    ax.annotate("7% assumption", (x.iloc[0], 7.2), fontsize=9, color=INK)
    ax.yaxis.set_major_formatter(lambda y, _: f"{y:.0f}%")
    ax.set_title("ATM 1-month ETH option premium, % of ETH price (avg of put & call, real Deribit IV)",
                 loc="left", fontsize=11, color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "premium.png", dpi=150)
    plt.close(fig)


def table(summary, keys, rules):
    rows = ["| Variant | Sizing | Total P&L | Months traded | Losing months | Max losing streak | Biggest position | "
            "Worst month | Hedge P&L | Capital (margin, worst start) | **Safe capital** | Capital (no leverage) | "
            "Return/yr on safe capital |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    s = summary.set_index(["key", "rule"])
    for v in keys:
        for rule in rules:
            r = s.loc[(v, rule)]
            hedge = usd(r.hedge_pnl) + f" ({r.hedge_fills} fills)" if r.hedge_fills else "–"
            rows.append(
                f"| {r.variant} | {rule} | **{usd(r.total_pnl)}** | {r.months_traded} | {r.losing_months} | "
                f"{r.max_loss_streak} | {r.max_size_x:.1f}× ({usd(r.max_notional)}) | {usd(r.worst_month)} | {hedge} | "
                f"{usd(r.capital_margin_worst_start)} | **{usd(r.safe_capital)}** | {usd(r.capital_unlevered_worst_start)} | "
                f"{r.ann_return_on_safe_capital:.1%} |")
    return "\n".join(rows)


def month_table(log):
    hedged = log.hedge_fills.sum() > 0
    head = "| Month | Side | ETH start → settle | Move | Last month low / high | Premium | Size | Notional | Option P&L |"
    head += " Hedge P&L |" if hedged else ""
    head += " Month P&L | Cum. P&L | Losses to recover |"
    rows = [head, "|" + "---|" * 4 + "---|" + "---:|" * (8 if hedged else 7)]
    for _, r in log.iterrows():
        if r.side == "-":
            rows.append(f"| {r.month} | no trade | {r.spot:,.0f} → {r.settle:,.0f} | {r.eth_move:+.1%} | "
                        f"{r.prev_low:,.0f} / {r.prev_high:,.0f} | | | | |" + (" |" if hedged else "") +
                        f" | {usd(r.cum_pnl)} | {usd(r.deficit_after)} |")
            continue
        line = (f"| {r.month} | {r.side} | {r.spot:,.0f} → {r.settle:,.0f} | {r.eth_move:+.1%} | "
                f"{r.prev_low:,.0f} / {r.prev_high:,.0f} | {r.premium_pct:.1%} | {r.size_x:.2f}× | {usd(r.notional)} | "
                f"{usd(r.option_pnl)} |")
        if hedged:
            line += f" {usd(r.hedge_pnl) + ' (' + str(int(r.hedge_fills)) + ')' if r.hedge_fills else '–'} |"
        line += f" {usd(r.pnl)} | {usd(r.cum_pnl)} | {usd(r.deficit_after)} |"
        rows.append(line)
    return "\n".join(rows)


def write_report(q, summary, logs, prem):
    S = summary.set_index(["key", "rule"])

    def g(v, rule="martingale"):
        return S.loc[(v, rule)]

    both = (prem.put_pct + prem.call_pct) / 2
    by_year = prem.assign(year=prem.month.str[:4], both=both).groupby("year").agg(
        iv=("iv", "mean"), prem=("both", "mean"), lo=("both", "min"), hi=("both", "max"))
    year_rows = "\n".join(f"| {y} | {r.iv:.0%} | {r.prem:.1%} | {r.lo:.1%} – {r.hi:.1%} |" for y, r in by_year.iterrows())
    eth0, eth1 = q.spot.iloc[0], q.settle.iloc[-1]
    b, c3 = g("puts_up"), g("switch_call_hedge")
    per100_b = 100_000 / b.safe_capital * BASE_NOTIONAL
    per100_c = 100_000 / c3.safe_capital * BASE_NOTIONAL

    md = f"""# Martingale ETH option selling: backtest, Jan 2023 to Sep 2026

Every month, on Deribit's monthly expiry (the last Friday, 08:00 UTC), the strategy sells the at-the-money ETH
option that expires one month later. It is held to expiry and settled at Deribit's real delivery price.
"Last month" means the expiry-to-expiry month that just ended.

| # | Rule |
|---|---|
| 1 | Sell a put every month |
| 2 | Sell a call every month |
| 3 | Momentum: after an up month sell a put, after a down month sell a call |
| **1b** | **Sell a put only if last month was up**, otherwise skip the month |
| **2b** | **Sell a call only if last month was down**, otherwise skip the month |
| **3b** | **3 plus a perp hedge.** Short put: when ETH trades below last month's low, short the perp (same size as the option). Stop out when ETH trades above last month's high, and re-enter whenever the low is broken again. Short call: long the perp above last month's high, with the stop below last month's low. The hedge is closed at expiry. |
| 1c / 2c | 1b / 2b with the same hedge |
| 3c | 3b, but only the calls are hedged. I added this after seeing the 1c/2c results. |

**Martingale sizing:** after a losing month, the next trade is sized so that its premium covers the losses still
to be recovered, plus the normal premium. The size resets after the losses are recovered. In 1b and 2b,
**the losses to recover (and so the larger size) carry over the skipped months** and are used at the next month
the strategy is allowed to trade. The monthly result includes the hedge P&L.

All $ figures are for a **base trade of ${BASE_NOTIONAL:,.0f} ETH notional** (about $650 of premium a month). Every figure scales linearly.
The test covers 45 monthly expiries, Jan 2023 to Sep 2026. ETH went from ${eth0:,.0f} to ${eth1:,.0f}.

---

## Summary: what the results mean for you

1. **The best new rule is 1b: sell puts only after an up month.** With martingale sizing it made **{usd(b.total_pnl)}**
   from {b.months_traded} trades, against {usd(g('puts').total_pnl)} for puts every month. It needed **{k(b.capital_margin_worst_start)} of capital**
   instead of {k(g('puts').capital_margin_worst_start)}. The position never went above **{b.max_size_x:.1f}×** the base, the worst month
   was {usd(b.worst_month)}. **Safe capital** (explained below the tables) was **{k(b.safe_capital)}**, a return of
   **{b.ann_return_on_safe_capital:.0%}/yr** on it.
   * The months it skips are the ones where puts lose. Fixed-size puts made {usd(g('puts_up','fixed').total_pnl)} in 1b against
     {usd(g('puts','fixed').total_pnl)} when sold every month.
   * The deep drops of Feb–Apr 2025, Nov 2025–Mar 2026 and Jun 2026 all came after down months, so 1b was not trading.
2. **2b: calls only after a down month. Do not trade this without the hedge.** It made {usd(g('calls_down').total_pnl)}, but at
   fixed size it lost {usd(abs(g('calls_down','fixed').total_pnl))}. The martingale pushed the position to
   **{g('calls_down').max_size_x:.0f}× ({usd(g('calls_down').max_notional)} notional)** in Oct 2025, after a {usd(g('calls_down').worst_month)} month
   (Jul 2025, ETH +48%). That needed **{k(g('calls_down').capital_margin_worst_start)} of capital**.
3. **3b: momentum plus the perp hedge.** The hedge cut the capital needed from {k(g('switch').capital_margin_worst_start)} to
   **{k(g('switch_hedged').capital_margin_worst_start)}** and the biggest position from {g('switch').max_size_x:.0f}× to {g('switch_hedged').max_size_x:.1f}×.
   The hedge made {usd(g('switch_hedged').hedge_pnl)} over {g('switch_hedged').hedge_fills} fills. Total P&L was {usd(g('switch_hedged').total_pnl)}
   ({g('switch_hedged').ann_return_on_safe_capital:.0%}/yr on safe capital of {k(g('switch_hedged').safe_capital)}).
4. **The hedge works for calls and fails for puts.** This held for every rule and stop level I tried.
   * **Call hedge:** it made {usd(g('calls_down_hedged').hedge_pnl)} on 2b. When ETH breaks last month's high, the rally usually keeps going
     (Nov 2024, May 2025 and Jul 2025 each covered about 70–95% of the option loss). The capital needed for 2b fell from
     {k(g('calls_down').capital_margin_worst_start)} to {k(g('calls_down_hedged').capital_margin_worst_start)}.
   * **Put hedge:** it lost {usd(abs(g('puts_up_hedged').hedge_pnl))} on 1b. After an up month, a break below last month's low usually
     bounces back. The short perp is then stopped out at the high far above (Mar 2023: -$1.8k on a put that made +$0.8k),
     or held to expiry at a loss. A tighter stop (at the strike, or 5–10% above the low) did not fix it.
   * **So 3c, which hedges only the calls, is the best momentum version:** {usd(c3.total_pnl)} with **{k(c3.capital_margin_worst_start)}** of capital,
     a maximum of {c3.max_size_x:.1f}×, and **{c3.ann_return_on_safe_capital:.0%}/yr** on safe capital of {k(c3.safe_capital)}.
5. **With full martingale sizing, the hedge does not change the total profit. It changes the risk.**
   A martingale's profit is roughly the base premium times the number of winning months. That is why 3 and 3c both end at {usd(g('switch').total_pnl)},
   and 2b and 2c at {usd(g('calls_down').total_pnl)}. What the hedge (or the filter) changes is how large the position and the capital
   requirement get on the way. **Judge each version by the capital it needs, not by its profit.**
6. **Fixed size gives a better return on capital than the martingale.** The martingale earns more per base trade, but it
   needs more capital per base trade, and the capital grows faster than the profit. On safe capital:
   * 1b made **{g('puts_up','fixed').ann_return_on_safe_capital:.0%}/yr at fixed size**, against {b.ann_return_on_safe_capital:.0%}/yr with the martingale.
   * 3c made **{g('switch_call_hedge','fixed').ann_return_on_safe_capital:.0%}/yr at fixed size**, against {c3.ann_return_on_safe_capital:.0%}/yr with the martingale.
   * Puts every month made {g('puts','fixed').ann_return_on_safe_capital:.0%}/yr at fixed size, against {g('puts').ann_return_on_safe_capital:.0%}/yr with the martingale.
   If your goal is the most profit from a given amount of money, use a bigger fixed size instead of the martingale.
7. **What to do:**
   * **Best overall: 1b at fixed size**, sell a put only after an up month. Hold about **{k(g('puts_up','fixed').safe_capital)} per $10k of base
     notional**, so **$100k supports about {k(100_000 / g('puts_up','fixed').safe_capital * BASE_NOTIONAL)} of puts a month**. Fully cash-secured,
     with no leverage, it needs {k(g('puts_up','fixed').capital_unlevered_worst_start)} per $10k.
   * **If you want the martingale: 1b with martingale sizing.** Hold **{k(b.safe_capital)} per $10k**, so $100k supports a base trade of
     about {k(per100_b)}. The size never went above {b.max_size_x:.1f}×.
   * **To trade every month: 3c**, momentum with the call hedge only. Hold {k(g('switch_call_hedge','fixed').safe_capital)} per $10k at fixed size, or
     {k(c3.safe_capital)} with the martingale. $100k supports about {k(100_000 / g('switch_call_hedge','fixed').safe_capital * BASE_NOTIONAL)} or {k(per100_c)} of base notional.
   * If you use the martingale, cap the multiplier at about 4–5×.
   * Treat 3c as a hypothesis, not a proven edge. I picked it after seeing the results, from only 5 call-hedge fills. The
     explanation (ETH breakouts above a monthly high tend to continue) makes sense, but the sample is small.

![Profit vs capital](capital_vs_profit.png)

![Cumulative P&L, new rules](equity_new.png)

![Hedge examples](hedge_examples.png)

---

## 1. New rules: full results

{table(summary, ['puts_up', 'calls_down', 'switch_hedged', 'switch_call_hedge', 'puts_up_hedged', 'calls_down_hedged'], ['martingale', 'last_only', 'fixed'])}

The same table for the original rules 1, 2 and 3 is in section 2.

* **Capital (margin, worst start)**: the smallest USD balance that would never have been liquidated, for the worst possible
  start month between Jan 2023 and Sep 2026, under Deribit standard margin. Opening an option needs 15% of notional
  plus the mark. Keeping it open needs 7.5% plus the mark. The perp hedge needs 2% of its notional. Everything is marked every hour at
  both the high and the low of the hour.
* **Safe capital**: the worst-start capital, plus the loss if the worst month ever seen for that side hit the biggest
  position once more. For puts that month is Feb 2025 (ETH −35%). For calls it is May/Jul 2025 (ETH +48%), with or without the hedge
  as the rule uses it, and counting all 45 months, not only the months the rule traded. **This is the number to plan with.**
* **No leverage**: 1× notional set aside for every option (cash-secured put or fully funded call), plus any running hedge loss.
* **Return/yr**: total P&L as an annualised return on the safe capital, over the full 45 months, including months with no trade.
* **Sizing**: *martingale* recovers all losses since the last reset. *last_only* covers only the last traded month's loss.
  *fixed* never changes size.

![Position size, new rules](position_size_new.png)

### How the hedge performed

* **All hedge fills in the momentum rule (3b):** 9. Five were on calls: Feb 2024, May 2024, Nov 2024, May 2025 and Jul 2025.
  Four were on puts: Mar 2023, May 2023, Oct 2023 and Apr 2024.
* **Call fills:** net strongly positive. The breakouts ran through the strike, and the long perp made back most
  of the option loss. May 2024 roughly broke even: the breakout came late and ETH settled at the entry level.
* **Put fills:** net negative. The dips reversed, so the short perp either lost the whole low-to-high range when stopped
  (Mar 2023, Oct 2023) or was closed at a loss at expiry (May 2023, Apr 2024).
* **Costs included:** 0.05% taker fee plus 0.05% slippage on every perp fill, and the real hourly Deribit funding
  (longs paid on average about 4%/yr over the period).

---

## 2. Original rules (1, 2, 3)

{table(summary, ORIGINAL, ['martingale', 'last_only', 'fixed'])}

![Cumulative P&L, original rules](equity.png)

![Position size, original rules](position_size.png)

What these show:

* **1 (puts every month)** works, but the full martingale reached 6.4× during Feb–Apr 2025.
* **2 (calls every month)** loses money at fixed size, and ended Sep 2026 still carrying {usd(g('calls').ends_with_open_deficit)} of losses to recover.
* **3 (momentum, unhedged)** reached 33× ({usd(g('switch').max_notional)}) in Aug 2025, after selling calls into the +48% rallies
  of May and Jul 2025.

---

## 3. Checking the 7% premium

The premium is priced with Black-Scholes at the **actual Deribit implied vol traded on the ATM strike** of the next monthly
expiry, in the first trades after 08:00 UTC on each roll day. It matches Deribit's mark price closely (correlation 0.92 for puts,
0.95 for calls) and the DVOL-based estimate ({prem.dvol_bs_pct.mean():.1%} on average).

| Year | Avg. implied vol | Avg. ATM premium (1 month) | Range |
|---|---:|---:|---:|
{year_rows}
| **All** | {prem.iv.mean():.0%} | **{both.mean():.1%}** | {both.min():.1%} – {both.max():.1%} |

![Premium](premium.png)

Only {(both >= 0.07).mean():.0%} of months paid 7% or more, so plan on about 6.5%. Rule of thumb: premium ≈ implied vol ÷ 8.7.

---

## 4. Month-by-month logs (martingale sizing)

<details><summary>1b: puts only after an up month</summary>

{month_table(logs[('puts_up', 'martingale')])}

</details>

<details><summary>2b: calls only after a down month</summary>

{month_table(logs[('calls_down', 'martingale')])}

</details>

<details><summary>3b: momentum + perp hedge</summary>

{month_table(logs[('switch_hedged', 'martingale')])}

</details>

<details><summary>3c: momentum + perp hedge on calls only</summary>

{month_table(logs[('switch_call_hedge', 'martingale')])}

</details>

<details><summary>1: puts every month</summary>

{month_table(logs[('puts', 'martingale')])}

</details>

<details><summary>2: calls every month</summary>

{month_table(logs[('calls', 'martingale')])}

</details>

<details><summary>3: momentum, no hedge</summary>

{month_table(logs[('switch', 'martingale')])}

</details>

The logs for every variant and sizing rule are in `results/trades_<variant>_<rule>.csv`.

---

## 5. Assumptions

* **Data:** Deribit public API (`fetch_data.py`, cached in `data/`): daily ETH delivery (settlement) prices, hourly
  ETH-PERPETUAL prices, hourly perp funding, hourly DVOL, and real option trades on every roll day.
* **Option:** the listed strike nearest to the ETH price at 08:00 UTC. It is sold at fair value at the traded IV,
  minus 1% slippage and Deribit fees (0.03% of the underlying to open, and 0.015% at settlement if in the money).
* **"Up/down month":** the ETH change between the two previous expiries.
* **Last month's low/high:** the lowest and highest hourly ETH-PERPETUAL prices over the previous expiry-to-expiry month.
* **Hedge fills:** checked on hourly bars. Entries and stops fill at the level, or at the bar's open if the price gapped through it.
  An open hedge is closed at the expiry settlement price. The hedge size equals the option size in ETH.
  There is at most one hedge change per hour.
* **Account:** USD P&L with a stablecoin-collateralised account. With ETH as collateral, the capital needs for puts are higher.
* **A month counts as a success** if its P&L (option plus hedge) is ≥ 0.
* **Not included:** interest on idle cash and taxes. The intramonth option mark uses DVOL, an ATM vol, so skew is ignored.

## Re-running

```bash
pip install pandas numpy matplotlib
python3 fetch_data.py   # optional: refreshes data/ from Deribit
python3 report.py       # backtest, charts and this report
```

To change the base size, fees, slippage or margin rates, edit the constants at the top of `backtest.py`.
To add a rule, add an entry to `VARIANTS` in `backtest.py`.
"""
    (OUT / "REPORT.md").write_text(md)


if __name__ == "__main__":
    q, summary, logs, prem = main()
    _, eth = load()
    chart_equity(logs, ORIGINAL, "equity.png", "Original rules · cumulative P&L, Jan 2023 – Sep 2026")
    chart_equity(logs, NEW, "equity_new.png", "New rules · cumulative P&L, Jan 2023 – Sep 2026")
    chart_size(logs, ORIGINAL, "position_size.png")
    chart_size(logs, NEW, "position_size_new.png")
    chart_capital(summary)
    chart_hedge_examples(q, eth)
    chart_premium(prem)
    write_report(q, summary, logs, prem)
    print("wrote", OUT / "REPORT.md")
