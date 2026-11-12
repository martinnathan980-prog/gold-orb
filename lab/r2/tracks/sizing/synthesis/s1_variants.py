"""Step 1: the declared variants S00-S05 (declared.json), FP and costs x1.5. IN SAMPLE ONLY.

S00 reference (= the account with the kept changes of Addendum I: none); S01 V05 as written by the conviction lens
(my implementation, information); S02 V05 with a strict training cut; S03 K1 (Addendum H); S04 K1 + V05;
S05 P2 = K1 + the new sleeves K2, K3 (Addendum H). Plain sum of the chains; equal weekly swing over the 157
out-of-fold weeks. Writes out/s1_variants.json, out/fits.json, the re-simulated chains, and trials.jsonl.

    NUMBA_CACHE_DIR=/tmp/synthI_numba PYTHONDONTWRITEBYTECODE=1 python3 s1_variants.py
"""
import gc
import os
import sys
import time

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import sy_common as C  # noqa: E402

DESC = ["vol", "al1", "al5", "al20", "room", "cushion", "trig", "riskbp", "rel", "prev", "oth24"]
ZERO_BAR = 0.02
MIN_TRAIN = 60


# ------------------------------------------------------------------------------------------- V05 (my implementation)
def tables(mode):
    """{k: (signals, training table)}: the training table is the sleeve's baseline chain (mine, checked equal to the
    context lens's) with the signal's descriptors."""
    T = {}
    for k in C.CRYPTO_BRK:
        s = C.load_ctx_signals(k, mode)
        ch = C.load_trades(f"ref__{k}__{mode}")
        tr = s.set_index("oid").loc[ch.oid.to_numpy()].reset_index()
        tr["exit_ns"] = C.ns_of(ch.exit_time)
        tr["R"] = ch.R.to_numpy(float)
        assert np.allclose(tr.R.to_numpy(), tr.chain_R.to_numpy(), rtol=0, atol=1e-12)
        T[k] = (s, tr)
    return T


def standardise(X):
    mu = np.nanmean(X, axis=0)
    sd = np.nanstd(X, axis=0)
    ok = np.isfinite(mu) & np.isfinite(sd) & (sd > 0)
    return np.where(ok, mu, 0.0), np.where(ok, sd, 1.0), ok


def zmat(X, mu, sd, ok):
    Z = np.clip((X - mu) / sd, -4.0, 4.0)
    Z = np.where(np.isfinite(Z), Z, 0.0)
    Z[:, ~ok] = 0.0
    return Z


def fit_v05(T, y, strict=False, alpha_factor=1.0, q=1 / 3, n_keep=6):
    cut = C.train_cut_ns(y)
    parts = {}
    for k in C.CRYPTO_BRK:
        tr = T[k][1]
        e = tr.exit_ns.to_numpy(np.int64)
        t = tr[(e < cut) if strict else (e <= cut)]
        X = t[DESC].to_numpy(float)
        mu, sd, ok = standardise(X)
        Z = zmat(X, mu, sd, ok)
        R = t.R.to_numpy(float)
        parts[k] = {"Z": Z, "yy": np.clip(R, -2.0, 4.0), "R": R, "mu": mu, "sd": sd, "ok": ok, "n": len(t)}
    Zc = np.vstack([p["Z"] - p["Z"].mean(axis=0) for p in parts.values()])
    yc = np.concatenate([p["yy"] - p["yy"].mean() for p in parts.values()])
    n = len(yc)
    if n < MIN_TRAIN:
        return None
    sz = Zc.std(axis=0)
    sy = yc.std()
    corr = np.where(sz > 0, (Zc * yc[:, None]).mean(axis=0) / np.where(sz > 0, sz, 1.0) / sy, 0.0)
    order = sorted(range(len(DESC)), key=lambda j: (-abs(corr[j]), DESC[j]))
    keep = [j for j in order if sz[j] > 0][:n_keep]
    A = Zc[:, keep]
    beta = np.linalg.solve(A.T @ A + alpha_factor * n * np.eye(len(keep)), A.T @ yc)
    sc = {k: p["Z"][:, keep] @ beta for k, p in parts.items()}
    b_lo, b_hi = np.quantile(np.concatenate(list(sc.values())), [q, 1 - q])
    m_lo = {k: float(parts[k]["R"][sc[k] <= b_lo].mean()) if (sc[k] <= b_lo).any() else float("nan") for k in parts}
    return {"year": y, "strict": strict, "n_train": int(n), "n_by_sleeve": {k: p["n"] for k, p in parts.items()},
            "keep": keep, "descriptors": [DESC[j] for j in keep], "beta": beta.tolist(),
            "coef": {DESC[j]: round(float(b), 4) for j, b in zip(keep, beta)},
            "corr": {DESC[j]: round(float(corr[j]), 4) for j in range(len(DESC))},
            "b_lo": float(b_lo), "b_hi": float(b_hi), "m_lo": m_lo,
            "zero_on": {k: bool(not (m_lo[k] > ZERO_BAR)) for k in parts},
            "stand": {k: (p["mu"].tolist(), p["sd"].tolist(), p["ok"].tolist()) for k, p in parts.items()}}


