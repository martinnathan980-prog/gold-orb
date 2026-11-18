"""Idea 020: gold ETF (GLD + IAU) off-exchange short-volume share -> next-session gold trade (in sample only).
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/020_gold_etf_short_volume/run.py
Reads declared.json (never writes it). Signal data: ~/explore_data/idea_020/raw_rows (fetch_finra.py)."""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..")))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data
import finra_series as F

NY = "America/New_York"

def share_series():
    g = F.daily_share()
    return data.external(g.index, g.share.to_numpy(), known=data.rule_local_close("18:30"),
                         min_lag=pd.Timedelta(hours=18), name="gld_iau_short_share")

def make_build(window, k):
    def build(d):
        s = d["share"]
        z = F.zscore(pd.Series(s.to_numpy(), index=s.index), window)
        z = z[z.index >= pd.Timestamp("2013-01-01", tz="UTC")]
        side = np.where(z >= k, 1, np.where(z <= -k, -1, 0))
        m = side != 0
        return pd.DataFrame({"known_at": pd.DatetimeIndex(z.index[m]), "side": side[m].astype(int)})
    return build

def side_fig(t):
    out = {}
    for nm, sel in (("long", t.side > 0), ("short", t.side < 0)):
        x = t[sel]
        out[nm] = {"n": int(len(x)), "PF_gross": stats.pf(x.R_gross), "PF_net": stats.pf(x.R),
                   "PF_stress": stats.pf(x.R_stress), "mean_R_gross": float(x.R_gross.mean()) if len(x) else None,
                   "mean_R": float(x.R.mean()) if len(x) else None, "t_net": stats.t_stat(x.R),
                   "mean_gross_bp": float(x.gross_bp.mean()) if len(x) else None}
    return out

def main():
    checks.declared_hash(HERE)
    decl = json.load(open(os.path.join(HERE, "declared.json")))
    cfgs, mk = decl["configurations"], decl["markets"][0]
    bars = data.load_bars(mk)
    print("bars:", bars.attrs.get("source"), bars.index.min(), bars.index.max(), len(bars))
    d = {"bars": bars, "share": share_series()}
    c0 = cfgs[0]
    b0 = make_build(c0["window"], c0["k"])
    tr = checks.truncation_test(b0, d, ["2015-03-02 23:00", "2018-08-15 22:00", "2020-06-01 12:00"],
                                row_len={"bars": pd.Timedelta(hours=1), "share": pd.Timedelta(0)})
    print("truncation pass:", tr["pass"], "n_signals:", tr["n_signals"])
    assert tr["pass"], tr
    bk = sim.books({mk: bars})
    def run(c, mode="one"):
        sig = make_build(c["window"], c["k"])(d).assign(market=mk)
        return sim.simulate(sig, bk, exit=tuple(c["exit"]), stop=tuple(c["stop"]),
                            target=tuple(c["target"]) if c.get("target") else None, mode=mode)
    main_t = run(c0)
    neigh = {c["id"]: run(c) for c in cfgs[1:]}
    every = run(c0, "every")
    null = stats.null_test(main_t, bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]), n_draws=2000)
    shift = checks.shift_test(b0(d).assign(market=mk), bk, exit=tuple(c0["exit"]), stop=tuple(c0["stop"]))
    eh = pd.DatetimeIndex(main_t.entry_time).tz_convert(NY)
    entry_clock = pd.Series([f"{a} {h:02d}" for a, h in zip(eh.day_name().str[:3], eh.hour)]).value_counts().to_dict()
    neigh_fig = {k: {"n": int(len(v)), "PF_gross": stats.pf(v.R_gross), "PF": stats.pf(v.R),
                     "PF_stress": stats.pf(v.R_stress), "t": stats.t_stat(v.R)} for k, v in neigh.items()}
    extra = {"shift_test": shift, "sides": side_fig(main_t), "entry_clock_ny": entry_clock,
             "neighbours_fig": neigh_fig, "counts": main_t.attrs.get("counts"),
             "every_n": int(len(every)), "every_mean_R": float(every.R.mean())}
    res = judge.verdict(HERE, main_t, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc="FINRA GLD+IAU short volume 2012-10..2021; xauusd H1 2013-2021 (9 years)",
                        extra=extra)
    main_t.to_csv(os.path.expanduser("~/explore_data/idea_020/trades_main.csv"), index=False)   # trades stay out of git
    print(json.dumps({"verdict": res["verdict"], "failed": res["failed_bars"]}, indent=1))
    print(json.dumps(extra, indent=1, default=str))
    print(res["ledger_line"])
    return res

if __name__ == "__main__":
    main()
