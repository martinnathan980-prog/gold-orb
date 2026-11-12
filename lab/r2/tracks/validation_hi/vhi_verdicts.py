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
Conventions: every value is computed from the trades of the run (unrounded); trades = entries inside the run's
evaluation window (the look: 2022-01-01 .. 2025-12-31); "as specified" = execution "lab"; years = the window's
years; the weekly measure = the plain sum at 1 R per trade (synthesis_B's portfolio metrics), server weeks (New
York + 7 h, booked at exit), every week of the window counted (an empty week = 0), sd with ddof 1; the skipped / kept
signals = the K1 signals decided inside the window that are usable (filled, not refused, not still open at the frame
end), each taken alone with FP costs (the walk-forward's labels).
"""
import numpy as np

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


def compute(spec, res, W):
    """The verdicts block: one entry per change in the run (res["changes"]["in_look"])."""
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
            raise ValueError(f"criteria[{cid}]: unknown kind {c['kind']!r} (registered: {sorted(CRITERIA)})")
        out[cid] = CRITERIA[c["kind"]](c, res, W)
    return out
