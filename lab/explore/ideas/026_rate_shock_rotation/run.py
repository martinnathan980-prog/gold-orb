"""Idea 026: rate shock, then rotation. Large 5-day move of the 10-year yield (FRED DGS10, z on its own past sd) ->
long (yields up) or short (yields down) the hedged pair us30/us100 at 10:00 New York of the next business day, exit
2 business days later, stop 1.5 x D20 of the pair.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/026_rate_shock_rotation/run.py
Reads declared.json (never writes it). Order: hash -> truncation -> main, neighbours, every-signal, null -> verdict.
Cache: ~/explore_data/idea_026 (FRED DGS10); prepared H1 bars from ~/explore_data/h1."""
import json, os, sys
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_026"))
os.environ.setdefault("EXPLORE_H1_DIR", os.path.expanduser("~/explore_data/h1"))
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from kit import checks, judge, sim, stats, data  # noqa: E402

NY = "America/New_York"
PAIR = "us30/us100"
END = pd.Timestamp("2022-01-01", tz="UTC")
FIRST_OBS = pd.Timestamp("2013-10-01")
MAX_WAIT_H = 1


def load_yield():
    """DGS10 as a frame indexed by the time each value is KNOWN (obs D + 1 business day 13:00 UTC), with its obs date."""
    y = data.fred("DGS10", known=data.rule_next_bday_utc(13, 1), start="2011-01-01")
    obs = pd.DatetimeIndex(y.attrs["obs_date"]) if "obs_date" in y.attrs else \
        pd.DatetimeIndex(y.index.tz_convert("UTC").tz_localize(None).normalize()) - pd.offsets.BDay(1)
    f = pd.DataFrame({"obs": obs.as_unit("ns"), "v": y.to_numpy(float)}, index=pd.DatetimeIndex(y.index))
    chk = (pd.DatetimeIndex(f.obs) + pd.offsets.BDay(1) + pd.Timedelta(hours=13)).tz_localize("UTC")
    assert (chk == pd.DatetimeIndex(f.index).tz_convert("UTC")).all(), "known-at rule mismatch"
    return f


def make_build(cfg):
    k, w, thr = int(cfg["chg_days"]), int(cfg["sd_window"]), float(cfg["z_thr"])

    def build(d):
        f = d["y"]
        v = pd.Series(f["v"].to_numpy(float))
        chg = v - v.shift(k)                                   # change over k observations, known with the last one
        sd = chg.shift(1).rolling(w).std()                     # past only: the w changes before this observation
        z = (chg / sd).to_numpy()
        obs = pd.DatetimeIndex(f["obs"])
        known = pd.DatetimeIndex(f.index).tz_convert("UTC")
        ok = np.isfinite(z) & (np.abs(z) >= thr) & (obs >= FIRST_OBS)
        # decision: 10:00 New York on the known-at date (= next business day after the observation), after 13:00 UTC
        day = known[ok].tz_localize(None).normalize()
        ka = (day + pd.Timedelta(hours=10)).tz_localize(NY).tz_convert("UTC")
        sig = pd.DataFrame({"known_at": ka, "side": np.where(z[ok] > 0, 1, -1).astype(int)})
        sig = sig[sig.known_at < END]
        return sig.sort_values("known_at").reset_index(drop=True)
    return build


def rule_of(cfg):
    return dict(exit=tuple(cfg["exit"]), stop=tuple(cfg["stop"]))


def run_cfg(sig, bk, cfg, mode="one"):
    return sim.simulate(sig.assign(market=PAIR), bk, mode=mode, max_wait_h=MAX_WAIT_H, **rule_of(cfg))


