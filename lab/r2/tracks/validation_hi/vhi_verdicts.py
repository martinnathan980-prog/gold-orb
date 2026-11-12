"""validation_hi -- the declared criteria of the look, computed mechanically (review F10): res["verdicts"].

spec["criteria"] = {change id: {"kind": <registered kind>, ...}}. Every change in the look (spec "changes_in_look")
gets one entry in the verdicts block: its criteria (criterion, value, reference, rule, pass), "adopted" (every
criterion passes) and the readings that are not criteria. A change in the look without a declared criterion is
reported as such ("declared": false, "adopted": null).

HOOK for the criteria the lead will add for other changes (payoff variants, Addendum I stake rules): write

    import vhi_verdicts as VD

    @VD.register_criterion("my_kind")
    def my_kind(c, res, W):          # c: the spec's criteria entry; res: the run (res["_trades"], res["_books"], ...)
        rows = [VD.row("...", value, reference, ">=", ok)]
        return VD.verdict(c, rows, readings={...})

in a file listed in spec["plugins"] (or here), and add {"<change id>": {"kind": "my_kind", ...}} to spec["criteria"]
before the declaration.

Built-in kinds: synthesis_B's declared criteria (results/r2/autopsy/synthesis_B.json, proposed_validation_look):
  k1_skip     "K1 is adopted only if, on 2022-2025, the sleeve's expectancy per trade with the skip is higher than
              without and its total R is not lower, both with FP costs and with costs x1.5, and the skipped signals
              taken alone earn less on average than the kept ones."
  new_sleeve  "Each new sleeve is adopted only if, with FP costs, PF >= 1.06, expectancy > 0, every-signal
              expectancy > 0, total R positive in at least 3 of the 4 years, and expectancy > 0 with costs x1.5; and
              the weekly mean / sd of R of the ten plus that sleeve is at least that of the ten alone. Read beside
              it, for the robot as it is (not a criterion of the rule): the same sleeve with entry one minute late
              and every position closed on Friday at 16:50 New York; if that version has expectancy <= 0, the sleeve
              waits for a robot that holds it over the weekend."
and synthesis A's declared criteria (results/r2/autopsy/synthesis_A.json, proposed_validation_look, items 3-6):
  synthesis_A_change  "A CHANGE PASSES only if all hold: V1 the sleeve's weekly Sharpe is higher with the change AND
              the ten-sleeve portfolio's weekly Sharpe with the change at its frozen factor is higher (FP); V2 the
              sleeve's total R at a constant stake (1 R per trade at its own stop) is not lower (FP); V3 V1 and V2
              also hold with costs x1.5; V4 the sleeve's gain at equal swing (total R with the change x its factor
              minus total R unchanged) is positive in at least 3 of the 4 entry years 2022, 2023, 2024, 2025 (FP);
              V5 the changed sleeve has an expectancy above 0 and a profit factor of at least 1.06 (FP)." The
              sleeve with the change is '<sleeve>+<variant>', the same sleeve unchanged is '<sleeve>@payoff' (same
              frame, costs and refusal rule); the unchanged portfolio is P0 (the ten sleeves at 1 R per trade, plain
              sum) and the portfolio with the change is P0 with that sleeve replaced by the changed sleeve staked at
              its FROZEN factor (fixed on 2018-02..2021-12 FP by synthesis A; the same factor in x1.5). "3. CHECK
              FIRST ... otherwise stop and report": when res["check_first"] did not pass, these changes are not
              judged (adopted = null, the values are still shown). Reported beside the verdicts (synthesis_A_block,
              res["synthesis_A"]): the passing changes together against the unchanged portfolio, and item 6 (every
              change alone, all five, the passing ones, at a constant stake and at equal swing, FP and x1.5) with
              synthesis A's own frozen measures() (portfolio.py, imported, sha256 checked).
Conventions: every value is computed from the trades of the run (unrounded); trades = entries inside the run's
evaluation window (the look: 2022-01-01 .. 2025-12-31); "as specified" = execution "lab"; years = the window's
years (by entry year, UTC); the weekly measure = the plain sum at 1 R per trade (synthesis_B's portfolio metrics),
server weeks (New York + 7 h, booked at exit), every week of the window counted (an empty week = 0), sd with ddof 1,
weekly Sharpe = mean / sd x sqrt(52); the skipped / kept signals = the K1 signals decided inside the window that are
usable (filled, not refused, not still open at the frame end), each taken alone with FP costs (the walk-forward's
labels). "higher" / "above" = strictly greater, "not lower" / "at least" = greater or equal. A synthesis A row also
carries the pass it would get on the values rounded as synthesis A's measures() rounds them (its rehearsal.py
logic): a difference is flagged ('rounding_tie'), the unrounded comparison decides.
"""
import numpy as np
import pandas as pd

