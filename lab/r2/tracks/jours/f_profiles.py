"""Track `jours`: robustness of the two candidate profiles, account realism on 1,000 EUR, and the frontier table.
IN SAMPLE ONLY.

    python3 f_profiles.py   -> results/r2/jours/profiles.json, frontier.csv
"""
import json
import os

import numpy as np
import pandas as pd

import common as C
import d_combo as D
from goldlab import r2
from goldlab.portfolio import Spec, run_account

USD_EUR = 0.89
out = {}
pd.set_option("display.width", 250)
pd.set_option("display.max_rows", 300)

# ---------- 1. reference and profile A (ten rules + s x mom500), three hypotheses on the structure's edge ----------
Pn, dn = D.port_days("net")
Pg, dg = D.port_days("gross")
Xn, Xg = D.struct_days("net"), D.struct_days("gross")
ref = C.stats(Pn)
cost_day = float(Xg.mean() - Xn.mean())
hyp = {"as_measured": Xn, "zero_edge_structure": Xn - Xn.mean(), "structure_loses_its_costs": Xg - Xg.mean() - cost_day}
rows = []
for s in (8, 12, 20):
    for h, x in hyp.items():
        day = D.add(Pn, x, s)
        st = C.stats(day)
        k = ref["worst_week"] / st["worst_week"]
        rows.append(dict(size=s, structure=h, green_days=st["green_days"], green_weeks=st["green_weeks"], green_months=st["green_months"],
                         red_in_greens=st["red_in_greens"], total=st["total"], worst_day=st["worst_day"], worst_week=st["worst_week"],
                         max_dd=st["max_dd"], scale_to_ref_worst_week=round(k, 3), scaled_total=round(st["total"] * k, 1),
                         scaled_per_year=round(st["per_year"] * k, 1), scaled_worst_day=round(st["worst_day"] * k, 2),
                         scaled_max_dd=round(st["max_dd"] * k, 1), scaled_avg_green=round(st["avg_green"] * k, 2),
                         scaled_avg_red=round(st["avg_red"] * k, 2)))
rob = pd.DataFrame(rows)
print("reference (ten rules, net, common):", ref)
print("structure cost per day (R):", round(cost_day, 4), " structure mean net (R/day, common):", round(float(Xn.mean()), 4),
      " t:", round(float(Xn.mean() / Xn.std(ddof=1) * np.sqrt(len(Xn))), 2))
print(rob.to_string())
out["reference_net_common"] = ref
out["reference_gross_common"] = C.stats(Pg)
out["profileA_robustness"] = rows

# per year, profile A (s = 12) net and gross
for kind, P, X in (("net", Pn, Xn), ("gross", Pg, Xg)):
    day = D.add(P, X, 12)
    by = {}
    for y, g in day.groupby(day.index.year):
        w = g.groupby(g.index.to_period("W-SUN")).sum()
        by[int(y)] = {"green_days": round(float((g > 0).mean() * 100), 1), "green_weeks": round(float((w > 0).mean() * 100), 1),
                      "total": round(float(g.sum()), 1), "worst_day": round(float(g.min()), 2), "worst_week": round(float(w.min()), 2)}
    out[f"profileA_s12_by_year_{kind}"] = by
    print("profile A s=12 by year", kind, by)
    byr = {}
    for y, g in P.groupby(P.index.year):
        w = g.groupby(g.index.to_period("W-SUN")).sum()
        byr[int(y)] = {"green_days": round(float((g > 0).mean() * 100), 1), "green_weeks": round(float((w > 0).mean() * 100), 1),
                       "total": round(float(g.sum()), 1)}
    out[f"reference_by_year_{kind}"] = byr
    print("reference by year", kind, byr)

# whole in-sample period 2013-2021 (the ten rules do not all exist before 2018): ten + 12 x mom500
for kind in ("net", "gross"):
    d = C.load_trades(kind)
    P = C.daily(d.t_out, d.R, "2013-01-01", "2022-01-01")
    t = pd.read_parquet(os.path.join(C.OUT, "c_trades", f"{D.STRUCT}__{kind}.parquet"))
    t = t[t.entry_time < C.IS_END]
    X = C.daily(t.exit_time, t.R, "2013-01-01", "2022-01-01")
    out[f"whole_2013_2021_{kind}"] = {"reference": C.stats(P), "ten+12xmom500": C.stats(D.add(P, X, 12)),
                                      "ten+20xmom500": C.stats(D.add(P, X, 20))}
    print("whole 2013-2021", kind, json.dumps(out[f"whole_2013_2021_{kind}"]))

