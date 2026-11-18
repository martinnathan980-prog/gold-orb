"""Idea 056: the gold 4-hour channel breakout (donch4h_stop) carried to oil. Reads declared.json (never writes it).
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/056_oil_channel_breakout/run.py"""
import json, os, sys, time
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data

FOLDER = os.path.dirname(os.path.abspath(__file__))
H = pd.Timedelta(hours=1)


def four_hour(b):
    """UTC 4-hour bars from hourly bars; 'end' = nominal end (bucket + 4 h) = the time the bar is known."""
    g = b.index.floor("4h")
    f = b.groupby(g).agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
    pc = f["close"].shift(1)
    tr = np.maximum(f["high"] - f["low"], np.maximum((f["high"] - pc).abs(), (f["low"] - pc).abs()))
    f["atr"] = tr.ewm(alpha=1 / 14, adjust=False).mean()
    f["end"] = f.index + pd.Timedelta(hours=4)
    return f


def _signals_arr(b, f, n, entry):
    up = f["high"].rolling(n).max().to_numpy()
    dn = f["low"].rolling(n).min().to_numpy()
    ends = f["end"].to_numpy()
    k = np.searchsorted(ends, b.index.to_numpy(), side="right") - 1      # 4h bars ended at or before the hour's open
    kc = np.clip(k, 0, None)
    U = np.where(k >= 0, up[kc], np.nan)
    Dn = np.where(k >= 0, dn[kc], np.nan)
    if entry == "close":
        c = b["close"].to_numpy()
        L, S = c > U, c < Dn
    else:                                                               # 'touch'
        L, S = b["high"].to_numpy() >= U, b["low"].to_numpy() <= Dn
        both = L & S
        L, S = L & ~both, S & ~both
    m = L | S
    ka = b.index[m] + H
    return pd.DataFrame({"known_at": ka, "side": np.where(L[m], 1, -1).astype(int)})


def build_signals(d, n=60, entry="close"):
    b = d["bars"]
    return _signals_arr(b, four_hour(b), n, entry)


def build_events(d, n=60, entry="close", trail=2.0):
    b = d["bars"]
    f = four_hour(b)
    sig = _signals_arr(b, f, n, entry)
    ends = f["end"].to_numpy()
    sk = pd.DatetimeIndex(sig["known_at"]).to_numpy()
    s = np.searchsorted(sk, ends, side="right") - 1                     # latest signal known at or before each 4h end
    ok = s >= 0
    sc = np.clip(s, 0, None)
    side = np.where(ok, sig["side"].to_numpy()[sc] if len(sig) else 0, 0)
    ja = np.searchsorted(ends, sk, side="right") - 1                    # last 4h bar ended at or before the signal
    atr_sig = np.where(ja >= 0, f["atr"].to_numpy()[np.clip(ja, 0, None)], np.nan)
    A = np.where(ok, atr_sig[sc] if len(sig) else np.nan, np.nan)
    c = f["close"].to_numpy()
    grp = pd.Series(np.where(ok, s, -1))
    cs = pd.Series(c)
    best_hi = cs.groupby(grp).cummax().to_numpy()
    best_lo = cs.groupby(grp).cummin().to_numpy()
    ev = ok & np.isfinite(A) & (((side > 0) & (c <= best_hi - trail * A)) | ((side < 0) & (c >= best_lo + trail * A)))
    return pd.DataFrame({"known_at": pd.DatetimeIndex(f["end"].to_numpy()[ev])})


def main():
    t0 = time.time()
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs = decl["configurations"]
    bars = data.load_bars("oil")
    d = {"bars": bars}
    bk = sim.books({"oil": bars})
    rl = {"bars": H}
    c0 = cfgs[0]

    def rule_of(c):
        ev = build_events(d, c["n"], c["entry"], c["trail_atr"])
        return dict(exit=sim.event_exit(ev, tuple(c["max_hold"])), stop=tuple(c["stop"]))

    tr = checks.truncation_test(lambda x: build_signals(x, c0["n"], c0["entry"]), d, row_len=rl)
    tre = checks.truncation_test(lambda x: build_events(x, c0["n"], c0["entry"], c0["trail_atr"]), d, row_len=rl)
    print("truncation signals:", tr["pass"], tr["n_failed_cuts"], len(tr["cuts"]), "| events:", tre["pass"],
          tre["n_failed_cuts"], len(tre["cuts"]), f"{time.time()-t0:.0f}s", flush=True)
    sig = build_signals(d, c0["n"], c0["entry"]).assign(market="oil")
    rule = rule_of(c0)
    main_t = sim.simulate(sig, bk, **rule)
    every = sim.simulate(sig, bk, mode="every", **rule)
    neigh = {}
    for c in cfgs[1:]:
        s_c = build_signals(d, c["n"], c["entry"]).assign(market="oil")
        neigh[c["id"]] = sim.simulate(s_c, bk, **rule_of(c))
    null = stats.null_test(main_t, bk, n_draws=2000, **rule)
    shift = checks.shift_test(sig, bk, **rule)

    def summ(t):
        if not len(t):
            return {"n": 0}
        return {"n": int(len(t)), "PF_net": stats.pf(t.R), "PF_gross": stats.pf(t.R_gross), "PF_stress": stats.pf(t.R_stress),
                "mean_R": float(t.R.mean()), "mean_R_gross": float(t.R_gross.mean()),
                "mean_net_bp": float(t.net_bp.mean()), "mean_gross_bp": float(t.gross_bp.mean()),
                "hold_h_median": float(t.hold_h.median())}
    yrs = main_t.entry_time.dt.year
    detail = {
        "main": summ(main_t), "long": summ(main_t[main_t.side > 0]), "short": summ(main_t[main_t.side < 0]),
        "by_year": {int(y): summ(g) for y, g in main_t.groupby(yrs)},
        "reasons": main_t.reason.value_counts().to_dict(),
        "every": summ(every), "neighbours": {k: summ(v) for k, v in neigh.items()},
        "counts": main_t.attrs["counts"], "shift_test": shift,
    }
    res = judge.verdict(FOLDER, main_t, neigh, every, null, n_configs=len(cfgs), truncation=tr, event_truncation=tre,
                        data_desc="oil hourly bars 2013-2021 (kit v2.1, roll-adjusted), PROVISIONAL costs",
                        extra={"detail": detail})
    json.dump(detail, open(os.path.join(FOLDER, "detail.json"), "w"), indent=1, default=str)
    print(json.dumps(detail, indent=1, default=str))
    print("VERDICT:", res["verdict"], "failed:", res["failed_bars"])
    print(res["ledger_line"])
    print(f"done in {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
