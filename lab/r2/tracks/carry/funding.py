"""Funding carry (long spot / short USDT-margined perpetual) on BTC and ETH, 2020-01-01 -> 2026-11-10.

Public data only (not the lab's validation data):
  Binance public archive data.binance.vision (funding rate history, 1h spot and perp klines, 1m mark/last/spot on event days)
  OKX public API funding-rate-history (2026-08-10 -> 2026-11-11; used for 2026-11-01..10 because Binance's monthly archive
  stops at 2026-10, and as a cross-check of Binance on the overlap)
  ECB data API: EUR/USD reference rate, euro short-term rate (EUR STR)

Model (hourly path, per coin, per margin regime, per cost profile):
  capital C split into spot leg q*S and perp margin M; target M = q*F/L (L = 5 offshore, L = 2 EU retail).
  Short receives q*F*rate at every funding time (00, 08, 16 UTC).
  Liquidation / close-out test inside every hour on the perp hourly HIGH (last price, more severe than mark):
    offshore 5x: margin equity < maintenance 0.5 % of notional;
    EU 2:1     : ESMA CFD rule, close-out when margin equity < 50 % of the initial margin (i.e. 25 % of notional).
  Rebalance (both legs resized to the target split of current equity) at an hourly close whenever the perp has moved
  more than BAND from the last rebalance price. If a liquidation happens anyway, the short is closed at the
  liquidation price (margin left = 0 at 5x, = 25 % of notional at 2:1), the spot is sold at the same hour's close and
  the position is re-opened at the close (all trading costs charged) -> the event shows in the daily result.
  Costs: per-leg fee + slippage on every trade (entry, rebalance, liquidation re-entry). Margin earns nothing.
"""
import glob, io, json, os, sys, warnings, zipfile
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

D = os.path.dirname(os.path.abspath(__file__)) + "/data"
if not os.path.isdir(D):
    D = "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/vert/portage/data"
OUT = sys.argv[1] if len(sys.argv) > 1 else os.path.dirname(os.path.abspath(__file__)) + "/carry_results.json"
START, END = pd.Timestamp("2020-01-01", tz="UTC"), pd.Timestamp("2026-11-11", tz="UTC")  # END exclusive
C0 = 1000.0

# ---------- cost profiles (fees in fraction per trade per leg) ----------
COSTS = {
    "zero": dict(spot=0.0, perp=0.0, slip=0.0),
    # offshore retail tier 0 (Binance-like, from memory: spot 0.10 % maker and taker, USDT-M perp 0.02 % maker / 0.05 % taker)
    "offshore_maker": dict(spot=0.0010, perp=0.0002, slip=0.0001),
    "offshore_taker": dict(spot=0.0010, perp=0.0005, slip=0.0002),
    # EU MiFID venue (Kraken Pro lowest tier, from memory: spot 0.25 % maker / 0.40 % taker; futures 0.02 / 0.05 %)
    "eu_maker": dict(spot=0.0025, perp=0.0002, slip=0.0002),
    "eu_taker": dict(spot=0.0040, perp=0.0005, slip=0.0004),
}
REGIMES = {"off5x": dict(L=5.0, liq="mm", mm=0.005), "eu2x": dict(L=2.0, liq="esma", mm=None)}
FX_HEDGE_COST = 6.23 * 365 / 112140.0  # ~2.03 %/yr, see above
BAND = 0.08  # rebalance when perp moved > 8 % since last rebalance (about 40 % of the ~20 % distance to liquidation)


def _read_zip_csv(path, header):
    with zipfile.ZipFile(path) as z:
        raw = z.read(z.namelist()[0]).decode()
    rows = [r for r in raw.splitlines() if r and r[0].isdigit()] if not header else raw.splitlines()[1:]
    return rows