def summ(t):
    if len(t) == 0:
        return {"n": 0}
    out = {"n": int(len(t)), "PF_gross": stats.pf(t.R_gross), "PF": stats.pf(t.R), "PF_stress": stats.pf(t.R_stress),
           "mean_R_gross": float(t.R_gross.mean()), "mean_R": float(t.R.mean()), "t_gross": stats.t_stat(t.R_gross),
           "t": stats.t_stat(t.R), "mean_gross_bp": float(t.gross_bp.mean()), "mean_net_bp": float(t.net_bp.mean()),
           "stops": int(t.reason.astype(str).str.startswith("stop").sum()),
           "by_year_R": {int(k): round(float(v), 2) for k, v in t.groupby(pd.DatetimeIndex(t.entry_time).year).R.sum().items()},
           "by_year_R_gross": {int(k): round(float(v), 2) for k, v in
                               t.groupby(pd.DatetimeIndex(t.entry_time).year).R_gross.sum().items()}}
    for nm, s in (("long_yields_up", 1), ("short_yields_down", -1)):
        g = t[t.side == s]
        out[nm] = {"n": int(len(g)), "PF_gross": stats.pf(g.R_gross) if len(g) else None,
                   "PF": stats.pf(g.R) if len(g) else None, "mean_R_gross": float(g.R_gross.mean()) if len(g) else None,
                   "mean_R": float(g.R.mean()) if len(g) else None, "t": stats.t_stat(g.R) if len(g) > 2 else None}
    return out


def main_():
    decl = json.load(open(os.path.join(HERE, "declared.json")))
    checks.declared_hash(HERE)
    cfgs = decl["configurations"]
    y = load_yield()
    b30, b100 = data.load_bars("us30"), data.load_bars("us100")
    print("bars:", b30.attrs.get("source"), len(b30), b30.index[0], "|", len(b100), b100.index[0])
    d = {"y": y}
    b_main = make_build(cfgs[0])
    tr = checks.truncation_test(b_main, d, ["2015-06-01 14:30", "2018-02-06 15:00", "2020-03-16 14:00"],
                                row_len={"y": pd.Timedelta(0)})
    assert tr["pass"], {k: v for k, v in tr.items() if k != "cuts"}
    print("truncation:", {k: v for k, v in tr.items() if k not in ("cuts",)})
    sig_main = b_main(d)
    print("main signals:", len(sig_main), "up", int((sig_main.side > 0).sum()), "down", int((sig_main.side < 0).sum()))
    bk = {PAIR: sim.pair_book(PAIR, "us30", "us100", b30, b100, kind="ratio")}
    results, sigs = {}, {}
    for c in cfgs:
        s = sig_main if c["id"] == cfgs[0]["id"] else make_build(c)(d)
        sigs[c["id"]] = s
        results[c["id"]] = run_cfg(s, bk, c)
    main = results.pop(cfgs[0]["id"])
    every = run_cfg(sig_main, bk, cfgs[0], mode="every")
    null = stats.null_test(main, bk, n_draws=2000, **rule_of(cfgs[0]))
    shift = checks.shift_test(sig_main.assign(market=PAIR), bk, **rule_of(cfgs[0]))
    main.to_csv(os.path.expanduser("~/explore_data/idea_026/main_trades.csv"), index=False)
    extra = {"main": summ(main), "neighbours_detail": {k: summ(t) for k, t in results.items()},
             "every_signal": summ(every), "counts_main": main.attrs.get("counts"),
             "signals_per_config": {k: int(len(s)) for k, s in sigs.items()},
             "null_summary": {k: null[k] for k in ("real_mean_R", "percentile", "null_mean", "null_sd") if k in null},
             "shift_test": shift, "truncation": {k: v for k, v in tr.items() if k != "cuts"}}
    res = judge.verdict(HERE, main, results, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="FRED DGS10 (known D+1 bday 13:00 UTC); prepared H1 BID us30, us100 bars 2013-10..2021, "
                                  "pair us30/us100 ratio", extra=extra)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    for k, v in res["bars"].items():
        print(f"  {k}: {v.get('value')} {'ok' if v.get('pass') else 'FAIL'}")
    print(json.dumps(extra["main"], default=str))
    for k, v in extra["neighbours_detail"].items():
        print(k, {z: (round(w, 3) if isinstance(w, float) else w) for z, w in v.items()
                  if not z.startswith("by_year") and not isinstance(w, dict)})
    print("every:", {z: w for z, w in extra["every_signal"].items() if not z.startswith("by_year")})
    print("null:", extra["null_summary"], "shift:", shift)
    return res


if __name__ == "__main__":
    main_()
