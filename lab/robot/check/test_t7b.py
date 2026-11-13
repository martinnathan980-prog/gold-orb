"""T7b account (step K): the whole EA in the replay mock against growth.engine, 2018-02 to 2021-12, plans F3S, F2S and
F1S, F3S with the three changes on, and D2 (the default plan: PROTOCOL_V3 Addendum G).

    python3 -I lab/robot/check/test_t7b.py [--plans F3S,F2S,F1S,F3S_on,D2] [--readings] [--keep]

--readings: also D2 and S7 with the crypto margin at 1:2 (MOCK_LEV_BTCUSD.r = MOCK_LEV_ETHUSD.r = 2; FP's retail crypto
margin may be 50 %, review F11): a reading, never a pass condition. Each reports the EA's MARGIN skips per sleeve and the
same plan run by growth.engine with that leverage on crypto (summary_readings.json).

The EA: dist/ClaudeRobot.mq5, harness build with CR_NO_GUARD (SPEC 7 T7b: the plans without the disaster guard) and
CR_BRK_NOTIONAL_X raised (the lab's engine has no cap on a position's value; the release build cuts a position to 20 x the
balance and its self-test refuses any other value: the requests that cap would cut are counted, notional_20x_would_cut,
as the volume cap's are), all ten real rules, J's follower and broker, I's ledger and sizing. The plan inputs are explicit: F3S, F2S, F1S with their stop
(InpStopFallPct 25, InpStopArmPaid 12000), D2 with none (InpStopFallPct 0, InpGuard false: SPEC 1's defaults). It trades (InpTrade true) on a demo account in the replay
mock from 2018-02-01 00:00 server (its first start rebuilds 120 / 60 days of history before that) to 2022-01-01:
1,000 EUR at the start (InpPlanStart = the start) and 1,000 EUR on the first of each month (DEAL_TYPE_BALANCE deals),
fast mode (broker stops checked at bar end with the lab rule), no broker commission on gold (MOCK_COMM_XAUUSD.r=0: the
exported spread already holds the lab's commission, SPEC 7) and no volume cap (MOCK_VMAX: the lab's engine has none; the
requests a 100-lot cap would cut are counted).
The reference: growth.run_one (and test_account.mirror, I's recording copy of growth.engine, bit for bit the same) fed
the EA's own trades and payments: one trade per sizing request of the EA (its SIZE line: stamp, sleeve), with
  t_in    the stamp (the paper fill bar; growth's entry time)
  t_out   the EA's own close stamp from the mock's deal (SL or stop-out in minute X: X + 60 s, an EA close in minute X: X;
          SPEC 5, sim.py:283-284), or the paper exit stamp for a request the EA skipped
  entry   the paper fill (growth's margin price)
  risk    the EA's sizing risk r of SPEC 4.2 (the SIZE line); with a change on, r / f (the frozen stake factor)
  pnl     side x (real exit - real entry) of the EA's position (the money the account booked), else the paper's
and the payments at their deal times. Checked equal: taken count, skips by reason (minimum lot, caps, margin), the
stop week, the money paid in by week, the weekly balances within 0.01 EUR, and per trade the lots and the skip.
Listed, never silent (SPEC 7 T7b's exceptions):
  P1    late intents (stop, limit, OCO: GFP, D4H, ORX) whose quote risk exceeded the paper risk: r (and so the lots)
        differ from the paper's |fill - stop| (counted per sleeve, with the largest ratio);
  P5    MISSED reason=exited intents (no sizing request, the lab books the trade, the account does not);
  open  positions still open at the end: kept as open positions until the end (caps, margin), booking nothing;
  NOT_READY  requests the EA skipped because their symbol's history did not cover SPEC 2.2's depth yet (ETH's data
        starts 2018-01-01, so ETH is READY from 2018-03-02): not requests the account could size, left out and listed;
  razor a stop distance r that differs from the paper's |fill - stop| by rounding only.
Outputs: check/out/test_t7b/summary.json.
"""
import argparse
import calendar
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

