"""Truncation test of the two finalists on us100 (IS frame): 26 targeted cuts around the decision minutes + 40 random."""
from causality_test import *     # noqa
cfg = {"noise30": dict(rule="noise"), "ocm4": dict(rule="ocm", n=4, stop="atr", k=0.3, size_min=1.0)}

def run2(sym="us100", n_cuts=40, seed=11):
    m1 = r2.load(sym, end="2022-01-01")
    full = {k: S.make_orders(m1, **p) for k, p in cfg.items()}
    rng = np.random.default_rng(seed)
    idx = m1.index
    ny = idx.tz_convert("America/New_York")
    mod = np.asarray(ny.hour * 60 + ny.minute)
    lo = int(idx.searchsorted(pd.Timestamp("2014-03-01", tz="UTC")))
    cuts = []
    for target in (569, 570, 571, 572, 573, 574, 575, 599, 600, 601, 629, 630, 631, 659, 660, 719, 720, 899, 900, 929, 930, 931, 954, 955, 956, 959):
        w = np.flatnonzero(mod[lo:] == target) + lo
        cuts.append(int(rng.choice(w)) + int(rng.integers(0, 2)))
    cuts += [int(x) for x in rng.integers(lo, len(m1) - 10, n_cuts)]
    problems, checked, compared_orders = [], 0, 0
    for c in cuts:
        mk = m1.iloc[:c]
        for k, p in cfg.items():
            oc = S.make_orders(mk, **p)
            err = compare(full[k], oc, c, f"{k}@cut={idx[c - 1]}")
            checked += 1
            compared_orders += int((oc.entry_i < c - 1).sum())
            if err:
                problems.append(err)
    return {"sym": sym, "cuts": len(cuts), "comparisons": checked, "orders_compared": compared_orders,
            "orders_full": {k: int(len(v)) for k, v in full.items()}, "problems": problems, "pass": not problems}

out = run2()
print(json.dumps(out, indent=1))
json.dump(out, open(os.path.join(RES, "causality_test.json"), "w"), indent=1)
