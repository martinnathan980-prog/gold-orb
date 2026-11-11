"""PROTOCOL_V3 addendum G: growth paths of an account that is fed 1,000 EUR a month and risks MORE per trade while it
is small (the user's request). An illustration of sizing on the validated trades, NOT a selection study.

    python3 r2/tracks/stake/growth.py dry     # in sample (2018-02..2021): self-checks only, nothing is written
    python3 r2/tracks/stake/growth.py val     # 2022-2025 (one logged access): writes results/r2/stake/growth.json

The account loop is the one of account.py (lots rounded down to the lot step, a trade is skipped when even the minimum
lot is too large for its budget, at most 6 positions and 2 per market, margin check, compounding, the adopted
`cushion_only` stake rule on the server week), written again for numba with three additions:
  * the risk per trade is a schedule: a % of the balance that depends on the size of the balance;
  * money is paid in at given times (it is not a gain: the week and day results of the stake rule exclude it);
  * the -50 % stop is optional. When it is off, the first time the hands' rule would have fired is recorded
    (balance <= half of the reference capital; reference = max(reference + payment, balance right after the payment)).
A balance at or below zero is set to zero and the open positions are dropped (the account is empty until the next
payment). Not modelled: slippage on larger sizes, the broker's margin call, the daily-loss lock, the minimum stop distance.
"""
import datetime as dt
import json
import os
import sys

import numpy as np
import pandas as pd
from numba import njit

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import stake as S  # noqa: E402
import account as A  # noqa: E402

DAY = 86400 * 10 ** 9
WEEK = 7 * DAY
MONTH = int(30.4375 * DAY)
CFG = S.INFO_ONLY["cushion_only"]["config"]
SCHEDULES = {                                   # (thresholds in EUR, risk % per trade below each, then above the last)
    "A": ((), (1.0,)),
    "B": ((5000.0,), (2.0, 1.0)),
    "C": ((3000.0, 10000.0, 20000.0), (5.0, 3.0, 2.0, 1.0)),
    "D": ((3000.0, 10000.0, 20000.0), (10.0, 5.0, 2.0, 1.0)),
    "E": ((3000.0, 10000.0, 20000.0), (20.0, 10.0, 5.0, 2.0)),
    "C2": ((3000.0, 10000.0, 20000.0), (5.0, 3.0, 2.0, 1.0)),       # clarification of addendum G: thresholds compared with
    "D2": ((3000.0, 10000.0, 20000.0), (10.0, 5.0, 2.0, 1.0)),      # max(balance, money paid in)
}
KEYED_ON_PAID = ("C2", "D2")
# second clarification of addendum G: plans that bound the loss. name -> (schedule used as cap, key of the risk rule,
# its parameters, monthly payments made whatever happens after the first 1,000 EUR, threshold of the steps (< 0 = no
# steps), catch-up paid with a month that is paid)
PROTECT = {
    "P": ("C2", 1, (0.0, 0.0), 2, 1.0, 0.0),
    "P2": ("C2", 1, (0.0, 0.0), 2, 1.0, 1000.0),
    "G": ("C2", 2, (0.10, 0.0), 0, -1.0, 0.0),
    "K70": ("C2", 3, (0.10, 0.70), 0, -1.0, 0.0),
    "K50": ("C2", 3, (0.10, 0.50), 0, -1.0, 0.0),
    "GP": ("C2", 2, (0.10, 0.0), 2, 1.0, 0.0),
    "K70P": ("C2", 3, (0.10, 0.70), 2, 1.0, 0.0),
}
PLANS = tuple(SCHEDULES) + tuple(PROTECT)
EDGES = (1.0, 0.5, 0.25, 0.0, -0.5)
NO_2024 = "1.0_no2024"                          # edge x1 with the weeks of 2024 left out of the draw
MILESTONES = (15000.0, 26000.0, 52000.0)
MONTHS = 36
N_PATHS = 2000
BLOCK = 8.0
SEED = 20261111
WINDOW = {"dry": (S.COMMON_START, S.IS_END), "val": (pd.Timestamp("2022-01-01", tz="UTC"), pd.Timestamp("2026-01-01", tz="UTC"))}
_mult = S.multiplier


