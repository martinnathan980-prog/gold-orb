"""Idea 002, world news tone shock (GDELT): the declared in-sample test, run with the kit.
    PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=lab/explore python3 -B lab/explore/ideas/002_news_tone/run_kit.py
Reads declared.json (never writes it; hash checked first). Tone: daily aggregates built by fetch_gdelt.py into
$GDELT_DIR (default ~/explore_data/idea_002/gdelt, else ~/explore_data/gdelt), cut at 2021-12-31 in the read.
Prices: kit.data.load_bars (prepared hourly BID bars). The old run.py (pre-kit, downloads prices) is not used.

Where the declaration and the kit differ (written in results.json 'extra.differences'):
- PUBLICATION TIME (the largest difference): the declaration assumed the file of day D is published about 06:00 UTC
  on D+1 and entered at the D+1 07:00 UTC bar's open. The files' Last-Modified says 07:00:07-07:00:48 UTC (2015-03 to
  2021), 07:34-14:15 UTC (2014-02 to 2015-02), and a back-processing on 15-16 Feb 2014 for 2013-04..2014-01. The 07:00
  entry is a look-ahead of seconds to hours on every day. The JUDGED main and neighbours enter at the first bar at or
  after D+1 08:00 UTC (D >= 2015-03-01) or D+1 15:00 UTC (before); the rule as written (07:00) is reported in
  extra.as_written_07utc, not judged. Values of 2013-04..2014-01 are back-processed (not as first published).
- The declaration has NO stop (time exit only; R = price change / D20). The kit needs a stop: ("d20", 50), which no
  trade can reach in 1-5 days (checked: exit reasons are reported), so the trades are the declared time exits.
  The kit's R is then net result / (50 x D20): a constant 1/50 of the declared R for every leg, so PF, t, years,
  shares, the null percentile, the correlation and the DSR are unchanged by the scale.
- D20: kit = 20 completed 17:00-New-York trading days; declaration = 20 completed UTC days.
- Exit: kit ("bdays", 3) = entry + pandas BDay(3) as declared, but when that time falls where no bar exists the kit
  exits at the close of the bar before (declaration: open of the first bar at or after).
- Costs: kit.costs (FP Raw; usdjpy spread in bp per the lead's ruling, not absolute; swaps at the 17:00 NY rollover).
- Null: the DECLARED one is judged (2000 draws of the same number of random signal days drawn without replacement
  among the days with a valid z of the main configuration, the four legs entered at D+1 07:00 UTC like real signals, same
  hold and overlap rule, simulated with kit.sim, pooled net mean R; percentile = share of draws strictly below the real
  mean). The kit's null (same market, side and New York clock time, independent random day per trade, every draw taken)
  is reported in extra.
- Bars: the judge applies the small-basket amendment (no market above 50 % of the profit with 4 markets) and the DSR
  as a label; the declaration wrote 25 % and DSR >= 0.95 (both reported here as extra)."""
import glob, json, math, os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import numpy as np, pandas as pd
from kit import checks, judge, sim, stats, data

HERE = os.path.dirname(os.path.abspath(__file__))
LEGS = [("xauusd", +1), ("usdjpy", -1), ("us500", -1), ("ger40", -1)]
DECL_H, DECL_LAG = 31, pd.Timedelta(hours=30)   # as declared: published ~06:00 UTC D+1, entry at D+1 07:00 UTC
# LAG NOTE (found in this run, before any return was computed): the HTTP Last-Modified of the daily files says the file
# of day D is written at D+1 07:00:07-07:00:48 UTC from 2015-03 to 2021 (sampled twice a month), at 07:34-14:15 UTC
# from 2014-02 to 2015-01, and the files 2013-04..2014-01 were all (re)written on 15-16 Feb 2014 (back-processed).
# The declared entry (open of the D+1 07:00 UTC bar) is therefore BEFORE the file exists on every day. JUDGED rule =
# the declared rule with the nearest entry that does not leak: known at D+1 08:00 UTC (entry at the 08:00 bar) for
# D >= 2015-03-01, and at D+1 15:00 UTC (entry at the 15:00 bar) before (latest sampled write 14:15 UTC).
HONEST_SWITCH = pd.Timestamp("2015-03-01")
KNOWN_MODE = "decl"          # set by evaluate(): "decl" (D+31 h, as written) or "honest"
MIN_LAG = DECL_LAG