def stake_v05(fit, k, X):
    mu, sd, ok = (np.asarray(v) for v in fit["stand"][k])
    sc = zmat(X, mu, sd, ok.astype(bool))[:, fit["keep"]] @ np.asarray(fit["beta"])
    st = np.ones(len(sc))
    if fit["b_lo"] < fit["b_hi"]:
        st[sc <= fit["b_lo"]] = 0.5 if fit["m_lo"][k] > ZERO_BAR else 0.0
        st[sc >= fit["b_hi"]] = 1.5
    return st, sc


def v05_stakes(T, strict):
    """{k: stake per signal (aligned with the signal table)}, fits by year"""
    stakes = {k: np.ones(len(T[k][0])) for k in C.CRYPTO_BRK}
    fits = {}
    for y in C.OOF_YEARS:
        f = fit_v05(T, y, strict)
        fits[y] = f
        for k in C.CRYPTO_BRK:
            s = T[k][0]
            m = s.year.to_numpy() == y
            stakes[k][m], _ = stake_v05(f, k, s.loc[m, DESC].to_numpy(float))
    return stakes, fits


# ------------------------------------------------------------------------------------------- K1 (Addendum H)
def k1_fit(x, y, q=1 / 3):
    ok = np.isfinite(x)
    x, y = x[ok], y[ok]
    q_lo, q_hi = np.quantile(x, [q, 1 - q])
    lo, hi = x <= q_lo, x >= q_hi
    e_lo = float(y[lo].mean()) if lo.any() else np.nan
    e_hi = float(y[hi].mean()) if hi.any() else np.nan
    side = None
    if np.nanmin([e_lo, e_hi]) < 0:
        side = "lo" if e_lo < e_hi else "hi"
    return {"q_lo": float(q_lo), "q_hi": float(q_hi), "E_lo": e_lo, "E_hi": e_hi, "skip": side, "n_train": int(len(x))}


def k1_skips(mode):
    s = pd.read_parquet(os.path.join(C.OUT, f"k1sig__brk72_24h_wd__ethusd__{mode}.parquet"),
                        filters=[("t_dec", "<", C.IS_END_NS)])
    use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()
    td = s.t_dec.to_numpy(np.int64)
    first = td.min()
    folds, skip = {}, np.zeros(len(s), bool)
    x = s.riskbp.to_numpy()
    for y in range(2013, 2022):
        if first > int(pd.Timestamp(f"{y - 1}-01-31", tz="UTC").value):
            continue
        tr = use & (td < C.train_cut_ns(y))
        if tr.sum() < 100:
            continue
        f = k1_fit(x[tr], s.label.to_numpy()[tr])
        te = (s.year == y).to_numpy()
        with np.errstate(invalid="ignore"):
            m = np.zeros(len(s), bool) if f["skip"] is None else ((x <= f["q_lo"]) if f["skip"] == "lo" else (x >= f["q_hi"]))
        m &= te
        skip |= m
        f.update(n_test=int(te.sum()), n_skipped=int(m.sum()))
        folds[y] = f
    return set(s.oid[skip].tolist()), folds


