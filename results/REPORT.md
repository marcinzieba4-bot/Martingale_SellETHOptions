# Martingale ETH option selling: backtest, Jan 2023 to Sep 2026

Every month, on Deribit's monthly expiry (the last Friday, 08:00 UTC), the strategy sells the
at-the-money ETH option that expires one month later. It is held to expiry and settled at
Deribit's real delivery price.

* **Variant 1: puts.** Sell an ATM put every month.
* **Variant 2: calls.** Sell an ATM call every month.
* **Variant 3: switch.** If ETH rose last month, sell a put. If it fell, sell a call.
* **Martingale sizing.** After a losing month, the next position is made large enough that its premium
  covers the losses still to be recovered, plus the normal premium. Once those losses are recovered,
  the size goes back to the base size.

All dollar figures are for a **base trade of $10,000 ETH notional** (about $650–700 of premium
a month). Every figure scales linearly: for a $50k base trade, multiply by 5.

Period: 45 monthly trades, from the Jan-2023 expiry (sold 30 Dec 2022) to the Sep-2026 expiry (25 Sep 2026).
ETH went from $1,188 to $2,671.

---

## Summary: what the results mean for you

1. **The 7% premium only holds on average in high-volatility years.** An ATM one-month ETH option paid
   **6.6% on average** (median 6.9%). Only **44% of months paid 7% or more**.
   In calm periods it fell to **3.5%** (2023: 5.3% on average). Plan on about 6.5%, not 7%,
   and on 3–4% when implied vol is near 30%.
2. **Variant 1 (puts) is the only one that works without a martingale.** Fixed-size puts made $4,851.
   Fixed-size calls lost $10,834 and the fixed-size switch broke even (-$278). ETH rallies of +20% to +48% in a month
   hurt call sellers much more than the crashes hurt put sellers.
3. **The martingale raised profits here, but only by taking on very large exposures.** It does not change the
   odds. It trades many small losses for rare, very large ones. Profits rose to $16,345 (puts), $3,664 (calls) and $17,892 (switch).
   To get there, the position had to grow to **6.4×**, **19.6×** and **33.3×**
   the base size. The longest losing streak in all three variants was only 3 months. One more losing
   month at the peak size would have cost about $18.7k, $82.8k
   and $97.5k, based on the worst month seen for each side.
4. **Capital needed**, taking the worst possible start month and never being liquidated (Deribit margin, checked every hour):
   * **Puts: about $37.6k** (3.8× the base notional).
     Fully cash-secured, with no leverage: $68.2k.
   * **Calls: about $64.6k** (6.5×). With no leverage: $206.7k.
     It also **finished Sep 2026 with $12,959 of losses not yet recovered**, holding a 20× position.
   * **Switch: about $99.5k** (9.9×). With no leverage: $356.4k.
   * Keep a buffer of **2–3× these figures**. A losing streak one month longer than any in 2023–2026
     would roughly triple the position again (each loss of about 20% against about 7% of premium multiplies the size by about 3).
5. **What to do:**
   * Sell **puts**, not calls.
   * Prefer the **"cover last month only"** rule. For puts it needs **$18.9k** instead of
     $37.6k of capital and still made $12,143. It is the best return on capital in this test:
     14%/yr, against 10%/yr for the full martingale
     and 13%/yr for fixed size.
   * **Cap the multiplier** at about 3–4×, so a longer streak cannot wipe out the account.
   * Size the base trade from your capital. For example, **$100k of capital supports a base trade of about
     $26.6k notional with martingale puts**, or about
     $52.9k with the cover-last-month rule.

![Cumulative P&L](equity.png)

![Position size](position_size.png)

---

## 1. Checking the 7% premium

The premium is priced with Black-Scholes at the **actual Deribit implied vol traded on the ATM strike** of the
next monthly expiry, in the first trades after 08:00 UTC on each roll day (median 4 minutes after the roll).
This modelled premium matches Deribit's own mark price closely (correlation 0.92 for puts, 0.95 for calls). It also
matches a cross-check using the DVOL index (average 7.0%).