@njit(cache=True)
def _pct(eq, thr, pct):
    for k in range(len(thr)):
        if eq < thr[k]:
            return pct[k]
    return pct[len(pct) - 1]


@njit(cache=True)
def _risk(eq, paid, thr, pct, key, rp):
    """Risk % of a trade.
    key 0  the schedule read on the balance;
    key 1  the schedule read on the larger of the balance and the money paid in;
    key 2  'gains pay for the risk': base % (1, or 0.5 / 0.25 when the balance is more than 10 / 20 % under the money
           paid in) + rp[0] x the accumulated gain, capped by the schedule of key 1 (never under the base);
    key 3  'floor': rp[0] x the cushion (balance - rp[1] x money paid in), capped by the schedule of key 1; 0 when the
           cushion is used up."""
    if key == 0:
        return _pct(eq, thr, pct)
    cap = _pct(max(eq, paid), thr, pct)
    if key == 1:
        return cap
    if eq <= 0.0:
        return 0.0
    if key == 2:
        g = (eq - paid) / paid if paid > 0.0 else 0.0
        base = 1.0 if g >= -0.10 else (0.5 if g >= -0.20 else 0.25)
        return min(base + 100.0 * rp[0] * max(0.0, eq - paid) / eq, max(cap, base))
    cushion = eq - rp[1] * paid
    if cushion <= 0.0:
        return 0.0
    return min(100.0 * rp[0] * cushion / eq, cap)


