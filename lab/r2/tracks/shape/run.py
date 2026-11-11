"""Track `shape`: simulate the exit variants of the eleven sleeves IN-SAMPLE, log every one, apply the
pre-registered selection rule (PROTOCOL_V3 section 4) and write results/r2/shape/{trials.jsonl, <sleeve>.csv,
variants_all.csv, checks.csv, selection.json}.

Variants: pure target k x R0, pure break-even at 1 R0, (target + break-even only if promising); every variant also
gives a "half and half" reading (half the risk on the original exit, half on the variant: the average of the two R
of each baseline order, no new simulation).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import strategy as S  # noqa: E402
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.metrics import report  # noqa: E402

OUT = os.path.join(S.LAB, "results", "r2", "shape")
T = lambda *ks: [dict(k=k, be=None) for k in ks]
BE = [dict(k=None, be=1.0)]
# Budget: <= 50 simulated variants. Grid chosen from the baseline MFE distribution (baseline_diag.csv): no k = 3 where
# fewer than ~10 % of trades ever reach 3 R; GOLD_FRI_PM never reaches 1.5 R; break-even is useless on
# donch4h_stop (its trailing stop at 1 R0 already sits at the entry once the trade is 1 R ahead), on GOLD_FRI_PM
# (1.4 % of trades reach 1 R) and is tested on one of each pair of near-identical crypto sleeves only.
GRID = {
    "noise30:us100": T(0.5, 1, 1.5, 2) + BE,
    "ocm4:us100": T(0.5, 1, 1.5, 2) + BE,
    "brk72_24h_wd:btcusd": T(0.5, 1, 1.5, 2) + BE,
    "nq_btc_follow:btcusd": T(0.5, 1, 1.5),
    "F1_brk_ridge_filter:btcusd": T(0.5, 1, 1.5, 2) + BE,
    "brk72_24h_wd:ethusd": T(0.5, 1, 1.5, 2),
    "F1_brk_ridge_filter:ethusd": T(0.5, 1, 1.5, 2),
    "GOLD_FRI_PM:xauusd": T(0.5, 1),
    "donch4h_stop:xauusd": T(0.5, 1, 1.5, 2),
    "orb_asia_2d_buf10:xauusd": T(0.5, 1, 1.5, 2, 3) + BE,
    "outer_close_ride:xauusd": T(0.5, 1, 1.5, 2) + BE,
}


def vname(v, half=False):
    s = "+".join(([f"T{v['k']:g}"] if v.get("k") is not None else []) + ([f"BE{v['be']:g}"] if v.get("be") is not None else []))
    return ("half:" if half else "") + (s or "base")


def stats(R, base_exp=None):
    R = np.asarray(R, float)
    w, l = R[R > 0].sum(), -R[R < 0].sum()
    d = dict(n=int(len(R)), win=round(float((R > 0).mean()), 4), pf=round(float(w / l), 3) if l > 0 else np.inf,
             exp=round(float(R.mean()), 4), t=round(float(R.mean() / R.std(ddof=1) * np.sqrt(len(R))), 2),
             total_R=round(float(R.sum()), 1))
    if base_exp is not None:
        d["keep"] = round(float(R.mean() / base_exp), 3)
    return d


def check(base, var_all, var_pure, m1, orders, rng):
    """Entries and initial stops of the variant identical to the baseline's (20 random trades), R0 estimate vs
    engine risk, causality of the added columns (R0 recomputed on the frame truncated at the entry minute)."""
    common = base.index.intersection(var_pure.index)
    pick = rng.choice(common, size=min(20, len(common)), replace=False)
    same_pure = bool(np.allclose(base.loc[pick, ["entry", "stop"]].to_numpy(), var_pure.loc[pick, ["entry", "stop"]].to_numpy())
                     and (base.loc[pick, "entry_time"] == var_pure.loc[pick, "entry_time"]).all())
    same_all = bool((base.entry_time == var_all.loc[base.index, "entry_time"]).all()
                    and np.allclose(base[["entry", "stop"]].to_numpy(), var_all.loc[base.index, ["entry", "stop"]].to_numpy()))
    caus = True
    for j in pick[:5]:
        ei = int(orders.loc[j, "entry_i"])
        a, _ = S.initial_risk(m1, orders.loc[[j]])
        b, _ = S.initial_risk(m1.iloc[:ei + 1], orders.loc[[j]])
        caus &= bool(np.allclose(a, b))
    return dict(n_common=int(len(common)), same_entry_stop_20=same_pure, same_entry_stop_all_base=same_all,
                causal=caus)


def main():
    if os.path.exists(os.path.join(OUT, "trials.jsonl")):
        raise SystemExit("trials.jsonl exists: the grid has already been run (no re-run, no double logging)")
    os.makedirs(OUT, exist_ok=True)
    rng = np.random.default_rng(3)
    allrows, checks, sel = [], [], {}
    n_sim = 0
    last = None
    for key, (sym, mo, params) in S.sleeves().items():
        if sym != last:
            r2.free(); last = sym
        t0 = time.time()
        m1 = r2.load(sym)
        base = gl.cut(r2.run(sym, mo, params, "fp", True, m1), "is")
        orders = mo(m1, **params).reset_index(drop=True)
        r0, _ = S.initial_risk(m1, orders)
        err = np.abs(r0[base.index.to_numpy()] / base.risk.to_numpy() - 1)
        b = stats(base.R)
        rows = [dict(sleeve=key, variant="base", **b, keep=1.0)]
        for v in GRID[key]:
            mv = S.shaped(mo, k=v["k"], be_r=v["be"])
            tp = gl.cut(r2.run(sym, mv, params, "fp", True, m1), "is")           # the variant as an EA would run it
            ta = gl.cut(r2.run(sym, mv, params, "fp", False, m1), "is")          # every order: R of each baseline order
            n_sim += 1
            ev = {"sym": sym, "is": report(tp), "is_bps_per_trade": r2._bps(tp)}
            r2.log_trial("shape", sym, dict(params, sleeve=key, shape_variant=vname(v), shape_k=v["k"], shape_be=v["be"]), ev)
            rows.append(dict(sleeve=key, variant=vname(v), **stats(tp.R, b["exp"])))
            half = 0.5 * base.R.to_numpy() + 0.5 * ta.loc[base.index, "R"].to_numpy()
            rows.append(dict(sleeve=key, variant=vname(v, True), **stats(half, b["exp"])))
            c = check(base, ta, tp, m1, orders, rng)
            checks.append(dict(sleeve=key, variant=vname(v), r0_err_med=round(float(np.median(err)), 5),
                               r0_err_p95=round(float(np.percentile(err, 95)), 5), r0_err_max=round(float(err.max()), 4),
                               tgt_exits=int((tp.reason == "target").sum()), **c))
        df = pd.DataFrame(rows)
        df.to_csv(os.path.join(OUT, f"{key.replace(':', '__')}.csv"), index=False)
        allrows.append(df)
        # PROTOCOL_V3 section 4: keep >= 85 % of the IS expectancy per trade and PF >= 1.12, highest win rate.
        # The original exit is one of the candidates (it trivially passes): a qualifying variant with a LOWER win
        # rate than the original is not a reason to change the exit.
        q = df[(df.variant != "base") & (df.keep >= 0.85) & (df.pf >= 1.12)]
        best = q.sort_values(["win", "exp"], ascending=False).head(1)
        if len(best) and best.win.iloc[0] > b["win"]:
            r = best.iloc[0]
            vv = r.variant
            half = vv.startswith("half:")
            core = vv.split(":")[-1]
            k = next((float(p[1:]) for p in core.split("+") if p.startswith("T")), None)
            be = next((float(p[2:]) for p in core.split("+") if p.startswith("BE")), None)
            sel[key] = dict(variant=vv, k=k, be=be, half=half, base=b, selected={c: r[c] for c in ("n", "win", "pf", "exp", "t", "total_R", "keep")},
                            n_qualifying=int(len(q)))
        else:
            sel[key] = dict(variant=None, base=b, n_qualifying=int(len(q)))
        print(key, f"[{time.time() - t0:.0f}s]", sel[key]["variant"], flush=True)
        print(df.to_string(index=False), flush=True)
    pd.concat(allrows).to_csv(os.path.join(OUT, "variants_all.csv"), index=False)
    pd.DataFrame(checks).to_csv(os.path.join(OUT, "checks.csv"), index=False)
    json.dump({"rule": "PROTOCOL_V3 s.4: among variants (pure and half-and-half) with IS expectancy/trade >= 85% of the "
                       "sleeve's and PF >= 1.12, the highest share of winning trades (ties: higher expectancy); the original "
                       "exit is kept if none qualifies or none beats its win rate",
               "n_simulated_variants": n_sim, "selection": sel},
              open(os.path.join(OUT, "selection.json"), "w"), indent=1, default=float)
    print("simulated variants:", n_sim)


if __name__ == "__main__":
    main()