sys.dont_write_bytecode = True
os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(LAB, "r2", "tracks", "stake"))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import compare  # noqa: E402
import test_worlds as W  # noqa: E402  (step J: positions from the mock's deals, clock conversions)
import test_account as TA  # noqa: E402  (step I: mirror, the recording copy of growth.engine)
import growth as G  # noqa: E402
import stake as S  # noqa: E402
from build import build  # noqa: E402

OUT = os.path.join(HERE, "out", "test_t7b")
DIST = os.path.join(ROBOT, "dist", "ClaudeRobot.mq5")
CODES = W.CODES
LAB_OF = {v: k for k, v in TA.CODE.items()}                     # code -> lab sleeve name
SYM_OF = {c: LAB_OF[c].rsplit("_", 1)[1] for c in CODES}
FACTOR = {"BKB": 0.771793, "F1E": 0.750978}                     # SPEC 5 (CR_Registry CR_FACTOR_S075, CR_FACTOR_H2)
PLANS = {"F3S": ("0:3;3000:2;6000:1;12000:0.5", "off"), "F2S": ("0:2;6000:1;12000:0.5", "off"), "F1S": ("0:1;12000:0.5", "off"),
         "F3S_on": ("0:3;3000:2;6000:1;12000:0.5", "on"), "D2": ("0:10;3000:5;10000:2;20000:1", "off")}
READINGS = {"D2_lev2": ("0:10;3000:5;10000:2;20000:1", "off"), "S7_lev2": ("0:7;3000:3.5;10000:1.4;20000:0.7", "off")}
# InpStopFallPct, InpStopArmPaid, InpGuard of each plan (SPEC 1): the stopped plans of growth.STOPPED, and D2 / S7 without
# stop or guard (the T7b build has CR_NO_GUARD in any case)
STOP_OF = {"F3S": ("25", "12000", "false"), "F2S": ("25", "12000", "false"), "F1S": ("25", "12000", "false"),
           "D2": ("0", "12000", "false"), "S7": ("0", "12000", "false")}
LEV2 = 2.0                                                       # the reading's crypto leverage (margin 50 %)
START_SRV = calendar.timegm((2018, 2, 1, 0, 0, 0))
END_SRV = calendar.timegm((2022, 1, 1, 0, 0, 0))
DEAL_SL, DEAL_SO = 4, 6
ENV = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")


def log(m):
    print(m, flush=True)


def payments():
    """1,000 EUR on the first of each month from 2018-03 to 2021-12, 00:00 server"""
    out = []
    for y in range(2018, 2022):
        for mth in range(1, 13):
            t = calendar.timegm((y, mth, 1, 0, 0, 0))
            if START_SRV < t < END_SRV:
                out.append((t, 1000.0))
    return out


def k1t():
    p = os.path.join(HERE, "out", "test_E", "test_changes.json")
    v = json.load(open(p)).get("k1_folds", {}).get("inpk1t_rebuilt") if os.path.exists(p) else None
    return v or "2019:505.84441393264945;2020:496.6915507295559;2021:465.14468666253265"


