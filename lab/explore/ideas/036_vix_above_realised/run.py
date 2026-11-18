"""Idea 036: VIX far above realised volatility -> long us500 for the next cash session (10:00 -> 16:00 New York).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/036_vix_above_realised/run.py
Reads declared.json (never writes it). Order: hash -> truncation -> main, neighbours, every-signal, null -> verdict.
Cache: ~/explore_data/idea_036 (FRED VIXCLS, Yahoo ^GSPC); prepared H1 bars from ~/explore_data/h1."""
import json, os, sys
os.environ.setdefault("EXPLORE_CACHE", os.path.expanduser("~/explore_data/idea_036"))
os.environ.setdefault("EXPLORE_H1_DIR", os.path.expanduser("~/explore_data/h1"))
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
from kit import checks, judge, sim, stats, data  # noqa: E402

NY = "America/New_York"
MK = "us500"
END = pd.Timestamp("2022-01-01", tz="UTC")
START = pd.Timestamp("2013-01-01")
MAX_WAIT_H = 1


def _ny_date(idx):
    """Naive NY calendar date of UTC time stamps (the observation date of a value known at 16:30 NY of that date)."""
    return pd.DatetimeIndex(idx).tz_convert(NY).tz_localize(None).normalize()


def gap_series(d, cfg):
    """x_D (VIX - RV or VIX / RV) indexed by naive observation date D, from values known by 16:30 NY of D."""
    vix = pd.Series(d["vix"].to_numpy(float), index=_ny_date(d["vix"].index))
    if cfg["rv_source"] == "gspc":
        px = pd.Series(d["spx"].to_numpy(float), index=_ny_date(d["spx"].index))
    else:                                                     # close of the us500 bar opening 15:00 NY = 16:00 NY level
        b = d[MK]
        ny = pd.DatetimeIndex(b.index).tz_convert(NY)
        sel = (ny.hour == 15) & (ny.minute == 0) & (ny.dayofweek < 5)
        px = pd.Series(b.close.to_numpy(float)[sel], index=ny[sel].tz_localize(None).normalize())
    px = px[~px.index.duplicated(keep="last")].sort_index()
    rv = np.log(px).diff().rolling(int(cfg["rv_days"])).std() * np.sqrt(252) * 100
    both = vix.index.intersection(rv.dropna().index)
    v, r = vix.reindex(both), rv.reindex(both)
    x = (v / r) if cfg["gap"].startswith("ratio") else (v - r)
    return x.dropna()


def make_build(cfg, holidays):
    hol = set(pd.DatetimeIndex(holidays))
    hh, mm = (int(z) for z in cfg["entry_ny"].split(":"))

    def build(d):
        x = gap_series(d, cfg)
        thr = x.shift(1).rolling(int(cfg["window"])).quantile(float(cfg["pct"]))
        days = x.index[(x > thr).to_numpy() & thr.notna().to_numpy() & (x.index >= START)]
        rows = []
        for D in days:
            n = D + pd.offsets.BDay(1)
            while n in hol:
                n = n + pd.offsets.BDay(1)
            ka = (n + pd.Timedelta(hours=hh, minutes=mm)).tz_localize(NY).tz_convert("UTC")
            if ka < END:
                rows.append(ka)
        sig = pd.DataFrame({"known_at": pd.DatetimeIndex(rows, tz="UTC") if rows else pd.DatetimeIndex([], tz="UTC"),
                            "side": 1})
        return sig.sort_values("known_at").reset_index(drop=True)
    return build


def run_cfg(sig, bk, cfg, mode="one"):
    return sim.simulate(sig.assign(market=MK), bk, exit=tuple(cfg["exit"]), stop=tuple(cfg["stop"]), mode=mode,
                        max_wait_h=MAX_WAIT_H)


