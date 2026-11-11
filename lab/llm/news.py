"""Pre-registered test: does a language model that READS market-moving statements predict the next hour?

Written on 2026-11-11, before any model answer and before any look at prices after a post.

WHY. Two blind tests showed that the model has no skill at reading charts (numbers, then images). The one use
of a language model never tested here is reading text. The test needs (1) text that moves markets, time-stamped
to the second, and (2) a period the model cannot know: its knowledge stops in June 2026.
Source: the Truth Social posts of the President of the United States, 2026-07-01 to 2026-11-10, from a public
archive (llm/news_fetch.py); creation times agree with the post ids to the second. Re-posts of other accounts
are excluded (their re-post time is not published).

WHAT THE MODEL SEES. One post at a time: its text, its publication time (New York), and the start of the
previous own posts of the last 48 hours (at most 8). No price, nothing after the post.
WHAT IT ANSWERS. impact: none / minor / major (will this post move markets within the hour?); a direction
(up / down / flat) for the Nasdaq 100, gold, EUR/USD and bitcoin; whether the post brings new information.

HOW A CALL IS SCORED (mid prices, one-minute bars of the same data vendor as the rest of the lab)
- A call = a post with impact minor or major and a direction up or down for a market.
- Entry at the open of the first minute bar starting at or after (post time + 2 minutes), if one starts
  within 5 minutes (otherwise the market is closed: no call). Bitcoin: no entry from Friday 16:55 to Sunday
  17:00 New York (the broker is closed).
- Exit at the open of the first bar at or after entry + H, H = 60 minutes (primary), 15 and 240 (secondary); if
  no bar starts within 5 minutes of that time the call is dropped for that horizon.
- One position per market: a call is dropped if a counted call on the same market started less than 60 minutes
  earlier.
- Signed return in basis points; z = signed return / the standard deviation of all 60-minute returns of that
  market over the period. Net = gross minus the round-trip cost of the user's account (us100 0.8 bp, gold
  1.1 bp, eurusd 0.85 bp, bitcoin 4.0 bp, slippage included).

PRIMARY HYPOTHESIS (one test)
H1: the mean z at 60 minutes, all four markets pooled, is positive, with p <= 0.05 against the null "the
    directions carry no information" (5,000 shuffles of the directions among the counted calls of the same
    market), AND the mean net return is positive.
Fewer than 40 counted calls = inconclusive, whatever the mean.

SECONDARY (reported, never promoted to a success): major calls alone; each market; 15 and 240 minutes; entry
delayed to 5 and 10 minutes after the post (a robot polling a feed is not instant); the move between 10
minutes before the post and the entry (how much is gone before one can act); the same calls at the same clock
time on the five previous and five next trading days (placebo); by month.

MODEL. claude-fable-5-2. A pilot of 40 posts is run first to measure the cost per post; its answers are not
scored. The effort level of the main run is "medium" if the projected cost of the main run is at most 45 USD,
otherwise "low". All posts are then sent in one batch.

DATA NOTE. The prices are July-November 2026 one-minute bars of us100, gold, eurusd and bitcoin, downloaded
for this test only (lab/data/llm/news/px, not committed). They are in the year reserved for the final test of
the rule portfolio; no rule is fitted, tuned or selected on them here.

    python3 lab/llm/news.py build              # posts -> results/llm/news/cases.parquet (what the model will see)
    (API calls: llm/runner.py, commands news_run / news_submit / news_collect)
    python3 lab/llm/news.py analyse <name>     # local: needs the price files
"""
import json
import os
import re
import sys

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
OUT = os.path.join(LAB, "results", "llm", "news")
PX = os.path.join(LAB, "data", "llm", "news", "px")
MODEL = "claude-fable-5-2"
T0, T1 = "2026-07-01 00:00:00", "2026-11-10 12:00:00"
MARKETS = {"us100": "usatechidxusd", "gold": "xauusd", "eurusd": "eurusd", "bitcoin": "btcusd"}
COST_BP = {"us100": 0.8, "gold": 1.1, "eurusd": 0.85, "bitcoin": 4.0}
NY = "America/New_York"

