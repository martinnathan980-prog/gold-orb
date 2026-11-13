"""T5 crypto changes (step E): BKE+K1, BKB+S0.75r and F1E+H2, switches on, against the lab's own implementations.

    python3 -I lab/robot/check/test_changes.py [--no-sanitize]

The EA runs as in test_BK.py (its harness), with InpK1 = InpH2 = InpS075 = 1 on the demo account, InpTrade false and
InpK1T = the in-sample folds the lab fits on the same bars (K1's walk-forward, those that skip the high side). The
references come from check/ref_changes.py (vhi_guard.open_run, then vhi_sleeves.run on the look spec's sleeves) in a
fresh process each, on the frames rebuilt from the same bars. Checks:
  * BKE+K1: the EA's skip lines (DEC skip=K1) are the lab's skipped signals; riskbp (DEC skip and info lines) equals
    the signal table's riskbp within 1e-12 relative (bit for bit counted), T(Y) is the folds'; razors within 1e-9 of
    T listed; the orders (refusal 2) are the change's orders as in test_BK; the trades are the K1 chain's;
  * BKB+S0.75r: stop_dist = 0.75 x (3 ATR) equal to the change's orders bit for bit; refusal 1; trades = the chain's;
  * F1E+H2: every order carries xh = min(15:55 New York two business days later, Friday 23:54 server) and xh_r 1;
    its exit bars equal the rule's, and for the orders the lab holds, max(xh, x) resolves to the lab's held exit bar;
    the trades the paper holds (HOLD lines) are the lab's held trades; trades = the chain's;
  * no refusal in sample (the lab refuses none), F1B unchanged (its trades = the lab's rule);
  * InpK1T: a generated unit program checks Brk72ParseK1T on good and bad strings (values bit for bit against Python's
    float), Brk72K1T and Brk72K1Known, BKB/BKE LatestExit and the Friday 23:54 server end against zoneinfo; through the
    EA itself, a bad InpK1T stops OnInit with an ERROR line, and with a good one every K1 line carries the input's T;
  * the folds on the rebuilt frames against the official frames (listed);
  * the sanitizer build replays the same bars with the switches on with an identical journal.
Outputs: check/out/test_E/test_changes.json.
"""
import argparse
import json
import os
import subprocess
import sys
import time
from zoneinfo import ZoneInfo

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import compare  # noqa: E402
import test_BK as H  # noqa: E402  (step E's harness)

ROBOT, OUT = H.ROBOT, H.OUT
NY = ZoneInfo("America/New_York")
EXPECT = {"BKE": {"et": 0, "xg": 1, "vle": 1, "ref": 2, "xh": 0},
          "BKB": {"et": 0, "xg": 1, "vle": 1, "ref": 1, "xh": 0},
          "F1E": {"et": 0, "xg": 1, "vle": 1, "ref": 1, "xr": 1.0}}


# ======================================================================================== K1
def k1_lines(rows):
    """riskbp and T of every BKE signal the EA decided (skip lines and info lines), by ea_oid"""
    out = {}
    for r in rows:
        if r["ev"] == "DEC" and r["code"] == "BKE" and H.what_of(r) in ("skip", "info"):
            out[int(r["utc"]) * 100 + 4] = (H.what_of(r), float(r["v1"]), float(r["v2"]))
    return out