def koff(obs):
    """Known-at offset from the observation date (naive midnight dates) under KNOWN_MODE."""
    obs = pd.DatetimeIndex(obs)
    if KNOWN_MODE == "decl":
        return pd.TimedeltaIndex(np.full(len(obs), DECL_H * 3600, "int64") * 10**9)
    h = np.where(obs >= HONEST_SWITCH, 32, 39)
    return pd.TimedeltaIndex(h.astype("int64") * 3600 * 10**9)
STOP = ("d20", 50)           # no stop in the declaration: a stop no 1-5 day trade can reach (see docstring)


def gdelt_dir():
    for d in (os.environ.get("GDELT_DIR"), "~/explore_data/idea_002/gdelt", "~/explore_data/gdelt"):
        if d and len(glob.glob(os.path.join(os.path.expanduser(d), "*.json"))) > 3000:
            return os.path.expanduser(d)
    raise SystemExit("GDELT daily aggregates missing: run fetch_gdelt.py first")


def tone_series():
    rows, missing = {}, []
    for f in sorted(glob.glob(os.path.join(gdelt_dir(), "*.json"))):
        d = pd.Timestamp(os.path.basename(f)[:8])
        if d >= pd.Timestamp("2022-01-01"):          # cut in the read
            continue
        j = json.load(open(f))
        if j.get("missing") or not j.get("n") or not j.get("mentions"):
            missing.append(str(d.date()))
            continue
        rows[d] = (j["tone_msum"] / j["mentions"], j["tone_sum"] / j["n"])
    t = pd.DataFrame(rows, index=["w", "u"]).T.sort_index()
    known = lambda obs: pd.DatetimeIndex(obs) + koff(obs)  # noqa: E731
    w = data.external(t.index, t.w.to_numpy(), known=known, min_lag=MIN_LAG, name="tone_w")
    u = data.external(t.index, t.u.to_numpy(), known=known, min_lag=MIN_LAG, name="tone_u")
    return {"tone_w": w, "tone_u": u}, missing, len(t)


def zser(s, window, minp):
    """z_D on calendar days D (naive dates): tone of D against the `window` previous calendar days D-window..D-1."""
    obs = (pd.DatetimeIndex(s.index) - pd.Timedelta(hours=31)).tz_localize(None).normalize()   # offsets 31-39 h
    x = pd.Series(s.to_numpy(), index=obs)
    x = x.reindex(pd.date_range(obs[0], obs[-1], freq="D"))
    past = x.shift(1).rolling(window, min_periods=minp)       # D-window .. D-1 calendar days
    return (x - past.mean()) / past.std()


def declared_null(tone, bk, exit, real_mean, n_days, n_draws=2000, seed=0):
    """The declared random-entry null: n_days random signal days (eligible = valid z of the main), same legs, entry,
    hold and overlap rule (kit.sim, mode 'one'), pooled net mean R of each draw."""
    z = zser(tone["tone_w"], 60, 50)
    elig = z.index[np.isfinite(z.to_numpy())]
    rng = np.random.default_rng(seed)
    means = np.empty(n_draws)
    for i in range(n_draws):
        days = pd.DatetimeIndex(np.sort(rng.choice(elig.to_numpy(), n_days, replace=False)))
        ka = (days + koff(days)).tz_localize("UTC")
        sg = pd.concat([pd.DataFrame({"known_at": ka, "side": sd, "market": mk}) for mk, sd in LEGS], ignore_index=True)
        means[i] = sim.simulate(sg, bk, exit=exit, stop=STOP, mode="one").R.mean()
    return {"percentile": float((means < real_mean).mean() * 100), "n_draws": int(n_draws), "real_mean_R": real_mean,
            "null_mean": float(means.mean()), "null_p975": float(np.percentile(means, 97.5)),
            "eligible_days": int(len(elig)), "kind": "declared: random signal days, same legs/hold/overlap"}


