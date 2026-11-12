"""Part 2 -- simulate exactly the variants of declared.json (FP costs and costs x1.5), one JSON line each in
results/r2/autopsy/path/trials.jsonl (losing ones too).

EC / NP: every signal run alone (no_overlap False) -> each order's own fill and path -> where the rule fires,
exit_i := decision bar + 1 (never later than the original exit) -> run with no_overlap True (an earlier exit frees
the sleeve for its next signal).  HC: the official trade set, each trade rerun alone with the cut exit, R = average
of the two halves.  Orders whose stop is under 3 spreads at their fill are removed first (none in the baseline).
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402


class Sleeve:
    """One sleeve on one frame (fp or stressed): orders, every-signal paths, baseline trades."""

    def __init__(self, name, sym, m1, stress, leader):
        self.name, self.sym, self.m1, self.stress = name, sym, m1, stress
        o = C.build_orders(name, sym, m1, leader)
        ta = C.sim(m1, o, sym, stress=stress, no_overlap=False)
        fi, xi = C.fill_exit_bars(m1, ta)
        spread = m1["ao"].to_numpy()[fi] - m1["bo"].to_numpy()[fi]
        tight = ta.risk.to_numpy() < 3 * spread
        self.n_orders = len(o)
        self.n_tight = int(tight.sum())
        drop = ta.index[tight]
        o = o.drop(index=drop)
        keep = ~tight
        ta, fi, xi = ta[keep], fi[keep], xi[keep]
        self.o = o                                     # order rows (original numbering, tight ones removed)
        self.ta = ta                                   # every-signal trades, indexed by order row
        self.fi, self.xi = fi, xi
        self.ns = C.ns_index(m1)
        self.A = C.arrays(m1)
        self.fill_ns = self.ns[fi]
        self.plan_ns = C.planned_end_ns(name, m1, o.loc[ta.index], self.fill_ns)
        self.side = ta.side.to_numpy(np.int64)
        self.entry = ta.entry.to_numpy(float)
        self.risk = ta.risk.to_numpy(float)
        self.tb = self.run(o)                          # baseline, one position at a time

    def run(self, orders):
        """no_overlap True run; trades indexed by order row (original numbering)."""
        oo = orders.sort_values("entry_i", kind="stable")
        rows = oo.index.to_numpy()
        t = C.sim(self.m1, oo.reset_index(drop=True), self.sym, stress=self.stress, no_overlap=True)
        t.index = rows[t.index.to_numpy()]
        return t

    def decision(self, ck):
        """Decision bar d, still-open flag and state u for every filled order (aligned with self.ta)."""
        d, _ = C.checkpoint_bars(self.ns, self.fill_ns, self.plan_ns, minutes=ck.get("minutes"), frac=ck.get("frac"))
        N = len(self.ns)
        is_open = (d >= self.fi) & (d < self.xi) & (d + 1 < N)
        dd = np.clip(d, 0, N - 1)
        u = C.open_result(self.A, dd, self.side, self.entry, self.risk)
        return dd, is_open, u

    def variant(self, v):
        dd, is_open, u = self.decision(v["ck"])
        if v["rule"] == "EC":
            fire = is_open & (u <= -v["x"])
        elif v["rule"] == "NP":
            fire = is_open & (u < v["y"])
        elif v["rule"] == "HC":
            fire = is_open & (u <= 0)
        else:
            raise ValueError(v["rule"])
        rows = self.ta.index.to_numpy()
        new_exit = pd.Series(dd + 1, index=rows)
        fired_rows = rows[fire]
        if v["rule"] in ("EC", "NP"):
            om = self.o.copy()
            ex = om.loc[fired_rows, "exit_i"].to_numpy(np.int64)
            ne = new_exit.loc[fired_rows].to_numpy(np.int64)
            om.loc[fired_rows, "exit_i"] = np.where(ex >= 0, np.minimum(ex, ne), ne)
            tv = self.run(om)
            info = {"n_fired_in_trades": int(np.isin(tv.index, fired_rows).sum()),
                    "n_new_trades": int((~np.isin(tv.index, self.tb.index)).sum()),
                    "n_lost_trades": int((~np.isin(self.tb.index, tv.index)).sum())}
            return tv, info, set(fired_rows)
        # HC: same trade set, half of each fired trade leaves at the cut
        tb = self.tb
        oc = self.o.loc[tb.index].copy()
        f_tb = np.isin(tb.index, fired_rows)
        ex = oc["exit_i"].to_numpy(np.int64)
        ne = new_exit.reindex(tb.index).to_numpy()
        ne = np.where(np.isfinite(ne), ne, -1).astype(np.int64)
        oc["exit_i"] = np.where(f_tb, np.where(ex >= 0, np.minimum(ex, ne), ne), ex)
        rows_tb = tb.index.to_numpy()
        tc = C.sim(self.m1, oc.reset_index(drop=True), self.sym, stress=self.stress, no_overlap=False).sort_index()
        assert len(tc) == len(tb)
        tc.index = rows_tb[tc.index.to_numpy()]
        tc = tc.loc[tb.index]
        assert (tc.entry_time.to_numpy() == tb.entry_time.to_numpy()).all()
        tv = tb.copy()
        tv["R"] = 0.5 * tb.R.to_numpy() + 0.5 * tc.R.to_numpy()
        info = {"n_fired_in_trades": int(f_tb.sum()), "n_new_trades": 0, "n_lost_trades": 0}
        return tv, info, set(fired_rows)


def summarise(tv, tb, info, fired):
    out = {}
    for per in ("common", "pre"):
        w = C.window(tv, per)
        out[per] = C.stats(w, years=C.YEARS if per == "common" else None)
        out[per]["n_fired"] = int(np.isin(w.index, list(fired)).sum()) if len(fired) else 0
    out.update(info)
    return out


def main():
    dec = json.load(open(os.path.join(C.RES, "declared.json")))
    by_sleeve = {}
    for v in dec["variants"]:
        by_sleeve.setdefault(v["sleeve"], []).append(v)
    path = os.path.join(C.RES, "trials.jsonl")
    done = set()
    if os.path.exists(path):
        done = {json.loads(l)["id"] for l in open(path)}
    base_out = {}
    cur = None
    m1 = leader = None
    t_start = time.time()
    for name, sym in C.ORDER:
        sl = f"{name}:{sym}"
        todo = [v for v in by_sleeve[sl] if v["id"] not in done]
        if sym != cur:
            m1 = None
            m1 = C.load_is(sym)
            leader = C.load_is("us100", cols=["bo", "ao", "bc", "ac"]) if sym == "btcusd" else None
            cur = sym
        res = {}
        for mode in ("fp", "stress"):
            t0 = time.time()
            fr = C.frame_for(m1, mode == "stress")
            S = Sleeve(name, sym, fr, mode == "stress", leader)
            if mode == "fp":   # the FP baseline must be the reproduced official set of step 0, trade for trade
                b0 = pd.read_parquet(os.path.join(C.RES, "baseline", f"{name}__{sym}.parquet"))
                assert len(b0) == len(S.tb) and (b0.entry_time.to_numpy() == S.tb.entry_time.to_numpy()).all()
                assert np.allclose(b0.R.to_numpy(), S.tb.R.to_numpy(), rtol=0, atol=1e-12)
            base = summarise(S.tb, S.tb, {"n_fired_in_trades": 0, "n_new_trades": 0, "n_lost_trades": 0}, set())
            base.update({"n_orders": S.n_orders, "n_orders_stop_under_3_spreads": S.n_tight})
            base_out.setdefault(sl, {})[mode] = base
            for v in todo:
                tv, info, fired = S.variant(v)
                res.setdefault(v["id"], {})[mode] = summarise(tv, S.tb, info, fired)
            print(f"{sl:28s} {mode:6s} base n {base['common']['n']:4d} exp {base['common']['exp_R']:+.4f} "
                  f"tot {base['common']['total_R']:+8.2f} | tight stops {S.n_tight} | {len(todo)} variants "
                  f"[{time.time() - t0:.0f}s]", flush=True)
            del S, fr
        with open(path, "a") as f:
            for v in todo:
                row = {"id": v["id"], "sleeve": sl, "rule": v["rule"], "checkpoint": v["checkpoint"],
                       "params": {k: v[k] for k in ("x", "y") if k in v}, "grid": v["grid"],
                       "fp": res[v["id"]]["fp"], "stress": res[v["id"]]["stress"],
                       "base_fp_common": {k: base_out[sl]["fp"]["common"][k] for k in ("n", "exp_R", "total_R", "avg_loss_R")},
                       "base_stress_common": {k: base_out[sl]["stress"]["common"][k] for k in ("n", "exp_R", "total_R", "avg_loss_R")}}
                f.write(C.jline(row) + "\n")
    C.jdump(base_out, os.path.join(C.RES, "variants_baseline.json"))
    print(f"done [{time.time() - t_start:.0f}s]")


if __name__ == "__main__":
    main()
