"""Blind test of "the algorithm proposes, Claude decides".

PRE-REGISTERED on 2026-11-10, before any model call and before any look at filtered results on the
validation period.

Question. When a rule fires, does a go / no-go from Claude, given the context of the moment, separate the
better signals from the worse ones?

Cases. Every trade of the ten sleeves below (frozen rules, FP Markets Raw costs, one position per sleeve:
results/r2/recalc/trades). In-sample = entries before 2022 (prompt checks, cost measurement, fitting of
the baseline); validation = entries 2022-2025 (the test). The outcome of a case is its net R.

What the model sees. The anonymous context sheet of context.py (no date, no absolute price, no news) and
the rule sheet of judge.py with in-sample statistics only. The prompt is frozen (hash stored with each run).

Leak probe. On 150 sheets spread over all years the model is asked to guess the calendar year. If its
guesses follow the true year (rank correlation above 0.3) the sheet is not anonymous enough and is
tightened before the test.

Primary test: validation cases of all sleeves pooled, `claude-opus-5-5` at its default effort, on every
validation case, or on a random sample per sleeve (seed 0) whose size is fixed before the run by the
API budget. Permutation within sleeve, 5,000 draws, one-sided.
  H1  mean R of the signals Claude takes > mean R of those it skips            (p <= 0.05)
  H2  mean R of the skipped signals <= 0   (they lose on average: skipping them costs nothing)
Secondary: rank correlation between `quality` and R; the same tables per sleeve; other models; and a
fitted baseline that reads the numeric version of the same sheet (ridge regression of R trained
in-sample, penalty = number of in-sample trades, skipping the signals below the 30th percentile of its
in-sample predictions). The baseline tells whether the sheet holds usable information at all and
whether Claude's judgement adds something a simple formula does not.

Decision.
  H1 and H2   -> Claude gets the final say in the robot, and stays measured live (taken vs refused).
  H1 only     -> Claude modulates the size (full / half) instead of vetoing.
  neither     -> Claude does not decide entries. It keeps the roles that price data cannot test:
                 news / calendar veto (forward test only) and supervision of the robot.
Each model / effort configuration is run once on validation; every run is kept in results/llm/runs.

AMENDMENTS of 2026-11-10, written before any validation run.
1. The leak probe failed on the first sheets (prices in % and basis points, market named): the model named
   the year 55 % of the time (rank correlation +0.68). As planned, the sheets were tightened: every price is
   now a distance in units of the market's own volatility and the market's name is hidden (mode "blind",
   sheets_blind.parquet). Second probe on the same cases: exact year 10 %, rank correlation +0.15 (with the
   name given: 25 %, +0.48). The validation test uses the blind sheets. The two in-sample pilots (120 cases)
   are not evidence: +0.46 R with the leaking sheets, +0.25 R (p 0.11) with the blind ones.
2. Robustness to an exceptional year (asked by the user). H3: the gap "taken minus skipped" is computed for
   each calendar year 2022, 2023, 2024, 2025 and for the test with each year removed in turn. The result is
   called robust only if the gap is positive in at least three of the four years AND stays positive with any
   single year removed. Claude gets the final say only if H1, H2 and H3 all hold.

Commands (from lab/):
  python3 llm/experiment.py build                         cases + sheets (no API call)
  python3 llm/experiment.py show [case_id]                the exact prompt of one case
  python3 llm/experiment.py baseline                      fitted baseline on validation
  python3 llm/experiment.py run   --name N --period is --per-sleeve 12 [--model M --effort E]   live calls
  python3 llm/experiment.py submit --name N --period val [--per-sleeve K] [--model M --effort E]  batch, half price
  python3 llm/experiment.py collect --name N [--wait]
  python3 llm/experiment.py probe --name N [--model M]
  python3 llm/experiment.py analyse --name N
"""
import argparse
import concurrent.futures as cf
import json
import os
import sys
import time

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
from llm import judge  # noqa: E402

ASSET = judge.ASSET                         # same labels as llm/context.py (not imported here: it needs the market data toolkit)

OUT = os.path.join(LAB, "results", "llm")
SHEETS = os.path.join(OUT, "sheets.parquet")                  # what the model reads, one text per case (in git: the
                                                              # test must be runnable where the API key is, without the market data)
