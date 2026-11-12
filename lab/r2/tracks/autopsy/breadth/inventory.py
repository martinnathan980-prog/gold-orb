"""PART 1 -- inventory (no simulation).

1. Instruments with M1 history (lab/data, lab/data/fp, raw folders), in-sample coverage and cost model.
   Only bar timestamps and, for the spread figure, the bid/ask closes of 2019-2021 are read (filters ts < 2022).
2. What the earlier tracks tried with the frozen rules of the ten sleeves on other instruments: every trials file
   under lab/results (round 1, round 2, round 3) is scanned for records whose parameters equal a frozen rule, plus
   the records written in other formats (gold2 silver re-tests, the round-1 cross-market audit, the idea panel's
   JP225 replica), each cited with its file.
3. The table rule x instrument: sleeve / tried and failed (with the number that failed it) / tried and passed /
   never tried, and for the never-tried pairs whether they are in this lens or out of it (with the reason).

Output: results/r2/autopsy/breadth/inventory_instruments.csv, inventory_pairs.csv, inventory.json
"""
import glob
import json
import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import pyarrow.parquet as pq  # noqa: E402

import common as C  # noqa: E402

LAB = C.LAB
IS_END = C.IS_END
FP_SPEC = {k: v for k, v in json.load(open(os.path.join(LAB, "r2", "fp_costs.json"))).items() if not k.startswith("_")}

INSTR = (["us100", "us500", "us30", "ger40", "xauusd", "xagusd", "btcusd", "ethusd"] + C.FX + ["jp225", "wti"] + C.STOCKS)


# ------------------------------------------------------------------------------------------------ 1. instruments
def _ts(path):
    t = pq.read_table(path, columns=["ts"], filters=[("ts", "<", IS_END)])
    return pd.DatetimeIndex(t.column("ts").to_pandas())


def _spread_bp(path):
    t = pq.read_table(path, columns=["ts", "bc", "ac"], filters=[("ts", ">=", pd.Timestamp("2019-01-01", tz="UTC")),
                                                                ("ts", "<", IS_END)]).to_pandas()
    mid = (t.bc + t.ac) / 2
    return round(float(((t.ac - t.bc) / mid).median() * 1e4), 2)


