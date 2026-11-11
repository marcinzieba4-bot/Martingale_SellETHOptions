"""Crash-after-a-rally scenarios (scenario.py): chart and results/SCENARIO.md."""
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import scenario as sn
from backtest import OUT
from report import INK, INK2, SLOT, k, usd  # also applies the chart style

NAMES = [None, "Apr 2024", "Dec 2024"]
LABEL = {None: "No crash (real history)", "Apr 2024": "Crash in Apr 2024", "Dec 2024": "Crash in Dec 2024"}


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def equity(sc, cap):
    r = sc["res"]["both"]
    eq = cap + np.r_[0, np.cumsum(r["pnl"])]
    x = np.r_[sc["q"].sell_date.iloc[0], pd.to_datetime(sc["q"].expiry)]
    return x, eq


def chart(scs, sums):
    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 6.4), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
    for (name, sc), c in zip(scs.items(), SLOT):
        s = sums[name]
        x, eq = equity(sc, s["capital"])
        a1.plot(x, (eq / s["capital"] - 1) * 100, color=c, lw=2,
                label=f"{LABEL[name]} · capital {k(s['capital'])} · Calmar {s['calmar_month_end']:.2f}")
        peak = np.maximum.accumulate(eq)
        a2.plot(x, -(peak - eq) / peak * 100, color=c, lw=1.8)
        if name:
            t = pd.Timestamp(sn.SCENARIOS[name])
            a1.axvline(t, color=c, lw=1, ls=":")
    a1.axhline(0, color=INK2, lw=1)
    a1.yaxis.set_major_formatter(lambda v, _: f"{v:+.0f}%")
    a1.set_ylabel("Return on capital held")
    a1.legend(frameon=False, fontsize=9, loc="upper left")
    a1.set_title("ETH 1b + 3b + BTC spread (1 BTC/leg), capital = what each path needs + 25% cushion",
                 loc="left", fontsize=11.5, weight="bold", color=INK)
    a2.yaxis.set_major_formatter(lambda v, _: f"{v:.0f}%")
    a2.set_ylabel("Drawdown (month-end)")
    a2.xaxis.set_major_locator(mdates.YearLocator())
    a2.xaxis.set_major_formatter(mdates.DateFormatter("%Y"))
    fig.tight_layout()
    fig.savefig(OUT / "scenario_crash.png", dpi=150)
    plt.close(fig)


def month_lines(sc, n_after=10):
    """Month-by-month around the crash: positions, P&L and equity on the capital held."""
    r = sc["res"]["both"]
    log = r["log"]
    i0 = sc["crash_i"]
    cap = r["capital"] * (1 + sn.CUSHION)
    eq = cap + np.cumsum(r["pnl"])
    rows = ["| Month | ETH | BTC | 1b | 3b | BTC spread | Month P&L | Equity |",
            "|---|---:|---:|---|---|---|---:|---:|"]
    for i in range(i0 - 1, min(i0 + n_after, len(sc["months"]))):
        m = sc["months"][i]
        g = log[log.month == m["month"]].set_index("book")

        def cell(book):
            if book not in g.index or g.loc[book, "side"] == "-":
                return "–"
            row = g.loc[book]
            size = f"{row.size_btc:.2f} BTC" if book == "btc" else f"{row.side} {row.size_x:.1f}×"
            return f"{size}: {usd(row.pnl)}"
        rows.append(f"| {m['month']}{' **crash**' if i == i0 else ''} | {m['eth_move']:+.0%} | "
                    f"{sc_btc_move(sc, i)} | {cell('1b')} | {cell('3b')} | {cell('btc')} | "
                    f"{usd(r['pnl'][i])} | {usd(eq[i])} |")
    return "\n".join(rows)


def sc_btc_move(sc, i):
    """BTC move over cycle i of this scenario (from the real BTC hourly data, scaled)."""
    q = sc["q"]
    perp = sc.setdefault("_perp", pd.read_csv(sn.cb.BTC_DIR / "btc_perp_1h.csv", parse_dates=["t"]).set_index("t")["close"])
    t0, t1 = q.sell_date[i] + pd.Timedelta(hours=8), q.expiry[i] + pd.Timedelta(hours=8)
    if sc["name"] and i == sc["crash_i"]:
        return f"{sn.BTC_TEMPLATE[3] / sn.BTC_TEMPLATE[2] - 1:+.0%}"
    a, b = perp.asof(t0), perp.asof(t1)
    return f"{b / a - 1:+.0%}"