import vhi_book as B

CRITERIA = {}


def register_criterion(kind):
    def deco(fn):
        CRITERIA[kind] = fn
        return fn
    return deco


def _win(t, W):
    a, b = W["eval"]
    return t[(t.entry_time >= a) & (t.entry_time < b)]


def _mean(x):
    x = np.asarray(x, float)
    return float(x.mean()) if len(x) else None


def _pf(R):
    R = np.asarray(R, float)
    w, lo = float(R[R > 0].sum()), float(-R[R < 0].sum())
    return (w / lo) if lo > 0 else None


def row(criterion, value, reference, rule, ok, **extra):
    return {"criterion": criterion, "value": value, "reference": reference, "rule": rule, "pass": bool(ok), **extra}


def verdict(c, rows, readings=None):
    return {"declared": True, "kind": c["kind"], "text": c.get("text"), "criteria": rows,
            "adopted": bool(rows) and all(r["pass"] for r in rows), "readings": readings or {}}


def weekly_mean_over_sd(d, W):
    a, b = W["eval"]
    ws = B.weekly(d, a, b)
    sd = float(ws.std(ddof=1))
    return float(ws.mean() / sd) if sd > 0 else None


@register_criterion("k1_skip")
def k1_skip(c, res, W):
    key, ex = c["sleeve"], c.get("exec", "lab")
    T = res["_trades"]
    rows = []
    for mode in c.get("modes", ["fp", "stress"]):
        tv, tb = _win(T[(key, "main", mode, ex)], W), _win(T[(key, "base", mode, ex)], W)
        ev, eb = _mean(tv.R), _mean(tb.R)
        sv, sb = float(tv.R.sum()), float(tb.R.sum())
        rows.append(row(f"{mode}/{ex}: expectancy per trade with the skip > without", ev, eb, ">",
                        ev is not None and eb is not None and ev > eb, n_with=int(len(tv)), n_without=int(len(tb))))
        rows.append(row(f"{mode}/{ex}: total R with the skip >= without", sv, sb, ">=", sv >= sb))
    sm = c.get("signals_mode", "fp")
    sig = res["_signals"][(key, sm)]
    a, b = W["eval"]
    s = sig[(sig.t_dec >= a) & (sig.t_dec < b)]
    use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()
    skip = s.skip.to_numpy(bool)
    lab = s.label.to_numpy(float)
    sk, kp = lab[use & skip], lab[use & ~skip]
    mk, mp = _mean(sk), _mean(kp)
    rows.append(row("skipped signals taken alone (FP costs): mean R < that of the kept signals", mk, mp, "<",
                    mk is not None and mp is not None and mk < mp, n_skipped=int(len(sk)), n_kept=int(len(kp)),
                    labels_mode=res["sleeves"][key]["runs"][f"{sm}/lab"]["info"]["change_diag"]["labels_mode"]))
    return verdict(c, rows)