def instruments():
    rows = []
    for s in INSTR:
        if s == "jp225":
            idx = None
            files = sorted(glob.glob(os.path.join(LAB, "data", "raw_jp", "jpnidxjpy-bid-*.csv")))
            fr = [pd.to_datetime(pd.read_csv(f, usecols=["timestamp"]).timestamp, unit="ms", utc=True) for f in files]
            idx = pd.DatetimeIndex(pd.concat(fr)).sort_values()
            idx = idx[idx < IS_END]
            src = "lab/data/raw_jp/jpnidxjpy-{bid,ask}-2013..2021.csv (Dukascopy JPN.IDX/JPY, real bid/ask; no frame built in the lab)"
            cost = ("none in the lab (COSTS_FP.md has no JP225 row; FP figure never read). Declared here: 12 points at 50,000 = "
                    "2.4 bp all-in (other brokers 5.5-10 points, Dukascopy 6-7), slippage 0.5/0.2 bp, swap long 5.5 %")
            spr = round(C.JP225_SPEC["spread"] / C.JP225_SPEC["spread_ref_price"] * 1e4, 2)
            usable = "yes (declared cost model)"
        elif s == "wti":
            path = os.path.join(LAB, "data", "lightcmdusd_m1.parquet")
            idx = _ts(path)
            src = "lab/data/lightcmdusd_m1.parquet (round 1: Dukascopy LIGHT.CMD/USD BID only, ask = bid + fixed 0.04 USD)"
            cost = ("none at FP; round-1 synthetic 4-cent spread on bid-only data; the series carries unadjusted "
                    "contract-roll jumps (e.g. +30 % at the 2020-04-19 reopen)")
            spr = _spread_bp(path)
            usable = "no: data unfit (bid-only, synthetic ask, roll jumps) and no FP cost"
        else:
            path = os.path.join(LAB, "data", "fp", f"{s}_m1.parquet")
            idx = _ts(path)
            spr = _spread_bp(path)
            if s in FP_SPEC:
                sp = FP_SPEC[s]
                src = f"lab/data/fp/{s}_m1.parquet (Dukascopy mids, FP Raw-account spread model)"
                cost = (f"r2/fp_costs.json: spread {sp['spread']} at {sp.get('spread_ref_price', 'last-60-day price')}, "
                        f"slip stop {sp['slip_stop_bps']} / market {sp['slip_mkt_bps']} bp, swap long {sp['swap_long']} "
                        f"short {sp['swap_short']}")
                usable = "yes (FP model)"
            else:
                src = f"lab/data/fp/{s}_m1.parquet (Dukascopy share-CFD bid/ask + 0.02 USD/share/side, split-adjusted, 09:30-16:00 NY only)"
                cost = ("provisional stocks model (r2/fp_costs.json _stocks; stocks track): quotes + 0.02 USD/share/side, "
                        "slip 2 / 1 bp, swap 7 % / 3 %; FP minimum commission 2 USD/side not in the frames")
                usable = "yes (provisional model; intraday rules only)"
        years = sorted(set(idx.year))
        cnt = pd.Series(idx.year).value_counts().sort_index()
        rows.append({"instrument": s, "source": src, "is_first_bar": str(idx[0]), "is_last_bar": str(idx[-1]),
                     "is_rows": int(len(idx)), "is_years": f"{years[0]}-{years[-1]}",
                     "rows_by_year": ";".join(f"{int(k)}:{int(v)}" for k, v in cnt.items()),
                     "median_spread_bp_2019_2021": spr, "cost_model": cost, "usable_here": usable})
        print(s, rows[-1]["is_years"], rows[-1]["is_rows"], spr, flush=True)
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------------------------ 2. what was tried
FROZEN = {
    "noise30": {"rule": "noise", "lookback": 14, "first_min": 600, "step": 30, "last_min": 930, "exit_min": 955, "vm": 1.0},
    "ocm4": {"rule": "ocm", "n": 4, "stop": "atr", "k": 0.3, "exit_min": 955, "size_min": 1.0, "size_win": 20,
             "atr_n": 14, "sides": "both"},
    "brk72_24h_wd": {"family": "brk", "n": 72, "stop_atr": 3.0, "hold_h": 24, "dow": "weekday"},
    "nq_btc_follow": {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6,
                      "hold": 60, "stop": 2.0},
    "F1_brk_ridge_filter": {"stop_k": 2.0, "hold_h": 13.0, "model": "B1_ridge_full.json", "q": "0.5"},
    "donch4h_stop": {"family": "donchian", "tf": "4h", "n": 60, "entry": "stop", "stop_atr": 2.0, "trail_atr": 2.0,
                     "max_days": 5, "atr_n": 14},
    "orb_asia_2d_buf10": {"tz": "LDN", "range_start": "00:00", "range_end": "07:00", "entry_end": "12:00",
                          "buf_frac": 0.1, "stop_mode": "opp", "exit_time": "16:00", "hold_days": 2},
    "GOLD_FRI_PM": {"tz": "NY", "entry": "13:30", "exit": "16:45", "weekdays": [4], "side": 1, "stop_atr": 3.0,
                    "atr_n": 14, "atr_tf": "1h", "entry_type": "limit", "limit_min": 60},
}


def _eq(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return abs(float(a) - float(b)) < 1e-9
    if isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)):
        return list(a) == list(b)
    return a == b


def scan_trials():
    found = {}
    for f in sorted(glob.glob(os.path.join(LAB, "results", "**", "trials*.jsonl"), recursive=True)):
        rel = os.path.relpath(f, LAB)
        if "/autopsy/" in rel or "trials_detail" in rel or "trials_full" in rel or "r2_format" in rel:
            continue
        for ln in open(f):
            try:
                d = json.loads(ln)
            except ValueError:
                continue
            p = d.get("params") or d.get("config") or {}
            if not isinstance(p, dict):
                continue
            sym = d.get("sym") or p.get("sym") or ("xauusd" if rel.startswith("results/trend") or rel.startswith("results/orb") else "?")
            for name, fz in FROZEN.items():
                if not all(k in p and _eq(p[k], v) for k, v in fz.items()):
                    continue
                if name == "F1_brk_ridge_filter" and p.get("oof") is not True and sym in ("us100", "ger40", "xauusd"):
                    continue
                if "shape_variant" in p or "sleeve" in p:            # exit variants of the sleeves (track shape)
                    continue
                if any(k in p for k in ("entry_delay_min", "delay", "hs_atr")) and p.get("oof") is not True:
                    continue
                isr = d.get("is", {}) if isinstance(d.get("is"), dict) else {}
                key = (name, sym)
                prev = found.get(key)
                if prev is None or (len(json.dumps(p)) < prev["_plen"]):
                    found[key] = {"_plen": len(json.dumps(p)), "source": rel, "n": isr.get("n"), "pf": isr.get("pf"),
                                  "t": isr.get("t_stat"), "exp_R": isr.get("expectancy_R"), "years_pos": isr.get("years_pos"),
                                  "extra_params": {k: v for k, v in p.items() if k not in fz}}
    return found


