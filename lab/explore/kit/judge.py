"""The verdict of an idea on the bars of CHARTER.md ('The bars'), results.json, trials.jsonl and the ledger line.

N_all  = running total of configurations in LEDGER.md (read BEFORE this idea is added) + this idea's configurations.
N_main = N_MAIN_BEFORE + ideas of this search with a read verdict (ledger rows with Configs > 0) + 1.
N_MAIN_BEFORE = 160: main configurations whose in-sample verdict the lab read before this search, estimated from
lab/PROTOCOL*.md and the trials.jsonl files (in-sample figures only): one per rule family per track (crossasset 8,
meanrev 7, orb 3, trend 3, pivots 7, pivbb 4, seasonality 3, crypto 6 (3 families x 2 markets), events 4, fx 10,
gold2 4, idx_eu 2, idx_us 4, leadlag 2, micro 1, ml 5, overnight 3, dip 3, jours 1, stocks 2, vol 1, shape 6,
autopsy lenses x sleeves 60, sizing and stakes 5, language model 2, rounds 4-6: 7) = about 163, rounded to 160
(plausible range 100 - 210: 100 without the autopsy lenses, 207 from a raw family count of the files).
The selection LABEL is read on N_all (CHARTER.md: 'the total number of configurations ever tested'); N_main is reported.
It is a label, not a gate (CHARTER 'Selection', amended 2026-11-18): 'pass' (deflated probability >= 0.95) and 'pass,
weak against selection' both go on to the independent attack and the single validation look.
Selection variance V (stats.deflated_sharpe): max(1/(T-1), the variance of the SRs of this idea's configurations, when
there are >= 3). A neighbour much better or worse than the main widens V and can push the DSR to 0 (conservative: a
real find may read 'weak'); results.json also reports dsr_N_all_V_noise (V = 1/(T-1)) so the lead can see that cost.
"""
import datetime as _dt
import hashlib
import json
import os
import re

import numpy as np
import pandas as pd

from . import checks as K
from . import costs as C
from . import stats as S

KIT = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(KIT, "..", "LEDGER.md")
N_MAIN_BEFORE = 160
MAX_CONFIGS = 11                                   # CHARTER rule 4: the main + its neighbours, at most 11
MAX_HOLD_DEFAULT = 5                               # CHARTER 'The bars': hold <= 5 trading days
MAX_HOLD_SLOW = 40                                 # CHARTER 'Slow track' (amendment of 2026-11-18): up to 40
IS_LAST_YEAR = 2021
VAL_YEARS = (2022, 2023, 2024, 2025)
# approximate EUR per unit of quote currency, for the minimum-lot figures only (reported, not judged)
EUR_PER = {"EUR": 1.0, "USD": 1 / 1.15, "JPY": 1 / 130.0, "CAD": 1 / 1.50, "CHF": 1 / 1.10}
SMALL_BASKET_SHARE = {2: 0.75, 3: 0.60, 4: 0.50}


def ledger_total(path=LEDGER):
    txt = open(path).read()
    m = re.search(r"Running total of configurations[^\n]*?\*\*([\d,\s]+)\*\*", txt)
    if not m:
        raise ValueError("running total not found in LEDGER.md")
    return int(re.sub(r"[^\d]", "", m.group(1)))


def ideas_read(path=LEDGER):
    """Ledger rows of this search whose configurations were run (Configs > 0)."""
    n = 0
    for line in open(path):
        c = [x.strip() for x in line.split("|")]
        if len(c) > 7 and re.fullmatch(r"\d{3}", c[1] or "") and re.fullmatch(r"\d+", c[6] or ""):
            n += int(c[6]) > 0
    return n


def ledger_add(n_configs, line=None, path=LEDGER):
    """Add n_configs to the running total in LEDGER.md and append the ledger line (if given). Returns the new total."""
    txt = open(path).read()
    old = ledger_total(path)
    new = old + int(n_configs)
    txt = re.sub(r"(Running total of configurations[^\n]*?\*\*)([\d,\s]+)(\*\*)", lambda m: f"{m.group(1)}{new}{m.group(3)}",
                 txt, count=1)
    if line:
        txt = txt.rstrip("\n") + "\n" + line.rstrip("\n") + "\n"
    with open(path, "w") as f:
        f.write(txt)
    return new