def write(scs, sums, eth_dec, base_on_dec_cap, caps):
    n, a, d = (sums[x] for x in NAMES)
    dec, apr = scs["Dec 2024"], scs["Apr 2024"]
    info = dec["info"]
    md = f"""# What if ETH and BTC crash together right after a rally? (2024 simulation)

**Portfolio:** ETH 1b + 3b (full martingale, $10k + $10k base) plus the BTC put spread at 1 BTC per leg
(loss recovery, capped at 4 BTC). Everything is on one USD account, Jan 2023 – Sep 2026.

**How the crash is simulated (`scenario.py`):**

* Take the real history and replace one month with a crash of both coins:
  * **ETH** follows, hour by hour, its worst real month (31 Jan → 28 Feb 2025, **−35%**), including that month's
    implied-vol spike. The 3b hedge, margin and marks all see this path.
  * **BTC** follows its worst real month (27 May → 24 Jun 2022, **−28%**).
* Every later month is the real history, shifted down to the new lower prices. Later monthly moves, and so
  the strategies' up/down and big-candle signals, stay the real ones.
  * The month after the crash is the exception: it sees the crash as "last month". ETH 3b sells a call, and BTC
    sees a −28% candle and opens a spread, priced from the real Deribit quotes of that date.
* **Crash months tested.** Both come right after a rally of both coins, the setup where 1b, 3b and BTC are all short the downside:
  * **Apr 2024**, after the March 2024 all-time-high rally (ETH +21%, BTC +37%). Positions were at base size.
  * **Dec 2024**, after the November 2024 election rally (ETH +43%, BTC +42%). The ETH martingale was already
    at about 2× base. This is the worst case.
* **Capital:** what each path needs to never hit margin (Deribit margin checked hourly, from Jan 2023), **plus a 25% cushion**,
  as you described. So no scenario wipes out the account.
* **Calmar** = annual return on that capital ÷ max drawdown. It is shown with the month-end drawdown (the usual
  definition) and with the intramonth (hourly) drawdown.

---

## Summary: what the results mean for you

| | No crash (real history) | Crash in Apr 2024 | **Crash in Dec 2024** |
|---|---:|---:|---:|
| Capital needed (never hit margin) | {usd(n['required'])} | {usd(a['required'])} | **{usd(d['required'])}** |
| Capital held (+25% cushion) | {usd(n['capital'])} | {usd(a['capital'])} | **{usd(d['capital'])}** |
| Crash month: 1b / 3b / BTC | – | {usd(a['crash_parts']['1b'])} / {usd(a['crash_parts']['3b'])} / {usd(a['crash_parts']['btc'])} | {usd(d['crash_parts']['1b'])} / {usd(d['crash_parts']['3b'])} / {usd(d['crash_parts']['btc'])} |
| Crash month total | – | {usd(a['crash_loss'])} | **{usd(d['crash_loss'])}** |
| Worst month, % of capital | {pct(n['worst_month'])} | {pct(a['worst_month'])} | {pct(d['worst_month'])} |
| Total P&L, Jan 2023 – Sep 2026 | {usd(n['total'])} | {usd(a['total'])} | {usd(d['total'])} |
| Annual return on capital held | {pct(n['ann_ret'])} | {pct(a['ann_ret'])} | **{pct(d['ann_ret'])}** |
| Max drawdown, month-end | {pct(n['dd_month'])} | {pct(a['dd_month'])} | **{pct(d['dd_month'])}** |
| Max drawdown, intramonth | {pct(n['dd_intra'])} | {pct(a['dd_intra'])} | {pct(d['dd_intra'])} |
| **Calmar (month-end drawdown)** | **{n['calmar_month_end']:.2f}** | **{a['calmar_month_end']:.2f}** | **{d['calmar_month_end']:.2f}** |
| Calmar (intramonth drawdown) | {n['calmar']:.2f} | {a['calmar']:.2f} | {d['calmar']:.2f} |
| Sharpe | {n['sharpe']:.2f} | {a['sharpe']:.2f} | {d['sharpe']:.2f} |
| Months to a new equity high after the crash | – | {a['recovery']} | {d['recovery']} |
| Largest size 1b / 3b / BTC | {n_sizes(scs[None])} | {n_sizes(apr)} | {n_sizes(dec)} |

Each path is measured on its own capital. The no-crash path holds much less capital, so its intramonth swings look
larger in %, even though they are smaller in dollars.

1. **The Dec 2024 crash costs {usd(-d['crash_loss'])} in one month, and the account survives it.**
   * That is {pct(-d['worst_month'])} of the capital held. The deepest drawdown is {pct(d['dd_month'])}.
   * **Calmar falls from {n['calmar_month_end']:.2f} to {d['calmar_month_end']:.2f}** (month-end drawdown), and the annual return on capital
     from {pct(n['ann_ret'])} to {pct(d['ann_ret'])}.
   * The milder Apr 2024 version gives Calmar {a['calmar_month_end']:.2f} and {pct(a['ann_ret'])} a year.
2. **The martingale wins the money back.** Total profit ends only a little lower ({usd(d['total'])} vs {usd(n['total'])}).
   * Equity is back at a new high {d['recovery']} months after the crash.
   * For ETH alone the final profit is identical to the cent. The recovery sizing pays back exactly what was lost.
   * BTC ends a little lower, because its profits after the crash are earned at a 27% lower BTC price.
3. **The crash itself is not what needs the capital. The recovery after it is.**
   * The account needs **{usd(d['required'])}**, not {usd(n['required'])}, although the crash month loses only {usd(-d['crash_loss'])}.
   * The peak need comes in **Jan 2025, the month after the crash**:
     * BTC sees the −28% candle and opens its recovery spread at the 4-BTC cap (about {usd(4 * (info['btc_new_trade']['sold'] - info['btc_new_trade']['bought'] - info['btc_new_trade']['credit']))} of collateral).
     * 3b sells its recovery call at {dec['res']['both']['log'].query("month == '2025-01' and book == '3b'").size_x.iloc[0]:.1f}× base.
     * All of that comes on top of the loss just taken.
   * 1b carries its loss through 5 skipped months (Jan–May 2025, after four down months in a row) and comes back
     at **{dec['res']['both']['max_x']['1b']:.0f}× base** in Jun 2025.
4. **Capping the martingale does not raise Calmar** (table below).
   * Tighter caps need less capital but also earn less, and they lengthen the recovery. Calmar stays around 0.4–0.5 in the Dec case.
   * Your current setup (ETH uncapped, BTC capped at 4×) is about as good as any cap tested.
5. **The price of being ready.**
   * If you hold the Dec-crash capital ({usd(d['capital'])}) and the crash never comes, the real history gives
     **{pct(base_on_dec_cap['ann_ret'])} a year with a {pct(base_on_dec_cap['dd_month'])} max drawdown** (Calmar {base_on_dec_cap['calmar_month_end']:.2f}).
   * So the insurance costs most of the return in a normal world.
   * A middle way, about **{usd(round(a['capital'], -3))}–{usd(round(d['required'], -3))} per $10k + $10k ETH base + 1 BTC/leg**, covers an
     Apr-2024-type crash fully. A Dec-type crash would then still need a top-up from outside the exchange.
6. **For comparison, ETH alone in the Dec 2024 crash** (no BTC):
   * Needs {usd(eth_dec['required'])} (+25% = {usd(eth_dec['capital'])}).
   * Loses {usd(-eth_dec['crash_loss'])} in the crash month.
   * Earns {pct(eth_dec['ann_ret'])} a year with Calmar {eth_dec['calmar_month_end']:.2f}.
   * The BTC spread adds about {usd(-d['crash_parts']['btc'])} to the crash loss and ~{usd(d['required'] - eth_dec['required'])} to the capital needed, and keeps its
     extra return. On a risk-adjusted basis the combination stays a little behind ETH alone in this one scenario (Calmar {d['calmar_month_end']:.2f} vs {eth_dec['calmar_month_end']:.2f}).

![Crash scenarios](scenario_crash.png)

---

## Month by month around the Dec 2024 crash

Equity uses the capital held ({usd(d['capital'])}). The ETH and BTC columns are each coin's move that month in the scenario.

{month_lines(dec)}

## Does capping the martingale help? (Dec 2024 crash)

| ETH size cap | BTC size cap | Capital needed | Total P&L | Annual return | Max DD month-end | Calmar month-end | Calmar intramonth |
|---|---|---:|---:|---:|---:|---:|---:|
""" + "\n".join(f"| {e or 'none'} | {b:g}× | {usd(s['required'])} | {usd(s['total'])} | {pct(s['ann_ret'])} | "
                f"{pct(s['dd_month'])} | {s['calmar_month_end']:.2f} | {s['calmar']:.2f} |" for (e, b), s in caps.items()) + """

## Limits

* This is one hand-built path, not a forecast. A real crash could be longer, for example two down months in a row after
  the rally, or it could hit when the martingale is already deeper. Either would need more capital than shown here.
* Implied vol after the crash month is the real one of each later month. After a real crash it would be higher,
  which means richer premiums for the recovery trades (slightly better for the strategy) but also higher margin.
* BTC spreads in the scenario are marked at intrinsic value during the month. Their margin is their max loss
  either way, so this only affects the intramonth drawdown a little.
"""
    (OUT / "SCENARIO.md").write_text(md)


