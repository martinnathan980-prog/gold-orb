"""Spike: is the offline test approach good enough for rules written in MQL5?

Rule brk72_24h_wd on btcusd, written in MQL5 as it would live inside the single EA (mql5/Brk72Rule.mqh, hosted by
mql5/SpikeRobot.mq5), translated to C++ (check/to_cpp_spike.py), compiled against a mock terminal + broker that replays
M1 bars minute by minute (check/mock_replay.h), and compared with the lab's own make_orders + simulator.

    python3 -B lab/robot/spike/run_spike.py            # everything below, about a minute
    python3 -B lab/robot/spike/run_spike.py --long     # also the whole in-sample history of btcusd (2017-05 .. 2021-12)

Steps
  1. export the lab frame data/fp/btcusd_m1.parquet for 2020-12-01 .. 2021-06-30 (in sample) as the broker would publish
     it: server time (New York + 7 h), BID open/high/low/close on the price grid (2 digits), spread in integer points;
  2. translate + compile the EA, replay it minute by minute (journal of every hour bar, evaluation, decision, trade);
  3. (a) lab make_orders (the registered sleeve of recalc.sleeves()) + simulate (r2.run, mode 'fp', no_overlap) on a frame
     REBUILT from the exported numbers: must match exactly;
     (b) the same lab run on the official (unrounded) frame: what rounding alone changes;
  4. restarts: the same replay cut into segments (OnDeinit / new process / OnInit), with and without downtime;
  5. speed.
Nothing outside lab/robot/spike/out is written; only bars dated before 2022-01-01 are read (parquet row filter).
"""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = Path(__file__).resolve().parent
LAB = HERE.parent.parent
OUT = HERE / "out"
sys.path.insert(0, str(LAB))
sys.path.insert(0, str(LAB / "r2"))
sys.path.insert(0, str(LAB / "live_ai"))
NY = "America/New_York"
IS_END = pd.Timestamp("2022-01-01", tz="UTC")
FP = LAB / "data" / "fp" / "btcusd_m1.parquet"
DIGITS = 2
SYM = "BTCUSD"


# ----------------------------------------------------------------------------------------------- data
def load_official(start, end):
    """the lab frame, sliced at read time (never a 2022+ row in memory)"""
    lo, hi = pd.Timestamp(start, tz="UTC"), min(pd.Timestamp(end, tz="UTC"), IS_END)
    m1 = pd.read_parquet(FP, filters=[("ts", ">=", lo), ("ts", "<", hi)])
    assert len(m1) and m1.index.max() < IS_END and m1.index.is_monotonic_increasing and m1.index.is_unique
    return m1


def server_secs(idx):
    srv = idx.tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)          # build_fp_frames.py: FP server clock
    return srv.values.astype("datetime64[s]").astype(np.int64)


def export(m1, path, digits=DIGITS):
    """bid OHLC rounded to the price grid + spread in integer points (one per bar: the lab frame has one per bar)"""
    sc = 10 ** digits
    bid = {k: np.rint(m1["b" + k].to_numpy() * sc).astype(np.int64) for k in "ohlc"}
    spread = np.rint((m1["ao"] - m1["bo"]).to_numpy() * sc).astype(np.int64)
    assert (spread >= 0).all() and all((v > 0).all() for v in bid.values())
    t = server_secs(m1.index)
    fmt = lambda v: f"{v // sc}.{v % sc:0{digits}d}"
    with open(path, "w") as f:
        f.write("time,open,high,low,close,tick_volume,spread\n")
        for i in range(len(t)):
            f.write(f"{t[i]},{fmt(bid['o'][i])},{fmt(bid['h'][i])},{fmt(bid['l'][i])},{fmt(bid['c'][i])},1,{spread[i]}\n")
    return t


