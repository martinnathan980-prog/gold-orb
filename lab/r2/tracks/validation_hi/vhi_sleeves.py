"""validation_hi -- one sleeve, one cost mode, one execution: orders -> change -> execution -> refusal -> trades.

A SLEEVE SPEC is a dict:
    key         unique name, e.g. "brk72_24h_wd__ethusd" or "brk72_24h_wd__ethusd+K1"
    rule, sym   the frozen rule (lab/r2/recalc.py::sleeves(), parameters untouched) and the instrument
    convention  "sB"     (synthesis_B / breadth / clock / conviction): 3-spread refusal by iterative re-simulation of
                         the one-position chain; trades still open at the last bar of the frame are dropped
                "payoff" (payoff lens): an order whose stop distance is under 3 spreads of its fill bar is removed
                         before the simulation; censoring of the payoff lens (crypto: 'eod'; others: closed at the
                         last bar by 'time' or 'eod')
    change      None, or one of the CHANGES below (more can be registered with register_change)
    base        (payoff variants) the reference sleeve key it is compared with

CHANGES (kind -> builder; each returns the orders to simulate, the per-order info, and its own diagnostics):
    k1_riskbp   K1 of synthesis_B: skip a brk72 signal when riskbp = 1e4 x stop_dist / P >= T(Y), T refitted every
                1 January on the sleeve's earlier signals (each taken alone in the run's cost mode, decided before
                1 January minus `purge_days`; terciles q; the worse side skipped only if it lost; >= min_train
                signals; history from 31 January of Y-1). A skipped signal never blocks a later one (the chain is
                re-simulated). Code: synthesis_B s1_run.signal_table / fit_fold (imported), the walk-forward
                generalised to any CUT (identical to s1_run.walk_forward at CUT 2022-01-01, checked in the proofs).
    payoff      a payoff-lens variant: family S (k, reentry), T (m), H (j), B (b); code: payoff variants.py
                (imported): info, S, T, H, B, hold_decision, refuse.
    new         nothing: the frozen rule unchanged on an instrument where it is a NEW sleeve (K2, K3)

EXECUTION
    lab   as the rules are specified (the official simulator, goldlab.sim.simulate)
    live  "as the live program would": every order that fills under the lab rules is entered ONE MINUTE LATE AT
          MARKET (market order at the open of the bar after its lab fill bar: ask/bid open x (1 +/- market slippage));
          an absolute stop stays at its price, a stop distance stays a distance from the new fill; time exits,
          trailing and break-even distances unchanged; every position still open is closed at market at the open of
          the first bar starting at or after Friday 16:50 New York of the first Friday on or after its entry's
          New-York date (the hands' InpFridayClose = 23:50 server; if the market is already closed then, at its
          reopen: the hands close "at the first opportunity"); an entry at or after Friday 16:50 New York and before
          the Sunday 17:00 New York reopen is not taken (the hands block new positions then). The 3-spread refusal
          is applied at the live fill bar (a refused order never blocks). The one-position rule keeps the rule's
          own test at the rule's own activation bar (a signal is ignored while the previous trade is open, including
          the minute that trade is closed by its time exit), applied to the LIVE exits: so a trade closed early by
          the Friday close frees the sleeve for the next signal, and a signal at the exit minute stays ignored
          (live_chain; with no delay and no Friday close it reproduces the official chain trade for trade, checked
          in the proofs). A change's decision (K1 skip, payoff transform) is made exactly as in lab.
"""
import time

import numpy as np
import pandas as pd

import vhi_guard as G
import vhi_lens as L
from goldlab import r2
from goldlab.sim import apply_spread_mult, simulate

NY = "America/New_York"
COLS = ["oid", "side", "entry_time", "exit_time", "entry", "exit", "stop", "reason", "mfe", "mae", "swap", "pnl", "risk",
        "R", "hold_min"]
CHANGES = {}


def register_change(kind):
    def deco(fn):
        CHANGES[kind] = fn
        return fn
    return deco


# ------------------------------------------------------------------------------------------------- frames and orders
def mode_frame(m1, mode):
    if mode == "fp":
        return m1
    if mode == "stress":
        return apply_spread_mult(m1, 1.5)
    raise ValueError(mode)


def mode_costs(sym, mode):
    return r2.costs(sym) if mode == "fp" else r2.costs(sym, 1.5)