# records written in other formats (read by hand from the files cited)
MANUAL = {
    ("donch4h_stop", "xagusd"): {"source": "results/r2/gold2/trials.jsonl (label A0_ref_legacy_donch4h_stop, stage A-confirmatory-silver)",
                                 "n": 514, "pf": 1.14, "t": 1.08, "years_pos": "5/9", "costs": "FP"},
    ("orb_asia_2d_buf10", "xagusd"): {"source": "results/r2/gold2/trials.jsonl (label A5_orb_asia_2d_buf10, silver)",
                                      "n": 1012, "pf": 0.897, "t": -1.23, "years_pos": "3/9", "costs": "FP"},
    ("donch4h_stop", "ger40"): {"source": "results/audit/crossmarket__trend__donch4h_stop.json (round-1 audit on deuidxeur, round-1 costs; its 2022-2025 result was also printed: PF 1.145)",
                                "n": 448, "pf": 1.148, "t": 1.08, "years_pos": "6/9", "costs": "round 1 (bid-only DAX, fixed 1.5 pt)"},
    ("donch4h_stop", "wti"): {"source": "results/audit/crossmarket__trend__donch4h_stop.json (round-1 audit; validation 2022-2025 already read: PF 0.599, 0/4 years)",
                              "n": 513, "pf": 1.343, "t": 2.47, "years_pos": "7/9", "costs": "round 1 (bid-only WTI, fixed 4 c)",
                              "val_pf": 0.599},
    ("donch4h_stop", "eurusd@r1"): {"source": "results/audit/crossmarket__trend__donch4h_stop.json (round 1)", "n": 512, "pf": 0.982, "t": -0.15},
    ("noise30", "jp225@tokyo"): {"source": "results/panel/panel_2026-11-11.json (reviewer replica, NOT the lab engine, Tokyo clock 09:00-15:00 JST)",
                                 "n": 785, "gross_bp": 2.88, "note": "net t 0.8-1.2 at 1.6 bp; noise leg dropped"},
    ("ocm4", "jp225@tokyo"): {"source": "results/panel/panel_2026-11-11.json (reviewer replica, Tokyo clock)",
                              "n": 577, "gross_bp": 7.63, "note": "2020 and 2021 gross +2.5 / +0.8 bp (at or below cost); rank 5, awaiting the FP spread"},
}


def classify(found):
    """Status of every rule x instrument pair."""
    sleeve = {(n, s) for n, s in C.SLEEVES}
    rows = []
    for rule in C.RULES:
        for s in INSTR:
            key = (rule, s)
            rec = found.get(key) or MANUAL.get(key)
            st, why, ev = None, "", {}
            if key in sleeve:
                st = "sleeve (validated)"
                ev = rec or {}
            elif rec is not None:
                ev = rec
                pf = rec.get("pf")
                if key == ("donch4h_stop", "wti"):
                    st, why = "tried: passed in sample, FAILED validation", "round-1 audit: IS PF 1.343 t 2.47, validation PF 0.599 (0/4 years)"
                elif key == ("donch4h_stop", "ger40"):
                    st, why = "tried and failed", "round-1 audit: IS PF 1.148, t 1.08 (bar t >= 2.0 / PF >= 1.2); validation also printed"
                elif s in C.STOCKS and rule in ("noise30", "ocm4"):
                    st, why = "tried and failed", f"stocks track (frozen transfer): PF {pf}, t {rec.get('t')}; basket net PF 0.68-0.73"
                elif rule == "F1_brk_ridge_filter":
                    st, why = "tried and failed", f"ml track, walk-forward out-of-fold: PF {pf}, t {rec.get('t')}"
                else:
                    st, why = "tried and failed", f"PF {pf}, t {rec.get('t')}, years {rec.get('years_pos')}"
            rows.append({"rule": rule, "instrument": s, "status": st, "evidence": why,
                         "source": ev.get("source", ""), "n": ev.get("n"), "pf": ev.get("pf"), "t": ev.get("t"),
                         "years_pos": ev.get("years_pos")})
    df = pd.DataFrame(rows)
    return df


