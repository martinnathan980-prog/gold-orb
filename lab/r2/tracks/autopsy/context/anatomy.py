"""PART 1 (description): where the losses are. Expectancy, win rate, average loss, total R and share of stop exits
by tercile of each descriptor (weekday: by day), by year, with the number of trades; and whether a descriptor
separates winners from losers in every year. Writes anatomy.csv, separation.csv, anatomy_summary.json."""
import math
import os

import numpy as np
import pandas as pd

import common as C
import descr as D

DESC = ["hour", "dow", "vol", "al1", "al5", "al20", "room", "cushion", "trig", "sprR", "rel", "rel2", "prev", "oth24"]


def population(s, pop):
    if pop == "chain":
        d = s[s.in_chain].copy()
        d["R"] = d.chain_R
    else:
        d = s[s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)].copy()
        d["R"] = d.label
    d["fyear"] = D.to_ts(d.fill_ns.to_numpy(np.int64)).year
    d["is_stop"] = d.label_reason.isin(["stop", "trail", "gap"])
    return d


def groups(x, desc):
    x = np.asarray(x, float)
    g = np.full(len(x), -1)
    if desc == "dow":
        ok = np.isfinite(x)
        g[ok] = x[ok].astype(int)
        return g, {}
    ok = np.isfinite(x)
    q1, q2 = np.quantile(x[ok], [1 / 3, 2 / 3])
    g[ok & (x <= q1)] = 1
    g[ok & (x > q1) & (x <= q2)] = 2
    g[ok & (x > q2)] = 3
    return g, {1: (float(np.min(x[ok])), float(q1)), 2: (float(q1), float(q2)), 3: (float(q2), float(np.max(x[ok])))}


def gstats(R, stop):
    R = np.asarray(R, float)
    n = len(R)
    if n == 0:
        return {"n": 0}
    los = R[R < 0]
    return {"n": n, "exp": float(R.mean()), "win": float((R > 0).mean()), "avg_loss": float(los.mean()) if len(los) else 0.0,
            "total": float(R.sum()), "stop_share": float(np.mean(stop)), "loss_sum": float(los.sum())}


def welch(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 3 or len(b) < 3:
        return float("nan")
    se = math.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return float((a.mean() - b.mean()) / se) if se > 0 else float("nan")


def main():
    rows, seps, summ = [], [], {}
    for k in C.KEYS:
        summ[k] = {}
        for mode in ("fp", "stress"):
            s = pd.read_parquet(os.path.join(C.OUT, "signals", f"{k}__{mode}.parquet"))
            for pop in ("chain", "every"):
                d = population(s, pop)
                years = sorted(d.fyear.unique())
                total_loss = float(d.R[d.R < 0].sum())
                for desc in DESC:
                    x = d[desc].to_numpy(float)
                    ok = np.isfinite(x)
                    if ok.sum() == 0 or (desc != "dow" and len(np.unique(x[ok])) < 3):
                        continue
                    g, bounds = groups(x, desc)
                    keys = sorted(set(g[g >= 0]))
                    for gg in keys:
                        m = g == gg
                        for yr in ["all"] + years:
                            mm = m if yr == "all" else m & (d.fyear.to_numpy() == yr)
                            st = gstats(d.R.to_numpy()[mm], d.is_stop.to_numpy()[mm])
                            row = {"sleeve": k, "mode": mode, "population": pop, "descriptor": desc, "group": int(gg),
                                   "lo": bounds.get(gg, (np.nan, np.nan))[0], "hi": bounds.get(gg, (np.nan, np.nan))[1],
                                   "year": yr}
                            row.update(st)
                            rows.append(row)
                    if desc == "dow":
                        continue
                    # separation: E(T3) - E(T1) per year
                    R = d.R.to_numpy()
                    fy = d.fyear.to_numpy()
                    diffs = {}
                    for yr in years:
                        a = R[(g == 3) & (fy == yr)]
                        b = R[(g == 1) & (fy == yr)]
                        if len(a) >= 10 and len(b) >= 10:
                            diffs[int(yr)] = float(a.mean() - b.mean())
                    sg = np.sign(list(diffs.values()))
                    d1821 = {y: v for y, v in diffs.items() if 2018 <= y <= 2021}
                    s1821 = np.sign(list(d1821.values()))
                    a, b = R[g == 3], R[g == 1]
                    sep = {"sleeve": k, "mode": mode, "population": pop, "descriptor": desc,
                           "n_T1": int((g == 1).sum()), "n_T3": int((g == 3).sum()),
                           "E_T1": float(b.mean()), "E_T2": float(R[g == 2].mean()), "E_T3": float(a.mean()),
                           "diff_T3_T1": float(a.mean() - b.mean()), "welch_t": welch(a, b),
                           "loss_share_T1": float(b[b < 0].sum() / total_loss) if total_loss < 0 else np.nan,
                           "loss_share_T3": float(a[a < 0].sum() / total_loss) if total_loss < 0 else np.nan,
                           "years_valid": len(diffs), "years_pos": int((sg > 0).sum()), "years_neg": int((sg < 0).sum()),
                           "every_year_same_sign": bool(len(diffs) >= 3 and (abs(sg.sum()) == len(sg))),
                           "y2018_2021_valid": len(d1821),
                           "y2018_2021_same_sign": bool(len(d1821) >= 3 and abs(s1821.sum()) == len(s1821)),
                           "diffs_by_year": diffs}
                    seps.append(sep)
    an = pd.DataFrame(rows)
    an.to_csv(os.path.join(C.OUT, "anatomy.csv"), index=False, float_format="%.5g")
    sp = pd.DataFrame(seps)
    sp.to_csv(os.path.join(C.OUT, "separation.csv"), index=False, float_format="%.5g")
    # plain summary on the primary view: baseline trades, FP costs
    out = {}
    for k in C.KEYS:
        q = sp[(sp.sleeve == k) & (sp["mode"] == "fp") & (sp.population == "chain")]
        nyr = int(q.years_valid.max())
        out[k] = {
            "years_with_data": nyr,
            "chance_all_years_same_sign_per_descriptor": round(2 * 0.5 ** nyr, 4) if nyr else None,
            "separate_every_year": {r.descriptor: {"direction": "higher is better" if r.diff_T3_T1 > 0 else "lower is better",
                                                   "E_T1": round(r.E_T1, 3), "E_T3": round(r.E_T3, 3),
                                                   "welch_t": round(r.welch_t, 2), "by_year": {y: round(v, 3) for y, v in r.diffs_by_year.items()}}
                                    for r in q.itertuples() if r.every_year_same_sign},
            "separate_2018_2021_only": [r.descriptor for r in q.itertuples() if r.y2018_2021_same_sign and not r.every_year_same_sign],
            "do_not_separate": [r.descriptor for r in q.itertuples() if not r.y2018_2021_same_sign and not r.every_year_same_sign],
            "pooled_abs_t_ge_2": {r.descriptor: round(r.welch_t, 2) for r in q.itertuples() if abs(r.welch_t) >= 2},
        }
    C.dump(out, os.path.join(C.OUT, "anatomy_summary.json"))
    for k, v in out.items():
        print(k, "| every year:", list(v["separate_every_year"]), "| 2018-21 only:", v["separate_2018_2021_only"],
              "| |t|>=2:", v["pooled_abs_t_ge_2"])


if __name__ == "__main__":
    main()