def _b(value, ok, bar):
    v = value if not isinstance(value, (np.floating, np.integer)) else value.item()
    return {"value": v, "bar": bar, "pass": bool(ok)}


def _sr_series(t, basket):
    return S.daily_sums(t).to_numpy() if basket else t.R.to_numpy(float)


def sizing(main):
    """Minimum-lot figures per market (lab/r2/fp_costs.json: min_lot, units_per_lot, leverage, quote): margin of one
    minimum lot at the median entry price, and its loss at the median stop distance, in EUR at rough fixed rates
    (EUR_PER). REPORTED, NOT JUDGED: the charter's sizing bar (1,000-5,000 EUR, margin at 1:500, at most 6 positions
    for the whole robot) needs the robot's risk plan, which the lead applies."""
    out = {"judged": False, "note": "reported only: the charter's sizing bar is checked by the lead (risk plan)",
           "by_market": {}}
    for mk, g in main.groupby("market") if len(main) else []:
        sp = C.spec(mk)
        if "pair" in sp:
            out["by_market"][mk] = _pair_sizing(sp, g)
            continue
        rate = EUR_PER.get(sp.get("quote", "USD"), 1 / 1.15)
        units = float(sp.get("min_lot", 0.01)) * float(sp.get("units_per_lot", 1))
        px, sd = float(g.entry_px.median()), float(g.stop_dist.median())
        notional = units * px * rate                                         # quote currency -> EUR
        out["by_market"][mk] = {"min_lot": float(sp.get("min_lot", 0.01)), "margin_eur": notional / float(sp.get("leverage", 500)),
                                "loss_at_median_stop_eur": units * sd * rate}
        if sp.get("min_commission_per_side"):                               # shares: MODELLED (kit v2.1 fix, V21-2)
            mc, cpu = float(sp["min_commission_per_side"]), float(sp.get("commission_per_unit", 0.0))
            n_us = C.trade_notional(mk)                                     # quote currency (USD)
            n_1k = C.trade_notional(mk, account_eur=1000.0)
            ub = mc / cpu if cpu else None

            def _rt(n):                                                     # commission round trip in bp, notional n
                return 2 * max(mc, cpu * n / px) / n * 1e4
            out["by_market"][mk].update({
                "min_commission_per_side": mc, "min_commission_modelled": True, "trade_notional_usd": n_us,
                "units_at_trade_notional": n_us / px, "units_below_which_min_commission_binds": ub,
                "commission_bp_round_trip_modelled": _rt(n_us),
                "commission_bp_round_trip_at_1000_eur_account": _rt(n_1k),
                "extra_cost_bp_round_trip_at_1000_eur_account": _rt(n_1k) - _rt(n_us),
                "note": "the commission per side is max(per share x shares, minimum per order) at the stake notional "
                        "(5,000 EUR / 6 positions x leverage, costs.trade_notional), in the net and stress results; a "
                        "1,000 EUR account pays the extra cost shown (round trip, at the median entry price)"})
    if out["by_market"]:
        out["min_lot_margin_eur"] = max(v["margin_eur"] for v in out["by_market"].values())
        out["min_lot_loss_at_median_stop_eur"] = max(v["loss_at_median_stop_eur"] for v in out["by_market"].values())
        out["min_lot_loss_pct_of_1000_eur"] = 100 * out["min_lot_loss_at_median_stop_eur"] / 1000
    return out


