"""N4 nulls: run the EXACT candidate rule (make_orders + simulate, same costs) on synthetic
gold histories in which the direction of each block's M1 path is randomly mirrored.

  mode=day    each NY-17:00 trading day mirrored with prob 1/2 (kills cross-day persistence
              and the drift; keeps intraday dynamics, volatility clustering, spreads, gaps,
              calendar, number of bars)
  mode=dayd   same, but mirrored around the calendar year's mean drift (keeps the yearly
              trend in expectation: a pure 'gold went up' strategy keeps its profit)
  mode=week   each NY trading week mirrored (keeps intra-week persistence <= 5 days)
  mode=ident  no flips (sanity: must reproduce the candidate exactly)

Spreads are rescaled with the synthetic price level (relative spread preserved); for a
mirrored bar the high/low spreads are swapped with the extremes.  One logged gl.cut for the
VAL rows of each mode.
Usage: python3 s03_synth.py <mode> <n_seeds>
"""
import gc
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa

mode, NSEED = sys.argv[1], int(sys.argv[2])
m1 = gl.load_m1("xauusd")
idx = m1.index
td = gl.trading_day(idx)
if mode == "week":
    key = pd.PeriodIndex(td, freq="W-FRI").asi8          # NY trading week (Sun 17:00 -> Fri 17:00)
else:
    key = td.asi8
blk_codes, blk = np.unique(key, return_inverse=True)
nblk = len(blk_codes)
year = td.year.to_numpy()

bo, bh, bl, bc = (m1[c].to_numpy(np.float64) for c in ("bo", "bh", "bl", "bc"))
ao, ah, al, ac = (m1[c].to_numpy(np.float64) for c in ("ao", "ah", "al", "ac"))
mo, mh, ml, mc = (bo + ao) / 2, (bh + ah) / 2, (bl + al) / 2, (bc + ac) / 2
so, sh, sl, sc = ao - bo, ah - bh, al - bl, ac - bc
del bo, bh, bl, bc, ao, ah, al, ac
lo, lc = np.log(mo), np.log(mc)
up = np.log(mh) - lo
dn = lo - np.log(ml)
cc = lc - lo
gap = np.r_[0.0, lo[1:] - lc[:-1]]
del mh, ml, mc
# drift per bar (for dayd): calendar-year mean of daily log returns spread over the bars of the day
if mode == "dayd":
    r_bar = gap + cc
    day_ret = np.bincount(blk, weights=r_bar, minlength=nblk)
    day_n = np.bincount(blk, minlength=nblk)
    day_year = np.zeros(nblk, int)
    day_year[blk] = year
    mu_day = np.zeros(nblk)
    for y in np.unique(day_year):
        m = day_year == y
        mu_day[m] = day_ret[m].mean()
    mu_bar = (mu_day / np.maximum(day_n, 1))[blk]
    del r_bar
gc.collect()
print("prepared", mode, nblk, "blocks", flush=True)


def synth(f_blk):
    f = f_blk[blk]
    neg = f < 0
    g2 = np.where(neg, -gap, gap)
    c2 = np.where(neg, -cc, cc)
    if mode == "dayd":
        c2 = c2 + np.where(neg, 2.0 * mu_bar, 0.0)
    u2 = np.where(neg, dn, up)
    d2 = np.where(neg, up, dn)
    lc2 = lo[0] + np.cumsum(g2 + c2)
    lo2 = lc2 - c2
    mo2 = np.exp(lo2)
    ratio = mo2 / mo
    mh2, ml2, mc2 = mo2 * np.exp(u2), mo2 * np.exp(-d2), np.exp(lc2)
    sh2 = np.where(neg, sl, sh) * ratio
    sl2 = np.where(neg, sh, sl) * ratio
    so2, sc2 = so * ratio, sc * ratio
    bo_, ao_ = mo2 - so2 / 2, mo2 + so2 / 2
    bc_, ac_ = mc2 - sc2 / 2, mc2 + sc2 / 2
    bh_ = np.maximum.reduce([mh2 - sh2 / 2, bo_, bc_])
    ah_ = np.maximum.reduce([mh2 + sh2 / 2, ao_, ac_])
    bl_ = np.minimum.reduce([ml2 - sl2 / 2, bo_, bc_])
    al_ = np.minimum.reduce([ml2 + sl2 / 2, ao_, ac_])
    return pd.DataFrame({"bo": bo_, "bh": bh_, "bl": bl_, "bc": bc_, "ao": ao_, "ah": ah_, "al": al_, "ac": ac_},
                        index=idx)