| Year | Avg. implied vol | Avg. ATM premium (1 month) | Range |
|---|---:|---:|---:|
| 2023 | 46% | 5.3% | 3.5% – 6.9% |
| 2024 | 60% | 6.9% | 4.5% – 8.1% |
| 2025 | 67% | 7.6% | 6.9% – 8.7% |
| 2026 | 57% | 6.6% | 5.0% – 7.7% |
| **All** | 57% | **6.6%** | 3.5% – 8.7% |

![Premium](premium.png)

Rule of thumb: ATM premium ≈ 0.4 × IV × √(1/12), which is about **IV ÷ 8.7**.
IV 60% → 6.9%, IV 70% → 8%, IV 35% → 4%.

## 2. Results, all variants

The sizing rules:

* **martingale**: size = base + (all unrecovered losses) ÷ premium per unit. It resets only after everything is recovered.
* **last_only**: the literal reading, "cover last month's loss". Size = base + (last month's loss) ÷ premium per unit.
  It resets after any profitable month.
* **fixed**: always the base size. This is the reference.

| Variant | Sizing | Total P&L | Losing months | Max losing streak | Biggest position | Worst month | Max drawdown | Capital (margin) | Capital (margin, worst start) | Capital (no leverage, worst start) | Return/yr on worst-start capital |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 - Sell PUTS | martingale | **$16,345** | 14/45 | 3 | 6.4× ($63,729) | -$3,552 | $4,136 | $27,845 | **$37,575** | $68,243 | 10.1% |
| 1 - Sell PUTS | last_only | **$12,143** | 14/45 | 3 | 5.6× ($55,762) | -$3,552 | $4,136 | $9,177 | **$18,907** | $60,615 | 14.1% |
| 1 - Sell PUTS | fixed | **$4,851** | 14/45 | 3 | 1.0× ($10,000) | -$2,927 | $3,947 | $2,554 | **$8,395** | $14,076 | 12.9% |
| 2 - Sell CALLS | martingale | **$3,664** | 16/45 | 3 | 19.6× ($196,379) | -$9,174 | $12,959 | $47,990 | **$64,612** | $206,722 | 1.5% |
| 2 - Sell CALLS | last_only | **-$6,239** | 16/45 | 3 | 17.5× ($175,305) | -$9,174 | $12,678 | $52,349 | **$58,788** | $185,648 | -2.9% |
| 2 - Sell CALLS | fixed | **-$10,834** | 16/45 | 3 | 1.0× ($10,000) | -$4,215 | $12,607 | $19,420 | **$19,420** | $22,607 | -19.6% |
| 3 - Up->PUTS / Down->CALLS | martingale | **$17,892** | 11/45 | 3 | 33.3× ($333,065) | -$21,832 | $25,097 | $88,944 | **$99,485** | $356,354 | 4.5% |
| 3 - Up->PUTS / Down->CALLS | last_only | **$9,479** | 11/45 | 3 | 7.6× ($75,836) | -$4,392 | $8,174 | $22,304 | **$28,390** | $80,006 | 8.0% |
| 3 - Up->PUTS / Down->CALLS | fixed | **-$278** | 11/45 | 3 | 1.0× ($10,000) | -$4,215 | $11,021 | $13,715 | **$19,186** | $20,966 | -0.4% |

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

| Month | Side | ETH start → settle | Move | IV | Premium | Size | Notional | P&L | Cum. P&L | Losses to recover |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023-01 | PUT | 1,188 → 1,583 | +33.3% | 56% | 6.8% | 1.00× | $10,000 | $667 | $667 | $0 |
| 2023-02 | PUT | 1,583 → 1,653 | +4.4% | 59% | 7.1% | 1.00× | $10,000 | $699 | $1,366 | $0 |
| 2023-03 | PUT | 1,653 → 1,789 | +8.3% | 55% | 8.4% | 1.00× | $10,000 | $827 | $2,193 | $0 |
| 2023-04 | PUT | 1,789 → 1,920 | +7.3% | 59% | 6.9% | 1.00× | $10,000 | $675 | $2,868 | $0 |
| 2023-05 | PUT | 1,920 → 1,814 | -5.5% | 49% | 4.9% | 1.00× | $10,000 | $30 | $2,898 | $0 |
| 2023-06 | PUT | 1,814 → 1,884 | +3.9% | 41% | 4.7% | 1.00× | $10,000 | $465 | $3,363 | $0 |
| 2023-07 | PUT | 1,884 → 1,861 | -1.2% | 38% | 4.7% | 1.00× | $10,000 | $253 | $3,616 | $0 |
| 2023-08 | PUT | 1,861 → 1,651 | -11.3% | 32% | 3.2% | 1.00× | $10,000 | -$756 | $2,860 | $756 |
| 2023-09 | PUT | 1,651 → 1,680 | +1.8% | 32% | 3.9% | 2.96× | $29,606 | $1,141 | $4,001 | $0 |
| 2023-10 | PUT | 1,680 → 1,783 | +6.2% | 32% | 4.2% | 1.00× | $10,000 | $414 | $4,416 | $0 |
| 2023-11 | PUT | 1,783 → 2,074 | +16.3% | 43% | 5.3% | 1.00× | $10,000 | $520 | $4,935 | $0 |
| 2023-12 | PUT | 2,074 → 2,345 | +13.1% | 50% | 6.8% | 1.00× | $10,000 | $673 | $5,608 | $0 |
| 2024-01 | PUT | 2,345 → 2,201 | -6.1% | 62% | 7.0% | 1.00× | $10,000 | $54 | $5,662 | $0 |
| 2024-02 | PUT | 2,201 → 2,933 | +33.2% | 41% | 4.5% | 1.00× | $10,000 | $442 | $6,104 | $0 |
| 2024-03 | PUT | 2,933 → 3,536 | +20.5% | 55% | 6.2% | 1.00× | $10,000 | $615 | $6,719 | $0 |
| 2024-04 | PUT | 3,536 → 3,137 | -11.3% | 74% | 8.3% | 1.00× | $10,000 | -$346 | $6,373 | $346 |
| 2024-05 | PUT | 3,137 → 3,732 | +18.9% | 60% | 6.8% | 1.51× | $15,143 | $1,020 | $7,393 | $0 |
| 2024-06 | PUT | 3,732 → 3,433 | -8.0% | 62% | 6.4% | 1.00× | $10,000 | -$84 | $7,309 | $84 |
| 2024-07 | PUT | 3,433 → 3,257 | -5.1% | 58% | 5.9% | 1.15× | $11,459 | $183 | $7,491 | $0 |
| 2024-08 | PUT | 3,257 → 2,524 | -22.5% | 63% | 8.5% | 1.00× | $10,000 | -$1,544 | $5,947 | $1,544 |
| 2024-09 | PUT | 2,524 → 2,660 | +5.4% | 60% | 6.1% | 3.56× | $35,618 | $2,147 | $8,094 | $0 |
| 2024-10 | PUT | 2,660 → 2,474 | -7.0% | 56% | 7.0% | 1.00× | $10,000 | -$158 | $7,936 | $158 |
| 2024-11 | PUT | 2,474 → 3,549 | +43.4% | 60% | 7.9% | 1.20× | $12,022 | $939 | $8,875 | $0 |
| 2024-12 | PUT | 3,549 → 3,334 | -6.0% | 68% | 6.8% | 1.00× | $10,000 | $199 | $9,074 | $0 |
| 2025-01 | PUT | 3,334 → 3,251 | -2.5% | 71% | 8.1% | 1.00× | $10,000 | $655 | $9,729 | $0 |
| 2025-02 | PUT | 3,251 → 2,102 | -35.3% | 62% | 7.7% | 1.00× | $10,000 | -$2,927 | $6,803 | $2,927 |
| 2025-03 | PUT | 2,102 → 1,910 | -9.1% | 72% | 7.9% | 4.75× | $47,514 | -$586 | $6,216 | $3,513 |
| 2025-04 | PUT | 1,910 → 1,774 | -7.2% | 63% | 6.6% | 6.37× | $63,729 | -$55 | $6,161 | $3,568 |
| 2025-05 | PUT | 1,774 → 2,627 | +48.1% | 67% | 9.1% | 4.98× | $49,753 | $4,466 | $10,627 | $0 |
| 2025-06 | PUT | 2,627 → 2,442 | -7.0% | 69% | 7.1% | 1.00× | $10,000 | $98 | $10,726 | $0 |
| 2025-07 | PUT | 2,442 → 3,620 | +48.2% | 64% | 6.2% | 1.00× | $10,000 | $611 | $11,337 | $0 |
| 2025-08 | PUT | 3,620 → 4,389 | +21.3% | 66% | 7.9% | 1.00× | $10,000 | $777 | $12,114 | $0 |
| 2025-09 | PUT | 4,389 → 3,921 | -10.7% | 69% | 7.8% | 1.00× | $10,000 | -$325 | $11,788 | $325 |
| 2025-10 | PUT | 3,921 → 3,830 | -2.3% | 62% | 7.3% | 1.45× | $14,506 | $785 | $12,573 | $0 |
| 2025-11 | PUT | 3,830 → 3,010 | -21.4% | 66% | 6.9% | 1.00× | $10,000 | -$1,387 | $11,186 | $1,387 |
| 2025-12 | PUT | 3,010 → 2,965 | -1.5% | 68% | 7.3% | 2.92× | $29,175 | $1,769 | $12,954 | $0 |
| 2026-01 | PUT | 2,965 → 2,731 | -7.9% | 61% | 8.1% | 1.00× | $10,000 | -$104 | $12,850 | $104 |
| 2026-02 | PUT | 2,731 → 2,029 | -25.7% | 57% | 5.7% | 1.19× | $11,870 | -$2,256 | $10,594 | $2,360 |
| 2026-03 | PUT | 2,029 → 2,067 | +1.9% | 66% | 7.9% | 4.05× | $40,483 | $3,135 | $13,729 | $0 |
| 2026-04 | PUT | 2,067 → 2,314 | +11.9% | 70% | 7.3% | 1.00× | $10,000 | $721 | $14,449 | $0 |
| 2026-05 | PUT | 2,314 → 2,004 | -13.4% | 60% | 7.1% | 1.00× | $10,000 | -$584 | $13,865 | $584 |
| 2026-06 | PUT | 2,004 → 1,580 | -21.2% | 46% | 4.9% | 2.20× | $22,026 | -$3,552 | $10,313 | $4,136 |
| 2026-07 | PUT | 1,580 → 1,887 | +19.5% | 58% | 7.9% | 6.33× | $63,293 | $4,912 | $15,225 | $0 |
| 2026-08 | PUT | 1,887 → 2,497 | +32.3% | 47% | 5.6% | 1.00× | $10,000 | $551 | $15,777 | $0 |
| 2026-09 | PUT | 2,497 → 2,671 | +7.0% | 52% | 5.8% | 1.00× | $10,000 | $568 | $16,345 | $0 |

</details>

<details><summary>Variant 2: sell calls</summary>

| Month | Side | ETH start → settle | Move | IV | Premium | Size | Notional | P&L | Cum. P&L | Losses to recover |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023-01 | CALL | 1,188 → 1,583 | +33.3% | 56% | 5.7% | 1.00× | $10,000 | -$2,660 | -$2,660 | $2,660 |
| 2023-02 | CALL | 1,583 → 1,653 | +4.4% | 59% | 6.0% | 5.49× | $54,946 | $1,416 | -$1,244 | $1,244 |
| 2023-03 | CALL | 1,653 → 1,789 | +8.3% | 55% | 5.5% | 3.29× | $32,911 | $5 | -$1,238 | $1,238 |
| 2023-04 | CALL | 1,789 → 1,920 | +7.3% | 59% | 6.2% | 3.01× | $30,118 | -$163 | -$1,401 | $1,401 |
| 2023-05 | CALL | 1,920 → 1,814 | -5.5% | 49% | 5.9% | 3.41× | $34,113 | $1,982 | $581 | $0 |
| 2023-06 | CALL | 1,814 → 1,884 | +3.9% | 41% | 5.5% | 1.00× | $10,000 | $76 | $657 | $0 |
| 2023-07 | CALL | 1,884 → 1,861 | -1.2% | 38% | 3.8% | 1.00× | $10,000 | $378 | $1,035 | $0 |
| 2023-08 | CALL | 1,861 → 1,651 | -11.3% | 32% | 3.8% | 1.00× | $10,000 | $374 | $1,409 | $0 |
| 2023-09 | CALL | 1,651 → 1,680 | +1.8% | 32% | 4.0% | 1.00× | $10,000 | $208 | $1,618 | $0 |
| 2023-10 | CALL | 1,680 → 1,783 | +6.2% | 32% | 3.0% | 1.00× | $10,000 | -$204 | $1,414 | $204 |
| 2023-11 | CALL | 1,783 → 2,074 | +16.3% | 43% | 4.3% | 1.48× | $14,768 | -$1,637 | -$223 | $1,841 |
| 2023-12 | CALL | 2,074 → 2,345 | +13.1% | 50% | 5.6% | 4.37× | $43,667 | -$2,777 | -$3,000 | $4,618 |
| 2024-01 | CALL | 2,345 → 2,201 | -6.1% | 62% | 6.8% | 7.92× | $79,179 | $5,285 | $2,285 | $0 |
| 2024-02 | CALL | 2,201 → 2,933 | +33.2% | 41% | 4.6% | 1.00× | $10,000 | -$2,885 | -$599 | $2,885 |
| 2024-03 | CALL | 2,933 → 3,536 | +20.5% | 55% | 7.4% | 4.97× | $49,663 | -$7,160 | -$7,760 | $10,045 |
| 2024-04 | CALL | 3,536 → 3,137 | -11.3% | 74% | 7.9% | 13.85× | $138,513 | $10,827 | $3,067 | $0 |
| 2024-05 | CALL | 3,137 → 3,732 | +18.9% | 60% | 8.0% | 1.00× | $10,000 | -$1,224 | $1,843 | $1,224 |
| 2024-06 | CALL | 3,732 → 3,433 | -8.0% | 62% | 7.3% | 2.71× | $27,066 | $1,942 | $3,784 | $0 |
| 2024-07 | CALL | 3,433 → 3,257 | -5.1% | 58% | 6.8% | 1.00× | $10,000 | $673 | $4,457 | $0 |
| 2024-08 | CALL | 3,257 → 2,524 | -22.5% | 63% | 7.2% | 1.00× | $10,000 | $709 | $5,166 | $0 |
| 2024-09 | CALL | 2,524 → 2,660 | +5.4% | 60% | 7.1% | 1.00× | $10,000 | $60 | $5,227 | $0 |
| 2024-10 | CALL | 2,660 → 2,474 | -7.0% | 56% | 5.5% | 1.00× | $10,000 | $544 | $5,770 | $0 |
| 2024-11 | CALL | 2,474 → 3,549 | +43.4% | 60% | 6.9% | 1.00× | $10,000 | -$3,563 | $2,207 | $3,563 |
| 2024-12 | CALL | 3,549 → 3,334 | -6.0% | 68% | 8.1% | 5.43× | $54,341 | $4,366 | $6,574 | $0 |
| 2025-01 | CALL | 3,334 → 3,251 | -2.5% | 71% | 9.2% | 1.00× | $10,000 | $905 | $7,479 | $0 |
| 2025-02 | CALL | 3,251 → 2,102 | -35.3% | 62% | 6.2% | 1.00× | $10,000 | $609 | $8,088 | $0 |
| 2025-03 | CALL | 2,102 → 1,910 | -9.1% | 72% | 8.0% | 1.00× | $10,000 | $791 | $8,880 | $0 |
| 2025-04 | CALL | 1,910 → 1,774 | -7.2% | 63% | 7.2% | 1.00× | $10,000 | $707 | $9,587 | $0 |
| 2025-05 | CALL | 1,774 → 2,627 | +48.1% | 67% | 7.6% | 1.00× | $10,000 | -$3,912 | $5,674 | $3,912 |
| 2025-06 | CALL | 2,627 → 2,442 | -7.0% | 69% | 8.1% | 5.88× | $58,778 | $4,714 | $10,389 | $0 |
| 2025-07 | CALL | 2,442 → 3,620 | +48.2% | 64% | 7.9% | 1.00× | $10,000 | -$4,215 | $6,173 | $4,215 |
| 2025-08 | CALL | 3,620 → 4,389 | +21.3% | 66% | 8.4% | 6.08× | $60,751 | -$8,212 | -$2,038 | $12,427 |
| 2025-09 | CALL | 4,389 → 3,921 | -10.7% | 69% | 7.5% | 17.71× | $177,119 | $13,171 | $11,133 | $0 |
| 2025-10 | CALL | 3,921 → 3,830 | -2.3% | 62% | 7.8% | 1.00× | $10,000 | $774 | $11,907 | $0 |
| 2025-11 | CALL | 3,830 → 3,010 | -21.4% | 66% | 7.6% | 1.00× | $10,000 | $754 | $12,661 | $0 |
| 2025-12 | CALL | 3,010 → 2,965 | -1.5% | 68% | 7.7% | 1.00× | $10,000 | $756 | $13,417 | $0 |
| 2026-01 | CALL | 2,965 → 2,731 | -7.9% | 61% | 7.0% | 1.00× | $10,000 | $687 | $14,104 | $0 |
| 2026-02 | CALL | 2,731 → 2,029 | -25.7% | 57% | 6.8% | 1.00× | $10,000 | $671 | $14,775 | $0 |
| 2026-03 | CALL | 2,029 → 2,067 | +1.9% | 66% | 6.8% | 1.00× | $10,000 | $586 | $15,361 | $0 |
| 2026-04 | CALL | 2,067 → 2,314 | +11.9% | 70% | 8.1% | 1.00× | $10,000 | -$477 | $14,884 | $477 |
| 2026-05 | CALL | 2,314 → 2,004 | -13.4% | 60% | 7.7% | 1.63× | $16,313 | $1,232 | $16,116 | $0 |
| 2026-06 | CALL | 2,004 → 1,580 | -21.2% | 46% | 5.1% | 1.00× | $10,000 | $506 | $16,622 | $0 |
| 2026-07 | CALL | 1,580 → 1,887 | +19.5% | 58% | 6.6% | 1.00× | $10,000 | -$1,170 | $15,453 | $1,170 |
| 2026-08 | CALL | 1,887 → 2,497 | +32.3% | 47% | 4.9% | 3.42× | $34,213 | -$9,174 | $6,279 | $10,344 |
| 2026-09 | CALL | 2,497 → 2,671 | +7.0% | 52% | 5.6% | 19.64× | $196,379 | -$2,615 | $3,664 | $12,959 |

</details>

<details><summary>Variant 3: up → puts, down → calls</summary>

| Month | Side | ETH start → settle | Move | IV | Premium | Size | Notional | P&L | Cum. P&L | Losses to recover |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| 2023-01 | PUT | 1,188 → 1,583 | +33.3% | 56% | 6.8% | 1.00× | $10,000 | $667 | $667 | $0 |
| 2023-02 | PUT | 1,583 → 1,653 | +4.4% | 59% | 7.1% | 1.00× | $10,000 | $699 | $1,366 | $0 |
| 2023-03 | PUT | 1,653 → 1,789 | +8.3% | 55% | 8.4% | 1.00× | $10,000 | $827 | $2,193 | $0 |
| 2023-04 | PUT | 1,789 → 1,920 | +7.3% | 59% | 6.9% | 1.00× | $10,000 | $675 | $2,868 | $0 |
| 2023-05 | PUT | 1,920 → 1,814 | -5.5% | 49% | 4.9% | 1.00× | $10,000 | $30 | $2,898 | $0 |
| 2023-06 | CALL | 1,814 → 1,884 | +3.9% | 41% | 5.5% | 1.00× | $10,000 | $76 | $2,974 | $0 |
| 2023-07 | PUT | 1,884 → 1,861 | -1.2% | 38% | 4.7% | 1.00× | $10,000 | $253 | $3,227 | $0 |
| 2023-08 | CALL | 1,861 → 1,651 | -11.3% | 32% | 3.8% | 1.00× | $10,000 | $374 | $3,601 | $0 |
| 2023-09 | CALL | 1,651 → 1,680 | +1.8% | 32% | 4.0% | 1.00× | $10,000 | $208 | $3,809 | $0 |
| 2023-10 | PUT | 1,680 → 1,783 | +6.2% | 32% | 4.2% | 1.00× | $10,000 | $414 | $4,224 | $0 |
| 2023-11 | PUT | 1,783 → 2,074 | +16.3% | 43% | 5.3% | 1.00× | $10,000 | $520 | $4,744 | $0 |
| 2023-12 | PUT | 2,074 → 2,345 | +13.1% | 50% | 6.8% | 1.00× | $10,000 | $673 | $5,417 | $0 |
| 2024-01 | PUT | 2,345 → 2,201 | -6.1% | 62% | 7.0% | 1.00× | $10,000 | $54 | $5,471 | $0 |
| 2024-02 | CALL | 2,201 → 2,933 | +33.2% | 41% | 4.6% | 1.00× | $10,000 | -$2,885 | $2,586 | $2,885 |
| 2024-03 | PUT | 2,933 → 3,536 | +20.5% | 55% | 6.2% | 5.69× | $56,902 | $3,500 | $6,086 | $0 |
| 2024-04 | PUT | 3,536 → 3,137 | -11.3% | 74% | 8.3% | 1.00× | $10,000 | -$346 | $5,739 | $346 |
| 2024-05 | CALL | 3,137 → 3,732 | +18.9% | 60% | 8.0% | 1.44× | $14,376 | -$1,760 | $3,979 | $2,106 |
| 2024-06 | PUT | 3,732 → 3,433 | -8.0% | 62% | 6.4% | 4.33× | $43,301 | -$365 | $3,614 | $2,471 |
| 2024-07 | CALL | 3,433 → 3,257 | -5.1% | 58% | 6.8% | 4.67× | $46,740 | $3,144 | $6,758 | $0 |
| 2024-08 | CALL | 3,257 → 2,524 | -22.5% | 63% | 7.2% | 1.00× | $10,000 | $709 | $7,468 | $0 |
| 2024-09 | CALL | 2,524 → 2,660 | +5.4% | 60% | 7.1% | 1.00× | $10,000 | $60 | $7,528 | $0 |
| 2024-10 | PUT | 2,660 → 2,474 | -7.0% | 56% | 7.0% | 1.00× | $10,000 | -$158 | $7,370 | $158 |
| 2024-11 | CALL | 2,474 → 3,549 | +43.4% | 60% | 6.9% | 1.23× | $12,328 | -$4,392 | $2,978 | $4,550 |
| 2024-12 | PUT | 3,549 → 3,334 | -6.0% | 68% | 6.8% | 7.82× | $78,203 | $1,556 | $4,533 | $2,995 |
| 2025-01 | CALL | 3,334 → 3,251 | -2.5% | 71% | 9.2% | 4.31× | $43,089 | $3,900 | $8,433 | $0 |
| 2025-02 | CALL | 3,251 → 2,102 | -35.3% | 62% | 6.2% | 1.00× | $10,000 | $609 | $9,042 | $0 |
| 2025-03 | CALL | 2,102 → 1,910 | -9.1% | 72% | 8.0% | 1.00× | $10,000 | $791 | $9,834 | $0 |
| 2025-04 | CALL | 1,910 → 1,774 | -7.2% | 63% | 7.2% | 1.00× | $10,000 | $707 | $10,541 | $0 |
| 2025-05 | CALL | 1,774 → 2,627 | +48.1% | 67% | 7.6% | 1.00× | $10,000 | -$3,912 | $6,628 | $3,912 |
| 2025-06 | PUT | 2,627 → 2,442 | -7.0% | 69% | 7.1% | 6.58× | $65,782 | $647 | $7,276 | $3,265 |
| 2025-07 | CALL | 2,442 → 3,620 | +48.2% | 64% | 7.9% | 5.18× | $51,791 | -$21,832 | -$14,556 | $25,097 |
| 2025-08 | PUT | 3,620 → 4,389 | +21.3% | 66% | 7.9% | 33.31× | $333,065 | $25,874 | $11,318 | $0 |
| 2025-09 | PUT | 4,389 → 3,921 | -10.7% | 69% | 7.8% | 1.00× | $10,000 | -$325 | $10,993 | $325 |
| 2025-10 | CALL | 3,921 → 3,830 | -2.3% | 62% | 7.8% | 1.42× | $14,200 | $1,099 | $12,092 | $0 |
| 2025-11 | CALL | 3,830 → 3,010 | -21.4% | 66% | 7.6% | 1.00× | $10,000 | $754 | $12,846 | $0 |
| 2025-12 | CALL | 3,010 → 2,965 | -1.5% | 68% | 7.7% | 1.00× | $10,000 | $756 | $13,602 | $0 |
| 2026-01 | CALL | 2,965 → 2,731 | -7.9% | 61% | 7.0% | 1.00× | $10,000 | $687 | $14,289 | $0 |
| 2026-02 | CALL | 2,731 → 2,029 | -25.7% | 57% | 6.8% | 1.00× | $10,000 | $671 | $14,960 | $0 |
| 2026-03 | CALL | 2,029 → 2,067 | +1.9% | 66% | 6.8% | 1.00× | $10,000 | $586 | $15,546 | $0 |
| 2026-04 | PUT | 2,067 → 2,314 | +11.9% | 70% | 7.3% | 1.00× | $10,000 | $721 | $16,267 | $0 |
| 2026-05 | PUT | 2,314 → 2,004 | -13.4% | 60% | 7.1% | 1.00× | $10,000 | -$584 | $15,682 | $584 |
| 2026-06 | CALL | 2,004 → 1,580 | -21.2% | 46% | 5.1% | 2.16× | $21,553 | $1,090 | $16,773 | $0 |
| 2026-07 | CALL | 1,580 → 1,887 | +19.5% | 58% | 6.6% | 1.00× | $10,000 | -$1,170 | $15,603 | $1,170 |
| 2026-08 | PUT | 1,887 → 2,497 | +32.3% | 47% | 5.6% | 3.12× | $31,211 | $1,721 | $17,324 | $0 |
| 2026-09 | PUT | 2,497 → 2,671 | +7.0% | 52% | 5.8% | 1.00× | $10,000 | $568 | $17,892 | $0 |

</details>

The logs for all 9 variant and rule combinations are in `results/trades_<variant>_<rule>.csv`.

## 4. Where it went wrong or nearly did

* **Puts:** Feb–Apr 2025 had 3 losses in a row. ETH fell from $3,250 to $1,770, and the size grew to
  6.4× before the May-2025 rally recovered everything. Jun 2026 (ETH -21%)
  was the largest single loss, -$3,552.
* **Calls:** every strong rally caused a streak: Oct–Dec 2023, Feb–Mar 2024, and Jul–Aug 2025 (+48%, then +21%).
  The size reached 17.7× in Sep 2025. Aug and Sep 2026 (+32%, +7%) left the strategy with $12,959
  still to recover.
* **Switch:** the direction signal was wrong at the worst moment. After ETH fell in Apr 2025 it sold calls
  into the +48% rally of May 2025, and again into Jul 2025. That pushed the size to **33×
  ($333,065 notional) in Aug 2025.** If that month had been as bad as the worst put month in the
  sample (ETH -35%), it would have lost about $97.5k.

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