def load_funding(sym):
    rows = []
    for f in sorted(glob.glob(f"{D}/fr/{sym}-*.zip")):
        for r in _read_zip_csv(f, True):
            t, h, v = r.split(",")
            rows.append((int(t), float(v)))
    s = pd.DataFrame(rows, columns=["t", "rate"])
    s["t"] = pd.to_datetime((s.t // 3600000) * 3600000, unit="ms", utc=True)  # calc_time has +1..5 ms jitter
    s = s.groupby("t").rate.last()
    # Nov 2026 from OKX (Binance archive not yet published)
    inst = {"BTCUSDT": "BTC-USDT-SWAP", "ETHUSDT": "ETH-USDT-SWAP"}[sym]
    ok = []
    for f in glob.glob(f"{D}/okx/{inst}-*.json"):
        for r in json.load(open(f))["data"]:
            ok.append((int(r["fundingTime"]), float(r["realizedRate"] or r["fundingRate"])))
    o = pd.DataFrame(ok, columns=["t", "rate"]).drop_duplicates("t")
    o["t"] = pd.to_datetime(o.t, unit="ms", utc=True)
    o = o.set_index("t").rate.sort_index()
    overlap = s.index.intersection(o.index)
    xc = dict(n=len(overlap), corr=float(np.corrcoef(s[overlap], o[overlap])[0, 1]) if len(overlap) > 10 else None,
              binance_mean=float(s[overlap].mean()) if len(overlap) else None, okx_mean=float(o[overlap].mean()) if len(overlap) else None)
    add = o[o.index > s.index.max()]
    return pd.concat([s, add]).sort_index(), xc, str(add.index.min()) if len(add) else None


def load_klines(sym, kind):
    rows = []
    pat = f"{D}/kl_{kind}/{sym}-1h-*.zip"
    files = sorted(glob.glob(pat)) + sorted(glob.glob(f"{D}/daily/{sym}-k{kind[0]}-*.zip"))
    for f in files:
        for r in _read_zip_csv(f, False):
            p = r.split(",")
            t = int(p[0]);
            t = t // 1000 if t > 10 ** 14 else t
            rows.append((t, float(p[1]), float(p[2]), float(p[3]), float(p[4])))
    k = pd.DataFrame(rows, columns=["t", "o", "h", "l", "c"]).drop_duplicates("t")
    k["t"] = pd.to_datetime(k.t, unit="ms", utc=True)
    return k.set_index("t").sort_index()


def build(sym):
    fr, xc, okx_from = load_funding(sym)
    sp, pp, mk = load_klines(sym, "spot"), load_klines(sym, "perp"), load_klines(sym, "mark")
    idx = pd.date_range(START, END - pd.Timedelta("1h"), freq="1h")
    sp, pp, mk = sp.reindex(idx).ffill(), pp.reindex(idx).ffill(), mk.reindex(idx).ffill()
    # trades at the perp last price; liquidation tested on the MARK high (exchanges liquidate on mark, and the last
    # price has bad prints, e.g. ETHUSDT perp +202 % on 2020-03-13 while mark rose 29 %); funding paid on mark open
    df = pd.DataFrame({"S": sp.c, "So": sp.o, "F": pp.c, "Fo": pp.o, "Fh": mk.h, "Fh_last": pp.h, "Mo": mk.o}, index=idx)
    df["rate"] = fr.reindex(idx).fillna(0.0)  # funding settled at the start of hours 00/08/16
    return df, fr[(fr.index >= START) & (fr.index < END)], xc, okx_from


def simulate(df, regime, cost, band=BAND, rebalance=True):
    L = regime["L"]; fee_s = cost["spot"] + cost["slip"]; fee_p = cost["perp"] + cost["slip"]
    S, So, F, Fo, Fh, R, Mo = (df[c].values for c in ["S", "So", "F", "Fo", "Fh", "rate", "Mo"])
    n = len(df); eq = np.empty(n); fund_cum = np.empty(n); cost_cum = np.empty(n)
    E = C0
    # open at first hour's open
    q = E / (So[0] * (1 + fee_s) + Fo[0] * (1 / L + fee_p))
    cash_cost = q * So[0] * fee_s + q * Fo[0] * fee_p
    M = q * Fo[0] / L; Fe = Fo[0]; spot_cash = 0.0; Fref = Fo[0]
    fsum = 0.0; csum = cash_cost; nreb = 0; nliq = 0; liq_times = []
    for i in range(n):
        # funding at the start of the hour, on the perp open price
        if R[i] != 0.0:
            fp = q * Mo[i] * R[i]; M += fp; fsum += fp
        # liquidation test inside the hour (on the perp high)
        Fx = Fh[i]
        meq = M + q * (Fe - Fx)
        thr = regime["mm"] * q * Fx if regime["liq"] == "mm" else 0.5 * (q * Fe / L)  # ESMA: 50 % of initial margin
        if meq < thr:
            nliq += 1; liq_times.append(str(df.index[i]))
            if regime["liq"] == "esma":
                Fl = Fe + (M - thr) / q; left = thr          # closed out, 50 % of the initial margin is returned
            else:
                Fl = (M / q + Fe) / (1 + regime["mm"]); left = 0.0  # liquidated, maintenance margin lost too
            c_liq = q * Fl * fee_p + q * S[i] * fee_s
            E = q * S[i] + spot_cash + left - c_liq
            csum += c_liq
            # re-open at the close
            q_new = E / (S[i] * (1 + fee_s) + F[i] * (1 / L + fee_p))
            c_re = q_new * S[i] * fee_s + q_new * F[i] * fee_p; csum += c_re
            q = q_new; M = q * F[i] / L; Fe = F[i]; spot_cash = 0.0; Fref = F[i]
            eq[i] = q * S[i] + M; fund_cum[i] = fsum; cost_cum[i] = csum
            continue
        E = q * S[i] + spot_cash + M + q * (Fe - F[i])
        if rebalance and abs(F[i] / Fref - 1) > band:
            q_new = E / (S[i] * (1 + 0) + F[i] / L)
            dq = abs(q_new - q)
            c = dq * S[i] * fee_s + dq * F[i] * fee_p
            E -= c; csum += c; nreb += 1
            q = E / (S[i] + F[i] / L)
            M = q * F[i] / L; Fe = F[i]; spot_cash = 0.0; Fref = F[i]
        eq[i] = E; fund_cum[i] = fsum; cost_cum[i] = csum
    out = pd.DataFrame({"eq": eq, "fund": fund_cum, "cost": cost_cum}, index=df.index)
    return out, dict(rebalances=nreb, liquidations=nliq, liq_times=liq_times[:20])


def period_stats(eq_daily, ret_daily):
    """eq_daily: end-of-day equity (UTC days); ret_daily: daily % return on start-of-day equity."""
    d = ret_daily
    w = (1 + d).groupby(d.index.to_period("W-SUN")).prod() - 1
    m = (1 + d).groupby(d.index.to_period("M")).prod() - 1
    g, r = d[d > 0], d[d < 0]
    dd = (eq_daily / eq_daily.cummax() - 1).min()
    return dict(days=int(len(d)), green_days=round(100 * (d > 0).mean(), 1), green_weeks=round(100 * (w > 0).mean(), 1),
                green_months=round(100 * (m > 0).mean(), 1),
                avg_green_day_pct=round(100 * g.mean(), 4) if len(g) else None,
                avg_red_day_pct=round(100 * r.mean(), 4) if len(r) else None,
                red_over_green=round(-r.mean() / g.mean(), 2) if len(g) and len(r) else None,
                worst_day_pct=round(100 * d.min(), 3), worst_week_pct=round(100 * w.min(), 3),
                worst_month_pct=round(100 * m.min(), 3), max_drawdown_pct=round(100 * dd, 3),
                total_pct=round(100 * ((1 + d).prod() - 1), 2),
                annual_pct=round(100 * ((1 + d).prod() ** (365.0 / max(len(d), 1)) - 1), 2))


def daily_series(sim, df, eur=None, view="mtm"):
    if view == "mtm":
        e = sim["eq"].resample("1D").last()
        e0 = pd.concat([pd.Series([C0], index=[e.index[0] - pd.Timedelta("1D")]), e])
        if eur is not None:
            fx = eur.reindex(e0.index).ffill().bfill()
            e0 = e0 / fx
        ret = (e0 / e0.shift(1) - 1).dropna()
        return e0.iloc[1:], ret
    # accrual view: funding received that day minus trading costs that day, on start equity
    f = sim.fund.resample("1D").last().diff().fillna(sim.fund.resample("1D").last().iloc[0])
    c = sim.cost.resample("1D").last().diff().fillna(sim.cost.resample("1D").last().iloc[0])
    e = sim["eq"].resample("1D").last().shift(1).fillna(C0)
    ret = (f - c) / e
    return (1 + ret).cumprod() * C0, ret


def neg_stretch(fr):
    """Longest run of consecutive negative funding prints and longest run of negative daily sums (days)."""
    neg = (fr < 0).values; best = cur = 0; bi = None; start = None
    for i, v in enumerate(neg):
        if v:
            cur += 1
            if cur == 1: start = i
            if cur > best: best, bi = cur, start
        else:
            cur = 0
    dly = fr.resample("1D").sum()
    nd = (dly < 0).values; bd = cd = 0; bdi = None; st = None
    for i, v in enumerate(nd):
        if v:
            cd += 1
            if cd == 1: st = i
            if cd > bd: bd, bdi = cd, st
        else:
            cd = 0
    # longest rolling-30d window with negative sum
    r30 = dly.rolling(30).sum()
    return dict(longest_negative_prints=int(best), from_=str(fr.index[bi]) if bi is not None else None,
                longest_negative_days=int(bd), days_from=str(dly.index[bdi].date()) if bdi is not None else None,
                share_negative_prints_pct=round(100 * (fr < 0).mean(), 1),
                worst_30d_sum_pct=round(100 * r30.min(), 3), worst_30d_end=str(r30.idxmin().date()))


def event_study(sym, day, df):
    """Event day: max perp rise vs the day's 00:00 UTC open (no rebalance within the day), from 1m mark and last
    price; max rise from the open 7 days earlier; worst basis (perp/spot - 1) on 1m closes."""
    out = dict(day=day)
    try:
        def m1(kind):
            f = f"{D}/m1/{sym}-{kind}-{day}.zip"
            if not os.path.exists(f): return None
            rows = [r.split(",") for r in _read_zip_csv(f, False)]
            k = pd.DataFrame([(int(p[0]) // (1000 if int(p[0]) > 10 ** 14 else 1), float(p[1]), float(p[2]), float(p[3]), float(p[4])) for p in rows],
                             columns=["t", "o", "h", "l", "c"])
            k["t"] = pd.to_datetime(k.t, unit="ms", utc=True); return k.set_index("t")
        mk, pe, spt = m1("mark"), m1("perp"), m1("spot")
        o = pe.o.iloc[0]
        out["day_open"] = o; out["day_low_pct"] = round(100 * (pe.l.min() / o - 1), 2)
        out["max_rise_last_pct"] = round(100 * (pe.h.max() / o - 1), 2)
        out["max_rise_mark_pct"] = round(100 * (mk.h.max() / mk.o.iloc[0] - 1), 2) if mk is not None else None
        # largest rebound off the intraday low (what a short opened/rebalanced at the low would suffer)
        lowt = pe.l.idxmin(); out["rebound_from_low_pct"] = round(100 * (pe.h[pe.index >= lowt].max() / pe.l.min() - 1), 2)
        if spt is not None:
            j = pe.c.to_frame("F").join(spt.c.rename("S"), how="inner")
            b = j.F / j.S - 1
            out["basis_min_pct"] = round(100 * b.min(), 3); out["basis_max_pct"] = round(100 * b.max(), 3)
        t0 = pd.Timestamp(day, tz="UTC")
        w = df[(df.index >= t0 - pd.Timedelta("7D")) & (df.index < t0 + pd.Timedelta("1D"))]
        out["max_rise_7d_pct"] = round(100 * (w.Fh.max() / w.Fo.iloc[0] - 1), 2)
        out["funding_that_day_pct"] = round(100 * df.rate[(df.index >= t0) & (df.index < t0 + pd.Timedelta("1D"))].sum(), 4)
    except Exception as e:  # noqa
        out["error"] = repr(e)
    # thresholds: 5x maint 0.5 % -> +19.4 %; ESMA 2:1 -> +20.0 %; 2:1 with whole capital as margin (N=C/2) -> +60 %
    for k, thr in [("liq_5x", 19.40), ("closeout_2to1_min_margin", 20.0), ("closeout_2to1_full_margin", 60.0)]:
        r = out.get("max_rise_mark_pct") or out.get("max_rise_last_pct")
        out[k + "_within_day"] = (r is not None and r >= thr)
        out[k + "_within_7d_no_rebal"] = (out.get("max_rise_7d_pct", 0) >= thr)
    return out


def main():
    eur = pd.read_csv(f"{D}/ecb/eurusd.csv")[["TIME_PERIOD", "OBS_VALUE"]]
    eur = pd.Series(eur.OBS_VALUE.values, index=pd.DatetimeIndex(pd.to_datetime(eur.TIME_PERIOD)).tz_localize("UTC")).sort_index()
    eur = eur.reindex(pd.date_range(eur.index.min(), END, freq="1D")).ffill()
    estr = pd.read_csv(f"{D}/ecb/estr.csv")[["TIME_PERIOD", "OBS_VALUE"]]
    estr = pd.Series(estr.OBS_VALUE.values, index=pd.to_datetime(estr.TIME_PERIOD)).sort_index()
    res = dict(meta=dict(start=str(START), end_exclusive=str(END), capital=C0, band=BAND, costs=COSTS, regimes=REGIMES,
                         note="All returns on the full capital (spot leg + margin). USD terms unless 'eur'. Week = Mon-Sun UTC."))
    res["estr"] = {str(y): round(float(estr[estr.index.year == y].mean()), 3) for y in range(2020, 2027)}
    res["estr"]["latest"] = [str(estr.index[-1].date()), float(estr.iloc[-1])]
    years = list(range(2020, 2027))
    events = ["2020-03-12", "2020-03-13", "2021-05-19", "2022-11-08", "2022-11-09", "2022-11-10", "2024-08-05", "2025-10-10", "2025-10-11"]
    combos = {}; combos_eur = {}
    for sym in ["BTCUSDT", "ETHUSDT"]:
        df, fr, xc, okx_from = build(sym)
        R = res[sym] = dict(okx_crosscheck=xc, okx_used_from=okx_from)
        # funding by year (annualised % of notional, 3 prints a day)
        R["funding_by_year"] = {str(y): dict(mean_per_8h_pct=round(100 * fr[fr.index.year == y].mean(), 5),
                                             annual_on_notional_pct=round(100 * fr[fr.index.year == y].sum() * 365 / max(1, fr[fr.index.year == y].resample('1D').sum().shape[0]), 2),
                                             share_negative_prints_pct=round(100 * (fr[fr.index.year == y] < 0).mean(), 1),
                                             green_days_funding_only_pct=round(100 * (fr[fr.index.year == y].resample('1D').sum() > 0).mean(), 1))
                                for y in years}
        R["negative_funding"] = neg_stretch(fr)
        R["negative_funding_by_year"] = {str(y): neg_stretch(fr[fr.index.year == y]) for y in years}
        R["events"] = [event_study(sym, d, df) for d in events]
        R["sims"] = {}
        for rg_name, rg in REGIMES.items():
            for c_name, c in COSTS.items():
                sim, info = simulate(df, rg, c)
                key = f"{rg_name}|{c_name}"
                entry = dict(info=info)
                for view in ["mtm", "accrual"]:
                    e, r = daily_series(sim, df, view=view)
                    entry[view] = dict(all=period_stats(e, r), by_year={str(y): period_stats(e[e.index.year == y], r[r.index.year == y]) for y in years})
                    if view == "mtm":
                        combos.setdefault(key, {})[sym] = (e, r)
                e, r = daily_series(sim, df, eur=eur, view="mtm")
                combos_eur.setdefault(key, {})[sym] = r
                entry["mtm_eur"] = dict(all=period_stats(e, r), by_year={str(y): period_stats(e[e.index.year == y], r[r.index.year == y]) for y in years})
                # EUR account with the USD exposure hedged by a long EURUSD CFD at FP Markets (0.01 lot = 1,000 EUR):
                # cost = FP's published long swap on 10 Nov 2026 (-6.23 USD per lot per night, ~2.0 %/yr of notional)
                e, r = daily_series(sim, df, view="mtm"); rh = r - FX_HEDGE_COST / 365.0
                eh = (1 + rh).cumprod() * C0
                entry["mtm_eur_hedged_fp"] = dict(all=period_stats(eh, rh), by_year={str(y): period_stats(eh[eh.index.year == y], rh[rh.index.year == y]) for y in years})
                entry["funding_received_pct_of_capital"] = round(100 * sim.fund.iloc[-1] / C0, 2)
                entry["costs_paid_pct_of_capital"] = round(100 * sim.cost.iloc[-1] / C0, 2)
                R["sims"][key] = entry
            # no-rebalance: per year, from Jan 1, does the short get liquidated / closed out?
            nr = {}
            for y in years:
                sub = df[df.index.year == y]
                sim, info = simulate(sub, rg, COSTS["zero"], rebalance=False)
                nr[str(y)] = dict(liquidations=info["liquidations"], first=info["liq_times"][:1])
            R["no_rebalance_from_jan1"] = {rg_name: nr} if "no_rebalance_from_jan1" not in R else {**R["no_rebalance_from_jan1"], rg_name: nr}
        # band sensitivity (offshore taker) to show what rebalancing costs
        bs = {}
        for b in [0.04, 0.08, 0.12, 0.16]:
            for rg_name, rg in REGIMES.items():
                for cn in ["offshore_taker", "eu_taker"]:
                    sim, info = simulate(df, rg, COSTS[cn], band=b)
                    e, r = daily_series(sim, df)
                    st = period_stats(e, r)
                    bs[f"{rg_name}|{cn}|band{int(b*100)}"] = dict(rebal=info["rebalances"], liq=info["liquidations"], annual_pct=st["annual_pct"],
                                                                 cost_pct_capital=round(100 * sim.cost.iloc[-1] / C0, 2), worst_day=st["worst_day_pct"])
        R["band_sensitivity"] = bs
        print(sym, "done", flush=True)
    # 50/50 BTC+ETH (each leg on half the capital, daily returns averaged)
    res["BTC_ETH_5050"] = {}
    for key, d in combos.items():
        r = (d["BTCUSDT"][1] + d["ETHUSDT"][1]) / 2
        e = (1 + r).cumprod() * C0
        res["BTC_ETH_5050"][key] = dict(all=period_stats(e, r), by_year={str(y): period_stats(e[e.index.year == y], r[r.index.year == y]) for y in years})
        rh = r - FX_HEDGE_COST / 365.0; eh = (1 + rh).cumprod() * C0
        res["BTC_ETH_5050"][key]["eur_hedged_fp"] = dict(all=period_stats(eh, rh), by_year={str(y): period_stats(eh[eh.index.year == y], rh[rh.index.year == y]) for y in years})
        re_ = (combos_eur[key]["BTCUSDT"] + combos_eur[key]["ETHUSDT"]) / 2; ee = (1 + re_).cumprod() * C0
        res["BTC_ETH_5050"][key]["eur_unhedged"] = dict(all=period_stats(ee, re_), by_year={str(y): period_stats(ee[ee.index.year == y], re_[re_.index.year == y]) for y in years})
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(res, open(OUT, "w"), indent=1, default=str)
    print("wrote", OUT)


if __name__ == "__main__":
    main()
