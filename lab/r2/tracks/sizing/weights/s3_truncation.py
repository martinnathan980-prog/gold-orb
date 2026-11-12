"""Lens `weights`, criterion (e), test T1 (trade level), as declared in declared.json. IN SAMPLE ONLY.

For every declared variant, on U10 and U8_noF1 (fp chains): decision times T = 300 entries of 2019-2021 drawn with
seed 3 + the first decision of each fold year 2019-2021 + up to 50 decisions where the variant's stake differs from
the previous trade of the same sleeve. At each T the book is cut to what is known at T (stakes.cut_book: trades
entered after T removed, trades not closed strictly before T keep their entry but lose exit time, week and R) and
the stakes of EVERY trade entered at or before T are recomputed from that book alone and compared with the full run.
Pass = identical everywhere.

Control (not a variant, no performance computed): a deliberately leaky rule that peeks one day past the decision
("stake 2 if the sleeve's paper mean over [t - 91 d, t + 1 d) is positive") must be caught by the same test.
Output: results/r2/sizing/weights/truncation_T1.json
"""
import json
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402

import common as C  # noqa: E402
import stakes as S  # noqa: E402

N_RANDOM, SEED, N_CHANGES = 300, 3, 50


def leaky(b, keys):
    """control: looks one day into the future (must FAIL the truncation test)"""
    out = np.ones(len(b))
    kk = b.k.to_numpy()
    ti = b.t_in.to_numpy()
    for k in keys:
        idx = np.nonzero(kk == k)[0]
        if not len(idx):
            continue
        s, n = S._trailing(b, k, ti[idx] + S.NS_DAY, 92)
        out[idx[(n > 0) & (s > 0)]] = 2.0
    return out


def points(b, st, rng_seed=SEED):
    oof = np.nonzero(np.isin(b.year_in.to_numpy(), list(C.OOF)))[0]
    rng = np.random.default_rng(rng_seed)
    T = set(b.t_in.to_numpy()[rng.choice(oof, N_RANDOM, replace=False)].tolist())
    for y in C.OOF:
        T.add(int(b.t_in.to_numpy()[b.year_in.to_numpy() == y].min()))
    # decisions where the stake differs from the previous trade of the same sleeve
    ch = []
    kk = b.k.to_numpy()
    for k in np.unique(kk):
        idx = np.nonzero((kk == k) & np.isin(b.year_in.to_numpy(), list(C.OOF)))[0]
        d = idx[1:][st[idx[1:]] != st[idx[:-1]]]
        ch.extend(d.tolist())
    if ch:
        rng2 = np.random.default_rng(rng_seed + 1)
        pick = rng2.choice(np.array(ch), min(N_CHANGES, len(ch)), replace=False)
        T.update(b.t_in.to_numpy()[pick].tolist())
    return sorted(T), len(ch)


def test(b, keys, fn, T_list):
    full = fn(b)
    bad_points, bad_decisions, compared = 0, 0, 0
    first_bad = None
    for T in T_list:
        c = S.cut_book(b, T)
        sc = fn(c)
        n = len(c)
        same = full[:n] == sc
        compared += n
        if not same.all():
            bad_points += 1
            bad_decisions += int((~same).sum())
            if first_bad is None:
                first_bad = {"T": str(np.datetime64(int(T), "ns")), "n_differ": int((~same).sum())}
    return {"points": len(T_list), "decisions_compared": int(compared), "points_with_a_difference": bad_points,
            "decisions_differing": bad_decisions, "first_bad": first_bad, "pass": bad_points == 0}


def main():
    decl = json.load(open(C.DECLARED))
    full = S.book_frame(C.load_book("fp"))
    res = {"what": __doc__.split("\n\n")[1], "variants": {}}
    t0 = time.time()
    for u in ("U10", "U8_noF1"):
        keys = C.UNIVERSES[u]
        b = full[full.k.isin(keys)].reset_index(drop=True)
        for v in decl["variants"]:
            fn = (lambda bb, v=v, keys=keys: S.stakes(bb, keys, v))
            st = fn(b)
            T_list, n_changes = points(b, st)
            r = test(b, keys, fn, T_list)
            r["stake_changes_available"] = n_changes
            res["variants"].setdefault(v["id"], {})[u] = r
            print(f"{u:8s} {v['id']:5s} points {r['points']} compared {r['decisions_compared']} "
                  f"bad points {r['points_with_a_difference']} {'PASS' if r['pass'] else 'FAIL'} [{time.time() - t0:.0f}s]", flush=True)
        st = leaky(b, keys)
        T_list, _ = points(b, st)
        res.setdefault("leaky_control", {})[u] = test(b, keys, lambda bb, keys=keys: leaky(bb, keys), T_list)
        print(u, "leaky control:", res["leaky_control"][u], flush=True)
    res["all_variants_pass"] = bool(all(r[u]["pass"] for r in res["variants"].values() for u in r))
    res["control_caught"] = bool(all(not r["pass"] for r in res["leaky_control"].values()))
    C.jdump(res, os.path.join(C.OUT, "truncation_T1.json"))
    print("T1:", "ALL PASS" if res["all_variants_pass"] else "SOME FAIL", "| control caught:", res["control_caught"])


if __name__ == "__main__":
    main()
