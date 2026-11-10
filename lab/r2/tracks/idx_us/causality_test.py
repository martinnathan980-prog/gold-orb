"""Truncation (causality) test: orders built on a frame cut at arbitrary minutes must equal the orders built
on the longer frame, for everything decided before the cut.

    python3 causality_test.py [sym] [n_cuts]

Compared per order with entry_i < cut - 1: entry_i, side, etype, level, stop, stop_dist, target_dist; exit_i is
compared when the long-frame exit lies at least 45 bars before the cut (a time exit scheduled after the cut
cannot be resolved on the cut frame, by construction)."""
import json
import sys

from harness import *          # noqa: F401,F403

CONFIGS = {
    "ocm_candle": dict(rule="ocm"),
    "ocm_atr": dict(rule="ocm", stop="atr", k=0.1),
    "ocm_size": dict(rule="ocm", size_min=1.0),
    "orb15": dict(rule="orb"),
    "noise": dict(rule="noise"),
    "last": dict(rule="last"),
}


def compare(full, cutf, c, name):
    # an order whose entry bar is the very last bar of the cut frame cannot get a time exit after its entry there
    # (the builders drop it); it is excluded on both sides
    a = full[full.entry_i < c - 1].reset_index(drop=True)
    b = cutf[cutf.entry_i < c - 1].reset_index(drop=True)
    if len(a) != len(b):
        return f"{name}: order count differs ({len(a)} on long frame vs {len(b)} on cut frame)"
    for col in ("entry_i", "side", "etype", "level", "stop", "stop_dist", "target_dist"):
        x, y = a[col].to_numpy(float), b[col].to_numpy(float)
        bad = ~(np.isclose(x, y, rtol=1e-12, atol=1e-9) | (np.isnan(x) & np.isnan(y)))
        if bad.any():
            return f"{name}: column {col} differs on {int(bad.sum())} orders (first at row {int(np.flatnonzero(bad)[0])})"
    early = a.exit_i.to_numpy() < c - 45
    if (a.exit_i.to_numpy()[early] != b.exit_i.to_numpy()[early]).any():
        return f"{name}: exit_i differs for exits resolved before the cut"
    return None


def run(sym="us100", n_cuts=14, configs=None, seed=7, end="2022-01-01"):
    configs = configs or CONFIGS
    m1 = r2.load(sym, end=end)
    full = {k: S.make_orders(m1, **p) for k, p in configs.items()}
    rng = np.random.default_rng(seed)
    idx = m1.index
    ny = idx.tz_convert("America/New_York")
    mod = np.asarray(ny.hour * 60 + ny.minute)
    lo = int(idx.searchsorted(pd.Timestamp("2014-03-01", tz="UTC")))
    cuts = []
    # targeted cuts: just before / after the decision minutes of the rules, on random days
    for target in (574, 575, 576, 584, 585, 586, 599, 600, 601, 629, 630, 631, 929, 930, 931, 954, 955, 956, 958, 959):
        w = np.flatnonzero(mod[lo:] == target) + lo
        cuts.append(int(rng.choice(w)) + int(rng.integers(0, 2)))
    cuts += [int(x) for x in rng.integers(lo, len(m1) - 10, n_cuts)]
    problems, checked = [], 0
    for c in cuts:
        mk = m1.iloc[:c]
        for k, p in configs.items():
            err = compare(full[k], S.make_orders(mk, **p), c, f"{k}@cut={idx[c - 1]}")
            checked += 1
            if err:
                problems.append(err)
    return {"sym": sym, "cuts": len(cuts), "comparisons": checked, "orders_full": {k: int(len(v)) for k, v in full.items()},
            "problems": problems, "pass": not problems}


if __name__ == "__main__":
    sym = sys.argv[1] if len(sys.argv) > 1 else "us100"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 14
    out = run(sym, n)
    print(json.dumps(out, indent=1))