@register_criterion("new_sleeve")
def new_sleeve(c, res, W):
    key, ex = c["sleeve"], c.get("exec", "lab")
    T, books = res["_trades"], res["_books"]
    pf_min, need = float(c.get("pf_min", 1.06)), int(c.get("min_positive_years", 3))
    years = list(W["years"])
    t = _win(T[(key, "main", "fp", ex)], W)
    R = t.R.to_numpy(float)
    rows = []
    pf = _pf(R)
    rows.append(row(f"fp/{ex}: profit factor >= {pf_min}", pf, pf_min, ">=",
                    (pf is not None and pf >= pf_min) or (pf is None and len(R) > 0 and (R > 0).any() and not (R < 0).any()),
                    n=int(len(R))))
    e = _mean(R)
    rows.append(row(f"fp/{ex}: expectancy per trade > 0", e, 0.0, ">", e is not None and e > 0))
    es = _mean(_win(T[(key, "every_signal", "fp", ex)], W).R)
    rows.append(row(f"fp/{ex}: every-signal expectancy (each signal taken alone) > 0", es, 0.0, ">",
                    es is not None and es > 0))
    yy = t.entry_time.dt.year.to_numpy() if len(t) else np.zeros(0, int)
    by = {int(y): float(R[yy == y].sum()) for y in years}
    pos = [y for y in years if by[y] > 0]
    rows.append(row(f"fp/{ex}: total R positive in at least {need} of the {len(years)} years", len(pos), need, ">=",
                    len(pos) >= need, total_R_by_year=by))
    est = _mean(_win(T[(key, "main", "stress", ex)], W).R)
    rows.append(row(f"stress/{ex}: expectancy per trade > 0 with costs x1.5", est, 0.0, ">", est is not None and est > 0))
    acc = c.get("account", "sum")
    w1 = weekly_mean_over_sd(books[(c["with"], "fp", ex, acc)], W)
    w0 = weekly_mean_over_sd(books[(c["without"], "fp", ex, acc)], W)
    rows.append(row(f"fp/{ex}/{acc}: weekly mean / sd of R of {c['with']} >= that of {c['without']}", w1, w0, ">=",
                    w1 is not None and w0 is not None and w1 >= w0))
    readings = {}
    for mode in ("fp", "stress"):
        if (key, "main", mode, "live") in T:
            lv = _win(T[(key, "main", mode, "live")], W)
            el = _mean(lv.R)
            readings[f"{mode}/live"] = {"n": int(len(lv)), "expectancy": el, "total_R": float(lv.R.sum())}
    if "fp/live" in readings:
        el = readings["fp/live"]["expectancy"]
        readings["as_the_live_program_would"] = (
            "not a criterion of the rule: run as the hands would (entry one minute late at market, every position "
            "closed on Friday 16:50 New York), FP costs, expectancy "
            + ("n/a (no trade)" if el is None else f"{el:+.4f} R per trade")
            + (": the sleeve waits for a robot that holds it over the weekend" if el is None or el <= 0
               else ": positive, the robot as it is can carry it"))
    return verdict(c, rows, readings)


# ------------------------------------------------------------------------------------------------- synthesis A
def _mkbook(per, W):
    """Plain-sum book of {key: (trades, stakes or None, meta)} on the judged window (entries in W['eval'])."""
    a, b = W["eval"]
    per = {k: v for k, v in per.items() if v[0] is not None and len(v[0])}
    if not per:
        e = pd.DatetimeIndex([], tz="UTC")
        return pd.DataFrame({"sleeve": pd.Series([], dtype=object), "entry_time": e, "exit_time": e,
                             "R": np.zeros(0), "m": np.zeros(0), "Rm": np.zeros(0)})
    return B.make_book(per, a, b)


def weekly_sharpe(d, W):
    """Weekly Sharpe of book d (column Rm) on the judged window: mean / sd (ddof 1) x sqrt(52), every week counted."""
    a, b = W["eval"]
    ws = B.weekly(d, a, b)
    sd = float(ws.std(ddof=1))
    return float(ws.mean() / sd * np.sqrt(52)) if sd > 0 else None


def weekly_sd(d, W):
    a, b = W["eval"]
    return float(B.weekly(d, a, b).std(ddof=1))


def _swapped(res, d0, swaps, mode, ex, W, scale):
    """Book d0 (P0 on the window) with each (replaced key, changed key, factor) of `swaps`: the replaced sleeve's rows
    removed, the changed sleeve's window trades added at a constant stake (scale=False) or at its factor."""
    T, meta = res["_trades"], res["_meta"]
    parts = [d0[~d0.sleeve.isin([rep for rep, _, _ in swaps])]]
    for rep, var, f in swaps:
        t = T[(var, "main", mode, ex)]
        parts.append(_mkbook({var: (t, np.full(len(t), float(f) if scale else 1.0), meta[var])}, W))
    return pd.concat([p for p in parts if len(p)], ignore_index=True) if any(len(p) for p in parts) else parts[0]


def _r(x, nd):
    return None if x is None else round(float(x), nd)


def _ops(rule):
    return {">": lambda a, b: a > b, ">=": lambda a, b: a >= b}[rule]


