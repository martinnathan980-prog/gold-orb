"""PART 1 (description, no selection): per sleeve, cost mode and descriptor, the walk-forward relation.

Terciles (q = 1/3: lo = x <= quantile(1/3), hi = x >= quantile(2/3), mid between) are fitted on the training set of
year Y (baseline chain trades of the sleeve with exit_time <= 1 January Y - 7 days), then year Y's baseline chain
trades (decision in Y) are grouped with those boundaries: n and mean R per tercile, Y = 2019, 2020, 2021 and pooled.
Agreement / neither / disagreement (another sleeve of the same market holds the same / the opposite side at the
decision, from the baseline chains) are grouped the same way (no fit). Earlier out-of-fold years (2016-2018 gold and
us100, 2018 btcusd) are reported apart. Writes part1.json and part1_table.csv."""
import os

import numpy as np
import pandas as pd

import cv_common as V
import cv_engine as E
import cv_stakes as S

DESCS = V.ELIGIBLE + V.PART1_EXTRA
EARLY = {"us100": (2016, 2017, 2018), "xauusd": (2016, 2017, 2018), "btcusd": (2018,), "ethusd": ()}


def welch(a, b):
    if len(a) < 2 or len(b) < 2:
        return None
    se = np.sqrt(a.var(ddof=1) / len(a) + b.var(ddof=1) / len(b))
    return round(float((a.mean() - b.mean()) / se), 3) if se > 0 else None


def mean_or_none(x):
    return round(float(np.mean(x)), 4) if len(x) else None


def main():
    rows, out = [], {}
    for mode in V.MODES:
        T = S.tables(mode)
        tdec = {k: T[k][0].t_dec.to_numpy(np.int64) for k in V.KEYS}
        base = {k: E.baseline(k, mode) for k in V.KEYS}
        status = E.agreement_status(base, mode, tdec=tdec)
        out[mode] = {}
        for k in V.KEYS:
            s, tr = T[k]
            tr = tr.copy()
            st = pd.Series(status[k], index=base[k].oid.to_numpy())
            tr["agree"] = st.reindex(tr.oid.to_numpy()).to_numpy()
            fold = pd.DatetimeIndex(tr.t_dec.to_numpy().astype("datetime64[ns]")).year.to_numpy()
            res_k = {}
            years = list(V.OOF_YEARS) + list(EARLY[V.SYM[k]])
            for d in DESCS + ["agree"]:
                per = {}
                pooled = {"lo": [], "mid": [], "hi": []}
                for y in years:
                    app = tr[fold == y]
                    R = app.R.to_numpy(float)
                    if d == "agree":
                        g = app.agree.to_numpy()
                        groups = {"disagree": R[g == -1], "neither": R[g == 0], "agree": R[g == 1]}
                        per[y] = {nm: {"n": int(len(v)), "mean_R": mean_or_none(v)} for nm, v in groups.items()}
                        rest = R[g != 1]
                        per[y]["agree_minus_rest"] = round(float(groups["agree"].mean() - rest.mean()), 4) \
                            if len(groups["agree"]) and len(rest) else None
                        for nm, v in groups.items():
                            rows.append({"mode": mode, "sleeve": k, "descriptor": d, "year": y, "group": nm,
                                         "n": len(v), "mean_R": mean_or_none(v)})
                        continue
                    t = S.train_rows(tr, y)
                    sep = S.separation(t[d].to_numpy(float), t.R.to_numpy(float), 1 / 3)
                    if sep is None:
                        per[y] = None
                        continue
                    g = S.apply_groups(app[d].to_numpy(float), sep["b_lo"], sep["b_hi"])
                    groups = {"lo": R[g == 0], "mid": R[g == 1], "hi": R[g == 2]}
                    per[y] = {"train": {"n": sep["n"], "b_lo": round(sep["b_lo"], 5), "b_hi": round(sep["b_hi"], 5),
                                        "mean_lo": round(sep["m_lo"], 4), "mean_hi": round(sep["m_hi"], 4),
                                        "t_hi_minus_lo": round(sep["t"], 3)},
                              "applied": {nm: {"n": int(len(v)), "mean_R": mean_or_none(v)} for nm, v in groups.items()},
                              "nan_n": int((g == -1).sum())}
                    for nm, v in groups.items():
                        rows.append({"mode": mode, "sleeve": k, "descriptor": d, "year": y, "group": nm, "n": len(v),
                                     "mean_R": mean_or_none(v), "train_mean": round(sep["m_" + nm], 4) if nm != "mid"
                                     else (round(sep["m_mid"], 4) if sep["m_mid"] is not None else None)})
                    if y in V.OOF_YEARS:
                        for nm in pooled:
                            pooled[nm].append(groups[nm])
                # pooled out-of-fold summary
                if d == "agree":
                    app = tr[np.isin(fold, V.OOF_YEARS)]
                    R = app.R.to_numpy(float)
                    g = app.agree.to_numpy()
                    summ = {nm: {"n": int((g == c).sum()), "mean_R": mean_or_none(R[g == c])}
                            for nm, c in (("disagree", -1), ("neither", 0), ("agree", 1))}
                    summ["welch_t_agree_vs_rest"] = welch(R[g == 1], R[g != 1])
                    summ["years_agree_above_rest"] = int(sum(
                        1 for y in V.OOF_YEARS if (per[y]["agree_minus_rest"] or 0) > 0))
                else:
                    if all(per.get(y) is not None for y in V.OOF_YEARS):
                        P = {nm: np.concatenate(v) if v else np.array([]) for nm, v in pooled.items()}
                        same = 0
                        for y in V.OOF_YEARS:
                            p = per[y]
                            tr_sign = np.sign(p["train"]["mean_hi"] - p["train"]["mean_lo"])
                            a_lo, a_hi = p["applied"]["lo"]["mean_R"], p["applied"]["hi"]["mean_R"]
                            if a_lo is not None and a_hi is not None and np.sign(a_hi - a_lo) == tr_sign:
                                same += 1
                        summ = {nm: {"n": int(len(v)), "mean_R": mean_or_none(v)} for nm, v in P.items()}
                        summ["oof_hi_minus_lo"] = round(float(P["hi"].mean() - P["lo"].mean()), 4) \
                            if len(P["hi"]) and len(P["lo"]) else None
                        summ["welch_t_hi_vs_lo_oof"] = welch(P["hi"], P["lo"])
                        summ["years_oof_sign_as_training"] = same
                    else:
                        summ = None
                res_k[d] = {"pooled_2019_2021": summ, "by_year": per}
            out[mode][k] = res_k
            print(mode, k, "done", flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(V.OUT, "part1_table.csv"), index=False)
    V.dump({"what": "part 1: walk-forward terciles (fit on the years before, minus 7 days) and next year's mean R of the "
                    "baseline chain trades per tercile; agreement groups; in sample only; FP and costs x1.5",
            "descriptors": DESCS + ["agree"], "results": out}, os.path.join(V.OUT, "part1.json"))


if __name__ == "__main__":
    main()
