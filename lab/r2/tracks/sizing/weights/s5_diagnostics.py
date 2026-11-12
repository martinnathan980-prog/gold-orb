"""Lens `weights`: diagnostics of the 15 evaluated variants (description only: no new stake rule is evaluated).
IN SAMPLE ONLY.

  (1) MV: the raw ratios r = mu / s^2 of each fold and their normalised values q (U10, fp): why the normalisation by
      the mean is carried by GOLD_FRI_PM;
  (2) attribution at equal weekly swing (U10, fp, 2019-2021) for IV00, MV50, Z24, D5: each sleeve's contribution to
      the portfolio's mean weekly R and its share of the portfolio's weekly variance (Euler: cov(W_i, W) / var W),
      reference against variant x k;
  (3) Z family: the out-of-fold trades put at 0, by sleeve and year, with their R (what the switch skipped);
  (4) D family: the stake by sleeve and year (mean over the out-of-fold trades).
Output: results/r2/sizing/weights/diagnostics.json
"""
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import common as C  # noqa: E402
import stakes as S  # noqa: E402


def sleeve_weekly(b, st, years):
    weeks = C.weeks_of_years(years)
    sel = np.isin(b.year_in.to_numpy(), list(years))
    out = {}
    for k in pd.unique(b.k):
        m = sel & (b.k.to_numpy() == k)
        s = pd.Series(st[m] * b.R.to_numpy()[m]).groupby(b.wk_out.to_numpy()[m]).sum()
        out[k] = s.reindex(weeks, fill_value=0.0).to_numpy()
    return pd.DataFrame(out, index=weeks)


def attribution(b, st, keys):
    M0 = sleeve_weekly(b, np.ones(len(b)), C.OOF)
    M1 = sleeve_weekly(b, st, C.OOF)
    W0, W1 = M0.sum(axis=1), M1.sum(axis=1)
    k = float(W0.std(ddof=1) / W1.std(ddof=1))
    M1 = M1 * k
    W1 = W1 * k
    rows = {}
    for s in keys:
        rows[C.SHORT[s]] = {"mean_week_ref": round(float(M0[s].mean()), 4), "mean_week_var": round(float(M1[s].mean()), 4),
                            "var_share_ref": round(float(np.cov(M0[s], W0)[0, 1] / W0.var(ddof=1)), 4),
                            "var_share_var": round(float(np.cov(M1[s], W1)[0, 1] / W1.var(ddof=1)), 4),
                            "sharpe_week_ann_alone": round(C.sharpe(M0[s].to_numpy()), 3)}
    return {"k": round(k, 4), "portfolio_mean_week_ref": round(float(W0.mean()), 4),
            "portfolio_mean_week_var": round(float(W1.mean()), 4), "sd_week": round(float(W0.std(ddof=1)), 4),
            "by_sleeve": rows}


def main():
    decl = {v["id"]: v for v in json.load(open(C.DECLARED))["variants"]}
    full = S.book_frame(C.load_book("fp"))
    keys = C.UNIVERSES["U10"]
    b = full[full.k.isin(keys)].reset_index(drop=True)
    out = {"what": __doc__.split("\n\n")[0]}
    # (1) MV ratios
    tab = {}
    for Y in (2018, 2019, 2020, 2021):
        est = S.fold_estimates(b, keys, Y)
        r = {k: e[0] / e[1] ** 2 for k, e in est.items()}
        m = float(np.mean(list(r.values())))
        tab[Y] = {C.SHORT[k]: {"mu_week": round(est[k][0], 4), "sd_week": round(est[k][1], 4),
                               "r_mu_over_s2": round(r[k], 4), "q_normalised": round(r[k] / m, 3),
                               "r_inv_s": round(1 / est[k][1], 4)} for k in est}
        tab[Y]["_mean_r"] = round(m, 4)
        tab[Y]["_mean_r_without_gold_fri"] = round(float(np.mean([v for k, v in r.items() if k != "GOLD_FRI_PM__xauusd"])), 4)
    out["mv_fold_ratios_U10_fp"] = tab
    # (2) attribution
    out["attribution_U10_fp_2019_2021"] = {}
    for vid in ("IV00", "IV50", "MV50", "Z24", "D5", "D7"):
        st = S.stakes(b, keys, decl[vid])
        out["attribution_U10_fp_2019_2021"][vid] = attribution(b, st, keys)
    # (3) Z skipped trades
    out["z_skipped_U10_fp"] = {}
    oof = np.isin(b.year_in.to_numpy(), list(C.OOF))
    for vid in ("Z12", "Z24", "Z36"):
        st = S.stakes(b, keys, decl[vid])
        rec = {}
        for k in keys:
            for y in C.OOF:
                m = (b.k.to_numpy() == k) & (b.year_in.to_numpy() == y)
                z = m & (st == 0)
                if z.any():
                    rec.setdefault(C.SHORT[k], {})[y] = {"trades_at_0": int(z.sum()), "of": int(m.sum()),
                                                         "R_of_skipped": round(float(b.R.to_numpy()[z].sum()), 2)}
        out["z_skipped_U10_fp"][vid] = {"total_trades_at_0": int((oof & (st == 0)).sum()),
                                        "R_of_skipped": round(float(b.R.to_numpy()[oof & (st == 0)].sum()), 2),
                                        "by_sleeve_year": rec}
    # (4) D stakes
    out["d_mean_stake_U10_fp"] = {}
    for vid in ("D4", "D5", "D6", "D7"):
        st = S.stakes(b, keys, decl[vid])
        out["d_mean_stake_U10_fp"][vid] = {C.SHORT[k]: {y: round(float(st[(b.k.to_numpy() == k) & (b.year_in.to_numpy() == y)].mean()), 3)
                                                        for y in C.OOF} for k in keys}
    C.jdump(out, os.path.join(C.OUT, "diagnostics.json"))
    print(json.dumps(out["mv_fold_ratios_U10_fp"][2019], indent=0)[:1500])
    for vid, a in out["attribution_U10_fp_2019_2021"].items():
        print(vid, a["k"], a["portfolio_mean_week_ref"], a["portfolio_mean_week_var"])
        for s, r in a["by_sleeve"].items():
            print("   ", s, r)
    print(json.dumps(out["z_skipped_U10_fp"], indent=0)[:3000])


if __name__ == "__main__":
    main()