def build_orders(rule, mk, leader=None):
    """Orders of the frozen rule on frame mk (the cut slice, fp or stressed), oid = row number."""
    L.assert_registry_live()
    _, mo, params = L.registry()["rules"][rule]
    L.clear_rule_caches()
    if rule == "nq_btc_follow":
        if leader is None:
            raise ValueError("nq_btc_follow needs the cut us100 leader")
        L.set_leader(leader)
        last = L.leader_last_minute()
        assert last is not None and last < G.current_cut().value // 60_000_000_000, "leader beyond CUT"
    o = mo(mk, **params).reset_index(drop=True)
    o["oid"] = np.arange(len(o), dtype=np.int64)
    return o


def rule_params(rule):
    _, mo, params = L.registry()["rules"][rule]
    return mo, params


# ------------------------------------------------------------------------------------------------- conventions
def refused_mask_sB(mk, t, min_spreads=3.0):
    return L.synthesis_B()["C"].refused_mask(mk, t, min_spreads)


def simulate_sB(mk, o, sym, costs):
    """synthesis_B's simulate_filtered (imported): iterative 3-spread refusal, one position."""
    return L.synthesis_B()["C"].simulate_filtered(mk, o, sym, costs)


def drop_boundary_sB(t, mk):
    """synthesis_B's drop_boundary generalised to any CUT: trades still open at the last bar of the frame (their exit
    time is at or after that bar's start) have no result inside the frame and are dropped. (synthesis_B's own
    function also filters entry_time < 2022-01-01, which every trade of a frame cut at CUT <= 2022 satisfies.)"""
    if not len(t):
        return t
    return t[t.exit_time < mk.index[-1]]


def censored_payoff(mk, t, sym):
    return L.payoff()["C"].censored(mk, t, sym)


def finish(mk, t, sym, convention):
    """Drop the trades without a result inside the frame, by the convention's rule."""
    n0 = len(t)
    if convention == "sB":
        t = drop_boundary_sB(t, mk)
    elif convention == "payoff":
        if len(t):
            t = t[~censored_payoff(mk, t, sym)]
    else:
        raise ValueError(convention)
    t = t.copy()
    t.attrs["boundary_dropped"] = int(n0 - len(t))
    return t


def fills(mk, o, sym, mode):
    """Fill bar and price of each order exactly as the simulator computes them (payoff common.fills, imported)."""
    return L.payoff()["C"].fills(mk, o, sym, mode == "stress")


def stop_distance_at_fill(o, fp):
    """Initial stop distance each order would have at fill price fp: absolute stop -> |fp - stop|, else stop_dist."""
    st = o["stop"].to_numpy(float) if "stop" in o else np.full(len(o), np.nan)
    sd = o["stop_dist"].to_numpy(float) if "stop_dist" in o else np.full(len(o), np.nan)
    return np.where(np.isfinite(st), np.abs(fp - st), sd)


def pre_refuse(mk, o, sym, mode, min_spreads=3.0):
    """Payoff convention: orders whose stop distance at their (alone) fill is under 3 spreads of the fill bar."""
    fb, fp = fills(mk, o, sym, mode)
    ao, bo = mk["ao"].to_numpy(), mk["bo"].to_numpy()
    j = np.clip(fb, 0, len(mk) - 1)
    spread = np.where(fb >= 0, ao[j] - bo[j], np.nan)
    d0 = stop_distance_at_fill(o, fp)
    return np.isfinite(spread) & (d0 < min_spreads * spread)


# ------------------------------------------------------------------------------------------------- live execution
def friday_close_bar(mk, entry_bar):
    """Index of the first bar starting at or after Friday 16:50 New York of the first Friday on or after the New-York
    date of each entry bar; len(mk) when there is none in the frame. Also: entries at or after that Friday 16:50
    (same day) are flagged (the hands refuse them)."""
    idx = mk.index
    ent = idx[np.clip(entry_bar, 0, len(idx) - 1)].tz_convert(NY)
    dn = ent.tz_localize(None).normalize()
    fri = dn + pd.to_timedelta((4 - dn.dayofweek) % 7, unit="D")
    tc = (fri + pd.Timedelta(hours=16, minutes=50)).tz_localize(NY, ambiguous="NaT", nonexistent="shift_forward")
    tcu = tc.tz_convert("UTC")
    j = np.searchsorted(idx.values, tcu.tz_localize(None).values.astype(idx.values.dtype), side="left")
    local = ent.tz_localize(None)
    blocked = ((local.dayofweek == 4) & ((local.hour * 60 + local.minute) >= 16 * 60 + 50)) | (local.dayofweek == 5) | \
              ((local.dayofweek == 6) & (local.hour < 17))
    return j.astype(np.int64), np.asarray(blocked)