def make_build(z_thr=-2.0, window=60, tone="tone_w"):
    minp = int(math.ceil(window * 50 / 60))           # declared: >= 50 valid days of 60 (scaled for 30 / 120)

    def build(d):
        s = d[tone]
        if len(s) == 0:
            return pd.DataFrame({"known_at": pd.DatetimeIndex([], tz="UTC"), "side": [], "market": []})
        z = zser(s, window, minp)
        days = z.index[(z <= z_thr).to_numpy()]
        ka = (days + koff(days)).tz_localize("UTC")
        parts = [pd.DataFrame({"known_at": ka, "side": sd, "market": mk}) for mk, sd in LEGS]
        return pd.concat(parts, ignore_index=True).sort_values(["known_at", "market"]).reset_index(drop=True)
    return build


def cfg_of(c):
    tone = "tone_u" if "unweighted" in c["tone"] or "plain" in c["tone"] else "tone_w"
    return dict(z_thr=float(c["z"]), window=int(c["window"]), tone=tone), ("bdays", int(c["hold_bdays"]))


def split(t):
    out = {}
    for mk, g in t.groupby("market"):
        out[mk] = {"n": int(len(g)), "side": int(g.side.iloc[0]), "PF_gross": stats.pf(g.R_gross), "PF": stats.pf(g.R),
                   "PF_stress": stats.pf(g.R_stress), "sum_R_gross_x50": float(g.R_gross.sum() * 50),
                   "sum_R_x50": float(g.R.sum() * 50), "mean_gross_bp": float(g.gross_bp.mean()),
                   "mean_net_bp": float(g.net_bp.mean())}
    return out


def evaluate(mode, min_lag, cfgs):
    """Everything for one known-at rule: signals, truncation, main, neighbours, every, nulls, shift."""
    global KNOWN_MODE, MIN_LAG
    KNOWN_MODE, MIN_LAG = mode, min_lag
    tone, missing, ndays = tone_series()
    kw0, exit0 = cfg_of(cfgs[0])
    build = make_build(**kw0)
    sig = build(tone)
    n_days_sig = sig.known_at.nunique()
    print(f"[known {mode}] tone days {ndays} (missing {len(missing)}), main signal days {n_days_sig}, rows {len(sig)}")
    tr = checks.truncation_test(build, tone, ["2015-06-01 07:00", "2018-03-15 12:00", "2020-03-20 07:00"],
                                row_len={"tone_w": pd.Timedelta(0), "tone_u": pd.Timedelta(0)})
    assert tr["pass"], tr
    bk = BOOKS
    run = lambda s, ex, mode="one": sim.simulate(s, bk, exit=ex, stop=STOP, mode=mode)  # noqa: E731
    main_t = run(sig, exit0)
    neigh = {}
    for c in cfgs[1:]:
        kw, ex = cfg_of(c)
        neigh[c["id"]] = run(make_build(**kw)(tone), ex)
    every = run(sig, exit0, "every")
    null_kit = stats.null_test(main_t, bk, exit=exit0, stop=STOP, n_draws=2000)
    null = declared_null(tone, bk, exit0, float(main_t.R.mean()), int(n_days_sig))
    shift = checks.shift_test(sig, bk, exit=exit0, stop=STOP)
    return dict(tone=tone, missing=missing, ndays=ndays, sig=sig, n_days_sig=int(n_days_sig), tr=tr, main=main_t,
                neigh=neigh, every=every, null=null, null_kit=null_kit, shift=shift)


def brief(e):
    sm = stats.summary(e["main"])
    return {"n": sm.get("n"), "PF_gross": sm.get("PF_gross"), "PF": sm.get("PF"), "PF_stress": sm.get("PF_stress"),
            "t_daily": sm.get("t_daily"),
            "t_daily_gross": stats.t_stat(stats.daily_sums(e["main"].assign(R=e["main"].R_gross))),
            "years_positive_frac": sm.get("years_positive_frac"), "by_year_R_x50": {k: v * 50 for k, v in sm.get("by_year_R", {}).items()},
            "markets_positive_frac": sm.get("markets_positive_frac"), "by_market": split(e["main"]),
            "neighbours_PF": {k: stats.pf(t.R) for k, t in e["neigh"].items()},
            "neighbours_median_PF": float(np.median([stats.pf(t.R) for t in e["neigh"].values()])),
            "every_mean_R_x50": float(e["every"].R.mean() * 50), "null_declared_pct": e["null"]["percentile"],
            "null_kit_pct": e["null_kit"]["percentile"], "shift": e["shift"], "main_signal_days": e["n_days_sig"]}