def dividend_report(main):
    """Kit v2.1 fix 2 (KF-4), fix 3 (R3-6): the long result's dependence on the dividend credit. For each share market of
    the main, and each share LEG of a hedged pair (PairBook credits a long leg too: kit v2.1 fix 3), the long trades /
    legs open at an ex-date's first bar and the dividends they were credited at the file's dividend_credit_long (0.70),
    and the main's PF and mean R (net) recomputed with the long credit at 0 and at 1 (a pair leg's dividend is a fraction
    of its notional, R moves by its change / stop_frac). REPORTED: the verdict uses the file's credit; a pass that needs
    the credit (PF at 0 below 1) is flagged."""
    out = {"by_market": {}, "credit_long_used": None}
    if not len(main):
        return out
    R0, R1 = main.R.to_numpy(float).copy(), main.R.to_numpy(float).copy()
    any_div = False
    for mk, g in main.groupby("market"):
        sp = C.spec(mk)
        et, xt = pd.DatetimeIndex(g.entry_time), pd.DatetimeIndex(g.exit_time)
        pos = main.index.get_indexer(g.index)
        if "pair" in sp:
            legs = [(k, int(s_)) for k, s_ in zip(sp["pair"]["legs"], sp["pair"]["sides"]) if "dividends" in C.spec(k)]
            if not legs:
                continue
            sdf = (g.stop_frac.to_numpy(float) if "stop_frac" in g else
                   g.stop_dist.to_numpy(float) / g.entry_px.to_numpy(float))
            one = np.ones(len(g))
            rec = {"legs": {}, "long_trades_across_ex_dates": 0, "short_trades_across_ex_dates": 0,
                   "long_credit_bp_total": 0.0}
            for leg, ls in legs:
                cl = float(C.spec(leg).get("dividend_credit_long", 0.0))
                out["credit_long_used"] = cl
                side = g.side.to_numpy() * ls
                d_used = C.dividends(leg, side, one, et, xt)
                d0 = C.dividends(leg, side, one, et, xt, credit_long=0.0)
                d1 = C.dividends(leg, side, one, et, xt, credit_long=1.0)
                R0[pos] += (d_used - d0) / sdf
                R1[pos] += (d_used - d1) / sdf
                lng = (side > 0) & (d0 == 0) & (d1 != 0)
                any_div |= bool(lng.any())
                lr = {"credit_long_used": cl, "long_trades_across_ex_dates": int(lng.sum()),
                      "short_trades_across_ex_dates": int(((side < 0) & (d_used != 0)).sum()),
                      "long_credit_bp_total": float((-d_used[lng] * 1e4).sum())}
                rec["legs"][leg] = lr
                for k_ in ("long_trades_across_ex_dates", "short_trades_across_ex_dates", "long_credit_bp_total"):
                    rec[k_] += lr[k_]
            rec["credit_long_used"] = out["credit_long_used"]
            out["by_market"][mk] = rec
            continue
        if "dividends" not in sp:
            continue
        cl = float(sp.get("dividend_credit_long", 0.0))
        out["credit_long_used"] = cl
        side, px, sd = g.side.to_numpy(), g.entry_px.to_numpy(float), g.stop_dist.to_numpy(float)
        d_used = C.dividends(mk, side, px, et, xt)
        d0 = C.dividends(mk, side, px, et, xt, credit_long=0.0)
        d1 = C.dividends(mk, side, px, et, xt, credit_long=1.0)
        R0[pos] += (d_used - d0) / sd
        R1[pos] += (d_used - d1) / sd
        lng = (side > 0) & (d0 == 0) & (d1 != 0)
        any_div |= bool(lng.any())
        out["by_market"][mk] = {"credit_long_used": cl, "long_trades_across_ex_dates": int(lng.sum()),
                                "short_trades_across_ex_dates": int(((side < 0) & (d_used != 0)).sum()),
                                "long_credit_bp_total": float((-d_used[lng] / px[lng] * 1e4).sum())}
    if out["by_market"]:
        out.update({"PF_net": S.pf(main.R), "mean_R_net": float(main.R.mean()),
                    "PF_net_credit_0": S.pf(pd.Series(R0)), "mean_R_net_credit_0": float(R0.mean()),
                    "PF_net_credit_1": S.pf(pd.Series(R1)), "mean_R_net_credit_1": float(R1.mean()),
                    "needs_credit": bool(any_div and S.pf(main.R) >= 1 > S.pf(pd.Series(R0)))})
    return out