@njit(cache=True)
def engine(t_in, t_out, order_out, wk_in, dy_in, wk_out, dy_out, fam, symid, pnl, risk, entry, upl, minlot, step, lev,
           dep_t, dep_wk, dep_amt, thr, pct, key, rp, gate_free, gate_theta, catch, p, famcap, start, max_pos, max_per_sym,
           kill_dd, stop_on_kill, usd_eur, nwk):
    """One account. Returns (balance at the end of each week, money paid in at the end of each week, counts) where
    counts = [taken, skipped by the rule, by the minimum lot, by the position caps, by the margin, week of the first
    time the -50 % rule fires (-1 = never), times the balance reached zero, 1 if the account was stopped]."""
    n = len(t_in)
    eq_wk = np.zeros(nwk)
    paid_wk = np.zeros(nwk)
    cnt = np.zeros(8)
    cnt[5] = -1.0
    eq = start
    paid = start
    ref = start
    o_idx = np.full(max_pos, -1, np.int64)
    o_lots = np.zeros(max_pos)
    o_margin = np.zeros(max_pos)
    o_boost = np.zeros(max_pos)
    cur_wk, cur_dy = -1, -1
    wk_paid = start
    held = 0.0                                # money of the skipped months, kept outside the robot
    wk_bal, dy_bal, wk_base, dy_base = start, start, start, start     # *_base = balance at the start + payments since
    prev_wk, prev_res = -2, 0.0
    rec = 0                                   # weeks < rec already have their end-of-week figures
    j, q = 0, 0
    nd = len(dep_t)
    stopped = False
    i = 0
    while True:
        # the next event: a close (strictly before the next entry), a payment (at or before it), or the entry itself
        t_entry = t_in[i] if i < n else np.int64(9223372036854775807)
        t_close = t_out[order_out[j]] if j < n else np.int64(9223372036854775807)
        t_dep = dep_t[q] if q < nd else np.int64(9223372036854775807)
        if i >= n and j >= n and q >= nd:
            break
        if t_dep <= t_entry and t_dep <= t_close and q < nd:
            w_ev = dep_wk[q]
            while rec < w_ev and rec < nwk:
                eq_wk[rec], paid_wk[rec] = eq, paid
                rec += 1
            if not stopped:
                amt = dep_amt[q]
                # payments by steps: after the first `gate_free` monthly payments, a month is paid in only if the balance
                # is at least gate_theta x the money already paid in; the money of a skipped month stays outside
                if gate_theta >= 0.0 and q >= gate_free and eq < gate_theta * paid:
                    held += amt
                    amt = 0.0
                elif catch > 0.0 and held > 0.0:
                    extra = min(held, catch)
                    held -= extra
                    amt += extra
                if amt > 0.0:
                    eq += amt
                    paid += amt
                    wk_base += amt
                    dy_base += amt
                    if eq == amt:              # the account was empty: nothing of the week is left to measure against
                        wk_base, dy_base = eq, eq
                    ref = max(ref + amt, eq)
            q += 1
            continue
        if t_close < t_entry and j < n:
            k = order_out[j]
            j += 1
            slot = -1
            for s in range(max_pos):
                if o_idx[s] == k:
                    slot = s
            if slot < 0:
                continue
            w_ev = wk_out[k]
            while rec < w_ev and rec < nwk:
                eq_wk[rec], paid_wk[rec] = eq, paid
                rec += 1
            if w_ev != cur_wk:
                if cur_wk >= 0:
                    prev_wk, prev_res = cur_wk, (eq - wk_base) / max(_risk(wk_bal, wk_paid, thr, pct, key, rp) / 100.0 * wk_bal, 1e-9)
                cur_wk, wk_bal, wk_base, wk_paid = w_ev, eq, eq, paid
            if dy_out[k] != cur_dy:
                cur_dy, dy_bal, dy_base = dy_out[k], eq, eq
            eq += pnl[k] * o_lots[slot] * upl[k] * usd_eur
            o_idx[slot] = -1
            if eq <= 0.0:                      # the account is empty: nothing left to trade with until the next payment
                eq = 0.0
                cnt[6] += 1.0
                for s in range(max_pos):
                    o_idx[s] = -1
            if eq <= ref * (1.0 - kill_dd) and cnt[5] < 0:
                cnt[5] = float(w_ev)
                if stop_on_kill:
                    stopped = True
                    cnt[7] = 1.0
                    if i >= n:                 # after the last entry account.py stops at once
                        for s in range(max_pos):
                            o_idx[s] = -1
            continue
        if i >= n:
            break
        # an entry
        w_ev = wk_in[i]
        while rec < w_ev and rec < nwk:
            eq_wk[rec], paid_wk[rec] = eq, paid
            rec += 1
        if stopped:                            # stopped for good: what was still open is dropped (as account.py does)
            for s in range(max_pos):
                o_idx[s] = -1
            i += 1
            continue
        if w_ev != cur_wk:
            if cur_wk >= 0:
                prev_wk, prev_res = cur_wk, (eq - wk_base) / max(_risk(wk_bal, wk_paid, thr, pct, key, rp) / 100.0 * wk_bal, 1e-9)
            cur_wk, wk_bal, wk_base, wk_paid = w_ev, eq, eq, paid
        if dy_in[i] != cur_dy:
            cur_dy, dy_bal, dy_base = dy_in[i], eq, eq
        unit = max(_risk(wk_bal, wk_paid, thr, pct, key, rp) / 100.0 * wk_bal, 1e-9)
        w = (eq - wk_base) / unit
        d = (eq - dy_base) / unit
        pw = prev_res if prev_wk == w_ev - 1 else 0.0
        open_boost, n_open, n_sym = 0.0, 0, 0
        used = 0.0
        for s in range(max_pos):
            if o_idx[s] >= 0:
                n_open += 1
                open_boost += o_boost[s]
                used += o_margin[s]
                if symid[o_idx[s]] == symid[i]:
                    n_sym += 1
        m, b = _mult(w, d, pw, fam[i], open_boost, p, famcap)
        if m <= 0.0 or eq <= 0.0:
            cnt[1] += 1.0
            i += 1
            continue
        per_lot = risk[i] * upl[i] * usd_eur
        lots = np.floor(eq * _risk(eq, paid, thr, pct, key, rp) * m / 100.0 / per_lot / step[i] + 1e-9) * step[i]
        if lots < minlot[i]:
            cnt[2] += 1.0
            i += 1
            continue
        if n_open >= max_pos or n_sym >= max_per_sym:
            cnt[3] += 1.0
            i += 1
            continue
        margin = lots * upl[i] * entry[i] * usd_eur / lev[i]
        if used + margin > eq:
            cnt[4] += 1.0
            i += 1
            continue
        for s in range(max_pos):
            if o_idx[s] < 0:
                o_idx[s], o_lots[s], o_margin[s], o_boost[s] = i, lots, margin, b
                break
        cnt[0] += 1.0
        i += 1
    while rec < nwk:
        eq_wk[rec], paid_wk[rec] = eq, paid
        rec += 1
    return eq_wk, paid_wk, cnt