# zero-edge control of profile A at its own stake (base 0.4 %): chance of losing half the account = -125 base units
d = dg
base = (d.R - d.groupby("sleeve").R.transform("mean")).to_numpy()
xb = (Xg - Xg.mean()).to_numpy()
rng = np.random.default_rng(21)
for s, half_units, lab in ((12, 125.0, "A_s12_base0.40pct"), (20, 178.0, "A_s20_base0.28pct"), (0, 50.0, "reference_base1pct")):
    z = []
    for b in range(1000):
        p = C.daily(d.t_out, base * rng.choice(np.array([-1.0, 1.0]), size=len(base)), D.START, D.END)
        day = D.add(p, pd.Series(rng.permutation(xb), index=Xg.index), s)
        wk = day.groupby(day.index.to_period("W-SUN")).sum()
        z.append(((day[day != 0] > 0).mean(), (wk > 0).mean(), wk.min(), day.min(), day.cumsum().min(), day.sum()))
    z = np.array(z)
    k = 50.0 / half_units                                    # base stake in % of the account
    out[f"zero_edge_{lab}"] = {"green_days": round(float(z[:, 0].mean() * 100), 1), "green_weeks": round(float(z[:, 1].mean() * 100), 1),
                               "worst_week_pct_account_median": round(float(np.median(z[:, 2]) * k), 1),
                               "worst_week_pct_account_p5": round(float(np.quantile(z[:, 2], 0.05) * k), 1),
                               "worst_day_pct_account_median": round(float(np.median(z[:, 3]) * k), 1),
                               "p_lose_half_in_3.9y": round(float((z[:, 4] <= -half_units).mean()), 4),
                               "p_lose_quarter_in_3.9y": round(float((z[:, 4] <= -half_units / 2).mean()), 4),
                               "total_pct_account_p5_p95": [round(float(np.quantile(z[:, 5], 0.05) * k), 1), round(float(np.quantile(z[:, 5], 0.95) * k), 1)]}
    print("zero edge", lab, out[f"zero_edge_{lab}"])

# ---------- 2. account realism: 1,000 EUR, minimum lots, 6 positions, 2 per market, stop at -50 % (in sample 2018-02..2021) ----------
def spec(sym):
    s = r2.SPEC[sym]
    return Spec(sym, s["units_per_lot"], s["min_lot"], s["lot_step"], USD_EUR, s["leverage"])


def sleeves_net(with_struct):
    sl = []
    for name, sym in C.SLEEVES:
        t = pd.read_parquet(os.path.join(C.NET_DIR, f"{name}__{sym}.parquet"))
        t = t[(t.entry_time < C.IS_END) & (t.entry_time >= C.COMMON_START)]
        sl.append((f"{name}_{sym}", t, spec(sym)))
    if with_struct:
        t = pd.read_parquet(os.path.join(C.OUT, "c_trades", f"{D.STRUCT}__net.parquet"))
        t = t[(t.entry_time < C.IS_END) & (t.entry_time >= C.COMMON_START)]
        sl.append(("mom500", t, spec("us500")))
    return sl


def account(label, risk, weights, with_struct, start=1000.0):
    log = []
    curve, s = run_account(sleeves_net(with_struct), start, risk, weights=weights, log=log, kill_dd=0.5, max_positions=6, max_per_sym=2)
    L = pd.DataFrame(log)
    L["t_out"] = pd.to_datetime(L.t_out, utc=True)
    eq0 = curve.shift(1).fillna(start)
    day_eq = curve.groupby(C.server_time(curve.index).normalize()).last()
    prev = day_eq.shift(1).fillna(start)
    ret = (day_eq / prev - 1) * 100
    ret = ret[ret != 0]
    wk_eq = day_eq.groupby(day_eq.index.to_period("W-SUN")).last()
    wret = (wk_eq / wk_eq.shift(1).fillna(start) - 1) * 100
    mo_eq = day_eq.groupby(day_eq.index.to_period("M")).last()
    mret = (mo_eq / mo_eq.shift(1).fillna(start) - 1) * 100
    by = L.groupby("sleeve").size().to_dict()
    n_all = {n: len(t) for n, t, _ in sleeves_net(with_struct)}
    s.update(label=label, start=start, risk_pct=risk, green_days=round(float((ret > 0).mean() * 100), 1),
             green_weeks=round(float((wret > 0).mean() * 100), 1), green_months=round(float((mret > 0).mean() * 100), 1),
             avg_green_day_pct=round(float(ret[ret > 0].mean()), 2), avg_red_day_pct=round(float(-ret[ret < 0].mean()), 2),
             worst_day_pct=round(float(ret.min()), 1), worst_week_pct=round(float(wret.min()), 1),
             taken_by_sleeve={k: f"{by.get(k, 0)}/{v}" for k, v in n_all.items()})
    print(label, json.dumps(s))
    return s


