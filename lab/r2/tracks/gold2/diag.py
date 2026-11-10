"""In-sample diagnostics of the shortlisted rules (no new configuration): sides, halves (gross and net),
entry hour, concentration, daily-break exposure."""
import json, os, sys
import numpy as np, pandas as pd
from research import RES, is_trades, pf, tstat, gl
import stageB, stageA

CANDS = {"SQ": stageB.B["B5_sq1h_n24_07"], "TR": stageB.B["B3_d1h_n48_tr240_k2"]}


def block(t):
    R = t.R.to_numpy()
    if len(R) == 0:
        return {"n": 0}
    return {"n": int(len(R)), "exp_R": round(float(R.mean()), 4), "pf": round(pf(R), 3), "t": round(tstat(R), 2),
            "bps": round(float((t.pnl / t.entry).mean() * 1e4), 2), "win": round(float((R > 0).mean()), 3)}


def diag(name, params, sym="xauusd"):
    out = {}
    net = is_trades(sym, params, "fp")
    gro = is_trades(sym, params, "gross")
    mid = pd.Timestamp("2017-07-01", tz="UTC")
    out["net"] = block(net)
    out["gross"] = block(gro)
    out["long_net"], out["short_net"] = block(net[net.side > 0]), block(net[net.side < 0])
    out["long_gross"], out["short_gross"] = block(gro[gro.side > 0]), block(gro[gro.side < 0])
    out["half1_net_2013-2017H1"], out["half2_net_2017H2-2021"] = block(net[net.entry_time < mid]), block(net[net.entry_time >= mid])
    out["half1_gross_2013-2017H1"], out["half2_gross_2017H2-2021"] = block(gro[gro.entry_time < mid]), block(gro[gro.entry_time >= mid])
    out["gross_by_year"] = {int(y): block(g) for y, g in gro.groupby(gro.entry_time.dt.year)}
    out["net_by_year_side"] = {int(y): {"long_R": round(float(g.R[g.side > 0].sum()), 1), "short_R": round(float(g.R[g.side < 0].sum()), 1)}
                               for y, g in net.groupby(net.entry_time.dt.year)}
    # entry hour (New York clock)
    ny = net.entry_time.dt.tz_convert(gl.NY)
    hh = ny.dt.hour
    out["net_by_ny_hour"] = {int(h): {"n": int(len(g)), "sum_R": round(float(g.R.sum()), 1), "exp_R": round(float(g.R.mean()), 3)}
                             for h, g in net.groupby(hh)}
    sess = np.where((hh >= 18) | (hh < 2), "asia_18-02ny", np.where(hh < 8, "london_02-08ny", np.where(hh < 12, "ny_am_08-12", "ny_pm_12-17")))
    out["net_by_session"] = {s: block(net[sess == s]) for s in ("asia_18-02ny", "london_02-08ny", "ny_am_08-12", "ny_pm_12-17")}
    reopen = (hh == 18) | ((hh == 17))
    out["entries_in_reopen_hour_17-19ny"] = block(net[reopen.to_numpy()])
    out["entries_first_5min_after_reopen"] = block(net[((hh == 18) & (ny.dt.minute < 5)).to_numpy()])
    # concentration
    R = np.sort(net.R.to_numpy())[::-1]
    k = max(1, int(round(0.05 * len(R))))
    out["top5pct_share_of_total_R"] = round(float(R[:k].sum() / R.sum()), 2)
    out["total_R_without_top5pct"] = round(float(R[k:].sum()), 1)
    out["best_trade_R"] = round(float(R[0]), 2)
    out["worst_trade_R"] = round(float(R[-1]), 2)
    out["exit_reasons"] = net.reason.value_counts().to_dict()
    out["avg_hold_h"] = round(float(net.hold_min.mean() / 60), 1)
    out["median_hold_h"] = round(float(net.hold_min.median() / 60), 1)
    out["median_risk_usd_is"] = round(float(net.risk.median()), 2)
    out["cost_R_per_trade"] = round(float(gro.R.mean() - net.R.mean()), 4)
    wk = net.groupby(net.exit_time.dt.tz_convert(None).dt.to_period("W"))["R"].sum()
    out["worst_week_R"] = round(float(wk.min()), 1)
    out["weeks_with_trades_pos_pct"] = round(float((wk > 0).mean() * 100), 1)
    return out


if __name__ == "__main__":
    res = {}
    for k, p in CANDS.items():
        res[k] = diag(k, p)
        d = res[k]
        print("=====", k)
        for q in ("net", "gross", "long_net", "short_net", "long_gross", "short_gross", "half1_net_2013-2017H1", "half2_net_2017H2-2021",
                  "half1_gross_2013-2017H1", "half2_gross_2017H2-2021", "net_by_session", "entries_in_reopen_hour_17-19ny",
                  "entries_first_5min_after_reopen", "top5pct_share_of_total_R", "total_R_without_top5pct", "best_trade_R", "worst_trade_R",
                  "exit_reasons", "avg_hold_h", "median_hold_h", "median_risk_usd_is", "cost_R_per_trade", "worst_week_R", "weeks_with_trades_pos_pct"):
            print(" ", q, json.dumps(d[q]))
        print("  gross by year:", {y: (v["n"], v["exp_R"], v["bps"]) for y, v in d["gross_by_year"].items()})
        print("  net by year/side:", d["net_by_year_side"])
        print("  by NY hour:", {h: (v["n"], v["sum_R"]) for h, v in d["net_by_ny_hour"].items()})
    json.dump(res, open(os.path.join(RES, "diag_shortlist_is.json"), "w"), indent=1)
