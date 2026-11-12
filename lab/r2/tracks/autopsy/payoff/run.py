"""Runs the declared variants of the payoff lens, one symbol per call.  IN SAMPLE ONLY.

    python3 run.py check <sym>     plumbing checks only (identity transforms reproduce the reference; no variant)
    python3 run.py run <sym>       every declared variant of the sleeves of <sym>; one line per variant appended to
                                   results/r2/autopsy/payoff/trials.jsonl; trades in trades_<name>__<sym>.parquet;
                                   reference trades with excursions in reference_<name>__<sym>.parquet
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

BY_SYM = {"us100": ["noise30", "ocm4"], "btcusd": ["brk72_24h_wd", "F1_brk_ridge_filter", "nq_btc_follow"],
          "ethusd": ["brk72_24h_wd", "F1_brk_ridge_filter"], "xauusd": ["GOLD_FRI_PM", "donch4h_stop", "orb_asia_2d_buf10"]}
TRIALS = os.path.join(C.OUT, "trials.jsonl")
KEEP_COLS = ["oid", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "swap", "pnl", "risk", "R",
             "hold_min", "mfe", "mae"]


def load_sym(sym):
    m1, m1s = C.frames(sym)
    if sym == "btcusd":
        us = C.load_is("us100")
        C.set_leader_is(((us["bc"] + us["ac"]) / 2).rename("mid"))
        del us
    return m1, m1s


def evaluate(frame, t, sym):
    t = C.finalize(frame, t, sym)
    out = {"censored": t.attrs["censored"]}
    for w in ("common", "early", "whole"):
        out[w] = C.stats(C.window(t, w))
    out["by_year"] = C.by_year(C.window(t, "common"))
    out["by_year_early"] = C.by_year(C.window(t, "early"))
    return out, t


def witness(tref, tv):
    """Reference trades of the common window against their own variant trade (joined on the order id)."""
    a = C.window(tref, "common").set_index("oid")
    b = tv.set_index("oid")
    j = a.join(b[["reason", "exit_time", "R"]], rsuffix="_v", how="left")
    taken = j["R_v"].notna()
    stopped_v = j["reason_v"].isin(["stop", "gap", "trail"])
    earlier = stopped_v & (j["exit_time_v"] < j["exit_time"])
    ref_stopped = j["reason"].isin(["stop", "gap", "trail"])
    later = taken & ref_stopped & ~(stopped_v & (j["exit_time_v"] <= j["exit_time"]))
    g = earlier & (j["R"] > 0)
    lo = earlier & (j["R"] <= 0)
    return {"ref_trades": int(len(j)), "not_taken": int((~taken).sum()),
            "stopped_earlier_by_tighter_stop": int(earlier.sum()),
            "of_which_reference_ended_in_gain": int(g.sum()),
            "reference_R_given_up_on_those": round(float(j.loc[g, "R"].sum()), 2),
            "of_which_reference_ended_in_loss": int(lo.sum()),
            "reference_R_on_those_losers": round(float(j.loc[lo, "R"].sum()), 2),
            "variant_R_on_all_stopped_earlier": round(float(j.loc[earlier, "R_v"].sum()), 2),
            "reference_stopped_but_variant_not_or_later": int(later.sum()),
            "of_which_variant_ended_in_gain": int((later & (j["R_v"] > 0)).sum())}


def run_variant(spec, ctx, stress):
    """One declared variant in one cost mode. Returns (result dict, trades, diag dict)."""
    name, sym = ctx["name"], ctx["sym"]
    frame = ctx["frames"][stress]
    O, I, tref = ctx["O"][stress], ctx["I"][stress], ctx["tref_raw"][stress]
    fam = spec["family"]
    if fam == "S":
        o, d0 = V.S(O, I, name, spec["k"])
    elif fam == "T":
        o, d0 = V.T(O, I, name, spec["m"])
    elif fam == "B":
        o, d0 = V.B(O, I, name, spec["b"])
    elif fam == "H":
        o, d0 = V.H(O, I, name, spec["j"], ctx["ahead"][stress])
    else:
        raise ValueError(fam)
    sub = np.ones(len(o), bool)
    if fam == "S" and spec.get("reentry") is False:
        sub = O["oid"].isin(tref["oid"]).to_numpy()
    ref_ = V.refuse(d0, I["spread"].to_numpy())
    taken = sub & ~ref_
    t = C.sim(frame, o[taken], sym, stress)
    res, tf = evaluate(frame, t, sym)
    res["orders"] = int(sub.sum())
    res["refused_orders"] = int((sub & ref_).sum())
    res["refused_share_of_orders"] = round(float((sub & ref_).sum() / max(sub.sum(), 1)), 4)
    if fam == "H":
        res["extended_orders"] = int((ctx["ahead"][stress] & sub).sum())
        res["extended_trades"] = int(np.isin(tf["oid"], O["oid"][ctx["ahead"][stress]]).sum())
    diag = None
    if (sub & ref_).any():
        td = C.sim(frame, o[sub], sym, stress)
        rd, tdf = evaluate(frame, td, sym)
        close = np.isin(tdf["oid"].to_numpy(), O["oid"].to_numpy()[sub & ref_])
        cw = C.window(tdf.assign(close=close), "common")
        diag = {"common": rd["common"], "trades_common": int(len(cw)),
                "trades_with_stop_under_3_spreads_common": int(cw["close"].sum()),
                "share_common": round(float(cw["close"].mean()), 4) if len(cw) else 0.0,
                "R_of_those_common": round(float(cw.loc[cw["close"], "R"].sum()), 2)}
    return res, tf, diag


def prepare(name, sym, m1, m1s):
    _, mo, params = C.registry()[(name, sym)]
    ctx = {"name": name, "sym": sym, "frames": {False: m1, True: m1s}, "O": {}, "I": {}, "tref_raw": {}, "tref": {},
           "ref": {}, "ahead": {}}
    for stress in (False, True):
        fr = ctx["frames"][stress]
        O = C.build_orders(name, sym, fr)
        I = V.info(name, sym, fr, O, stress, params, mo)
        t = C.sim(fr, O, sym, stress)
        res, tf = evaluate(fr, t, sym)
        rr = V.refuse(I["r0"].to_numpy(), I["spread"].to_numpy())
        res["orders"] = int(len(O))
        res["orders_with_stop_under_3_spreads"] = int(rr.sum())
        res["taken_with_stop_under_3_spreads"] = int(np.isin(tf["oid"], O["oid"][rr]).sum())
        ctx["O"][stress], ctx["I"][stress], ctx["tref_raw"][stress], ctx["tref"][stress] = O, I, t, tf
        ctx["ref"][stress] = res
        ctx["ahead"][stress] = V.hold_decision(fr, O, I, sym, stress)
    return ctx


def same(t1, t2):
    if len(t1) != len(t2):
        return False
    c = ["entry_time", "exit_time", "side", "reason"]
    if not all((t1[k].to_numpy() == t2[k].to_numpy()).all() for k in c):
        return False
    return bool(np.allclose(t1["R"].to_numpy(), t2["R"].to_numpy(), rtol=0, atol=1e-9))


def check(sym):
    m1, m1s = load_sym(sym)
    for name in BY_SYM[sym]:
        ctx = prepare(name, sym, m1, m1s)
        for stress in (False, True):
            fr, O, I, tref = ctx["frames"][stress], ctx["O"][stress], ctx["I"][stress], ctx["tref_raw"][stress]
            o1, _ = V.S(O, I, name, 1.0)
            ok_s = same(C.sim(fr, o1, sym, stress), tref)
            o2, _ = V.B(O, I, name, np.inf)
            ok_b = same(C.sim(fr, o2, sym, stress), tref)
            o3, _ = V.H(O, I, name, 1, np.zeros(len(O), bool))
            ok_h = same(C.sim(fr, o3, sym, stress), tref)
            I2 = I.copy()
            I2["cap"] = O["exit_i"].to_numpy()
            I2["unit"] = 1e12
            o4, _ = V.T(O, I2, name, 1)
            ok_t = same(C.sim(fr, o4, sym, stress), tref)
            r0_err = float(np.nanmax(np.abs(I["r0"].to_numpy()[tref.index] - tref["risk"].to_numpy()) / tref["risk"].to_numpy()))
            fp_err = float(np.nanmax(np.abs(I["fp"].to_numpy()[tref.index] - tref["entry"].to_numpy())))
            ahead = ctx["ahead"][stress]
            print(f"{name:20s} {sym} stress={stress}: S1 {ok_s} Binf {ok_b} H-none {ok_h} T-identity {ok_t} | "
                  f"fill err {fp_err:.2e} r0 rel err {r0_err:.2e} | clock {int(I['clock'].sum())}/{len(O)} "
                  f"ahead>=1R at clock {int(ahead.sum())} | ref n(common) {ctx['ref'][stress]['common']['n']} "
                  f"stops<3spr orders {ctx['ref'][stress]['orders_with_stop_under_3_spreads']} "
                  f"taken {ctx['ref'][stress]['taken_with_stop_under_3_spreads']}", flush=True)
            ext_len = (I["ext1"] - O["exit_i"]).to_numpy()[I["clock"].to_numpy()]
            cap_len = (I["cap"] - O["exit_i"]).to_numpy()[I["clock"].to_numpy()]
            print(f"    ext1-exit bars: min {ext_len.min() if len(ext_len) else 0} med "
                  f"{np.median(ext_len) if len(ext_len) else 0}; cap-exit bars: min {cap_len.min() if len(cap_len) else 0} "
                  f"med {np.median(cap_len) if len(cap_len) else 0}; unit/r0 med "
                  f"{np.nanmedian(I['unit'] / I['r0']):.3f}; spread/r0 max {np.nanmax(I['spread'] / I['r0']):.4f}")


def save_refs(ctx, name, sym):
    """Reference trades (both cost modes, with excursions and the per-order info) and their statistics."""
    parts = []
    for stress in (False, True):
        rt = ctx["tref"][stress].copy()
        I = ctx["I"][stress]
        rt["unit"] = I["unit"].to_numpy()[rt["oid"].to_numpy()]
        rt["spread"] = I["spread"].to_numpy()[rt["oid"].to_numpy()]
        rt["clock"] = I["clock"].to_numpy()[rt["oid"].to_numpy()]
        rt["ahead_at_clock"] = ctx["ahead"][stress][rt["oid"].to_numpy()]
        parts.append(rt[[c for c in KEEP_COLS + ["year", "unit", "spread", "clock", "ahead_at_clock"] if c in rt]]
                     .assign(mode="stress" if stress else "fp"))
    pd.concat(parts, ignore_index=True).to_parquet(os.path.join(C.OUT, f"reference_{name}__{sym}.parquet"))
    json.dump({"fp": ctx["ref"][False], "stress": ctx["ref"][True]},
              open(os.path.join(C.OUT, f"reference_{name}__{sym}.json"), "w"), indent=1, default=str)


def refs(sym):
    """Reference runs only (no variant, nothing appended to trials.jsonl)."""
    m1, m1s = load_sym(sym)
    for name in BY_SYM[sym]:
        save_refs(prepare(name, sym, m1, m1s), name, sym)
        print(f"{name}:{sym} references saved", flush=True)


def run(sym):
    decl = json.load(open(os.path.join(C.OUT, "declared.json")))
    done = set()
    if os.path.exists(TRIALS):
        for line in open(TRIALS):
            d = json.loads(line)
            done.add((d["sleeve"], d["variant"]["id"]))
    m1, m1s = load_sym(sym)
    for name in BY_SYM[sym]:
        key = f"{name}:{sym}"
        t0 = time.time()
        ctx = prepare(name, sym, m1, m1s)
        tr_all = []
        save_refs(ctx, name, sym)
        for spec in decl["sleeves"][key]["variants"]:
            if (key, spec["id"]) in done:
                print(f"  {key} {spec['id']} already logged: skipped", flush=True)
                continue
            line = {"sleeve": key, "variant": spec, "ts": time.strftime("%Y-%m-%dT%H:%M:%S")}
            for stress in (False, True):
                res, tf, diag = run_variant(spec, ctx, stress)
                line["stress" if stress else "fp"] = res
                if diag is not None and not stress:
                    line["diag_no_refusal_fp"] = diag
                tr_all.append(tf.assign(variant=spec["id"], mode="stress" if stress else "fp"))
                if spec["family"] == "S" and spec.get("reentry") in (False, "n/a"):
                    line["witness_" + ("stress" if stress else "fp")] = witness(ctx["tref"][stress], tf)
                elif spec["family"] == "S":
                    line["witness_" + ("stress" if stress else "fp")] = witness(ctx["tref"][stress], tf)
            with open(TRIALS, "a") as f:
                f.write(json.dumps(line, default=str) + "\n")
            c, r = line["fp"]["common"], ctx["ref"][False]["common"]
            print(f"  {key:28s} {spec['id']:6s} n {c.get('n', 0):5d} exp {c.get('exp_R', 0):+.4f} (ref {r['exp_R']:+.4f}) "
                  f"tot {c.get('total_R', 0):8.2f} (ref {r['total_R']:8.2f}) loss {c.get('avg_loss_R', 0):+.3f} "
                  f"(ref {r['avg_loss_R']:+.3f}) win {c.get('win_rate', 0):.3f} | stress exp "
                  f"{line['stress']['common'].get('exp_R', 0):+.4f} (ref {ctx['ref'][True]['common']['exp_R']:+.4f}) "
                  f"refused {line['fp']['refused_orders']}", flush=True)
        if tr_all:
            allt = pd.concat(tr_all, ignore_index=True)
            path = os.path.join(C.OUT, f"trades_{name}__{sym}.parquet")
            if os.path.exists(path):
                allt = pd.concat([pd.read_parquet(path), allt], ignore_index=True)
            keep = [c for c in KEEP_COLS + ["variant", "mode", "year"] if c in allt]
            allt[keep].to_parquet(path)
        print(f"{key} done [{time.time() - t0:.0f}s]", flush=True)


if __name__ == "__main__":
    mode, sym = sys.argv[1], sys.argv[2]
    {"check": check, "run": run, "refs": refs}[mode](sym)
