"""Idea 043: Upbit KRW-BTC daily candles (scout/sources.md 16), in sample only, cached in ~/explore_data/idea_043/upbit.
The request bound is to=2021-12-31T00:00:00Z: the last candle asked is the one of 2021-12-30 (00:00 UTC to 2021-12-31
00:00 UTC); the candle of 2021-12-31 closes at 2022-01-01 00:00 UTC and is never requested. Polite: 1 s between
requests, generic User-Agent, stop after two refusals."""
import json, os, time, urllib.request
import pandas as pd

OUT = os.path.expanduser("~/explore_data/idea_043/upbit/krw_btc_daily.csv")
UA = {"User-Agent": "python-urllib/3"}


def main():
    if os.path.exists(OUT):
        print("cached", OUT)
        return
    to, out, refused = pd.Timestamp("2021-12-31T00:00:00Z"), [], 0
    while True:
        url = f"https://api.upbit.com/v1/candles/days?market=KRW-BTC&to={to:%Y-%m-%dT%H:%M:%SZ}&count=200"
        try:
            j = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60).read())
        except Exception as e:  # noqa: BLE001
            refused += 1
            print("error", e)
            if refused >= 2:
                raise
            time.sleep(10)
            continue
        if not j:
            break
        out += j
        to = pd.Timestamp(j[-1]["candle_date_time_utc"] + "Z")
        time.sleep(1.0)
    d = pd.DataFrame(out).drop_duplicates("candle_date_time_utc").sort_values("candle_date_time_utc")
    d = d[pd.to_datetime(d.candle_date_time_utc) < pd.Timestamp("2021-12-31")]
    d[["candle_date_time_utc", "opening_price", "high_price", "low_price", "trade_price", "timestamp",
       "candle_acc_trade_volume"]].to_csv(OUT, index=False)
    print(len(d), d.candle_date_time_utc.iloc[0], d.candle_date_time_utc.iloc[-1])


if __name__ == "__main__":
    main()