def run(exe, name):
    table, sw = PLANS[name] if name in PLANS else READINGS[name]
    fall, arm, guard = STOP_OF[name.split("_")[0]]
    files = os.path.join(OUT, name)
    if os.path.isdir(files):
        shutil.rmtree(files)
    os.makedirs(os.path.join(files, "_mock"))
    pp = os.path.join(files, "_mock", "payments.csv")
    with open(pp, "w") as f:
        f.write("\n".join(f"{t},{a}" for t, a in payments()) + "\n")
    on = "1" if sw == "on" else "0"
    e = dict(ENV, MOCK_FILES=files, MOCK_SYMS=",".join(W.SYMS), MOCK_QUIET="1", MOCK_FROM=str(START_SRV), MOCK_TO=str(END_SRV),
             MOCK_BALANCE="1000", MOCK_PAYMENTS=pp, MOCK_INPUT_InpTrade="true", MOCK_INPUT_InpPlanStart=str(START_SRV),
             MOCK_INPUT_InpRiskTable=table, MOCK_INPUT_InpStopFallPct=fall, MOCK_INPUT_InpStopArmPaid=arm, MOCK_INPUT_InpGuard=guard,
             MOCK_INPUT_InpPush="false", MOCK_INPUT_InpK1=on, MOCK_INPUT_InpH2=on, MOCK_INPUT_InpS075=on,
             MOCK_INPUT_InpK1T=k1t() if sw == "on" else "",
             MOCK_COMM_XAUUSD_r="0")
    # the exported gold spread already holds the lab's commission (SPEC 7: CR_XAU_COMM_PTS=0 in harness builds), so the mock
    # broker must not charge its default 3 USD per side per lot on top: the account then books exactly the lab's money
    e["MOCK_COMM_XAUUSD.r"] = e.pop("MOCK_COMM_XAUUSD_r")
    # the lab's engine has no volume cap; the mock's SYMBOL_VOLUME_MAX (100 lots) would cut the largest ETH orders late in
    # the period (BrkOpen journals SEND cut=vmax): raised here so that the account books growth's lots; the trades a 100-lot
    # cap would cut are counted (vmax_100_would_cut) - FP's real caps are a Mac item (SPEC 10.6)
    for s_ in W.SYMS:
        e[f"MOCK_VMAX_{s_}"] = "1000000"
    for s, p in W.bar_paths().items():
        e[f"MOCK_BARS_{s}"] = p
    if name.endswith("_lev2"):
        for s_ in ("BTCUSD.r", "ETHUSD.r"):
            e[f"MOCK_LEV_{s_}"] = repr(LEV2)
    t0 = time.time()
    r = subprocess.run([exe], env=e, capture_output=True, text=True, timeout=10800)
    if r.returncode:
        raise RuntimeError(f"{name}: replay failed ({r.returncode}) {r.stdout[-1500:]} {r.stderr[-1500:]}")
    return files, round(time.time() - t0, 1), r.stdout.strip()


def close_stamp_srv(t_out, reason):
    """the ledger's stamp of a close (SPEC 5): SL / stop-out in minute X -> X + 60 s, an EA close -> X (server seconds)"""
    m = int(t_out) - int(t_out) % 60
    return m + 60 if int(reason) in (DEAL_SL, DEAL_SO) else m