def load(period):
    """The ten sleeves' trades of the period at today's price level, with everything the engine needs."""
    a, b = WINDOW[period]
    per = {}
    for name, sym in S.SLEEVES:
        t = pd.read_parquet(os.path.join(S.NET_DIR, f"{name}__{sym}.parquet"))
        per[(name, sym)] = t[(t.entry_time >= a) & (t.entry_time < b)]          # the cut comes first
    if period == "val":
        with open(os.path.join(S.LAB, "results", "val_access.log"), "a") as f:
            f.write(json.dumps({"time": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"), "track": "stake",
                                "label": "growth_paths:risk_schedules:illustration_no_selection", "period": "val"}) + "\n")
    return S.build_frame(per)


def arrays(d, price_level="today"):
    fr = A.frame(d=d, price_level=price_level)
    a = S.prepare(fr)
    syms = sorted(set(fr.sym))
    si, so = S.server_time(fr.t_in), S.server_time(fr.t_out)
    monday = a["week_monday"].values.astype("datetime64[ns]").astype("int64")[a["wk_in"]]
    x = dict(
        t_in=a["t_in"], t_out=a["t_out"], wk_in=a["wk_in"].astype(np.int64), wk_out=a["wk_out"].astype(np.int64),
        dy_in=a["dy_in"].astype(np.int64), dy_out=a["dy_out"].astype(np.int64), fam=a["fam"],
        symid=np.array([syms.index(s) for s in fr.sym], dtype=np.int64),
        pnl=fr.pnl.to_numpy(float), risk=fr.risk.to_numpy(float), entry=fr.entry.to_numpy(float),
        upl=fr.units_per_lot.to_numpy(float), minlot=fr.min_lot.to_numpy(float), step=fr.lot_step.to_numpy(float),
        lev=fr.leverage.to_numpy(float), nwk=a["nwk"], sleeve=fr.sleeve.to_numpy(),
        off_in=si.values.astype("datetime64[ns]").astype("int64") - monday,      # server time since Monday 00:00 of the entry week
        off_out=so.values.astype("datetime64[ns]").astype("int64") - monday,
        week_monday=a["week_monday"], t_in_server=si,
    )
    assert (x["off_in"] >= 0).all() and (x["off_in"] < WEEK).all() and (x["off_out"] >= x["off_in"]).all()
    return x


def with_edge(x, f):
    """Each sleeve's mean R multiplied by f: a constant per sleeve is subtracted from every trade's R."""
    if f == 1.0:
        return x["pnl"]
    R = x["pnl"] / x["risk"]
    pnl = x["pnl"].copy()
    for s in np.unique(x["sleeve"]):
        k = x["sleeve"] == s
        pnl[k] = (R[k] - (1.0 - f) * R[k].mean()) * x["risk"][k]
    return pnl


def pack(x, idx=None, t=None, nwk=None):
    """Everything of a path that does not depend on the schedule or on the edge."""
    if idx is None:
        t_in, t_out, wk_in, wk_out, dy_in, dy_out = x["t_in"], x["t_out"], x["wk_in"], x["wk_out"], x["dy_in"], x["dy_out"]
        idx = slice(None)
    else:
        t_in, t_out, wk_in, wk_out, dy_in, dy_out = t
    return dict(head=(t_in, t_out, np.argsort(t_out, kind="stable"), wk_in, dy_in, wk_out, dy_out, x["fam"][idx], x["symid"][idx]),
                tail=(x["risk"][idx], x["entry"][idx], x["upl"][idx], x["minlot"][idx], x["step"][idx], x["lev"][idx]),
                idx=idx, nwk=x["nwk"] if nwk is None else nwk)


def run_one(pk, pnl, sched, dep_t, dep_wk, dep_amt, start=1000.0, stop_on_kill=False, kill_dd=0.5):
    """`pk` = pack(...) ; `pnl` = the per-trade result in price units for the whole frame (the edge scenario)."""
    p, famcap = S.params(CFG)
    if sched in PROTECT:
        base, key, rp, gate_free, gate_theta, catch = PROTECT[sched]
    else:
        base, key, rp, gate_free, gate_theta, catch = sched, (1 if sched in KEYED_ON_PAID else 0), (0.0, 0.0), 0, -1.0, 0.0
    thr, pct = (np.array(v, dtype=np.float64) for v in SCHEDULES[base])
    return engine(*pk["head"], pnl[pk["idx"]], *pk["tail"], dep_t, dep_wk, dep_amt, thr, pct, key, np.array(rp, dtype=np.float64),
                  gate_free, gate_theta, catch, p, famcap, start,
                  A.LIMITS["max_positions"], A.LIMITS["max_per_sym"], kill_dd, stop_on_kill, A.USD_EUR, pk["nwk"])