_DIR = {"type": "string", "enum": ["up", "down", "flat"]}
SCHEMA = {
    "type": "object",
    "properties": {
        "impact": {"type": "string", "enum": ["none", "minor", "major"]},
        "us100": _DIR, "gold": _DIR, "eurusd": _DIR, "bitcoin": _DIR,
        "new_information": {"type": "string", "enum": ["yes", "no"]},
        "reason_fr": {"type": "string"},
    },
    "required": ["impact", "us100", "gold", "eurusd", "bitcoin", "new_information", "reason_fr"],
    "additionalProperties": False,
}

SYSTEM = """You work for an automated trading robot. You read, at the moment it is published, one post written by the President of the United States on Truth Social, and you decide whether it will move financial markets during the next hour.

Markets: "us100" = Nasdaq 100 index, "gold" = gold in US dollars per ounce, "eurusd" = euro against US dollar (up = euro stronger, dollar weaker), "bitcoin" = bitcoin in US dollars.

What you are given: the post (text only: attached images and videos are not shown), its publication time in New York, and the beginning of his own earlier posts of the last 48 hours, for context. You know nothing about what happened after the post, and you are not shown any price.

How to judge:
- Most posts move nothing: endorsements, campaign messages, attacks on opponents or media, congratulations, ceremonies, polls, reposted praise, slogans. Answer impact "none" and "flat" everywhere.
- A post matters when it announces, threatens or reveals something NEW with economic consequences: tariffs and trade deals, sanctions, war, cease-fires and peace talks, the Federal Reserve and interest rates, the dollar, taxes and spending, energy, technology and crypto policy, a concrete measure against or for a named company or sector, or market-relevant facts not yet public.
- News that was already known, or the same message repeated, moves nothing: check the earlier posts.
- "minor" = a visible but small reaction is likely; "major" = the kind of post that moves an index by several tenths of a percent within minutes.
- Give a direction only for the markets you expect to react; "flat" for the others. If impact is "none", every market is "flat".
- The robot can only act about two minutes after the post. Judge the move from that point on, not the first seconds.

Answer with the JSON object only. "reason_fr": one short sentence in French."""


def _clean(t):
    return re.sub(r"\s+", " ", re.sub(r"https?://\S+", "", t)).strip()


def build():
    """One case per own post with text in the test period; `sheet` is exactly what the model reads."""
    p = pd.read_parquet(os.path.join(OUT, "posts.parquet"))
    p["clean"] = p.text.map(_clean)
    p = p[p.clean.str.len() >= 40].sort_values("time").reset_index(drop=True)
    ny = p.time.dt.tz_convert(NY)
    rows = []
    for i in range(len(p)):
        t = p.time[i]
        if not (pd.Timestamp(T0, tz="UTC") <= t <= pd.Timestamp(T1, tz="UTC")):
            continue
        j = i - 1
        prev = []
        while j >= 0 and len(prev) < 8 and (t - p.time[j]) <= pd.Timedelta(hours=48):
            ago = (t - p.time[j]).total_seconds() / 60
            when = f"{ago:.0f} min earlier" if ago < 120 else f"{ago / 60:.0f} h earlier"
            prev.append(f"- ({when}) {p.clean[j][:280]}")
            j -= 1
        ctx = "\n".join(reversed(prev)) if prev else "(none)"
        sheet = (f"PUBLICATION TIME (New York): {ny[i].strftime('%A %d %B %Y, %H:%M')}\n\n"
                 f"HIS EARLIER POSTS OF THE LAST 48 HOURS (oldest first, beginning of each):\n{ctx}\n\n"
                 f"THE POST TO JUDGE:\n{p.clean[i][:4000]}")
        rows.append({"id": f"p{int(p.mirror_id[i])}", "time": t, "n_chars": len(p.clean[i]), "sheet": sheet})
    d = pd.DataFrame(rows)
    d.to_parquet(os.path.join(OUT, "cases.parquet"))
    print(len(d), "cases", d.time.min(), "->", d.time.max(), "| sheet length median", int(d.sheet.str.len().median()),
          "max", int(d.sheet.str.len().max()))
    print(d.groupby(d.time.dt.strftime("%Y-%m")).size().to_dict())
    return d