# ------------------------------------------------------------------------------------------- books
def book_of(chains, stakes):
    """chains: {key: trades}; stakes: {key: {oid: stake}} (missing = 1)"""
    rows = []
    for k, t in chains.items():
        st = stakes.get(k)
        s = np.ones(len(t)) if st is None else np.array([st[o] for o in t.oid.to_numpy()], float)
        rows.append(C.book_rows(k, t, s))
    return pd.concat(rows, ignore_index=True)


def per_sleeve_oof(book, ref_book, keys):
    out = {}
    for k in keys:
        a = book[(book.sleeve == k) & book.week.isin(C.OOF_W)]
        r = ref_book[(ref_book.sleeve == k) & ref_book.week.isin(C.OOF_W)]
        taken = a.stake > 0
        out[k] = {"trades": int(taken.sum()), "trades_ref": int(len(r)), "stakes": round(float(a.stake.sum()), 1),
                  "R_at_stake_unscaled": round(float(a.pnl.sum()), 2), "R_ref": round(float(r.pnl.sum()), 2),
                  "R_per_stake": round(float(a.pnl.sum() / a.stake.sum()), 4) if a.stake.sum() > 0 else None,
                  "stake_counts": {str(v): int((a.stake == v).sum()) for v in sorted(a.stake.unique())}}
    return out


def trade_diff(base, var):
    b, v = set(base.oid.tolist()), set(var.oid.tolist())
    rem, new = b - v, v - b
    return {"baseline_trades_removed": len(rem), "R_removed": round(float(base[base.oid.isin(rem)].R.sum()), 3),
            "new_trades": len(new), "R_new": round(float(var[var.oid.isin(new)].R.sum()), 3)}


