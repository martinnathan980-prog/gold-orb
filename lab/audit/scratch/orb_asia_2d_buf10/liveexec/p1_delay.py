"""P1: manual execution.  The alert fires when the stop order WOULD have filled (touch bar fi);
the trader enters AT MARKET N minutes later (open of the first M1 bar starting >= t(fi)+N min).
Same time exit.  Two stop conventions:
  A 'dist'  : same stop DISTANCE as designed (|level-stop| = 1.2 x range width) from the actual fill
  B 'abs'   : same ABSOLUTE stop price (opposite level); signal dropped if price already beyond it
One position at a time (engine no_overlap on the delayed entry bar).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
o = pd.read_pickle(os.path.join(HERE, "orders_base.pkl"))
t_base = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
idx = m1.index
ao, bo = m1.ao.to_numpy(), m1.bo.to_numpy()
fi = o.entry_i.to_numpy()
t_fill = idx[fi]
dist = (o.level - o.stop).abs().to_numpy()

rows, frames = [], []
for N in (0, 1, 5, 15, 60, 240):
    for conv in ("dist", "abs"):
        if N == 0 and conv == "abs":
            continue
        if N == 0:
            oo = o.copy()          # the backtest itself (stop order at the level)
        else:
            ei = gl.entry_index(m1, t_fill + pd.Timedelta(minutes=N))
            ei = np.minimum(ei, len(m1) - 1)
            oo = pd.DataFrame({"entry_i": ei, "side": o.side, "etype": 0, "exit_i": o.exit_i,
                               "date": o.date, "orig_fill_i": fi})
            if conv == "dist":
                oo["stop"] = np.nan
                oo["stop_dist"] = dist
            else:
                oo["stop"] = o.stop.to_numpy()
                px = np.where(o.side > 0, bo[ei], ao[ei])  # the quote that would trigger the stop
                beyond = np.where(o.side > 0, px <= o.stop, px >= o.stop)
                oo = oo[~beyond]
            oo = oo[oo.exit_i > oo.entry_i]
        tt = gl.simulate(m1, oo, no_overlap=True)
        tt["variant"] = f"N{N}_{conv}"
        tt["N"] = N
        frames.append(tt)

allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "manual-delay N=0/1/5/15/60/240 min, stop same-distance vs same-absolute")

base_by_date = t_base.set_index("date")
for var in allt.variant.unique():
    a, b = ti[ti.variant == var], tv[tv.variant == var]
    # entry price change vs the backtest fill, in R of the designed risk, on common dates
    full = allt[allt.variant == var]
    com = full[full.date.isin(base_by_date.index)]
    if var != "N0_dist":
        bb = base_by_date.loc[com.date]
        dR = (com.side.to_numpy() * (com.entry.to_numpy() - bb.entry.to_numpy()) /
              (bb.entry.to_numpy() - bb.stop.to_numpy()).__abs__())
        adv = float(np.mean(dR))
        # baseline trades already stopped out before the delayed entry
        stopped_before = int(((bb.reason.to_numpy() == "stop") &
                              (bb.exit_time.to_numpy() <= com.entry_time.to_numpy())).sum())
    else:
        adv, stopped_before = 0.0, 0
    si, sv = stats(a), stats(b)
    rows.append({"variant": var, "IS_n": si["n"], "IS_pf": si["pf"], "IS_t": si["t"], "IS_exp": si["exp"],
                 "IS_yrs": si["yrs_pos"], "IS_pfL": si["pf_long"], "IS_pfS": si["pf_short"],
                 "VAL_n": sv["n"], "VAL_pf": sv["pf"], "VAL_t": sv["t"], "VAL_exp": sv["exp"],
                 "VAL_pfL": sv["pf_long"], "VAL_pfS": sv["pf_short"],
                 "entry_worse_R_mean": round(adv, 4), "n_common_dates": int(len(com)),
                 "base_stopped_before_entry": stopped_before})
res = pd.DataFrame(rows)
pd.set_option("display.width", 250)
pd.set_option("display.max_columns", 30)
print(res.to_string(index=False))
res.to_csv(os.path.join(HERE, "p1_delay.csv"), index=False)

# where does the delay cost come from?  mean favourable move of price after the touch (mid, in R)
mid_o = 0.5 * (ao + bo)
for N in (1, 5, 15, 60, 240):
    ei = np.minimum(gl.entry_index(m1, t_fill + pd.Timedelta(minutes=N)), len(m1) - 1)
    mv = o.side.to_numpy() * (mid_o[ei] - o.level.to_numpy()) / dist
    yrs = idx[fi].year
    isv = yrs <= 2021
    print(f"N={N:3d}  mid move after touch in R (side-signed, + = trade direction): IS mean {mv[isv].mean():+.3f} "
          f"median {np.median(mv[isv]):+.3f} | share beyond stop (<-1R) IS {np.mean(mv[isv] < -1):.3f}")
