"""P4: retail rollover spreads.  Gold is closed 17:00-18:00 NY in the data (daily break), so
'around the rollover' = the last minutes before the break and the first after the reopen.
Spread widened symmetrically around mid (bid cols -= h, ask cols += h, h = (k-1)*bar spread/2):
  R1 x2  16:30-17:00 + 18:00-18:30 NY  (1 trading hour around rollover)
  R2 x2  16:00-17:00 + 18:00-19:00 NY  (2 trading hours; includes the 16:00 NY time exit)
  R2 x3, R2 x5
  SPK    +$1.00 / +$2.00 absolute spread 16:55-17:00 & 18:00-18:15 NY (retail rollover spike)
Orders are rebuilt on the modified frame (the 00-07 London range never overlaps these windows).
"""
import gc
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *  # noqa: F401,F403

m1 = gl.load_m1("xauusd")
t = pd.read_pickle(os.path.join(HERE, "trades_base.pkl"))
o_base = pd.read_pickle(os.path.join(HERE, "orders_base.pkl"))
ny = m1.index.tz_convert(gl.NY)
mm = (ny.hour * 60 + ny.minute).to_numpy()
spr = (m1.ac - m1.bc).to_numpy()


def win(a, b):
    return (mm >= a) & (mm < b)


W1 = win(16 * 60 + 30, 17 * 60) | win(18 * 60, 18 * 60 + 30)
W2 = win(16 * 60, 17 * 60) | win(18 * 60, 19 * 60)
WS = win(16 * 60 + 55, 17 * 60) | win(18 * 60, 18 * 60 + 15)
SC = {"R1_x2": (W1, "mult", 2.0), "R2_x2": (W2, "mult", 2.0), "R2_x3": (W2, "mult", 3.0),
      "R2_x5": (W2, "mult", 5.0), "SPK_+1usd": (WS, "add", 1.0), "SPK_+2usd": (WS, "add", 2.0)}
frames = [t.assign(variant="baseline")]
info = {}
for k, (mask, mode, x) in SC.items():
    h = np.where(mask, spr * (x - 1) / 2 if mode == "mult" else x / 2, 0.0)
    mm1 = m1.copy()
    for c in ("bo", "bh", "bl", "bc"):
        mm1[c] = mm1[c].to_numpy() - h
    for c in ("ao", "ah", "al", "ac"):
        mm1[c] = mm1[c].to_numpy() + h
    o = S.make_orders(mm1, **PARAMS)
    same = len(o) == len(o_base) and np.allclose(o.level.to_numpy(), o_base.level.to_numpy())
    tt = gl.simulate(mm1, o, no_overlap=True)
    tt["variant"] = k
    xi = gl.entry_index(m1, tt.exit_time - pd.Timedelta(minutes=1) * (tt.reason != "time"))
    info[k] = {"levels_unchanged": bool(same), "stop_exits_in_window": int(((tt.reason == "stop") & mask[np.minimum(xi, len(m1) - 1)]).sum()),
               "mean_spread_in_window_after": round(float(np.mean((mm1.ac - mm1.bc).to_numpy()[mask])), 3)}
    frames.append(tt)
    del mm1
    gc.collect()
xi = gl.entry_index(m1, t.exit_time - pd.Timedelta(minutes=1) * (t.reason != "time"))
info["baseline"] = {"stop_exits_in_W2": int(((t.reason == "stop") & W2[np.minimum(xi, len(m1) - 1)]).sum()),
                    "stop_exits_in_W1": int(((t.reason == "stop") & W1[np.minimum(xi, len(m1) - 1)]).sum()),
                    "stop_exits_in_WS": int(((t.reason == "stop") & WS[np.minimum(xi, len(m1) - 1)]).sum()),
                    "mean_spread_W2": round(float(spr[W2].mean()), 3), "mean_spread_all": round(float(spr.mean()), 3)}
allt = pd.concat(frames)
ti = is_part(allt)
tv = val_part(allt, "rollover spread x2/x3/x5 (16-17 & 18-19 NY) and +$1/$2 spikes")
rows = []
for k in ["baseline"] + list(SC):
    sa, sb = stats(ti[ti.variant == k]), stats(tv[tv.variant == k])
    rows.append({"variant": k, "IS_n": sa["n"], "IS_pf": sa["pf"], "IS_t": sa["t"], "IS_exp": sa["exp"],
                 "VAL_n": sb["n"], "VAL_pf": sb["pf"], "VAL_t": sb["t"], "VAL_exp": sb["exp"]})
r = pd.DataFrame(rows)
pd.set_option("display.width", 250)
print(r.to_string(index=False))
for k, v in info.items():
    print(k, v)
r.to_csv(os.path.join(HERE, "p4_rollover.csv"), index=False)
