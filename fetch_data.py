"""Download the market data used by the backtest from Deribit's public API.

Outputs (in ./data):
  delivery_prices.csv  - daily ETH index settlement price (08:00 UTC, what options settle on)
  eth_hourly.csv       - hourly ETH-PERPETUAL OHLC (used for intramonth mark-to-market / margin)
  dvol_hourly.csv      - hourly ETH DVOL (30d implied-vol index)
  atm_quotes.csv       - for every monthly roll: ATM strike and the market implied vol / mark
                         of the next monthly ETH option, taken from real Deribit trades
"""
import datetime as dt
import json
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import pandas as pd

API = "https://www.deribit.com/api/v2/public/"
HIST = "https://history.deribit.com/api/v2/public/"
DATA = Path(__file__).parent / "data"

START = dt.datetime(2022, 11, 1, tzinfo=dt.timezone.utc)   # need Dec-2022 for the first sale + Nov direction
END = dt.datetime(2026, 9, 26, tzinfo=dt.timezone.utc)
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


def get(base, method, **params):
    url = base + method + "?" + urllib.parse.urlencode(params)
    for attempt in range(6):
        try:
            with urllib.request.urlopen(url, timeout=60) as r:
                return json.load(r)["result"]
        except urllib.error.HTTPError as e:
            if e.code == 400:  # e.g. instrument/strike that was never listed
                return None
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)
            print("retry", method, e)
        except Exception as e:  # noqa: BLE001 - retry any transient network error
            if attempt == 5:
                raise
            time.sleep(2 ** attempt)
            print("retry", method, e)


def ms(t):
    return int(t.timestamp() * 1000)


def last_friday(year, month):
    nxt = dt.date(year + (month == 12), month % 12 + 1, 1)
    d = nxt - dt.timedelta(days=1)
    while d.weekday() != 4:
        d -= dt.timedelta(days=1)
    return d


def monthly_expiries():
    out, y, m = [], 2022, 11
    while (y, m) <= (2026, 9):
        out.append(last_friday(y, m))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def instrument(expiry, strike, kind):
    return f"ETH-{expiry.day}{MONTHS[expiry.month - 1]}{expiry.year % 100:02d}-{int(strike)}-{kind}"


def fetch_delivery_prices():
    rows, offset = [], 0
    while True:
        res = get(API, "get_delivery_prices", index_name="eth_usd", offset=offset, count=1000)
        rows += res["data"]
        offset += len(res["data"])
        if not res["data"] or offset >= res["records_total"]:
            break
    df = pd.DataFrame(rows).rename(columns={"delivery_price": "price"})
    df["date"] = pd.to_datetime(df["date"])
    df = df.sort_values("date")
    df[df.date >= "2022-10-01"].to_csv(DATA / "delivery_prices.csv", index=False)
    return df


def fetch_hourly():
    frames, dvol = [], []
    t = START
    while t < END:
        t2 = min(t + dt.timedelta(days=30), END)
        c = get(API, "get_tradingview_chart_data", instrument_name="ETH-PERPETUAL",
                start_timestamp=ms(t), end_timestamp=ms(t2), resolution=60)
        frames.append(pd.DataFrame({k: c[k] for k in ("ticks", "open", "high", "low", "close")}))
        v = get(API, "get_volatility_index_data", currency="ETH",
                start_timestamp=ms(t), end_timestamp=ms(t2), resolution=3600)
        dvol.append(pd.DataFrame(v["data"], columns=["ticks", "open", "high", "low", "close"]))
        t = t2
    for name, parts in (("eth_hourly", frames), ("dvol_hourly", dvol)):
        df = pd.concat(parts).drop_duplicates("ticks").sort_values("ticks")
        df.insert(0, "time", pd.to_datetime(df.ticks, unit="ms", utc=True))
        df.drop(columns="ticks").to_csv(DATA / f"{name}.csv", index=False)


def fetch_atm_quotes(delivery):
    """For each roll (monthly expiry E_i at 08:00 UTC) find the ATM strike of the next monthly
    expiry E_{i+1} and read its market price from the first trades after 08:00."""
    px = delivery.set_index("date")["price"]
    exps = monthly_expiries()
    rows = []
    for sell, expiry in zip(exps[:-1], exps[1:]):
        s0 = float(px[pd.Timestamp(sell)])
        t0 = dt.datetime(sell.year, sell.month, sell.day, 8, tzinfo=dt.timezone.utc)
        step = 50 if s0 < 2000 else 100
        base = round(s0 / step) * step
        cands = sorted({base, base - step, base + step, round(s0 / 50) * 50}, key=lambda k: abs(k - s0))
        found = None
        for k in cands:
            trades = []
            for kind in ("P", "C"):
                res = get(HIST, "get_last_trades_by_instrument_and_time",
                          instrument_name=instrument(expiry, k, kind), start_timestamp=ms(t0),
                          end_timestamp=ms(t0 + dt.timedelta(hours=24)), count=50, sorting="asc")
                if res:
                    trades += [dict(tr, kind=kind) for tr in res["trades"]]
            if trades:
                found = (k, trades)
                break
        if not found:
            print("no trades", sell, expiry)
            rows.append(dict(sell_date=sell, expiry=expiry, spot=s0))
            continue
        k, trades = found
        tr = pd.DataFrame(trades).sort_values("timestamp")
        first = tr.head(10)  # trades closest to 08:00 (both put & call of that strike)
        rows.append(dict(
            sell_date=sell, expiry=expiry, spot=s0, strike=k, n_trades=len(tr),
            first_trade_min=(first.timestamp.iloc[0] - ms(t0)) / 60000,
            iv_median=first.iv.median(),
            put_mark_eth=first[first.kind == "P"].mark_price.median(),
            call_mark_eth=first[first.kind == "C"].mark_price.median(),
            index_at_trades=first.index_price.median(),
        ))
        print(sell, expiry, s0, k, len(tr), round(first.iv.median(), 1))
    pd.DataFrame(rows).to_csv(DATA / "atm_quotes.csv", index=False)


if __name__ == "__main__":
    DATA.mkdir(exist_ok=True)
    d = fetch_delivery_prices()
    if not (DATA / "dvol_hourly.csv").exists():
        fetch_hourly()
    fetch_atm_quotes(d)