def _pair_sizing(sp, g):
    """Minimum-lot figures of a hedged pair (both legs, equal notional at entry): the notional per leg is the larger of
    the two legs' minimum-lot notionals at their median entry prices (so each leg is at least one minimum lot); each
    leg's lots for that notional (raw, then rounded UP to its lot step: equal notional is then only approximate);
    margin = the sum of both legs' margins; loss at the median stop = notional per leg x median stop fraction (the
    pair's result is per unit of one leg's notional). Reported, not judged, at the rough EUR_PER rates."""
    legs = sp["pair"]["legs"]
    sdf = float(g.stop_frac.median()) if "stop_frac" in g else float((g.stop_dist / g.entry_px).median())
    info, need = {}, []
    for key, col in zip(legs, ("entry_px_a", "entry_px_b")):
        s = C.spec(key)
        rate = EUR_PER.get(s.get("quote", "USD"), 1 / 1.15)
        px = float(g[col].median())
        unit_eur = px * rate                                                # one unit of the leg in EUR
        info[key] = {"s": s, "unit_eur": unit_eur, "px": px}
        need.append(float(s.get("min_lot", 0.01)) * float(s.get("units_per_lot", 1)) * unit_eur)
    notional = max(need)
    legs_out, margin = {}, 0.0
    for key in legs:
        s, ue = info[key]["s"], info[key]["unit_eur"]
        lots = notional / ue / float(s.get("units_per_lot", 1))
        step = float(s.get("lot_step", s.get("min_lot", 0.01)))
        lots_r = max(float(s.get("min_lot", 0.01)), np.ceil(lots / step - 1e-9) * step)
        m = lots_r * float(s.get("units_per_lot", 1)) * ue / float(s.get("leverage", 500))
        margin += m
        legs_out[key] = {"median_entry_px": info[key]["px"], "lots_for_equal_notional": lots, "lots_rounded_up": lots_r,
                         "margin_eur": m}
    return {"pair": True, "legs": legs_out, "notional_per_leg_eur": notional, "min_lot": None,
            "margin_eur": margin, "loss_at_median_stop_eur": notional * sdf, "median_stop_frac": sdf}


def _same_events(rep, main):
    """Does an event truncation report test the events each simulated market of the main used? Compared per market
    (verifier V2): the report's own set for that market, else its '*' set, against main.attrs['events_used']; falls back
    to the exact events_sha when either side lacks the per-market record."""
    used, by_key = main.attrs.get("events_used"), rep.get("events_by_key")
    if isinstance(used, dict) and used and isinstance(by_key, dict):
        return all(v is not None and v == by_key.get(m, by_key.get("*")) for m, v in used.items())
    return rep.get("events_sha") is not None and rep.get("events_sha") == main.attrs.get("events_sha")