def n_sizes(sc):
    m = sc["res"]["both"]["max_x"]
    return f"{m['1b']:.1f}× / {m['3b']:.1f}× / {m['btc'] * sn.BTC_BASE:.1f} BTC"


if __name__ == "__main__":
    scs = {name: sn.run_scenario(name) for name in NAMES}
    sums = {name: sn.summary(sc) for name, sc in scs.items()}
    eth_dec = sn.summary(scs["Dec 2024"], "eth")
    base_on_dec_cap = sn.summary(scs[None], capital=sums["Dec 2024"]["capital"])
    caps = {}
    for e, b in ((None, 4.0), (6, 4.0), (4, 4.0), (None, 2.0), (None, 1.0), (4, 1.0)):
        caps[(e, b)] = sn.summary(sn.run_scenario("Dec 2024", eth_cap=e, btc_cap_x=b))
    chart(scs, sums)
    write(scs, sums, eth_dec, base_on_dec_cap, caps)
    rows = []
    for name, s in sums.items():
        rows.append({"scenario": LABEL[name], **{k2: v for k2, v in s.items() if not isinstance(v, dict)}})
    pd.DataFrame(rows).to_csv(OUT / "scenario_summary.csv", index=False, float_format="%.4f")
    print("wrote", OUT / "SCENARIO.md")