def self_check(x_is_prices, d, period):
    """Schedule A, no payment, the -50 % stop: the engine must give account.py's figures exactly."""
    out = []
    none = (np.zeros(0, np.int64), np.zeros(0, np.int64), np.zeros(0))
    for level, x in (("is", x_is_prices), ("today", arrays(d, "today"))):
        ref = A.account(CFG, 1000.0, base_pct=1.0, d=A.frame(d=d, price_level=level), compound=True)
        eq, _, c = run_one(pack(x), x["pnl"], "A", *none, stop_on_kill=True)
        got = {"final": round(float(eq[-1]), 2), "taken": int(c[0]), "min_lot": int(c[2]), "cap": int(c[3]), "margin": int(c[4])}
        want = {"final": ref["final"], "taken": ref["n_taken"], "min_lot": ref["skipped"]["min_lot"], "cap": ref["skipped"]["position_cap"],
                "margin": ref["skipped"]["margin"]}
        ok = got == want
        out.append({"price_level": level, "engine": got, "account.py": want, "identical": ok})
        print(f"self-check {period} prices={level}: engine {got} | account.py {want} | {'IDENTICAL' if ok else 'DIFFERENT'}")
        assert ok, "the engine does not reproduce account.py"
    return out


def real_order(x):
    """2022-2025 in their real order: 1,000 EUR at the start, 1,000 EUR on the first day of each following month."""
    first = x["t_in_server"].min().normalize().replace(day=1)
    last = x["t_in_server"].max()
    months = pd.date_range(first, last, freq="MS")[1:]
    dep_srv = months.values.astype("datetime64[ns]").astype("int64")
    w0 = x["week_monday"][0].value
    dep_wk = ((dep_srv - w0) // WEEK).astype(np.int64)
    # the engine compares payment times with UTC entry times: use the first entry at or after the server month start
    order = np.argsort(x["t_in"], kind="stable")
    srv = x["t_in_server"].values.astype("datetime64[ns]").astype("int64")[order]
    pos = np.searchsorted(srv, dep_srv, side="left")
    keep = pos < len(order)
    dep_t = x["t_in"][order][pos[keep]]
    dep_wk = x["wk_in"][order][pos[keep]]
    dep_amt = np.full(int(keep.sum()), 1000.0)
    out = {}
    week_end = [str((m + pd.Timedelta(days=6)).date()) for m in x["week_monday"]]
    pk = pack(x)
    for name in SCHEDULES:
        eq, paid, c = run_one(pk, x["pnl"], name, dep_t, dep_wk, dep_amt)
        out[name] = {"balance_by_week": [round(float(v), 0) for v in eq], "paid_by_week": [round(float(v), 0) for v in paid],
                     "final": round(float(eq[-1]), 0), "paid": round(float(paid[-1]), 0), "lowest_vs_paid_pct": round(float((eq / paid).min() * 100), 0),
                     "taken": int(c[0]), "skipped_min_lot": int(c[2]), "skipped_caps": int(c[3]), "skipped_margin": int(c[4]),
                     "stop_rule_first_fires_week": None if c[5] < 0 else week_end[int(c[5])], "times_at_zero": int(c[6])}
        # the largest fall of the balance from its highest point (payments included: they soften it)
        gain = eq - paid
        dd = (np.maximum.accumulate(eq) - eq) / np.maximum.accumulate(eq)
        out[name]["largest_fall_pct"] = round(float(dd.max() * 100), 0)
        out[name]["gain"] = round(float(gain[-1]), 0)
    return {"week_end": week_end, "schedules": out}


def draw_paths(x, n_paths, months, rng, without_year=None):
    """Resampled calendars: for each path, the original week placed at each position (blocks of mean length BLOCK).
    `without_year`: the weeks whose Monday falls in that year are left out of the draw (blocks run over the others)."""
    weeks_with = np.unique(x["wk_in"])
    lo, hi = int(weeks_with.min()), int(weeks_with.max())
    allowed = np.arange(lo, hi + 1)
    if without_year is not None:
        allowed = allowed[x["week_monday"].year.to_numpy()[allowed] != without_year]
    n_weeks = int(np.ceil(months * 30.4375 / 7.0))
    span = len(allowed)
    plan = np.zeros((n_paths, n_weeks), np.int64)
    for k in range(n_paths):
        pos = 0
        while pos < n_weeks:
            startw = rng.integers(0, span)
            length = int(rng.geometric(1.0 / BLOCK))
            for q in range(length):
                if pos >= n_weeks:
                    break
                plan[k, pos] = allowed[(startw + q) % span]
                pos += 1
    return plan, n_weeks


def resampled(x, months=MONTHS, n_paths=N_PATHS, seed=SEED, only=None):
    """`only` = number of first paths to compute (the plan is always drawn for `n_paths`, so path k is the same path
    whatever `only` is)."""
    rng = np.random.default_rng(seed)
    plan, n_weeks = draw_paths(x, n_paths, months, rng)
    plan_no24, _ = draw_paths(x, n_paths, months, np.random.default_rng(seed + 1), without_year=2024)   # its own draws
    if only is not None:
        plan, plan_no24, n_paths = plan[:only], plan_no24[:only], only
    order = np.argsort(x["wk_in"], kind="stable")                # trades are already sorted by entry time
    wk_sorted = x["wk_in"][order]
    first = np.searchsorted(wk_sorted, np.arange(x["nwk"] + 1), side="left")
    dep_m = np.arange(1, months)                                  # 1,000 EUR at the start, then at the start of each month
    dep_t = (dep_m * MONTH).astype(np.int64)
    dep_wk = (dep_t // WEEK).astype(np.int64)
    dep_amt = np.full(len(dep_m), 1000.0)
    month_wk = np.minimum(((np.arange(months + 1) * MONTH) // WEEK).astype(np.int64), n_weeks) - 1     # last full week before each month end
    month_wk[0] = -1
    pnls = {f: with_edge(x, f) for f in EDGES}
    keys = list(EDGES) + [NO_2024]
    res = {s: {f: np.zeros((n_paths, months + 1)) for f in keys} for s in PLANS}
    paid_in = {s: {f: np.zeros((n_paths, months + 1)) for f in keys} for s in PLANS}
    fired = {s: {f: np.zeros(n_paths) for f in keys} for s in PLANS}
    zero = {s: {f: np.zeros(n_paths) for f in keys} for s in PLANS}
    paid_m = 1000.0 * np.maximum(np.arange(months + 1), 1)       # paid in by the end of month h: payments at months 0 .. h-1
    for k in range(n_paths):
        for the_plan, the_keys in ((plan, EDGES), (plan_no24, (NO_2024,))):
            parts = [order[first[w]:first[w + 1]] for w in the_plan[k]]
            idx = np.concatenate(parts)
            pos = np.repeat(np.arange(n_weeks), [len(q) for q in parts]).astype(np.int64)
            t_in = pos * WEEK + x["off_in"][idx]
            t_out = pos * WEEK + x["off_out"][idx]
            t = (t_in, t_out, pos, pos + (x["wk_out"][idx] - x["wk_in"][idx]), t_in // DAY, t_out // DAY)
            pk = pack(x, idx, t, n_weeks)
            for s in PLANS:
                for f in the_keys:
                    eq, pd_, c = run_one(pk, pnls[1.0 if f == NO_2024 else f], s, dep_t, dep_wk, dep_amt)
                    res[s][f][k, 0] = 1000.0
                    res[s][f][k, 1:] = eq[month_wk[1:]]
                    paid_in[s][f][k, 0] = 1000.0
                    paid_in[s][f][k, 1:] = pd_[month_wk[1:]]
                    fired[s][f][k] = c[5]
                    zero[s][f][k] = c[6]
    resampled.paid_in = paid_in                                   # per path: the plans with steps do not pay every month
    return res, fired, zero, paid_m, n_weeks


def summarise(res, fired, zero, paid_m):
    out = {}
    q = (10, 25, 50, 75, 90)
    paid_in = getattr(resampled, "paid_in", None)
    for s in res:
        out[s] = {}
        for f in res[s]:
            m = res[s][f]
            pc = np.percentile(m, q, axis=0)
            row = {"percentiles_by_month": {str(p): [round(float(v), 0) for v in pc[i]] for i, p in enumerate(q)},
                   "mean_by_month": [round(float(v), 0) for v in m.mean(axis=0)]}
            for h in (12, 24, 36):
                row[f"at_{h}_months"] = {
                    "paid": float(paid_m[h]), "median": round(float(np.median(m[:, h])), 0),
                    "p10": round(float(np.percentile(m[:, h], 10)), 0), "p90": round(float(np.percentile(m[:, h], 90)), 0),
                    "below_paid_pct": round(float(100 * (m[:, h] < paid_m[h]).mean()), 1),
                    "below_half_paid_pct": round(float(100 * (m[:, h] < 0.5 * paid_m[h]).mean()), 1),
                    **{f"above_{int(x)}_pct": round(float(100 * (m[:, h] >= x).mean()), 1) for x in MILESTONES}}
            reach = {}
            for x in MILESTONES:
                hit = m >= x
                ever = hit.any(axis=1)
                when = np.where(ever, hit.argmax(axis=1), 10 ** 6)
                reach[str(int(x))] = {"within_36_months_pct": round(float(100 * ever.mean()), 1),
                                      "median_month": (int(np.median(when)) if ever.mean() >= 0.5 else None)}
            row["first_reach"] = reach
            # gains = balance minus the money really paid in, path by path (the plans with steps do not pay every month)
            pin = paid_in[s][f] if paid_in is not None else np.tile(paid_m, (len(m), 1))
            gains = m - pin
            gq = np.percentile(gains, q, axis=0)
            row["gain_percentiles_by_month"] = {str(p_): [round(float(v), 0) for v in gq[i]] for i, p_ in enumerate(q)}
            for h in (12, 24, 36):
                row[f"at_{h}_months"].update({
                    "gain_median": round(float(np.median(gains[:, h])), 0), "gain_p10": round(float(np.percentile(gains[:, h], 10)), 0),
                    "gain_p90": round(float(np.percentile(gains[:, h], 90)), 0), "in_loss_pct": round(float(100 * (gains[:, h] < 0).mean()), 1),
                    "paid_in_median": round(float(np.median(pin[:, h])), 0), "paid_in_p10": round(float(np.percentile(pin[:, h], 10)), 0),
                    "paid_in_p90": round(float(np.percentile(pin[:, h], 90)), 0), "balance_median": round(float(np.median(m[:, h])), 0),
                    "worst_gain": round(float(gains[:, h].min()), 0)})
            # the first month from which the median path gains at least 1,000 EUR a month, on a 6-month average, for good
            g = np.median(gains, axis=0)
            ok = np.array([(g[h + 6] - g[h]) / 6.0 >= 1000.0 for h in range(len(g) - 6)])
            later_all_ok = np.flip(np.cumprod(np.flip(ok))).astype(bool)
            row["month_of_a_lasting_1000_a_month"] = int(np.argmax(later_all_ok)) if later_all_ok.any() else None
            row["gain_per_month_by_year_median_path"] = [round(float((g[12 * (y + 1)] - g[12 * y]) / 12.0), 0) for y in range(3)]
            row["stop_rule_fires_pct"] = round(float(100 * (fired[s][f] >= 0).mean()), 1)
            row["balance_reaches_zero_pct"] = round(float(100 * (zero[s][f] > 0).mean()), 1)
            out[s][str(f)] = row
    return out


def main(period):
    d = load(period)
    x_is = arrays(d, "is")
    checks = self_check(x_is, d, period)
    x = arrays(d, "today")
    if period == "dry":
        res, fired, zero, paid_m, n_weeks = resampled(x, months=12, n_paths=50)
        s = summarise_small(res, paid_m)
        print("dry run on 50 paths of 12 months (in sample):", s)
        return
    ro = real_order(x)
    for name, r in ro["schedules"].items():
        print(f"real order {name}: final {r['final']:>10,.0f} EUR for {r['paid']:,.0f} paid in | lowest {r['lowest_vs_paid_pct']} % of the money paid | "
              f"largest fall {r['largest_fall_pct']} % | taken {r['taken']} | stop rule {r['stop_rule_first_fires_week']} | at zero {r['times_at_zero']}")
    res, fired, zero, paid_m, n_weeks = resampled(x)
    summ = summarise(res, fired, zero, paid_m)
    for s in PLANS:
        for f in list(EDGES) + [NO_2024]:
            r = summ[s][str(f)]["at_36_months"]
            if s in PROTECT or s in ("A", "C2"):
                a = summ[s][str(f)]["at_12_months"]
                print(f"{s:4s} edge x{str(f):<10}: 36 m gain median {r['gain_median']:>9,.0f} (1 in 10: {r['gain_p10']:>9,.0f} .. {r['gain_p90']:>9,.0f}) paid in {r['paid_in_median']:>7,.0f} "
                      f"in loss {r['in_loss_pct']:5.1f} % worst {r['worst_gain']:>9,.0f} | 12 m gain {a['gain_median']:>8,.0f} (1 in 10: {a['gain_p10']:>8,.0f}) paid {a['paid_in_median']:>6,.0f} | "
                      f"1,000 a month from {summ[s][str(f)]['month_of_a_lasting_1000_a_month']} | stop rule {summ[s][str(f)]['stop_rule_fires_pct']:5.1f} %")
                continue
            print(f"{s:2s} edge x{str(f):<10}: at 36 months median {r['median']:>10,.0f} (10 %: {r['p10']:>9,.0f}, 90 %: {r['p90']:>10,.0f}) for {r['paid']:,.0f} paid | "
                  f"below paid {r['below_paid_pct']:5.1f} % | lasting 1,000 a month from month {summ[s][str(f)]['month_of_a_lasting_1000_a_month']} | "
                  f"stop rule {summ[s][str(f)]['stop_rule_fires_pct']:5.1f} % | zero {summ[s][str(f)]['balance_reaches_zero_pct']:5.1f} %")
    out = {"protocol": "PROTOCOL_V3 addendum G", "period": [str(v.date()) for v in WINDOW[period]], "n_signals": int(len(d)),
           "schedules": {k: {"thresholds_eur": list(v[0]), "risk_pct": list(v[1])} for k, v in SCHEDULES.items()},
           "edges": list(EDGES), "extra_scenario": {NO_2024: "edge x1, the weeks of 2024 left out of the draw (its own draws, seed + 1)"},
           "keyed_on_max_of_balance_and_paid": list(KEYED_ON_PAID),
           "protect": {k: {"cap_schedule": v[0], "risk_key": v[1], "risk_params": list(v[2]), "free_monthly_payments": v[3], "steps_threshold": v[4],
                           "catch_up": v[5]} for k, v in PROTECT.items()}, "months": MONTHS, "paths": N_PATHS, "block_weeks": BLOCK, "seed": SEED, "payment_eur": 1000.0,
           "paid_by_month": [float(v) for v in paid_m], "self_check": checks, "real_order": ro, "resampled": summ,
           "not_modelled": "slippage on larger sizes, broker margin call, daily-loss lock, minimum stop distance; the -50 % stop is recorded, not applied"}
    json.dump(out, open(os.path.join(S.OUT, "growth.json"), "w"), indent=1)


def summarise_small(res, paid_m):
    return {s: {str(f): round(float(np.median(res[s][f][:, -1])), 0) for f in res[s]} for s in res}


def dump(path, k=30):
    """For an independent recomputation: the month-end balances of the first k resampled paths, per schedule and edge
    (2022-2025 trades: the access is logged)."""
    x = arrays(load("val"), "today")
    res, fired, zero, paid_m, n_weeks = resampled(x, only=k)
    np.savez(path, **{f"{s}_{f}": res[s][f] for s in res for f in res[s]},
             **{f"paid_{s}_{f}": resampled.paid_in[s][f] for s in res for f in res[s]},
             **{f"fired_{s}_{f}": fired[s][f] for s in res for f in res[s]}, paid=paid_m)
    print("written", path, "paths", k, "weeks", n_weeks)


if __name__ == "__main__":
    if sys.argv[1] == "dump":
        dump(sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 30)
    else:
        main(sys.argv[1])