def main():
    t_start = time.time()
    res = {"variants": {}, "fits": {}, "k1_folds": {}}
    for mode in C.MODES:
        T = tables(mode)
        st01, fit01 = v05_stakes(T, strict=False)
        st02, fit02 = v05_stakes(T, strict=True)
        k1_skip, k1_folds = k1_skips(mode)
        res["fits"][mode] = {"S01_V05": fit01, "S02_V05_strict": fit02}
        res["k1_folds"][mode] = k1_folds
        # skip sets per variant and sleeve (signals not sent); stakes per signal
        zero = {}
        for vid, st in (("S01_V05", st01), ("S02_V05_strict", st02)):
            zero[vid] = {k: set(np.flatnonzero(st[k] == 0).tolist()) for k in C.CRYPTO_BRK}
        zero["S03_K1"] = {"brk72_24h_wd__ethusd": set(k1_skip)}
        zero["S04_K1_V05"] = {k: set(z) for k, z in zero["S01_V05"].items()}
        zero["S04_K1_V05"]["brk72_24h_wd__ethusd"] |= set(k1_skip)
        stakes = {vid: {} for vid in zero}
        for vid, st in (("S01_V05", st01), ("S02_V05_strict", st02), ("S04_K1_V05", st01)):
            for k in C.CRYPTO_BRK:
                stakes[vid][k] = dict(enumerate(st[k].tolist()))
        # reference chains
        ref = {k: C.load_trades(f"ref__{k}__{mode}") for k in C.KEYS}
        new = {k: C.load_trades(f"ref__{k}__{mode}") for k in C.NEW_KEYS}
        # re-simulate the sleeves whose skip set is not empty
        realised = {vid: {} for vid in zero}
        for sym in ("btcusd", "ethusd"):
            todo = [(vid, k) for vid, d in zero.items() for k, z in d.items() if z and C.split_key(k)[1] == sym]
            if not todo:
                continue
            m1 = C.load_is(sym)
            mk = C.mode_frame(m1, mode)
            for k in sorted({k for _, k in todo}):
                name = C.split_key(k)[0]
                o = C.build_orders(name, mk)
                s_ctx = T[k][0]
                assert len(o) == len(s_ctx) and (o.side.to_numpy() == s_ctx.side.to_numpy()).all(), k
                b = C.chain(mk, o, sym, mode)
                assert (b.oid.to_numpy() == ref[k].oid.to_numpy()).all() and np.allclose(b.R, ref[k].R, rtol=0, atol=1e-12)
                for vid in [v for v, kk in todo if kk == k]:
                    t = C.chain(mk, o, sym, mode, exclude=zero[vid][k])
                    realised[vid][k] = t
                    C.save_trades(t, f"var__{vid}__{k}__{mode}")
            del mk, m1
            gc.collect()
        ref_book = book_of(ref, {})
        books = {"S00_R0": ref_book}
        for vid in ("S01_V05", "S02_V05_strict", "S03_K1", "S04_K1_V05"):
            ch = {k: realised[vid].get(k, ref[k]) for k in C.KEYS}
            books[vid] = book_of(ch, stakes[vid])
        ch5 = {k: realised["S03_K1"].get(k, ref[k]) for k in C.KEYS}
        ch5.update(new)
        books["S05_P2"] = book_of(ch5, {})
        for vid, bk in books.items():
            r = {"vs_S00": C.compare(bk, ref_book)}
            r["unscaled_pooled"] = C.measures(bk, C.OOF_W, 1.0, 36)
            if vid == "S04_K1_V05":
                r["vs_S03_K1"] = C.compare(bk, books["S03_K1"])
            r["per_sleeve_oof"] = per_sleeve_oof(bk, ref_book, C.KEYS + (C.NEW_KEYS if vid == "S05_P2" else []))
            r["trade_changes"] = {k: trade_diff(ref[k], realised[vid][k]) for k in realised.get(vid, {})}
            res["variants"].setdefault(vid, {})[mode] = r
            p = r["vs_S00"]["pooled"]
            line = {"synthesis": "addendum_I_lead", "variant": vid, "mode": mode, "account": "plain sum",
                    "window": "157 server weeks, Thursday in 2019-2021", "scale_k": r["vs_S00"]["scale_k"],
                    "sharpe": p["sharpe"], "sharpe_ref": r["vs_S00"]["pooled_ref"]["sharpe"],
                    "ratio_vs_ref": p["sharpe_ratio_vs_ref"], "years_up": r["vs_S00"]["years_up"],
                    "by_year_ratio": {y: v["variant"]["sharpe_ratio_vs_ref"] for y, v in r["vs_S00"]["by_year"].items()},
                    "trades": p["trades"], "total_R_equal_swing": p["total_R"], "losing_weeks_pct": p["losing_weeks_pct"],
                    "worst_week": p["worst_week"], "longest_losing_weeks": p["longest_losing_weeks"],
                    "losing_trades_per_month": p["losing_trades_per_month"], "role": "information" if vid != "S00_R0" else "reference"}
            if vid == "S04_K1_V05":
                line["ratio_vs_S03_K1"] = r["vs_S03_K1"]["pooled"]["sharpe_ratio_vs_ref"]
                line["years_up_vs_S03_K1"] = r["vs_S03_K1"]["years_up"]
            C.append_trial(line)
            print(f"{mode:6s} {vid:16s} k {r['vs_S00']['scale_k']:.4f} Sharpe {p['sharpe']:.4f} ratio "
                  f"{p['sharpe_ratio_vs_ref']:.4f} years up {r['vs_S00']['years_up']} by year "
                  f"{line['by_year_ratio']} trades {p['trades']} R {p['total_R']}"
                  + (f" | vs K1 {line['ratio_vs_S03_K1']:.4f} up {line['years_up_vs_S03_K1']}" if vid == "S04_K1_V05" else ""),
                  flush=True)
        del T
        gc.collect()
    res["sec"] = round(time.time() - t_start, 1)
    C.dump(res, os.path.join(C.OUT, "s1_variants.json"))


if __name__ == "__main__":
    main()