stress = stressed_costs("xauusd")
rows, vparts = [], []
t00 = time.time()
for s in range(NSEED):
    rng = np.random.default_rng(777_000 + s + (0 if mode == "day" else 50_000 if mode == "dayd" else 90_000))
    f_blk = np.ones(nblk) if mode == "ident" else np.where(rng.random(nblk) < 0.5, -1.0, 1.0)
    sm = synth(f_blk)
    S._bar_cache.clear()
    o = S.make_orders(sm, **PARAMS)
    t = gl.simulate(sm, o, no_overlap=True)
    ts = gl.simulate(sm, o, costs=stress, no_overlap=True)
    te = gl.simulate(sm, o, no_overlap=False)
    ri, rsi = rep_pair(t, ts)
    crit = is_criteria(ri, rsi)
    ti = gl.cut(t, "is")
    tei = gl.cut(te, "is")
    px_end_is = float(sm["bc"].iloc[np.searchsorted(idx.values, IS_B.to_datetime64()) - 1])
    rows.append({"seed": s, "is_n": ri["n"], "is_pf": ri["pf"], "is_t": ri["t_stat"], "is_exp": ri["expectancy_R"],
                 "is_years": ri["years_pos"], "is_stress_pf": rsi["pf"], "is_pass": bool(crit["pass"]),
                 "is_pass_core": bool(crit["pf>=1.20"] and crit["t>=2"]),
                 "is_long_pf": pf(ti.R[ti.side > 0]), "is_short_pf": pf(ti.R[ti.side < 0]),
                 "is_every_pf": pf(tei.R), "is_every_n": len(tei),
                 "px_2013": float(sm["bc"].iloc[0]), "px_end_is": px_end_is, "px_end": float(sm["bc"].iloc[-1])})
    for v, d in (("normal", t), ("every", te)):
        x = d[d.entry_time >= VA_A - pd.Timedelta(days=10)].copy()
        x["seed"], x["variant"] = s, v
        vparts.append(x)
    del sm, o, t, ts, te
    gc.collect()
    if s % 5 == 0:
        print(s, rows[-1], round(time.time() - t00, 1), flush=True)

allv = pd.concat(vparts, ignore_index=True)
tv = gl.cut(allv, "val", track="review", label=label(f"null-N4-{mode}({NSEED} synthetic histories, VAL reports)"))
df = pd.DataFrame(rows).set_index("seed")
for (s, v), grp in tv.groupby(["seed", "variant"]):
    if v == "normal":
        rv = gl.report(grp)
        vc = val_criteria(rv)
        df.loc[s, ["val_n", "val_pf", "val_t", "val_exp", "val_pass", "val_long_pf", "val_short_pf"]] = [
            rv["n"], rv["pf"], rv["t_stat"], rv["expectancy_R"], bool(vc["pass"]),
            pf(grp.R[grp.side > 0]), pf(grp.R[grp.side < 0])]
    else:
        df.loc[s, ["val_every_pf", "val_every_n"]] = [pf(grp.R), len(grp)]
df["val_pass"] = df["val_pass"].astype(bool)
df.to_csv(os.path.join(HERE, f"s03_N4_{mode}.csv"))
q = lambda c, p: round(float(np.nanpercentile(df[c].astype(float), p)), 3)
summ = {"mode": mode, "seeds": NSEED, "is_n_med": float(df.is_n.median()), "val_n_med": float(df.val_n.median()),
        "is_pf_p5_50_95_max": [q("is_pf", 5), q("is_pf", 50), q("is_pf", 95), round(float(df.is_pf.max()), 3)],
        "is_t_p5_50_95_max": [q("is_t", 5), q("is_t", 50), q("is_t", 95), round(float(df.is_t.max()), 2)],
        "is_t_mean_sd": [round(float(df.is_t.mean()), 3), round(float(df.is_t.std()), 3)],
        "val_pf_p5_50_95_max": [q("val_pf", 5), q("val_pf", 50), q("val_pf", 95), round(float(df.val_pf.max()), 3)],
        "val_t_mean_sd": [round(float(df.val_t.mean()), 3), round(float(df.val_t.std()), 3)],
        "frac_is_pass": round(float(df.is_pass.mean()), 4), "frac_is_core": round(float(df.is_pass_core.mean()), 4),
        "frac_val_pass": round(float(df.val_pass.mean()), 4),
        "frac_both": round(float((df.is_pass & df.val_pass).mean()), 4),
        "frac_is_pf_ge_1.35": round(float((df.is_pf >= 1.35).mean()), 4),
        "frac_val_pf_ge_1.294": round(float((df.val_pf >= 1.294).mean()), 4),
        "is_every_pf_med": q("is_every_pf", 50), "val_every_pf_med": q("val_every_pf", 50),
        "secs": round(time.time() - t00, 1)}
print(json.dumps(summ), flush=True)
json.dump(summ, open(os.path.join(HERE, f"s03_N4_{mode}.json"), "w"), indent=1)
