"""Criterion (f): truncation tests of every variant that passes (a)-(e).  IN SAMPLE ONLY.

For each (sleeve, family) with at least one candidate, up to N trades of the candidates (common window, FP costs) are
drawn at random (seed 7).  For each drawn trade:

1. DECISION TEST.  The frame is cut right after the decision bar and the variant's decision fields are recomputed
   with the sleeve's own make_orders + this lens' transformation, then compared with the full-frame values.
   * S / T / B (decided when the order is filled): market orders -> the frame ends with the signal bar, followed by
     one provisional bar stamped like the fill bar whose bid/ask O=H=L=C equal the fill bar's real bid/ask OPEN (the
     fill price is the only thing taken from it), then two flat provisional bars (the rules emit an order only once
     its entry bar plus one or two more bars exist, see the brain maps).  Stop entries (donch4h_stop, orb) -> the
     frame ends with the touch (fill) bar, then three flat provisional bars.
     Compared: stop distance (S, T), trailing distance and scheduled time cap (T), break-even distance (B).
   * H (decided at the close of the bar before the clock exit bar X): the frame ends with bar X-1, then three flat
     provisional bars at X-1's close.  Compared: 'still open and ahead by >= 1 R0 at that close' and the scheduled
     extension time.
2. PATH TEST.  The full-frame variant order is simulated alone on frames cut at 3 random bars inside the trade (plus
   its exit bar): when the full-frame exit is at or before the cut, the exit must be identical (bar, price, reason);
   otherwise the trade must still be open at the end of the cut frame.
The nq_btc_follow leader (us100) is cut at the same last real bar as bitcoin.
Output: results/r2/autopsy/payoff/causality.json
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402
import variants as V  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

N_TRADES = 10
STOP_ENTRY = {"donch4h_stop", "orb_asia_2d_buf10"}


def prov(frame, base_bar_vals, t0, k):
    """k flat provisional bars stamped t0, t0+1min, ... with bid/ask O=H=L=C given by base_bar_vals (bid, ask)."""
    b, a = base_bar_vals
    idx = pd.DatetimeIndex([t0 + pd.Timedelta(minutes=j) for j in range(k)]).as_unit(frame.index.unit)
    d = {c: np.full(k, b) for c in ("bo", "bh", "bl", "bc")}
    d.update({c: np.full(k, a) for c in ("ao", "ah", "al", "ac")})
    return pd.DataFrame(d, index=idx)[list(frame.columns)].rename_axis(frame.index.name)


def cut_frame_market(m1, fb):
    """Frame ending with the signal bar, + provisional fill bar (real bid/ask open only) + 2 flat bars."""
    head = m1.iloc[:fb]
    t_fb = m1.index[fb]
    p1 = prov(m1, (m1["bo"].iat[fb], m1["ao"].iat[fb]), t_fb, 3)
    return pd.concat([head, p1])


def cut_frame_after(m1, last):
    """Frame ending with bar `last` (included), + 3 flat provisional bars at its close."""
    head = m1.iloc[:last + 1]
    p1 = prov(m1, (m1["bc"].iat[last], m1["ac"].iat[last]), m1.index[last] + pd.Timedelta(minutes=1), 3)
    return pd.concat([head, p1])


def set_leader_cut(us_mid, t_last):
    if us_mid is not None:
        C.set_leader_is(us_mid[us_mid.index <= t_last])


def find(Oc, O, oid):
    """Row of the cut-frame orders matching the full-frame order (same entry time, side)."""
    r = O.loc[O["oid"] == oid].iloc[0]
    return r


def transform(fam, spec, O, I, name, ahead=None):
    if fam == "S":
        return V.S(O, I, name, spec["k"])[0]
    if fam == "T":
        return V.T(O, I, name, spec["m"])[0]
    if fam == "B":
        return V.B(O, I, name, spec["b"])[0]
    return V.H(O, I, name, spec["j"], ahead)[0]


def test_group(name, sym, m1, fam, specs, trades, us_mid, rng):
    _, mo, params = C.registry()[(name, sym)]
    if us_mid is not None:
        C.set_leader_is(us_mid)                    # full in-sample leader for the full-frame orders
    full_O = C.build_orders(name, sym, m1)
    full_I = V.info(name, sym, m1, full_O, False, params, mo)
    ahead_full = V.hold_decision(m1, full_O, full_I, sym, False) if fam == "H" else None
    full_vo = {s["id"]: transform(fam, s, full_O, full_I, name, ahead_full) for s in specs}
    pool = trades[trades["variant"].isin([s["id"] for s in specs])]
    oids = pool["oid"].drop_duplicates().to_numpy()
    if fam == "H":   # test the decision on orders that reached their clock exit (extended or not)
        reached = np.flatnonzero(full_I["clock"].to_numpy())
        oids = np.intersect1d(oids, full_O["oid"].to_numpy()[reached])
        ext = np.intersect1d(oids, full_O["oid"].to_numpy()[ahead_full])
        pick = np.r_[rng.choice(ext, min(len(ext), N_TRADES // 2), replace=False),
                     rng.choice(np.setdiff1d(oids, ext), min(len(np.setdiff1d(oids, ext)), N_TRADES - N_TRADES // 2),
                                replace=False)]
    else:
        pick = rng.choice(oids, min(len(oids), N_TRADES), replace=False)
    out = {"decision_tests": 0, "decision_mismatches": 0, "path_tests": 0, "path_mismatches": 0, "details": []}
    fb_all, _ = C.fills(m1, full_O, sym, False)
    for oid in pick:
        row = full_O.loc[full_O["oid"] == oid].iloc[0]
        k = int(np.flatnonzero(full_O["oid"].to_numpy() == oid)[0])
        fb = int(fb_all[k])
        if fam == "H":
            X = int(row["exit_i"])
            cut = cut_frame_after(m1, X - 1)
            set_leader_cut(us_mid, m1.index[X - 1])
        elif name in STOP_ENTRY:
            cut = cut_frame_after(m1, fb)
            set_leader_cut(us_mid, m1.index[fb])
        else:
            cut = cut_frame_market(m1, fb)
            set_leader_cut(us_mid, m1.index[fb - 1])
        Oc = C.build_orders(name, sym, cut)
        et = m1.index[int(row["entry_i"])]
        ent_c = cut.index[np.clip(Oc["entry_i"].to_numpy(), 0, len(cut) - 1)]
        mt = np.flatnonzero((ent_c == et) & (Oc["side"].to_numpy() == row["side"]))
        det = {"oid": int(oid), "entry_time": str(et), "cut_last_real_bar": str(cut.index[len(cut) - 4]),
               "found": bool(len(mt))}
        out["decision_tests"] += 1
        if not len(mt):
            out["decision_mismatches"] += 1
            out["details"].append(det)
            continue
        Ic = V.info(name, sym, cut, Oc, False, params, mo)
        ahead_c = V.hold_decision(cut, Oc, Ic, sym, False) if fam == "H" else None
        if fam == "H":
            # on the cut frame the clock exit bar does not exist yet: the decision is 'open and ahead at X-1's close',
            # recomputed directly from the cut frame's real bars
            j = mt[0]
            o1 = Oc.iloc[[j]].copy()
            o1["exit_i"] = len(cut) + 10                          # no time exit inside the cut frame
            t1 = C.sim(cut, o1, sym, False, no_overlap=False)
            open_at_end = len(t1) == 1 and t1["reason"].iat[0] == "eod"
            s = int(row["side"])
            mark = cut["bc"].iat[len(cut) - 4] if s > 0 else cut["ac"].iat[len(cut) - 4]
            dec_c = bool(open_at_end and s * (mark - t1["entry"].iat[0]) >= t1["risk"].iat[0]) if len(t1) else False
            dec_f = bool(ahead_full[k])
            same_t = all(pd.Timestamp(Ic[f"ext{jj}_t"].iat[j]) == pd.Timestamp(full_I[f"ext{jj}_t"].iat[k]) for jj in (1, 2))
            ok = (dec_c == dec_f) and same_t
            det.update({"decision_full": dec_f, "decision_cut": dec_c, "ext_times_equal": same_t})
        else:
            j = mt[0]
            ok = True
            for s in specs:
                vc = transform(fam, s, Oc, Ic, name)
                vf = full_vo[s["id"]]
                for col in ("stop_dist", "trail", "be"):
                    a, b = vc[col].iat[j] if col in vc else np.nan, vf[col].iat[k] if col in vf else np.nan
                    if not ((np.isnan(a) and np.isnan(b)) or abs(a - b) <= 1e-9 * max(1.0, abs(b))):
                        ok = False
                        det[f"{s['id']}_{col}"] = [float(a), float(b)]
                if fam == "T":
                    tc, tf = Ic["cap_t"].iat[j], full_I["cap_t"].iat[k]
                    if not (pd.isna(tc) and pd.isna(tf)) and pd.Timestamp(tc) != pd.Timestamp(tf):
                        ok = False
                        det[f"{s['id']}_cap_t"] = [str(tc), str(tf)]
        det["decision_identical"] = bool(ok)
        out["decision_mismatches"] += int(not ok)
        # path test on the full-frame variant orders
        for s in specs:
            vo = full_vo[s["id"]].iloc[[k]]
            tf = C.sim(m1, vo, sym, False, no_overlap=False)
            if not len(tf):
                continue
            xb = int(C.exit_bar(m1, tf)[0])
            lo, hi = fb, min(xb + 5, len(m1) - 2)
            cuts = sorted(set([int(c) for c in rng.integers(lo, hi + 1, 3)] + [xb]))
            for c in cuts:
                tc = C.sim(m1.iloc[:c + 1], vo, sym, False, no_overlap=False)
                out["path_tests"] += 1
                if xb <= c:
                    good = (len(tc) == 1 and tc["exit_time"].iat[0] == tf["exit_time"].iat[0]
                            and tc["reason"].iat[0] == tf["reason"].iat[0] and abs(tc["exit"].iat[0] - tf["exit"].iat[0]) < 1e-9)
                else:
                    good = len(tc) == 1 and (tc["reason"].iat[0] == "eod" or int(C.exit_bar(m1.iloc[:c + 1], tc)[0]) == c)
                    # a time exit exactly at the last bar of the cut is the scheduled exit only if it is the full one
                    if good and tc["reason"].iat[0] != "eod":
                        good = int(vo["exit_i"].iat[0]) <= c
                if not good:
                    out["path_mismatches"] += 1
                    det.setdefault("path_fail", []).append([s["id"], c])
        out["details"].append(det)
    return out


def main():
    ev = json.load(open(os.path.join(C.OUT, "evaluation.json")))
    groups = {}
    for key, sl in ev["sleeves"].items():
        for vid, v in sl["variants"].items():
            if v["criteria"].get("candidate_a_to_e"):
                groups.setdefault(key, {}).setdefault(v["spec"]["family"], []).append(v["spec"])
    res = {}
    by_sym = {}
    for key in groups:
        by_sym.setdefault(key.split(":")[1], []).append(key)
    rng = np.random.default_rng(7)
    for sym, keys in by_sym.items():
        m1 = C.load_is(sym)
        us_mid = None
        if sym == "btcusd":
            us = C.load_is("us100")
            us_mid = ((us["bc"] + us["ac"]) / 2).rename("mid")
            del us
        for key in keys:
            name = key.split(":")[0]
            tr = pd.read_parquet(os.path.join(C.OUT, f"trades_{name}__{sym}.parquet"))
            tr = C.window(tr[tr["mode"] == "fp"], "common")
            for fam, specs in groups[key].items():
                t0 = time.time()
                r = test_group(name, sym, m1, fam, specs, tr, us_mid if name == "nq_btc_follow" else None, rng)
                r["variants"] = [s["id"] for s in specs]
                r["passed"] = r["decision_mismatches"] == 0 and r["path_mismatches"] == 0
                res[f"{key}|{fam}"] = r
                print(f"{key:28s} {fam} {r['variants']}: decision {r['decision_tests'] - r['decision_mismatches']}/"
                      f"{r['decision_tests']} path {r['path_tests'] - r['path_mismatches']}/{r['path_tests']} "
                      f"-> {r['passed']} [{time.time() - t0:.0f}s]", flush=True)
            if sym == "btcusd":
                C.set_leader_is(us_mid)
        del m1
    json.dump(res, open(os.path.join(C.OUT, "causality.json"), "w"), indent=1, default=str)


if __name__ == "__main__":
    main()