def rebuild(path, digits=DIGITS):
    """the exported file as a lab frame: bid = the published price, ask = bid + spread points (both on the grid);
    UTC from the server time with pont.server_to_utc (independent of the EA's own clock code)"""
    import pont
    raw = pd.read_csv(path, dtype=str)
    sc = 10 ** digits

    def pts(col):
        a = raw[col].str.split(".", expand=True)
        return a[0].astype(np.int64) * sc + a[1].astype(np.int64)
    sp = raw["spread"].astype(np.int64).to_numpy()
    out = {}
    for k, col in zip("ohlc", ("open", "high", "low", "close")):
        p = pts(col).to_numpy()
        out["b" + k] = p / sc                       # exact decimal -> nearest double, as strtod in the mock
        out["a" + k] = (p + sp) / sc
    utc = pont.server_to_utc(raw["time"].astype(np.int64).to_numpy())
    m1 = pd.DataFrame({k: out[k] for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")},
                      index=pd.DatetimeIndex(utc).as_unit("ms").rename("ts"))
    return m1


# ----------------------------------------------------------------------------------------------- lab side
_LAB = {}


def lab():
    if not _LAB:
        import recalc
        import goldlab as gl
        from goldlab import r2
        reg = [s for s in recalc.sleeves() if s[1] == "brk72_24h_wd" and s[2] == "btcusd"]
        assert len(reg) == 1
        _LAB.update(gl=gl, r2=r2, entry=reg[0], strat=sys.modules["r2_crypto_strategy"])
    return _LAB


def lab_run(m1):
    L = lab()
    track, name, sym, make_orders, params = L["entry"]
    orders = make_orders(m1, **params)
    trades = L["r2"].run(sym, make_orders, params, "fp", True, m1)            # recalc.py:98, the official call
    return orders, trades


def lab_hours(m1):
    S = lab()["strat"]
    b = S.h1_bars(m1)
    c = b["c"]
    b["hi"] = c.rolling(72).max().shift(1)
    b["lo"] = c.rolling(72).min().shift(1)
    b["atr"] = S.sma_atr(b, 24)
    b["side"] = np.where(c > b["hi"], 1, np.where(c < b["lo"], -1, 0))
    b["dec"] = pd.to_datetime(b["start"] + 3_600_000, unit="ms", utc=True)
    return b


def lab_trades_table(t, m1):
    x = t[["side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "dec_time", "sched_exit"]].copy()
    x["exit_bar"] = np.where(x.reason == "time", x.exit_time, x.exit_time - pd.Timedelta(minutes=1))
    x["exit_bar"] = pd.to_datetime(x["exit_bar"], utc=True)
    x["artefact"] = x["sched_exit"] > m1.index[-1]           # exit beyond the frame: wrapper's fake 'time' exit or 'eod'
    return x.reset_index(drop=True)


# ----------------------------------------------------------------------------------------------- EA side
def build(work):
    work.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, "-I", "-B", str(HERE / "check" / "to_cpp_spike.py"), str(HERE / "mql5" / "SpikeRobot.mq5"),
                    str(work / "spike.cpp")], check=True)
    (work / "run.cpp").write_text('#include "mock_replay.h"\n#include "spike.cpp"\n')
    exe = work / "replay"
    cmd = ["g++", "-std=c++17", "-O2", "-ffp-contract=off", "-Wall", "-Wno-unused-function", "-Wno-unused-variable",
           "-I", str(HERE / "check"), "-I", str(work), str(work / "run.cpp"), "-o", str(exe)]
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode:
        sys.stderr.write(r.stderr)
        raise SystemExit("compile failed")
    warn = [ln for ln in r.stderr.splitlines() if "warning" in ln]
    return exe, warn


def replay(exe, bars, files, frm=None, to=None, debug=True, extra_env=None, fresh=True):
    files = Path(files)
    if fresh and files.exists():
        for p in sorted(files.rglob("*"), reverse=True):
            p.unlink() if p.is_file() else p.rmdir()
    files.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, MOCK_FILES=str(files), MOCK_SYMS=SYM, **{f"MOCK_BARS_{SYM}": str(bars), f"MOCK_DIGITS_{SYM}": str(DIGITS)},
               MOCK_INPUT_InpDebugHours="1" if debug else "0")
    if frm is not None:
        env["MOCK_FROM"] = str(int(frm))
    if to is not None:
        env["MOCK_TO"] = str(int(to))
    env.update(extra_env or {})
    t0 = time.perf_counter()
    r = subprocess.run([str(exe)], env=env, capture_output=True, text=True)
    wall = time.perf_counter() - t0
    if r.returncode:
        raise SystemExit(f"replay failed: {r.stdout}\n{r.stderr}")
    return r.stdout.strip(), wall


