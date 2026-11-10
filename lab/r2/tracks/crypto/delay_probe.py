"""Execution-delay / stale-quote probe for the two shortlisted rules (IS only).

Part 1 (descriptive, mid prices, no stop): for every signal of the rule, signed move in bp from the decision
  time to +1, +2, +5, +15, +30, +60 minutes, and from the decision to the scheduled exit. If the quotes were
  stale (the data's mid lagging the real market), most of the edge would sit in the first minutes.
Part 2 (engine, logged as trials tagged diag-delay): the same rule with the market order sent 5 and 30 minutes late.
"""
import sys, json
sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/crypto")
from helpers import *  # noqa

CFG = {
    "brk72_24h": {"family": "brk", "n": 72, "stop_atr": 3.0, "hold_h": 24},
    "sess_8_8_13": {"family": "sess", "dec_h": 8, "look_h": 8, "stop_atr": 3.0, "hold_h": 13},
}
IS_END = pd.Timestamp("2022-01-01", tz="UTC")

if __name__ == "__main__":
    out = {}
    for sym in ("btcusd", "ethusd"):
        m1 = r2.load(sym)
        ts = S.ts_ms(m1)
        mid_o = ((m1["bo"].to_numpy() + m1["ao"].to_numpy()) / 2)
        for name, p in CFG.items():
            o = S.make_orders(m1, **p)
            o = o[o.dec_time < IS_END].reset_index(drop=True)
            dec = o.dec_time.values.astype("datetime64[ms]").astype(np.int64)
            px0 = mid_o[o.entry_i.to_numpy()]
            row = {"n_signals": int(len(o))}
            for d in (1, 2, 5, 15, 30, 60):
                i = np.searchsorted(ts, dec + d * S.M_MS)
                ok = (i < len(ts)) & (ts[np.clip(i, 0, len(ts) - 1)] - (dec + d * S.M_MS) <= 5 * S.M_MS)
                mv = o.side.to_numpy()[ok] * (mid_o[i[ok]] / px0[ok] - 1) * 1e4
                row[f"move_first_{d}min_bp"] = round(float(mv.mean()), 2)
                row[f"t_{d}min"] = round(float(mv.mean() / mv.std() * np.sqrt(len(mv))), 2)
            xi = np.clip(o.exit_i.to_numpy(), 0, len(ts) - 1)
            tot = o.side.to_numpy() * (mid_o[xi] / px0 - 1) * 1e4
            row["move_to_sched_exit_bp(no stop)"] = round(float(tot.mean()), 2)
            # by year: first 5 minutes
            i5 = np.clip(np.searchsorted(ts, dec + 5 * S.M_MS), 0, len(ts) - 1)
            mv5 = pd.Series(o.side.to_numpy() * (mid_o[i5] / px0 - 1) * 1e4, index=o.dec_time.dt.year.to_numpy())
            row["first_5min_bp_by_year"] = {int(k): round(float(v), 2) for k, v in mv5.groupby(level=0).mean().items()}
            out[f"{name}:{sym}"] = {"descriptive": row}
            print(name, sym, row, flush=True)
            for d in (5, 30):
                ev = run_trial(sym, dict(p, delay_min=d), full=False, stage="diag-delay", note=f"execution-delay probe of {name}")
                out[f"{name}:{sym}"][f"engine_delay_{d}min"] = {"n": ev["is"]["n"], "pf": ev["is"]["pf"], "t": ev["is"]["t_stat"],
                                                                 "exp_R": ev["is"]["expectancy_R"], "bps": ev["is_bps_per_trade"]}
        r2.free()
    json.dump(out, open(os.path.join(OUT, "delay_probe.json"), "w"), indent=1)