def live_orders(o, mk, sym, mode, late=1):
    """The orders as the live program would send them (see module docstring). Returns (orders, info)."""
    if not len(o):
        return o.copy(), {"orders": 0}
    fb, fp = fills(mk, o, sym, mode)
    N = len(mk)
    ok = (fb >= 0) & (fb + late < N)
    x = o.loc[ok].copy()
    fb = fb[ok]
    eb = (fb + late).astype(np.int64)
    fc, blocked = friday_close_bar(mk, eb)
    keep = ~blocked
    x, eb, fc = x.loc[keep].copy(), eb[keep], fc[keep]
    x["act_i"] = x["entry_i"].to_numpy(np.int64)          # the rule's own activation bar (one-position decision)
    x["entry_i"] = eb
    x["etype"] = 0
    x["level"] = np.nan
    x["expiry_i"] = -1
    if "stop_dist" not in x:
        x["stop_dist"] = np.nan
    if "stop" not in x:
        x["stop"] = np.nan
    xe = x["exit_i"].to_numpy(np.int64) if "exit_i" in x else np.full(len(x), -1, np.int64)
    fcx = np.where(fc < N, fc, -1)
    new_x = np.where(xe < 0, fcx, np.where(fcx < 0, xe, np.minimum(xe, fcx)))
    x["exit_i"] = new_x.astype(np.int64)
    x["friday_close"] = (fcx >= 0) & ((xe < 0) | (fcx < xe))
    info = {"orders_in": int(len(o)), "never_filled_in_lab": int((~ok).sum()), "blocked_friday_window": int(blocked.sum()),
            "orders_out": int(len(x))}
    return x.reset_index(drop=True), info


def live_refuse(mk, x, sym, mode, min_spreads=3.0):
    """Live orders the broker refuses: stop under 3 spreads of the live fill bar, or already crossed at the fill."""
    if not len(x):
        return np.zeros(0, bool)
    fb, fp = fills(mk, x, sym, mode)
    j = np.clip(fb, 0, len(mk) - 1)
    spread = mk["ao"].to_numpy()[j] - mk["bo"].to_numpy()[j]
    st = x["stop"].to_numpy(float)
    side = x["side"].to_numpy()
    stop_px = np.where(np.isfinite(st), st, fp - side * x["stop_dist"].to_numpy(float))
    d0 = np.abs(fp - stop_px)
    crossed = ((side > 0) & (stop_px >= fp)) | ((side < 0) & (stop_px <= fp))
    return (fb >= 0) & ((d0 < min_spreads * spread) | crossed)


def exit_bar(mk, t):
    """Bar index of each trade's exit (time exits: exit_time is the bar start; other exits: start + 1 minute)."""
    return L.payoff()["C"].exit_bar(mk, t)


def live_chain(mk, x, sym, costs):
    """The one-position chain of live orders: every live order simulated alone (the official simulator,
    no_overlap=False), then taken greedily in the order of the RULE's activation bar (`act_i`), an order being ignored
    when the sleeve's previous live trade exits on or after its activation bar -- the lab's own one-position test
    (goldlab.sim._run: i0 <= last_exit), applied to the live exits (one minute late, Friday close)."""
    t = simulate(mk, x, sym=sym, costs=costs, no_overlap=False)
    if not len(t):
        return t
    xb = exit_bar(mk, t)
    act = t["act_i"].to_numpy(np.int64)
    order = np.lexsort((t["oid"].to_numpy(), act))
    keep = np.zeros(len(t), bool)
    last = -1
    for j in order:
        if act[j] <= last:
            continue
        keep[j] = True
        last = xb[j]
    out = t.iloc[np.flatnonzero(keep)].sort_values("entry_time", kind="stable")
    out.attrs.update(t.attrs)
    out.attrs["skipped"] = int((~keep).sum())
    return out


# ------------------------------------------------------------------------------------------------- changes
@register_change("new")
def change_new(spec, mk, O, mode, ctx):
    return O, {}


@register_change("none")
def change_none(spec, mk, O, mode, ctx):
    return O, {}


