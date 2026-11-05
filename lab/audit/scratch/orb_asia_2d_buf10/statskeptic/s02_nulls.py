"""Empirical nulls with the candidate's exact trade structure: same engine and frozen costs, same
risk (stop distance = 1.2 x Asian-range width = distance to the opposite OCO level), same time
exit (16:00 NY, 2 business days after the entry day), one position at a time (no_overlap=True).

Signal-time families (the candidate's own 2621 OCO first-touch events, IS+VAL):
  C1   true side, market entry at the open of the bar after the touch  (mechanism control)
  F1   opposite side (fade), same mechanism          L1 / S1  always long / always short
  N1   coin-flip side                                N1y  true sides permuted within calendar year
Random-time families (random entry times with the candidate's time-of-day profile):
  N2   each weekday session drawn with prob p_day (calibrated on IS so n ~ candidate's 1037);
       entry minute = 07:00 London + offset drawn from the candidate's empirical touch offsets;
       market entry, coin-flip side, stop_dist = 1.2 x that day's Asian range width, same exit.
  N2L / N2S  same, always long / always short.
Per seed: IS report (+ stress x1.5 run when IS PF >= 1.15, otherwise pass is already False)
-> is_criteria; VAL trades of ALL seeds of a family -> ONE logged gl.cut -> val_criteria per seed.
Monthly (entry-month) aggregates per seed are saved for the holdout model.
"""
import json
import time

from common import *  # noqa

NS = int(os.environ.get("NS", 2000))
ONLY = os.environ.get("ONLY")
m1 = gl.load_m1("xauusd")
N = len(m1)
cand = pd.read_parquet(os.path.join(HERE, "cand_orders.parquet"))
p = dict(S.DEFAULTS)
p.update(PARAMS)
sess = S.sessions(m1, p)
sess = sess[(sess.width > 0)].reset_index(drop=True)
idx_ns = m1.index.values
IDX_I64 = pd.DatetimeIndex(m1.index).as_unit("ns").asi8
DRYVAL = os.environ.get("DRYVAL") == "1"
# empirical touch offsets (minutes after the range end) of the candidate's signals
t_touch = m1.index[cand.entry_i.to_numpy()]
t_re_c = pd.merge_asof(pd.DataFrame({"t": t_touch.as_unit("ns")}),
                       sess[["t_re"]].assign(t=sess.t_re).sort_values("t"), on="t", direction="backward").t_re
OFFS = ((t_touch - pd.DatetimeIndex(t_re_c)).total_seconds() / 60).to_numpy()
OFFS = OFFS[np.isfinite(OFFS) & (OFFS >= 0) & (OFFS < 300)]
print("touch offsets (min) pct 10/50/90:", np.percentile(OFFS, [10, 50, 90]), flush=True)

# --- signal-time base (market at the bar after the touch, risk 1.2W, same exit)
sig = cand.copy()
sig["ent"] = sig.entry_i + 1
sig["risk"] = (sig.level - sig.stop).abs()
sig = sig[(sig.ent < sig.exit_i) & (sig.ent < N)].reset_index(drop=True)
sig_year = pd.DatetimeIndex(m1.index[sig.ent.to_numpy()]).year.to_numpy()
_sig_t = pd.DatetimeIndex(m1.index[sig.ent.to_numpy()]).tz_convert(None)
sig_q = (_sig_t.year * 10 + _sig_t.quarter).to_numpy()
sig_m = (_sig_t.year * 100 + _sig_t.month).to_numpy()


def sig_orders(side):
    return pd.DataFrame({"entry_i": sig.ent.to_numpy(), "side": side.astype(np.int64), "etype": 0,
                         "stop_dist": sig.risk.to_numpy(), "exit_i": sig.exit_i.to_numpy()})


def fam_sig(mode):
    true = sig.side.to_numpy()

    def f(rng):
        if mode == "true":
            s = true
        elif mode == "fade":
            s = -true
        elif mode == "long":
            s = np.ones(len(true), np.int64)
        elif mode == "short":
            s = -np.ones(len(true), np.int64)
        elif mode == "coin":
            s = np.where(rng.random(len(true)) < 0.5, 1, -1)
        elif mode in ("perm_year", "perm_q", "perm_m"):
            key = {"perm_year": sig_year, "perm_q": sig_q, "perm_m": sig_m}[mode]
            s = true.copy()
            for y in np.unique(key):
                k = np.flatnonzero(key == y)
                s[k] = rng.permutation(true[k])
        return sig_orders(s)
    return f


# --- random-time base
S_RE = pd.DatetimeIndex(sess.t_re).as_unit("ns").asi8
S_IE = sess.ie.to_numpy()
S_IX = sess.ix.to_numpy()
S_W = sess.width.to_numpy()