def frame_of(files, name):
    """the reference input: one trade per live SIZE line, the EA's position (if any) and the paper trade"""
    rows = compare.read_journal(files)
    sw = (PLANS[name] if name in PLANS else READINGS[name])[1]
    size = [r for r in rows if r["ev"] == "SIZE" and r.get("rp") != 1]
    missed = [r for r in rows if r["ev"] == "MISSED" and r.get("rp") != 1]
    pos = W.positions(files)
    paper, still_open = {}, {}
    for c in CODES:
        done, void = compare.paper_chain(rows, c)
        for oid, (f, x) in done.items():
            paper[oid] = (f, x)
        for r in rows:                                          # paper trades still open when the run ends
            if r["ev"] == "PFILL" and r["code"] == c and r["oid"] not in done and r["oid"] not in void:
                still_open[r["oid"]] = r
    end_utc = W.srv_to_utc(END_SRV)
    used, recs, lists = set(), [], {"P1": {}, "razor": {}, "open_at_end": [], "no_paper_trade": [], "notready": {}}
    for r in size:
        c, oid, S0 = r["code"], int(r["oid"]), int(r["utc"])
        if r.get("skip") == "notready":
            # SPEC 2.2: a symbol whose history does not cover its depth is NOT_READY and its sleeves enter nothing (ETH's data
            # starts 2018-01-01: 60 days are there on 2018-03-02); not a request the account could size: left out, listed
            lists["notready"].setdefault(c, []).append(S0)
            continue
        p = pos[(pos.code == c) & (pos.u_in >= S0) & (pos.u_in <= S0 + 300)] if len(pos) else pos
        p = p[~p.position.isin(used)] if len(p) else p
        pt = paper.get(oid)
        if pt is None and oid in still_open:
            # open when the run ends: kept as an open position (caps, margin) until the end, booking nothing
            pt = (still_open[oid], {"utc": end_utc, "px": float(still_open[oid]["px"])})
        if pt is None:
            lists["no_paper_trade"].append({"code": c, "oid": oid})
            continue
        f, x = pt
        side = int(f["side"])
        fill, st0 = float(f["px"]), float(f["st0"])
        risk_paper = abs(fill - st0)
        r_ea = float(r["r"]) if r.get("skip") not in ("notallowed",) and float(r.get("r", 0.0)) > 0 else risk_paper
        if abs(r_ea - risk_paper) > 0:
            rel = abs(r_ea - risk_paper) / risk_paper
            kind = "P1" if (int(r.get("late", 0)) == 1 and r_ea > risk_paper and rel > 1e-12) else "razor"
            e_ = {"oid": oid, "r": r_ea, "paper_risk": risk_paper, "ratio": r_ea / risk_paper, "lots": float(r["lots"])}
            if kind == "P1" and r.get("skip") == "none":
                # the lots the paper risk would give, with the EA's own B, rate, m and f (growth.py:296)
                upl = {"xauusd": 100.0, "us100": 1.0, "btcusd": 1.0, "ethusd": 1.0}[SYM_OF[c]]
                step = 0.1 if SYM_OF[c] == "us100" else 0.01
                per_lot = risk_paper * upl * 0.89
                e_["lots_paper"] = float(np.floor(float(r["B"]) * float(r["rate"]) * float(r["m"]) * float(r["f"]) / 100.0 / per_lot / step
                                                  + 1e-9) * step)
            lists[kind].setdefault(c, []).append(e_)
        taken = r.get("skip") == "none" and len(p) > 0
        if taken:
            q = p.iloc[0]
            used.add(int(q.position))
            if pd.isna(q.get("t_out", np.nan)):
                lists["open_at_end"].append({"code": c, "oid": oid})
                pnl, t_out = 0.0, end_utc
            else:
                pnl = side * (float(q.px_out) - float(q.px_in))
                t_out = W.srv_to_utc(close_stamp_srv(q.t_out, q.reason_out))
        else:
            pnl = side * (float(x["px"]) - fill)
            t_out = int(x["utc"])
        f_ = FACTOR.get(c, 1.0) if sw == "on" else 1.0
        recs.append({"sleeve": LAB_OF[c], "sym": SYM_OF[c], "fam": S.FAMILY[SYM_OF[c]], "t_in": pd.Timestamp(S0, unit="s", tz="UTC"),
                     "t_out": pd.Timestamp(max(t_out, S0), unit="s", tz="UTC"), "entry": fill, "risk": r_ea / f_, "pnl": pnl,
                     "R": pnl / r_ea, "code": c, "oid": oid, "skip_ea": r.get("skip"), "lots_ea": float(r["lots"]), "m_ea": float(r["m"]),
                     "taken_ea": taken})
    d = pd.DataFrame(recs)
    d = d.sort_values(["t_in", "sleeve"], kind="stable").reset_index(drop=True)
    p5 = [m for m in missed if m.get("reason") == "exited"]
    other_missed = [m for m in missed if m.get("reason") != "exited"]
    return d, rows, pos, lists, p5, other_missed


UNITS = {"N30": 1.0, "OC4": 1.0, "BKB": 1.0, "BKE": 1.0, "F1B": 1.0, "F1E": 1.0, "NQB": 1.0, "GFP": 100.0, "D4H": 100.0, "ORX": 100.0}