def summ(t):
    if len(t) == 0:
        return {"n": 0}
    return {"n": int(len(t)), "PF_gross": stats.pf(t.R_gross), "PF": stats.pf(t.R), "PF_stress": stats.pf(t.R_stress),
            "mean_R_gross": float(t.R_gross.mean()), "mean_R": float(t.R.mean()), "t_gross": stats.t_stat(t.R_gross),
            "t": stats.t_stat(t.R), "mean_gross_bp": float(t.gross_bp.mean()), "mean_net_bp": float(t.net_bp.mean()),
            "stops": int(t.reason.astype(str).str.startswith("stop").sum()),
            "by_year_R": {int(k): round(float(v), 2) for k, v in stats.by_year(t).items()},
            "by_year_R_gross": {int(k): round(float(v), 2) for k, v in t.groupby(pd.DatetimeIndex(t.entry_time).year).R_gross.sum().items()}}


def main_():
    decl = json.load(open(os.path.join(HERE, "declared.json")))
    checks.declared_hash(HERE)
    cfgs = decl["configurations"]
    vix = data.fred("VIXCLS", known=data.rule_local_close("16:30"))
    spx = data.yahoo_daily("^GSPC", known=data.rule_local_close("16:30"))
    bars = data.load_bars(MK)
    print("bars source:", bars.attrs.get("source"), len(bars), bars.index[0], bars.index[-1])
    # NYSE closures 2013-2021 (calendar knowledge, published ahead): weekdays without an S&P 500 close
    wd = pd.bdate_range("2013-01-01", "2021-12-31")
    holidays = wd.difference(_ny_date(spx.index))
    print("NYSE closures 2013-2021:", len(holidays))
    d = {"vix": vix, "spx": spx, MK: bars}
    row_len = {"vix": pd.Timedelta(0), "spx": pd.Timedelta(0), MK: pd.Timedelta(hours=1)}
    b_main = make_build(cfgs[0], holidays)
    tr = checks.truncation_test(b_main, d, ["2015-06-01 14:30", "2018-02-06 15:00", "2020-03-16 13:00"], row_len=row_len)
    assert tr["pass"], tr
    sig_main = b_main(d)
    print("main signals:", len(sig_main))
    bk = sim.books({MK: bars})
    results, sigs = {}, {}
    for c in cfgs:
        s = sig_main if c["id"] == cfgs[0]["id"] else make_build(c, holidays)(d)
        sigs[c["id"]] = s
        results[c["id"]] = run_cfg(s, bk, c)
    main = results.pop(cfgs[0]["id"])
    every = run_cfg(sig_main, bk, cfgs[0], mode="every")
    null = stats.null_test(main, bk, exit=tuple(cfgs[0]["exit"]), stop=tuple(cfgs[0]["stop"]), n_draws=2000)
    shift = checks.shift_test(sig_main.assign(market=MK), bk, exit=tuple(cfgs[0]["exit"]), stop=tuple(cfgs[0]["stop"]))
    main.to_csv(os.path.expanduser("~/explore_data/idea_036/main_trades.csv"), index=False)
    extra = {"main": summ(main), "neighbours_detail": {k: summ(t) for k, t in results.items()},
             "every_signal": summ(every), "counts_main": main.attrs.get("counts"),
             "signals_per_config": {k: int(len(s)) for k, s in sigs.items()},
             "null_summary": {k: null[k] for k in ("real_mean_R", "percentile", "null_mean", "null_sd") if k in null},
             "shift_test": shift, "sides": "long only by construction",
             "truncation": {k: v for k, v in tr.items() if k != "cuts"}}
    res = judge.verdict(HERE, main, results, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="FRED VIXCLS + Yahoo ^GSPC closes (known 16:30 NY); prepared H1 BID us500 bars 2013-2021",
                        extra=extra)
    print(res["verdict"], res["failed_bars"])
    print(res["ledger_line"])
    for k, v in res["bars"].items():
        print(f"  {k}: {v.get('value')} {'ok' if v.get('pass') else 'FAIL'}")
    print(json.dumps(extra["main"], default=str))
    for k, v in extra["neighbours_detail"].items():
        print(k, {z: (round(w, 3) if isinstance(w, float) else w) for z, w in v.items() if not z.startswith("by_year")})
    print("every:", {z: w for z, w in extra["every_signal"].items() if not z.startswith("by_year")})
    print("null:", extra["null_summary"], "shift:", shift)
    return res


if __name__ == "__main__":
    main_()