def read_journal(files):
    rows = {"HB": [], "EV": [], "DEC": [], "TRD": [], "REAL": [], "INIT": []}
    for ln in (Path(files) / "spike_journal.csv").read_text().splitlines():
        f = ln.split(",")
        rows.setdefault(f[0], []).append(f[1:])
    u = lambda s: pd.to_datetime(pd.Series(s, dtype="int64"), unit="s", utc=True)
    out = {}
    if rows["HB"]:
        h = pd.DataFrame(rows["HB"], columns=["code", "start", "o", "h", "l", "c", "cnt"])
        h["start"] = u(h.start.astype(np.int64))
        for k in "ohlc":
            h[k] = h[k].astype(float)
        h["cnt"] = h.cnt.astype(int)
        out["HB"] = h
    if rows["EV"]:
        e = pd.DataFrame(rows["EV"], columns=["code", "dec", "side", "hi", "lo", "atr"])
        e["dec"] = u(e.dec.astype(np.int64))
        e["side"] = e.side.astype(int)
        for k in ("hi", "lo", "atr"):
            e[k] = e[k].astype(float)
        out["EV"] = e
    d = pd.DataFrame(rows["DEC"], columns=["code", "dec", "side", "atr", "stop_dist", "bar", "status"])
    d["dec"], d["bar"] = u(d.dec.astype(np.int64)), u(d.bar.astype(np.int64))
    d["side"] = d.side.astype(int)
    d["atr"], d["stop_dist"] = d.atr.astype(float), d.stop_dist.astype(float)
    out["DEC"] = d
    t = pd.DataFrame(rows["TRD"], columns=["code", "dec_time", "entry_time", "side", "entry", "stop", "exit_bar", "exit", "reason", "atr",
                                           "exit_at"])
    for k in ("dec_time", "entry_time", "exit_bar", "exit_at"):
        t[k] = u(t[k].astype(np.int64))
    t["side"] = t.side.astype(int)
    for k in ("entry", "stop", "exit", "atr"):
        t[k] = t[k].astype(float)
    out["TRD"] = t
    out["REAL"] = pd.DataFrame(rows["REAL"], columns=["code", "what", "ticket", "price", "sl", "retcode", "t"]) if rows["REAL"] else None
    out["INIT"] = rows["INIT"]
    return out


def read_deals(files):
    p = Path(files) / "_mock" / "deals.csv"
    d = pd.read_csv(p, header=None, names=["deal", "position", "time", "symbol", "type", "entry", "volume", "price", "reason", "magic",
                                           "comment"], float_precision="round_trip")
    import pont
    d["utc"] = pont.server_to_utc(d["time"].to_numpy())
    ins, outs = d[d.entry == 0].set_index("position"), d[d.entry == 1].set_index("position")
    t = pd.DataFrame({"entry_time": ins.utc, "side": np.where(ins.type == 0, 1, -1), "entry": ins.price})
    t = t.join(pd.DataFrame({"exit_bar": outs.utc, "exit": outs.price, "reason": np.where(outs.reason == 4, "stop", "time")}))
    return t.reset_index()


# ----------------------------------------------------------------------------------------------- comparisons
def cmp_hours(ea, labh):
    lb = labh.copy()
    lb["start_t"] = pd.to_datetime(lb.start, unit="ms", utc=True)
    m = lb.merge(ea, left_on="start_t", right_on="start", how="outer", suffixes=("_lab", "_ea"), indicator=True)
    both = m[m._merge == "both"]
    eq = {k: int((both[f"{k}_lab"] == both[f"{k}_ea"]).sum()) for k in ("o", "h", "l", "c", "cnt")}
    return {"lab_hours": int(len(lb)), "ea_hours": int(len(ea)), "both": int(len(both)),
            "only_lab": [str(x) for x in m.loc[m._merge == "left_only", "start_t"]],
            "only_ea": [str(x) for x in m.loc[m._merge == "right_only", "start_ea"]],
            "bitwise_equal": eq}


def cmp_evals(ea, labh):
    lb = labh.dropna(subset=["hi", "atr"])
    m = lb.merge(ea, on="dec", how="inner", suffixes=("_lab", "_ea"))
    rel = ((m.atr_lab - m.atr_ea).abs() / m.atr_lab)
    return {"evaluations": int(len(m)), "lab_evaluable": int(len(lb)), "ea_evaluations": int(len(ea)),
            "side_equal": int((m.side_lab == m.side_ea).sum()),
            "hi_lo_bitwise_equal": int(((m.hi_lab == m.hi_ea) & (m.lo_lab == m.lo_ea)).sum()),
            "atr_bitwise_equal": int((m.atr_lab == m.atr_ea).sum()), "atr_max_rel_diff": float(rel.max()),
            "atr_max_ulps": float(((m.atr_lab - m.atr_ea).abs() / np.spacing(m.atr_lab.to_numpy())).max())}