def notional_cuts(rows):
    """the taken requests whose position value (lots x units x quote x 0.89, the mock's tick value) exceeds 20 x the
    balance at sizing: the release build would cut them (CR_Broker, cut=notional); per sleeve"""
    out = {}
    for r in rows:
        if r["ev"] != "SIZE" or r.get("rp") == 1 or r.get("skip") != "none":
            continue
        v = float(r["lots"]) * UNITS[r["code"]] * float(r["quote"]) * 0.89
        if v > 20.0 * float(r["B"]):
            out[r["code"]] = out.get(r["code"], 0) + 1
    return out


def ea_weeks(pos, files, week_monday):
    """the EA's balance at the start of each week after w (server Mondays), with the ledger's stamps"""
    deals = W.deals(files)
    bal = deals[deals.type == 2]                                  # DEAL_TYPE_BALANCE
    money = []
    for r in pos.itertuples():
        if pd.isna(getattr(r, "t_out", np.nan)):
            continue
        dd = deals[(deals.position == r.position)]
        m = float((dd.profit + dd.commission + dd.swap).sum())
        money.append((close_stamp_srv(r.t_out, r.reason_out), m))
    money += [(int(t), float(a)) for t, a in zip(bal.time, bal.profit)]
    money.sort()
    t = np.array([a for a, _ in money], np.int64)
    v = np.cumsum([b for _, b in money])
    mon = week_monday.values.astype("datetime64[s]").astype(np.int64)
    out = []
    for w in range(len(mon)):
        nxt = mon[w] + 7 * 86400
        k = int(np.searchsorted(t, nxt, side="left"))
        out.append(1000.0 + (float(v[k - 1]) if k > 0 else 0.0))
    paid = []
    bt = np.array(sorted(int(x) for x in bal.time), np.int64)
    for w in range(len(mon)):
        paid.append(1000.0 + 1000.0 * int(np.searchsorted(bt, mon[w] + 7 * 86400, side="left")))
    return np.array(out), np.array(paid)