@register_criterion("synthesis_A_change")
def synthesis_A_change(c, res, W):
    var, ref, rep, pn = c["sleeve"], c["unchanged"], c["replaces"], c.get("portfolio", "P0")
    f, ex, acc = float(c["frozen_factor"]), c.get("exec", "lab"), c.get("account", "sum")
    pf_min, need = float(c.get("pf_min", 1.06)), int(c.get("min_positive_years", 3))
    years = [int(y) for y in W["years"]]
    T, meta = res["_trades"], res["_meta"]
    if rep not in res["portfolio_sleeves"][pn]:
        raise ValueError(f"{var}: the replaced sleeve {rep} is not in {pn}")
    rows, vals, readings = [], {}, {}
    for mode in c.get("modes", ["fp", "stress"]):
        tv, tr = _win(T[(var, "main", mode, ex)], W), _win(T[(ref, "main", mode, ex)], W)
        sv = weekly_sharpe(_mkbook({var: (tv, None, meta[var])}, W), W)
        sr = weekly_sharpe(_mkbook({ref: (tr, None, meta[ref])}, W), W)
        d0 = res["_books"][(pn, mode, ex, acc)]
        p0 = weekly_sharpe(d0, W)
        p1 = weekly_sharpe(_swapped(res, d0, [(rep, var, f)], mode, ex, W, True), W)
        pll = weekly_sharpe(_swapped(res, d0, [(rep, ref, 1.0)], mode, ex, W, True), W)
        Rv, Rr = float(tv.R.sum()), float(tr.R.sum())
        vals[mode] = {"sleeve_weekly_sharpe": [sr, sv], "portfolio_weekly_sharpe_frozen_factor": [p0, p1],
                      "total_R_constant_stake": [Rr, Rv], "n": [int(len(tr)), int(len(tv))]}
        tag1, tag2 = ("V1", "V2") if mode == "fp" else ("V3", "V3")
        for tag, crit_, v, r_, rule, nd in (
                (tag1, f"{mode}/{ex}: the sleeve's weekly Sharpe with the change > unchanged ({ref})", sv, sr, ">", 4),
                (tag1, f"{mode}/{ex}/{acc}: the ten-sleeve portfolio's weekly Sharpe with the change at its frozen "
                       f"factor x{f} > the unchanged portfolio's ({pn})", p1, p0, ">", 4),
                (tag2, f"{mode}/{ex}: the sleeve's total R at a constant stake with the change >= unchanged", Rv, Rr,
                 ">=", 2)):
            ok = v is not None and r_ is not None and _ops(rule)(v, r_)
            ok_r = v is not None and r_ is not None and _ops(rule)(_r(v, nd), _r(r_, nd))
            rows.append(row(f"{tag} {crit_}", v, r_, rule, ok, test=tag, pass_at_synthesis_A_rounding=bool(ok_r),
                            rounding_tie=bool(ok != ok_r)))
        prv = (res.get("payoff_reference_vs_sB") or {}).get(ref, {}).get(f"{mode}/{ex}", {})
        sd_v = weekly_sd(_mkbook({var: (tv, None, meta[var])}, W), W)
        sd_r = weekly_sd(_mkbook({ref: (tr, None, meta[ref])}, W), W)
        readings[f"{mode}/{ex}"] = {
            "changed_sleeve": B.sstats(tv.R), "unchanged_sleeve": B.sstats(tr.R),
            "portfolio_like_for_like (P0 with the unchanged sleeve in the changed sleeve's convention, not a criterion)":
                {"weekly_sharpe": pll,
                 "equals_P0": bool(pll is not None and p0 is not None and abs(pll - p0) <= 1e-12 * max(1.0, abs(p0))),
                 "diff_from_P0": None if pll is None or p0 is None else pll - p0,
                 "V1_portfolio_part_would_be": bool(p1 is not None and pll is not None and p1 > pll)},
            "unchanged_sleeve_identical_to_the_P0_sleeve_in_the_window": prv.get("identical"),
            "equal_swing_factor_recomputed_on_this_window (a reading; the criteria use the frozen factor)":
                (sd_r / sd_v) if sd_v > 0 else None}
    # V4 (FP): the gain at equal swing by entry year
    tv, tr = _win(T[(var, "main", "fp", ex)], W), _win(T[(ref, "main", "fp", ex)], W)
    yv = tv.entry_time.dt.year.to_numpy() if len(tv) else np.zeros(0, int)
    yr = tr.entry_time.dt.year.to_numpy() if len(tr) else np.zeros(0, int)
    Rv_y = {y: float(tv.R.to_numpy()[yv == y].sum()) for y in years}
    Rr_y = {y: float(tr.R.to_numpy()[yr == y].sum()) for y in years}
    gain = {y: f * Rv_y[y] - Rr_y[y] for y in years}
    gain_r = {y: round(round(Rv_y[y], 2) * f - round(Rr_y[y], 2), 2) for y in years}   # synthesis A's rehearsal.py
    pos, pos_r = [y for y in years if gain[y] > 0], [y for y in years if gain_r[y] > 0]
    rows.append(row(f"V4 fp/{ex}: the sleeve's gain at equal swing (total R with the change x {f} minus total R "
                    f"unchanged) positive in at least {need} of the {len(years)} entry years {years}", len(pos), need,
                    ">=", len(pos) >= need, test="V4", gain_by_entry_year=gain, total_R_changed_by_entry_year=Rv_y,
                    total_R_unchanged_by_entry_year=Rr_y, years_positive=pos,
                    pass_at_synthesis_A_rounding=bool(len(pos_r) >= need), rounding_tie=bool((len(pos) >= need)
                                                                                         != (len(pos_r) >= need))))
    # V5 (FP): the changed sleeve's expectancy and profit factor
    Rv = tv.R.to_numpy(float)
    e, pf = _mean(Rv), _pf(Rv)
    no_loss_win = pf is None and len(Rv) > 0 and (Rv > 0).any() and not (Rv < 0).any()
    ok_e, ok_pf = e is not None and e > 0, (pf is not None and pf >= pf_min) or no_loss_win
    rows.append(row(f"V5 fp/{ex}: the changed sleeve's expectancy per trade > 0", e, 0.0, ">", ok_e, test="V5",
                    n=int(len(Rv)), pass_at_synthesis_A_rounding=bool(e is not None and round(e, 4) > 0),
                    rounding_tie=bool(ok_e != (e is not None and round(e, 4) > 0))))
    ok_pf_r = (pf is not None and round(pf, 3) >= pf_min) or no_loss_win
    rows.append(row(f"V5 fp/{ex}: the changed sleeve's profit factor >= {pf_min}", pf, pf_min, ">=", ok_pf, test="V5",
                    pass_at_synthesis_A_rounding=bool(ok_pf_r), rounding_tie=bool(ok_pf != ok_pf_r)))
    V = {t: all(r["pass"] for r in rows if r["test"] == t) for t in ("V1", "V2", "V3", "V4", "V5")}
    out = verdict(c, rows, readings)
    out["V"] = V
    out["values"] = vals
    out["frozen_factor"] = f
    out["rounding_tie"] = any(r.get("rounding_tie") for r in rows)
    out["same_verdict_at_synthesis_A_rounding"] = bool(all(r["pass_at_synthesis_A_rounding"] for r in rows)
                                                       == out["adopted"])
    cf = res.get("check_first") or {}
    out["check_first_passed"] = bool(cf.get("passed"))
    if not cf.get("passed"):
        out["adopted_if_judged"] = out["adopted"]
        out["adopted"] = None
        out["stopped_by_check_first"] = True
        out["note"] = ("NOT JUDGED: synthesis A's CHECK FIRST failed (res['check_first']): 'otherwise stop and "
                       "report'. The values are shown for the record only.")
    return out


