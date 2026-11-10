import sys, os
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/leadlag")
import numpy as np, pandas as pd
import desc
def tgrid(start, end="2022-01-01"):
    t0 = int(pd.Timestamp(start, tz="UTC").value // 60_000_000_000); t1 = int(pd.Timestamp(end, tz="UTC").value // 60_000_000_000)
    n = t1 - t0
    ts = pd.DatetimeIndex((np.arange(n) + t0).astype("int64") * 60_000_000_000, tz="UTC")
    ny = ts.tz_convert("America/New_York"); be = ts.tz_convert("Europe/Berlin")
    return t0, t1, (ny.hour*60+ny.minute).to_numpy(), (be.hour*60+be.minute).to_numpy(), ny.dayofweek.to_numpy(), ts.year.to_numpy()
# 1) us100 z quantiles in US cash hours; btc sigma
t0, t1, nym, bem, wd, yr = tgrid("2017-06-01")
cL, oL, spL, hasL = desc.grid("us100", t0, t1)
cF, oF, spF, hasF = desc.grid("btcusd", t0, t1)
us = desc.S_USCASH(nym, bem, wd)
for k in (1, 5, 15):
    x = np.where(hasL, desc.lret(cL, k) * 1e4, np.nan)
    sg = desc.trailing_sigma(x)
    z = np.abs(x / sg)
    m = us & np.isfinite(z)
    qs = np.quantile(z[m], [0.9, 0.95, 0.975, 0.99, 0.995, 0.999])
    print(f"us100 k={k}: trailing sigma median {np.nanmedian(sg[m]):.2f} bp | |z| quantiles in US cash 90/95/97.5/99/99.5/99.9: {np.round(qs,2)} | share of cash minutes with |z|>=3: {np.mean(z[m]>=3):.4f}, >=4: {np.mean(z[m]>=4):.4f}, >=5: {np.mean(z[m]>=5):.4f}, >=6: {np.mean(z[m]>=6):.4f}")
x1 = desc.lret(cF, 1) * 1e4
sgF = desc.trailing_sigma(np.where(hasF, x1, np.nan))
print("btc 1-min trailing sigma (bp) by year (median in US cash):", pd.Series(sgF[us]).groupby(yr[us]).median().round(2).to_dict())
x1 = desc.lret(cL, 1) * 1e4
sgL = desc.trailing_sigma(np.where(hasL, x1, np.nan))
print("us100 1-min trailing sigma (bp) by year (median in US cash):", pd.Series(sgL[us]).groupby(yr[us]).median().round(2).to_dict())
# 2) DAX residual z quantiles
t0, t1, nym, bem, wd, yr = tgrid("2014-01-01")
cL, oL, spL, hasL = desc.grid("us500", t0, t1)
cF, oF, spF, hasF = desc.grid("ger40", t0, t1)
rl5 = desc.lret(cL, 5); rf5 = desc.lret(cF, 5)
sl = slice(4, None, 5)
beta = np.full(len(cL), np.nan); beta[sl] = desc.trailing_beta(rl5[sl], rf5[sl]); beta = pd.Series(beta).ffill(limit=5).to_numpy()
print("beta ger40 on us500: quantiles", np.round(np.nanquantile(beta, [0.01, 0.1, 0.5, 0.9, 0.99]), 2), "by year median", pd.Series(beta).groupby(yr).median().round(2).to_dict())
for k in (1, 5, 15):
    u = np.where(hasL, beta * desc.lret(cL, k) * 1e4 - desc.lret(cF, k) * 1e4, np.nan)
    sg = desc.trailing_sigma(u)
    z = np.abs(u / sg)
    for nm, fn in (("eu_am", desc.S_EUAM), ("eurex_pm", desc.S_EUREX_PM), ("xetra", desc.S_XETRA)):
        m = fn(nym, bem, wd) & np.isfinite(z)
        qs = np.quantile(z[m], [0.9, 0.95, 0.975, 0.99, 0.995, 0.999])
        print(f"ger40 residual k={k} {nm}: sigma median {np.nanmedian(sg[m]):.2f} bp | |z| q90/95/97.5/99/99.5/99.9: {np.round(qs,2)} | share |z|>=2: {np.mean(z[m]>=2):.4f} >=3: {np.mean(z[m]>=3):.4f} >=4: {np.mean(z[m]>=4):.4f}")
x1 = desc.lret(cF, 1) * 1e4
sgF = desc.trailing_sigma(np.where(hasF, x1, np.nan))
for nm, fn in (("eu_am", desc.S_EUAM), ("eurex_pm", desc.S_EUREX_PM), ("xetra", desc.S_XETRA)):
    m = fn(nym, bem, wd)
    print(f"ger40 1-min: trailing sigma median in {nm}: {np.nanmedian(sgF[m]):.2f} bp ; realised RMS in session {np.sqrt(np.nanmean(x1[m]**2)):.2f} bp")