def rand_orders(rng, p_day, side_mode):
    pick = np.flatnonzero(rng.random(len(sess)) < p_day)
    off = OFFS[rng.integers(0, len(OFFS), len(pick))]
    tt = S_RE[pick] + (off * 60e9).astype(np.int64)
    ent = np.searchsorted(IDX_I64, tt, side="left")
    ok = (ent < S_IE[pick]) & (ent < S_IX[pick]) & (ent < N)
    pick, ent = pick[ok], ent[ok]
    if side_mode == "coin":
        s = np.where(rng.random(len(pick)) < 0.5, 1, -1)
    elif side_mode == "long":
        s = np.ones(len(pick), np.int64)
    else:
        s = -np.ones(len(pick), np.int64)
    return pd.DataFrame({"entry_i": ent, "side": s.astype(np.int64), "etype": 0,
                         "stop_dist": 1.2 * S_W[pick], "exit_i": S_IX[pick]})


def calibrate():
    res = {}
    for pd_ in (0.55, 0.65, 0.75, 0.85, 1.0):
        ns = []
        for s in range(6):
            o = rand_orders(np.random.default_rng(777 + s), pd_, "coin")
            t = gl.simulate(m1, o, no_overlap=True)
            ns.append(len(gl.cut(t, "is")))
        res[pd_] = float(np.median(ns))
        print("calib p_day", pd_, "IS n median", res[pd_], flush=True)
    return res


cal = calibrate()
PDAY = min(cal, key=lambda k: abs(cal[k] - 1037))
print("chosen p_day", PDAY, flush=True)

