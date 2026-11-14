"""Runs the seven declared configurations of night_fade (PROTOCOL_V3 Addendum L, declared.json), IN SAMPLE ONLY.

For every configuration and cross, six readings (L18-L20):
  base      orders built on the base frame, base costs, one position per cross (goldlab.sim.simulate no_overlap=True)
  stress_a  costs x1.5, orders REBUILT on apply_spread_mult(base, 1.5) (the filter sees 1.5 C), slippage x1.5
  stress_b  costs x1.5, the base orders replayed unchanged on the widened quotes, slippage x1.5
  gross     the base orders replayed on apply_spread_mult(base, 0.0), no slippage (information; the gross and cost bp
            of base and stress_b)
  gross_a   reading a's own rebuilt orders replayed on the same gross frame, no slippage (information; the gross and cost
            bp of stress_a, review R6-3)
  every     the base orders with overlaps allowed (no_overlap=False), base costs (every-signal expectancy)
Outputs in results/r2/round6/night_fade/: trials.jsonl (91 lines: one per configuration and cross, one pooled line per
configuration; written once: the run refuses to run twice), run.json, trades_<id>_<name>_<reading>.parquet.
Write order (review R6-5): everything is computed and serialised first, then run.json is written, then trials.jsonl
(exclusive and atomic), then the val_access.log hashes recorded in run.json must be equal.
The null (null.py), the correlation (correlation.py) and the verdict (verdict.py) come after.

    python3 -I run.py --smoke   # structure only (orders, columns, times; no simulation, nothing written)
    python3 -I run.py           # the declared run
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

import hashlib  # noqa: E402
import json  # noqa: E402
import time  # noqa: E402

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

READINGS = ("base", "stress_a", "stress_b", "gross", "gross_a", "every")
GROSS_OF = {"base": "gross", "stress_b": "gross", "stress_a": "gross_a"}   # the gross replay of each reading's own orders
FRAME_OF = {"base": "base", "every": "base", "stress_a": "x1.5", "stress_b": "x1.5", "gross": "gross", "gross_a": "gross"}
KEEP = ["cross", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "exit_kind", "pnl", "risk", "R", "ret",
        "hold_min", "evening", "k_dec", "dec_utc", "mu", "sigma", "close_mid", "D", "C", "entry_delay_min", "h1_mean_range",
        "target_px", "mm_trigger_end_ns", "ny_summer_time", "mfe", "mae"]


def past_target(t):
    """Fills already at or past the frozen target (long: fill >= target; short: fill <= target)."""
    if len(t) == 0:
        return np.zeros(0, bool)
    tg = t.target_px.to_numpy(np.float64)
    e = t.entry.to_numpy(np.float64)
    return np.where(t.side.to_numpy() > 0, e >= tg, e <= tg)


def run_cross(m1, cross, cfgs):
    """Every reading of every configuration on one cross (frames of this cross only)."""
    bk = C.Book(m1, cross)
    m15 = C.stressed(m1, 1.5)
    bk15 = C.Book(m15, cross)
    mmid = C.stressed(m1, 0.0)
    E_trad = bk.tradable(480)
    out = {"tradable_evenings": int(len(E_trad)),
           "first_tradable_evening": str(E_trad[0].date()) if len(E_trad) else None,
           "evenings_not_tradable_warm_up": int(len(C.evenings()) - len(E_trad)), "configs": {}}
    for c in cfgs:
        p = c["params"]
        o, tb = C.make_orders(bk, p)
        oa, tba = C.make_orders(bk15, p)
        frozen = p["target_mode"] == "frozen_middle_band"
        t = {"base": C.run_orders(bk, o, C.costs(p)),
             "stress_a": C.run_orders(bk15, oa, C.costs(p, 1.5)),
             "stress_b": C.run_orders(bk, o, C.costs(p, 1.5), frame=m15),
             "gross": C.run_orders(bk, o, C.GROSS, frame=mmid),
             "gross_a": C.run_orders(bk, oa, C.GROSS, frame=mmid),
             "every": C.run_orders(bk, o, C.costs(p), no_overlap=False)}
        assert len(t["every"]) == len(o), "every order of a market entry must fill"
        assert t["base"].attrs["nofill"] == 0 and t["every"].attrs["nofill"] == 0
        frames = {"base": m1, "x1.5": m15, "gross": mmid}
        for k in READINGS:
            t[k] = t[k].copy()
            t[k]["cross"] = cross
            t[k]["same_bar_stop_and_target"] = C.same_bar_both(frames[FRAME_OF[k]], t[k]) if frozen else False
            t[k]["fill_past_target"] = past_target(t[k]) if frozen else False
        stc = {C.STATUS[s]: int(v) for s, v in pd.Series(tb.status).value_counts().sort_index().items()}
        sta = {C.STATUS[s]: int(v) for s, v in pd.Series(tba.status).value_counts().sort_index().items()}
        out["configs"][c["name"]] = {
            "trades": t, "orders": int(len(o)), "orders_stress_a": int(len(oa)), "decisions": int(len(tb)),
            "status_counts": stc, "status_counts_stress_a": sta,
            "skipped_by_one_position": int(t["base"].attrs["skipped"]),
            "signals": {"buy": int(((tb.side > 0) & tb.usable).sum()), "sell": int(((tb.side < 0) & tb.usable).sum())}}
    return out


def config_stats(name, per_cross, crosses):
    """Pooled and per-cross figures of one configuration for every reading."""
    pooled = {k: pd.concat([per_cross[c]["configs"][name]["trades"][k] for c in crosses], ignore_index=True)
              .sort_values(["entry_time", "cross"], kind="stable").reset_index(drop=True) for k in READINGS}
    res = {"pooled": {}, "per_cross": {}}
    for k in READINGS:
        res["pooled"][k] = C.stats(pooled[k], gross=pooled[GROSS_OF[k]] if k in GROSS_OF else None, crosses=crosses)
    for c in crosses:
        tc = per_cross[c]["configs"][name]["trades"]
        res["per_cross"][c] = {k: C.stats(tc[k], gross=tc[GROSS_OF[k]] if k in GROSS_OF else None, per_cross=False)
                               for k in READINGS}
        cc = per_cross[c]["configs"][name]
        res["per_cross"][c]["orders"] = cc["orders"]
        res["per_cross"][c]["orders_stress_a"] = cc["orders_stress_a"]
        res["per_cross"][c]["status_counts"] = cc["status_counts"]
        res["per_cross"][c]["status_counts_stress_a"] = cc["status_counts_stress_a"]
        res["per_cross"][c]["skipped_by_one_position"] = cc["skipped_by_one_position"]
        res["per_cross"][c]["signals"] = cc["signals"]
    b = pooled["base"]
    res["pooled"]["extras"] = {
        "same_bar_stop_and_target": int(b.same_bar_stop_and_target.astype(bool).sum()) if len(b) else 0,
        "stress_b_fills_past_target": int(pooled["stress_b"].fill_past_target.astype(bool).sum()) if len(pooled["stress_b"]) else 0,
        "stress_a_fills_past_target": int(pooled["stress_a"].fill_past_target.astype(bool).sum()) if len(pooled["stress_a"]) else 0,
        "base_fills_past_target": int(b.fill_past_target.astype(bool).sum()) if len(b) else 0,
        "orders": int(sum(per_cross[c]["configs"][name]["orders"] for c in crosses)),
        "orders_stress_a": int(sum(per_cross[c]["configs"][name]["orders_stress_a"] for c in crosses)),
        "skipped_by_one_position": int(sum(per_cross[c]["configs"][name]["skipped_by_one_position"] for c in crosses)),
        "status_counts": {s: int(sum(per_cross[c]["configs"][name]["status_counts"].get(s, 0) for c in crosses))
                          for s in C.STATUS.values()},
        "status_counts_stress_a": {s: int(sum(per_cross[c]["configs"][name]["status_counts_stress_a"].get(s, 0)
                                              for c in crosses)) for s in C.STATUS.values()},
        "trades_differing_from_base": {k: int(len(set(zip(b.cross, b.entry_time)) ^ set(zip(pooled[k].cross, pooled[k].entry_time))))
                                       for k in ("stress_a", "stress_b", "gross")},
        "gross_a_trades_differing_from_stress_a": int(len(set(zip(pooled["stress_a"].cross, pooled["stress_a"].entry_time))
                                                          ^ set(zip(pooled["gross_a"].cross, pooled["gross_a"].entry_time))))}
    return res, pooled


def trial_lines(cfg, res, crosses):
    """One trials.jsonl line per cross and one pooled line for a configuration (L29)."""
    lines = []
    period = "in sample: evenings 2013-01-02 .. 2021-12-22, frames read with ts < 2022-01-01"
    for c in crosses + ["pooled"]:
        r = res["per_cross"][c] if c != "pooled" else res["pooled"]
        line = {"track": C.TRACK, "config_id": cfg["id"], "config": cfg["name"], "role": cfg["role"], "cross": c,
                "params": cfg["params"], "period": period}
        for k in READINGS:
            line["every_signal" if k == "every" else k] = C.short(r[k])
        if c == "pooled":
            line["orders"] = r["extras"]["orders"]
            line["status_counts"] = r["extras"]["status_counts"]
        else:
            line["orders"] = r["orders"]
            line["status_counts"] = r["status_counts"]
        lines.append(line)
    return lines


def save_trades(pooled, cfg, out):
    files = {}
    for k in READINGS:
        t = pooled[k]
        cols = [x for x in KEEP + ["same_bar_stop_and_target", "fill_past_target"] if x in t.columns]
        name = f"trades_{cfg['id']:02d}_{cfg['name']}_{k}.parquet"
        t[cols].to_parquet(os.path.join(out, name))
        files[k] = name
    return files


def write_replace(path, text):
    """Write `text` to `path` atomically (a temporary file in the same folder, then os.replace)."""
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "x", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_new(path, text):
    """Create `path` with `text`, never overwriting it: the text goes to a temporary file in the same folder, which is
    then hard-linked to the final name (os.link raises if the name exists), so the name only ever appears with its
    complete content (exclusive creation, as open(path, 'x'), but atomic)."""
    tmp = f"{path}.tmp{os.getpid()}"
    with open(tmp, "x", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    try:
        os.link(tmp, path)
    finally:
        os.unlink(tmp)


def run_all(cfgs, crosses, load, out, decl_sha=None, decl_utc=None, val_log=C.VAL_LOG):
    """The declared run on the given crosses (frames from `load(cross)`), outputs in `out`. Refuses to run twice.
    Write order (review R6-5): everything is computed, and run.json and trials.jsonl are serialised in memory, before
    either is written; then run.json (atomic), then trials.jsonl (exclusive and atomic); then the val_access.log hashes,
    both recorded in run.json, must be equal. A failure before the writes leaves neither file (the declared run can be
    started again: nothing was logged); once trials.jsonl exists, the complete run.json is next to it."""
    tri = os.path.join(out, "trials.jsonl")
    assert not os.path.exists(tri), "trials.jsonl exists: the declared run is done once (L29)"
    val0 = C.sha256(val_log) if os.path.exists(val_log) else None
    t0 = time.time()
    per_cross = {}
    for c in crosses:
        m1 = load(c)
        C.assert_is(m1)
        per_cross[c] = run_cross(m1, c, cfgs)
        del m1
        print(f"computed {c}", flush=True)
    results, lines, files = {}, [], {}
    for cfg in cfgs:
        res, pooled = config_stats(cfg["name"], per_cross, crosses)
        results[cfg["name"]] = res
        lines += trial_lines(cfg, res, crosses)
        files[cfg["name"]] = save_trades(pooled, cfg, out)
    assert len(lines) == len(cfgs) * (len(crosses) + 1)
    trials_txt = "".join(json.dumps(line, default=C._default) + "\n" for line in lines)
    ev_skips = {c: {"calendar": {k: int(v) for k, v in C.calendar().status.value_counts().items() if k != "ok"},
                    "warm_up_480_h1": per_cross[c]["evenings_not_tradable_warm_up"],
                    "tradable": per_cross[c]["tradable_evenings"],
                    "first_tradable_evening": per_cross[c]["first_tradable_evening"]} for c in crosses}
    val1 = C.sha256(val_log) if os.path.exists(val_log) else None
    out_json = {"what": "night_fade (PROTOCOL_V3 Addendum L), seven declared configurations, in sample only",
                "declared_sha256": decl_sha, "declared_utc": decl_utc, "crosses": crosses,
                "configs": [{"id": c["id"], "name": c["name"], "role": c["role"], "params": c["params"],
                             "results": results[c["name"]], "trade_files": files[c["name"]]} for c in cfgs],
                "evenings": ev_skips, "trials_logged": len(lines),
                "trials_sha256": hashlib.sha256(trials_txt.encode("utf-8")).hexdigest(),
                "val_access_log_sha256_before": val0, "val_access_log_sha256_after": val1,
                "seconds": round(time.time() - t0, 1)}
    run_txt = json.dumps(out_json, indent=1, default=C._default, ensure_ascii=False)
    write_replace(os.path.join(out, "run.json"), run_txt)
    write_new(tri, trials_txt)                                  # exclusive creation: never overwritten
    assert val0 == val1, "results/val_access.log changed"
    return out_json


def main(smoke=False):
    decl, sha = C.declared()
    C.check_frames(decl)
    cfgs = decl["configurations"]
    assert [c["name"] for c in cfgs] == [c["name"] for c in C.CONFIGS]
    assert all(c["params"] == k["params"] for c, k in zip(cfgs, C.CONFIGS)), "declared parameters differ from common.py"
    crosses = decl["crosses_kept"]
    if smoke:
        m1 = C.load_base(crosses[0])
        bk = C.Book(m1, crosses[0])
        for c in cfgs:
            o, tb = C.make_orders(bk, c["params"])
            print(c["name"], "orders", len(o), "decisions", len(tb), "columns", list(o.columns)[:8],
                  "first", o.dec_utc.min(), "last", o.dec_utc.max())
        return
    res = run_all(cfgs, crosses, C.load_base, C.OUT, sha, decl["_written_utc"])
    for c in res["configs"]:
        s = c["results"]["pooled"]
        print(c["name"], {k: s["base"].get(k) for k in ("n", "pf", "t_daily", "expectancy_R", "years_pos",
                                                        "crosses_positive", "max_cross_share")},
              "stress a/b pf", s["stress_a"].get("pf"), s["stress_b"].get("pf"), "gross bp", s["base"].get("bp_gross_per_trade"),
              "every exp", s["every"].get("expectancy_R"))


if __name__ == "__main__":
    main(smoke="--smoke" in sys.argv)
