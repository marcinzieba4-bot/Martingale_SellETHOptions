"""Hedging the danger months (hedges.py) against the 2024 crash scenarios: chart and results/HEDGE.md."""
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

import hedges as hd
import scenario as sn
from backtest import OUT
from report import INK, INK2, SLOT, usd  # also applies the chart style

WORLDS = [None, "Apr 2024", "Dec 2024"]
WNAME = {None: "No crash", "Apr 2024": "Crash Apr 2024", "Dec 2024": "Crash Dec 2024"}


def pct(x, d=1):
    return f"{x * 100:.{d}f}%"


def collect():
    rows = []
    for v in hd.VARIANTS:
        scs = {w: sn.run_scenario(w, hedge=v) for w in WORLDS}
        cap = scs["Dec 2024"]["res"]["both"]["capital"] * (1 + sn.CUSHION)
        row = dict(variant=v, label=hd.LABELS[v], capital=cap, danger_months=int(sum(scs[None]["danger"])))
        for w, sc in scs.items():
            s = sn.summary(sc, capital=cap)
            tag = WNAME[w]
            row.update({f"{tag}|{k}": s[k] for k in ("total", "ann_ret", "dd_month", "dd_intra", "calmar_month_end",
                                                      "calmar", "worst_month")})
            if w is not None:
                row[f"{tag}|crash_loss"] = s["crash_loss"]
                row[f"{tag}|crash_parts"] = s["crash_parts"]
                row[f"{tag}|max_x"] = sc["res"]["both"]["max_x"]
        row["worst_calmar"] = min(row[f"{WNAME[w]}|calmar_month_end"] for w in WORLDS)
        rows.append(row)
    return pd.DataFrame(rows)


def chart(df):
    show = df[~df.variant.str.contains("delta")].reset_index(drop=True)
    fig, ax = plt.subplots(figsize=(11, 5.2))
    y = np.arange(len(show))
    h = 0.26
    for j, (w, c) in enumerate(zip(WORLDS, SLOT)):
        vals = show[f"{WNAME[w]}|calmar_month_end"].to_numpy()
        ax.barh(y + (j - 1) * h, vals, height=h - 0.03, color=c, label=WNAME[w])
        for yy, v in zip(y + (j - 1) * h, vals):
            ax.annotate(f"{v:.2f}", (v, yy), xytext=(3, 0), textcoords="offset points", va="center", fontsize=8,
                        color=INK2)
    ax.set_yticks(y)
    ax.set_yticklabels([f"{r.label}  ({usd(r.capital)})" for _, r in show.iterrows()], fontsize=9)
    ax.invert_yaxis()
    ax.set_xlabel("Calmar (annual return ÷ max month-end drawdown)")
    ax.set_xlim(0, max(show[[f"{WNAME[w]}|calmar_month_end" for w in WORLDS]].max()) * 1.32)
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    ax.set_title("Hedging the danger months: Calmar in each world · capital = what the Dec-2024 crash needs + 25%",
                 loc="left", fontsize=11, weight="bold", color=INK)
    fig.tight_layout()
    fig.savefig(OUT / "hedge_calmar.png", dpi=150)
    plt.close(fig)


