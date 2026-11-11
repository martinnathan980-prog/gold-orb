"""Track `pyramid` (PROTOCOL_V3, draft Addendum F): adding to a winning trade. Engine.

THE QUESTION (the user's): "when a trade is winning and the market takes a big direction, for example on gold,
should we add trades each time it wins, to blow up the gain?"  The honest prior: it is a choice of SIZE, not an
edge. It is worth it only if a unit added after the trade is already +k R in profit earns more per unit of risk
than simply risking more from the start.

DEFINITIONS (fixed by the lead; nothing is added to the grid)
    parent    a trade of one of the ten rules exactly as the lab simulates it (goldlab.sim.simulate through
              goldlab.r2.run, FP Markets costs, one position per rule). Never modified by its add-ons.
    R         the parent's initial risk |entry - initial stop|.
    reach     the parent "reaches +kR" at the first one-minute bar that it survives whose favourable extreme on
              the side where the parent would be CLOSED (bid high for a long, ask low for a short) is beyond
              entry +/- k x R. The bar where the parent is stopped does not count (the order inside a bar is
              unknown; the simulator itself does not count it in the trade's best excursion).
    add-on    opened at the OPEN of the NEXT bar (market: ask for a long, bid for a short, plus the simulator's
              market slippage), in the parent's direction. No add-on if the parent has already left, or leaves on
              that bar's open (time exit, or the open is beyond the stop), or if the add-on's entry is not on the
              right side of the stop. It is closed at the same moment and price as the parent.
              Its stop at entry = the parent's stop in force at that moment (the simulator's trailing and
              break-even logic is replayed bar by bar: `_replay`, which must reproduce every parent's exit).
              Its own risk = |add-on entry - that stop|.
    costs     spread: in the quotes. Slippage: the simulator's market slippage on the entry, the parent's exit
              price (slippage included) on the exit. Swap: the simulator's formula on the add-on's own holding
              period. Commission: the same Costs object as the parent (r2.costs: zero, it is in the quotes).
    grid      thresholds k in {1, 2}; at most n add-ons per parent, n in {1, 2} (the second at +2k R); add-ons
              never trigger add-ons.
              F1 "fixed risk": each add-on risks f base stakes at ITS OWN stop, f in {0.5, 1}.
              F2 "free risk" : each add-on is sized so that, if the stop in force is hit right after the add, the
                               parent plus all its add-ons lose at most 1 base stake together:
                               stake = max(0, 1 - loss of the units already open at that stop), in base stakes at
                               the add-on's own risk (loss measured at the stop PRICE, slippage not counted).
                               With a stop that never moves the budget is exactly zero: F2 adds only where the
                               stop trails (one rule of the ten: donch4h_stop on gold).
              scope "all" = add-ons on the ten rules; "trend" = add-ons only on the rules whose parent uses a
              trailing stop or holds more than one day on average (rule stated before any add-on result:
              `trail` present in the rule's orders, or mean hold of the in-sample trades > 1,440 minutes).
              => F1: 2 k x 2 n x 2 f = 8, F2: 2 k x 2 n = 4, on 2 scopes = 24 configurations (CONFIGS).

ACCOUNTING (the stake study's: r2/tracks/stake/stake.py, same clock, same functions)
    Base stake = 1 = 1 % of the account risked at the stop; no compounding; a result is booked in the server day /
    week / month of its EXIT (server time = New York + 7 h). The reference is the ten rules at 1 stake each. A
    configuration = the same parents at 1 stake + its add-ons at their stake. Results WITH costs. Common in-sample
    period: parents entered from 2018-02-01 to 2021-12-31 (stake.COMMON_START / stake.IS_END).
    Maximum drawdown: on the results cumulated trade by trade in exit order (stake.stats). A parent and its
    add-ons leave at the same instant; the parent is booked first.
    "Profit at equal drawdown" = total x (reference maximum drawdown / configuration maximum drawdown).

SELECTION RULE (declared here BEFORE the 24 configurations were run; see results/r2/pyramid/run_log.jsonl)
    The finalist is the configuration with the highest profit at equal drawdown among those that satisfy ALL of:
    (a) pooled add-on expectancy per unit of its own risk > 0 with t >= 2.5: mean of the R of every add-on the
        configuration really opens (stake > 0) in the common period, t-statistic clustered by server day of exit;
    (b) profit at equal drawdown >= 1.15 x the reference's total;
    (c) worst week at equal drawdown <= 1.25 x the reference's worst week (absolute values);
    (d) the add-ons alone (their booked results in stakes) are positive in at least 3 of the 4 in-sample years of
        the common period (2018 from February, 2019, 2020, 2021; year of the exit on the server clock; results
        booked in the first days of January 2022 by trades entered in December 2021 are added to 2021);
    (e) the zero-edge control shows no gain in profit at equal drawdown. A zero-edge reference has a total near
        zero, so the RATIO of (b) is undefined there; the control is read on the DIFFERENCE
            G = (configuration total x reference drawdown / configuration drawdown) - reference total
        computed inside each draw, and reported as "1 + mean(G) / real reference total" so that it reads like
        the ratio of (b). The criterion fails only if the 95 % confidence interval of that figure (mean over 200
        draws +/- 1.96 standard errors) lies entirely above 1.
    Tie: the configuration with fewer add-ons. If none qualifies the finalist is NONE.

IN SAMPLE ONLY in research (`build(end=IS_END, price_end="2022-01-01")`): every trades file is cut at
entry_time < 2022-01-01 on the line after it is read and prices are loaded with r2.load(sym, end="2022-01-01").
The only caller allowed to pass another window is val.py in `val` mode (the lead, once).
"""
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd
from numba import njit

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
for _p in (LAB, os.path.join(LAB, "r2", "tracks", "stake")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from goldlab import r2  # noqa: E402
from goldlab.data import NY, trading_day  # noqa: E402
import stake as S  # noqa: E402

OUT = os.path.join(LAB, "results", "r2", "pyramid")
IS_END = S.IS_END
COMMON_START = S.COMMON_START
LEVELS_DESC = (0.5, 1.0, 1.5, 2.0, 3.0)            # descriptive table only
LEVELS = (0.5, 1.0, 1.5, 2.0, 3.0, 4.0)            # every level replayed (the grid uses 1, 2 and 4)
GRID_LEVELS = (1.0, 2.0, 4.0)
SYM_ORDER = ("us100", "xauusd", "btcusd", "ethusd")
STOP, TARGET, TIME, TRAIL, EOD, GAP = 0, 1, 2, 3, 4, 7
REASON_CODE = {"stop": 0, "target": 1, "time": 2, "trail": 3, "eod": 4, "gap": 7}
EPS = 1e-9


def _c(fam, k, n, f, scope):
    name = f"{fam}_k{k:g}_n{n}" + (f"_f{f:g}" if fam == "F1" else "") + f"_{scope}"
    return name, dict(fam=fam, k=float(k), n=int(n), f=None if f is None else float(f), scope=scope)


# The declared grid, in the order it is run (append-only: it is the trial log).
CONFIGS = [_c("F1", k, n, f, scope) for scope in ("all", "trend") for k in (1, 2) for n in (1, 2) for f in (0.5, 1)] + \
          [_c("F2", k, n, None, scope) for scope in ("all", "trend") for k in (1, 2) for n in (1, 2)]
assert len(CONFIGS) == 24 and len({c[0] for c in CONFIGS}) == 24


def log(step, **kw):
    """Append one line to the run log (the order of the runs is part of the evidence)."""
    import datetime as dt
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "run_log.jsonl"), "a") as fh:
        fh.write(json.dumps({"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "step": step, **kw},
                            default=str) + "\n")


# ------------------------------------------------------------------ the ten rules
def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


_defs = {}


def sleeve_defs():
    """{(name, sym): (make_orders, params)} for the ten rules, from r2/recalc.py::sleeves() (not edited)."""
    if not _defs:
        recalc = sys.modules.get("r2_recalc") or _load_module(os.path.join(LAB, "r2", "recalc.py"), "r2_recalc")
        for track, name, sym, mo, params in recalc.sleeves():
            if (name, sym) in S.SLEEVES:
                _defs[(name, sym)] = (mo, params)
        assert set(_defs) == set(S.SLEEVES)
    return _defs


def set_leader(price_end):
    """nq_btc_follow reads the us100 closes by itself (whole research file). When the prices are cut
    (price_end given), the leader is registered cut at the same date, so that nothing later is ever loaded."""
    sleeve_defs()
    ll = sys.modules["r2_leadlag_strategy"]
    ll.clear_leaders()
    if price_end is not None:
        df = r2.load("us100", end=price_end)
        ll.set_leader("us100", df[["bo", "ao", "bc", "ac"]])
        r2.free()


# ------------------------------------------------------------------ replay of the simulator, with the add-on points
@njit(cache=True)
def _replay(bo, bh, bl, bc, ao, ah, al, ac, fi, fp, st, tg, xe, trail, be, side, et, lvl, slip, slip_m, levels,
            x_i, x_px, reason, trig_i, add_i, add_px, add_stop):
    """goldlab.sim._run from the fill onward (same statements, same order), for parents whose fill bar `fi`, fill
    price `fp` and initial stop `st` are known. In addition, for each level L of `levels`:
        trig_i  the first bar the parent survives whose favourable extreme reaches fp +/- L x |fp - st|
        add_i   trig_i + 1 when the add-on is really opened there (-1 otherwise), add_px its fill price,
                add_stop the parent's stop in force at that open.
    Nothing decided for the bar add_i uses anything later than the close of bar add_i - 1, except the open of
    add_i itself (the fill, and whether the parent leaves on that open)."""
    N = len(bo)
    nl = len(levels)
    for k in range(len(fi)):
        s = side[k]
        f = fi[k]
        p = fp[k]
        cur = st[k]
        if (s > 0 and cur >= p) or (s < 0 and cur <= p):
            x_i[k] = f
            x_px[k] = bo[f] * (1 - slip) if s > 0 else ao[f] * (1 + slip)
            reason[k] = GAP
            continue
        R = abs(p - cur)
        tgk = tg[k]
        best = p
        moved = False
        done = False
        pending = False
        xek = xe[k]
        i = f
        while i < N:
            if xek >= 0 and i >= xek and i > f:
                x_i[k] = i
                x_px[k] = bo[i] * (1 - slip_m) if s > 0 else ao[i] * (1 + slip_m)
                reason[k] = TIME
                done = True
                break
            if pending:
                # add-ons decided at the close of bar i-1: opened at this open unless the parent leaves on it
                if s > 0:
                    out_at_open = bo[i] <= cur or ((not np.isnan(tgk)) and bo[i] >= tgk)
                    px = ao[i] * (1 + slip_m)
                    right_side = px > cur
                else:
                    out_at_open = ao[i] >= cur or ((not np.isnan(tgk)) and ao[i] <= tgk)
                    px = bo[i] * (1 - slip_m)
                    right_side = px < cur
                if (not out_at_open) and right_side:
                    for j in range(nl):
                        if trig_i[k, j] == i - 1:
                            add_i[k, j] = i
                            add_px[k, j] = px
                            add_stop[k, j] = cur
                pending = False
            first = i == f
            if s > 0:
                hit_stop = bl[i] <= cur
                hit_tgt = (not np.isnan(tgk)) and bh[i] >= tgk
                if first and et[k] == 1 and hit_tgt and not (ao[i] < lvl[k]):
                    hit_tgt = False
                if first and et[k] == 2:
                    hit_tgt = False
                if hit_stop:
                    px = cur if first else min(cur, bo[i])
                    x_i[k] = i
                    x_px[k] = px * (1 - slip)
                    reason[k] = TRAIL if moved else STOP
                    done = True
                    break
                if hit_tgt:
                    x_i[k] = i
                    x_px[k] = tgk if first else max(tgk, bo[i])
                    reason[k] = TARGET
                    done = True
                    break
                if bh[i] > best:
                    best = bh[i]
                if not np.isnan(trail[k]) and best - trail[k] > cur:
                    cur = best - trail[k]
                    moved = True
                if not np.isnan(be[k]) and best - p >= be[k] and p > cur:
                    cur = p
                    moved = True
                for j in range(nl):
                    if trig_i[k, j] < 0 and bh[i] >= p + levels[j] * R:
                        trig_i[k, j] = i
                        pending = True
            else:
                hit_stop = ah[i] >= cur
                hit_tgt = (not np.isnan(tgk)) and al[i] <= tgk
                if first and et[k] == 1 and hit_tgt and not (bo[i] > lvl[k]):
                    hit_tgt = False
                if first and et[k] == 2:
                    hit_tgt = False
                if hit_stop:
                    px = cur if first else max(cur, ao[i])
                    x_i[k] = i
                    x_px[k] = px * (1 + slip)
                    reason[k] = TRAIL if moved else STOP
                    done = True
                    break
                if hit_tgt:
                    x_i[k] = i
                    x_px[k] = tgk if first else min(tgk, ao[i])
                    reason[k] = TARGET
                    done = True
                    break
                if al[i] < best:
                    best = al[i]
                if not np.isnan(trail[k]) and best + trail[k] < cur:
                    cur = best + trail[k]
                    moved = True
                if not np.isnan(be[k]) and p - best >= be[k] and p < cur:
                    cur = p
                    moved = True
                for j in range(nl):
                    if trig_i[k, j] < 0 and al[i] <= p - levels[j] * R:
                        trig_i[k, j] = i
                        pending = True
            i += 1
        if not done:
            x_i[k] = N - 1
            x_px[k] = bc[N - 1] if s > 0 else ac[N - 1]
            reason[k] = EOD


def quotes(m1):
    return tuple(m1[c].to_numpy(np.float64) for c in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"))


def slips(c):
    return c.slip_bps * 1e-4, (c.slip_mkt_bps if c.slip_mkt_bps >= 0 else c.slip_bps) * 1e-4


def order_fields(orders, t):
    """The order parameters of the filled trades `t` (simulate keeps the row label of the order)."""
    o = orders.reset_index(drop=True)
    n = len(t)
    g = lambda c, d: o[c].to_numpy()[t.index.to_numpy()] if c in o else np.full(n, d)
    side = t.side.to_numpy(np.int64)
    fp = t.entry.to_numpy(np.float64)
    tg = np.asarray(g("target", np.nan), np.float64)
    td = np.asarray(g("target_dist", np.nan), np.float64)
    tg = np.where(np.isnan(tg), np.where(np.isnan(td), np.nan, fp + side * td), tg)
    return dict(tg=tg, xe=np.asarray(g("exit_i", -1), np.int64), trail=np.asarray(g("trail", np.nan), np.float64),
                be=np.asarray(g("be", np.nan), np.float64), et=np.asarray(g("etype", 0), np.int64),
                lvl=np.asarray(g("level", np.nan), np.float64))


def replay(m1, q, t, of, c, levels=LEVELS):
    """Replays the filled trades `t` (output of simulate on `m1`). Returns the arrays of `_replay`."""
    idx = m1.index
    n = len(t)
    fi = np.asarray(idx.searchsorted(t.entry_time), np.int64)
    side = t.side.to_numpy(np.int64)
    lv = np.asarray(levels, np.float64)
    x_i = np.full(n, -1, np.int64)
    x_px = np.full(n, np.nan)
    reason = np.full(n, -1, np.int64)
    trig_i = np.full((n, len(lv)), -1, np.int64)
    add_i = np.full((n, len(lv)), -1, np.int64)
    add_px = np.full((n, len(lv)), np.nan)
    add_stop = np.full((n, len(lv)), np.nan)
    slip, slip_m = slips(c)
    _replay(*q, fi, t.entry.to_numpy(np.float64), t.stop.to_numpy(np.float64), of["tg"], of["xe"], of["trail"], of["be"],
            side, of["et"], of["lvl"], slip, slip_m, lv, x_i, x_px, reason, trig_i, add_i, add_px, add_stop)
    return dict(fi=fi, x_i=x_i, x_px=x_px, reason=reason, trig_i=trig_i, add_i=add_i, add_px=add_px, add_stop=add_stop)


def swap_of(entry_time, exit_time, entry, side, c):
    """goldlab.sim.simulate's swap, statement for statement."""
    d0 = trading_day(entry_time).values.astype("datetime64[D]")
    d1 = trading_day(pd.DatetimeIndex(exit_time) - pd.Timedelta(seconds=1)).values.astype("datetime64[D]")
    nights = np.busday_count(d0, d1) + 2 * np.busday_count(d0, d1, weekmask=c.swap_triple)
    rate = np.where(np.asarray(side) > 0, c.swap_long, c.swap_short)
    return np.asarray(entry) * rate / 360.0 * nights


def addon_table(m1, t, rp, c, levels=LEVELS):
    """One row per add-on really opened. `t` = the parents (rows aligned with the replay `rp`), whose exit_time
    and exit are the ones the add-ons take."""
    idx = m1.index
    rows = []
    side = t.side.to_numpy(np.int64)
    for j, L in enumerate(levels):
        k = np.nonzero(rp["add_i"][:, j] >= 0)[0]
        if not len(k):
            continue
        et = pd.DatetimeIndex(idx[rp["add_i"][k, j]])
        xt = pd.DatetimeIndex(t.exit_time.iloc[k])
        e = rp["add_px"][k, j]
        x = t.exit.to_numpy(float)[k]
        sw = swap_of(et, xt, e, side[k], c)
        pnl = side[k] * (x - e) - sw - c.commission
        risk = np.abs(e - rp["add_stop"][k, j])
        rows.append(pd.DataFrame({
            "prow": k, "level": L, "side": side[k], "entry_time": et, "exit_time": xt, "entry": e, "exit": x,
            "stop": rp["add_stop"][k, j], "add_i": rp["add_i"][k, j], "swap": sw, "pnl": pnl, "risk": risk,
            "R": pnl / risk, "bps": pnl / e * 1e4,
            "p_entry": t.entry.to_numpy(float)[k], "p_risk": t.risk.to_numpy(float)[k], "p_R": t.R.to_numpy(float)[k]}))
    if not rows:
        return pd.DataFrame(columns=["prow", "level", "side", "entry_time", "exit_time", "entry", "exit", "stop", "add_i",
                                     "swap", "pnl", "risk", "R", "bps", "p_entry", "p_risk", "p_R"])
    return pd.concat(rows, ignore_index=True)


# ------------------------------------------------------------------ build: parents + add-ons of the ten rules
def stored_trades(name, sym, start, end):
    """The lab's saved trades of one rule, cut to the window on the line after the read."""
    t = pd.read_parquet(os.path.join(S.NET_DIR, f"{name}__{sym}.parquet"))
    t = t[(t.entry_time < end) & (t.entry_time >= (start if start is not None else pd.Timestamp("1900-01-01", tz="UTC")))]
    return t.reset_index(drop=True)


def simulate_rule(sym, m1, name):
    """Parents of one rule on `m1`, through goldlab.r2.run (FP costs, one position per rule), with their orders."""
    mo, params = sleeve_defs()[(name, sym)]
    box = {}

    def keep(m, **p):
        box["o"] = mo(m, **p)
        return box["o"]

    t = r2.run(sym, keep, params, "fp", True, m1)
    return t, box["o"]


def build(start=None, end=IS_END, price_end="2022-01-01", levels=LEVELS, checks=True, hook=None):
    """Parents and add-ons of the ten rules for parents entered in [start, end), prices cut at `price_end`.

    Returns (parents, addons, report):
      parents  one row per parent: the SAVED trade (results/r2/recalc/trades) + pid, sleeve, sym, fam, `trail`
      addons   one row per add-on really opened, every level of `levels`, linked by pid
      report   the self-checks (replay == simulator == saved trades; add-on re-simulated on its own; prefix test)
    `hook(sym, name, m1, q, parents_of_rule, orders_fields, costs)` is called while the prices of `sym` are loaded
    (used by the zero-edge control)."""
    assert (end <= IS_END and price_end is not None and pd.Timestamp(price_end, tz="UTC") <= IS_END) or \
        os.environ.get("PYRAMID_VAL_LOOK") == "lead", "research is in sample only"
    set_leader(price_end)
    P, A, rep = [], [], {}
    pid0 = 0
    for sym in SYM_ORDER:
        r2.free()
        m1 = r2.load(sym, end=price_end)
        q = quotes(m1)
        c = r2.costs(sym)
        for name, s in S.SLEEVES:
            if s != sym:
                continue
            sv = stored_trades(name, sym, start, end)
            t, orders = simulate_rule(sym, m1, name)
            t = t[(t.entry_time < end) & (t.entry_time >= (start if start is not None else t.entry_time.min()))]
            of = order_fields(orders, t)
            rp = replay(m1, q, t, of, c, levels)
            key = f"{name}__{sym}"
            ck = {"n_saved": int(len(sv)), "n_resimulated": int(len(t))}
            same_set = len(sv) == len(t) and bool((sv.entry_time.to_numpy() == t.entry_time.to_numpy()).all())
            ck["same_entries_as_saved"] = same_set
            assert same_set, key
            # 1. replay == simulator (on the same price frame)
            x_i_sim = np.asarray(m1.index.searchsorted(t.exit_time - pd.Timedelta(minutes=1) * (t.reason != "time").to_numpy()), np.int64)
            rs = t.reason.map(REASON_CODE).to_numpy()
            bad = (rp["x_i"] != x_i_sim) | (rp["x_px"] != t.exit.to_numpy()) | (rp["reason"] != rs)
            ck["replay_vs_simulator_mismatches"] = int(bad.sum())
            # 2. simulator on this frame == saved trades (differences: parents still open when the frame ends)
            d_time = sv.exit_time.to_numpy() != t.exit_time.to_numpy()
            d_px = sv.exit.to_numpy() != t.exit.to_numpy()
            d_reason = sv.reason.to_numpy() != t.reason.to_numpy()
            diff = d_time | d_px | d_reason
            open_at_end = (sv.exit_time > m1.index[-1]).to_numpy() & diff      # the saved exit is after the last bar loaded
            ck["saved_vs_resimulated_mismatches"] = int(diff.sum())
            ck["of_which_open_at_the_end_of_the_price_frame"] = int((diff & open_at_end).sum())
            ck["unexplained_mismatches"] = int((diff & ~open_at_end).sum() + (bad.sum()))
            ck["max_abs_pnl_diff_non_straddlers"] = float(np.abs(sv.pnl.to_numpy() - t.pnl.to_numpy())[~diff].max()) if (~diff).any() else 0.0
            # 3. "reached" as replayed == the simulator's own best excursion
            Rr = t.risk.to_numpy()
            mfe_reach = np.stack([t.mfe.to_numpy() >= L * Rr for L in levels], axis=1)
            edge = np.stack([np.abs(t.mfe.to_numpy() - L * Rr) < 1e-7 * t.entry.to_numpy() for L in levels], axis=1)
            ck["reach_vs_simulator_mfe_mismatches"] = int((((rp["trig_i"] >= 0) != mfe_reach) & ~edge).sum())
            ck["swap_formula_max_abs_diff"] = float(np.abs(swap_of(pd.DatetimeIndex(t.entry_time), pd.DatetimeIndex(t.exit_time),
                                                                    t.entry.to_numpy(), t.side.to_numpy(), c) - t.swap.to_numpy()).max())
            # the parents the study uses = the saved trades (the stake study's), with the replayed order fields
            par = sv.copy()
            par["sleeve"], par["sym"], par["fam"], par["name"] = f"{name}_{sym}", sym, S.FAMILY[sym], name
            par["pid"] = np.arange(pid0, pid0 + len(par))
            par["trail"] = of["trail"]
            par["stop_moves"] = ~np.isnan(of["trail"]) | ~np.isnan(of["be"])
            for j, L in enumerate(levels):
                par[f"reach_{L:g}"] = rp["trig_i"][:, j] >= 0
            pid0 += len(par)
            ad = addon_table(m1, par, rp, c, levels)
            ad["pid"] = par.pid.to_numpy()[ad.prow.to_numpy()] if len(ad) else []
            ad["sleeve"], ad["sym"], ad["fam"], ad["name"] = f"{name}_{sym}", sym, S.FAMILY[sym], name
            ck["addons_opened"] = {f"{L:g}": int((ad.level == L).sum()) for L in levels}
            ck["addons_on_parents_open_at_the_end_of_the_frame"] = int(open_at_end[ad.prow.to_numpy()].sum()) if len(ad) else 0
            if checks and len(ad):
                ck.update(check_addons(m1, q, t, of, rp, ad, c, levels, open_at_end))
            rep[key] = ck
            P.append(par)
            A.append(ad)
            if hook is not None:
                hook(sym, name, m1, q, par, of, c)
        r2.free()
    parents = pd.concat(P, ignore_index=True)
    addons = pd.concat(A, ignore_index=True)
    return parents, addons, rep


def check_addons(m1, q, t, of, rp, ad, c, levels, open_at_end):
    """Two independent checks of the add-ons of one rule.
    (1) each add-on re-simulated ON ITS OWN by the lab's simulator: market order at its bar, absolute stop = the
        stop in force, the parent's trailing distance and time exit. It must fill at the same price and leave at
        the same time and price as the parent.
    (2) prefix test: the replay is run again on prices that stop at the add-on's bar, of which only the OPEN is
        kept (high / low / close replaced by the open): the add-on must come out identical."""
    from goldlab.sim import simulate
    out = {}
    k = ad.prow.to_numpy()
    o = pd.DataFrame({"entry_i": ad.add_i.to_numpy(np.int64), "side": ad.side.to_numpy(np.int64), "etype": 0,
                      "stop": ad["stop"].to_numpy(float), "exit_i": of["xe"][k], "trail": of["trail"][k]})
    ts = simulate(m1, o, sym="x", costs=c, no_overlap=False)
    assert len(ts) == len(ad)
    ts = ts.loc[np.arange(len(ad))]
    live = ~open_at_end[k]
    same_fill = ts.entry.to_numpy() == ad.entry.to_numpy()
    same_exit = (ts.exit_time.to_numpy() == t.exit_time.to_numpy()[k]) & (ts.exit.to_numpy() == t.exit.to_numpy()[k])
    out["addon_resimulated_alone_fill_mismatches"] = int((~same_fill).sum())
    out["addon_resimulated_alone_exit_mismatches"] = int((~same_exit & live).sum())
    out["addon_resimulated_alone_max_abs_pnl_diff"] = float(np.abs(ts.pnl.to_numpy() - ad.pnl.to_numpy())[live & same_exit].max()) if (live & same_exit).any() else 0.0
    out["addon_exit_equals_parent_exit"] = bool((ad.exit_time.to_numpy() == t.exit_time.to_numpy()[k])[live].all()
                                                and (ad.exit.to_numpy() == t.exit.to_numpy()[k])[live].all())
    # prefix test, every add-on
    lv = np.asarray(levels, np.float64)
    slip, slip_m = slips(c)
    bad = 0
    fi = rp["fi"]
    jl = {L: j for j, L in enumerate(levels)}
    t_entry, t_stop, t_side = t.entry.to_numpy(np.float64), t.stop.to_numpy(np.float64), t.side.to_numpy(np.int64)
    ad_level, ad_i, ad_entry, ad_stop = ad.level.to_numpy(), ad.add_i.to_numpy(), ad.entry.to_numpy(), ad["stop"].to_numpy()
    for r in range(len(ad)):
        p = k[r]
        j = jl[ad_level[r]]
        a0, a1 = fi[p], int(ad_i[r])
        qq = [x[a0:a1 + 1].copy() for x in q]
        for z in (1, 2, 3):
            qq[z][-1] = qq[0][-1]                       # bid high / low / close of the add bar := its open
        for z in (5, 6, 7):
            qq[z][-1] = qq[4][-1]
        x_i, x_px, reason = np.full(1, -1, np.int64), np.full(1, np.nan), np.full(1, -1, np.int64)
        tr, ai = np.full((1, len(lv)), -1, np.int64), np.full((1, len(lv)), -1, np.int64)
        ap, as_ = np.full((1, len(lv)), np.nan), np.full((1, len(lv)), np.nan)
        xe = of["xe"][p:p + 1] - a0 if of["xe"][p] >= 0 else of["xe"][p:p + 1]
        _replay(*qq, np.zeros(1, np.int64), t_entry[p:p + 1], t_stop[p:p + 1],
                of["tg"][p:p + 1], np.asarray(xe, np.int64), of["trail"][p:p + 1], of["be"][p:p + 1],
                t_side[p:p + 1], of["et"][p:p + 1], of["lvl"][p:p + 1], slip, slip_m, lv,
                x_i, x_px, reason, tr, ai, ap, as_)
        if not (ai[0, j] + a0 == a1 and ap[0, j] == ad_entry[r] and as_[0, j] == ad_stop[r]):
            bad += 1
    out["prefix_test_addons_checked"] = int(len(ad))
    out["prefix_test_mismatches"] = int(bad)
    return out


# ------------------------------------------------------------------ descriptive statistics
def server_day(ts):
    return S.server_time(ts).normalize()


def cluster_t(x, groups):
    """t-statistic of the mean of x, clustered by `groups` (sum of the deviations per cluster)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return float("nan")
    mu = x.mean()
    s = pd.Series(x - mu).groupby(np.asarray(groups)).sum().to_numpy()
    G = len(s)
    if G < 3:
        return float("nan")
    se = np.sqrt((s ** 2).sum() * G / (G - 1)) / n
    return float(mu / se) if se > 0 else float("nan")


def describe(parents, addons, levels=LEVELS_DESC):
    """Per rule, per family and for the ten rules pooled: what is left of a trade after +kR, against a fresh trade."""
    r = lambda v, d=4: None if v is None or not np.isfinite(v) else round(float(v), d)
    groups = [(s, parents.sleeve == s, addons.sleeve == s) for s in [f"{n}_{y}" for n, y in S.SLEEVES]]
    groups += [(f"FAMILY {S.FAM_NAMES[f]}", parents.fam == f, addons.fam == f) for f in (0, 1, 2)]
    groups += [("ALL TEN", parents.fam >= 0, addons.fam >= 0)]
    out = {}
    for label, pm, am in groups:
        p = parents[pm]
        pday = server_day(p.exit_time)
        base = {"parents": int(len(p)), "parent_mean_R": r(p.R.mean()), "parent_t_by_day": r(cluster_t(p.R, pday), 2),
                "parent_mean_bps": r((p.pnl / p.entry).mean() * 1e4, 2), "parent_share_positive": r((p.R > 0).mean(), 3),
                "parent_mean_hold_h": r(p.hold_min.mean() / 60, 1), "levels": {}}
        for L in levels:
            a = addons[am & (addons.level == L)]
            d = {"share_reaching": r(p[f"reach_{L:g}"].mean(), 4), "addons": int(len(a))}
            if len(a):
                d.update({"addon_mean_R": r(a.R.mean()), "addon_median_R": r(a.R.median()), "addon_share_positive": r((a.R > 0).mean(), 3),
                          "addon_t_by_day": r(cluster_t(a.R, server_day(a.exit_time)), 2), "addon_mean_bps": r(a.bps.mean(), 2),
                          "addon_sum_R": r(a.R.sum(), 1),
                          "addon_mean_risk_in_parent_R": r((a.risk / a.p_risk).mean(), 3),
                          "parents_that_reached_mean_R": r(p.R[p[f"reach_{L:g}"]].mean()),
                          "parents_that_did_not_reach_mean_R": r(p.R[~p[f"reach_{L:g}"]].mean())})
            base["levels"][f"{L:g}"] = d
        out[label] = base
    return out


# ------------------------------------------------------------------ portfolio accounting (in base stakes)
TREND_RULE = "trailing stop in the rule's orders, or mean hold of the parents > 1,440 minutes"
# Frozen from the in-sample parents (2013-2021) by TREND_RULE, before any add-on result (run.py asserts it):
# donch4h_stop is the only rule with a trailing stop (mean hold 39 h); orb_asia_2d_buf10 holds 42 h on average.
TREND = ("donch4h_stop_xauusd", "orb_asia_2d_buf10_xauusd")


def trend_sleeves(parents):
    """Scope `trend`, by TREND_RULE, from the parents only."""
    g = parents.groupby("sleeve").agg(trail=("trail", lambda v: bool(v.notna().any())), hold=("hold_min", "mean"))
    return sorted(g.index[(g.trail) | (g.hold > 1440.0)]), {k: {"trailing_stop": bool(v.trail), "mean_hold_h": round(float(v.hold) / 60, 1)}
                                                            for k, v in g.iterrows()}


REFERENCE = dict(fam="F1", k=-1.0, n=1, f=0.0, scope="all")      # no add-on at all: the ten rules at 1 stake


def portfolio_frame(parents, addons):
    """One frame: the parents (as stake.build_frame builds them) + the add-ons of the grid levels, in the stake
    study's order for the parents (entry time, then rule). At the same minute: new trades first, then add-ons
    (by rule name, then the lower threshold first). A parent always comes before its own add-ons."""
    cols = ["sleeve", "sym", "fam", "t_in", "t_out", "entry", "risk", "pnl", "R"]
    p = pd.DataFrame({"sleeve": parents.sleeve, "sym": parents.sym, "fam": parents.fam,
                      "t_in": pd.to_datetime(parents.entry_time, utc=True).astype("datetime64[ns, UTC]"),
                      "t_out": pd.to_datetime(parents.exit_time, utc=True).astype("datetime64[ns, UTC]"),
                      "entry": parents.entry.astype(float), "risk": parents.risk.astype(float), "pnl": parents.pnl.astype(float),
                      "R": parents.R.astype(float)})[cols]
    p["is_add"], p["level"], p["pid"], p["side"] = 0, 0.0, parents.pid.to_numpy(), parents.side.to_numpy()
    p["stop"], p["p_entry"], p["p_risk"] = parents["stop"].to_numpy(float), parents.entry.to_numpy(float), parents.risk.to_numpy(float)
    a = addons[addons.level.isin(GRID_LEVELS)]
    q = pd.DataFrame({"sleeve": a.sleeve, "sym": a.sym, "fam": a.fam,
                      "t_in": pd.to_datetime(a.entry_time, utc=True).astype("datetime64[ns, UTC]"),
                      "t_out": pd.to_datetime(a.exit_time, utc=True).astype("datetime64[ns, UTC]"),
                      "entry": a.entry.astype(float), "risk": a.risk.astype(float), "pnl": a.pnl.astype(float), "R": a.R.astype(float)})[cols]
    q["is_add"], q["level"], q["pid"], q["side"] = 1, a.level.to_numpy(float), a.pid.to_numpy(), a.side.to_numpy()
    q["stop"], q["p_entry"], q["p_risk"] = a["stop"].to_numpy(float), a.p_entry.to_numpy(float), a.p_risk.to_numpy(float)
    d = pd.concat([p, q], ignore_index=True)
    return d.sort_values(["t_in", "is_add", "sleeve", "level"], kind="stable").reset_index(drop=True)


def stakes(fr, cfg, trend):
    """Stake of every row of the frame under one configuration (parents 1, add-ons per the family; 0 = not opened)."""
    m = np.where(fr.is_add.to_numpy() == 0, 1.0, 0.0)
    k, n = cfg["k"], cfg["n"]
    add = fr.is_add.to_numpy() == 1
    if cfg["scope"] == "trend":
        add &= fr.sleeve.isin(trend).to_numpy()
    lev = fr.level.to_numpy()
    a1 = add & (lev == k)
    a2 = add & (lev == 2 * k) & (n == 2)
    if cfg["fam"] == "F1":
        m[a1 | a2] = cfg["f"]
        return m
    side, pe, pr = fr.side.to_numpy(float), fr.p_entry.to_numpy(float), fr.p_risk.to_numpy(float)
    e, st, rk = fr.entry.to_numpy(float), fr["stop"].to_numpy(float), fr.risk.to_numpy(float)
    b1 = np.zeros(len(fr))
    b1[a1] = np.maximum(0.0, 1.0 - side[a1] * (pe[a1] - st[a1]) / pr[a1])
    b1[b1 <= EPS] = 0.0
    m[a1] = b1[a1]
    if n == 2 and a2.any():
        first = pd.DataFrame({"u": b1[a1] / rk[a1], "e": e[a1]}, index=fr.pid.to_numpy()[a1])
        u1 = first.u.reindex(fr.pid.to_numpy()[a2]).fillna(0.0).to_numpy()
        e1 = first.e.reindex(fr.pid.to_numpy()[a2]).fillna(0.0).to_numpy()
        loss = side[a2] * (pe[a2] - st[a2]) / pr[a2] + u1 * side[a2] * (e1 - st[a2])
        b2 = np.maximum(0.0, 1.0 - loss)
        b2[b2 <= EPS] = 0.0
        m[a2] = b2
    return m


def _year_of_exit(a_t_out, end_year=None):
    y = S.server_time(pd.to_datetime(a_t_out, utc=True)).year.to_numpy()
    return y


def open_risk(a, m):
    """Time-weighted average and maximum of the stakes open at the same time (sum of the stakes of the open
    positions, each counted at the risk it had at its own entry)."""
    took = m > 0
    ev_t = np.r_[a["t_in"][took], a["t_out"][took]]
    ev_v = np.r_[m[took], -m[took]]
    o = np.lexsort((ev_v, ev_t))
    lvl = np.cumsum(ev_v[o])
    t = ev_t[o]
    dt = np.diff(t)
    span = t[-1] - t[0]
    return float((lvl[:-1] * dt).sum() / span), float(lvl.max())


def pstats(a, fr, m, ref=None, last_year=None, yr=None):
    """Statistics of one configuration on the prepared frame `a` (stake.prepare), in base stakes."""
    st = S.stats(a, m)
    r = m * a["R"]
    is_add = fr.is_add.to_numpy() == 1
    if yr is None:
        yr = _year_of_exit(fr.t_out)
        if last_year is not None:
            yr = np.minimum(yr, last_year)                   # January exits of December entries stay in the last year
    took_add = is_add & (m > 0)
    avg_open, max_open = open_risk(a, m)
    out = {k: st[k] for k in ("total", "max_dd", "worst_week", "worst_day", "worst_month", "best_week", "win_days_pct", "win_weeks_pct",
                              "win_months_pct", "longest_red_weeks", "days", "weeks", "months", "avg_green_week", "avg_red_week")}
    out.update({
        "n_parents": int((~is_add).sum()), "n_addons": int(took_add.sum()),
        "addons_total": round(float(r[took_add].sum()), 2),
        "addons_avg_stake": round(float(m[took_add].mean()), 3) if took_add.any() else 0.0,
        "addons_max_stake": round(float(m[took_add].max()), 2) if took_add.any() else 0.0,
        "by_year": {int(y): round(float(r[yr == y].sum()), 1) for y in np.unique(yr)},
        "addons_by_year": {int(y): round(float(r[took_add & (yr == y)].sum()), 2) for y in np.unique(yr)},
        "avg_open_risk": round(avg_open, 3), "max_open_risk": round(max_open, 2),
        "total_exact": float(r.sum()),
    })
    # pooled add-on expectancy per unit of its own risk (criterion a)
    if took_add.any():
        x = a["R"][took_add]
        out["addon_mean_R"] = round(float(x.mean()), 4)
        out["addon_t_by_day"] = round(cluster_t(x, a["dy_out"][took_add]), 2)
        out["addon_share_positive"] = round(float((x > 0).mean()), 3)
        # position multiple: units of the whole group (parent + add-ons) / units of the parent
        u = pd.Series(np.where(took_add, m / fr.risk.to_numpy() * fr.p_risk.to_numpy(), 0.0)).groupby(fr.pid.to_numpy()).sum()
        out["max_position_multiple"] = round(float(1.0 + u.max()), 2)
    if ref is not None:
        s = ref["max_dd"] / st["max_dd"]
        out["equal_dd"] = {
            "scale": round(float(s), 4), "profit": round(float(out["total_exact"] * s), 1),
            "profit_vs_ref": round(float(out["total_exact"] * s / ref["total_exact"]), 4),
            "worst_week": round(float(st["worst_week"] * s), 2),
            "worst_week_vs_ref": round(float(st["worst_week"] * s / ref["worst_week"]), 4),
            "worst_day": round(float(st["worst_day"] * s), 2)}
        f = out["total_exact"] / ref["total_exact"]
        out["reference_with_a_bigger_flat_stake_same_total"] = {
            "flat_stake": round(float(f), 4), "max_dd": round(float(ref["max_dd"] * f), 2),
            "worst_week": round(float(ref["worst_week"] * f), 2), "worst_day": round(float(ref["worst_day"] * f), 2),
            "dd_of_configuration_vs_flat": round(float(st["max_dd"] / (ref["max_dd"] * f)), 4)}
    return out


def evaluate_all(parents, addons, last_year=None, log_runs=False):
    """Reference + the 24 configurations on one set of parents and add-ons (scope `trend` = the frozen TREND)."""
    fr = portfolio_frame(parents, addons)
    a = S.prepare(fr)
    trend = list(TREND)
    yr = _year_of_exit(fr.t_out)
    if last_year is not None:
        yr = np.minimum(yr, last_year)
    ref = pstats(a, fr, stakes(fr, REFERENCE, trend), yr=yr)
    res = {"reference": ref}
    for name, cfg in CONFIGS:
        res[name] = pstats(a, fr, stakes(fr, cfg, trend), ref, yr=yr)
        res[name]["config"] = cfg
        if log_runs:
            log("configuration_run", name=name)
    return res, fr, a


def criteria(res, control=None, t_min=2.5):
    """The five criteria of the selection rule for every configuration; `control` = output of control.summary."""
    ref = res["reference"]
    out = {}
    for name, _ in CONFIGS:
        x = res[name]
        if x["n_addons"] == 0:
            out[name] = {"pass": False, "no_addon": True}
            continue
        yrs = x["addons_by_year"]
        c = {"a_addon_expectancy>0_t>=%g" % t_min: bool(x["addon_mean_R"] > 0 and x["addon_t_by_day"] >= t_min),
             "b_profit_at_equal_dd>=1.15x_ref": bool(x["equal_dd"]["profit_vs_ref"] >= 1.15),
             "c_worst_week_at_equal_dd<=1.25x_ref": bool(abs(x["equal_dd"]["worst_week_vs_ref"]) <= 1.25),
             "d_addons_positive_years>=3of4": bool(sum(v > 0 for v in yrs.values()) >= 3),
             "d_years_positive": f"{sum(v > 0 for v in yrs.values())}/{len(yrs)}"}
        if control is not None:
            c["e_zero_edge_no_gain"] = bool(control[name]["ratio_equivalent_ci95_of_mean"][0] <= 1.0)
        c["pass"] = bool(all(v for k, v in c.items() if isinstance(v, bool)))
        out[name] = c
    return out


def select(res, crit):
    ok = [n for n, _ in CONFIGS if crit[n]["pass"]]
    if not ok:
        return None
    ok.sort(key=lambda n: (-res[n]["equal_dd"]["profit"], res[n]["n_addons"]))
    return ok[0]