def check_plan(exe, name):
    files, wall, mock = run(exe, name)
    d, rows, pos, lists, p5, other_missed = frame_of(files, name)
    plan = name.split("_")[0]
    x = G.arrays(d[["sleeve", "sym", "fam", "t_in", "t_out", "entry", "risk", "pnl", "R"]], price_level="is")
    mon0 = x["week_monday"][0].value
    pays = payments()
    dep_srv = np.array([t for t, _ in pays], np.int64)
    dep_t = np.array([W.srv_to_utc(int(t)) * 10 ** 9 for t in dep_srv], np.int64)
    dep_wk = ((dep_srv * 10 ** 9 - mon0) // (7 * 86400 * 10 ** 9)).astype(np.int64)
    dep_amt = np.full(len(pays), 1000.0)
    if name.endswith("_lev2"):
        crypto = np.array([str(v).endswith(("_btcusd", "_ethusd")) for v in x["sleeve"]])
        x["lev"] = np.where(crypto, LEV2, x["lev"])               # the reading: growth.engine with the same crypto leverage
    pk = G.pack(x)
    eq_wk, paid_wk, cnt = G.run_one(pk, x["pnl"], plan, dep_t, dep_wk, dep_amt, start=1000.0)
    m_eq, m_paid, m_cnt, rec = TA.mirror(x, x["pnl"], plan, dep_t, dep_wk, dep_amt)
    mirror_same = bool(np.array_equal(m_eq, eq_wk) and np.array_equal(m_paid, paid_wk) and np.array_equal(m_cnt, cnt))
    ea_eq, ea_paid = ea_weeks(pos, files, x["week_monday"])
    n = len(d)
    sk_ea = d.skip_ea.value_counts().to_dict()
    # per trade: the EA's skip and lots against the recording copy
    per_diff, first = 0, None
    for i, r in d.iterrows():
        lr = rec[i]
        lab_skip = lr["skip"]
        ea_skip = r.skip_ea if r.skip_ea in ("none", "min_lot", "cap", "margin", "stopped") else "other:" + str(r.skip_ea)
        same = (lab_skip == ea_skip) and (lab_skip != "none" or (r.taken_ea and float(lr["lots"]) == r.lots_ea))
        if not same:
            per_diff += 1
            if first is None:
                first = {"i": int(i), "code": r.code, "oid": int(r.oid), "t_in": str(r.t_in), "ea": [ea_skip, r.lots_ea],
                         "lab": [lab_skip, lr.get("lots")]}
    taken_ea = int(d.taken_ea.sum())
    stop_lines = [r for r in rows if r["ev"] == "STOP"]
    dB = np.abs(ea_eq - eq_wk)
    dP = np.abs(ea_paid - paid_wk)
    res = {"plan": name, "wall_s": wall, "mock": mock, "requests": n, "taken_ea": taken_ea, "taken_lab": int(cnt[0]),
           "skips_ea": sk_ea, "skips_lab": {"min_lot": int(cnt[2]), "cap": int(cnt[3]), "margin": int(cnt[4]), "rule": int(cnt[1]),
                                            "stopped": int(n - cnt[0] - cnt[1] - cnt[2] - cnt[3] - cnt[4])},
           "stop_week_lab": int(cnt[5]) if int(cnt[7]) == 1 else -1, "minus_50_rule_week_lab": int(cnt[5]),
           "stop_lines_ea": len(stop_lines), "weeks": int(len(eq_wk)),
           "margin_skips_ea_by_sleeve": {c: int(((d.code == c) & (d.skip_ea == "margin")).sum()) for c in CODES
                                         if ((d.code == c) & (d.skip_ea == "margin")).any()},
           "margin_skips_lab_by_sleeve": {c: int(sum(1 for i in range(n) if d.code.iloc[i] == c and rec[i]["skip"] == "margin")) for c in CODES
                                          if any(d.code.iloc[i] == c and rec[i]["skip"] == "margin" for i in range(n))},
           "max_abs_diff_weekly_balance_eur": float(dB.max()), "max_abs_diff_weekly_paid_eur": float(dP.max()),
           "final_balance_ea": float(ea_eq[-1]), "final_balance_lab": float(eq_wk[-1]), "paid_in": float(paid_wk[-1]),
           "per_trade_differences": per_diff, "first_difference": first, "engine_copy_equals_run_one": mirror_same,
           "P1_lots": {c: {"quote_risk_larger": len(v), "max_ratio": max(z["ratio"] for z in v),
                           "lots_smaller": sum(1 for z in v if "lots_paper" in z and z["lots"] < z["lots_paper"] - 1e-9)}
                       for c, v in lists["P1"].items()},
           "razor_r": {c: len(v) for c, v in lists["razor"].items()}, "P5_missed_exited": len(p5),
           "P5": [{"code": m["code"], "oid": m.get("oid"), "stamp": m.get("stamp")} for m in p5][:10],
           "other_missed": [{"code": m["code"], "reason": m.get("reason")} for m in other_missed][:10],
           "open_at_end": lists["open_at_end"], "no_paper_trade": lists["no_paper_trade"][:5],
           "vmax_100_would_cut": {c: int(((d.code == c) & (d.lots_ea > 100.0)).sum()) for c in CODES if ((d.code == c) & (d.lots_ea > 100.0)).any()},
           "notional_20x_would_cut": notional_cuts(rows),
           "sends_cut": sum(1 for r in rows if r["ev"] == "SEND" and r.get("cut") not in (None, "", "-", "none")),
           "notready_left_out": {c: {"n": len(v), "first": str(pd.Timestamp(min(v), unit="s", tz="UTC")),
                                     "last": str(pd.Timestamp(max(v), unit="s", tz="UTC"))} for c, v in lists["notready"].items()},
           "errors": [r.get("what") for r in rows if r["ev"] == "ERROR"][:5]}
    ok = (res["taken_ea"] == res["taken_lab"] and per_diff == 0 and float(dB.max()) <= 0.01 and float(dP.max()) <= 0.01
          and mirror_same and not res["errors"] and not other_missed and not lists["no_paper_trade"]
          and res["skips_lab"]["rule"] == 0 and (res["stop_lines_ea"] > 0) == (int(cnt[7]) == 1) and int(cnt[6]) == 0)
    for k in ("min_lot", "cap", "margin"):
        ok = ok and sk_ea.get(k, 0) == res["skips_lab"][k]
    res["pass"] = bool(ok)
    return res, files


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--plans", default=",".join(PLANS))
    ap.add_argument("--readings", action="store_true", help="also D2 and S7 with the crypto margin at 1:2 (a reading only)")
    ap.add_argument("--only-readings", action="store_true")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args(argv)
    t0 = time.time()
    os.makedirs(OUT, exist_ok=True)
    exe, w = build(DIST, name="test_t7b_ng", defines=["CR_NO_GUARD", "CR_BRK_NOTIONAL_X=1e15"])
    names = [] if a.only_readings else a.plans.split(",")
    reads = list(READINGS) if (a.readings or a.only_readings) else []
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(names) + len(reads)))) as ex:
        out = list(ex.map(lambda n: check_plan(exe, n), names + reads))
    res = {r[0]["plan"]: r[0] for r in out if r[0]["plan"] in PLANS}
    rd = {r[0]["plan"]: r[0] for r in out if r[0]["plan"] in READINGS}
    if rd:
        with open(os.path.join(OUT, "summary_readings.json"), "w") as f:
            json.dump({"dist_cr_build": open(DIST).readline().strip(), "crypto_leverage": LEV2, "readings": rd}, f, indent=1, default=str)
        for n, r in rd.items():
            log(f"READING {n} (crypto margin 1:{LEV2:g}): requests {r['requests']}, taken EA {r['taken_ea']} / lab {r['taken_lab']}, "
                f"MARGIN skips EA {r['margin_skips_ea_by_sleeve']} lab {r['margin_skips_lab_by_sleeve']}, skips EA {r['skips_ea']}, final "
                f"{r['final_balance_ea']:.2f} / {r['final_balance_lab']:.2f} ({r['wall_s']} s)")
    if a.only_readings:
        return 0
    summary = {"dist_cr_build": open(DIST).readline().strip(), "build": "harness + CR_NO_GUARD",
               "warnings": len(w), "plans": res, "sec": round(time.time() - t0, 1)}
    summary["pass"] = bool(summary["warnings"] == 0 and all(r["pass"] for r in res.values()))
    with open(os.path.join(OUT, "summary.json"), "w") as f:
        json.dump(summary, f, indent=1, default=str)
    for n, r in res.items():
        log(f"{'PASS' if r['pass'] else 'FAIL'} {n}: requests {r['requests']}, taken EA {r['taken_ea']} / lab {r['taken_lab']}, skips EA "
            f"{r['skips_ea']} lab {r['skips_lab']}, stop week {r['stop_week_lab']} (EA STOP lines {r['stop_lines_ea']}), weekly B max diff "
            f"{r['max_abs_diff_weekly_balance_eur']:.4g} EUR, paid max diff {r['max_abs_diff_weekly_paid_eur']:.4g}, per trade diffs "
            f"{r['per_trade_differences']}, final {r['final_balance_ea']:.2f} / {r['final_balance_lab']:.2f} for {r['paid_in']:.0f} paid, "
            f"P1 {r['P1_lots']}, P5 {r['P5_missed_exited']}, razor r {r['razor_r']}, open at end {len(r['open_at_end'])}, NOT_READY left out "
            f"{r['notready_left_out']} ({r['wall_s']} s)")
        if r["first_difference"]:
            log(f"   first difference: {r['first_difference']}")
    log(f"test_t7b: {'PASS' if summary['pass'] else 'FAIL'} ({summary['sec']} s)")
    if not a.keep:
        for _, files in out:
            shutil.rmtree(files, ignore_errors=True)
    return 0 if summary["pass"] else 1


if __name__ == "__main__":
    sys.exit(main())
