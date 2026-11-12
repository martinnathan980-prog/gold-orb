"""PART 1 of the clock lens (description, written after declared.json): per sleeve, mean R of the reference chain
(FP costs, stake 1) by hour band and by weekday, by year, and walk-forward (each fold's training table, its worst and
best cell, and what that cell did the next year). Also the family-pooled weekdays and two portfolio-level cuts quoted
by the autopsy (Friday; fills after 12:00 New York). IN SAMPLE ONLY; nothing is simulated here.

    NUMBA_CACHE_DIR=/tmp/numba_clock PYTHONDONTWRITEBYTECODE=1 python3 s2_describe.py
"""
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from scipy.stats import spearmanr  # noqa: E402

import common as C  # noqa: E402
import fits as F  # noqa: E402

WD = {0: "Mon", 1: "Tue", 2: "Wed", 3: "Thu", 4: "Fri"}
FOLDS = (2018, 2019, 2020, 2021)


def chain(k, mode="fp"):
    ch = pd.read_parquet(os.path.join(C.BASE, f"{k}__{mode}__chain.parquet"))
    assert (ch.entry_time < C.IS_END).all() and (ch.exit_time < C.IS_END).all()
    return ch


def label(k, dim, c):
    if dim == "D":
        return WD[int(c)]
    clock, bands = C.BANDS[k]
    a, b = bands[int(c)]
    f = lambda h: f"{int(h):02d}:{int(round((h - int(h)) * 60)) % 60:02d}"
    return f"{f(a)}-{f(min(b, 24.0) if b < 24 else 24.0)} {clock}"


def cell_stats(R, cc):
    out = {}
    for v in np.unique(cc):
        if v < 0:
            continue
        m = cc == v
        out[int(v)] = {"n": int(m.sum()), "mean": round(float(R[m].mean()), 4), "total": round(float(R[m].sum()), 2)}
    return out


def by_year(ch, k, dim):
    cc = F.cells(k, ch.entry_time, dim)
    if cc is None:
        return None
    y = ch.entry_time.dt.year.to_numpy()
    R = ch.R.to_numpy(float)
    return {int(yy): cell_stats(R[y == yy], cc[y == yy]) for yy in np.unique(y)}


def walk_forward(ch, k, dim, family_chains=None, fam_keys=None):
    out = {}
    for Y in FOLDS:
        fit = F.fit_fold(ch, k, dim, Y, family_chains)
        if fit is None:
            return None
        row = {"n_train": fit["n_train"], "mean_train": round(fit["mean_train"], 4) if fit["n_train"] else None,
               "acts": fit["acts"],
               "train_table": {str(c): {"n": v[0], "mean": round(v[1], 4)} for c, v in fit["table"].items()}}
        # what the year did
        if family_chains is None:
            ty = ch[ch.entry_time.dt.year == Y]
            Ry = ty.R.to_numpy(float)
            cy = F.cells(k, ty.entry_time, dim)
        else:
            Rs, cs = [], []
            for kk, chh in family_chains:
                tt = chh[chh.entry_time.dt.year == Y]
                cc_ = F.cells(kk, tt.entry_time, dim)
                if cc_ is None:
                    continue
                Rs.append(tt.R.to_numpy(float))
                cs.append(cc_)
            Ry = np.concatenate(Rs)
            cy = np.concatenate(cs)
        row["year_table"] = {str(c): v for c, v in cell_stats(Ry, cy).items()}
        row["year_n"] = int(len(Ry))
        row["year_mean"] = round(float(Ry.mean()), 4) if len(Ry) else None
        if fit["acts"]:
            for nm in ("worst", "best"):
                c = fit[nm]
                m = cy == c
                row[nm] = {"cell": int(c), "label": label(k, dim, c) if family_chains is None else WD[int(c)],
                           "train_mean": round(fit[nm + "_mean"], 4), "train_n": fit["table"][c][0],
                           "year_n": int(m.sum()), "year_mean": round(float(Ry[m].mean()), 4) if m.any() else None,
                           "rest_year_n": int((~m).sum()),
                           "rest_year_mean": round(float(Ry[~m].mean()), 4) if (~m).any() else None}
            # rank agreement between training means and the year's means over eligible cells with >= 5 trades
            xs, ys = [], []
            for c in fit["eligible"]:
                m = cy == c
                if m.sum() >= 5:
                    xs.append(fit["table"][c][1])
                    ys.append(float(Ry[m].mean()))
            row["spearman_train_vs_year"] = round(float(spearmanr(xs, ys)[0]), 3) if len(xs) >= 3 else None
            row["cells_in_rank"] = len(xs)
        out[Y] = row
    return out