acc = []
acc.append(account("reference 1 % stake, 1000 EUR", 1.0, None, False))
acc.append(account("profile A: base 0.40 %, mom500 x12, 1000 EUR", 0.40, {"mom500": 12.0}, True))
acc.append(account("profile A: base 0.40 %, mom500 x12, 3000 EUR", 0.40, {"mom500": 12.0}, True, 3000.0))
acc.append(account("profile A': base 1 %, mom500 x12 (worst week 2.5x), 1000 EUR", 1.0, {"mom500": 12.0}, True))
acc.append(account("reference 0.40 % stake, 1000 EUR", 0.40, None, False))
out["account_1000_eur_in_sample"] = acc

# minimum-lot money at risk per sleeve at the END of the in-sample period (2021) vs the stake
ml = {}
for name, t, sp in sleeves_net(True):
    t = t[t.entry_time >= pd.Timestamp("2021-01-01", tz="UTC")]
    if len(t):
        ml[name] = round(float(t.risk.median() * sp.units_per_lot * sp.min_lot * sp.fx), 2)
out["min_lot_risk_eur_median_2021"] = ml
print("EUR at risk on the minimum lot, median 2021:", ml)

# ---------- 3. the frontier table ----------
fr = []
A = json.load(open(os.path.join(C.OUT, "a_shape.json")))
AC = json.load(open(os.path.join(C.OUT, "a_control.json")))
for v in ("base", "T0.5_S1", "T0.5_S3", "T0.3_S3", "T0.2_S3", "T0.2_S3_eve"):
    for kind in ("gross", "net"):
        s = A[v][f"{kind}_common"]
        fr.append(dict(construction="(a) exit shaping, ten rules", config=v, kind=kind, green_days=s["green_days"], green_weeks=s["green_weeks"],
                       red_in_greens=s["red_in_greens"], total=s["total"], worst_day=s["worst_day"], worst_week=s["worst_week"],
                       zero_edge_green_days=AC[v]["green_days"]))
B = json.load(open(os.path.join(C.OUT, "b_marti.json")))
for v in ("ref", "lock0", "rec5_lock0", "dbl4_lock0", "dbl8_lock0"):
    for kind in ("gross", "net"):
        s = B[v][f"{kind}_common_ten"]
        fr.append(dict(construction="(b) intraday martingale (4 rules), ten rules view", config=v, kind=kind, green_days=s["green_days"],
                       green_weeks=s["green_weeks"], red_in_greens=s["red_in_greens"], total=s["total"], worst_day=s["worst_day"],
                       worst_week=s["worst_week"], zero_edge_green_days=B[v]["zero_edge_common_intraday4"]["green_days"]))
        s = B[v][f"{kind}_common_intraday4"]
        fr.append(dict(construction="(b) intraday martingale, the 4 rules alone", config=v, kind=kind, green_days=s["green_days"],
                       green_weeks=s["green_weeks"], red_in_greens=s["red_in_greens"], total=s["total"], worst_day=s["worst_day"],
                       worst_week=s["worst_week"], zero_edge_green_days=B[v]["zero_edge_common_intraday4"]["green_days"]))
for kind in ("gross", "net"):
    s = D.struct_days(kind)
    st = C.stats(s)
    fr.append(dict(construction="(c) one trade a day alone (mom us500 T0.10 S0.60, size 1)", config=D.STRUCT, kind=kind, green_days=st["green_days"],
                   green_weeks=st["green_weeks"], red_in_greens=st["red_in_greens"], total=st["total"], worst_day=st["worst_day"],
                   worst_week=st["worst_week"], zero_edge_green_days=None))
Dj = json.load(open(os.path.join(C.OUT, "d_combo.json")))
for s_ in (5, 8, 12, 20):
    for kind in ("gross", "net"):
        s = Dj[f"ten+{s_}xmom500"][kind]
        fr.append(dict(construction="(d) ten rules + s x daily structure", config=f"s={s_}", kind=kind, green_days=s["green_days"],
                       green_weeks=s["green_weeks"], red_in_greens=s["red_in_greens"], total=s["total"], worst_day=s["worst_day"],
                       worst_week=s["worst_week"], zero_edge_green_days=Dj[f"ten+{s_}xmom500"]["zero_edge"]["green_days"]))
E = json.load(open(os.path.join(C.OUT, "e_daytarget.json")))
for v in ("none", "g3.0", "g2.0", "g1.5", "g1.0", "g0.5", "g0.25", "g1_L3"):
    for kind in ("gross", "net"):
        s = E[v][kind]
        fr.append(dict(construction="(e) account daily target, ten rules", config=v, kind=kind, green_days=s["green_days"],
                       green_weeks=s["green_weeks"], red_in_greens=s["red_in_greens"], total=s["total"], worst_day=s["worst_day"],
                       worst_week=s["worst_week"], zero_edge_green_days=E[v]["zero_edge"]["green_days"]))
fr = pd.DataFrame(fr)
fr.to_csv(os.path.join(C.OUT, "frontier.csv"), index=False)
print(fr.to_string())
json.dump(out, open(os.path.join(C.OUT, "profiles.json"), "w"), indent=1, default=str)