ELIGIBLE = ("taken", "taken_paper", "busy", "exit_bar")


def cmp_decisions(ea_dec, orders, m1, cut):
    o = orders.copy()
    o["entry_t"] = m1.index[o.entry_i.to_numpy()]
    o = o[o.dec_time < cut]
    d = ea_dec[ea_dec.dec < cut]
    e = d[d.status.isin(ELIGIBLE)]
    m = o.merge(e, left_on="dec_time", right_on="dec", how="outer", suffixes=("_lab", "_ea"), indicator=True)
    both = m[m._merge == "both"]
    return {"lab_orders": int(len(o)), "ea_eligible_signals": int(len(e)), "both": int(len(both)),
            "only_lab": [str(x) for x in m.loc[m._merge == "left_only", "dec_time"]],
            "only_ea": [str(x) for x in m.loc[m._merge == "right_only", "dec"]],
            "side_equal": int((both.side_lab == both.side_ea).sum()),
            "entry_bar_equal": int((both.entry_t == both.bar).sum()),
            "stop_dist_bitwise_equal": int((both.stop_dist_lab == both.stop_dist_ea).sum()),
            "stop_dist_max_abs_diff": float((both.stop_dist_lab - both.stop_dist_ea).abs().max()) if len(both) else 0.0,
            "ea_status_counts": d.status.value_counts().to_dict()}


def cmp_trades(a, b, key=("entry_time", "side"), names=("lab", "ea")):
    """trade-by-trade: same entry minute and side, then exit minute, reason, prices"""
    k = list(key)
    m = a.merge(b, on=k, how="outer", suffixes=(f"_{names[0]}", f"_{names[1]}"), indicator=True)
    both = m[m._merge == "both"].copy()
    n0, n1 = names
    same_exit = (both[f"exit_bar_{n0}"] == both[f"exit_bar_{n1}"]) & (both[f"reason_{n0}"] == both[f"reason_{n1}"])
    res = {f"{n0}_trades": int(len(a)), f"{n1}_trades": int(len(b)), "same_entry_minute_and_side": int(len(both)),
           f"only_{n0}": int((m._merge == "left_only").sum()), f"only_{n1}": int((m._merge == "right_only").sum()),
           "same_exit_minute_and_reason": int(same_exit.sum())}
    for c in ("entry", "stop", "exit"):
        if f"{c}_{n0}" in both and f"{c}_{n1}" in both:
            d = (both[f"{c}_{n0}"] - both[f"{c}_{n1}"]).abs()
            res[f"{c}_bitwise_equal"] = int((d == 0).sum())
            res[f"{c}_max_abs_diff"] = float(d.max()) if len(d) else 0.0
    return res, m


def explain_official_vs_rounded(off_o, off_t, reb_o, reb_t, m1_off, m1_reb, labh_off, labh_reb):
    """every trade that is not identical between the lab on the official frame and the lab on the rounded frame"""
    res, m = cmp_trades(off_t, reb_t, names=("off", "rnd"))
    od = off_o.set_index("dec_time")
    rd = reb_o.set_index("dec_time")
    hb_o = labh_off.set_index("dec")
    hb_r = labh_reb.set_index("dec")
    rows = []
    for _, r in m.iterrows():
        if r._merge == "both" and r.exit_bar_off == r.exit_bar_rnd and r.reason_off == r.reason_rnd:
            continue
        dec = r.dec_time_off if r._merge != "right_only" else r.dec_time_rnd
        row = {"entry_time": str(r.entry_time), "side": int(r.side), "in": r._merge, "dec": str(dec)}
        if r._merge == "both":
            row["kind"] = "same entry, other exit"
            row["exit_off"] = f"{r.exit_bar_off} {r.reason_off}"
            row["exit_rnd"] = f"{r.exit_bar_rnd} {r.reason_rnd}"
            # the stop touched in one frame only: distance of the stop from the extreme on the official frame
            bar = r.exit_bar_off if r.reason_off == "stop" else r.exit_bar_rnd
            col = "bl" if r.side > 0 else "ah"
            row["stop_off"], row["stop_rnd"] = float(r.stop_off), float(r.stop_rnd)
            row["extreme_off"], row["extreme_rnd"] = float(m1_off.loc[bar, col]), float(m1_reb.loc[bar, col])
        else:
            in_o, in_r = dec in od.index, dec in rd.index
            if in_o and in_r:
                row["kind"] = "signal in both frames, skipped in one (chain: an earlier trade differs)"
            else:
                row["kind"] = "signal in one frame only (channel break flipped by rounding)"
                h_o, h_r = hb_o.loc[dec], hb_r.loc[dec]
                ref = h_o.hi if r.side > 0 else h_o.lo
                ref_r = h_r.hi if r.side > 0 else h_r.lo
                row["break_off_bp"] = float(r.side * (h_o.c - ref) / h_o.c * 1e4)
                row["break_rnd_bp"] = float(r.side * (h_r.c - ref_r) / h_r.c * 1e4)
        rows.append(row)
    return res, rows