def persistence(wf_all):
    """over sleeves x folds 2019-2021: did the training-worst cell do worse than the rest the next year, and the best
    better? (cells with at least 5 trades in the year)"""
    res = {}
    for dim in ("H", "D", "FD"):
        rows = []
        seen = set()
        for k, d in wf_all.items():
            w = d.get(dim)
            if not w:
                continue
            unit = C.FAMILY[k] if dim == "FD" else k          # a family fold is counted once, not once per member
            if unit in seen:
                continue
            seen.add(unit)
            for Y in C.OOF:
                r = w[Y]
                if not r["acts"]:
                    continue
                rows.append((unit, Y, r))
        def agg(nm, sign):
            diffs, hits, ws, n_used = [], 0, [], 0
            for k, Y, r in rows:
                x = r[nm]
                if x["year_n"] < 5 or x["rest_year_mean"] is None or x["year_mean"] is None:
                    continue
                dlt = x["year_mean"] - x["rest_year_mean"]
                diffs.append(dlt)
                n_used += 1
                hits += int(sign * dlt > 0)
                ws.append(x["year_n"])
            return {"folds": n_used, "folds_in_expected_direction": hits,
                    "mean_diff_year_cell_minus_rest_R": round(float(np.mean(diffs)), 4) if diffs else None,
                    "median_diff": round(float(np.median(diffs)), 4) if diffs else None,
                    "trade_weighted_diff": round(float(np.average(diffs, weights=ws)), 4) if diffs else None}
        sp = [r["spearman_train_vs_year"] for k, Y, r in rows if r.get("spearman_train_vs_year") is not None]
        res[dim] = {"sleeve_folds": len(rows), "worst_cell": agg("worst", -1), "best_cell": agg("best", +1),
                    "mean_spearman_train_vs_next_year": round(float(np.mean(sp)), 3) if sp else None,
                    "n_spearman": len(sp)}
    return res


def portfolio_cuts(chains):
    """the autopsy's two portfolio-level cuts, by year (description)"""
    d = pd.concat([ch.assign(sleeve=k) for k, ch in chains.items()], ignore_index=True)
    d["year"] = d.entry_time.dt.year
    d["wd"] = C.server_weekday(d.entry_time)
    d["ny_h"] = C.local_hours(d.entry_time, C.NY)
    out = {"friday_vs_mon_thu": {}, "after_12_ny_vs_before": {}}
    for y, g in d[d.year >= 2014].groupby("year"):
        f = g.wd == 4
        a = g.ny_h >= 12
        out["friday_vs_mon_thu"][int(y)] = {"fri": C.sstats(g.R[f]), "mon_thu": C.sstats(g.R[~f])}
        out["after_12_ny_vs_before"][int(y)] = {"after_12": C.sstats(g.R[a]), "before_12": C.sstats(g.R[~a])}
    return out


def main():
    chains = {k: chain(k) for k in C.KEYS}
    res = {"what": "PART 1, description: reference chains (FP, stake 1) by hour band / weekday, by year and walk-forward",
           "cells": {}, "walk_forward": {}}
    flat = []
    for k in C.KEYS:
        ch = chains[k]
        res["cells"][k] = {}
        res["walk_forward"][k] = {}
        for dim in ("H", "D"):
            by = by_year(ch, k, dim)
            if by is None:
                continue
            res["cells"][k][dim] = {"labels": {str(c): label(k, dim, c) for c in sorted({c for y in by.values() for c in y})},
                                   "by_year": by}
            res["walk_forward"][k][dim] = walk_forward(ch, k, dim)
            for y, cs in by.items():
                for c, v in cs.items():
                    flat.append({"sleeve": k, "dim": dim, "cell": c, "label": label(k, dim, c), "year": y, **v})
    # family-pooled weekdays
    fams = {}
    for k in C.KEYS:
        if k in C.NO_WEEKDAY:
            continue
        fams.setdefault(C.FAMILY[k], []).append(k)
    res["family_weekday"] = {}
    for fam, ks in fams.items():
        fc = [(kk, chains[kk]) for kk in ks]
        res["family_weekday"][fam] = {"sleeves": ks, "walk_forward": walk_forward(None, ks[0], "D", fc)}
        allc = pd.concat([chains[kk] for kk in ks], ignore_index=True)
        res["family_weekday"][fam]["by_year"] = by_year(allc, ks[0], "D")
        for kk in ks:
            res["walk_forward"].setdefault(kk, {})["FD"] = res["family_weekday"][fam]["walk_forward"]
    res["persistence_2019_2021"] = persistence({k: v for k, v in res["walk_forward"].items()})
    res["portfolio_cuts"] = portfolio_cuts(chains)
    pd.DataFrame(flat).to_csv(os.path.join(C.OUT, "part1_cells_by_year.csv"), index=False)
    C.jdump(res, os.path.join(C.OUT, "part1.json"))
    # console digest
    for k in C.KEYS:
        for dim in ("H", "D"):
            w = res["walk_forward"][k].get(dim)
            if not w:
                continue
            s = []
            for Y in FOLDS:
                r = w[Y]
                if r["acts"]:
                    s.append(f"{Y}: worst {r['worst']['label']} tr {r['worst']['train_mean']:+.3f} -> yr {r['worst']['year_mean'] if r['worst']['year_mean'] is None else round(r['worst']['year_mean'],3)} (n {r['worst']['year_n']}) vs rest {r['worst']['rest_year_mean']}; "
                             f"best {r['best']['label']} tr {r['best']['train_mean']:+.3f} -> {r['best']['year_mean']} | sleeve tr {r['mean_train']:+.3f}")
                else:
                    s.append(f"{Y}: no action (n_train {r['n_train']})")
            print(f"--- {k} {dim}")
            print("\n".join("   " + x for x in s))
    print(res["persistence_2019_2021"])


if __name__ == "__main__":
    main()
