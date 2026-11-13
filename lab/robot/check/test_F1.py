"""T4 crypto F1 (step E): F1B and F1E, switches off, against the lab on the whole in-sample period; the frozen scorecard.

    python3 -I lab/robot/check/test_F1.py [--no-sanitize]

The EA and the lab run as in test_BK.py (its harness: the private tree with the S0 stubs of the parallel steps, the
2013-2021 bars of the four symbols, InpTrade false, the three switches 0; ref_lab.py's one() for F1B and F1E in fresh
processes on the frames rebuilt from the same bars). Checks, per sleeve:
  * candidates: every candidate of ml/strategy.py candidates() (the lab's code, fresh process) has the EA's DEC info
    line (v1 = score, v2 = A) at its decision with the same side; A bit for bit; the score within 1e-12 of the lab's
    score_model (numpy) and bit for bit equal to the same sum taken term by term in the EA's order (which shows that
    the 15 features are the lab's to the last bit); every other EA candidate has no entry bar within 5 min or is void,
    and is then checked against candidates() with max_wait_min raised (the lab's code, the same features); razors:
    lab scores within 1e-9 of the threshold, listed;
  * orders: every lab order (score >= threshold) has its DEC line: same oid and side, stop_dist = 2 A within 1e-12,
    activation [t_dec, t_dec + 5 min] on the lab's entry bar, exit min(t_dec + 13 h, 15:55 New York) with the gap rule
    on the lab's exit bar; every other EA order has no bar in its window or is void;
  * trades: compare.cmp_trades, every lab trade that ends before the frame's last bar;
  * the scorecard: tools/gen_f1_model.py --check (src/CR_F1Model.mqh is the generator's output), every constant reads
    back as the JSON's double, the generator refuses a copy of the model with one digit changed (wrong sha256) and
    writes nothing; the EA's Score() (a generated unit program) on every lab candidate's features: bit for bit the
    term-by-term sum, within 1e-12 of numpy;
  * LatestExit (SPEC 4.8): 15:55 New York of the decision's date, against zoneinfo, on 48 open times; with H2 on (SPEC
    v2.1, review F1) the H2 horizon min(15:55 New York on the decision's New York date + 2 business days, Friday 23:54
    server), against pandas BDay and zoneinfo, on the same open times;
  * the lab trades on the rebuilt frames against the official trades: differences listed with their cause;
  * the sanitizer build replays the same bars with an identical journal.
Outputs: check/out/test_E/test_F1.json.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import test_BK as H  # noqa: E402  (step E's harness)

ROBOT, LAB, OUT = H.ROBOT, H.LAB, H.OUT
MODEL = os.path.join(LAB, "r2", "tracks", "ml", "models", "B1_ridge_full.json")
GEN = os.path.join(ROBOT, "tools", "gen_f1_model.py")
NY = ZoneInfo("America/New_York")
FEATURES = ["brk", "bar", "body", "ret4", "ret14", "ret70", "chan", "vol", "pos", "seq", "opp", "pdd", "dret", "hour", "dow"]
EXPECT_OFF = {"et": 0, "xg": 1, "vle": 1, "ref": 0, "xh": 0}


# ======================================================================================== the lab's candidates
def lab_candidates(code):
    """candidates() and score_model() of ml/strategy.py on the rebuilt frame, in a fresh process (recalc.sleeves() once):
    the real parameters, and max_wait_min raised (the EA journals a candidate before it knows its entry bar)"""
    out = os.path.join(H.REF, "rebuilt_is", code)
    os.makedirs(out, exist_ok=True)
    src = f"""