# ----------------------------------------------------------------------------------------------- main
def window_run(exe, start, end, tag, restarts=True):
    rep = {}
    m1_off = load_official(start, end)
    bars = OUT / f"btcusd_m1_{tag}.csv"
    t_srv = export(m1_off, bars)
    m1_reb = rebuild(bars)
    assert (m1_reb.index == m1_off.index).all(), "server -> UTC round trip"
    rep["frame"] = {"start": str(m1_off.index[0]), "end": str(m1_off.index[-1]), "bars": int(len(m1_off)),
                    "rounding_max_abs_bid": float((m1_reb.bo - m1_off.bo).abs().max()),
                    "spread_points_median": float(np.median(np.rint((m1_off.ao - m1_off.bo) * 100)))}
    # ---- EA replay (debug journal) and production-like replay (speed)
    files = OUT / f"run_{tag}"
    so, wall = replay(exe, bars, files, debug=True)
    J = read_journal(files)
    so2, wall2 = replay(exe, bars, OUT / f"run_{tag}_nodebug", debug=False)
    months = (m1_off.index[-1] - m1_off.index[0]).days / 30.4375
    rep["speed"] = {"replay_stdout_debug": so, "wall_s_debug": round(wall, 3), "replay_stdout": so2, "wall_s": round(wall2, 3),
                    "simulated_months": round(months, 2), "months_per_second": round(months / wall2, 1)}
    # ---- lab on the rebuilt frame (a)
    t0 = time.perf_counter()
    reb_o, reb_t = lab_run(m1_reb)
    rep["speed"]["lab_python_s"] = round(time.perf_counter() - t0, 3)
    labh_reb = lab_hours(m1_reb)
    lt = lab_trades_table(reb_t, m1_reb)
    cut = m1_reb.index[-1] - pd.Timedelta(days=1)
    ea_t = J["TRD"]
    rep["a_hours"] = cmp_hours(J["HB"], labh_reb) if "HB" in J else None
    rep["a_evaluations"] = cmp_evals(J["EV"], labh_reb) if "EV" in J else None
    rep["a_decisions"] = cmp_decisions(J["DEC"], reb_o, m1_reb, cut)
    lab_in = lt[~lt.artefact]
    res, m = cmp_trades(lab_in, ea_t)
    res["lab_trades_excluded_as_frame_end_artefacts"] = int(lt.artefact.sum())
    res["ea_trade_open_at_end"] = int(len(J["DEC"][J["DEC"].status == "taken"]) - len(ea_t))
    res["mismatches"] = m[(m._merge != "both") | (m.exit_bar_lab != m.exit_bar_ea) | (m.reason_lab != m.reason_ea)][
        ["entry_time", "side", "_merge", "exit_bar_lab", "reason_lab", "exit_bar_ea", "reason_ea"]].astype(str).to_dict("records")
    rep["a_trades"] = res
    # broker (the mock's deals) against the lab
    deals = read_deals(files)
    resb, mb = cmp_trades(lab_in[["entry_time", "side", "entry", "exit", "exit_bar", "reason"]], deals, names=("lab", "broker"))
    resb["mismatches"] = mb[(mb._merge != "both") | (mb.exit_bar_lab != mb.exit_bar_broker)][
        ["entry_time", "side", "_merge", "exit_bar_lab", "reason_lab", "exit_bar_broker", "reason_broker"]].astype(str).to_dict("records")
    rep["a_broker"] = resb
    rep["a_real_actions"] = J["REAL"].what.value_counts().to_dict() if J["REAL"] is not None else {}
    # ---- (b) the official frame
    off_o, off_t = lab_run(m1_off)
    labh_off = lab_hours(m1_off)
    ot = lab_trades_table(off_t, m1_off)
    resx, rows = explain_official_vs_rounded(off_o, ot[~ot.artefact], reb_o, lt[~lt.artefact], m1_off, m1_reb, labh_off, labh_reb)
    resx["R_sum_official"] = float(off_t[~ot.artefact.to_numpy()].R.sum())
    resx["R_sum_rounded"] = float(reb_t[~lt.artefact.to_numpy()].R.sum())
    resx["orders_official"], resx["orders_rounded"] = int(len(off_o)), int(len(reb_o))
    so_ = set(off_o.dec_time.astype("int64")) ; sr_ = set(reb_o.dec_time.astype("int64"))
    resx["signals_only_official"], resx["signals_only_rounded"] = len(so_ - sr_), len(sr_ - so_)
    resx["differences"] = rows
    rep["b_official_vs_rounded"] = resx
    resy, _ = cmp_trades(ot[~ot.artefact], ea_t, names=("official", "ea"))
    rep["b_official_vs_ea"] = resy
    # ---- restarts
    if restarts:
        rep["restarts"] = restart_tests(exe, bars, t_srv, J)
    return rep