# ------------------------------------------------------------------------------------------ API side (GitHub Actions)
def request(model, sheet, effort):
    return dict(model=model, max_tokens=8000, system=SYSTEM, messages=[{"role": "user", "content": sheet}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": SCHEMA}})


def parse(msg):
    u = msg.usage
    out = {"answer": None, "stop_reason": msg.stop_reason, "model": msg.model,
           "usage": {"in": u.input_tokens, "out": u.output_tokens, "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
                     "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0}}
    if msg.stop_reason == "end_turn":
        try:
            out["answer"] = json.loads(next(b.text for b in msg.content if b.type == "text"))
        except (StopIteration, ValueError):
            pass
    return out


def _run_dir(name):
    d = os.path.join(OUT, "runs", name)
    os.makedirs(d, exist_ok=True)
    return d


def _cases(n=None, seed=0):
    d = pd.read_parquet(os.path.join(OUT, "cases.parquet"))
    return d.sample(n, random_state=seed).sort_values("time") if n else d


def _summary(name, model, batch):
    from llm import judge
    d = pd.DataFrame([json.loads(x) for x in open(os.path.join(_run_dir(name), "decisions.jsonl"))])
    u = pd.DataFrame(list(d.usage))
    spent = sum(judge.cost(x, model, batch=batch) for x in d.usage)
    imp = pd.Series([a.get("impact") if isinstance(a, dict) else None for a in d.answer]).value_counts(dropna=False).to_dict()
    n_all = len(pd.read_parquet(os.path.join(OUT, "cases.parquet")))
    print(f"{name}: {len(d)} answers, {spent:.2f} USD = {100 * spent / max(len(d), 1):.2f} cents per post | tokens in {u['in'].mean():.0f} "
          f"out {u.out.mean():.0f} | impact {imp} | stop reasons {d.stop_reason.value_counts().to_dict()} | "
          f"projected batch cost for {n_all} posts at this effort: {0.5 * spent / max(len(d), 1) * n_all if not batch else spent:.1f} USD")
    return spent


def run_sync(name, n=40, model=MODEL, effort="medium", workers=4):
    """Pilot (live calls) to measure cost and check the answer format. Its answers are not scored."""
    import concurrent.futures as cf
    from llm import judge
    todo = _cases(n)
    cl = judge.client()
    json.dump({"model": model, "effort": effort, "n": len(todo), "mode": "live", "kind": "news"},
              open(os.path.join(_run_dir(name), "meta.json"), "w"), indent=1)

    def one(r):
        try:
            return {"id": r["id"], **parse(cl.messages.create(**request(model, r["sheet"], effort)))}
        except Exception as e:                                   # noqa: BLE001
            return {"id": r["id"], "error": f"{type(e).__name__}: {e}"[:300]}

    with open(os.path.join(_run_dir(name), "decisions.jsonl"), "w") as f, cf.ThreadPoolExecutor(workers) as ex:
        for res in ex.map(one, todo[["id", "sheet"]].to_dict("records")):
            if "error" in res:
                print("error", res["id"], res["error"], flush=True)
                continue
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
    _summary(name, model, batch=False)


def submit(name, model=MODEL, effort="medium"):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    from llm import judge
    recs = _cases()[["id", "sheet"]].to_dict("records")
    cl, ids = judge.client(), []
    for k in range(0, len(recs), 5000):
        reqs = [Request(custom_id=r["id"], params=MessageCreateParamsNonStreaming(**request(model, r["sheet"], effort))) for r in recs[k:k + 5000]]
        ids.append(cl.messages.batches.create(requests=reqs).id)
        print(f"{name}: batch {ids[-1]} submitted with {len(reqs)} requests", flush=True)
    json.dump({"model": model, "effort": effort, "n": len(recs), "mode": "batch", "kind": "news", "batch_ids": ids},
              open(os.path.join(_run_dir(name), "meta.json"), "w"), indent=1)


def collect(name, wait=True):
    import time
    from llm import judge
    mp = os.path.join(_run_dir(name), "meta.json")
    m = json.load(open(mp))
    cl = judge.client()
    while True:
        st = [cl.messages.batches.retrieve(b) for b in m["batch_ids"]]
        print(f"{name}:", [(b.processing_status, b.request_counts.succeeded, b.request_counts.processing) for b in st], flush=True)
        if all(b.processing_status == "ended" for b in st) or not wait:
            break
        time.sleep(60)
    if not all(b.processing_status == "ended" for b in st):
        return
    n = 0
    with open(os.path.join(_run_dir(name), "decisions.jsonl"), "w") as f:
        for bid in m["batch_ids"]:
            for r in cl.messages.batches.results(bid):
                if r.result.type != "succeeded":
                    print("not done:", r.custom_id, r.result.type)
                    continue
                f.write(json.dumps({"id": r.custom_id, **parse(r.result.message)}, ensure_ascii=False) + "\n")
                n += 1
    spent = _summary(name, m["model"], batch=True)
    m.update(collected=n, cost_usd=round(spent, 2))
    json.dump(m, open(mp, "w"), indent=1)


# ------------------------------------------------------------------------------------------ scoring (local)
def _px(market):
    f = MARKETS[market]
    b = pd.read_csv(os.path.join(PX, f"{f}-bid.csv"))
    a = pd.read_csv(os.path.join(PX, f"{f}-ask.csv"))
    d = b.merge(a, on="timestamp", suffixes=("_b", "_a"))
    d = d[(d.volume_b > 0) | (d.volume_a > 0)]
    t = pd.to_datetime(d.timestamp, unit="ms", utc=True)
    mid = ((d.open_b + d.open_a) / 2).to_numpy()
    if market == "bitcoin":                                       # the broker is closed at the weekend
        ny = t.dt.tz_convert(NY)
        wk = ny.dt.dayofweek.to_numpy()
        mins = (ny.dt.hour * 60 + ny.dt.minute).to_numpy()
        closed = ((wk == 4) & (mins >= 16 * 60 + 55)) | (wk == 5) | ((wk == 6) & (mins < 17 * 60))
        t, mid = t[~closed], mid[~closed]
    return t.dt.tz_localize(None).to_numpy().astype("datetime64[ns]"), mid


def _at(ts, when, tol_min=5):
    """Index of the first bar starting at or after `when` (array of datetime64), -1 if none within tol."""
    i = np.searchsorted(ts, when, side="left")
    ok = (i < len(ts))
    j = np.where(ok, i, len(ts) - 1)
    ok &= (ts[j] - when) <= np.timedelta64(tol_min, "m")
    return np.where(ok, j, -1)


def score(d, delay=2, horizons=(15, 60, 240)):
    """d: one row per (post, market) call with columns time (UTC), market, side. Adds entry / returns (bp)."""
    out = []
    for m in MARKETS:
        ts, mid = _px(m)
        x = d[d.market == m].sort_values("time").copy()
        if not len(x):
            continue
        t = x.time.dt.tz_convert("UTC").dt.tz_localize(None).to_numpy().astype("datetime64[ns]")
        e = _at(ts, t + np.timedelta64(delay, "m"))
        r60 = mid[60:] / mid[:-60] - 1                       # every 60-bar return whose two ends are 60 +/- 5 minutes apart
        ok60 = np.abs((ts[60:] - ts[:-60]) / np.timedelta64(1, "m") - 60) <= 5
        x["sd60_bp"] = float(np.std(r60[ok60]) * 1e4)
        x["entry_i"] = e
        x["entry_t"] = np.where(e >= 0, ts[np.maximum(e, 0)], np.datetime64("NaT"))
        for h in horizons:
            xi = _at(ts, np.where(e >= 0, ts[np.maximum(e, 0)], ts[0]) + np.timedelta64(h, "m"))
            good = (e >= 0) & (xi >= 0)
            ret = np.where(good, x.side.to_numpy() * (mid[np.maximum(xi, 0)] / mid[np.maximum(e, 0)] - 1) * 1e4, np.nan)
            x[f"r{h}"] = ret
        pre = _at(ts, t - np.timedelta64(10, "m"))
        x["pre"] = np.where((e >= 0) & (pre >= 0), x.side.to_numpy() * (mid[np.maximum(e, 0)] / mid[np.maximum(pre, 0)] - 1) * 1e4, np.nan)
        out.append(x)
    return pd.concat(out).sort_values("time").reset_index(drop=True) if out else d.iloc[:0]


def _dedup(x, gap=60):
    keep = []
    for m, g in x.groupby("market"):
        last = None
        for i, t in zip(g.index, g.entry_t):
            if pd.isna(t):
                continue
            if last is None or (t - last) >= np.timedelta64(gap, "m"):
                keep.append(i)
                last = t
    return x.loc[sorted(keep)]


def calls(name):
    c = pd.read_parquet(os.path.join(OUT, "cases.parquet"))[["id", "time"]]
    d = pd.DataFrame([json.loads(x) for x in open(os.path.join(_run_dir(name), "decisions.jsonl"))])
    d = d[d.answer.map(lambda a: isinstance(a, dict))].merge(c, on="id")
    rows = []
    for _, r in d.iterrows():
        a = r.answer
        if a["impact"] == "none":
            continue
        for m in MARKETS:
            if a[m] in ("up", "down"):
                rows.append({"id": r.id, "time": r.time, "market": m, "side": 1 if a[m] == "up" else -1, "impact": a["impact"],
                             "new": a["new_information"]})
    return d, pd.DataFrame(rows)


def analyse(name, n_perm=5000, seed=0):
    d, raw = calls(name)
    imp = d.answer.map(lambda a: a["impact"]).value_counts().to_dict()
    res = {"answers": int(len(d)), "impact": imp, "raw_calls": int(len(raw))}
    if not len(raw):
        res["verdict"] = "no call at all: inconclusive"
        json.dump(res, open(os.path.join(_run_dir(name), "summary.json"), "w"), indent=1)
        print(json.dumps(res, indent=1))
        return res
    x = _dedup(score(raw))
    x = x[x.r60.notna()].copy()
    x["z"] = x.r60 / x.sd60_bp
    x["net"] = x.r60 - x.market.map(COST_BP)
    rng = np.random.default_rng(seed)

    def perm_p(g):
        obs, null = g.z.mean(), []
        parts = [(gg.r60.to_numpy() * gg.side.to_numpy() / gg.sd60_bp.to_numpy(), gg.side.to_numpy())
                 for _, gg in g.groupby("market")]              # the market's own move in z units, and the sides to shuffle
        for _ in range(n_perm):
            null.append(np.concatenate([mv * rng.permutation(s) for mv, s in parts]).mean())
        return float((np.array(null) >= obs).mean())

    def block(g):
        if not len(g):
            return {"n": 0}
        return {"n": int(len(g)), "mean_z": round(float(g.z.mean()), 3), "gross_bp": round(float(g.r60.mean()), 2),
                "net_bp": round(float(g.net.mean()), 2), "win_pct": round(float((g.r60 > 0).mean() * 100), 1),
                "t": round(float(g.z.mean() / g.z.std(ddof=1) * np.sqrt(len(g))), 2) if len(g) > 2 else None,
                "p_shuffle": round(perm_p(g), 4) if len(g) >= 10 else None,
                "r15_bp": round(float(g.r15.mean()), 2), "r240_bp": round(float(g.r240.mean()), 2),
                "pre_move_bp": round(float(g.pre.mean()), 2), "up_share": round(float((g.side > 0).mean()), 2)}

    res["primary"] = block(x)
    res["major_only"] = block(x[x.impact == "major"])
    res["new_information_only"] = block(x[x.new == "yes"])
    res["by_market"] = {m: block(g) for m, g in x.groupby("market")}
    res["by_month"] = {k: block(g) for k, g in x.groupby(x.time.dt.strftime("%Y-%m"))}
    for dl in (5, 10):                                           # latency
        y = _dedup(score(raw, delay=dl))
        y = y[y.r60.notna()]
        res[f"delay_{dl}min"] = {"n": int(len(y)), "gross_bp": round(float(y.r60.mean()), 2),
                                 "mean_z": round(float((y.r60 / y.sd60_bp).mean()), 3)}
    plc = []                                                     # placebo: same calls, same clock time, other days
    for k in (-5, -4, -3, -2, -1, 1, 2, 3, 4, 5):
        y = raw[raw.id.isin(x.id)].copy()
        y["time"] = [t + pd.offsets.BDay(k) for t in y.time]
        y = score(y)
        y = y[y.r60.notna()]
        if len(y):
            plc.append(float((y.r60 / y.sd60_bp).mean()))
    res["placebo_other_days_mean_z"] = {"mean": round(float(np.mean(plc)), 3), "sd": round(float(np.std(plc)), 3), "n_sets": len(plc)} if plc else None
    p = res["primary"]
    if p["n"] < 40:
        res["verdict"] = f"inconclusive: {p['n']} counted calls (< 40)"
    else:
        ok = p["mean_z"] > 0 and (p["p_shuffle"] is not None and p["p_shuffle"] <= 0.05) and p["net_bp"] > 0
        res["verdict"] = "H1 confirmed" if ok else "H1 not confirmed"
    x.drop(columns=["entry_i"]).to_csv(os.path.join(_run_dir(name), "calls_scored.csv"), index=False)
    json.dump(res, open(os.path.join(_run_dir(name), "summary.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))
    return res


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    elif sys.argv[1] == "analyse":
        analyse(sys.argv[2])