import sys, os, json
sys.dont_write_bytecode = True
import numpy as np, pandas as pd
LAB = {LAB!r}
sys.path.insert(0, LAB); sys.path.insert(0, os.path.join(LAB, "r2"))
import recalc
reg = {{(s[1], s[2]): s for s in recalc.sleeves()}}
M = sys.modules["r2_ml_strategy"]
params = reg[("F1_brk_ridge_filter", {H.LAB_SYM[code]!r})][4]
m1 = pd.read_parquet({os.path.join(HERE, "out", "frames", H.LAB_SYM[code] + "_is.parquet")!r}, filters=[("ts", "<", pd.Timestamp("2022-01-01", tz="UTC"))])
spec = M.load_model(params["model"])["frozen"]
thr = M._thr(spec, params["q"])
def table(f):
    X = M._design(f, spec)
    coef = np.asarray(spec["coef"], float)
    seq = np.empty(len(f))
    for i in range(len(f)):
        s = 0.0
        for k in range(X.shape[1]):
            s = s + X[i, k] * coef[k]
        seq[i] = spec["intercept"] + s
    t = pd.DataFrame({{"t_dec": pd.DatetimeIndex(f["t_dec"]).as_unit("s").asi8, "side": f["side"].to_numpy(np.int64),
                      "A": f["A"].to_numpy(float), "score": M.score_model(f, spec), "score_seq": seq,
                      "entry_i": f["entry_i"].to_numpy(np.int64), "exit_i": f["exit_i"].to_numpy(np.int64)}})
    for c in {FEATURES!r}:
        t["f_" + c] = f[c].to_numpy(float)
    return t