BOOKS = None


def main():
    global BOOKS
    decl = json.load(open(os.path.join(HERE, "declared.json")))
    checks.declared_hash(HERE)
    cfgs = decl["configurations"]
    bars = {mk: data.load_bars(mk) for mk, _ in LEGS}
    src = {mk: b.attrs.get("source") for mk, b in bars.items()}
    BOOKS = sim.books(bars)
    as_written = evaluate("decl", DECL_LAG, cfgs)          # the declaration verbatim (entry D+1 07:00 UTC)
    aw = brief(as_written)
    print("AS WRITTEN (07:00 UTC entry, before the file exists on 2016-2021 days):", json.dumps(aw, default=str))
    e = evaluate("honest", pd.Timedelta(hours=32), cfgs)   # judged
    main_t, neigh, every, null, null_kit, shift, tr = (e[k] for k in ("main", "neigh", "every", "null", "null_kit", "shift", "tr"))
    sm = stats.summary(main_t)
    extra = {
        "differences": __doc__.split("Where the declaration and the kit differ")[1].strip(),
        "judged_known_at": "D+1 08:00 UTC for D >= 2015-03-01, D+1 15:00 UTC before (LAG NOTE in run_kit.py)",
        "as_written_07utc": aw,
        "tone_days": e["ndays"], "tone_missing_days": e["missing"], "main_signal_days": e["n_days_sig"],
        "bars_source": src, "stop_used": STOP, "R_scale_note": "kit R = declared R / 50 (R x 50 = net / D20)",
        "main_by_market": split(main_t), "every_by_market": split(every),
        "neighbours_by_market": {k: split(t) for k, t in neigh.items()},
        "main_exit_reasons": sm.get("exit_reasons"),
        "declared_25pct_share_bar": {"max_market_share_of_profit": sm.get("max_market_share_of_profit"),
                                     "pass_25pct": (sm.get("max_market_share_of_profit") or 9) <= 0.25},
        "shift_test_one_bar_later": shift,
        "null_kit": {k: v for k, v in null_kit.items() if k != "means"},
        "gross": {"PF_gross": sm.get("PF_gross"), "mean_R_gross_x50": sm.get("mean_R_gross", 0) * 50,
                  "t_daily_gross": stats.t_stat(stats.daily_sums(main_t.assign(R=main_t.R_gross)))},
    }
    res = judge.verdict(HERE, main_t, neigh, every, null, corr="compute", n_configs=len(cfgs), truncation=tr,
                        data_desc=f"GDELT 1.0 daily events 2013-04..2021-12 ({e['ndays']} days); prepared H1 BID bars",
                        extra=extra)
    print(json.dumps({k: res[k] for k in ("verdict", "failed_bars")}, indent=1))
    print(json.dumps({k: (v["value"], v["pass"]) for k, v in res["bars"].items()}, indent=1, default=str))
    print("main", json.dumps({k: sm.get(k) for k in ("n", "PF_gross", "PF", "PF_stress", "t_trade", "t_daily",
                                                     "years_positive_frac", "by_year_R", "exit_reasons", "long_n",
                                                     "long_R", "short_n", "short_R", "markets_positive_frac",
                                                     "max_market_share_of_profit", "hold_tdays_max")}, default=str))
    print("by market", json.dumps(split(main_t), indent=1))
    print("neighbours", json.dumps(res["neighbours"], default=str))
    print("every", res["every_signal"], "null", res["null"], "null_kit", extra["null_kit"])
    print("shift", shift)
    print("gross", extra["gross"])
    print("selection", json.dumps(res["selection"], default=str)[:700])
    print(res["ledger_line"])


if __name__ == "__main__":
    main()
