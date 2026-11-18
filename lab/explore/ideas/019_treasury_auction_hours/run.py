"""Idea 019: US Treasury long auctions on USDJPY (PRE long T-5h..T-1h, POST short T+1h..16:00 NY), in sample.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/019_treasury_auction_hours/run.py
Reads declared.json (never writes it). Data: ~/explore_data/idea_019/auctions_2012_2021.csv (fetch_auctions.py)."""
import json, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data
from kit.data import NY

FOLDER = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(os.path.expanduser("~"), "explore_data", "idea_019", "auctions_2012_2021.csv")
H = pd.Timedelta(hours=1)


def calendar():
    """Kept auctions, indexed by the time the calendar row is KNOWN (announcement day + 1 day, 00:00 New York)."""
    a = pd.read_csv(CSV)
    a = a[pd.to_datetime(a.auction_date) <= pd.Timestamp("2021-12-31")]          # cut in the read
    yrs = a.security_term.str.extract(r"^(\d+)-Year")[0].astype(float)
    a = a[(a.inflation_index_security == "No") & (a.floating_rate == "No") & (yrs >= 6) & (a.offering_amt >= 1e9)
          & (pd.to_datetime(a.auction_date) >= pd.Timestamp("2013-01-01"))].copy()
    assert a.auction_date.is_unique, "two long auctions on one day"
    hhmm = pd.to_datetime(a.closing_time_comp, format="%I:%M %p")
    loc = pd.to_datetime(a.auction_date) + pd.to_timedelta(hhmm.dt.hour, "h") + pd.to_timedelta(hhmm.dt.minute, "m")
    T = pd.DatetimeIndex(loc).tz_localize(NY).tz_convert("UTC")
    known = data.known_at(a.announcemt_date, lag_days=1, time="00:00", tz=NY)
    ann = pd.DatetimeIndex(pd.to_datetime(a.announcemt_date)).tz_localize("UTC")
    assert ((known - ann) >= pd.Timedelta(days=1)).all(), "publication lag below the declared 1 day"
    cal = pd.DataFrame({"T_ns": T.as_unit("ns").asi8, "term": a.security_term.to_numpy(),
                        "close": a.closing_time_comp.to_numpy()}, index=known).sort_index()
    cal.index.name = "known"
    return cal


def build(d, pre_in_h=-5, post_in_h=1, mirrored=False):
    """WHOLE signal table from the calendar known at known_at: PRE at floor_hour(T + pre_in_h), POST at
    ceil_hour(T + post_in_h). leg column kept for the two exits."""
    cal = d["cal"]
    T = pd.DatetimeIndex(cal.T_ns.to_numpy().astype("datetime64[ns]")).tz_localize("UTC")
    pre = (T + pre_in_h * H).floor("h")
    post = (T + post_in_h * H).ceil("h")
    s = -1 if mirrored else 1
    kn = pd.DatetimeIndex(cal.index)
    assert (pre > kn).all() and (post > kn).all(), "a signal before its calendar row is known"
    out = pd.concat([pd.DataFrame({"known_at": pre, "side": s, "leg": "PRE"}),
                     pd.DataFrame({"known_at": post, "side": -s, "leg": "POST"})])
    return out.sort_values(["known_at", "leg"]).reset_index(drop=True)