M._cache.clear()
a = table(M.candidates(m1, **params))
M._cache.clear()
b = table(M.candidates(m1, **{{**params, "max_wait_min": 10**9}}))
a.to_parquet(os.path.join({out!r}, "candidates.parquet"))
b.to_parquet(os.path.join({out!r}, "candidates_any_wait.parquet"))
print(json.dumps({{"candidates": len(a), "candidates_any_wait": len(b), "thr": thr, "taken": int((a.score >= thr).sum())}}))
"""
    res = H.spawn(src)
    return res, pd.read_parquet(os.path.join(out, "candidates.parquet")), pd.read_parquet(os.path.join(out, "candidates_any_wait.parquet"))


def cmp_candidates(rows, code, cand, cand_any, thr):
    """the EA's DEC info lines (v1 score, v2 A) against the lab's candidates"""
    ea = H.dec_rows(rows, code, "info")
    res = {"code": code, "lab_candidates": int(len(cand)), "ea_candidates": int(len(ea))}
    if not len(ea):
        res["pass"] = False
        return res
    ea = ea.rename(columns={"utc": "t_dec"})
    dup = int(ea.t_dec.duplicated().sum())
    ea = ea.drop_duplicates("t_dec", keep="last").set_index("t_dec")
    lab = cand.set_index("t_dec")
    both = lab.index.intersection(ea.index)
    only_lab = sorted(int(x) for x in lab.index.difference(ea.index))
    L, E = lab.loc[both], ea.loc[both]
    side_ok = (L.side.to_numpy() == E.side.to_numpy())
    a_eq = (L.A.to_numpy() == E.v2.to_numpy())
    d_np = np.abs(L.score.to_numpy() - E.v1.to_numpy())
    seq_eq = (L.score_seq.to_numpy() == E.v1.to_numpy())
    np_eq = (L.score.to_numpy() == E.v1.to_numpy())
    dec_ok = ((L.score.to_numpy() >= thr) == (E.v1.to_numpy() >= thr))
    # EA candidates the lab does not keep (no entry bar within 5 min, or void): the lab's code with the wait raised
    extra = ea.loc[ea.index.difference(lab.index)]
    la = cand_any.set_index("t_dec")
    ex_in = extra.index.intersection(la.index)
    X, LA = extra.loc[ex_in], la.loc[ex_in]
    idx = H.frame_secs(H.LAB_SYM[code])
    ai = H.act_bar(idx, extra.index.to_numpy(np.int64), extra.index.to_numpy(np.int64) + 300)
    extra_no_bar = int((ai < 0).sum())
    razors = lab[(lab.score - thr).abs() < 1e-9]
    res.update({"matched": int(len(both)), "duplicates": dup, "only_lab": len(only_lab), "only_lab_first": only_lab[:10],
                "side_differs": int((~side_ok).sum()), "A_bit_equal": int(a_eq.sum()),
                "score_max_abs_diff_vs_numpy": float(d_np.max()) if len(d_np) else 0.0,
                "score_bit_equal_numpy": int(np_eq.sum()), "score_bit_equal_term_by_term": int(seq_eq.sum()),
                "decision_differs": int((~dec_ok).sum()),
                "ea_only": int(len(extra)), "ea_only_no_entry_bar": extra_no_bar,
                "ea_only_found_with_wait_raised": int(len(ex_in)),
                "ea_only_side_A_score_equal": int(((X.side.to_numpy() == LA.side.to_numpy()) & (X.v2.to_numpy() == LA.A.to_numpy())
                                                   & (X.v1.to_numpy() == LA.score_seq.to_numpy())).sum()),
                "razors_within_1e-9": [{"t_dec": int(t), "score": float(s)} for t, s in zip(razors.index, razors.score)],
                "closest_to_threshold": float((lab.score - thr).abs().min()) if len(lab) else None})
    ea_only_ok = res["ea_only_side_A_score_equal"] == res["ea_only_found_with_wait_raised"]
    res["pass"] = bool(dup == 0 and not only_lab and side_ok.all() and a_eq.all() and (d_np <= 1e-12).all() and seq_eq.all()
                       and dec_ok.all() and ea_only_ok)
    return res


def check_times(ea):
    """[t_dec, t_dec + 5 min], x = min(t_dec + 13 h, 15:55 New York of t_dec's date) (zoneinfo)"""
    if not len(ea):
        return 0
    d = ea.reset_index()
    bad = 0
    for oid, tf, tt, x in zip(d.oid, d.tf, d.tt, d.x):
        t = int(oid) // 100
        ny = pd.Timestamp(t, unit="s", tz="UTC").tz_convert(NY)
        cap = int(pd.Timestamp(ny.year, ny.month, ny.day, 15, 55, tz=NY).tz_convert("UTC").value // 10**9)
        bad += int(tf != t or tt != t + 300 or x != min(t + 46800, cap))
    return bad


# ======================================================================================== the scorecard
def literals(path):
    """the generated constants of CR_F1Model.mqh: {name: float or [floats]}"""
    txt = open(path).read()
    out = {}
    for m in re.finditer(r"^#define (CR_F1_\w+) (\S+)$", txt, re.M):
        try:
            out[m.group(1)] = float(m.group(2))
        except ValueError:
            out[m.group(1)] = m.group(2)
    for m in re.finditer(r"^(?:int|double)\s+(CR_F1_\w+)\[\w+\] = \{([^}]*)\};$", txt, re.M):
        out[m.group(1)] = [float(v) for v in m.group(2).split(",")]
    return out


def check_scorecard():
    res = {}
    r = subprocess.run([sys.executable, "-I", GEN, "--check"], capture_output=True, text=True)
    res["generator_check"] = {"exit": r.returncode, "out": r.stdout.strip()}
    m = json.load(open(MODEL))["frozen"]
    lit = literals(os.path.join(ROBOT, "src", "CR_F1Model.mqh"))
    exact = (lit["CR_F1_INTERCEPT"] == m["intercept"] and lit["CR_F1_THR"] == m["thr"]["0.5"] and lit["CR_F1_CLIP"] == m.get("clip", 4.0)
             and lit["CR_F1_MEAN"] == [float(v) for v in m["mean"]] and lit["CR_F1_STD"] == [float(v) for v in m["std"]]
             and lit["CR_F1_COEF"] == [float(v) for v in m["coef"]]
             and lit["CR_F1_NUM_FEAT"] == [float(FEATURES.index(f)) for f in m["num"]]
             and lit["CR_F1_DUM_FEAT"] == [float(FEATURES.index(d[0])) for d in m["dummies"]]
             and lit["CR_F1_DUM_LO"] == [float(d[1]) for d in m["dummies"]] and lit["CR_F1_DUM_HI"] == [float(d[2]) for d in m["dummies"]])
    res["constants_equal_json"] = bool(exact)
    # a copy with one digit changed: refused (wrong sha256), nothing written
    d = os.path.join(OUT, "gen_refusal")
    if os.path.isdir(d):
        shutil.rmtree(d)
    os.makedirs(d)
    raw = open(MODEL, "rb").read()
    k = raw.index(b'"intercept": ') + len(b'"intercept": ') + 5
    bad = raw[:k] + (b"1" if raw[k:k + 1] != b"1" else b"2") + raw[k + 1:]
    p_bad, p_out = os.path.join(d, "B1_ridge_full.json"), os.path.join(d, "CR_F1Model.mqh")
    open(p_bad, "wb").write(bad)
    r2 = subprocess.run([sys.executable, "-I", GEN, "--model", p_bad, "--out", p_out], capture_output=True, text=True)
    res["wrong_sha_refused"] = {"exit": r2.returncode, "stderr": r2.stderr.strip()[:300], "file_written": os.path.exists(p_out)}
    ok = (r.returncode == 0 and exact and r2.returncode == 2 and "REFUSED" in r2.stderr and "sha256" in r2.stderr
          and not os.path.exists(p_out))
    res["pass"] = bool(ok)
    return res


UNIT_SCORE = r"""
#include <cstdio>
#include <cstdlib>
int main(int argc, char **argv)
  {
   // argv[1]: a text file of rows "<15 features>" (17 digits); prints one score per row (17 digits)
   FILE *f = fopen(argv[1], "r");
   if(!f) return 2;
   CRuleF1 r;
   ArrayResize(r.m_x, CR_F1_NFEAT);
   double v[CR_F1_NFEAT];
   while(true)
     {
      int got = 0;
      for(int k = 0; k < CR_F1_NFEAT; k++) got += fscanf(f, "%lf", &v[k]);
      if(got != CR_F1_NFEAT) break;
      for(int k = 0; k < CR_F1_NFEAT; k++) r.m_x[k] = v[k];
      printf("%.17g\n", r.Score());
     }
   fclose(f);
   // LatestExit: argv[2] = a file of "open_time comment_dec" rows
   FILE *g = fopen(argv[2], "r");
   if(!g) return 3;
   long o = 0, c = 0;
   CRuleF1 q, qh;
   q.m_h2 = false;
   qh.m_h2 = true;                                            // F1E with H2 on: LatestExit is the H2 horizon
   while(fscanf(g, "%ld %ld", &o, &c) == 2)
     {
      printf("LX %ld %ld %ld\n", o, c, (long)q.LatestExit(o, c));
      printf("LH %ld %ld %ld\n", o, c, (long)qh.LatestExit(o, c));
     }
   fclose(g);
   return 0;
  }
"""


def unit_checks(cands):
    """the EA's Score() on the lab candidates' features, and F1's LatestExit, through a generated unit program"""
    d = os.path.join(OUT, "unit_f1")
    os.makedirs(d, exist_ok=True)
    allc = pd.concat(cands, ignore_index=True)
    feats = allc[[f"f_{c}" for c in FEATURES]].to_numpy(float)
    with open(os.path.join(d, "features.txt"), "w") as f:
        for row in feats:
            f.write(" ".join("%.17g" % v for v in row) + "\n")
    # open times: on the hour and minutes after, around both 2021 DST switches, Fridays, a comment that agrees, one that
    # does not (too far before the open time: floor used), and none
    base = [pd.Timestamp(x, tz="UTC") for x in ("2021-03-12 13:00", "2021-03-15 13:03", "2021-03-15 19:00", "2021-11-05 18:02",
                                                 "2021-11-08 14:07", "2020-06-19 19:04", "2019-12-31 08:00", "2018-07-02 07:09")]
    cases = []
    for b in base:
        t = int(b.value // 10**9)
        for off in (0, 59, 300, 599):
            cases.append((t + off, 0))
        cases.append((t + 120, t))                          # the comment's decision agrees
        cases.append((t + 120, t - 3600))                   # 62 min before: not consistent, floor used
    with open(os.path.join(d, "latest.txt"), "w") as f:
        for o, c in cases:
            f.write(f"{o} {c}\n")
    exe, warn = H.build_unit("unit_f1", "CR_Rule_F1.mqh", UNIT_SCORE)
    r = subprocess.run([exe, os.path.join(d, "features.txt"), os.path.join(d, "latest.txt")], capture_output=True, text=True)
    lines = r.stdout.split("\n")
    sc = np.array([float(x) for x in lines if x and not x.startswith(("LX", "LH"))])
    lx = [tuple(int(v) for v in x.split()[1:]) for x in lines if x.startswith("LX")]
    lh = [tuple(int(v) for v in x.split()[1:]) for x in lines if x.startswith("LH")]
    seq_eq = int((sc == allc.score_seq.to_numpy()).sum()) if len(sc) == len(allc) else -1
    d_np = float(np.abs(sc - allc.score.to_numpy()).max()) if len(sc) == len(allc) else None
    bad_lx = []
    for o, c, x in lx:
        t = o - o % 3600
        if c > 0 and c % 3600 == 0 and c <= o and o - c <= 600:
            t = c
        ny = pd.Timestamp(t, unit="s", tz="UTC").tz_convert(NY)
        cap = int(pd.Timestamp(ny.year, ny.month, ny.day, 15, 55, tz=NY).tz_convert("UTC").value // 10**9)
        if x != min(t + 46800, cap):
            bad_lx.append([o, c, x, min(t + 46800, cap)])
    bad_lh = []
    from pandas.tseries.offsets import BDay
    for o, c, x in lh:
        t = o - o % 3600
        if c > 0 and c % 3600 == 0 and c <= o and o - c <= 600:
            t = c
        ny = pd.Timestamp(t, unit="s", tz="UTC").tz_convert(NY)
        cap = int(pd.Timestamp(ny.year, ny.month, ny.day, 15, 55, tz=NY).tz_convert("UTC").value // 10**9)
        d2 = pd.Timestamp(ny.year, ny.month, ny.day) + BDay(2)
        xa = int(pd.Timestamp(d2.year, d2.month, d2.day, 15, 55, tz=NY).tz_convert("UTC").value // 10**9)
        srv = ny.tz_localize(None) + pd.Timedelta(hours=7)          # the server wall clock (New York + 7 h)
        fri = srv.normalize() + pd.Timedelta(days=4 - srv.dayofweek) + pd.Timedelta(hours=23, minutes=54)
        xb = int((fri - pd.Timedelta(hours=7)).tz_localize(NY).tz_convert("UTC").value // 10**9)
        want = max(min(t + 46800, cap), min(xa, xb))
        if x != want:
            bad_lh.append([o, c, x, want])
    res = {"build_warnings": warn, "exit": r.returncode, "scores": int(len(sc)), "lab_candidates": int(len(allc)),
           "score_bit_equal_term_by_term": seq_eq, "score_max_abs_diff_vs_numpy": d_np,
           "latest_exit_cases": len(lx), "latest_exit_wrong": bad_lx[:10], "latest_exit_h2_cases": len(lh),
           "latest_exit_h2_wrong": bad_lh[:10]}
    res["pass"] = bool(r.returncode == 0 and not warn and seq_eq == len(allc) and d_np is not None and d_np <= 1e-12
                       and len(lx) == len(cases) and not bad_lx and len(lh) == len(cases) and not bad_lh)
    return res


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    res = {"test": "T4 F1 F1B F1E, switches off; the frozen scorecard", "per_sleeve": {}}
    res["scorecard"] = check_scorecard()
    print(f"scorecard: generator --check exit {res['scorecard']['generator_check']['exit']}, constants = JSON "
          f"{res['scorecard']['constants_equal_json']}, wrong sha256 refused exit {res['scorecard']['wrong_sha_refused']['exit']} "
          f"file written {res['scorecard']['wrong_sha_refused']['file_written']} | {'PASS' if res['scorecard']['pass'] else 'FAIL'}",
          flush=True)
    ok = res["scorecard"]["pass"]
    refs = {c: H.lab_ref(c) for c in ("F1B", "F1E")}
    offs = {c: H.lab_ref(c, "official") for c in ("F1B", "F1E")}
    cands = {c: lab_candidates(c) for c in ("F1B", "F1E")}
    exe, warn = H.build_ea(False)
    res["tree"] = H.tree()["origin"]
    res["build_warnings"] = warn
    rows, out, wall, files = H.replay(exe, "off", H.SWITCHES_OFF)
    res["replay"] = {"stdout": out, "wall_s": round(wall, 1), "errors": H.errors(rows)[:5]}
    ok &= not warn and not res["replay"]["errors"]
    fm, last = H.first_minute(rows), H.manifest_last()
    for code in ("F1B", "F1E"):
        info, lab_o, lab_t = refs[code]
        sym = H.LAB_SYM[code]
        ci, cand, cand_any = cands[code]
        rc = cmp_candidates(rows, code, cand, cand_any, ci["thr"])
        ro, ea = H.cmp_orders(rows, code, lab_o, sym, EXPECT_OFF)
        ro["window_or_exit_not_as_rule"] = check_times(ea)
        rt = H.cmp_trades(rows, code, lab_t, fm, last[H.BROKER[sym]] - 1)
        c = H.counts(rows, code)
        extra_lines = {k: v for k, v in c.items() if k in ("DEC:skip", "PREFUSE", "HOLD")}
        od = H.official_diff(code, lab_t, H.with_ea_oid(offs[code][1], code), H.with_ea_oid(lab_o, code))
        od["causes"] = H.explain(code, od)
        good = rc["pass"] and ro["pass"] and ro["window_or_exit_not_as_rule"] == 0 and rt["pass"] and not extra_lines
        res["per_sleeve"][code] = {"candidates": rc, "orders": ro, "trades": rt, "journal_counts": c, "unexpected_lines": extra_lines,
                                   "lab_rebuilt": {k: info[k] for k in ("orders", "trades", "R_sum", "reasons")},
                                   "lab_official": {k: offs[code][0][k] for k in ("orders", "trades", "R_sum")},
                                   "rebuilt_vs_official": od, "pass": bool(good)}
        ok &= good
        print(f"{code}: candidates lab {rc['lab_candidates']} EA {rc['ea_candidates']} matched {rc.get('matched')} A bit-equal "
              f"{rc.get('A_bit_equal')} score = numpy {rc.get('score_bit_equal_numpy')}, = term by term "
              f"{rc.get('score_bit_equal_term_by_term')}, max |diff| {rc.get('score_max_abs_diff_vs_numpy', 0):.3g}, razors "
              f"{len(rc.get('razors_within_1e-9', []))}, closest {rc.get('closest_to_threshold')} | EA only {rc.get('ea_only')} "
              f"(no entry bar {rc.get('ea_only_no_entry_bar')}, equal with the wait raised {rc.get('ea_only_side_A_score_equal')}/"
              f"{rc.get('ea_only_found_with_wait_raised')})", flush=True)
        print(f"     orders lab {ro['lab_orders']} EA {ro['ea_orders']} matched {ro.get('matched')} wrong {ro.get('wrong')} "
              f"only_lab {ro.get('only_lab')} | EA extra: no bar {ro.get('only_ea_no_bar_in_window')} void {ro.get('only_ea_void')} "
              f"unexplained {ro.get('only_ea_unexplained')} | stop_dist bit-equal {ro.get('stop_dist_bit_equal')} | trades lab "
              f"{rt.get('lab_trades')} EA {rt.get('ea_trades')} same {rt.get('same_exit_and_reason')} entry/stop/exit bit-equal "
              f"{rt.get('entry_equal')}/{rt.get('stop_equal')}/{rt.get('exit_equal')} | {'PASS' if good else 'FAIL'}", flush=True)
        print(f"     rebuilt vs official: official {od['official']} rebuilt {od['rebuilt']} same exit+reason "
              f"{od['same_exit_and_reason']} only official {od['only_official']} only rebuilt {od['only_rebuilt']}", flush=True)
    res["unit"] = unit_checks([cands[c][1] for c in ("F1B", "F1E")])
    ok &= res["unit"]["pass"]
    print(f"unit: Score() on {res['unit']['scores']} lab candidates, term-by-term bit-equal {res['unit']['score_bit_equal_term_by_term']}, "
          f"max |diff| vs numpy {res['unit']['score_max_abs_diff_vs_numpy']}; LatestExit with H2 {res['unit']['latest_exit_h2_cases']} cases, "
          f"wrong {len(res['unit']['latest_exit_h2_wrong'])}; LatestExit {res['unit']['latest_exit_cases']} cases, "
          f"wrong {len(res['unit']['latest_exit_wrong'])} | {'PASS' if res['unit']['pass'] else 'FAIL'}", flush=True)
    if not a.no_sanitize:
        exe_s, warn_s = H.build_ea(True)
        rows_s, out_s, wall_s, files_s = H.replay(exe_s, "off_san", H.SWITCHES_OFF)
        same = H.journals_identical(files, files_s)
        res["sanitizer"] = {"build_warnings": warn_s, "stdout": out_s, "wall_s": round(wall_s, 1), "journal_identical": same}
        ok &= same and not warn_s
        print(f"sanitizer: warnings {len(warn_s)} journal identical {same} ({wall_s:.0f} s)", flush=True)
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    H.write("test_F1.json", res)
    print(f"test_F1: {'PASS' if ok else 'FAIL'} ({res['sec']} s) -> {os.path.relpath(os.path.join(OUT, 'test_F1.json'), ROBOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
