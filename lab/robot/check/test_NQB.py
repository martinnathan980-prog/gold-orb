"""T4 NQB nq_btc_follow (step F): every decision, every trade and every sigma of NQB over the whole in-sample period.

    python3 -I lab/robot/check/test_NQB.py [--world all|is|holes|restarts] [--no-sanitize] [--sanitize-holes] [--fresh]
                                           [--verbose]

SPEC 7 T4/T5 for src/CR_Rule_NqBtc.mqh, and SPEC 8 row F: "sigma within 1e-12 of the lab's rolling RMS".
Robot side: a private tree, build/test_NQB/src (SPEC 8: the finished files of S0, A, B, C and I as they are in src/, this
step's CR_Rule_NqBtc.mqh, and the S0 stubs of the steps running beside F (D, E, G, H, J, K), read from commit 7b87227
with git show), made into one file by tools/amalgam.py (--out build/test_NQB/dist, never dist/), translated by
check/to_cpp.py and compiled with the spec's flags (CR_HARNESS, CR_XAU_COMM_PTS=0) against S0's mock and shim and J's
mock_faults.h stub. Lab side: the lab's own code on the frames rebuilt from the same bars (export_frames.py --tag is),
with strategy.set_leader("us100", <the US100 frame of the same world>) before every call and clear_leaders() after (P2):
make_orders (every signal) and r2.run(sym, make_orders, params, "fp", True, m1), in a fresh process per world (P8); and,
in this process, the helpers xlead_orders itself calls (_grid, _on_grid, _ffill, _lret, _trail_rms, _clock, _sess_mask),
in its own order, for the values of every grid minute.
Two levels:
  unit  the rule alone (CRuleNqb: the tree's file translated with what it includes) in a generated driver that feeds it
        the kept bars of US100 and BTC as CR_Main does (OnBar for each bar in (time, symbol) order, then OnMinute(M),
        every minute) and writes, for every grid minute, x = r_US100, sigma_L, r_BTC and sigma_B, and every order and DEC
        info record. Checks: (1) the grid is the lab's (from the first BTC bar); (2) x and r equal the lab's np.log returns,
        except where numpy's log and the C library's log differ by one unit in the last place (counted), and equal bit
        for bit the lab's formula taken with the C library's log (math.log, the log MathLog calls in the harness); (3)
        sigma_L and sigma_B equal the lab's _trail_rms within 1e-12 relative on every grid minute, NaN at the same
        minutes, and bit for bit when the lab's arrays are built with the C library's log; (4) the signals are the lab's
        decision minutes one for one, with x equal and sigma_L within 1e-12; (5) the orders, read as the paper reads a
        CrOrder, equal make_orders' orders: entry bar, side and exit bar equal, stop_dist within 1e-12; (6) the sanitizer
        build (world is) writes the same bytes.
  ea    the whole EA (the private single file) replays the bars of the four symbols through the S0 driver, InpTrade false
        (SPEC 8: no order is sent). Checks: (1) the journal parses and keeps S0's replay contract (INIT, SELFTEST ok,
        PLAN, 4 READY, REBUILD per start; no ERROR, no SEND), and the builds (harness, release, debug, sanitizer) have no
        warning; (2) every NQB DEC info line is a lab decision minute and every lab decision has one, with x equal or one
        unit in the last place and sigma_L within 1e-12; the DEC order lines, read as the paper reads a CrOrder
        (activation = the first kept bar in [t_from, t_to]; exit = gl.exit_index of x_sched; void when the exit bar does
        not follow the activation bar), give per oid the lab's order (entry bar, side, exit bar, stop_dist within 1e-12),
        or no order for the lab's own reason (no BTC bar in [g + 1, g + 2]; exit_i <= entry_i); (3) trades:
        compare.cmp_trades (entry and exit minute, side, reason equal; entry, stop and exit within 1e-12) on every lab
        trade that ends before the frame's last bar; (4) razors listed: lab decisions within 1e-9 of the 6-sigma
        threshold, lab trades whose stop lies within 1e-9 of a bar extreme it was tested against; (5) world is: the
        sanitizer build writes a byte-identical journal.
Worlds:
  is        the in-sample bars (2013-2021; BTC from 2017-05-07). Also listed: the lab trades on the rebuilt frames against
            the official trades (results/r2/recalc, entries before 2022), with their cause (SPEC 7: the export rounds the
            bid to 2 digits).
  holes     the same frames with holes cut in, aimed at the paths in-sample data barely reaches, chosen from the lab's
            own decisions and trades: entry bar g + 1 missing (second entry minute), g + 1 and g + 2 missing (no entry),
            no BTC bar from just after the entry to x + 30 min (void_le: the lab drops the order), exits falling back
            before a hole (PREVISE), an exit bar at exactly x + 30 min and one at x + 31 min, the decision's BTC bar
            missing, BTC and US100 forward fills of 3 minutes (kept) and 4 minutes (not), the decision's US100 bar
            missing, a 17-day BTC hole and a 17-day US100 hole (fewer than 4,800 returns: sigma NaN), and random holes.
            The unit level takes the BTC and US100 holes; the EA level the BTC ones (US100 holes add no paper path).
            Each level has its own lab references on its own frames. Every targeted path must be reached.
  restarts  unit: the rule started afresh from 60 days of history (SPEC 2.2 depth) at 12 times and compared over the
            next 10 days (decisions and orders equal, sigma within 1e-12); ea: the in-sample bars replayed in segments
            (MOCK_FROM / MOCK_TO), each start rebuilding from the depth, compared on the lines the live passes wrote.
Outputs: check/out/test_NQB/ (<world>_result.json, journals); builds under build/test_NQB/. In sample only: every frame
and trade file is read with the 2022-01-01 cut inside the read call.
"""
import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
os.environ.setdefault("PYTHONDONTWRITEBYTECODE", "1")
_NB = os.environ.get("NUMBA_CACHE_DIR", "")
if not _NB.startswith("/tmp/"):
    _NB = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba"
os.environ["NUMBA_CACHE_DIR"] = _NB

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
sys.path.insert(0, HERE)
import build as B  # noqa: E402
import compare  # noqa: E402
import export_frames as EF  # noqa: E402

OUT = os.path.join(HERE, "out", "test_NQB")
TREE = os.path.join(ROBOT, "build", "test_NQB")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
NY = "America/New_York"
STUB_COMMIT = "7b87227"                 # the end of part 1: the files of D, E, G, H, J and K are S0's stubs there
OWN = ("CR_Rule_NqBtc.mqh",)
FINISHED = ("ClaudeRobot.mq5", "CR_Types.mqh", "CR_Registry.mqh", "CR_Journal.mqh", "CR_Main.mqh", "CR_Rule_Script.mqh",
            "CR_Clock.mqh", "CR_Math.mqh", "CR_Bars.mqh", "CR_Paper.mqh", "CR_Ledger.mqh", "CR_Sizing.mqh")
PARALLEL = ("CR_Rule_IdxUS.mqh", "CR_Rule_Brk72.mqh", "CR_Rule_F1.mqh", "CR_F1Model.mqh", "CR_Rule_GoldFri.mqh",
            "CR_Rule_Orb.mqh", "CR_Rule_Donch.mqh", "CR_Broker.mqh", "CR_Follower.mqh", "CR_Guards.mqh", "CR_Golden.mqh")
SYMS = ("XAUUSD.r", "US100.r", "BTCUSD.r", "ETHUSD.r")
CODE, SID = "NQB", 7
REL = 1e-12                             # SPEC 7: rolling values and the stops built on them
RAZOR = 1e-9                            # SPEC 7: decisions this close to a threshold are listed
DEPTH_S = 60 * 86400                    # SPEC 2.2: 60 days of BTC and US100 history at a start
SEED = 20261113


def log(msg):
    print(msg, flush=True)


def secs(ts):
    return pd.DatetimeIndex(ts).tz_convert("UTC").as_unit("s").asi8.astype(np.int64)


def ny_str(t):
    return str(pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(NY))[:16]