TRADES = os.path.join(LAB, "results", "r2", "recalc", "trades")
SPLIT = pd.Timestamp("2022-01-01", tz="UTC")
SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("nq_btc_follow", "btcusd"), ("F2_brk_unfiltered", "btcusd"), ("F2_brk_unfiltered", "ethusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]


# ------------------------------------------------------------------------------------------ build
def _rule_stats(t):
    w, lo = t.R[t.R > 0], t.R[t.R <= 0]
    m = lambda x: round(float(x.mean()), 4) if len(x) else None
    return {"n": int(len(t)), "win_rate": round(float((t.R > 0).mean()), 3), "avg_win_R": m(w), "avg_loss_R": m(lo),
            "exp_R": m(t.R), "med_hold_h": round(float(t.hold_min.median() / 60), 2),
            "long_exp_R": m(t.R[t.side > 0]), "short_exp_R": m(t.R[t.side < 0])}


def build():
    from goldlab import r2
    from llm.context import ASSET as ASSET_CTX, Market
    assert ASSET_CTX == ASSET
    os.makedirs(OUT, exist_ok=True)
    ref = Market("us100")
    r2.free()
    rows, sheets, stats, mk = [], [], {}, None
    for name, sym in SLEEVES:
        t = pd.read_parquet(os.path.join(TRADES, f"{name}__{sym}.parquet"))
        if sym == "us100":
            mk = ref
        elif mk is None or mk.sym != sym:
            mk = Market(sym)
            r2.free()
        key = f"{name}_{sym}"
        stats[key] = _rule_stats(t[t.entry_time < SPLIT])
        ii = mk.index.searchsorted(pd.DatetimeIndex(t.entry_time))
        assert (mk.index[ii] == pd.DatetimeIndex(t.entry_time)).all(), key
        skipped = 0
        for n, (i, r) in enumerate(zip(ii, t.itertuples(index=False))):
            res = mk.sheet(i, r.side, r.entry, r.stop, ref=ref)
            if res is None:
                skipped += 1
                continue
            cid = f"{key}-{n:05d}"
            rows.append({"id": cid, "sleeve": key, "name": name, "sym": sym,
                         "period": "is" if r.entry_time < SPLIT else "val", "entry_time": r.entry_time,
                         "R": float(r.R), **res[1]})
            sheets.append({"id": cid, "text": res[0]})
        print(f"{key}: {len(t)} trades, {skipped} without enough history", flush=True)
    cases = pd.DataFrame(rows)
    cases.to_parquet(os.path.join(OUT, "cases.parquet"))
    pd.DataFrame(sheets).to_parquet(SHEETS, compression="zstd", compression_level=19, index=False)
    json.dump(stats, open(os.path.join(OUT, "rule_stats.json"), "w"), indent=1)
    print(cases.groupby(["sleeve", "period"]).size().unstack().to_string())
    print("sheet length (chars): median", int(pd.DataFrame(sheets).text.str.len().median()))


def make_blind(out, named=False, ids=None):
    """Scale-free sheets (context.Market.sheet_blind) for the given case ids (default: every case) -> results/llm/<out>."""
    from goldlab import r2
    from llm.context import Market
    cases = pd.read_parquet(os.path.join(OUT, "cases.parquet"))
    want = set(cases.id if ids is None else ids)
    ref = Market("us100")
    r2.free()
    rows, mk = [], None
    for name, sym in SLEEVES:
        key = f"{name}_{sym}"
        todo = sorted(int(c.split("-")[-1]) for c in want if c.rsplit("-", 1)[0] == key)
        if not todo:
            continue
        t = pd.read_parquet(os.path.join(TRADES, f"{name}__{sym}.parquet"))
        if sym == "us100":
            mk = ref
        elif mk is None or mk.sym != sym:
            mk = Market(sym)
            r2.free()
        ii = mk.index.searchsorted(pd.DatetimeIndex(t.entry_time))
        for n in todo:
            r = t.iloc[n]
            rows.append({"id": f"{key}-{n:05d}", "text": mk.sheet_blind(ii[n], r.side, r.entry, r.stop, ref=ref, named=named)})
    d = pd.DataFrame(rows)
    assert d.text.notna().all() and len(d) == len(want)
    d.to_parquet(os.path.join(OUT, out), compression="zstd", compression_level=19, index=False)
    print(f"{out}: {len(d)} sheets, median length {int(d.text.str.len().median())} chars")


def probe_ids(cases, n=150):
    """The sheets of the leak probe: the same number per calendar year, fixed seed."""
    c = cases.assign(year=pd.DatetimeIndex(cases.entry_time).year)
    return pd.concat([g.sample(min(len(g), max(1, n // c.year.nunique())), random_state=0) for _, g in c.groupby("year")])


def load(sheets=None):
    cases = pd.read_parquet(os.path.join(OUT, "cases.parquet"))
    texts = pd.read_parquet(os.path.join(OUT, sheets) if sheets else SHEETS).set_index("id").text
    stats = json.load(open(os.path.join(OUT, "rule_stats.json")))
    return cases, texts, stats


def system_for(row, stats, mode="pct"):
    return judge.system_blocks(row["name"], row["sym"], stats[row["sleeve"]], mode)


def pick(cases, period, per_sleeve=None, seed=0):
    c = cases[cases.period == period]
    if per_sleeve:
        c = pd.concat([g.sample(min(per_sleeve, len(g)), random_state=seed) for _, g in c.groupby("sleeve")])
    return c.sort_values("id")


# ------------------------------------------------------------------------------------------ statistics
def _pf(x):
    neg = -x[x < 0].sum()
    return round(float(x[x > 0].sum() / neg), 3) if neg > 0 else float("nan")


def _table(d):
    out = []
    for s, g in list(d.groupby("sleeve")) + [("ALL", d)]:
        tk, sk = g[g["take"]], g[~g["take"]]
        out.append({"sleeve": s, "n": len(g), "skip_pct": round(100 * len(sk) / len(g), 1),
                    "R_all": round(g.R.mean(), 4), "R_take": round(tk.R.mean(), 4) if len(tk) else None,
                    "R_skip": round(sk.R.mean(), 4) if len(sk) else None,
                    "total_all": round(g.R.sum(), 1), "total_take": round(tk.R.sum(), 1),
                    "pf_all": _pf(g.R), "pf_take": _pf(tk.R) if len(tk) else None})
    return out


def stats_of(d, n_perm=5000, seed=0):
    """d: sleeve, R, take (bool), quality. Pre-registered statistics (permutation within sleeve)."""
    rng = np.random.default_rng(seed)
    R, take = d.R.to_numpy(float), d["take"].to_numpy(bool)
    groups = [np.flatnonzero(d.sleeve.to_numpy() == s) for s in d.sleeve.unique()]
    diff = lambda tk: R[tk].mean() - R[~tk].mean() if tk.any() and (~tk).any() else 0.0
    obs = diff(take)
    # quality vs R: rank correlation within sleeve, weighted by the number of cases
    zq, zr = np.zeros(len(d)), np.zeros(len(d))
    q = d.quality.to_numpy(float)
    for g in groups:
        for z, v in ((zq, q[g]), (zr, R[g])):
            rk = pd.Series(v).rank().to_numpy()
            z[g] = (rk - rk.mean()) / rk.std() if rk.std() > 0 else 0.0
    rho = float((zq * zr).mean())
    ge_d = ge_r = 0
    for _ in range(n_perm):
        tk, zp = take.copy(), zq.copy()
        for g in groups:
            p = rng.permutation(len(g))
            tk[g], zp[g] = take[g][p], zq[g][p]
        ge_d += diff(tk) >= obs
        ge_r += (zp * zr).mean() >= rho
    sk = R[~take]
    return {"n": int(len(d)), "skip_pct": round(100 * float((~take).mean()), 1),
            "R_take_minus_skip": round(float(obs), 4), "p_H1": round((ge_d + 1) / (n_perm + 1), 4),
            "R_skip": round(float(sk.mean()), 4) if len(sk) else None,
            "H1": bool((ge_d + 1) / (n_perm + 1) <= 0.05 and obs > 0), "H2": bool(len(sk) > 0 and sk.mean() <= 0),
            "rank_corr_quality_R": round(rho, 4), "p_rank_corr": round((ge_r + 1) / (n_perm + 1), 4),
            "table": _table(d)}


def show_stats(st, title):
    print(f"\n== {title}: n {st['n']}, skipped {st['skip_pct']}% | R(take) - R(skip) = {st['R_take_minus_skip']:+.4f} "
          f"(p {st['p_H1']}) | R(skip) = {st['R_skip']} | H1 {st['H1']} H2 {st['H2']} | "
          f"rank corr quality~R {st['rank_corr_quality_R']:+.4f} (p {st['p_rank_corr']})")
    print(pd.DataFrame(st["table"]).to_string(index=False))


# ------------------------------------------------------------------------------------------ fitted baseline
def baseline():
    cases, _, _ = load()
    meta = {"id", "sleeve", "name", "sym", "period", "entry_time", "R"}
    feats = [c for c in cases.columns if c not in meta]
    parts = []
    for s, g in cases.groupby("sleeve"):
        a, v = g[g.period == "is"], g[g.period == "val"]
        cols = [c for c in feats if a[c].notna().mean() > 0.9 and a[c].std() > 0]
        med, mu, sd = a[cols].median(), None, None
        Xa, Xv = a[cols].fillna(med), v[cols].fillna(med)
        mu, sd = Xa.mean(), Xa.std()
        Xa, Xv = ((Xa - mu) / sd).clip(-5, 5).to_numpy(), ((Xv - mu) / sd).clip(-5, 5).to_numpy()
        y = a.R.clip(*a.R.quantile([0.01, 0.99])).to_numpy()
        beta = np.linalg.solve(Xa.T @ Xa + len(a) * np.eye(len(cols)), Xa.T @ (y - y.mean()))
        pa, pv = Xa @ beta, Xv @ beta
        parts.append(pd.DataFrame({"id": v.id.to_numpy(), "sleeve": s, "R": v.R.to_numpy(),
                                   "take": pv >= np.percentile(pa, 30), "quality": pv}))
    d = pd.concat(parts)
    st = stats_of(d)
    json.dump(st, open(os.path.join(OUT, "baseline.json"), "w"), indent=1)
    show_stats(st, "fitted baseline (ridge on the numeric sheet), validation 2022-2025")


# ------------------------------------------------------------------------------------------ model runs
def _run_dir(name):
    d = os.path.join(OUT, "runs", name)
    os.makedirs(d, exist_ok=True)
    return d


def _meta(name, **kw):
    p = os.path.join(_run_dir(name), "meta.json")
    m = json.load(open(p)) if os.path.exists(p) else {}
    m.update(kw)
    json.dump(m, open(p, "w"), indent=1)
    return m


def _done(name):
    p = os.path.join(_run_dir(name), "decisions.jsonl")
    return {json.loads(x)["id"] for x in open(p)} if os.path.exists(p) else set()


def run(name, period, per_sleeve, model, effort, workers=4, mode="pct", sheets=None):
    """Live (synchronous) calls: for the in-sample pilot and small checks."""
    cases, texts, stats = load(sheets)
    todo = pick(cases, period, per_sleeve)
    todo = todo[~todo.id.isin(_done(name))]
    _meta(name, model=model, effort=effort, period=period, per_sleeve=per_sleeve, mode="live", sheet_mode=mode,
          sheets=sheets or "sheets.parquet", prompt=judge.prompt_hash(mode))
    cl = judge.client()

    def one(row):
        try:
            return {"id": row["id"], **judge.decide(cl, model, system_for(row, stats, mode), texts[row["id"]], effort)}
        except Exception as e:                                   # noqa: BLE001  (logged, the case stays undone)
            return {"id": row["id"], "error": f"{type(e).__name__}: {e}"[:300]}

    spent = 0.0
    with open(os.path.join(_run_dir(name), "decisions.jsonl"), "a") as f, cf.ThreadPoolExecutor(workers) as ex:
        for k, res in enumerate(ex.map(one, todo.to_dict("records")), 1):
            if "error" in res:
                print("error", res["id"], res["error"], flush=True)
                continue
            spent += judge.cost(res["usage"], model)
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            f.flush()
            if k % 20 == 0:
                print(f"{k}/{len(todo)} done, {spent:.2f} USD so far", flush=True)
    print(f"{name}: {len(todo)} calls, {spent:.2f} USD")


def submit(name, period, per_sleeve, model, effort, mode="pct", sheets=None):
    """Batch API (half price, results usually within the hour)."""
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    cases, texts, stats = load(sheets)
    todo = pick(cases, period, per_sleeve)
    reqs = [Request(custom_id=row["id"], params=MessageCreateParamsNonStreaming(
        **judge.request(model, system_for(row, stats, mode), texts[row["id"]], effort))) for row in todo.to_dict("records")]
    b = judge.client().messages.batches.create(requests=reqs)
    _meta(name, model=model, effort=effort, period=period, per_sleeve=per_sleeve, mode="batch", batch_id=b.id,
          n=len(reqs), sheet_mode=mode, sheets=sheets or "sheets.parquet", prompt=judge.prompt_hash(mode))
    print(f"{name}: batch {b.id} submitted with {len(reqs)} requests")


def collect(name, wait=False):
    m = _meta(name)
    cl = judge.client()
    while True:
        b = cl.messages.batches.retrieve(m["batch_id"])
        print(f"{name}: {b.processing_status} | {b.request_counts}", flush=True)
        if b.processing_status == "ended" or not wait:
            break
        time.sleep(60)
    if b.processing_status != "ended":
        return
    spent, n = 0.0, 0
    with open(os.path.join(_run_dir(name), "decisions.jsonl"), "w") as f:
        for r in cl.messages.batches.results(m["batch_id"]):
            if r.result.type != "succeeded":
                print("not done:", r.custom_id, r.result.type)
                continue
            res = {"id": r.custom_id, **judge.parse(r.result.message)}
            spent += judge.cost(res["usage"], m["model"], batch=True)
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
            n += 1
    _meta(name, collected=n, cost_usd=round(spent, 2))
    print(f"{name}: {n} results, {spent:.2f} USD")


def by_year(d):
    """H3: gap taken - skipped per calendar year, and with each year left out."""
    rows = []
    for y, g in list(d.groupby("year")) + [(f"without {y}", d[d.year != y]) for y in sorted(d.year.unique())]:
        tk, sk = g[g["take"]], g[~g["take"]]
        rows.append({"year": str(y), "n": len(g), "skip_pct": round(100 * len(sk) / len(g), 1), "R_take": round(tk.R.mean(), 4),
                     "R_skip": round(sk.R.mean(), 4) if len(sk) else None,
                     "gap": round(tk.R.mean() - sk.R.mean(), 4) if len(sk) and len(tk) else None})
    yrs = [r for r in rows if not r["year"].startswith("without")]
    out = [r for r in rows if r["year"].startswith("without")]
    h3 = sum((r["gap"] or 0) > 0 for r in yrs) >= 3 and all((r["gap"] or 0) > 0 for r in out)
    return {"H3": bool(h3), "table": rows}


def analyse(name):
    cases, _, _ = load()
    m = _meta(name)
    d = pd.DataFrame([json.loads(x) for x in open(os.path.join(_run_dir(name), "decisions.jsonl"))])
    u = pd.DataFrame(list(d.usage))
    live = m.get("mode") != "batch"
    spent = sum(judge.cost(x, m["model"], batch=not live) for x in d.usage)
    print(f"{name}: model {m['model']}, effort {m['effort']}, {len(d)} answers, no decision {int(d.decision.isna().sum())} "
          f"({d.stop_reason.value_counts().to_dict()})")
    print(f"tokens per call: in {u['in'].mean():.0f} (+ cache read {u.cache_read.mean():.0f}, write {u.cache_write.mean():.0f}), "
          f"out {u.out.mean():.0f} | {spent:.2f} USD = {spent / len(d) * 100:.2f} cents per call")
    d = d[d.decision.notna()].merge(cases[["id", "sleeve", "R", "period", "entry_time"]], on="id")
    d["take"] = d.decision == "take"
    d["year"] = pd.DatetimeIndex(d.entry_time).year
    st = stats_of(d)
    st["usd"] = round(spent, 2)
    st["by_year"] = by_year(d)
    json.dump(st, open(os.path.join(_run_dir(name), "summary.json"), "w"), indent=1)
    show_stats(st, f"{name} ({'/'.join(sorted(d.period.unique()))})")
    print(f"\nH3 (robust to any single year): {st['by_year']['H3']}")
    print(pd.DataFrame(st["by_year"]["table"]).to_string(index=False))


def probe(name, model, n=150, workers=2, sheets=None, named=True):
    """Leak probe: can the model tell the year from an anonymous sheet? (named: the market's name is given)"""
    cases, texts, _ = load(sheets)
    c = probe_ids(cases, n)
    schema = {"type": "object", "properties": {"year": {"type": "integer"}}, "required": ["year"], "additionalProperties": False}
    cl = judge.client()

    def one(row):
        try:
            return ask(row)
        except Exception as e:                                   # noqa: BLE001  (a failed call is one sheet less, not a crash)
            print("error", row["id"], f"{type(e).__name__}: {e}"[:200], flush=True)
            return {"id": row["id"], "year": row["year"], "guess": None}

    def ask(row):
        msg = cl.messages.create(
            model=model, max_tokens=judge.MAX_TOKENS,
            system="This is a snapshot of a financial market at one moment between 2013 and 2025, with the date removed. "
                   "Guess the calendar year. Answer with the JSON object only.",
            messages=[{"role": "user", "content": (f"Asset: {ASSET[row['sym']]}\n\n" if named else "") + texts[row["id"]]}],
            output_config={"effort": "medium", "format": {"type": "json_schema", "schema": schema}})
        txt = next((b.text for b in msg.content if b.type == "text"), None) if msg.stop_reason == "end_turn" else None
        return {"id": row["id"], "year": row["year"], "guess": json.loads(txt)["year"] if txt else None}

    with cf.ThreadPoolExecutor(workers) as ex:
        d = pd.DataFrame(list(ex.map(one, c.to_dict("records")))).dropna()
    d.to_json(os.path.join(_run_dir(name), "probe.jsonl"), orient="records", lines=True)
    rho = d.year.rank().corr(d.guess.rank())
    print(f"{name}: {len(d)} sheets | exact year {100 * (d.year == d.guess).mean():.0f}% | within one year "
          f"{100 * ((d.year - d.guess).abs() <= 1).mean():.0f}% | rank correlation guess~year {rho:+.2f} "
          f"({'LEAK: tighten the sheet' if rho > 0.3 else 'anonymous enough'})")


def show(cid=None, mode="pct", sheets=None):
    cases, texts, stats = load(sheets)
    cases = cases[cases.id.isin(texts.index)]
    row = (cases[cases.id == cid] if cid else cases[cases.period == "is"].sample(1, random_state=1)).iloc[0].to_dict()
    sysb = system_for(row, stats, mode)[0]["text"]
    print("=" * 30, "SYSTEM", "=" * 30, "\n" + sysb, "\n" + "=" * 30, "USER (the sheet)", "=" * 30, "\n" + texts[row["id"]])
    print("=" * 78, f"\ncase {row['id']} | system {len(sysb)} chars | sheet {len(texts[row['id']])} chars | prompt {judge.prompt_hash(mode)}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["build", "blind", "show", "baseline", "run", "submit", "collect", "probe", "analyse"])
    ap.add_argument("--mode", default="pct", choices=["pct", "blind", "blind_named"])
    ap.add_argument("--sheets")
    ap.add_argument("--probe-only", action="store_true")
    ap.add_argument("case", nargs="?")
    ap.add_argument("--name")
    ap.add_argument("--period", default="is", choices=["is", "val"])
    ap.add_argument("--per-sleeve", type=int)
    ap.add_argument("--model", default=judge.MODEL)
    ap.add_argument("--effort", default="medium")
    ap.add_argument("--wait", action="store_true")
    a = ap.parse_args()
    if a.cmd == "build":
        build()
    elif a.cmd == "blind":        # scale-free sheets: --mode blind | blind_named ; --probe-only = the leak-probe sample
        ids = probe_ids(pd.read_parquet(os.path.join(OUT, "cases.parquet"))).id if a.probe_only else None
        make_blind(a.sheets, named=a.mode == "blind_named", ids=ids)
    elif a.cmd == "show":
        show(a.case, a.mode, a.sheets)
    elif a.cmd == "baseline":
        baseline()
    elif a.cmd == "run":
        run(a.name, a.period, a.per_sleeve, a.model, a.effort, mode=a.mode, sheets=a.sheets)
    elif a.cmd == "submit":
        submit(a.name, a.period, a.per_sleeve, a.model, a.effort, mode=a.mode, sheets=a.sheets)
    elif a.cmd == "collect":
        collect(a.name, a.wait)
    elif a.cmd == "probe":
        probe(a.name, a.model, sheets=a.sheets, named=a.mode != "blind")
    elif a.cmd == "analyse":
        analyse(a.name)
