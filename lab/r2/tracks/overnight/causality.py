"""Truncation test: orders built on data cut at random times must equal the orders built on the full data
up to those times (entry bar, side, stop distance; and the exit bar when the exit lies before the cut).
Usage: python3 causality.py            (runs every config in CONFIGS; IS frame only)
"""
import json
import sys

import numpy as np
import pandas as pd

from common import RES, S, r2, use

CONFIGS = {
    "btc_late": ("btcusd", dict(tz="NY", entry="17:05", exit="19:00", stop_atr=2.0, atr_tf="1h")),
    "idx_fade_long": ("us100", dict(tz="NY", entry="09:30", exit="16:00", weekdays=(0, 1, 2, 3, 4), cond="prev_sess_down",
                                    stop_atr=1.0, atr_tf="D")),
    "idx_fade_ls": ("us500", dict(tz="NY", entry="09:30", exit="16:00", weekdays=(0, 1, 2, 3, 4), cond="fade_prev_sess",
                                  stop_atr=1.0, atr_tf="D")),
    "idx_night_up": ("us100", dict(tz="NY", entry="15:55", exit="09:30", exit_next=True, weekdays=(0, 1, 2, 3, 4),
                                   cond="sess_up", stop_atr=1.0, atr_tf="D")),
    "ger_night": ("ger40", dict(tz="BER", entry="17:25", exit="09:00", exit_next=True, weekdays=(0, 1, 2, 3, 4),
                                cond="sess_up", sess_open="09:00", sess_close="17:30", stop_atr=1.0, atr_tf="D")),
    "btc_late_limit": ("btcusd", dict(tz="NY", entry="17:05", exit="19:00", stop_atr=2.0, atr_tf="1h", entry_type="limit",
                                      limit_min=30)),
    # the two finalists, every sleeve
    "FINALIST GOLD_FRI_PM xauusd": ("xauusd", S.finalist_params("GOLD_FRI_PM", "xauusd")),
    "FINALIST MONTH_END_NIGHT us500": ("us500", S.finalist_params("MONTH_END_NIGHT", "us500")),
    "FINALIST MONTH_END_NIGHT us100": ("us100", S.finalist_params("MONTH_END_NIGHT", "us100")),
    "FINALIST MONTH_END_NIGHT ger40": ("ger40", S.finalist_params("MONTH_END_NIGHT", "ger40")),
}


def check(sym, params, n_cuts=8, seed=7, m1=None):
    use(sym)
    m1 = r2.load(sym, end="2022-01-01") if m1 is None else m1
    full = S.make_orders(m1, **params)
    t_entry = m1.index[full["entry_i"].to_numpy()]
    t_exit = m1.index[full["exit_i"].to_numpy()]
    rng = np.random.default_rng(seed)
    lo, hi = int(len(m1) * 0.15), len(m1) - 10
    res = []
    for cut in sorted(rng.integers(lo, hi, n_cuts)):
        T = m1.index[cut]
        part = S.make_orders(m1.iloc[:cut], **params)
        ref = full[t_entry < T].reset_index(drop=True)
        ref_exit = t_exit[t_entry < T]
        same_n = len(part) == len(ref)
        k = min(len(part), len(ref))
        a, b = part.iloc[:k], ref.iloc[:k]
        same_entry = bool((a["entry_i"].to_numpy() == b["entry_i"].to_numpy()).all())
        same_side = bool((a["side"].to_numpy() == b["side"].to_numpy()).all())
        same_stop = bool(np.allclose(a["stop_dist"].to_numpy(), b["stop_dist"].to_numpy(), rtol=1e-12, atol=0))
        done = (ref_exit[:k] < T - pd.Timedelta(minutes=2))
        same_exit = bool((a["exit_i"].to_numpy()[done] == b["exit_i"].to_numpy()[done]).all())
        if "level" in a:      # limit entries: level always, expiry when the trade is over before the cut
            same_entry &= bool(np.allclose(a["level"].to_numpy(), b["level"].to_numpy(), rtol=1e-12, atol=0))
            same_exit &= bool((a["expiry_i"].to_numpy()[done] == b["expiry_i"].to_numpy()[done]).all())
        res.append({"cut": str(T), "orders_cut": len(part), "orders_full_before_cut": len(ref), "same_n": same_n,
                    "same_entry": same_entry, "same_side": same_side, "same_stop": same_stop, "same_exit_when_done": same_exit,
                    "open_at_cut": int((~done).sum())})
    ok = all(r["same_n"] and r["same_entry"] and r["same_side"] and r["same_stop"] and r["same_exit_when_done"] for r in res)
    return ok, res


if __name__ == "__main__":
    names = sys.argv[1:] or list(CONFIGS)
    out = {}
    for nm in names:
        sym, params = CONFIGS[nm]
        ok, res = check(sym, params)
        out[nm] = {"sym": sym, "params": params, "pass": ok, "cuts": res}
        print(f"{nm:<32} {sym:<7} causality {'PASS' if ok else 'FAIL'}  "
              + " ".join(f"[{r['orders_cut']}/{r['orders_full_before_cut']} open={r['open_at_cut']}]" for r in res), flush=True)
        if not ok:
            print(json.dumps(res, indent=1))
    r2.free()
    json.dump(out, open(f"{RES}/causality.json", "w"), indent=1, default=str)
