"""Step 1: regenerate the finalist's trades (fp / gross / stress / every-signal), IS free, VAL through the
logged gl.cut; also the side-flipped ("mirror") trade for every rule trade, and H1 mid bars (<= 2025-12-31)."""
from common import *
from goldlab.sim import simulate
os.makedirs(os.path.join(HERE, "trades"), exist_ok=True)
os.makedirs(os.path.join(HERE, "bars"), exist_ok=True)
out = {}
for sym in SYMS:
    m1 = r2.load(sym)
    print(sym, len(m1), m1.index[0], m1.index[-1], flush=True)
    assert m1.index[-1] < pd.Timestamp("2026-01-01", tz="UTC")
    b = S.h1_bars(m1)
    b["t"] = pd.to_datetime(b["start"], unit="ms", utc=True)
    b.to_parquet(os.path.join(HERE, "bars", f"h1_{sym}.parquet"))
    for kind, mode, no in (("fp", "fp", True), ("gross", "gross", True), ("stress", "stress", True), ("every", "fp", False), ("every_gross", "gross", False)):
        t = r2.run(sym, S.make_orders, P, mode, no, m1)
        ti = gl.cut(t, "is")
        tv = vcut(t, f"{sym}:{kind}")
        ti.to_parquet(os.path.join(HERE, "trades", f"{kind}_is_{sym}.parquet"))
        tv.to_parquet(os.path.join(HERE, "trades", f"{kind}_val_{sym}.parquet"))
        out[f"{sym}:{kind}:is"] = stats(ti); out[f"{sym}:{kind}:val"] = stats(tv)
        print(sym, kind, "IS", stats(ti), "| VAL", stats(tv), flush=True)
    # mirror trades: same entry bars / stop distance / exit bar, opposite side, each simulated independently
    for costname, cst, frame in (("fp", r2.costs(sym), m1),):
        o = S.make_orders(frame, **P).reset_index(drop=True)
        t = simulate(frame, o, sym=sym, costs=cst, no_overlap=True)
        oo = o.loc[t.index].copy()
        # the engine's fill bar = entry_i for market orders
        om = oo.copy(); om["side"] = -om["side"]
        tm = simulate(frame, om.reset_index(drop=True), sym=sym, costs=cst, no_overlap=False)
        # align by entry_time (unique within the one-position run)
        assert t.entry_time.is_unique
        tm = tm.set_index("entry_time").reindex(t.entry_time.to_numpy())
        pair = pd.DataFrame({"entry_time": t.entry_time.to_numpy(), "side": t.side.to_numpy(), "R": t.R.to_numpy(),
                             "R_mirror": tm.R.to_numpy(), "ret": t.ret.to_numpy(), "ret_mirror": tm.ret.to_numpy(),
                             "risk": t.risk.to_numpy(), "entry": t.entry.to_numpy(), "exit_time": t.exit_time.to_numpy(),
                             "exit_time_mirror": tm.exit_time.to_numpy(), "dec_time": t.dec_time.to_numpy()})
        pair["entry_time"] = pd.to_datetime(pair["entry_time"], utc=True)
        pi = pair[pair.entry_time < IS_END]
        pv = vcut(pair, f"{sym}:mirror")
        pi.to_parquet(os.path.join(HERE, "trades", f"mirror_is_{sym}.parquet"))
        pv.to_parquet(os.path.join(HERE, "trades", f"mirror_val_{sym}.parquet"))
        print(sym, "mirror IS: rule", round(pi.R.mean(), 4), "mirror", round(pi.R_mirror.mean(), 4), "| VAL rule", round(pv.R.mean(), 4), "mirror", round(pv.R_mirror.mean(), 4), flush=True)
    r2.free()
json.dump(out, open(os.path.join(HERE, "step1_summary.json"), "w"), indent=1)