FAMS = {
    "C1": (fam_sig("true"), 1), "F1": (fam_sig("fade"), 1), "L1": (fam_sig("long"), 1), "S1": (fam_sig("short"), 1),
    "N1": (fam_sig("coin"), NS), "N1y": (fam_sig("perm_year"), max(NS // 4, 1)),
    "N1q": (fam_sig("perm_q"), max(NS // 4, 1)), "N1m": (fam_sig("perm_m"), max(NS // 4, 1)),
    "N2": (lambda rng: rand_orders(rng, PDAY, "coin"), NS),
    "N2L": (lambda rng: rand_orders(rng, PDAY, "long"), max(NS // 6, 1)),
    "N2S": (lambda rng: rand_orders(rng, PDAY, "short"), max(NS // 6, 1)),
}
FAM_ORDER = ["C1", "F1", "L1", "S1", "N1", "N1y", "N2", "N2L", "N2S", "N1q", "N1m"]  # stable RNG streams
if ONLY:
    FAMS = {k: v for k, v in FAMS.items() if k in ONLY.split(",")}

CAND_IS = (1.1773, 1.8297)      # patched-data candidate IS PF, t
CAND_IS_UNP = (1.196, 1.99)     # unpatched (track report) IS PF, t
MONTHS = pd.period_range("2013-01", "2025-12", freq="M")
KEEP = ["side", "entry_time", "exit_time", "R", "ret", "hold_min", "reason"]

outp = os.path.join(HERE, "s02_nulls.json")
out = json.load(open(outp)) if os.path.exists(outp) else {"families": {}}
out["p_day"] = PDAY
out["calibration"] = cal
for name, (fn, ns) in FAMS.items():
    t0 = time.time()
    rows, val_parts = [], []
    mon = np.zeros((ns, len(MONTHS), 3))  # sum_pos, sum_neg(abs), n  by entry month
    for s in range(ns):
        rng = np.random.default_rng(1_000_003 * (1 + FAM_ORDER.index(name)) + s)
        o = fn(rng)
        t = gl.simulate(m1, o, no_overlap=True)
        ti = gl.cut(t, "is")
        ri = gl.report(ti)
        if ri.get("pf", 0) >= 1.15:
            ts = gl.simulate(m1, o, costs=STRESS, no_overlap=True)
            rsi = gl.report(gl.cut(ts, "is"))
            crit = is_criteria(ri, rsi)
            spf = rsi.get("pf")
        else:
            crit = is_criteria(ri)
            crit["pass"] = False
            spf = np.nan
        R = ti.R.to_numpy()
        rows.append({"seed": s, "is_n": ri["n"], "is_pf": pf(R), "is_t": tstat(R), "is_exp": float(np.nanmean(R)),
                     "is_years": ri["years_pos"], "is_tpy": ri["trades_per_year"], "is_maxhold": ri["max_hold_h"],
                     "is_stress_pf": spf, "is_pass": bool(crit["pass"]),
                     "is_core": bool(pf(R) >= 1.20 and tstat(R) >= 2.0),
                     "is_near": bool(pf(R) >= CAND_IS[0] and tstat(R) >= CAND_IS[1]),
                     "is_near_unp": bool(pf(R) >= CAND_IS_UNP[0] and tstat(R) >= CAND_IS_UNP[1]),
                     "is_long_pf": pf(R[ti.side.to_numpy() > 0]), "is_short_pf": pf(R[ti.side.to_numpy() < 0]),
                     "is_long_share": float((ti.side > 0).mean())})
        mi = ti.entry_time.dt.tz_convert(None).dt.to_period("M")
        g = pd.DataFrame({"m": mi, "pos": np.where(R > 0, R, 0), "neg": np.where(R < 0, -R, 0), "n": 1}).groupby("m").sum()
        k = MONTHS.get_indexer(g.index)
        mon[s, k[k >= 0]] = g.to_numpy()[k >= 0]
        tt = t[t.entry_time >= VA_A - pd.Timedelta(days=15)][KEEP].copy()
        tt["seed"] = s
        val_parts.append(tt)
    allv = pd.concat(val_parts, ignore_index=True)
    if DRYVAL:
        print(name, "DRY: IS only", round(time.time() - t0, 1), "s", pd.DataFrame(rows)[["is_n", "is_pf", "is_t"]].describe().round(3).to_dict(), flush=True)
        continue
    tv = gl.cut(allv, "val", track="review", label=label(f"null-{name}({ns} seeds, VAL reports + monthly aggregates)"))
    df = pd.DataFrame(rows).set_index("seed")
    for c in ("val_n", "val_pf", "val_t", "val_exp", "val_pass", "val_long_pf", "val_short_pf"):
        df[c] = np.nan
    for s, grp in tv.groupby("seed"):
        rv = gl.report(grp)
        vc = val_criteria(rv)
        R = grp.R.to_numpy()
        df.loc[s, ["val_n", "val_pf", "val_t", "val_exp", "val_pass", "val_long_pf", "val_short_pf"]] = [
            rv["n"], pf(R), tstat(R), float(np.nanmean(R)), float(bool(vc["pass"])),
            pf(R[grp.side.to_numpy() > 0]), pf(R[grp.side.to_numpy() < 0])]
        mi = grp.entry_time.dt.tz_convert(None).dt.to_period("M")
        g = pd.DataFrame({"m": mi, "pos": np.where(R > 0, R, 0), "neg": np.where(R < 0, -R, 0), "n": 1}).groupby("m").sum()
        k = MONTHS.get_indexer(g.index)
        mon[s, k[k >= 0]] = g.to_numpy()[k >= 0]
    df["val_pass"] = df["val_pass"].astype(bool)
    df.to_csv(os.path.join(HERE, f"s02_{name}.csv"))
    np.save(os.path.join(HERE, f"s02_{name}_monthly.npy"), mon)
    q = lambda c, pp: round(float(np.nanpercentile(df[c].astype(float), pp)), 3)
    summ = {"seeds": ns, "secs": round(time.time() - t0, 1),
            "is_n_med": float(df.is_n.median()), "val_n_med": float(df.val_n.median()),
            "is_pf_p1_5_50_95_99_max": [q("is_pf", 1), q("is_pf", 5), q("is_pf", 50), q("is_pf", 95), q("is_pf", 99), round(float(df.is_pf.max()), 3)],
            "is_t_mean_sd_max": [round(float(df.is_t.mean()), 3), round(float(df.is_t.std()), 3), round(float(df.is_t.max()), 2)],
            "is_exp_mean": round(float(df.is_exp.mean()), 4),
            "val_pf_p1_5_50_95_99_max": [q("val_pf", 1), q("val_pf", 5), q("val_pf", 50), q("val_pf", 95), q("val_pf", 99), round(float(df.val_pf.max()), 3)],
            "val_t_mean_sd": [round(float(df.val_t.mean()), 3), round(float(df.val_t.std()), 3)],
            "val_exp_mean": round(float(df.val_exp.mean()), 4),
            "frac_is_pass": round(float(df.is_pass.mean()), 5), "frac_is_core": round(float(df.is_core.mean()), 5),
            "frac_is_near": round(float(df.is_near.mean()), 5), "frac_is_near_unp": round(float(df.is_near_unp.mean()), 5),
            "frac_val_pass": round(float(df.val_pass.mean()), 4),
            "frac_is_pass_and_val": round(float((df.is_pass & df.val_pass).mean()), 5),
            "frac_is_near_and_val": round(float((df.is_near & df.val_pass).mean()), 5),
            "is_long_pf_med": q("is_long_pf", 50), "is_short_pf_med": q("is_short_pf", 50),
            "val_long_pf_med": q("val_long_pf", 50), "val_short_pf_med": q("val_short_pf", 50)}
    if ns == 1:
        summ["row"] = {k: (v if not isinstance(v, (np.floating, np.integer)) else float(v)) for k, v in df.iloc[0].to_dict().items()}
    out["families"][name] = summ
    print(name, json.dumps(summ, default=str), flush=True)
    json.dump(out, open(outp, "w"), indent=1, default=str)