def verdict(idea_dir, main, neighbours=None, every_signal=None, null=None, corr="compute", n_configs=None,
            basket=None, small_basket=True, write=True, idea=None, data_desc=None, ledger=LEDGER, ten=None, extra=None,
            truncation=None, event_truncation=None, max_hold_tdays=MAX_HOLD_DEFAULT):
    """Judge the MAIN configuration. main / every_signal / neighbours[id]: trade tables of kit.sim.simulate (every_signal
    = the same rule with mode='every'); null: the dict of stats.null_test (>= 2000 draws); corr: 'compute' (reads the
    ten's trades from lab/results/r2/recalc/trades with the in-sample filter), a number, or None (bar fails as missing);
    truncation: the report of checks.truncation_test on the main signal build (REQUIRED: bar 'truncation_test' passes
    only if the report passed, cut at least one signal's own time stamp and its signals_sha equals
    main.attrs['signals_sha']); the declaration is checked here (bar 'declared_hash': declared.json must match
    declared.sha256 in idea_dir). More than MAX_CONFIGS (11) configurations fails (bar 'configs<=11').
    Years positive: every calendar year from the main's first entry year to 2021 counts; a year without a trade is
    not positive. The minimum-lot sizing figures are reported in res['sizing'] and are NOT judged (a hedged pair:
    both legs, judge._pair_sizing).
    Exit on a condition: when the main was simulated with exit=('event', events, max_hold) (main.attrs['events_sha']),
    bar 'event_truncation_test' is added: it passes only if event_truncation is the passing report of
    checks.truncation_test on the EVENT build, with at least one cut at an event's own time stamp and its events_sha
    equal to main.attrs['events_sha'] (compared per simulated market: main.attrs['events_used'] against the report's
    events_by_key, so a table without market and {market: times} with the same times are the same events). Every
    truncation report must carry the dense cuts of checks.cuts_ok (verifier V1). The null bar also requires
    null['exit_key'] == main.attrs['exit_key'] (the null ran the main's own exit, stop, target and events; verifier V4).
    A pair is one market (its name), several pairs a basket of pairs.
    max_hold_tdays: 5 by default (bar 'hold<=5d'); a run of the slow track (CHARTER 'Slow track') passes 40 (bar
    'hold<=40d', the ledger line says 'slow track'), and only when idea_dir/declared.json says "track": "slow"; any
    other value raises (kit v2.1 fix, V21-6). results.json records it.
    PROVISIONAL COSTS: when a market of the main (or a leg of a pair) has provisional costs (kit/extra_costs.json), the
    ledger line and results.json say 'PROVISIONAL COSTS' (a pass must be re-judged on the broker's own figures).
    Returns {'verdict', 'bars', 'ledger_line', ...}; with write=True writes results.json and appends trials.jsonl in
    idea_dir. Call it BEFORE ledger_add (N_all reads the running total as it stands)."""
    if isinstance(max_hold_tdays, bool) or not isinstance(max_hold_tdays, (int, np.integer)) or \
            int(max_hold_tdays) not in (MAX_HOLD_DEFAULT, MAX_HOLD_SLOW):
        raise ValueError(f"max_hold_tdays is {MAX_HOLD_DEFAULT} or {MAX_HOLD_SLOW} (CHARTER: 5, or 40 on the slow track); "
                         f"got {max_hold_tdays!r}")
    max_hold_tdays = int(max_hold_tdays)
    if max_hold_tdays == MAX_HOLD_SLOW:                    # kit v2.1 fix (V21-6): only an idea DECLARED slow
        try:
            trk = json.load(open(os.path.join(idea_dir, "declared.json"))).get("track")
        except (OSError, ValueError, AttributeError):
            trk = None
        if str(trk).strip().lower() != "slow":
            raise ValueError(f"max_hold_tdays={MAX_HOLD_SLOW} (slow track) needs the idea's declared.json to say "
                             f"\"track\": \"slow\" (CHARTER 'Slow track'); it says {trk!r}")
    neighbours = neighbours or {}
    n_configs = int(n_configs if n_configs is not None else 1 + len(neighbours))
    mk = sorted(main.market.unique()) if len(main) else []
    basket = (len(mk) > 1) if basket is None else basket
    sm = S.summary(main)
    if len(main):
        y0 = int(pd.DatetimeIndex(main.entry_time).year.min())
        yr = S.by_year(main).reindex(range(y0, max(IS_LAST_YEAR, y0) + 1), fill_value=0.0)
        sm["years_positive_frac"] = float((yr > 0).mean())
        sm["by_year_R"] = {int(k): float(v) for k, v in yr.items()}
    bars = {}
    dens = K.cuts_ok(truncation) if isinstance(truncation, dict) else (False, "")
    tr_ok = (isinstance(truncation, dict) and bool(truncation.get("pass")) and dens[0]
             and truncation.get("signals_sha") is not None and truncation.get("signals_sha") == main.attrs.get("signals_sha"))
    why = ("missing" if not isinstance(truncation, dict) else "failed" if not truncation.get("pass") else
           dens[1] if not dens[0] else
           "built from other signals than the main's" if not tr_ok else "passed")
    bars["truncation_test"] = _b(why, tr_ok, "checks.truncation_test on the main signal build passed (same signals, "
                                             "dense cuts: checks.cuts_ok)")
    if main.attrs.get("events_sha") is not None:
        et = event_truncation
        edens = K.cuts_ok(et) if isinstance(et, dict) else (False, "")
        same_ev = isinstance(et, dict) and _same_events(et, main)
        ev_ok = isinstance(et, dict) and bool(et.get("pass")) and edens[0] and same_ev
        ewhy = ("missing" if not isinstance(et, dict) else "failed" if not et.get("pass") else
                edens[1] if not edens[0] else
                "built from other events than the main's exit" if not ev_ok else "passed")
        bars["event_truncation_test"] = _b(ewhy, ev_ok, "checks.truncation_test on the exit-event build passed (same events "
                                                        "per market, dense cuts)")
    try:
        K.declared_hash(idea_dir)
        dh = True
        dwhy = "matches declared.sha256"
    except (AssertionError, OSError, IndexError) as e:
        dh, dwhy = False, f"{type(e).__name__}: {e}"[:200]
    bars["declared_hash"] = _b(dwhy, dh, "declared.json matches declared.sha256")
    bars[f"configs<={MAX_CONFIGS}"] = _b(n_configs, n_configs <= MAX_CONFIGS, f"at most {MAX_CONFIGS} configurations")
    if not basket:
        bars["n>=250"] = _b(sm.get("n", 0), sm.get("n", 0) >= 250, ">= 250 trades")
        bars["t>=2.5"] = _b(sm.get("t_trade"), (sm.get("t_trade") or 0) >= 2.5, "t per trade >= 2.5")
    else:
        bars["t_daily>=2.5"] = _b(sm.get("t_daily"), (sm.get("t_daily") or 0) >= 2.5, "t on daily sums of R >= 2.5")
        share_bar = SMALL_BASKET_SHARE.get(len(mk), 0.25) if small_basket else 0.25
        bars["markets_positive>=65%"] = _b(sm.get("markets_positive_frac"), sm.get("markets_positive_frac", 0) >= 0.65,
                                           ">= 65 % of markets with positive expectancy")
        msh = sm.get("max_market_share_of_profit")
        msh_ok = msh is not None and np.isfinite(msh)
        bars[f"max_market_share<={share_bar:.0%}"] = _b(msh if msh_ok else "n/a (total profit <= 0)",
                                                        msh_ok and msh <= share_bar,
                                                        f"no market above {share_bar:.0%} of the profit")
    bars["PF>=1.12"] = _b(sm.get("PF", 0), sm.get("PF", 0) >= 1.12, "PF net >= 1.12")
    bars["years>=60%"] = _b(sm.get("years_positive_frac", 0), sm.get("years_positive_frac", 0) >= 0.6, ">= 60 % of years positive")
    bars["PF_stress>=1.04"] = _b(sm.get("PF_stress", 0), sm.get("PF_stress", 0) >= 1.04, "PF with spread and slippage x1.5 >= 1.04")
    npf = [S.pf(t.R) for t in neighbours.values()]
    nmed = float(np.median(npf)) if npf else None
    bars["neighbours_median_PF>=1.06"] = _b(nmed, nmed is not None and nmed >= 1.06, "median PF of the neighbours >= 1.06")
    ev = float(every_signal.R.mean()) if every_signal is not None and len(every_signal) else None
    bars["every_signal_exp>0"] = _b(ev, ev is not None and ev > 0, "every-signal expectancy > 0")
    hb = f"hold<={max_hold_tdays}d"
    bars[hb] = _b(sm.get("hold_tdays_max"), sm.get("hold_tdays_max", 99) <= max_hold_tdays,
                  f"hold <= {max_hold_tdays} trading days" + (" (slow track)" if max_hold_tdays != MAX_HOLD_DEFAULT else ""))
    npct = None if null is None else float(null["percentile"])
    nd = 0 if null is None else int(null["n_draws"])
    n_bound = null is not None and null.get("exit_key") is not None and null.get("exit_key") == main.attrs.get("exit_key")
    bars["null>=97.5"] = _b(npct if (null is None or n_bound) else
                            f"{npct} but the null was run with another exit, stop, target or events than the main",
                            npct is not None and nd >= 2000 and npct >= 97.5 and n_bound,
                            "random-entry null (same market, side, clock, the main's own exit rule: exit_key; >= 2000 "
                            "draws) >= 97.5th percentile")
    if isinstance(corr, str) and corr == "compute":
        corr = S.corr_with_ten(main, ten=ten)
    bars["corr<=0.30"] = _b(corr, corr is not None and corr <= 0.30,
                            "weekly corr with the sum of the ten <= 0.30 (CHARTER 'Independence'; a negative one passes)")
    n_all = ledger_total(ledger) + n_configs
    n_main = N_MAIN_BEFORE + ideas_read(ledger) + 1
    x = _sr_series(main, basket)
    srs = [S.deflated_sharpe(_sr_series(t, basket), 2)["sr"] for t in list(neighbours.values()) + [main] if len(t) > 2]
    var_sr = float(np.var(srs, ddof=1)) if len(srs) >= 3 else None
    d_all = S.deflated_sharpe(x, n_all, var_sr)
    d_main = S.deflated_sharpe(x, n_main, var_sr)
    d_noise = S.deflated_sharpe(x, n_all)          # V = 1/(T-1) only: reported, to show what the neighbours' spread costs
    selection = {"N_all": n_all, "N_main": n_main, "dsr_N_all": d_all, "dsr_N_main": d_main, "dsr_N_all_V_noise": d_noise,
                 "pass": bool(np.isfinite(d_all["dsr"]) and d_all["dsr"] >= 0.95)}
    failed = [k for k, v in bars.items() if not v["pass"]]
    verdict_ = "fail" if failed else ("pass" if selection["pass"] else "pass, weak against selection")
    decl = os.path.join(idea_dir, "declared.json")
    sha = hashlib.sha256(open(decl, "rb").read()).hexdigest() if os.path.exists(decl) else None
    if idea is None and os.path.exists(decl):
        try:
            idea = json.load(open(decl)).get("idea")
        except Exception:
            idea = None
    idea = idea or os.path.basename(os.path.abspath(idea_dir))
    years = sorted(sm.get("by_year_R", {}))
    fmt = lambda v, k=2: "n/a" if v is None or (isinstance(v, float) and not np.isfinite(v)) else f"{v:.{k}f}"  # noqa: E731
    key = (f"n {sm.get('n', 0)}, PF net {fmt(sm.get('PF'))}, t {fmt(sm.get('t_daily' if basket else 't_trade'))}"
           f"{' (daily sums)' if basket else ''}, PF x1.5 {fmt(sm.get('PF_stress'))}, years + "
           f"{int(round(sm.get('years_positive_frac', 0) * len(years)))}/{len(years)}, null {fmt(npct, 1)} pct, "
           f"corr {fmt(corr)}, DSR {fmt(d_all['dsr'], 3)} (N_all {n_all}) / {fmt(d_main['dsr'], 3)} (N_main {n_main})")
    vtxt = {"fail": "fermee : echoue (" + ", ".join(failed) + ")", "pass": "passe en echantillon (A VERIFIER)",
            "pass, weak against selection": "passe en echantillon, faible face a la selection (A VERIFIER)"}[verdict_]
    provisional = sorted(m for m in mk if C.is_provisional(m))
    if max_hold_tdays != MAX_HOLD_DEFAULT:
        vtxt += f" ; slow track (hold<={max_hold_tdays}d)"
    if provisional:
        vtxt += " ; PROVISIONAL COSTS (" + ", ".join(provisional) + ")"
    sz = sizing(main)
    divr = dividend_report(main)
    if divr.get("by_market") and any(v["long_trades_across_ex_dates"] for v in divr["by_market"].values()):
        key += (f", long dividend credit {divr['credit_long_used']:.2f} (PF net at credit 0 / 1: "
                f"{fmt(divr['PF_net_credit_0'])} / {fmt(divr['PF_net_credit_1'])})")
        if divr.get("needs_credit"):
            vtxt += " ; LONG RESULT NEEDS THE DIVIDEND CREDIT"
    if "min_lot_margin_eur" in sz:
        key += (f", sizing not judged (min lot: margin {sz['min_lot_margin_eur']:.0f} EUR, loss at median stop "
                f"{sz['min_lot_loss_at_median_stop_eur']:.1f} EUR)")
    num = os.path.basename(os.path.abspath(idea_dir))[:3]
    line = (f"| {num} | {_dt.date.today().isoformat()} | {idea} | {', '.join(mk)} | {data_desc or ''} | {n_configs} | "
            f"{vtxt} | {key} |")
    res = {"idea": idea, "declared_sha256": sha, "verdict": verdict_, "failed_bars": failed, "basket": basket,
           "bars": bars, "selection": selection, "main": sm, "sizing": sz, "dividends": divr,
           "max_hold_tdays": max_hold_tdays,
           "slow_track": max_hold_tdays != MAX_HOLD_DEFAULT,
           "costs": ("PROVISIONAL COSTS: " + ", ".join(provisional) + " (kit/extra_costs.json; re-judge on the broker's "
                     "own figures before anything else)") if provisional else "FP costs (lab/r2/fp_costs.json)",
           "provisional_costs": bool(provisional),
           "neighbours": {k: {"n": int(len(t)), "PF": S.pf(t.R), "mean_R": float(t.R.mean()) if len(t) else None}
                          for k, t in neighbours.items()},
           "every_signal": None if every_signal is None else {"n": int(len(every_signal)), "mean_R": ev},
           "null": None if null is None else {k: v for k, v in null.items() if k != "means"},
           "counts": main.attrs.get("counts"), "rule": main.attrs.get("rule"), "ledger_line": line,
           "written_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if extra:
        res["extra"] = extra
    if write:
        with open(os.path.join(idea_dir, "results.json"), "w") as f:
            json.dump(res, f, indent=1, default=_js)
        tp = os.path.join(idea_dir, "trials.jsonl")
        if sha is not None and os.path.exists(tp):          # a re-run replaces this declaration's rows (no duplicates)
            keep = [x for x in open(tp).read().splitlines() if x.strip() and f'"declared_sha256": "{sha}"' not in x]
            with open(tp, "w") as f:
                f.write("".join(x + "\n" for x in keep))
        with open(tp, "a") as f:
            for cid, t in [("main", main)] + list(neighbours.items()):
                s = S.summary(t)
                f.write(json.dumps({"id": cid, "role": "main" if cid == "main" else "neighbour", "n": s.get("n", 0),
                                    "PF": s.get("PF"), "t": s.get("t_daily" if basket else "t_trade"),
                                    "PF_stress": s.get("PF_stress"), "mean_R": s.get("mean_R"),
                                    "declared_sha256": sha, "time": res["written_utc"]}, default=_js) + "\n")
    return res


def val_verdict(idea_dir, trades, every_signal, write=True):
    """The single validation look (CHARTER 'The bars', VAL; rule 5) on the frozen main configuration simulated on
    2022-2025 (after data.unlock_val): PF >= 1.06, expectancy > 0, every-signal expectancy > 0, positive in at least 3 of
    the 4 years 2022-2025 (a year without a trade is not positive). Trades must all enter in 2022-2025 (else ValueError:
    no in-sample row may be mixed in, nothing of 2026 exists). Needs idea_dir/val_declared.json. With write=True writes
    val_results.json (never overwrites one: a second look is refused). Returns {'verdict': 'pass'|'fail', 'bars', ...}."""
    p = os.path.join(idea_dir, "val_declared.json")
    if not os.path.isfile(p):
        raise ValueError("val_verdict: no val_declared.json (declare the look first, charter rule 5)")
    out_p = os.path.join(idea_dir, "val_results.json")
    if write and os.path.exists(out_p):
        raise ValueError("val_results.json exists: the validation look is done once")
    for nm, t in (("trades", trades), ("every_signal", every_signal)):
        if len(t):
            y = pd.DatetimeIndex(t.entry_time).year
            if (y < VAL_YEARS[0]).any() or (y > VAL_YEARS[-1]).any():
                raise ValueError(f"val_verdict: {nm} enter outside 2022-2025")
    R = trades.R.to_numpy(float) if len(trades) else np.array([])
    yr = (trades.R.groupby(pd.DatetimeIndex(trades.entry_time).year).sum() if len(trades) else pd.Series(dtype=float))
    yr = yr.reindex(list(VAL_YEARS), fill_value=0.0)
    pf_ = S.pf(R)
    exp_ = float(R.mean()) if len(R) else None
    ev = float(every_signal.R.mean()) if len(every_signal) else None
    npos = int((yr > 0).sum())
    bars = {"PF>=1.06": _b(pf_, pf_ >= 1.06, "PF net >= 1.06"),
            "exp>0": _b(exp_, exp_ is not None and exp_ > 0, "expectancy (mean net R) > 0"),
            "every_signal_exp>0": _b(ev, ev is not None and ev > 0, "every-signal expectancy > 0"),
            "years>=3/4": _b(npos, npos >= 3, "positive in at least 3 of the 4 years 2022-2025")}
    failed = [k for k, v in bars.items() if not v["pass"]]
    try:
        looks = sum(1 for x in open(_val_log()) if '"track": "explore"' in x)
    except OSError:
        looks = None
    res = {"verdict": "fail" if failed else "pass", "failed_bars": failed, "bars": bars, "n": int(len(R)),
           "t_trade": S.t_stat(R), "val_looks_of_this_search_so_far": looks,
           "PF_stress": S.pf(trades.R_stress) if "R_stress" in trades and len(trades) else None,
           "by_year_R": {int(k): float(v) for k, v in yr.items()},
           "val_declared_sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(),
           "written_utc": _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
    if write:
        with open(out_p, "w") as f:
            json.dump(res, f, indent=1, default=_js)
    return res


def _val_log():
    from . import data as _d
    return _d.val_log_path()


def _js(o):
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if isinstance(o, (pd.Timestamp, np.datetime64)):
        return str(o)
    if isinstance(o, float) and not np.isfinite(o):
        return str(o)
    return str(o)