def _k1_folds(s, cut, q, purge, min_train, first_year=2013):
    """s1_run.walk_forward generalised to any CUT: folds for every year from `first_year` to the year before CUT,
    plus the fit that would be frozen for the year starting at CUT (signals decided before CUT - purge)."""
    S1 = L.synthesis_B()["S1"]
    use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()
    first = s.t_dec.min()
    x = s.riskbp.to_numpy()
    lab = s.label.to_numpy()
    td = s.t_dec
    folds, skip = {}, np.zeros(len(s), bool)
    last_year = (cut - pd.Timedelta(nanoseconds=1)).year
    for y in range(first_year, last_year + 1):
        y0 = pd.Timestamp(f"{y}-01-01", tz="UTC")
        if first > pd.Timestamp(f"{y - 1}-01-31", tz="UTC"):
            continue
        tr = use & (td < y0 - purge).to_numpy()
        if tr.sum() < min_train:
            continue
        f = S1.fit_fold(x[tr], lab[tr], q)
        te = (s.year == y).to_numpy()
        with np.errstate(invalid="ignore"):
            m = np.zeros(len(s), bool) if f["skip"] is None else ((x <= f["q_lo"]) if f["skip"] == "lo" else (x >= f["q_hi"]))
        m &= te
        skip |= m
        f.update(n_test=int(te.sum()), n_skipped=int(m.sum()))
        folds[y] = f
    tr = use & (td < cut - purge).to_numpy()
    f_next = S1.fit_fold(x[tr], lab[tr], q)
    return skip, folds, f_next


@register_change("k1_riskbp")
def change_k1(spec, mk, O, mode, ctx):
    """K1: returns the variant's orders (refused-alone and skipped signals removed). The base chain of the K1
    comparison (refused-alone removed, nothing skipped) is returned in the diagnostics' 'base_orders'."""
    S1 = L.synthesis_B()["S1"]
    ch = spec["change"]
    q = float(ch.get("q", 1 / 3))
    purge = pd.Timedelta(days=float(ch.get("purge_days", 7)))
    min_train = int(ch.get("min_train", 100))
    # the labels of the walk-forward: every signal taken alone in the cost mode `labels_mode` ("run" = the run's own)
    lm = ch.get("labels_mode", "run")
    lab_mode = mode if lm == "run" else lm
    ml = mode_frame(ctx["m1"], lab_mode)
    L.clear_rule_caches()
    o_sig, s = S1.signal_table(ml, spec["sym"], lab_mode)
    assert len(o_sig) == len(O) and (o_sig.entry_i.to_numpy() == O.entry_i.to_numpy()).all() \
        and (o_sig.side.to_numpy() == O.side.to_numpy()).all(), "K1: signal table orders differ from the sleeve's"
    skip, folds, f_next = _k1_folds(s, G.current_cut(), q, purge, min_train)
    s = s.assign(skip=skip)
    refused = set(s.oid[s.refused].tolist())
    skipped = set(s.oid[skip].tolist())
    base_orders = O[~O.oid.isin(refused)]
    var_orders = O[~O.oid.isin(refused | skipped)]
    diag = {"signals": int(len(s)), "refused_alone": int(len(refused)), "skipped": int(len(skipped)),
            "folds": {int(y): {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f.items()} for y, f in folds.items()},
            "folds_full": {int(y): f for y, f in folds.items()},
            "fit_for_year_starting_at_cut": {k: (round(v, 4) if isinstance(v, float) else v) for k, v in f_next.items()},
            "skipped_by_year": {int(y): int(skip[(s.year == y).to_numpy()].sum()) for y in sorted(s.year.unique())},
            "labels_mode": lab_mode}
    dT = ch.get("declared_T")
    if dT:
        cy = G.current_cut().year if G.current_cut() == pd.Timestamp(f"{G.current_cut().year}-01-01", tz="UTC") else None
        chk = {}
        for y, v in dT.items():
            f = folds.get(int(y)) or (f_next if int(y) == cy else None)
            got = None if f is None else f["q_hi"]
            chk[str(y)] = {"declared": float(v), "fitted": got,
                           "fitted_from": "fold" if int(y) in folds else ("fit_for_year_starting_at_cut" if got is not None else None),
                           "same_to_0.01bp": bool(got is not None and abs(got - float(v)) < 0.01)}
        diag["declared_T_check"] = chk
    return var_orders, {"diag": diag, "base_orders": base_orders, "signals": s}


@register_change("payoff")
def change_payoff(spec, mk, O, mode, ctx):
    """A payoff-lens variant (variants.py, imported). Returns the transformed orders that are TAKEN (reentry subset,
    3-spread pre-refusal at the lab fill) and the variant's diagnostics."""
    P = L.payoff()
    V = P["V"]
    ch = spec["change"]
    rule, sym = spec["rule"], spec["sym"]
    mo, params = rule_params(rule)
    stress = mode == "stress"
    I = V.info(rule, sym, mk, O, stress, params, mo)
    fam = ch["family"]
    diag = {}
    if fam == "S":
        o, d0 = V.S(O, I, rule, float(ch["k"]))
    elif fam == "T":
        o, d0 = V.T(O, I, rule, float(ch["m"]))
    elif fam == "B":
        o, d0 = V.B(O, I, rule, float(ch["b"]))
    elif fam == "H":
        ahead = V.hold_decision(mk, O, I, sym, stress)
        o, d0 = V.H(O, I, rule, int(ch["j"]), ahead)
    else:
        raise ValueError(fam)
    sub = np.ones(len(o), bool)
    if fam == "S" and ch.get("reentry") is False:
        tref = P["C"].sim(mk, O, sym, stress)
        sub = O["oid"].isin(tref["oid"]).to_numpy()
    ref_ = V.refuse(d0, I["spread"].to_numpy())
    taken = sub & ~ref_
    diag.update(orders=int(sub.sum()), refused_orders=int((sub & ref_).sum()))
    extra = {"diag": diag}
    if fam == "H":
        diag["extended_orders"] = int((ahead & sub).sum())
        extra["ahead_oids"] = set(O["oid"].to_numpy()[ahead].tolist())
    return o[taken], extra