def rel_diff(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    den = np.maximum(np.abs(a), np.abs(b))
    return np.where(a == b, 0.0, np.abs(a - b) / np.where(den > 0, den, 1.0))


def sha_files(paths, extra=""):
    h = hashlib.sha256(extra.encode())
    for p in paths:
        h.update(open(p, "rb").read())
    return h.hexdigest()


# ======================================================================================== the private tree and builds
def git_stub(rel):
    """a file as it was at STUB_COMMIT (S0's stub), read with git show (read only)"""
    r = subprocess.run(["git", "-C", ROBOT, "show", f"{STUB_COMMIT}:./{rel}"], capture_output=True)
    if r.returncode:
        raise RuntimeError(f"git show {STUB_COMMIT}:{rel} failed: {r.stderr.decode()[-500:]}")
    if b"S0 STUB" not in r.stdout:
        raise RuntimeError(f"{rel} at {STUB_COMMIT} is not an S0 stub")
    return r.stdout


def make_tree():
    src, har, dist = (os.path.join(TREE, d) for d in ("src", "harness", "dist"))
    for d in (src, har, dist):
        if os.path.isdir(d):
            shutil.rmtree(d)
        os.makedirs(d)
    names = {n for n in os.listdir(os.path.join(ROBOT, "src")) if n.endswith((".mqh", ".mq5"))}
    want = set(OWN + FINISHED + PARALLEL)
    if names != want:
        raise RuntimeError(f"src/ has unknown files {sorted(names - want)} or misses {sorted(want - names)}")
    origin = {}
    for n in OWN + FINISHED:
        shutil.copy(os.path.join(ROBOT, "src", n), os.path.join(src, n))
        origin[n] = "src/"
    for n in PARALLEL:
        with open(os.path.join(src, n), "wb") as f:
            f.write(git_stub(f"src/{n}"))
        origin[n] = f"git {STUB_COMMIT} (S0 stub)"
    for n in ("mock_replay.h", "mql5_shim.h"):
        shutil.copy(os.path.join(HERE, n), os.path.join(har, n))
    with open(os.path.join(har, "mock_faults.h"), "wb") as f:
        f.write(git_stub("check/mock_faults.h"))
    origin["mock_faults.h"] = f"git {STUB_COMMIT} (S0 stub)"
    r = subprocess.run([sys.executable, "-I", os.path.join(ROBOT, "tools", "amalgam.py"), "--src", os.path.join(src, "ClaudeRobot.mq5"),
                        "--out", dist], capture_output=True, text=True)
    if r.returncode:
        raise RuntimeError("amalgam refused the tree:\n" + r.stderr)
    return {"src": src, "harness": har, "dist": os.path.join(dist, "ClaudeRobot.mq5"),
            "dist_debug": os.path.join(dist, "ClaudeRobot_debug.mq5"), "origin": origin, "amalgam": r.stdout.strip().splitlines()[:2]}


_TREE = {}


def tree():
    if "t" not in _TREE:
        _TREE["t"] = make_tree()
    return _TREE["t"]


def compile_cpp(run_cpp, exe, sanitize, harness=True):
    t = tree()
    cmd = B.CXX + (B.SAN if sanitize else []) + (["-DCR_HARNESS", "-DCR_XAU_COMM_PTS=0"] if harness else []) + \
        ["-I", t["harness"], "-I", os.path.dirname(run_cpp), run_cpp, "-o", exe]
    r = subprocess.run(cmd, capture_output=True, text=True)
    warn = [ln for ln in r.stderr.splitlines() if "warning:" in ln]
    if r.returncode:
        raise B.BuildError(f"compile failed ({exe}):\n" + r.stderr[-20000:])
    return warn


def cached_build(name, key, make):
    """a build under build/test_NQB/<name>, made again only when its key changed; returns (exe, warnings)"""
    work = os.path.join(TREE, name)
    stamp = os.path.join(work, "stamp.json")
    if os.path.exists(stamp):
        old = json.load(open(stamp))
        if old.get("key") == key and os.path.exists(old.get("exe", "")):
            return old["exe"], old["warnings"]
    if os.path.isdir(work):
        shutil.rmtree(work)
    os.makedirs(work)
    exe, warn = make(work)
    with open(stamp, "w") as f:
        json.dump({"key": key, "exe": exe, "warnings": warn}, f)
    return exe, warn


def build_ea(sanitize):
    """the replay binary of the private single file"""
    t = tree()
    har = [os.path.join(t["harness"], n) for n in ("mock_replay.h", "mql5_shim.h", "mock_faults.h")]
    key = sha_files([t["dist"]] + har, repr((sanitize, B.CXX, B.SAN)))

    def make(work):
        B.translate(t["dist"], os.path.join(work, "ea.cpp"))
        run = os.path.join(work, "run.cpp")
        with open(run, "w") as f:
            f.write(f'#include "{har[0]}"\n#include "{os.path.join(work, "ea.cpp")}"\n')
        exe = os.path.join(work, "replay")
        return exe, compile_cpp(run, exe, sanitize)
    return cached_build("ea_san" if sanitize else "ea", key, make)


def build_variants():
    """the private single file as the user gets it (no CR_HARNESS: CR_XAU_COMM_PTS 6) and its debug twin (CR_DEBUG),
    compiled only: every warning is reported"""
    t = tree()
    out = {}
    for name, src, harness in (("release", t["dist"], False), ("debug", t["dist_debug"], True)):
        work = os.path.join(TREE, "variant_" + name)
        if os.path.isdir(work):
            shutil.rmtree(work)
        os.makedirs(work)
        B.translate(src, os.path.join(work, "ea.cpp"))
        run = os.path.join(work, "run.cpp")
        with open(run, "w") as f:
            f.write(f'#include "{os.path.join(t["harness"], "mock_replay.h")}"\n#include "{os.path.join(work, "ea.cpp")}"\n')
        try:
            warn = compile_cpp(run, os.path.join(work, "replay"), False, harness)
            out[name] = {"ok": True, "warnings": warn[:10]}
        except B.BuildError as e:
            out[name] = {"ok": False, "warnings": [], "error": str(e)[-2000:]}
    out["pass"] = all(v["ok"] and not v["warnings"] for v in out.values() if isinstance(v, dict))
    return out


# the unit driver: CRuleNqb alone, fed as CR_Main feeds a rule (written under build/test_NQB/unit*/, git-ignored)
UNIT_MAIN = r"""
// generated by check/test_NQB.py (step F): CRuleNqb alone, fed minute by minute as CR_Main feeds a rule (SPEC 2.4)
//   stdin : int64 n, then n records <int64 t (bar start, UTC s), int32 sym, int32 pad, double bc, double ac> in (t, sym)
//           order (kept bars of US100 and BTC, paper quotes)
//   stdout: one record per grid minute <int64 g (minutes since 1970), double x, sigma_L, r_B, sigma_B>
//   argv[1]: CSV of what the rule emitted (kind ord | info; from 0 OnMinute, 1 OnBar; at = M or the bar start)
#include <cstdio>
#include <cstdint>
#include <vector>

struct NqbIn { int64_t t; int32_t sym; int32_t pad; double bc, ac; };
struct NqbOut { int64_t g; double x, sl, rb, sb; };

static void nqb_rows(FILE *f, const CrOut &out, long at, int from)
  {
   for(int i = 0; i < out.n_dec; i++)
      fprintf(f, "info,%d,%ld,0,%d,0,0,0,0,0,0,%ld,%.17g,%.17g\n", from, at, out.dec[i].side, (long)out.dec[i].dec,
              out.dec[i].v1, out.dec[i].v2);
   for(int i = 0; i < out.n_ord; i++)
     {
      const CrOrder &o = out.ord[i];
      fprintf(f, "ord,%d,%ld,%ld,%d,%ld,%ld,%.17g,%ld,%d,%d,%ld,0,0\n", from, at, (long)o.oid, o.side, (long)o.t_from,
              (long)o.t_to, o.stop_dist, (long)o.x_sched, o.x_gap ? 1 : 0, o.void_le ? 1 : 0, (long)o.dec);
     }
  }

int main(int argc, char **argv)
  {
   if(argc < 2) return 2;
   g_jrn_print = false;
   g_jrn_file = false;
   g_cfg = CrConfig();
   g_cfg.harness = true;
   g_nsl = 1;
   g_sl[0] = CrSleeveInfo();
   g_sl[0].id = 7;
   g_sl[0].code = "NQB";
   g_sl[0].lab = "nq_btc_follow_btcusd";
   g_sl[0].kind = CR_K_NQB;
   g_sl[0].sym = CR_BTC;
   g_sl[0].sym2 = CR_IDX;
   string err = "";
   if(!ClkInit("", err)) return 3;
   static CRuleNqb r;
   if(!r.Init(0)) return 4;
   int64_t n = 0;
   if(fread(&n, 8, 1, stdin) != 1 || n <= 0) return 5;
   std::vector<NqbIn> in((size_t)n);
   if(fread(in.data(), sizeof(NqbIn), (size_t)n, stdin) != (size_t)n) return 6;
   FILE *f = fopen(argv[1], "w");
   if(!f) return 7;
   fprintf(f, "kind,from,at,oid,side,t_from,t_to,stop_dist,x_sched,x_gap,void_le,dec,v1,v2\n");
   std::vector<NqbOut> buf;
   buf.reserve(1 << 16);
   long M = (long)(in[0].t / 60 + 1) * 60;
   long M_end = (long)(in[(size_t)n - 1].t / 60 + 2) * 60;
   size_t k = 0;
   long last_g = -1;
   static CrOut out;
   for(; M <= M_end; M += 60)
     {
      while(k < in.size() && in[k].t < M)
        {
         CrBar b = CrBar();
         b.t = (datetime)in[k].t;
         b.sym = in[k].sym;
         b.bc = in[k].bc;
         b.ac = in[k].ac;
         CrOutClear(out);
         r.OnBar(b.sym, b, out);
         nqb_rows(f, out, (long)b.t, 1);
         k++;
        }
      CrOutClear(out);
      r.OnMinute((datetime)M, out);
      nqb_rows(f, out, M, 0);
      if(r.m_started && r.m_g != last_g)
        {
         NqbOut o;
         o.g = r.m_g;
         o.x = r.m_r[CR_NQB_L];
         o.sl = r.m_sig[CR_NQB_L];
         o.rb = r.m_r[CR_NQB_F];
         o.sb = r.m_sig[CR_NQB_F];
         buf.push_back(o);
         last_g = r.m_g;
         if(buf.size() >= (1u << 16))
           {
            fwrite(buf.data(), sizeof(NqbOut), buf.size(), stdout);
            buf.clear();
           }
        }
     }
   if(!buf.empty()) fwrite(buf.data(), sizeof(NqbOut), buf.size(), stdout);
   fclose(f);
   fflush(stdout);
   // SPEC 4.8 table: NQB's latest exit is the open time + 60 min, whatever the comment says
   long le1 = (long)r.LatestExit((datetime)1600000000, (datetime)0);
   long le2 = (long)r.LatestExit((datetime)1600000000, (datetime)1599999780);
   long le3 = (long)r.LatestExit((datetime)1600000000, (datetime)1700000000);
   fprintf(stderr, "unit: %ld bars, last grid minute %ld, signals %ld, latest exit %ld %ld %ld\n", (long)n, last_g, (long)r.m_signals,
           le1, le2, le3);
   return 0;
  }
"""
UNIT_REC = np.dtype([("t", "<i8"), ("sym", "<i4"), ("pad", "<i4"), ("bc", "<f8"), ("ac", "<f8")])
UNIT_OUT = np.dtype([("g", "<i8"), ("x", "<f8"), ("sl", "<f8"), ("rb", "<f8"), ("sb", "<f8")])


def build_unit(sanitize):
    t = tree()
    srcs = [os.path.join(t["src"], n) for n in ("CR_Rule_NqBtc.mqh", "CR_Types.mqh", "CR_Clock.mqh", "CR_Journal.mqh", "CR_Math.mqh")]
    har = os.path.join(t["harness"], "mock_replay.h")
    key = sha_files(srcs + [har, os.path.join(t["harness"], "mql5_shim.h")], UNIT_MAIN + repr((sanitize, B.CXX, B.SAN)))

    def make(work):
        B.translate(srcs[0], os.path.join(work, "ea.cpp"))
        run = os.path.join(work, "run.cpp")
        with open(run, "w") as f:
            f.write(f'#define MOCK_REPLAY_NO_MAIN\n#include "{har}"\n#include "{os.path.join(work, "ea.cpp")}"\n' + UNIT_MAIN)
        exe = os.path.join(work, "unit")
        return exe, compile_cpp(run, exe, sanitize)
    return cached_build("unit_san" if sanitize else "unit", key, make)


# ======================================================================================== data
def bars_is():
    """the 2013-2021 broker bars of the four symbols (S0's export_frames.py --tag is), exported when missing"""
    p = {s: os.path.join(HERE, "out", "bars", f"{s}_is.bin") for s in SYMS}
    man = os.path.join(HERE, "out", "manifest_is.json")
    if not all(os.path.exists(v) for v in p.values()) or not os.path.exists(man):
        r = subprocess.run([sys.executable, "-I", os.path.join(HERE, "export_frames.py"), "--tag", "is"], capture_output=True, text=True,
                           env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NUMBA_CACHE_DIR=_NB))
        if r.returncode:
            raise RuntimeError("export_frames.py failed:\n" + r.stderr[-3000:])
    return p


_FRAMES = {}


def frame_is(sym):
    """the rebuilt in-sample frame (= the EA's kept bars, T2), read with the 2022 cut inside the read call"""
    if sym not in _FRAMES:
        bars_is()
        m1 = pd.read_parquet(os.path.join(HERE, "out", "frames", f"{sym}_is.parquet"), filters=[("ts", "<", CUT)])
        assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
        _FRAMES[sym] = m1
    return _FRAMES[sym]


def cut_frame(m1, cuts):
    """m1 without the bars starting in any [a, b) of cuts (UTC seconds)"""
    if not cuts:
        return m1
    t = secs(m1.index)
    keep = np.ones(len(t), bool)
    for a, b in cuts:
        keep[np.searchsorted(t, a, "left"):np.searchsorted(t, b, "left")] = False
    return m1[keep]


# ======================================================================================== the lab side
_MOD = {}