def synthesis_A_block(spec, res, W, verdicts):
    """synthesis A, reported beside the verdicts (deciding nothing alone): '4. ... then the changes that pass,
    together, against the unchanged portfolio' and '6. REPORTED: for the unchanged portfolio, for all five changes and
    for the passing ones, at a constant stake and at equal swing, FP and x1.5: [synthesis A's measures]; every failing
    change is shown too' -- on the plain sum (lab), the equal swing at the FROZEN factors, measured by synthesis A's
    own frozen measures() over the window's weeks. Never raises (an error is recorded)."""
    crit = spec.get("criteria") or {}
    in_look = set(res["changes"]["in_look"])
    ids = [cid for cid, c in crit.items() if cid in in_look and (c or {}).get("kind") == "synthesis_A_change"]
    out = {"changes": ids}                               # in the order of spec["criteria"]
    if not ids:
        return out
    try:
        import vhi_lens as L
        a, b = W["eval"]
        wr = B.week_range(a, b)
        w0, w1 = int(wr[0]), int(wr[-1])
        sA = L.synthesis_A()
        out["measures"] = {"function": "synthesis A portfolio.py measures() (frozen)", "sha256": sA.get("sha256"),
                           "error": sA.get("error"), "weeks": [w0, w1, int(len(wr))]}

        def M(d):
            if sA.get("error"):
                return {"error": sA["error"]}
            try:
                return sA["P"].measures(d, w0, w1, col="Rm")
            except Exception as e:  # noqa: BLE001 -- reported, never raised
                return {"error": repr(e)[:300]}

        sw = {cid: (crit[cid]["replaces"], crit[cid]["sleeve"], float(crit[cid]["frozen_factor"])) for cid in ids}
        judged = {cid: verdicts.get(cid, {}).get("adopted") for cid in ids}
        passing = [cid for cid in ids if judged[cid] is True]
        out.update(passing=passing, failing=[cid for cid in ids if judged[cid] is False],
                   not_judged=[cid for cid in ids if judged[cid] is None],
                   check_first_passed=bool((res.get("check_first") or {}).get("passed")),
                   frozen_factors={cid: sw[cid][2] for cid in ids})
        ex, pn = "lab", "P0"
        rep, head = {}, {}
        for mode in ("fp", "stress"):
            d0 = res["_books"][(pn, mode, ex, "sum")]
            r = {"unchanged": M(d0)}
            for nm, sel in (("all_five", ids), ("passing", passing)):
                for sc in (False, True):
                    k = f"{nm}_{'equal_swing' if sc else 'constant_stake'}"
                    r[k] = M(_swapped(res, d0, [sw[c] for c in sel], mode, ex, W, sc)) if sel else \
                        {"note": "no change passes: the portfolio is the unchanged one"}
            for cid in ids:
                for sc in (False, True):
                    r[f"only_{cid}_{'equal_swing' if sc else 'constant_stake'}"] = M(
                        _swapped(res, d0, [sw[cid]], mode, ex, W, sc))
                rep_k, var_k, _ = sw[cid]
                ref_k = crit[cid]["unchanged"]
                r[f"sleeve_{cid}"] = {
                    "unchanged": M(_mkbook({ref_k: (res["_trades"][(ref_k, "main", mode, ex)], None,
                                                    res["_meta"][ref_k])}, W)),
                    "changed_constant_stake": M(_mkbook({var_k: (res["_trades"][(var_k, "main", mode, ex)], None,
                                                                 res["_meta"][var_k])}, W))}
            rep[mode] = r
            u = r["unchanged"]
            t = r.get("passing_equal_swing", {})
            keys = ("n_trades", "expectancy_R", "euros_per_100_risked", "win_rate", "avg_win_R", "avg_loss_R",
                    "profit_factor", "total_R", "worst_week_R", "max_drawdown_R_trades_exit_order",
                    "max_drawdown_R_weekly", "longest_losing_run_weeks", "losing_weeks_share", "mean_over_sd_per_trade",
                    "weekly_sharpe")
            if passing and "error" not in u and "error" not in t:
                head[mode] = {"passing": passing, "weekly_sharpe_unchanged_vs_together_equal_swing":
                              [u.get("weekly_sharpe"), t.get("weekly_sharpe")],
                              "total_R_unchanged_vs_together_equal_swing": [u.get("total_R"), t.get("total_R")],
                              "deltas_equal_swing": {k: (round(t[k] - u[k], 4) if isinstance(t.get(k), (int, float))
                                                         and isinstance(u.get(k), (int, float)) else None) for k in keys}}
            else:
                head[mode] = {"passing": passing, "note": "no change passes: nothing to put together"
                              if not passing else "measures not available (see 'measures')"}
        out["together_vs_unchanged_headline"] = head
        out["report_item_6"] = rep
    except Exception as e:  # noqa: BLE001 -- the look's output must still be written
        out["error"] = repr(e)[:500]
    return out


def compute(spec, res, W):
    """The verdicts block: one entry per change in the run (res["changes"]["in_look"]). A criterion that raises is
    recorded with its error (adopted = null): the look's output is still written."""
    crit = spec.get("criteria") or {}
    out = {}
    for cid in res["changes"]["in_look"]:
        c = crit.get(cid)
        if c is None:
            out[cid] = {"declared": False, "adopted": None,
                        "note": "no criterion declared for this change: add one to spec['criteria'] before the "
                                "declaration (a kind registered with vhi_verdicts.register_criterion)"}
            continue
        if c["kind"] not in CRITERIA:
            out[cid] = {"declared": True, "kind": c["kind"], "adopted": None, "criteria": [],
                        "error": f"unknown criterion kind {c['kind']!r} (registered: {sorted(CRITERIA)})"}
            continue
        try:
            out[cid] = CRITERIA[c["kind"]](c, res, W)
        except Exception as e:  # noqa: BLE001 -- recorded, the run goes on
            out[cid] = {"declared": True, "kind": c["kind"], "adopted": None, "criteria": [], "error": repr(e)[:500]}
    return out