def restart_tests(exe, bars, t_srv, J_full):
    rng = np.random.default_rng(20261112)
    out = {}
    base = J_full["TRD"].drop(columns=["code"]).astype(str).to_csv(index=False)
    base_dec = J_full["DEC"].drop(columns=["code"]).astype(str).to_csv(index=False)
    # 1) 25 restarts at random minutes, no downtime: must be identical to the run without restart
    cuts = np.sort(rng.choice(t_srv[2000:-2000], 25, replace=False))
    files = OUT / "run_restart0"
    edges = [None] + list(cuts) + [None]
    for i in range(len(edges) - 1):
        replay(exe, bars, files, frm=edges[i], to=edges[i + 1], debug=False, fresh=(i == 0))
    J = read_journal(files)
    same = J["TRD"].drop(columns=["code"]).astype(str).to_csv(index=False) == base
    same_dec = J["DEC"].drop(columns=["code"]).astype(str).to_csv(index=False) == base_dec
    deals = read_deals(files)
    out["no_downtime"] = {"restarts": len(cuts), "trades_identical": bool(same), "decisions_identical": bool(same_dec),
                          "inits": len(J["INIT"]), "broker_trades": int(len(deals)), "paper_trades": int(len(J["TRD"]))}
    # 2) 10 outages of 30 min to 6 h: the paper chain must stay identical (catch-up), real trades can be missed or late
    files = OUT / "run_outage"
    starts = np.sort(rng.choice(t_srv[2000:-20000], 10, replace=False))
    downs = rng.integers(30, 361, 10) * 60
    edges = []
    for s, dwn in zip(starts, downs):
        edges.append((s, s + dwn))
    frm = None
    for i, (s, e) in enumerate(edges):
        replay(exe, bars, files, frm=frm, to=s, debug=False, fresh=(i == 0))
        frm = e
    replay(exe, bars, files, frm=frm, to=None, debug=False, fresh=False)
    J2 = read_journal(files)
    a = J_full["TRD"].drop(columns=["code"])
    b = J2["TRD"].drop(columns=["code"])
    same2 = a.astype(str).to_csv(index=False) == b.astype(str).to_csv(index=False)
    deals2 = read_deals(files)
    st = J2["DEC"].status.value_counts().to_dict()
    out["outages"] = {"outages_min": [int(x // 60) for x in downs], "paper_trades_identical": bool(same2),
                      "paper_trades": int(len(b)), "broker_trades": int(len(deals2)),
                      "decisions_status": st, "real_actions": J2["REAL"].what.value_counts().to_dict() if J2["REAL"] is not None else {}}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--long", action="store_true", help="also replay the whole in-sample history of btcusd")
    a = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    t0 = time.perf_counter()
    exe, warn = build(OUT / "build")
    report = {"build": {"seconds": round(time.perf_counter() - t0, 2), "warnings": warn}}
    report["window"] = window_run(exe, "2020-12-01", "2021-07-01", "2020-12_2021-06")
    if a.long:
        report["long"] = window_run(exe, "2017-01-01", "2022-01-01", "is_all", restarts=False)
    (OUT / "results.json").write_text(json.dumps(report, indent=1, default=str))
    print(json.dumps(report, indent=1, default=str)[:20000])


if __name__ == "__main__":
    main()