# Structural / scope reasons for the never-tried pairs, fixed before any new simulation.
def scope(df, instr_df):
    usable = dict(zip(instr_df.instrument, instr_df.usable_here))
    reasons = []
    for r in df.itertuples():
        if isinstance(r.status, str):
            reasons.append((r.status, r.evidence))
            continue
        rule, s = r.rule, r.instrument
        why = None
        if s == "wti":
            why = ("OUT: no FP cost model and the only M1 file is bid-only with a synthetic 4-cent ask and unadjusted contract-"
                   "roll jumps (e.g. +30 % at the 2020-04-19 reopen); a frozen rule would trade the roll gaps")
        elif rule == "nq_btc_follow" and s == "us100":
            why = "OUT: degenerate (the follower would be its own leader)"
        elif rule == "GOLD_FRI_PM" and s in ("us100", "us500", "us30", "ger40", "jp225"):
            why = ("OUT (structural): the rule exits at 16:45 New York and drops a Friday with no quote within 10 minutes after "
                   "16:45; these index frames stop at 16:14-16:15 New York (ger40: 108 bars in Friday 16:45-16:55 over 2019-2021, "
                   "us indices and jp225: 0), so the frozen rule takes no trade")
        elif rule == "GOLD_FRI_PM" and s in C.STOCKS:
            why = "OUT (structural): share frames stop at 16:00 New York, the 16:45 exit never has a quote, no trade"
        elif rule == "orb_asia_2d_buf10" and s in C.STOCKS:
            why = "OUT (structural): share frames hold 09:30-16:00 New York only, no bar in the 00:00-07:00 London range"
        elif rule in ("donch4h_stop", "brk72_24h_wd") and s in C.STOCKS:
            why = ("OUT: the rule holds positions overnight (up to 5 days / 24 h); PROTOCOL_V3 section 5 forbids overnight share "
                   "holds in this lab (dividends and share-CFD financing are not in the cost model)")
        elif rule == "F1_brk_ridge_filter" and s in C.STOCKS:
            why = ("OUT: the frozen rule is defined on 14 session bars a day (02:00-15:00 New York); a share has 7 (09:30-16:00), "
                   "so n=14 and vol_n=70 would mean 2 and 10 sessions instead of 1 and 5: in effect new parameters")
        elif rule in ("noise30", "ocm4") and s == "jp225@tokyo":
            why = "OUT: needs a new clock"
        if why is None:
            why = f"IN: never tried; frozen rule runs unchanged on its own clock; cost: {usable.get(s)}"
            reasons.append(("never tried -> PART 2", why))
        else:
            reasons.append(("never tried, out of this lens", why))
    df = df.copy()
    df["status"] = [a for a, _ in reasons]
    df["evidence"] = [b for _, b in reasons]
    return df


def main():
    inst = instruments()
    inst.to_csv(os.path.join(C.RES, "inventory_instruments.csv"), index=False)
    found = scan_trials()
    tab = classify(found)
    tab = scope(tab, inst)
    tab.to_csv(os.path.join(C.RES, "inventory_pairs.csv"), index=False)
    cnt = tab.groupby("status").size().to_dict()
    by_rule = {rule: tab[tab.rule == rule].groupby("status").size().to_dict() for rule in C.RULES}
    other = {f"{k[0]}|{k[1]}": v for k, v in MANUAL.items() if "@" in k[1]}
    scanned = {f"{k[0]}|{k[1]}": {kk: vv for kk, vv in v.items() if kk != "_plen"} for k, v in found.items()}
    C.jdump({"counts": cnt, "by_rule": by_rule, "scanned_records": scanned, "other_records": other},
            os.path.join(C.RES, "inventory.json"))
    print(json.dumps(cnt, indent=1))
    for rule in C.RULES:
        print(rule, by_rule[rule])


if __name__ == "__main__":
    main()
