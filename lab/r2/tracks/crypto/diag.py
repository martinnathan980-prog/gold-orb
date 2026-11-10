"""Diagnostics on configurations ALREADY logged as trials (no new configuration): IS trades split by year x side,
weekday / weekend, decision hour, compression, first-vs-continuation signal, halves of the IS period."""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from helpers import *  # noqa
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 200)


def agg(t, key, name):
    g = t.groupby(key)["R"].agg(["size", "mean", "sum"]).round(3)
    g["bps"] = (t.assign(b=t.pnl / t.entry * 1e4).groupby(key)["b"].mean()).round(1)
    g["win"] = t.assign(w=t.R > 0).groupby(key)["w"].mean().round(3)
    print(f"-- by {name}"); print(g.to_string())


def diag(sym, params, label):
    t = is_trades(sym, params)
    tg = is_trades(sym, params, mode="gross")
    print(f"\n===== {label} {sym} n={len(t)} meanR={t.R.mean():.4f} | reasons {t.reason.value_counts().to_dict()}")
    t = t.copy()
    t["year"] = t.entry_time.dt.year
    t["sidec"] = np.where(t.side > 0, "long", "short")
    agg(t, ["year", "sidec"], "year x side")
    t["wk"] = np.where(pd.DatetimeIndex(t.dec_time).dayofweek >= 5, "weekend", "weekday")
    agg(t[t.year >= 2019], ["wk"], "weekday/weekend (2019-2021, when weekends exist)")
    agg(t[t.year >= 2019], ["year", "wk"], "year x weekday/weekend")
    hr = pd.DatetimeIndex(t.dec_time).hour
    t["sess"] = np.select([hr < 8, hr < 13, hr < 21], ["00-08 asia", "08-13 eu", "13-21 us"], "21-24 late")
    agg(t, ["sess"], "decision hour block (UTC)")
    if "vc" in t:
        t["vcb"] = pd.cut(t.vc, [0, 0.8, 1.0, 1.25, 99], labels=["<0.8", "0.8-1", "1-1.25", ">1.25"])
        agg(t, ["vcb"], "compression ATR24/ATR240 at decision")
        agg(t, ["prev1"], "previous bar already a same-direction signal")
        t["ovb"] = pd.cut(t.over_atr, [-1, 0.25, 0.75, 1.5, 99], labels=["<0.25", "0.25-0.75", "0.75-1.5", ">1.5"])
        agg(t, ["ovb"], "size of the break beyond the channel (ATR)")
    # halves
    mid = t.entry_time.min() + (pd.Timestamp("2022-01-01", tz="UTC") - t.entry_time.min()) / 2
    for nm, tt in (("net", t), ("gross", tg)):
        a, b = tt[tt.entry_time < mid], tt[tt.entry_time >= mid]
        f = lambda x: f"n={len(x)} R={x.R.mean():+.4f} bps={(x.pnl / x.entry).mean() * 1e4:+.1f}"
        print(f"-- halves ({nm}) split at {mid.date()}: first {f(a)} | second {f(b)} | 2021 only {f(tt[tt.entry_time.dt.year == 2021])}")
    top = t.R.sort_values(ascending=False)
    k = max(1, int(round(0.05 * len(t))))
    print(f"-- top 5% of trades ({k}) = {top.iloc[:k].sum():.1f}R of total {t.R.sum():.1f}R; avg win {t.R[t.R > 0].mean():.2f} avg loss {t.R[t.R < 0].mean():.2f}")
    return t


if __name__ == "__main__":
    cfgs = json.loads(sys.argv[1])
    for sym in ("btcusd", "ethusd"):
        for label, p in cfgs.items():
            diag(sym, p, label)
        r2.free()