def leadlag():
    """the lab's leadlag strategy module, loaded under the name recalc.py gives it"""
    if "S" not in _MOD:
        if LAB not in sys.path:
            sys.path.insert(0, LAB)
        spec = importlib.util.spec_from_file_location("r2_leadlag_strategy", os.path.join(LAB, "r2", "tracks", "leadlag", "strategy.py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules["r2_leadlag_strategy"] = m
        spec.loader.exec_module(m)
        _MOD["S"] = m
    return _MOD["S"]


def lab_params():
    """nq_btc_follow's frozen parameters: FINALISTS plus xlead_orders' own defaults (sig_days, delay)"""
    S = leadlag()
    import inspect
    p = dict(S.FINALISTS["nq_btc_follow"]["params"])
    d = {k: v.default for k, v in inspect.signature(S.xlead_orders).parameters.items() if v.default is not inspect.Parameter.empty}
    for k in ("sig_days", "delay"):
        p.setdefault(k, d[k])
    return p


def constants_check():
    """the rule's #define constants against the lab's frozen parameters (strategy.py:188-189, :328-334, SESSIONS :168)"""
    S = leadlag()
    p = lab_params()
    txt = open(os.path.join(ROBOT, "src", "CR_Rule_NqBtc.mqh")).read()
    c = {m.group(1): float(m.group(2)) for m in re.finditer(r"^#define\s+(CR_NQB_\w+)\s+(-?[0-9.]+)", txt, re.M)}
    clock, a, b, inside = S.SESSIONS[p["sess"]]
    want = {"CR_NQB_Z": float(p["z"]), "CR_NQB_STOP": float(p["stop"]), "CR_NQB_HOLD_MIN": float(p["hold"]),
            "CR_NQB_HOLD_S": 60.0 * p["hold"], "CR_NQB_WIN": float(p["sig_days"] * 1440),
            "CR_NQB_MINOBS": float(p["sig_days"] * 1440 // 6), "CR_NQB_FFILL": 3.0, "CR_NQB_SESS_A": float(a),
            "CR_NQB_SESS_B": float(b), "CR_NQB_DIRN": float(p["dirn"])}
    bad = {k: (c.get(k), v) for k, v in want.items() if c.get(k) != v}
    shape = {"rule": p["rule"] == "xlead", "leader": p["leader"] == "us100", "pred": p["pred"] == "lead", "k": p["k"] == 1,
             "delay": p["delay"] == 0, "session_clock_ny": clock == "ny", "exit_need_not_be_inside": inside is False,
             "ffill_limit_3": S._ffill.__defaults__ == (3,)}
    return {"params": p, "robot": c, "different": bad, "shape": shape, "pass": not bad and all(shape.values())}


def lret_c(c):
    """_lret(c, 1) (strategy.py:122-125) with the C library's log (math.log: the log MathLog calls in the harness)"""
    out = np.full(len(c), np.nan)
    rat = c[1:] / c[:-1]
    ok = np.isfinite(rat) & (rat > 0)
    v = np.full(len(rat), np.nan)
    v[ok] = np.fromiter((math.log(q) for q in rat[ok].tolist()), float, int(ok.sum()))
    out[1:] = v
    return out


def lab_arrays(btc, us):
    """xlead_orders' own steps (strategy.py:190-219), with its helpers, the leader set to this world's US100 frame (P2);
    plus the same returns and sigmas with the C library's log"""
    S = leadlag()
    p = lab_params()
    S.clear_leaders()
    S.set_leader(p["leader"], us)
    try:
        assert p["leader"] in S._LEADERS
        tm, t0, n = S._grid(btc)
        mid_c = ((btc["bc"] + btc["ac"]) / 2).to_numpy(np.float64)
        cF_raw = S._on_grid(tm, mid_c, t0, n)
        hasF = np.isfinite(cF_raw)
        cF = S._ffill(cF_raw)
        win = int(p["sig_days"]) * 1440
        minobs = win // 6
        rF1 = np.where(hasF, S._lret(cF, 1), np.nan)
        sigF1 = S._trail_rms(rF1, win, minobs)
        ltm, lc, _ = S._leader(p["leader"])
        cL_raw = S._on_grid(ltm, lc, t0, n)
        hasL = np.isfinite(cL_raw)
        cL = S._ffill(cL_raw)
        x = np.where(hasL, S._lret(cL, int(p["k"])), np.nan)
        sigX = S._trail_rms(x, win, minobs)
        nym, bem, wd = S._clock(t0, n)
        sess = S._sess_mask(p["sess"], nym, bem, wd, int(p["hold"]))
        sig = sess & np.isfinite(x) & np.isfinite(sigX) & (np.abs(x) >= p["z"] * sigX) & np.isfinite(sigF1) & hasF
        xc = np.where(hasL, lret_c(cL), np.nan)
        rc = np.where(hasF, lret_c(cF), np.nan)
        sigXc = S._trail_rms(xc, win, minobs)
        sigF1c = S._trail_rms(rc, win, minobs)
        assert p["leader"] in S._LEADERS, "the leader was replaced by the default loader"
    finally:
        S.clear_leaders()
    return {"t0": int(t0), "n": int(n), "tm": tm, "hasF": hasF, "hasL": hasL, "x": x, "sigX": sigX, "rF1": rF1, "sigF1": sigF1,
            "xc": xc, "sigXc": sigXc, "rc": rc, "sigF1c": sigF1c, "sess": sess, "sig": sig, "mid_c": mid_c}


REF_CODE = r'''
import json, os, sys
sys.dont_write_bytecode = True
a = json.loads(sys.argv[1])
os.environ["NUMBA_CACHE_DIR"] = a["nb"]
import numpy as np
import pandas as pd
sys.path.insert(0, a["lab"])
sys.path.insert(0, os.path.join(a["lab"], "r2"))
import recalc
from goldlab import r2
reg = {(s[1], s[2]): s for s in recalc.sleeves()}           # once in this fresh process (P8)
track, name, sym, mo, params = reg[("nq_btc_follow", "btcusd")]
S = sys.modules["r2_leadlag_strategy"]
CUT = pd.Timestamp("2022-01-01", tz="UTC")
cuts = json.load(open(a["cuts"])) if a["cuts"] else {"btc": [], "us": []}


def frame(p, cl):
    m1 = pd.read_parquet(p, filters=[("ts", "<", CUT)])
    assert len(m1) and m1.index.max() < CUT
    if cl:
        t = pd.DatetimeIndex(m1.index).as_unit("s").asi8
        keep = np.ones(len(t), bool)
        for x0, x1 in cl:
            keep[np.searchsorted(t, x0, "left"):np.searchsorted(t, x1, "left")] = False
        m1 = m1[keep]
    return m1


btc = frame(a["btc"], cuts["btc"])
us = frame(a["us"], cuts["us"])


def with_leader(fn):
    S.clear_leaders()
    S.set_leader("us100", us)
    assert "us100" in S._LEADERS
    try:
        return fn()
    finally:
        assert "us100" in S._LEADERS, "the leader was replaced by the default loader"
        S.clear_leaders()


orders = with_leader(lambda: mo(btc, **params)).reset_index(drop=True)
trades = with_leader(lambda: r2.run(sym, mo, params, "fp", True, btc))
n = len(btc)
o = orders.copy()
o["entry_t"] = pd.DatetimeIndex(btc.index[np.clip(o.entry_i.to_numpy(), 0, n - 1)]).where(o.entry_i.to_numpy() < n)
xi = o.exit_i.to_numpy()
o["exit_t"] = pd.DatetimeIndex(btc.index[np.clip(xi, 0, n - 1)]).where((xi >= 0) & (xi < n))
os.makedirs(a["out"], exist_ok=True)
o.to_parquet(os.path.join(a["out"], "orders.parquet"))
trades.to_parquet(os.path.join(a["out"], "trades.parquet"))
res = {"btc_bars": int(n), "us100_bars": int(len(us)), "orders": int(len(o)), "trades": int(len(trades)),
       "reasons": {k: int(v) for k, v in trades.reason.value_counts().items()}, "R_sum": float(trades.R.sum()),
       "leader": "set_leader('us100', this world's US100 frame) before each call; the default loader never ran"}
if a["official"]:
    off = pd.read_parquet(os.path.join(a["lab"], "results", "r2", "recalc", "trades", "nq_btc_follow__btcusd.parquet"),
                          filters=[("entry_time", "<", CUT)])
    m = off.merge(trades, on=["entry_time", "side"], how="outer", suffixes=("_off", "_lab"), indicator=True)
    both = m[m._merge == "both"]
    same_x = (both.exit_time_off == both.exit_time_lab) & (both.reason_off == both.reason_lab)
    d = lambda c: float((both[c + "_off"] - both[c + "_lab"]).abs().div(both[c + "_off"].abs()).max()) if len(both) else 0.0
    res["official"] = {"official_trades": int(len(off)), "rebuilt_trades": int(len(trades)), "same_entry_and_side": int(len(both)),
                       "only_official": int((m._merge == "left_only").sum()), "only_rebuilt": int((m._merge == "right_only").sum()),
                       "same_exit_and_reason": int(same_x.sum()), "entry_bit_equal": int((both.entry_off == both.entry_lab).sum()),
                       "stop_bit_equal": int((both.stop_off == both.stop_lab).sum()), "max_rel_entry": d("entry"),
                       "max_rel_stop": d("stop"), "max_rel_exit": d("exit"),
                       "examples_only_official": [str(t) for t in m[m._merge == "left_only"].entry_time.head(5)],
                       "examples_only_rebuilt": [str(t) for t in m[m._merge == "right_only"].entry_time.head(5)],
                       "examples_other_exit": [str(t) for t in both[~same_x].entry_time.head(5)]}
print(json.dumps(res, default=str))
'''


def ref_lab_one():
    """S0's ref_lab.one("NQB", "rebuilt", "is") in a fresh process (P8), its outputs under OUT/ref_lab/rebuilt_is/NQB/"""
    d = os.path.join(OUT, "ref_lab")
    src = (f"import sys, json; sys.dont_write_bytecode = True; sys.path.insert(0, {HERE!r}); import ref_lab; "
           f"ref_lab.OUT = {d!r}; print(json.dumps(ref_lab.one('NQB', 'rebuilt', 'is'), default=str))")
    r = subprocess.run([sys.executable, "-I", "-c", src], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NUMBA_CACHE_DIR=_NB))
    if r.returncode:
        raise RuntimeError("ref_lab.one failed:\n" + r.stderr[-4000:])
    res = json.loads(r.stdout.strip().splitlines()[-1])
    p = os.path.join(d, "rebuilt_is", CODE)
    lo = pd.read_parquet(os.path.join(p, "orders.parquet"))
    lt = pd.read_parquet(os.path.join(p, "trades.parquet"), filters=[("entry_time", "<", CUT)])
    return res, lo, lt


def same_frames(a, b, cols):
    """two lab outputs equal value for value (NaN = NaN) on cols"""
    if len(a) != len(b):
        return False
    for c in cols:
        x, y = a[c].reset_index(drop=True), b[c].reset_index(drop=True)
        if x.dtype.kind == "f":
            if not ((x.to_numpy() == y.to_numpy()) | (np.isnan(x.to_numpy()) & np.isnan(y.to_numpy()))).all():
                return False
        elif not (x == y).all():
            return False
    return True


def lab_ref(name, cuts=None, official=False):
    """make_orders and r2.run on this world's frames, in a fresh process (P8), written under OUT/ref_<name>/ (ref_lab.one's
    calls, plus the holes of a world cut into the frames after the read)"""
    out = os.path.join(OUT, f"ref_{name}")
    cpath = ""
    if cuts:
        os.makedirs(OUT, exist_ok=True)
        cpath = os.path.join(OUT, f"cuts_{name}.json")
        with open(cpath, "w") as f:
            json.dump({"btc": [[int(a), int(b)] for a, b in cuts.get("btc", [])], "us": [[int(a), int(b)] for a, b in cuts.get("us", [])]}, f)
    arg = {"nb": _NB, "lab": LAB, "cuts": cpath, "out": out, "official": official,
           "btc": os.path.join(HERE, "out", "frames", "btcusd_is.parquet"), "us": os.path.join(HERE, "out", "frames", "us100_is.parquet")}
    r = subprocess.run([sys.executable, "-I", "-c", REF_CODE, json.dumps(arg)], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1", NUMBA_CACHE_DIR=_NB))
    if r.returncode:
        raise RuntimeError("reference process failed:\n" + r.stderr[-4000:])
    res = json.loads(r.stdout.strip().splitlines()[-1])
    lo = pd.read_parquet(os.path.join(out, "orders.parquet"))
    lt = pd.read_parquet(os.path.join(out, "trades.parquet"), filters=[("entry_time", "<", CUT)])
    return res, lo, lt


def lab_decisions(la):
    """the lab's decision minutes g (minutes since 1970)"""
    t0 = la["t0"]
    return t0 + np.flatnonzero(la["sig"]).astype(np.int64)


def lab_order_g(lab_o, la):
    """the decision minute of each make_orders order: the minute before its entry bar, or the one before that when the
    entry came at g + 2 (strategy.py:223-226)"""
    e = secs(lab_o.entry_t) // 60
    k1 = e - 1 - la["t0"]
    k2 = e - 2 - la["t0"]
    s1 = np.array([0 <= k < la["n"] and bool(la["sig"][k]) for k in k1], bool)
    s2 = np.array([0 <= k < la["n"] and bool(la["sig"][k]) for k in k2], bool)
    assert (s1 | s2).all(), "a lab order without a decision minute"
    return np.where(s1, e - 1, e - 2).astype(np.int64)


def in_range(la, g_lo, g_hi):
    """la with its decisions kept only in [g_lo, g_hi) (minutes since 1970)"""
    sub = dict(la)
    sig = np.zeros_like(la["sig"])
    a, b = max(g_lo - la["t0"], 0), min(max(g_hi - la["t0"], 0), la["n"])
    sig[a:b] = la["sig"][a:b]
    sub["sig"] = sig
    return sub


def check_derivation(la, lab_o, btc):
    """the orders that the lab arrays give (entry: first BTC bar in [g + 1, g + 2]; side sign(x); stop 2 sigma_B sqrt(60)
    x the mid close of the bar before the entry; exit gl.exit_index(entry + 60 min); exit after entry) = make_orders"""
    gl = leadlag().gl
    tm, t0 = la["tm"], la["t0"]
    g = np.flatnonzero(la["sig"])
    ei = np.searchsorted(tm, t0 + g + 1, side="left")
    ok = ei < len(tm)
    g, ei = g[ok], ei[ok]
    ok = (tm[ei] - (t0 + g + 1)) <= 1
    g, ei = g[ok], ei[ok]
    xi = gl.exit_index(btc, btc.index[ei] + pd.Timedelta(minutes=60))
    sd = 2.0 * la["sigF1"][g] * np.sqrt(60.0) * la["mid_c"][ei - 1]
    side = np.sign(la["x"][g]).astype(np.int64)
    keep = (xi > ei) & np.isfinite(sd) & (sd > 0) & (side != 0)
    same = keep.sum() == len(lab_o) and (ei[keep] == lab_o.entry_i.to_numpy()).all() and (side[keep] == lab_o.side.to_numpy()).all() \
        and (xi[keep] == lab_o.exit_i.to_numpy()).all() and (sd[keep] == lab_o.stop_dist.to_numpy()).all()
    return {"decisions": int(len(np.flatnonzero(la["sig"]))), "with_an_entry_bar": int(len(g)), "orders": int(keep.sum()),
            "equal_to_make_orders_bit_for_bit": bool(same)}


def razors(la, btc, lab_t):
    """lab decisions within 1e-9 of the 6-sigma threshold, and lab trades whose stop came within 1e-9 (relative) of a bar
    extreme it was tested against (the robot's stop may differ by 1e-16 relative: such a bar would decide differently)"""
    v = la["sess"] & np.isfinite(la["x"]) & np.isfinite(la["sigX"]) & np.isfinite(la["sigF1"]) & la["hasF"] & (la["sigX"] > 0)
    thr = 6.0 * la["sigX"][v]
    rel = np.abs(np.abs(la["x"][v]) - thr) / thr
    near = np.flatnonzero(v)[rel <= RAZOR]
    dec = [{"g": ny_str((la["t0"] + int(i)) * 60), "rel": float(r)} for i, r in zip(near, rel[rel <= RAZOR])]
    ts = secs(btc.index)
    bl, ah = btc["bl"].to_numpy(), btc["ah"].to_numpy()
    stops, closest = [], np.inf
    for tr in lab_t.itertuples():
        i0 = int(np.searchsorted(ts, int(tr.entry_time.value // 10**9)))
        xs = int(tr.exit_time.value // 10**9) - (0 if tr.reason == "time" else 60)
        i1 = int(np.searchsorted(ts, xs))                     # the exit bar
        hi = i1 if tr.reason == "time" else i1 + 1             # a time exit happens at the exit bar's open, before its stop test
        ext = bl[i0:hi] if tr.side > 0 else ah[i0:hi]
        if not len(ext):
            continue
        r = float(np.min(np.abs(ext - tr.stop)) / abs(tr.stop))
        closest = min(closest, r)
        if r <= RAZOR:
            stops.append({"entry": ny_str(tr.entry_time.value // 10**9), "side": int(tr.side), "reason": tr.reason, "rel": r})
    return {"decisions_within_1e-9": dec, "evaluable_minutes": int(v.sum()), "closest_decision_rel": float(rel.min()) if len(rel) else None,
            "stops_within_1e-9": stops, "closest_stop_rel": closest}


# ======================================================================================== orders read as the paper reads them
def act_bar(idx, tf, tt):
    """the activation bar of [tf, tt]: the first bar starting inside, -1 when none"""
    k = int(np.searchsorted(idx, tf, "left"))
    return k if k < len(idx) and idx[k] <= tt else -1


def exit_bar(idx, x):
    """gl.exit_index (data.py:95-104) on the frame's bar starts: the first bar at or after x, or the bar before when the
    next one starts more than 30 min after x (or there is none)"""
    k = int(np.searchsorted(idx, x, "left"))
    gap = k >= len(idx) or idx[min(k, len(idx) - 1)] - x > 1800
    return k - 1 if gap and k > 0 else k


def resolve(od, idx):
    """per oid, the orders in emission order: the first one with a kept bar in its window is the order that activates
    (the paper's market order; a second order of an oid may only follow a first one whose minute had no BTC bar); its exit
    bar is exit_index(x_sched); void_le when that bar does not follow the activation bar"""
    out, shape_bad = [], []
    for oid, grp in od.sort_values(["oid", "at"], kind="stable").groupby("oid", sort=False):
        rows = list(grp.itertuples())
        dec = int(rows[0].dec)
        r = {"oid": int(oid), "dec": dec, "side": int(rows[0].side), "n_orders": len(rows), "status": "void_window", "entry": None,
             "exit": None, "stop_dist": float(rows[0].stop_dist), "chance": None}
        for k, q in enumerate(rows):
            if int(q.t_from) != dec + 60 * k or int(q.t_to) != int(q.t_from) or int(q.x_sched) != int(q.t_from) + 3600 \
                    or int(q.x_gap) != 1 or int(q.void_le) != 1 or int(q.side) != r["side"] or float(q.stop_dist) != r["stop_dist"] \
                    or k > 1:
                shape_bad.append(int(oid))
        for k, q in enumerate(rows):
            a = act_bar(idx, int(q.t_from), int(q.t_to))
            if a < 0:
                continue
            if k != len(rows) - 1:
                shape_bad.append(int(oid))                 # an order after the one that activated
            x = exit_bar(idx, int(q.x_sched))
            r.update({"chance": k + 1, "entry": int(idx[a]), "exit": int(idx[x]) if 0 <= x < len(idx) else None})
            r["status"] = "void_le" if x <= a else "ok"
            break
        out.append(r)
    return out, sorted(set(shape_bad))


def cmp_orders(res, lab_o, idx):
    """the resolved orders against make_orders' orders (entry bar, side, exit bar equal; stop_dist within 1e-12); every
    other one must be void for the lab's own reason, read on the frame"""
    ok = pd.DataFrame([r for r in res if r["status"] == "ok"])
    lab = lab_o.copy()
    lab["entry_s"] = secs(lab.entry_t)
    lab["exit_s"] = secs(lab.exit_t)
    out = {"lab_orders": int(len(lab)), "ea_orders": int(len(ok))}
    if len(ok):
        m = lab.merge(ok, left_on=["entry_s", "side"], right_on=["entry", "side"], how="outer", suffixes=("_lab", "_ea"), indicator=True)
        both = m[m._merge == "both"]
        d = rel_diff(both.stop_dist_lab.to_numpy(), both.stop_dist_ea.to_numpy())
        same_exit = both.exit_s.to_numpy() == both.exit.to_numpy().astype(np.int64)
        out.update({"matched": int(len(both)), "only_lab": int((m._merge == "left_only").sum()), "only_ea": int((m._merge == "right_only").sum()),
                    "same_exit_bar": int(same_exit.sum()), "stop_dist_bit_equal": int((d == 0).sum()),
                    "stop_dist_within_1e-12": int((d <= REL).sum()), "stop_dist_max_rel_diff": float(d.max()) if len(d) else 0.0,
                    "second_entry_minute": int((both.chance == 2).sum()),
                    "examples_only_lab": [ny_str(t) for t in m[m._merge == "left_only"].entry_s.head(8)],
                    "examples_only_ea": [ny_str(t) for t in m[m._merge == "right_only"].entry.head(8)]})
        good = out["only_lab"] == 0 and out["only_ea"] == 0 and out["same_exit_bar"] == len(both) and out["stop_dist_within_1e-12"] == len(both)
    else:
        good = len(lab) == 0
    voids, bad = {}, []
    for r in res:
        if r["status"] == "ok":
            continue
        g1 = r["dec"]
        if r["status"] == "void_window":
            why = "lab: no BTC bar in [g + 1, g + 2]" if act_bar(idx, g1, g1 + 60) < 0 else "unclassified"
        else:
            why = "lab: exit_i <= entry_i (no BTC bar from the entry to x + 30 min)" if exit_bar(idx, r["entry"] + 3600) <= \
                int(np.searchsorted(idx, r["entry"])) else "unclassified"
        voids[why] = voids.get(why, 0) + 1
        if why == "unclassified":
            bad.append({"dec": ny_str(g1), "status": r["status"]})
    out["voids"] = voids
    out["unclassified"] = bad[:10]
    out["pass"] = bool(good) and not bad
    return out


def cmp_signals(dec_g, x, sig_l, la):
    """the rule's signal minutes g with its x and sigma_L against the lab's decision minutes and arrays"""
    lab_g = lab_decisions(la)
    ea_g = np.asarray(dec_g, np.int64)
    s_ea, s_lab = set(ea_g.tolist()), set(lab_g.tolist())
    common = np.array(sorted(s_ea & s_lab), np.int64)
    pos = common - la["t0"]
    out = {"lab_decisions": int(len(lab_g)), "ea_signals": int(len(ea_g)), "duplicates": int(len(ea_g) - len(s_ea)),
           "only_lab": [ny_str(t * 60) for t in sorted(s_lab - s_ea)[:8]], "only_ea": [ny_str(t * 60) for t in sorted(s_ea - s_lab)[:8]],
           "n_only_lab": len(s_lab - s_ea), "n_only_ea": len(s_ea - s_lab)}
    if len(common):
        order = {int(gv): i for i, gv in enumerate(ea_g.tolist())}
        k = np.array([order[int(gv)] for gv in common])
        xe, se = np.asarray(x, float)[k], np.asarray(sig_l, float)[k]
        out["x_bit_equal"] = int((xe == la["x"][pos]).sum())
        out["x_bit_equal_c_log"] = int((xe == la["xc"][pos]).sum())
        out["x_max_rel_diff"] = float(rel_diff(xe, la["x"][pos]).max())
        d = rel_diff(se, la["sigX"][pos])
        out["sigma_L_bit_equal"] = int((d == 0).sum())
        out["sigma_L_max_rel_diff"] = float(d.max())
        out["sigma_L_within_1e-12"] = int((d <= REL).sum())
    out["pass"] = out["n_only_lab"] == 0 and out["n_only_ea"] == 0 and out["duplicates"] == 0 and \
        (not len(common) or (out["sigma_L_within_1e-12"] == len(common) and out["x_max_rel_diff"] <= 2.3e-16))
    return out


def cmp_series(ea, lab):
    """two arrays of one grid: NaN at the same minutes; the finite ones equal, or how far apart"""
    ea, lab = np.asarray(ea, float), np.asarray(lab, float)
    na, nb = np.isnan(ea), np.isnan(lab)
    both = ~na & ~nb
    a, b = ea[both], lab[both]
    d = rel_diff(a, b)
    ulp = (a == b) | (a == np.nextafter(b, np.inf)) | (a == np.nextafter(b, -np.inf))
    return {"nan_mismatch": int((na != nb).sum()), "finite": int(both.sum()), "bit_equal": int((a == b).sum()),
            "within_1_ulp": int(ulp.sum()), "max_rel_diff": float(d.max()) if len(d) else 0.0, "over_1e-12": int((d > REL).sum())}


# ======================================================================================== the unit level
def unit_input(btc, us, t_lo=None, t_hi=None):
    """the driver's input: the kept bars of US100 (sym 1) and BTC (sym 2) in (time, symbol) order, mid-close fields"""
    parts = []
    for m1, sym in ((us, 1), (btc, 2)):
        r = np.zeros(len(m1), UNIT_REC)
        r["t"] = secs(m1.index)
        r["sym"] = sym
        r["bc"] = m1["bc"].to_numpy()
        r["ac"] = m1["ac"].to_numpy()
        parts.append(r)
    r = np.concatenate(parts)
    r = r[np.lexsort((r["sym"], r["t"]))]
    if t_lo is not None:
        r = r[r["t"] >= t_lo]
    if t_hi is not None:
        r = r[r["t"] < t_hi]
    return np.int64(len(r)).tobytes() + r.tobytes()


def run_unit(exe, inp, name):
    os.makedirs(OUT, exist_ok=True)
    csv = os.path.join(OUT, f"unit_{name}.csv")
    t0 = time.time()
    p = subprocess.run([exe, csv], input=inp, capture_output=True, timeout=7200,
                       env=dict(os.environ, ASAN_OPTIONS="detect_leaks=1"))
    if p.returncode:
        raise RuntimeError(f"unit driver failed ({p.returncode}): {p.stderr.decode()[-3000:]}")
    vals = np.frombuffer(p.stdout, UNIT_OUT).copy()
    em = pd.read_csv(csv, float_precision="round_trip")             # %.17g read back exactly (the default parser is not)
    return {"vals": vals, "em": em, "stderr": p.stderr.decode().strip(), "sec": round(time.time() - t0, 1),
            "sha": hashlib.sha256(p.stdout + open(csv, "rb").read()).hexdigest()}


def unit_check(name, u, la, lab_o, btc, t_from=None, t_to=None):
    """the unit level's checks (module docstring) on the grid minutes in [t_from, t_to) (UTC s; default: the lab's grid)"""
    v, em = u["vals"], u["em"]
    t0, n = la["t0"], la["n"]
    g = v["g"]
    res = {"world": name, "driver": u["stderr"], "sec": u["sec"]}
    if t_from is None:
        grid_ok = len(g) >= n and g[0] == t0 and (g[:n] == t0 + np.arange(n)).all()
        lo, k0, hi = 0, 0, n
    else:
        k0 = int(np.searchsorted(g, t_from // 60))
        lo = int(g[k0] - t0)
        grid_ok = bool((np.diff(g) == 1).all()) and lo >= 0 and int(g[k0]) == t_from // 60
        hi = min(n, lo + len(g) - k0, t_to // 60 - t0)
    res["grid"] = {"lab_first_minute_utc": str(pd.Timestamp(t0 * 60, unit="s", tz="UTC")), "lab_minutes": n,
                   "ea_first_minute_utc": str(pd.Timestamp(int(g[0]) * 60, unit="s", tz="UTC")), "ea_minutes": int(len(g)),
                   "compared_minutes": int(hi - lo), "same_grid": bool(grid_ok)}
    vv = v[k0:k0 + (hi - lo)]
    s = slice(lo, hi)
    res["x"] = cmp_series(vv["x"], la["x"][s])
    res["x_c_log"] = cmp_series(vv["x"], la["xc"][s])
    res["r_btc"] = cmp_series(vv["rb"], la["rF1"][s])
    res["r_btc_c_log"] = cmp_series(vv["rb"], la["rc"][s])
    res["sigma_L"] = cmp_series(vv["sl"], la["sigX"][s])
    res["sigma_B"] = cmp_series(vv["sb"], la["sigF1"][s])
    res["sigma_L_c_log"] = cmp_series(vv["sl"], la["sigXc"][s])
    res["sigma_B_c_log"] = cmp_series(vv["sb"], la["sigF1c"][s])
    g_lo, g_hi = t0 + lo, t0 + hi
    la_sub = in_range(la, g_lo, g_hi)                       # the lab's decisions inside the compared minutes
    info = em[em.kind == "info"]
    dec_g = (info.dec.to_numpy(np.int64) // 60) - 1
    keep = (dec_g >= g_lo) & (dec_g < g_hi)
    res["signals"] = cmp_signals(dec_g[keep], info.v1.to_numpy()[keep], info.v2.to_numpy()[keep], la_sub)
    ords = em[em.kind == "ord"]
    og = ords.dec.to_numpy(np.int64) // 60 - 1
    ords = ords[(og >= g_lo) & (og < g_hi)]
    idx = secs(btc.index)
    resolved, shape_bad = resolve(ords, idx)
    lg = lab_order_g(lab_o, la)
    lab_sub = lab_o[(lg >= g_lo) & (lg < g_hi)]
    res["orders"] = cmp_orders(resolved, lab_sub, idx)
    res["orders"]["emitted"] = int(len(ords))
    res["orders"]["oids"] = int(len(resolved))
    res["orders"]["bad_shape"] = shape_bad[:10]
    res["orders"]["emitted_from_onbar"] = int((em["from"] == 1).sum())
    sig_ok = all(res[k]["nan_mismatch"] == 0 and res[k]["over_1e-12"] == 0 for k in ("sigma_L", "sigma_B"))
    ret_ok = all(res[k]["nan_mismatch"] == 0 and res[k]["within_1_ulp"] == res[k]["finite"] for k in ("x", "r_btc"))
    m = re.search(r"latest exit (\d+) (\d+) (\d+)", u["stderr"])
    res["latest_exit"] = {"open_1600000000": [int(v) for v in m.groups()] if m else None, "expected": 1600003600}
    le_ok = bool(m) and all(int(v) == 1600003600 for v in m.groups())
    res["pass"] = bool(grid_ok and sig_ok and ret_ok and res["signals"]["pass"] and res["orders"]["pass"] and not shape_bad and le_ok)
    return res


# ======================================================================================== the EA level
def what_of(r):
    """the DEC kind; compare.num reads any text holding "inf" or "nan" as a number, so "info" comes back as inf"""
    w = r.get("what")
    if isinstance(w, float) and w == float("inf"):
        return "info"
    return w


def s0_contract(rows, starts=1):
    """S0's replay contract on this journal: per start (a process: INIT at OnInit and at OnDeinit) one SELFTEST ok, one
    PLAN, one REBUILD, and a READY line for each symbol NQB reads (US100, BTCUSD); one start: four READY; no ERROR, no
    SEND (the rule adds only its own lines). With restarts, a segment may end before a symbol it does not need is READY
    (the first one, 2013-2018, ends before ETH is)"""
    ev, seg = {}, []
    for r in rows:
        ev[r["ev"]] = ev.get(r["ev"], 0) + 1
        if r["ev"] == "INIT" and "deinit" not in r:
            seg.append(set())
        elif r["ev"] == "READY" and seg:
            seg[-1].add(r["code"])
    st = [r for r in rows if r["ev"] == "SELFTEST"]
    res = {"INIT": ev.get("INIT", 0), "SELFTEST_ok": int(all(int(r["ok"]) == 1 for r in st)) if st else None, "PLAN": ev.get("PLAN", 0),
           "READY": ev.get("READY", 0), "REBUILD": ev.get("REBUILD", 0), "ERROR": ev.get("ERROR", 0), "SEND": ev.get("SEND", 0),
           "GAP": ev.get("GAP", 0), "NOTREADY": ev.get("NOTREADY", 0), "LATEBAR": ev.get("LATEBAR", 0), "starts": len(seg),
           "starts_with_US100_and_BTC_READY": sum(1 for s in seg if {"US100", "BTCUSD"} <= s)}
    res["pass"] = (res["INIT"] == 2 * starts and len(seg) == starts and len(st) == starts and res["SELFTEST_ok"] == 1
                   and res["PLAN"] == starts and res["REBUILD"] == starts and res["starts_with_US100_and_BTC_READY"] == starts
                   and (starts > 1 or res["READY"] == 4) and res["ERROR"] == 0 and res["SEND"] == 0)
    return res


def replay(world, sanitize=False, fresh=False):
    """the EA over the world's bars (one process, or one per segment with restarts); cached on the binary, the bars and
    the restart points"""
    exe, warn = build_ea(sanitize)
    files = os.path.join(OUT, f"{world['name']}_{'san' if sanitize else 'plain'}")
    env = {"MOCK_INPUT_InpTrade": "false"}
    if sanitize:
        env["ASAN_OPTIONS"] = "detect_leaks=1"
    key = json.dumps({"exe": sha_files([exe]), "env": env, "restarts": world.get("restarts_srv", []),
                      "bars": {s: [os.path.getsize(p), int(os.path.getmtime(p))] for s, p in world["bars"].items()}}, sort_keys=True)
    sp = os.path.join(files, "_replay.json")
    if not fresh and os.path.exists(sp):
        old = json.load(open(sp))
        if old.get("key") == key and os.path.isdir(os.path.join(files, "ClaudeRobot")):
            old["cached"] = True
            return old
    cuts = list(world.get("restarts_srv", []))
    outs, wall = [], 0.0
    for k in range(len(cuts) + 1):
        frm = cuts[k - 1] if k > 0 else None
        to = cuts[k] if k < len(cuts) else None
        out, w = B.replay(exe, files, world["bars"], env=env, fresh=(k == 0), frm=frm, to=to, timeout=7200)
        outs.append(out)
        wall += w
    res = {"key": key, "files": files, "replay": outs[0] if len(outs) == 1 else f"{len(outs)} processes; last: {outs[-1]}",
           "wall_s": round(wall, 1), "warnings": warn, "processes": len(outs), "cached": False}
    with open(sp, "w") as f:
        json.dump(res, f, indent=1)
    return res


def live_rows(rows):
    """the journal of a run with restarts, as the live passes wrote it: lines with rp=1 (a start's replay of the
    history) are dropped, except, for a trade filled during a replay and exited live, its PFILL (the latest replayed one
    before that live exit, put back in front of it)"""
    out, last_rp_fill, live_fill = [], {}, set()
    for r in rows:
        key = (r["code"], r.get("oid"))
        if r.get("rp") == 1:
            if r["ev"] == "PFILL":
                last_rp_fill[key] = r
            continue
        if r["ev"] == "PFILL":
            live_fill.add(key)
        elif r["ev"] in ("PEXIT", "PREVISE", "PVOID") and key not in live_fill and key in last_rp_fill:
            out.append(last_rp_fill.pop(key))
            live_fill.add(key)
        out.append(r)
    return out


def ea_check(world, rep, la, lab_o, lab_t, btc):
    all_rows = compare.read_journal(rep["files"])
    restarts = world["name"] == "restarts"
    rows = live_rows(all_rows) if restarts else all_rows
    starts = len(world.get("restarts_srv", [])) + 1
    res = {"world": world["name"], "replay": rep["replay"], "wall_s": rep["wall_s"], "cached_replay": rep.get("cached", False),
           "build_warnings": rep["warnings"], "contract": s0_contract(all_rows, starts),
           "errors": [r for r in all_rows if r["ev"] == "ERROR"][:5]}
    reb = compare.events(all_rows, "REBUILD").iloc[0]
    first = int(reb["from"]) + 60 if int(reb["from"]) > 0 else int(reb["to"]) + 60
    ok = res["contract"]["pass"] and not rep["warnings"]
    # with restarts: the lines the live passes wrote (the restart points keep away from every decision, entry and exit)
    info = [r for r in rows if r["ev"] == "DEC" and r["code"] == CODE and what_of(r) == "info"]
    ords = [r for r in rows if r["ev"] == "DEC" and r["code"] == CODE and what_of(r) == "ord"]
    g_lo = first // 60
    la_sub = in_range(la, g_lo, 2**62)
    dec_g = np.array([int(r["utc"]) // 60 - 1 for r in info], np.int64)
    res["signals"] = cmp_signals(dec_g, [float(r["v1"]) for r in info], [float(r["v2"]) for r in info], la_sub)
    ok &= res["signals"]["pass"]
    idx = secs(btc.index)
    od = pd.DataFrame([{"oid": int(r["oid"]), "dec": int(r["utc"]), "side": int(r["side"]), "t_from": int(r["tf"]), "t_to": int(r["tt"]),
                        "x_sched": int(r["x"]), "x_gap": int(r["xg"]), "void_le": int(r["vle"]), "stop_dist": float(r["sd"]),
                        "at": int(r["at"]), "et": int(r["et"]), "ref": int(r["ref"]), "xh": int(r["xh"]), "ax": int(r["ax"]),
                        "stop": float(r["st"])} for r in ords])
    others = {}
    if len(od):
        others = {"etype_not_market": int((od.et != 0).sum()), "refusal": int((od.ref != 0).sum()), "hold": int((od.xh != 0).sum()),
                  "after_exit_of": int((od.ax != 0).sum()), "absolute_stop": int((od.stop != 0).sum())}
    resolved, shape_bad = resolve(od, idx) if len(od) else ([], [])
    lg = lab_order_g(lab_o, la)
    res["orders"] = cmp_orders(resolved, lab_o[lg >= g_lo], idx)
    res["orders"].update({"dec_lines": int(len(od)), "oids": int(len(resolved)), "bad_shape": shape_bad[:10], "fields": others})
    ok &= res["orders"]["pass"] and not shape_bad and not any(others.values())
    last_btc = int(idx[-1])
    t_lab, ea_rows = lab_t, rows
    tr = compare.cmp_trades(ea_rows, t_lab, CODE, t_from=first, t_to=last_btc - 1, rel=REL)
    ea_t = compare.paper_trades(ea_rows, CODE)
    tr["ea_trades_total"] = int(len(ea_t))
    tr["lab_trades_total"] = int(len(t_lab))
    if len(ea_t):
        tr["reasons_ea"] = {k: int(v) for k, v in ea_t.reason.value_counts().items()}
        tr["revised_ea"] = int(ea_t.revised.sum())
    tr["reasons_lab"] = {k: int(v) for k, v in t_lab.reason.value_counts().items()}
    tr["prices_bit_for_bit"] = bool(tr.get("entry_equal") == tr.get("stop_equal") == tr.get("exit_equal") == tr.get("lab_trades"))
    pev = {}
    for r in rows:
        if r["code"] == CODE and r["ev"] in ("PFILL", "PEXIT", "PREVISE", "PVOID", "PREFUSE", "HOLD", "PSTOP"):
            pev[r["ev"]] = pev.get(r["ev"], 0) + 1
    tr["paper_events"] = pev
    res["trades"] = tr
    ok &= bool(tr["pass"]) and tr.get("lab_trades", 0) > 0 and tr.get("same_exit_and_reason") == tr.get("lab_trades") and \
        not pev.get("PREFUSE") and not pev.get("HOLD") and not pev.get("PSTOP")
    res["first_minute_utc"] = first
    res["pass"] = bool(ok)
    return res


# ======================================================================================== worlds
def world_is():
    btc, us = frame_is("btcusd"), frame_is("us100")
    return {"name": "is", "btc": btc, "us": us, "bars": bars_is()}


def hole_cuts(btc, us, la, lab_o, lab_t, seed=SEED):
    """windows [a, b) (UTC seconds) of bars removed, per market, each aimed at one path (module docstring); picked from
    the lab's own in-sample decisions and trades, one per neighbourhood of 6 hours so that they stay apart"""
    rng = np.random.default_rng(seed)
    t0 = la["t0"]
    hasF = la["hasF"]
    dec = lab_decisions(la)                                     # decision minutes g
    used = set()
    cuts = {"btc": [], "us": []}
    kinds = {}

    def bar(m):
        k = m - t0
        return 0 <= k < len(hasF) and bool(hasF[k])

    def free(m):
        return all((m // 360 + d) not in used for d in (-1, 0, 1))

    def claim(m):
        used.add(m // 360)

    def pick(cands, n, kind, make, mkt="btc"):
        cands = [c for c in cands if free(c[0])]
        got = 0
        for i in rng.permutation(len(cands)):
            c = cands[i]
            if not free(c[0]):
                continue
            ws = make(*c)
            if ws is None:
                continue
            claim(c[0])
            for a, b in ws:
                cuts[mkt].append((int(a), int(b), kind))
            got += 1
            if got >= n:
                break
        kinds[kind] = got

    entry_of = {int(t) // 60: True for t in secs(lab_o.entry_t)}
    plain = [(int(g),) for g in dec if bar(g + 1) and bar(g + 2) and (g + 1) in entry_of]
    trades = lab_t.reset_index(drop=True)
    te = secs(trades.entry_time) // 60
    tx = secs(trades.exit_time) // 60
    timed = [(int(e), int(x)) for e, x, r in zip(te, tx, trades.reason) if r == "time" and x == e + 60]
    anyt = [(int(e),) for e in te]
    pick(plain, 25, "A_entry_g1_missing", lambda g: [((g + 1) * 60, (g + 2) * 60)])
    pick(plain, 12, "B_entry_g1_g2_missing", lambda g: [((g + 1) * 60, (g + 3) * 60)])
    pick(anyt, 15, "C_void_le_no_bar_to_x30", lambda e: [((e + 1) * 60, (e + 91) * 60)])
    pick(timed, 12, "D_exit_falls_back", lambda e, x: [((x - 10) * 60, (x + 45) * 60)])
    pick([c for c in timed if bar(c[1] + 30)], 8, "E_exit_at_x30", lambda e, x: [(x * 60, (x + 30) * 60)])
    pick([c for c in timed if bar(c[1] + 31)], 8, "F_exit_x31_falls_back", lambda e, x: [(x * 60, (x + 31) * 60)])
    pick([(int(g),) for g in dec], 10, "G_decision_btc_bar_missing", lambda g: [(g * 60, (g + 1) * 60)])
    pick([(int(g),) for g in dec if bar(g - 4)], 8, "H3_btc_ffill_3min", lambda g: [((g - 3) * 60, g * 60)])
    pick([(int(g),) for g in dec], 8, "H4_btc_ffill_4min", lambda g: [((g - 4) * 60, g * 60)])
    pick([(int(g),) for g in dec], 8, "J3_us100_ffill_3min", lambda g: [((g - 3) * 60, g * 60)], "us")
    pick([(int(g),) for g in dec], 8, "J4_us100_ffill_4min", lambda g: [((g - 4) * 60, g * 60)], "us")
    pick([(int(g),) for g in dec], 8, "J0_decision_us100_bar_missing", lambda g: [(g * 60, (g + 1) * 60)], "us")
    a = int(pd.Timestamp("2019-06-03", tz="UTC").value // 10**9)
    cuts["btc"].append((a, a + 17 * 86400, "I_btc_17_days"))
    a = int(pd.Timestamp("2020-02-03", tz="UTC").value // 10**9)
    cuts["us"].append((a, a + 17 * 86400, "K_us100_17_days"))
    kinds["I_btc_17_days"] = kinds["K_us100_17_days"] = 1
    lo = int(pd.Timestamp("2017-06-01", tz="UTC").value // 10**9)
    hi = int(pd.Timestamp("2021-12-20", tz="UTC").value // 10**9)
    for mkt, n in (("btc", 150), ("us", 100)):
        for _ in range(n):
            t = int(rng.integers(lo, hi)) // 60 * 60
            if rng.random() < 0.7:                              # mostly in and around New York cash hours
                d = pd.Timestamp(t, unit="s", tz="UTC").tz_convert(NY).normalize()
                t = int((d + pd.Timedelta(minutes=int(rng.integers(540, 990)))).value // 10**9)
            cuts[mkt].append((t, t + 60 * int(rng.integers(1, 61)), "R_random"))
        kinds[f"R_random_{mkt}"] = n
    return {"btc": sorted(cuts["btc"]), "us": sorted(cuts["us"]), "kinds": kinds}


def holes_bars(btc_cut, name):
    """a BTC bar file of the cut frame (S0's export_frames layout) checked to give the frame back; the other symbols keep
    their in-sample bars"""
    d = os.path.join(OUT, "bars")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, f"BTCUSD.r_{name}.bin")
    key = os.path.join(d, f"BTCUSD.r_{name}.key")
    k = hashlib.sha256(np.ascontiguousarray(secs(btc_cut.index)).tobytes()).hexdigest()
    if not (os.path.exists(p) and os.path.exists(key) and open(key).read() == k):
        t = EF.server_secs(btc_cut.index)
        pts, spread = EF.to_points(btc_cut)
        EF.write_bin(p, t, pts, spread)
        _, rec = EF.read_bin(p)
        fr = EF.rebuild(rec)
        assert (fr.index == btc_cut.index.as_unit(fr.index.unit)).all(), "server -> UTC round trip"
        for c in btc_cut.columns:
            assert (fr[c].to_numpy() == btc_cut[c].to_numpy()).all(), f"the bar file does not give the frame back ({c})"
        with open(key, "w") as f:
            f.write(k)
    bars = dict(bars_is())
    bars["BTCUSD.r"] = p
    return bars


def coverage_unit(u, la, cuts, btc, lab_o):
    em = u["em"]
    ords = em[em.kind == "ord"]
    idx = secs(btc.index)
    res, _ = resolve(ords, idx)
    st = pd.Series([r["status"] for r in res]).value_counts().to_dict()
    sig_nan = int((~np.isfinite(la["sigF1"][1:]) & np.isfinite(la["sigF1"][:-1])).sum())
    sigl_nan = int((~np.isfinite(la["sigX"][1:]) & np.isfinite(la["sigX"][:-1])).sum())
    return {"second_entry_minute_taken": sum(1 for r in res if r["chance"] == 2), "void_both_minutes": st.get("void_window", 0),
            "void_le": st.get("void_le", 0), "sigma_B_turns_NaN": sig_nan, "sigma_L_turns_NaN": sigl_nan}


def coverage_ea(res_ea, lab_t):
    pev = res_ea["trades"].get("paper_events", {})
    t = lab_t
    hold = (t.exit_time - t.entry_time).dt.total_seconds() // 60
    return {"PVOID": pev.get("PVOID", 0), "PREVISE": pev.get("PREVISE", 0),
            "second_entry_minute": res_ea["orders"].get("second_entry_minute", 0),
            "void_both_minutes": res_ea["orders"]["voids"].get("lab: no BTC bar in [g + 1, g + 2]", 0),
            "void_le": res_ea["orders"]["voids"].get("lab: exit_i <= entry_i (no BTC bar from the entry to x + 30 min)", 0),
            "lab_exit_at_x30": int(((hold == 90) & (t.reason == "time")).sum())}


def restart_points(la, lab_o, lab_t, n_mid=6, n_before=4, n_rand=4, seed=SEED):
    """restart times (UTC s) for the EA, on weekdays: inside open lab trades and at random, more than 6 minutes from any
    lab decision, entry window, exit or revision minute; and 4 minutes before a decision's barrier, with nothing else
    within 6 minutes. The first live barrier comes about 2 minutes after a start (two settle reads, then the replay of
    the depth), so every decision, fill and exit is journaled by a live pass"""
    rng = np.random.default_rng(seed + 1)
    dec = lab_decisions(la)
    marks = np.unique(np.r_[dec, dec + 1, dec + 2, secs(lab_o.entry_t) // 60, secs(lab_o.exit_t) // 60, secs(lab_o.exit_t) // 60 + 31,
                            secs(lab_t.entry_time) // 60, secs(lab_t.exit_time) // 60].astype(np.int64))

    def near(m, lo=-6, hi=6, but=()):
        k = np.searchsorted(marks, m + lo)
        while k < len(marks) and marks[k] <= m + hi:
            if int(marks[k]) not in but:
                return True
            k += 1
        return False

    def weekday(t):
        return pd.Timestamp(int(t), unit="s", tz="UTC").tz_convert(NY).dayofweek < 5

    pts = []
    te, tx = secs(lab_t.entry_time), secs(lab_t.exit_time)
    for k in rng.permutation(len(te)):
        t = (int(te[k]) + int(tx[k])) // 2 // 60 * 60
        if weekday(t) and not near(t // 60):
            pts.append(t)
        if len(pts) >= n_mid:
            break
    for g in rng.permutation(dec):
        t = (int(g) + 1 - 4) * 60                                  # the decision's barrier g + 1 is 4 minutes later
        own = {int(g), int(g) + 1, int(g) + 2}
        if weekday(t) and not near(t // 60, -6, 2) and not near(t // 60, 3, 10, own):
            pts.append(t)
        if len(pts) >= n_mid + n_before:
            break
    lo = int(pd.Timestamp("2017-08-01", tz="UTC").value // 10**9)
    hi = int(pd.Timestamp("2021-12-01", tz="UTC").value // 10**9)
    while len(pts) < n_mid + n_before + n_rand:
        t = int(rng.integers(lo, hi)) // 60 * 60
        if weekday(t) and not near(t // 60):
            pts.append(t)
    return sorted(set(pts))


# ======================================================================================== runs
def run_world_is(sanitize=True, fresh=False):
    t_start = time.time()
    w = world_is()
    btc, us = w["btc"], w["us"]
    res = {"world": "is", "constants": constants_check()}
    s0, lab_o, lab_t = ref_lab_one()                       # SPEC 7: ref_lab.py's references
    ref, own_o, own_t = lab_ref("is", official=True)        # this file's reference code, used for the holes worlds
    ref["ref_lab_one"] = {k: s0.get(k) for k in ("orders", "trades", "reasons", "R_sum", "leader", "first_bar", "last_bar")}
    ref["same_as_ref_lab_one"] = same_frames(lab_o, own_o, ["entry_i", "side", "stop_dist", "exit_i", "entry_t", "exit_t"]) and \
        same_frames(lab_t, own_t, [c for c in lab_t.columns])
    res["lab"] = ref
    la = lab_arrays(btc, us)
    res["lab_arrays_reproduce_make_orders"] = check_derivation(la, lab_o, btc)
    res["razors"] = razors(la, btc, lab_t)
    exe, warn = build_unit(False)
    u = run_unit(exe, unit_input(btc, us), "is")
    res["unit"] = unit_check("is", u, la, lab_o, btc)
    res["unit"]["build_warnings"] = warn
    ok = res["constants"]["pass"] and res["lab_arrays_reproduce_make_orders"]["equal_to_make_orders_bit_for_bit"] and \
        res["unit"]["pass"] and not warn and ref["same_as_ref_lab_one"]
    if sanitize:
        exe_s, warn_s = build_unit(True)
        us_ = run_unit(exe_s, unit_input(btc, us), "is_san")
        res["unit"]["sanitizer"] = {"build_warnings": warn_s, "same_bytes": us_["sha"] == u["sha"], "sec": us_["sec"]}
        ok &= us_["sha"] == u["sha"] and not warn_s
    rep = replay(w, False, fresh)
    res["ea"] = ea_check(w, rep, la, lab_o, lab_t, btc)
    ok &= res["ea"]["pass"]
    res["builds"] = build_variants()
    ok &= res["builds"]["pass"]
    if sanitize:
        san = replay(w, True, fresh)
        same = subprocess.run(["diff", "-r", "-q", os.path.join(rep["files"], "ClaudeRobot"), os.path.join(san["files"], "ClaudeRobot")],
                              capture_output=True, text=True)
        res["ea"]["sanitizer"] = {"replay": san["replay"], "wall_s": san["wall_s"], "cached_replay": san.get("cached", False),
                                  "build_warnings": san["warnings"], "journal_identical_to_plain_build": same.returncode == 0}
        ok &= same.returncode == 0 and not san["warnings"]
    res["tree"] = {k: v for k, v in tree().items() if k in ("origin", "amalgam")}
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t_start, 1)
    return res, la, lab_o, lab_t


def run_world_holes(la_is, lab_o_is, lab_t_is, sanitize=False, fresh=False):
    t_start = time.time()
    btc, us = frame_is("btcusd"), frame_is("us100")
    hc = hole_cuts(btc, us, la_is, lab_o_is, lab_t_is)
    res = {"world": "holes", "cuts": {"btc": len(hc["btc"]), "us100": len(hc["us"]), "by_kind": hc["kinds"]}}
    cb = [(a, b) for a, b, _ in hc["btc"]]
    cu = [(a, b) for a, b, _ in hc["us"]]
    btc_c, us_c = cut_frame(btc, cb), cut_frame(us, cu)
    res["cuts"]["btc_bars_removed"] = int(len(btc) - len(btc_c))
    res["cuts"]["us100_bars_removed"] = int(len(us) - len(us_c))
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "holes_world.json"), "w") as f:
        json.dump({"seed": SEED, "kinds": hc["kinds"], "btc": [[a, b, k, ny_str(a), ny_str(b)] for a, b, k in hc["btc"]],
                   "us100": [[a, b, k, ny_str(a), ny_str(b)] for a, b, k in hc["us"]]}, f, indent=1)
    # unit level: BTC and US100 holes
    ref_u, lo_u, lt_u = lab_ref("holes_unit", {"btc": cb, "us": cu})
    la_u = lab_arrays(btc_c, us_c)
    res["unit_lab"] = ref_u
    res["unit_lab_arrays_reproduce_make_orders"] = check_derivation(la_u, lo_u, btc_c)
    exe, warn = build_unit(False)
    u = run_unit(exe, unit_input(btc_c, us_c), "holes")
    res["unit"] = unit_check("holes", u, la_u, lo_u, btc_c)
    res["unit"]["coverage"] = coverage_unit(u, la_u, hc, btc_c, lo_u)
    cov_u = res["unit"]["coverage"]
    ok = res["unit"]["pass"] and res["unit_lab_arrays_reproduce_make_orders"]["equal_to_make_orders_bit_for_bit"] and \
        all(cov_u[k] > 0 for k in ("second_entry_minute_taken", "void_both_minutes", "void_le", "sigma_B_turns_NaN", "sigma_L_turns_NaN"))
    # EA level: BTC holes (US100 holes add no paper path)
    ref_e, lo_e, lt_e = lab_ref("holes_ea", {"btc": cb, "us": []})
    la_e = lab_arrays(btc_c, us)
    res["ea_lab"] = ref_e
    res["ea_razors"] = razors(la_e, btc_c, lt_e)
    w = {"name": "holes", "bars": holes_bars(btc_c, "nqbholes")}
    rep = replay(w, False, fresh)
    res["ea"] = ea_check(w, rep, la_e, lo_e, lt_e, btc_c)
    res["ea"]["coverage"] = coverage_ea(res["ea"], lt_e)
    ok &= res["ea"]["pass"] and all(v > 0 for v in res["ea"]["coverage"].values())
    if sanitize:
        san = replay(w, True, fresh)
        same = subprocess.run(["diff", "-r", "-q", os.path.join(rep["files"], "ClaudeRobot"), os.path.join(san["files"], "ClaudeRobot")],
                              capture_output=True, text=True)
        res["ea"]["sanitizer"] = {"wall_s": san["wall_s"], "journal_identical_to_plain_build": same.returncode == 0,
                                  "build_warnings": san["warnings"]}
        ok &= same.returncode == 0
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t_start, 1)
    return res


def run_world_restarts(la, lab_o, lab_t, fresh=False):
    t_start = time.time()
    btc, us = frame_is("btcusd"), frame_is("us100")
    res = {"world": "restarts"}
    # unit level: the rule afresh from 60 days of history, compared over the next 10 days
    rng = np.random.default_rng(SEED + 2)
    dec = lab_decisions(la)
    lo = int(pd.Timestamp("2017-07-15", tz="UTC").value // 10**9)
    hi = int(pd.Timestamp("2021-12-15", tz="UTC").value // 10**9)
    starts = sorted({int(t) // 60 * 60 for t in rng.integers(lo, hi, 8)} |
                    {(int(g) - 3) * 60 for g in rng.permutation(dec[(dec * 60 > lo) & (dec * 60 < hi)])[:4]})
    exe, warn = build_unit(False)
    rows, ok = [], not warn
    for T in starts:
        u = run_unit(exe, unit_input(btc, us, T - DEPTH_S, T + 10 * 86400), f"restart_{T}")
        # compared over [T, T + 9 days): the last day of the input is a margin (an entry window or an exit past its end)
        r = unit_check(f"restart {ny_str(T)}", u, la, lab_o, btc, t_from=T, t_to=T + 9 * 86400)
        rows.append({"start_ny": ny_str(T), "pass": r["pass"], "grid_minutes": r["grid"]["compared_minutes"],
                     "lab_decisions": r["signals"]["lab_decisions"], "ea_signals": r["signals"]["ea_signals"],
                     "orders_matched": r["orders"].get("matched", 0), "lab_orders": r["orders"]["lab_orders"],
                     "sigma_L_max_rel": r["sigma_L"]["max_rel_diff"], "sigma_B_max_rel": r["sigma_B"]["max_rel_diff"],
                     "sigma_nan_mismatch": r["sigma_L"]["nan_mismatch"] + r["sigma_B"]["nan_mismatch"]})
        ok &= r["pass"]
    res["unit"] = {"starts": rows, "decisions_compared": int(sum(r["lab_decisions"] for r in rows)),
                   "sigma_max_rel": max(max(r["sigma_L_max_rel"], r["sigma_B_max_rel"]) for r in rows), "pass": bool(ok)}
    # EA level: the in-sample bars in segments
    pts = restart_points(la, lab_o, lab_t)
    srv = [int(pd.Timestamp(p, unit="s", tz="UTC").tz_convert(NY).tz_localize(None).value // 10**9) + 7 * 3600 for p in pts]
    w = {"name": "restarts", "bars": bars_is(), "restarts_utc": pts, "restarts_srv": srv}
    rep = replay(w, False, fresh)
    res["ea"] = ea_check(w, rep, la, lab_o, lab_t, btc)
    te, tx = secs(lab_t.entry_time), secs(lab_t.exit_time)
    res["ea"]["restarts"] = {"at_ny": [ny_str(p) for p in pts], "processes": rep["processes"],
                             "inside_an_open_trade": int(sum(1 for p in pts if ((te < p) & (tx > p)).any())),
                             "decision_within_10_min_after": int(sum(1 for p in pts if ((dec * 60 > p) & (dec * 60 <= p + 600)).any()))}
    ok &= res["ea"]["pass"] and res["ea"]["restarts"]["inside_an_open_trade"] > 0 and res["ea"]["restarts"]["decision_within_10_min_after"] > 0
    res["pass"] = bool(ok)
    res["sec"] = round(time.time() - t_start, 1)
    return res


# ======================================================================================== report
def show_unit(u):
    g = u["grid"]
    log(f"  unit: grid {g['compared_minutes']} minutes from {g['ea_first_minute_utc']} (same as the lab's: {g['same_grid']}), "
        f"driver {u['sec']} s ({u['driver']})")
    for k in ("x", "r_btc", "sigma_L", "sigma_B"):
        a, c = u[k], u[k + "_c_log"]
        log(f"    {k:8s} finite {a['finite']:8d}  NaN mismatches {a['nan_mismatch']}  bit-equal {a['bit_equal']:8d}  within 1 ulp "
            f"{a['within_1_ulp']:8d}  max rel {a['max_rel_diff']:.2e}  | lab with the C log: bit-equal {c['bit_equal']} of {c['finite']}")
    s, o = u["signals"], u["orders"]
    log(f"    signals: lab {s['lab_decisions']}, rule {s['ea_signals']}, only lab {s['n_only_lab']}, only rule {s['n_only_ea']}; "
        f"x bit-equal {s.get('x_bit_equal')} (C log {s.get('x_bit_equal_c_log')}), sigma_L max rel {s.get('sigma_L_max_rel_diff')}")
    log(f"    orders: emitted {o['emitted']} for {o['oids']} oids; lab {o['lab_orders']}, matched {o.get('matched')}, only lab "
        f"{o.get('only_lab')}, only rule {o.get('only_ea')}, same exit bar {o.get('same_exit_bar')}, stop_dist bit-equal "
        f"{o.get('stop_dist_bit_equal')} (max rel {o.get('stop_dist_max_rel_diff')}), second entry minute {o.get('second_entry_minute')}; "
        f"voids {o['voids']}")
    if "sanitizer" in u:
        log(f"    sanitizer: same bytes {u['sanitizer']['same_bytes']}, warnings {len(u['sanitizer']['build_warnings'])}, {u['sanitizer']['sec']} s")
    if "coverage" in u:
        log(f"    coverage: {u['coverage']}")
    log(f"  unit: {'PASS' if u['pass'] else 'FAIL'}")


def show_ea(e):
    c = e["contract"]
    log(f"  ea: replay {e['wall_s']} s{' (cached)' if e['cached_replay'] else ''}, contract {'ok' if c['pass'] else 'FAILED'} {c}")
    s, o, t = e["signals"], e["orders"], e["trades"]
    log(f"    decisions (DEC info): lab {s['lab_decisions']}, EA {s['ea_signals']}, only lab {s['n_only_lab']} {s['only_lab'][:3]}, "
        f"only EA {s['n_only_ea']} {s['only_ea'][:3]}; x bit-equal {s.get('x_bit_equal')}, sigma_L max rel {s.get('sigma_L_max_rel_diff')}")
    log(f"    orders (DEC ord): {o['dec_lines']} lines, {o['oids']} oids; lab {o['lab_orders']}, matched {o.get('matched')}, only lab "
        f"{o.get('only_lab')}, only EA {o.get('only_ea')}, same exit bar {o.get('same_exit_bar')}, stop_dist bit-equal "
        f"{o.get('stop_dist_bit_equal')} / within 1e-12 {o.get('stop_dist_within_1e-12')} (max rel {o.get('stop_dist_max_rel_diff')}), "
        f"second entry minute {o.get('second_entry_minute')}; voids {o['voids']}")
    log(f"    trades: lab {t.get('lab_trades')}, EA {t.get('ea_trades')}, same entry {t.get('same_entry')}, same exit and reason "
        f"{t.get('same_exit_and_reason')}, entry/stop/exit bit-equal {t.get('entry_equal')}/{t.get('stop_equal')}/{t.get('exit_equal')}, "
        f"within 1e-12 {t.get('entry_within_rel')}/{t.get('stop_within_rel')}/{t.get('exit_within_rel')}, voided {t.get('voided_in_journal')}")
    log(f"    reasons EA {t.get('reasons_ea')} lab {t.get('reasons_lab')}; paper events {t.get('paper_events')}")
    if "sanitizer" in e:
        log(f"    sanitizer: journal identical {e['sanitizer']['journal_identical_to_plain_build']}, {e['sanitizer']['wall_s']} s")
    if "coverage" in e:
        log(f"    coverage: {e['coverage']}")
    if "restarts" in e:
        log(f"    restarts: {e['restarts']}")
    if e["errors"] or e["build_warnings"]:
        log(f"    errors {e['errors']} warnings {e['build_warnings'][:3]}")
    log(f"  ea: {'PASS' if e['pass'] else 'FAIL'}")


def save(res):
    os.makedirs(OUT, exist_ok=True)
    p = os.path.join(OUT, f"{res['world']}_result.json")
    with open(p, "w") as f:
        json.dump(res, f, indent=1, default=str)
    return os.path.relpath(p, ROBOT)


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--world", default="all", choices=["all", "is", "holes", "restarts"])
    ap.add_argument("--no-sanitize", action="store_true", help="skip the sanitizer builds of the in-sample world")
    ap.add_argument("--sanitize-holes", action="store_true", help="also replay the holes world under the sanitizer build")
    ap.add_argument("--fresh", action="store_true", help="ignore cached replays")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args(argv)
    ok = True
    if a.world in ("all", "is"):
        res, la, lab_o, lab_t = run_world_is(not a.no_sanitize, a.fresh)
    else:                                                   # the in-sample lab references the other worlds start from
        _, lab_o, lab_t = lab_ref("is")
        la = lab_arrays(frame_is("btcusd"), frame_is("us100"))
    if a.world in ("all", "is"):
        k = res["constants"]
        log(f"NQB world is: constants equal the lab's frozen parameters: {k['pass']} {k['different'] or ''}")
        d = res["lab_arrays_reproduce_make_orders"]
        log(f"  lab: {res['lab']['orders']} orders, {res['lab']['trades']} trades {res['lab']['reasons']} (ref_lab.one: "
            f"{res['lab']['ref_lab_one']['orders']} orders, {res['lab']['ref_lab_one']['trades']} trades; this file's reference code "
            f"gives the same: {res['lab']['same_as_ref_lab_one']}); the per-minute arrays give make_orders bit for bit: "
            f"{d['equal_to_make_orders_bit_for_bit']} ({d['decisions']} decisions, {d['with_an_entry_bar']} with an entry bar)")
        log(f"  latest exit: {res['unit']['latest_exit']}")
        if "official" in res["lab"]:
            log(f"  lab on the rebuilt frames vs official trades: {res['lab']['official']}")
        r = res["razors"]
        log(f"  razors: decisions within 1e-9 {len(r['decisions_within_1e-9'])} (closest {r['closest_decision_rel']:.2e} of "
            f"{r['evaluable_minutes']} evaluable minutes); stops within 1e-9 of a bar {len(r['stops_within_1e-9'])} (closest "
            f"{r['closest_stop_rel']:.2e})")
        show_unit(res["unit"])
        show_ea(res["ea"])
        b = res["builds"]
        log(f"  builds: release {b['release']['ok']} warnings {len(b['release']['warnings'])}, debug {b['debug']['ok']} warnings "
            f"{len(b['debug']['warnings'])}")
        log(f"NQB world is: {'PASS' if res['pass'] else 'FAIL'} ({res['sec']} s) -> {save(res)}")
        ok &= res["pass"]
    if a.world in ("all", "holes"):
        h = run_world_holes(la, lab_o, lab_t, a.sanitize_holes, a.fresh)
        log(f"NQB world holes: cuts {h['cuts']}")
        log(f"  lab (unit frames) {h['unit_lab']['orders']} orders, {h['unit_lab']['trades']} trades; (EA frames) {h['ea_lab']['orders']} "
            f"orders, {h['ea_lab']['trades']} trades")
        show_unit(h["unit"])
        show_ea(h["ea"])
        log(f"NQB world holes: {'PASS' if h['pass'] else 'FAIL'} ({h['sec']} s) -> {save(h)}")
        ok &= h["pass"]
    if a.world in ("all", "restarts"):
        r = run_world_restarts(la, lab_o, lab_t, a.fresh)
        log(f"NQB world restarts: unit {len(r['unit']['starts'])} starts, {r['unit']['decisions_compared']} decisions, sigma max rel "
            f"{r['unit']['sigma_max_rel']:.2e}: {'PASS' if r['unit']['pass'] else 'FAIL'}")
        if a.verbose or not r["unit"]["pass"]:
            for row in r["unit"]["starts"]:
                log(f"    {row}")
        show_ea(r["ea"])
        log(f"NQB world restarts: {'PASS' if r['pass'] else 'FAIL'} ({r['sec']} s) -> {save(r)}")
        ok &= r["pass"]
    log(f"NQB: {'PASS' if ok else 'FAIL'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