def write(df):
    r = df.set_index("variant")
    n, best, keep = r.loc["none"], r.loc["eth_put20+btc_skip"], r.loc["eth_put15+btc_w15"]
    dec, apr, nc = "Crash Dec 2024", "Crash Apr 2024", "No crash"
    dl = r.loc["eth_delta"]

    def parts(v, w=dec):
        p = r.loc[v, f"{w}|crash_parts"]
        return f"{usd(p.get('1b', 0))} / {usd(p.get('3b', 0))} / {usd(p.get('btc', 0))}"

    rows = ["| Hedge in danger months | Capital held | Crash-month loss Dec 2024 (1b / 3b / BTC) | Annual return | "
            "Calmar: no crash | Calmar: crash Apr 2024 | **Calmar: crash Dec 2024** | Max DD, Dec crash | P&L, no crash |",
            "|---|---:|---|---:|---:|---:|---:|---:|---:|"]
    for v, x in r.iterrows():
        name = f"**{x.label}**" if v in ("eth_put20+btc_skip", "eth_put15+btc_w15") else x.label
        rows.append(f"| {name} | {usd(x.capital)} | {usd(x[f'{dec}|crash_loss'])} ({parts(v)}) | "
                    f"{pct(x[f'{nc}|ann_ret'])} | {x[f'{nc}|calmar_month_end']:.2f} | {x[f'{apr}|calmar_month_end']:.2f} | "
                    f"**{x[f'{dec}|calmar_month_end']:.2f}** | {pct(x[f'{dec}|dd_month'])} | {usd(x[f'{nc}|total'])} |")
    md = f"""# Hedging the "danger months": can it stop Calmar falling to 0.47 in a crash?

**Setup.** This is the same portfolio and the same crash simulation as [SCENARIO.md](SCENARIO.md): ETH 1b + 3b
($10k + $10k base, martingale) plus the BTC put spread at 1 BTC/leg, Jan 2023 – Sep 2026. The crash is ETH −35%
and BTC −28% in the same month, right after a rally of both coins.

**Danger month:** ETH rose last month (so 1b and 3b both sell a put) **and** BTC had a big green candle (so the BTC
strategy sells its spread). All three positions are short the downside at once. That happened in
{int(n.danger_months)} of 45 months, including the two crash months tested. **Every hedge below is used only in danger months.**

**Capital.** For each hedge it is what the account needs to survive the Dec 2024 crash, plus 25%. You prepare
for the worst case, so the same capital is used in all three worlds.

---

## Summary: what the results mean for you

1. **Yes, hedging the danger months works. Calmar in the Dec 2024 crash goes from {n[f'{dec}|calmar_month_end']:.2f} to {best[f'{dec}|calmar_month_end']:.2f}.**
   The best version is **"buy a 20% OTM ETH put + skip the BTC trade"** in danger months:
   * The crash month costs {usd(-best[f'{dec}|crash_loss'])} instead of {usd(-n[f'{dec}|crash_loss'])}.
   * The capital needed falls from {usd(n.capital)} to **{usd(best.capital)}**.
   * The annual return on that capital rises from {pct(n[f'{nc}|ann_ret'])} to **{pct(best[f'{nc}|ann_ret'])}**, in all three worlds.
   * Calmar in the Apr 2024 crash rises from {n[f'{apr}|calmar_month_end']:.2f} to {best[f'{apr}|calmar_month_end']:.2f}.
2. **If you want to keep the BTC trade:** use **"buy a 15% OTM ETH put + narrow the BTC spread to a 15% wing"**.
   * Dec-crash Calmar {keep[f'{dec}|calmar_month_end']:.2f} on {usd(keep.capital)}, with {pct(keep[f'{nc}|ann_ret'])} a year.
   * It keeps more profit in normal months ({usd(keep[f'{nc}|total'])} vs {usd(best[f'{nc}|total'])}), but needs more capital.
3. **Your hunch about BTC is right, and the reason is its recovery size, not just its loss.**
   * BTC's crash loss is {usd(-n[f'{dec}|crash_parts']['btc'])}. Its −28% candle then makes it open the next trade at the 4-BTC cap,
     which needs about $24k of collateral at the worst moment.
   * Skipping BTC in danger months alone lifts the Dec-crash Calmar to {r.loc['btc_skip', f'{dec}|calmar_month_end']:.2f} and cuts the capital to {usd(r.loc['btc_skip'].capital)}.
   * A narrower 15% wing alone gives {r.loc['btc_w15', f'{dec}|calmar_month_end']:.2f}.
4. **The ETH tail put is cheap insurance.** A 20% OTM put costs about 1.2–1.4% of the ETH price, against about 6.6% collected on the ATM put.
   * Over the {int(n.danger_months)} danger months it cost {usd(n[f'{nc}|total'] - r.loc['eth_put20', f'{nc}|total'])} net in the real history.
   * In the Dec crash it pays back {usd(r.loc['eth_put20', f'{dec}|crash_loss'] - n[f'{dec}|crash_loss'])}.
   * The 15% put protects more ({usd(r.loc['eth_put15', f'{dec}|crash_loss'] - n[f'{dec}|crash_loss'])}) but costs more in normal months.
5. **Daily delta hedging does not work with the martingale.** Calmar falls to {dl[f'{dec}|calmar_month_end']:.2f}, and the capital needed is {usd(dl.capital)}.
   * In normal up months the hedge loses about as much as the put earns, which turns winners into small losers.
   * The recovery rule then sizes up: 3b reached 43× base in mid-2024.
   * The BTC session found the same with its own recovery rule: the martingale must not be combined with hedges that realise small losses.
6. **The price of the hedge.**
   * With no crash, the hedged versions earn more per $ of capital ({pct(best[f'{nc}|ann_ret'])} vs {pct(n[f'{nc}|ann_ret'])}), because they need less capital.
     But they swing more, so the no-crash Calmar is lower ({best[f'{nc}|calmar_month_end']:.2f} vs {n[f'{nc}|calmar_month_end']:.2f}).
   * You give up some of the smoothness of the good world to roughly halve the damage in the bad one.
   * The worst Calmar across the three worlds rises from {n.worst_calmar:.2f} to {best.worst_calmar:.2f}.

### Rule to use

In a month where **ETH rose last month and BTC moved more than +10%**, at the monthly roll (last Friday, 08:00 UTC):
1. Sell the ETH puts as usual (1b and 3b, with their martingale sizes).
2. **Buy the ETH put nearest 0.80 × price**, same expiry, **1 for every ETH put sold** (the 1b and 3b sizes added together).
3. **Skip the BTC spread that month.** Or, to keep it: buy the 15% OTM BTC put instead of the 20% one, and buy the 0.85 × price ETH put instead.
4. Count the protective put's cost and payoff in the month's result for the martingale. That way, a crash that the put
   absorbed does not force a big recovery size afterwards.

![Calmar by hedge](hedge_calmar.png)

---

## All variants (capital = what the Dec 2024 crash needs + 25%)

{chr(10).join(rows)}

* "Annual return" is on the capital held, with no crash. With the crash it is almost the same, because the martingale
  wins the loss back. The full numbers are in `results/hedge_summary.csv`.
* ETH tail puts use real Deribit prices of the 15% / 20% OTM put at each roll (`data/eth_otm_put_quotes.csv`).
  The one missing 20% quote (Jun 2025) is priced from the 15% put's implied vol.
* The BTC 15% wing uses the BTC session's own code and quotes (`btc/btc_spread_trades_w15.csv`).
* The delta hedge rebalances once a day at 08:00 UTC to the Black-Scholes delta (ATM implied vol moved by DVOL),
  pays 0.1% per perp fill and real funding.

## Limits

* This is one hand-built crash path and 13 danger months in 3¾ years, so treat the numbers as an estimate.
* The protective put helps most against a fast, deep crash like this one. In a slow −10% to −15% month it would expire
  worthless and the ETH puts would still lose.
* Skipping BTC in danger months gave up profit that BTC earned in every one of those months historically
  ({usd(r.loc['none', f'{nc}|total'] - r.loc['btc_skip', f'{nc}|total'])} over 2023–26). That is the price of not stacking three short-downside positions.
"""
    (OUT / "HEDGE.md").write_text(md)


if __name__ == "__main__":
    df = collect()
    flat = df.drop(columns=[c for c in df.columns if c.endswith("|crash_parts") or c.endswith("|max_x")])
    flat.to_csv(OUT / "hedge_summary.csv", index=False, float_format="%.4f")
    chart(df)
    write(df)
    print("wrote", OUT / "HEDGE.md")