# ------------------------------------------------------------------------------------------------- the run
def run(spec, m1, mode, exec_mode="lab", leader=None, every_signal=False, keep_signals=False,
        live_one_position="rule"):
    """Trades of one sleeve spec in one cost mode ('fp' | 'stress') and one execution ('lab' | 'live').
    live_one_position: 'rule' (default: the rule's own one-position test at its activation bar, live_chain) or
    'entry_bar' (the official simulator on the delayed orders: the test moves to the delayed entry bar, so a signal
    arriving in the minute the previous trade is closed by its time exit is taken; the synthesis_B verifiers' way).
    Returns (trades, info). trades carry COLS (oid = row of the rule's own order table)."""
    t0 = time.time()
    sym, rule, conv = spec["sym"], spec["rule"], spec.get("convention", "sB")
    mk = mode_frame(m1, mode)
    costs = mode_costs(sym, mode)
    O = build_orders(rule, mk, leader)
    ch = spec.get("change") or {"kind": "none"}
    ctx = {"m1": m1}
    o, extra = CHANGES[ch["kind"]](spec, mk, O, mode, ctx)
    info = {"orders": int(len(O)), "change": ch.get("kind"), "convention": conv, "exec": exec_mode}
    if extra.get("diag"):
        info["change_diag"] = extra["diag"]
    chains = {"main": o}
    if "base_orders" in extra:
        chains["base"] = extra["base_orders"]
    out = {}
    for nm, oo in chains.items():
        li = None
        if exec_mode == "live":
            oo, li = live_orders(oo, mk, sym, mode)
            bad = live_refuse(mk, oo, sym, mode)         # both conventions: refused at the live fill, never blocks
            nref = int(bad.sum())
            if live_one_position == "rule":
                t = live_chain(mk, oo[~bad], sym, costs)
            elif live_one_position == "entry_bar":
                t = simulate(mk, oo[~bad], sym=sym, costs=costs, no_overlap=True)
            else:
                raise ValueError(live_one_position)
        elif exec_mode != "lab":
            raise ValueError(exec_mode)
        elif conv == "sB":
            t = simulate_sB(mk, oo, sym, costs)
            nref = int(t.attrs.get("refused_3spreads", 0))
        else:
            nref = 0                                     # the payoff change made its refusal before (lab fill)
            t = simulate(mk, oo, sym=sym, costs=costs, no_overlap=True)
        t = finish(mk, t, sym, conv)
        cols = [c for c in COLS if c in t.columns]
        extra_cols = [c for c in ("friday_close",) if c in t.columns]
        tt = t[cols + extra_cols].reset_index(drop=True)
        tt.attrs = {"refused_3spreads": nref, "boundary_dropped": t.attrs.get("boundary_dropped", 0)}
        out[nm] = tt
        if nm == "main" and "ahead_oids" in extra:
            info["change_diag"]["extended_trades"] = int(np.isin(tt["oid"].to_numpy(), list(extra["ahead_oids"])).sum())
        info[f"{nm}_refused_3spreads"] = nref
        info[f"{nm}_boundary_dropped"] = int(t.attrs.get("boundary_dropped", 0))
        if li is not None:
            info[f"{nm}_live"] = li
    if every_signal:
        oo = o
        if exec_mode == "live":
            oo, _ = live_orders(oo, mk, sym, mode)
            bad = live_refuse(mk, oo, sym, mode)
        else:
            bad = pre_refuse(mk, oo, sym, mode)
        te = simulate(mk, oo[~bad], sym=sym, costs=costs, no_overlap=False)
        te = finish(mk, te, sym, conv)
        out["every_signal"] = te[[c for c in COLS if c in te.columns]].reset_index(drop=True)
    if keep_signals and "signals" in extra:
        out["signals"] = extra["signals"]
    info["sec"] = round(time.time() - t0, 1)
    return out, info