def cmp_k1(rows, files, folds_T):
    sig = files["signals"].copy()
    lab_skip = set(int(x) for x in sig.loc[sig["skip"], "ea_oid"])
    ea = k1_lines(rows)
    ea_skip = set(k for k, v in ea.items() if v[0] == "skip")
    idx = H.frame_secs("ethusd")
    common = [k for k in sig.ea_oid.astype(np.int64) if int(k) in ea]
    s = sig.set_index(sig.ea_oid.astype(np.int64))
    rb_lab = s.loc[common, "riskbp"].to_numpy(float)
    rb_ea = np.array([ea[int(k)][1] for k in common])
    T_ea = np.array([ea[int(k)][2] for k in common])
    T_exp = np.array([folds_T.get(pd.Timestamp(int(k) // 100, unit="s", tz="UTC").year, 0.0) for k in common])
    rd = H.rel_diff(rb_lab, rb_ea)
    missing = sorted(set(int(k) for k in sig.ea_oid) - set(ea))
    # EA signals the lab's table does not have: no kept bar in [D, D + 5 min], or void (exit bar not after the entry bar)
    extra = sorted(set(ea) - set(int(k) for k in sig.ea_oid))
    D = np.array([k // 100 for k in extra], np.int64)
    ai = H.act_bar(idx, D, D + 300) if len(D) else np.array([], np.int64)
    xi = H.exit_bar(idx, D + 86400, True) if len(D) else np.array([], np.int64)
    extra_unexplained = [int(k) for k, a, x in zip(extra, ai, xi) if a >= 0 and x > a]
    razors = [{"ea_oid": int(k), "riskbp": float(r), "T": float(t)} for k, r, t in zip(common, rb_lab, T_exp)
              if t > 0 and abs(r - t) <= 1e-9 * t]
    near = float(np.min(np.abs(rb_lab - T_exp)[T_exp > 0] / T_exp[T_exp > 0])) if (T_exp > 0).any() else None
    res = {"lab_signals": int(len(sig)), "lab_skipped": len(lab_skip), "ea_signal_lines": len(ea), "ea_skipped": len(ea_skip),
           "skip_same": len(lab_skip & ea_skip), "skip_only_lab": sorted(lab_skip - ea_skip)[:10],
           "skip_only_ea_with_a_lab_signal": sorted((ea_skip - lab_skip) & set(int(k) for k in sig.ea_oid))[:10],
           "skip_only_ea_without_lab_signal": len((ea_skip - lab_skip) - set(int(k) for k in sig.ea_oid)),
           "signals_missing_in_ea": missing[:10], "ea_extra_signals": len(extra), "ea_extra_unexplained": extra_unexplained[:10],
           "riskbp_bit_equal": int((rd == 0).sum()), "riskbp_compared": int(len(rd)),
           "riskbp_max_rel_diff": float(rd.max()) if len(rd) else 0.0, "T_wrong": int((T_ea != T_exp).sum()),
           "razors_within_1e-9": razors, "closest_relative_distance_to_T": near}
    res["pass"] = bool(lab_skip == (ea_skip & set(int(k) for k in sig.ea_oid)) and not missing and not extra_unexplained
                       and (rd <= H.REL).all() and (T_ea == T_exp).all())
    return res


# ======================================================================================== H2
def cmp_h2(rows, ea_orders, files, info):
    """xh of every order, the held orders' exit bars, and the trades the paper holds"""
    idx = H.frame_secs("ethusd")
    ea = ea_orders.copy()
    o = files["orders"].set_index("ea_oid")
    held = [int(k) for k in info["held_ea_oids"]]
    # the lab's xh times (variants.info: ny_clock(BDay(date, 2), 15:55) and common.friday_close_time(entry)), each order
    bad_xh = 0
    for oid, xh in zip(ea.index, ea.xh):
        t = int(oid) // 100
        ny = pd.Timestamp(t, unit="s", tz="UTC").tz_convert(NY)
        d2 = (pd.Timestamp(ny.year, ny.month, ny.day) + pd.offsets.BDay(2))
        xa = int(pd.Timestamp(d2.year, d2.month, d2.day, 15, 55, tz=NY).tz_convert("UTC").value // 10**9)
        srv = pd.Timestamp(t, unit="s", tz="UTC").tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
        fri = srv.normalize() + pd.Timedelta(days=4 - srv.dayofweek) + pd.Timedelta(hours=23, minutes=54)
        xb = int((fri - pd.Timedelta(hours=7)).tz_localize(NY).tz_convert("UTC").value // 10**9)
        bad_xh += int(xh != min(xa, xb))
    hx = ea.loc[[k for k in held if k in ea.index]]
    xi_h = H.exit_bar(idx, np.maximum(hx.xh.to_numpy(np.int64), hx.x.to_numpy(np.int64)), True)
    lab_xi = o.loc[hx.index, "exit_i"].to_numpy(np.int64)
    held_exit_wrong = [int(k) for k, a, b in zip(hx.index, xi_h, lab_xi) if a != b]
    # the paper's holds: the last HOLD line of each oid (px > 0 granted, px = 0 withdrawn), for the chain's trades
    last = {}
    for r in rows:
        if r["ev"] == "HOLD" and r["code"] == "F1E":
            last[int(r["oid"])] = float(r["px"]) > 0
    voided = set(compare.paper_chain(rows, "F1E")[1])
    ea_held = sorted(k for k, v in last.items() if v and k not in voided)
    lab_held = sorted(int(k) for k in info["held_trades_ea_oids"])
    res = {"orders": int(len(ea)), "xh_wrong": bad_xh, "lab_held_orders": len(held), "held_orders_in_ea": int(len(hx)),
           "held_exit_bar_wrong": held_exit_wrong[:10], "lab_held_trades": len(lab_held), "ea_held_trades": len(ea_held),
           "held_only_lab": sorted(set(lab_held) - set(ea_held))[:10], "held_only_ea": sorted(set(ea_held) - set(lab_held))[:10],
           "hold_lines": sum(1 for r in rows if r["ev"] == "HOLD" and r["code"] == "F1E"),
           "holds_withdrawn": sum(1 for v in last.values() if not v)}
    res["pass"] = bool(bad_xh == 0 and len(hx) == len(held) and not held_exit_wrong and set(lab_held) == set(ea_held))
    return res


# ======================================================================================== unit checks of the parser
CASES_GOOD = ["", "2019:505.84441393264945;2020:496.6915507295559;2021:465.14468666253265", " 2021 : 465.1 ; ", "2021:0",
              "2022:478.284;;2023:1e2", "2021:465.14468666253265;2019:1", "2024:4.6511781401054350e+02", "2100:7;2000:0.5"]
CASES_BAD = ["2021", "2021:", ":465", "21:465", "2021:-5", "2021:abc", "2021:4 65", "2021:465;2021:470", "1999:5", "2101:5",
             "2021:465:1", "2021:.5", "2021:5.", "2021:1e", "2021:inf", "2021:nan", "2021,465", "2021:+5", "20x1:5",
             ";".join(f"{2000 + k}:1" for k in range(65))]


def py_parse(s):
    """the parser's rules, in Python (expected results)"""
    import re
    out = []
    t = s.strip()
    if not t:
        return out
    for e in t.split(";"):
        e = e.strip()
        if not e:
            continue
        if e.count(":") != 1:
            return None
        y, v = (x.strip() for x in e.split(":"))
        if not re.fullmatch(r"\d{4}", y) or not 2000 <= int(y) <= 2100:
            return None
        if not re.fullmatch(r"\d+(\.\d+)?([eE][+-]?\d+)?", v):
            return None
        if any(int(y) == a for a, _ in out) or len(out) >= 64:
            return None
        out.append((int(y), float(v)))
    return out


UNIT_K1 = r"""
#include <cstdio>
#include <string>
int main(int argc, char **argv)
  {
   // argv[1]: one InpK1T case per line; prints "OK n y:T ..." (T with 17 digits) or "BAD why"
   FILE *f = fopen(argv[1], "r");
   if(!f) return 2;
   char buf[8192];
   while(fgets(buf, sizeof(buf), f))
     {
      std::string s(buf);
      while(!s.empty() && (s.back() == '\n' || s.back() == '\r')) s.pop_back();
      if(s == "<EMPTY>") s = "";
      string why = "";
      bool ok = Brk72ParseK1T(s, why);
      if(!ok) { printf("BAD %s\n", why.c_str()); continue; }
      printf("OK %d", g_brk_k1_n);
      for(int j = 0; j < g_brk_k1_n; j++) printf(" %d:%.17g:%d", g_brk_k1_year[j], Brk72K1T(g_brk_k1_year[j]), Brk72K1Known(g_brk_k1_year[j]) ? 1 : 0);
      printf("\n");
     }
   fclose(f);
   // LatestExit of BKB / BKE and the Friday end: argv[2] = rows "open_time comment_dec"
   FILE *g = fopen(argv[2], "r");
   if(!g) return 3;
   long o = 0, c = 0;
   CRuleBrk72 q;
   while(fscanf(g, "%ld %ld", &o, &c) == 2) printf("LX %ld %ld %ld %ld\n", o, c, (long)q.LatestExit(o, c), (long)Brk72FridayEnd(o));
   fclose(g);
   return 0;
  }
"""


def friday_end_py(t):
    """payoff common.friday_close_time for one UTC instant (seconds)"""
    srv = pd.Timestamp(t, unit="s", tz="UTC").tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)
    fri = srv.normalize() + pd.Timedelta(days=4 - srv.dayofweek) + pd.Timedelta(hours=23, minutes=54)
    return int((fri - pd.Timedelta(hours=7)).tz_localize(NY).tz_convert("UTC").value // 10**9)


def unit_k1():
    d = os.path.join(OUT, "unit_k1")
    os.makedirs(d, exist_ok=True)
    cases = CASES_GOOD + CASES_BAD
    with open(os.path.join(d, "cases.txt"), "w") as f:
        for c in cases:
            f.write((c if c else "<EMPTY>") + "\n")
    base = [pd.Timestamp(x, tz="UTC") for x in ("2021-03-12 21:00", "2021-03-15 00:00", "2021-11-05 19:02", "2021-11-01 23:09",
                                                 "2020-06-18 20:04", "2019-12-31 08:00", "2018-07-06 18:59", "2021-07-02 20:50")]
    lx_cases = []
    for b in base:
        t = int(b.value // 10**9)
        for off in (0, 299, 600):
            lx_cases.append((t + off, 0))
        lx_cases.append((t + 120, t - t % 3600))
        lx_cases.append((t + 120, t - t % 3600 - 7200))
    with open(os.path.join(d, "latest.txt"), "w") as f:
        for o, c in lx_cases:
            f.write(f"{o} {c}\n")
    exe, warn = H.build_unit("unit_k1", "CR_Rule_Brk72.mqh", UNIT_K1)
    r = subprocess.run([exe, os.path.join(d, "cases.txt"), os.path.join(d, "latest.txt")], capture_output=True, text=True)
    lines = [x for x in r.stdout.split("\n") if x]
    parse_lines = [x for x in lines if not x.startswith("LX")]
    wrong = []
    for c, ln in zip(cases, parse_lines):
        exp = py_parse(c)
        if exp is None:
            if not ln.startswith("BAD"):
                wrong.append({"case": c[:60], "got": ln[:100], "expected": "refused"})
            continue
        got = ln.split()
        if got[0] != "OK" or int(got[1]) != len(exp):
            wrong.append({"case": c[:60], "got": ln[:100], "expected": exp})
            continue
        for (y, v), item in zip(exp, got[2:]):
            yy, vv, kn = item.split(":")
            if int(yy) != y or float(vv) != v or int(kn) != int(v > 0):
                wrong.append({"case": c[:60], "got": item, "expected": [y, v]})
    lx_wrong = []
    for ln in [x for x in lines if x.startswith("LX")]:
        o, c, x, fe = (int(v) for v in ln.split()[1:])
        D = o - o % 3600
        if c > 0 and c % 3600 == 0 and c <= o and o - c <= 600:
            D = c
        exp_fe = friday_end_py(o)
        if fe != exp_fe or x != min(D + 86400, exp_fe):
            lx_wrong.append([o, c, x, fe, min(D + 86400, exp_fe), exp_fe])
    res = {"build_warnings": warn, "exit": r.returncode, "cases": len(cases), "good": len(CASES_GOOD), "bad": len(CASES_BAD),
           "parse_wrong": wrong, "latest_exit_cases": len(lx_cases), "latest_exit_wrong": lx_wrong[:10]}
    res["pass"] = bool(r.returncode == 0 and not warn and len(parse_lines) == len(cases) and not wrong
                       and len([x for x in lines if x.startswith("LX")]) == len(lx_cases) and not lx_wrong)
    return res


def k1t_through_the_ea(exe, k1t_good):
    """the input path: a bad InpK1T stops OnInit with an ERROR line; with a good one the EA runs and every K1 line of
    2021 carries T(2021) of the input to the last bit (ten days of March 2021, server time)"""
    t0 = int(pd.Timestamp("2021-03-01 00:00").value // 10**9)
    out = {}
    for name, val, days in (("bad_duplicate", "2021:465;2021:470", 2), ("bad_text", "2021:abc", 2), ("good", k1t_good, 10)):
        files = os.path.join(OUT, f"k1t_{name}")
        env = dict(os.environ, MOCK_FILES=files, MOCK_SYMS=",".join(H.SYMS), MOCK_QUIET="1", MOCK_INPUT_InpK1T=val,
                   MOCK_INPUT_InpK1="1", MOCK_INPUT_InpTrade="false", MOCK_FROM=str(t0), MOCK_TO=str(t0 + days * 86400))
        for k, v in H.bars().items():
            env[f"MOCK_BARS_{k}"] = v
        if os.path.isdir(files):
            subprocess.run(["rm", "-rf", files], check=True)
        os.makedirs(files)
        r = subprocess.run([exe], env=env, capture_output=True, text=True, timeout=600)
        rows = compare.read_journal(files) if compare.journal_files(files) else []
        errs = [x for x in rows if x["ev"] == "ERROR"]
        k1 = [float(x["v2"]) for x in rows if x["ev"] == "DEC" and x["code"] == "BKE" and H.what_of(x) in ("skip", "info")]
        out[name] = {"exit": r.returncode, "stderr": r.stderr.strip()[-200:], "errors": [str(e.get("what"))[:120] for e in errs[:3]],
                     "k1_lines": len(k1), "k1_T_values": sorted(set(k1))}
    t21 = dict((int(y), float(v)) for y, v in (e.split(":") for e in k1t_good.split(";"))).get(2021)
    g = out["good"]
    out["good_T_exact"] = bool(g["k1_lines"] > 0 and g["k1_T_values"] == [t21])
    ok = (out["bad_duplicate"]["exit"] == 3 and any("InpK1T refused" in e for e in out["bad_duplicate"]["errors"])
          and out["bad_text"]["exit"] == 3 and any("InpK1T refused" in e for e in out["bad_text"]["errors"])
          and g["exit"] == 0 and not g["errors"] and out["good_T_exact"])
    out["pass"] = bool(ok)
    return out


# ======================================================================================== main
def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-sanitize", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    res = {"test": "T5 crypto changes K1, S0.75r, H2 (switches on)", "per_change": {}}
    ch = {c: H.change_ref(c) for c in ("K1", "S0.75r", "H2")}
    ch_off = H.change_ref("K1", "official")
    k1t = ch["K1"][0]["k1t_input"]
    folds_T = {int(y): float(f["q_hi"]) for y, f in ch["K1"][0]["folds"].items() if f["skip"] == "hi"}
    res["k1_folds"] = {"rebuilt": ch["K1"][0]["folds"], "official": ch_off[0]["folds"], "inpk1t_rebuilt": k1t,
                       "inpk1t_official": ch_off[0]["k1t_input"],
                       "max_abs_T_diff_bp": max(abs(float(ch["K1"][0]["folds"][y]["q_hi"]) - float(ch_off[0]["folds"][y]["q_hi"]))
                                                for y in ch["K1"][0]["folds"])}
    exe, warn = H.build_ea(False)
    res["tree"] = H.tree()["origin"]
    res["build_warnings"] = warn
    inputs = {"InpTrade": "false", "InpK1": "1", "InpH2": "1", "InpS075": "1", "InpK1T": k1t}
    rows, out, wall, files = H.replay(exe, "on", inputs)
    res["replay"] = {"stdout": out, "wall_s": round(wall, 1), "errors": H.errors(rows)[:5], "inputs": inputs}
    ok = not warn and not res["replay"]["errors"]
    fm, last = H.first_minute(rows), H.manifest_last()
    for cid, code in (("K1", "BKE"), ("S0.75r", "BKB"), ("H2", "F1E")):
        info, files_c = ch[cid]
        sym = H.LAB_SYM[code]
        lab_orders = files_c["orders"] if cid != "H2" else files_c["rule_orders"]
        ro, ea = H.cmp_orders(rows, code, lab_orders, sym, EXPECT[code])
        rt = H.cmp_trades(rows, code, files_c["trades"], fm, last[H.BROKER[sym]] - 1)
        c = H.counts(rows, code)
        n_ref = c.get("PREFUSE", 0)
        lab_ref = info.get("refused_3spreads", 0) + info.get("refused_orders", 0) + info.get("refused_alone", 0)
        r = {"orders": ro, "trades": rt, "journal_counts": c, "prefuse_ea": n_ref, "refused_lab": lab_ref,
             "lab": {k: info[k] for k in ("orders_rule", "orders_change", "trades", "R_sum", "note")}}
        good = ro["pass"] and rt["pass"] and n_ref == lab_ref
        if cid == "K1":
            r["k1"] = cmp_k1(rows, files_c, folds_T)
            good &= r["k1"]["pass"]
        if cid == "H2":
            r["h2"] = cmp_h2(rows, ea, files_c, info)
            good &= r["h2"]["pass"]
        r["pass"] = bool(good)
        res["per_change"][cid] = r
        ok &= good
        print(f"{cid} ({code}): orders lab {ro['lab_orders']} EA {ro['ea_orders']} matched {ro.get('matched')} wrong {ro.get('wrong')} "
              f"only_lab {ro.get('only_lab')} | EA extra: no bar {ro.get('only_ea_no_bar_in_window')} void {ro.get('only_ea_void')} "
              f"unexplained {ro.get('only_ea_unexplained')} | stop_dist bit-equal {ro.get('stop_dist_bit_equal')} max rel "
              f"{ro.get('stop_dist_max_rel_diff', 0):.3g} | trades lab {rt.get('lab_trades')} EA {rt.get('ea_trades')} same "
              f"{rt.get('same_exit_and_reason')} entry/stop/exit bit-equal {rt.get('entry_equal')}/{rt.get('stop_equal')}/"
              f"{rt.get('exit_equal')} | refusals EA {n_ref} lab {lab_ref} | {'PASS' if good else 'FAIL'}", flush=True)
        if cid == "K1":
            k = r["k1"]
            print(f"     K1: signals lab {k['lab_signals']} skipped lab {k['lab_skipped']} EA {k['ea_skipped']} same {k['skip_same']} "
                  f"| riskbp bit-equal {k['riskbp_bit_equal']}/{k['riskbp_compared']} max rel {k['riskbp_max_rel_diff']:.3g} "
                  f"| T wrong {k['T_wrong']} | razors {len(k['razors_within_1e-9'])} (closest {k['closest_relative_distance_to_T']})",
                  flush=True)
        if cid == "H2":
            h = r["h2"]
            print(f"     H2: xh wrong {h['xh_wrong']} | held orders lab {h['lab_held_orders']} exit bar wrong {len(h['held_exit_bar_wrong'])} "
                  f"| held trades lab {h['lab_held_trades']} EA {h['ea_held_trades']} | HOLD lines {h['hold_lines']} withdrawn "
                  f"{h['holds_withdrawn']}", flush=True)
    # the 2018-02..2021 window of SPEC 3 (entries 2018-02-01 to 2021-12-31): off -> on, EA and lab (rebuilt frames)
    rows_off, _, _, _ = H.replay(exe, "off", H.SWITCHES_OFF)
    w0, w1 = pd.Timestamp("2018-02-01", tz="UTC"), pd.Timestamp("2022-01-01", tz="UTC")
    win = {}
    for cid, code in (("K1", "BKE"), ("S0.75r", "BKB"), ("H2", "F1E")):
        def n_in(t):
            return int(((t.entry_time >= w0) & (t.entry_time < w1)).sum()) if len(t) else 0
        lab_base = ch[cid][1]["base"] if cid == "K1" else H.lab_ref(code)[2]
        win[cid] = {"ea_off": n_in(compare.paper_trades(rows_off, code)), "ea_on": n_in(compare.paper_trades(rows, code)),
                    "lab_off": n_in(lab_base), "lab_on": n_in(ch[cid][1]["trades"])}
        if cid == "H2":
            ht = set(int(k) for k in ch[cid][0]["held_trades_ea_oids"])
            t = ch[cid][1]["trades"]
            win[cid]["lab_held"] = int(t[(t.entry_time >= w0) & (t.entry_time < w1)].ea_oid.isin(ht).sum())
    res["window_2018_02_2021"] = win
    print(f"window 2018-02..2021 (off -> on): " + ", ".join(f"{k} EA {v['ea_off']} -> {v['ea_on']} lab {v['lab_off']} -> {v['lab_on']}"
                                                         for k, v in win.items()), flush=True)
    # F1B is not touched by the switches
    i_f1b, o_f1b, t_f1b = H.lab_ref("F1B")
    rt = H.cmp_trades(rows, "F1B", t_f1b, fm, last["BTCUSD.r"] - 1)
    res["F1B_unchanged"] = rt
    ok &= rt["pass"]
    print(f"F1B (no change): trades lab {rt.get('lab_trades')} EA {rt.get('ea_trades')} same {rt.get('same_exit_and_reason')} | "
          f"{'PASS' if rt['pass'] else 'FAIL'}", flush=True)
    res["unit_k1"] = unit_k1()
    ok &= res["unit_k1"]["pass"]
    print(f"unit: InpK1T parser {res['unit_k1']['cases']} cases ({res['unit_k1']['good']} good, {res['unit_k1']['bad']} bad), wrong "
          f"{len(res['unit_k1']['parse_wrong'])}; LatestExit {res['unit_k1']['latest_exit_cases']} cases, wrong "
          f"{len(res['unit_k1']['latest_exit_wrong'])} | {'PASS' if res['unit_k1']['pass'] else 'FAIL'}", flush=True)
    res["k1t_input_path"] = k1t_through_the_ea(exe, k1t)
    ok &= res["k1t_input_path"]["pass"]
    kp = res["k1t_input_path"]
    print(f"InpK1T through the EA: bad -> exit {kp['bad_duplicate']['exit']}/{kp['bad_text']['exit']}, good -> exit "
          f"{kp['good']['exit']}, {kp['good']['k1_lines']} K1 lines with T(2021) exact {kp['good_T_exact']} | "
          f"{'PASS' if kp['pass'] else 'FAIL'}", flush=True)
    if not a.no_sanitize:
        exe_s, warn_s = H.build_ea(True)
        rows_s, out_s, wall_s, files_s = H.replay(exe_s, "on_san", inputs)
        same = H.journals_identical(files, files_s)
        res["sanitizer"] = {"build_warnings": warn_s, "stdout": out_s, "wall_s": round(wall_s, 1), "journal_identical": same}
        ok &= same and not warn_s
        print(f"sanitizer: warnings {len(warn_s)} journal identical {same} ({wall_s:.0f} s)", flush=True)
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t0, 1)
    H.write("test_changes.json", res)
    print(f"test_changes: {'PASS' if ok else 'FAIL'} ({res['sec']} s) -> {os.path.relpath(os.path.join(OUT, 'test_changes.json'), ROBOT)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