def run_legs(sig, bk, mk, cfg, mode="one"):
    """Simulate PRE and POST with their own exit; one table (legs never overlap). attrs['signals_sha'] = sig's."""
    stop = tuple(cfg["stop"])
    parts, counts = [], {}
    for leg, ex in (("PRE", tuple(cfg["pre_exit"])), ("POST", tuple(cfg["post_exit"]))):
        g = sig[sig.leg == leg][["known_at", "side"]].assign(market=mk)
        t = sim.simulate(g, bk, exit=ex, stop=stop, mode=mode)
        t["leg"] = leg
        counts[leg] = t.attrs["counts"][mk]
        parts.append(t)
    out = pd.concat(parts, ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    out.attrs["counts"] = {mk: {k: counts["PRE"][k] + counts["POST"][k] for k in counts["PRE"]}, "legs": counts}
    out.attrs["signals_sha"] = sim.signals_sha(sig)
    out.attrs["rule"] = {"pre_exit": cfg["pre_exit"], "post_exit": cfg["post_exit"], "stop": cfg["stop"], "mode": mode}
    return out


def brief(t):
    s = stats.summary(t)
    keep = ["n", "PF_gross", "PF", "PF_stress", "mean_R_gross", "mean_R", "mean_R_stress", "mean_gross_bp", "mean_net_bp",
            "t_trade", "t_daily", "years_positive_frac", "by_year_R", "long_n", "long_R", "short_n", "short_R",
            "exit_reasons", "by_market", "hold_tdays_max"]
    return {k: s.get(k) for k in keep if k in s}


def main():
    decl = json.load(open(os.path.join(FOLDER, "declared.json")))
    checks.declared_hash(FOLDER)
    cfgs = {c["id"]: c for c in decl["configurations"]}
    c0 = cfgs["01_main"]
    d = {"cal": calendar()}
    print("calendar rows", len(d["cal"]))
    cuts = ["2014-03-01", "2016-06-01 14:30", "2019-09-09 09:00", "2020-05-12 12:00", "2021-11-01"]
    tr = checks.truncation_test(lambda x: build(x), d, cuts, row_len={"cal": pd.Timedelta(0)})
    assert tr["pass"], tr
    sig = build(d)
    print("main signals", len(sig), sig.leg.value_counts().to_dict())
    bars = {k: data.load_bars(k) for k in ("usdjpy", "xauusd")}
    bk = sim.books(bars)
    main_t = run_legs(sig, bk, "usdjpy", c0)
    every = run_legs(sig, bk, "usdjpy", c0, mode="every")
    neigh = {}
    for cid in [f"0{i}_" for i in range(2, 10)]:
        c = next(v for k, v in cfgs.items() if k.startswith(cid))
        s2 = build(d, c["pre_in_h"], c["post_in_h"])
        neigh[c["id"]] = run_legs(s2, bk, "usdjpy", c)
    # side configurations (not in the neighbours' median)
    sg = build(d, -5, 1, mirrored=True)
    gold = run_legs(sg, bk, "xauusd", cfgs["10_gold_mirrored"])
    basket = pd.concat([main_t, gold], ignore_index=True).sort_values("entry_time").reset_index(drop=True)
    # null per leg, combined per draw
    nl = {}
    for i, (leg, ex) in enumerate((("PRE", tuple(c0["pre_exit"])), ("POST", tuple(c0["post_exit"])))):
        nl[leg] = stats.null_test(main_t[main_t.leg == leg], bk, exit=ex, stop=tuple(c0["stop"]), n_draws=2000, seed=i)
    nP, nQ = int((main_t.leg == "PRE").sum()), int((main_t.leg == "POST").sum())
    means = (nl["PRE"]["means"] * nP + nl["POST"]["means"] * nQ) / (nP + nQ)
    real = float(main_t.R.mean())
    null = {"real_mean_R": real, "percentile": float((means < real).mean() * 100), "n_draws": 2000, "seed": [0, 1],
            "mode": "every, per leg (own exit), combined per draw", "null_mean": float(means.mean()),
            "null_sd": float(means.std(ddof=1)), "means": means,
            "legs": {k: {kk: vv for kk, vv in v.items() if kk != "means"} for k, v in nl.items()}}
    shift = {leg: checks.shift_test(sig[sig.leg == leg][["known_at", "side"]].assign(market="usdjpy"), bk,
                                    exit=tuple(c0["pre_exit"] if leg == "PRE" else c0["post_exit"]), stop=tuple(c0["stop"]))
             for leg in ("PRE", "POST")}
    extra = {"legs_main": {leg: brief(main_t[main_t.leg == leg]) for leg in ("PRE", "POST")},
             "gross_main": {"PF_gross": stats.pf(main_t.R_gross), "mean_R_gross": float(main_t.R_gross.mean()),
                            "mean_gross_bp": float(main_t.gross_bp.mean()), "mean_net_bp": float(main_t.net_bp.mean())},
             "neighbours_legs": {k: {leg: brief(t[t.leg == leg]) for leg in ("PRE", "POST")} for k, t in neigh.items()},
             "side_10_gold_mirrored": {"all": brief(gold), **{leg: brief(gold[gold.leg == leg]) for leg in ("PRE", "POST")}},
             "side_11_basket_usdjpy_gold": brief(basket),
             "shift_test": shift, "truncation": {k: v for k, v in tr.items() if k != "cuts"},
             "every_signal_legs": {leg: brief(every[every.leg == leg]) for leg in ("PRE", "POST")}}
    res = judge.verdict(FOLDER, main_t, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="fiscaldata auction calendar 2013-2021 (9 years, 344 long auctions); H1 BID USDJPY",
                        extra=extra)
    with open(os.path.join(FOLDER, "trials.jsonl"), "a") as f:
        for cid, t, bas in (("10_gold_mirrored", gold, False), ("11_basket_usdjpy_gold", basket, True)):
            s = stats.summary(t)
            f.write(json.dumps({"id": cid, "role": "side configuration", "n": s["n"], "PF": s["PF"],
                                "t": s["t_daily"] if bas else s["t_trade"], "PF_stress": s["PF_stress"],
                                "mean_R": s["mean_R"], "declared_sha256": res["declared_sha256"],
                                "time": res["written_utc"]}) + "\n")
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    print(json.dumps({k: v["value"] for k, v in res["bars"].items()}, default=str, indent=0))
    print(json.dumps(extra["legs_main"], default=str))
    print("gross", extra["gross_main"])
    print("neighbours", res["neighbours"])
    print("gold", {k: extra["side_10_gold_mirrored"]["all"][k] for k in ("n", "PF_gross", "PF", "t_trade")},
          "basket", {k: extra["side_11_basket_usdjpy_gold"][k] for k in ("n", "PF_gross", "PF", "t_daily")})
    print("null", {k: v for k, v in null.items() if k != "means"})
    print("shift", shift)
    return res


if __name__ == "__main__":
    main()
