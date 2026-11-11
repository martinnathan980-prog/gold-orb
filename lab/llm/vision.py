"""Blind test with chart images: "you are the trader" (the user's second claim).

The first blind test (experiment.py) asked Claude for a go / no-go on rule signals from numbers only: no
value. What it did not test, and what the user believes makes the difference: real chart pictures and
complete freedom. Here, at random moments of the gold session, the model receives three candlestick
charts (15 minutes, 1 hour, daily: Bollinger bands and daily pivots drawn as on the user's screen) plus
the scale-free context sheet, and decides freely: buy, sell or wait, with its own stop, target and size.
No date, no price level, no market name: distances are in units of the market's daily ATR.

PRE-REGISTERED 2026-11-11, before any model call of this test.
  Cases: gold, Monday-Friday, 03:00-15:30 New York, on 15-minute boundaries, drawn at random at least
  45 minutes apart. Pilot on in-sample moments (before 2022); test on 2022-2025.
  Trade evaluation (identical for every answer): entry at the mid price of the decision minute; stop and
  target as chosen; otherwise exit at 16:50 New York; cost = the spread of that minute + 0.3 bp entry
  slippage + 1 bp when stopped; result in R (R = the chosen stop distance); size 2 doubles the result.
  Primary: mean net R of the model's trades > 0, AND better than the same trades given to random moments
  (permutation of the answers across cases, 5,000 draws, one-sided p <= 0.05).
  Secondary: direction hit rate (does price first move 0.25 dATR the chosen way), size-2 trades vs size-1,
  conviction vs result, by year (robust only if positive in 3 of 4 years).
  Leak probe first (year guess from the same images + sheet): rank correlation with the true year <= 0.3.
  Model: the most capable one, claude-fable-5-2, at its default effort (high). No server-side fallback, on
  purpose: another model answering would contaminate the measurement; a refusal counts as "wait".

Local (needs the market data):  python3 llm/vision.py build | analyse --name N
Remote (needs the API key):     requests "vision_run" / "vision_submit" / "vision_probe" handled by runner.py
"""
import base64
import io
import json
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
OUT = os.path.join(LAB, "results", "llm")
NPZ = os.path.join(OUT, "vision_cases.npz")
META = os.path.join(OUT, "vision_cases.parquet")
MODEL = "claude-fable-5-2"
N15, N60, ND = 96, 96, 60
PIV = ["S3", "S2", "S1", "P", "R1", "R2", "R3"]

SCHEMA = {
    "type": "object",
    "properties": {
        "action": {"type": "string", "enum": ["buy", "sell", "wait"]},
        "size": {"type": "string", "enum": ["1", "2"]},
        "stop_datr": {"type": "string", "enum": ["0.15", "0.25", "0.50"]},
        "target": {"type": "string", "enum": ["1R", "2R", "3R", "none"]},
        "conviction": {"type": "integer"},
        "reason_fr": {"type": "string"},
    },
    "required": ["action", "size", "stop_datr", "target", "conviction", "reason_fr"],
    "additionalProperties": False,
}

SYSTEM = """You are the trader. An automated robot shows you the market at one moment and executes exactly what you decide.

What you see
- Three candlestick charts of the same market at this moment: 15-minute bars (about one day), 1-hour bars (about four days) and daily bars (about three months). On the two intraday charts the Bollinger bands (20, 2) are drawn, and the daily pivot points (P, R1-R3, S1-S3) as horizontal lines. The current price is the dotted line at 0. The vertical scale is the distance from the current price in dATR (the market's average daily range over the last 14 days). Time runs left to right; the right edge is now.
- A context sheet with the same moment in numbers (clock, session, levels, trend, momentum, volatility, recent bars).
- There is deliberately no date, no price level, no market name and no news.

What you decide
- action: "buy", "sell" or "wait". Waiting is a real decision: trade only when you see an edge. Every trade costs about 0.03 to 0.08 R in spread and slippage.
- stop_datr: your stop distance from the entry, "0.15", "0.25" or "0.50" dATR. This distance is your risk, 1 R.
- target: "1R", "2R", "3R", or "none" to hold until the end of the session (16:50 New York), where every position is closed.
- size: "1" normally, "2" to double the stake when you are exceptionally confident.
- conviction: integer 0-100.
- reason_fr: one short sentence in French (25 words at most).
When you wait, still fill the other fields (they are ignored).

Answer with the JSON object only."""

PROBE_SYSTEM = ("These charts and this sheet show a financial market at one moment between 2013 and 2025, with the date, the price "
                "level and the market's name removed. Guess the calendar year. Answer with the JSON object only.")
PROBE_SCHEMA = {"type": "object", "properties": {"year": {"type": "integer"}}, "required": ["year"], "additionalProperties": False}


# ------------------------------------------------------------------------------------------ charts
def _candles(ax, o, h, l, c):
    x = np.arange(len(c)) - len(c) + 1
    up = c >= o
    for m, col in ((up, "#1a9d6c"), (~up, "#d94a4a")):
        ax.vlines(x[m], l[m], h[m], color=col, lw=0.9, zorder=3)
        ax.bar(x[m], np.maximum(np.abs(c[m] - o[m]), 1e-9), bottom=np.minimum(o[m], c[m]), width=0.62, color=col, zorder=3)
    return x


def render(case):
    """case: dict of arrays in dATR units (see build). Returns three PNG images as bytes."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    out = []
    for key, bb, title, xlab in (("b15", "bb15", "15-minute bars, Bollinger bands (20, 2), daily pivots", "bars (right edge = now, 4 bars = 1 hour)"),
                                 ("b60", "bb60", "1-hour bars, Bollinger bands (20, 2), daily pivots", "bars (right edge = now, 24 bars = 1 day)"),
                                 ("bD", None, "daily bars", "bars (right edge = yesterday's bar)")):
        b = case[key]
        b = b[np.isfinite(b).all(axis=1)]
        fig, ax = plt.subplots(figsize=(9.0, 5.6), dpi=100)
        x = _candles(ax, b[:, 0], b[:, 1], b[:, 2], b[:, 3])
        lo, hi = float(b[:, 2].min()), float(b[:, 1].max())
        if bb is not None:
            w = case[bb][-len(b):]
            ok = np.isfinite(w).all(axis=1)
            ax.plot(x[ok], w[ok, 0], color="#2a6fdb", lw=1.1, zorder=2)
            ax.plot(x[ok], w[ok, 1], color="#d94a4a", lw=1.0, zorder=2)
            ax.plot(x[ok], w[ok, 2], color="#1a9d6c", lw=1.0, zorder=2)
            ax.fill_between(x[ok], w[ok, 2], w[ok, 1], color="#2a6fdb", alpha=0.06, zorder=1)
            lo, hi = min(lo, float(np.nanmin(w[ok, 2]))), max(hi, float(np.nanmax(w[ok, 1])))
            pad = 0.08 * (hi - lo)
            for name, v in zip(PIV, case["piv"]):
                if lo - pad <= v <= hi + pad:
                    ax.axhline(v, color="#e08a00", lw=1.0, zorder=2)
                    ax.text(x[0], v, f" {name}", color="#a86400", fontsize=10, va="bottom", ha="left")
        pad = 0.08 * (hi - lo)
        ax.set_ylim(lo - pad, hi + pad)
        ax.axhline(0.0, color="#333333", lw=0.9, ls=":", zorder=2)
        ax.set_xlim(x[0] - 1, 3)
        ax.set_title(title, fontsize=12, loc="left")
        ax.set_xlabel(xlab, fontsize=10)
        ax.set_ylabel("distance from the current price (dATR)", fontsize=10)
        ax.grid(color="#e6e6e6", lw=0.6)
        ax.set_axisbelow(True)
        for sp in ("top", "right"):
            ax.spines[sp].set_visible(False)
        buf = io.BytesIO()
        fig.savefig(buf, format="png")
        plt.close(fig)
        out.append(buf.getvalue())
    return out


def content(case, text, head=""):
    """User message: the three charts, then the sheet."""
    imgs = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.standard_b64encode(p).decode()}}
            for p in render(case)]
    return imgs + [{"type": "text", "text": head + text}]


def load_cases():
    z = np.load(NPZ)
    meta = pd.read_parquet(META)
    cases = {cid: {k: z[k][n] for k in ("b15", "bb15", "b60", "bb60", "bD", "piv")} for n, cid in enumerate(meta.id)}
    return meta, cases


def request(model, case, text, effort, system=SYSTEM, schema=SCHEMA):
    return dict(model=model, max_tokens=12000, system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": content(case, text)}],
                output_config={"effort": effort, "format": {"type": "json_schema", "schema": schema}})


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


# ------------------------------------------------------------------------------------------ build (local)
def _grid(mk, width):
    key = mk.tmin // width
    first = np.r_[0, np.flatnonzero(np.diff(key)) + 1]
    last = np.r_[first[1:], len(key)] - 1
    b = pd.DataFrame({"end": key[first] * width + width, "o": mk.o[first], "h": np.maximum.reduceat(mk.h, first),
                      "l": np.minimum.reduceat(mk.l, first), "c": mk.c[last]})
    b["mid"] = b.c.rolling(20).mean()
    b["sd"] = b.c.rolling(20).std(ddof=0)
    return b


def build(n_is=150, n_val=800, seed=0):
    from goldlab import r2
    from goldlab.data import NY
    from llm.context import Market
    mk, ref = Market("xauusd"), Market("us100")
    r2.free()
    ny = mk.index.tz_convert(NY)
    nym = (ny.hour * 60 + ny.minute).to_numpy()
    ok = (ny.dayofweek < 5) & (nym >= 180) & (nym <= 930) & (nym % 15 == 0)
    g15, g60 = _grid(mk, 15), _grid(mk, 60)
    e15, e60 = g15.end.to_numpy(), g60.end.to_numpy()
    rng = np.random.default_rng(seed)
    rows, arr = [], {k: [] for k in ("b15", "bb15", "b60", "bb60", "bD", "piv")}
    for period, a, b, n in (("is", "2014-01-01", "2022-01-01", n_is), ("val", "2022-01-01", "2026-01-01", n_val)):
        lo, hi = mk.index.searchsorted(pd.Timestamp(a, tz="UTC")), mk.index.searchsorted(pd.Timestamp(b, tz="UTC"))
        cand = np.flatnonzero(ok[lo:hi]) + lo
        pick, taken = [], np.zeros(0, np.int64)
        for i in rng.permutation(cand):
            if len(pick) >= n:
                break
            if len(taken) and np.abs(mk.tmin[taken] - mk.tmin[i]).min() < 45:
                continue
            sc = mk._scales(mk.index[i])
            if sc is None:
                continue
            full, _, _, A, _ = sc
            k15 = int(np.searchsorted(e15, mk.tmin[i], side="right")) - 1
            k60 = int(np.searchsorted(e60, mk.tmin[i], side="right")) - 1
            if k15 < 200 or k60 < 200 or len(full) < ND:
                continue
            px = float(mk.o[i])
            text = mk.sheet_blind(i, 1, px, px - 0.25 * A, ref=ref)
            if text is None:
                continue
            L = text.split("\n")
            assert L[0] == "SIGNAL" and L[1].startswith("market:") and L[2].startswith("stop:")
            text = "\n".join(["DECISION POINT", "market: (name hidden) | you decide: buy, sell or wait", L[3]] + L[4:])
            n_ = lambda v: ((np.asarray(v, float) - px) / A).astype(np.float32)
            s15, s60 = g15.iloc[k15 - N15 + 1:k15 + 1], g60.iloc[k60 - N60 + 1:k60 + 1]
            arr["b15"].append(n_(s15[["o", "h", "l", "c"]]))
            arr["bb15"].append(n_(np.c_[s15.mid, s15.mid + 2 * s15.sd, s15.mid - 2 * s15.sd]))
            arr["b60"].append(n_(s60[["o", "h", "l", "c"]]))
            arr["bb60"].append(n_(np.c_[s60.mid, s60.mid + 2 * s60.sd, s60.mid - 2 * s60.sd]))
            d = full[-ND:]
            arr["bD"].append(n_(np.c_[mk.d_o[d], mk.d_h[d], mk.d_l[d], mk.d_c[d]]))
            H, Lw, C = mk.d_h[full[-1]], mk.d_l[full[-1]], mk.d_c[full[-1]]
            P = (H + Lw + C) / 3
            arr["piv"].append(n_([2 * P - (2 * H - Lw), P - (H - Lw), 2 * P - H, P, 2 * P - Lw, P + (H - Lw), 2 * P + (H - 2 * Lw)]))
            rows.append({"id": f"v{period}-{len(pick):04d}", "period": period, "t": mk.index[i], "i": int(i), "px": px, "atr": float(A),
                         "spread": float(mk.spr[i - 1]), "text": text})
            pick.append(i)
            taken = np.array(pick)
        print(period, len(pick), "cases", flush=True)
    np.savez_compressed(NPZ, **{k: np.stack(v) for k, v in arr.items()})
    pd.DataFrame(rows).to_parquet(META, index=False)
    print("saved", len(rows), "cases |", round(os.path.getsize(NPZ) / 1e6, 1), "MB")


# ------------------------------------------------------------------------------------------ outcome and analysis (local)
def outcome(mk, i, px, atr, spread, action, stop_k, target, eod):
    """Net R of one decision (0 for wait). Mid-price path, stop first when both are hit inside one minute."""
    if action == "wait":
        return 0.0, 0.0
    s = 1 if action == "buy" else -1
    risk = stop_k * atr
    stop = px - s * risk
    tgt = px + s * risk * {"1R": 1, "2R": 2, "3R": 3}.get(target, 1e9)
    cost = spread + 0.3e-4 * px
    for j in range(i, eod):
        hit_s = mk.l[j] <= stop if s == 1 else mk.h[j] >= stop
        hit_t = mk.h[j] >= tgt if s == 1 else mk.l[j] <= tgt
        if hit_s:
            return -1.0 - (cost + 1e-4 * px) / risk, -1.0
        if hit_t:
            g = abs(tgt - px) / risk
            return g - cost / risk, g
    g = s * (mk.c[eod - 1] - px) / risk
    return g - cost / risk, g


def analyse(name, n_perm=5000):
    from goldlab import r2
    from goldlab.data import NY
    from llm.context import Market
    mk = Market("xauusd")
    r2.free()
    meta = pd.read_parquet(META).set_index("id")
    run = os.path.join(OUT, "runs", name)
    d = pd.DataFrame([json.loads(x) for x in open(os.path.join(run, "decisions.jsonl"))]).set_index("id")
    d = d.join(meta[["period", "t", "i", "px", "atr", "spread"]])
    wait = {"action": "wait", "size": "1", "stop_datr": "0.25", "target": "2R", "conviction": 0, "reason_fr": ""}
    d = d.join(pd.DataFrame([a if isinstance(a, dict) else wait for a in d.answer], index=d.index))
    ny = mk.index.tz_convert(NY)
    nym = (ny.hour * 60 + ny.minute).to_numpy()
    # every possible answer on every moment: 2 sides x 3 stops x 4 targets
    combos = [(a, k, t) for a in ("buy", "sell") for k in ("0.15", "0.25", "0.50") for t in ("1R", "2R", "3R", "none")]
    col = {c: n for n, c in enumerate(combos)}
    tab = np.zeros((len(d), len(combos)))
    for n, (cid, r) in enumerate(d.iterrows()):
        j = int(r.i)                                              # the position is closed on the last bar before 16:50 New York
        while j < len(nym) - 1 and nym[j] < 1010 and mk.tmin[j + 1] - mk.tmin[j] < 30:
            j += 1
        for c, m in col.items():
            tab[n, m] = outcome(mk, int(r.i), r.px, r.atr, r.spread, c[0], float(c[1]), c[2], j + 1)[0]
    trade = (d.action != "wait").to_numpy()
    code = np.array([col.get((a, k, t), 0) for a, k, t in zip(d.action, d.stop_datr, d.target)])
    mult = np.where(d["size"].to_numpy() == "2", 2.0, 1.0)
    res = np.where(trade, tab[np.arange(len(d)), code] * mult, 0.0)
    d["R"] = res
    tr = d[trade]
    u = pd.DataFrame(list(d.usage))
    print(f"{name}: {len(d)} answers | no answer {int(d.answer.isna().sum())} | buy {int((d.action == 'buy').sum())} sell {int((d.action == 'sell').sum())} "
          f"wait {int((d.action == 'wait').sum())} | size 2: {int(((d['size'] == '2') & trade).sum())}")
    print(f"tokens per call: in {u['in'].mean():.0f} (+cache {u.cache_read.mean():.0f}) out {u.out.mean():.0f}")
    if trade.sum() == 0:
        return
    obs = float(res[trade].mean())
    rng = np.random.default_rng(0)
    null = np.empty(n_perm)
    for q in range(n_perm):                                       # the same answers handed to other moments
        p = rng.permutation(len(d))
        null[q] = (tab[np.arange(len(d)), code[p]] * mult[p])[trade[p]].mean()
    pval = (1 + (null >= obs).sum()) / (n_perm + 1)
    unit = res[trade] / mult[trade]
    print(f"trades {int(trade.sum())} ({100 * trade.mean():.0f}% of moments) | mean net R per trade {obs:+.4f} | total {res.sum():+.1f} R | winners "
          f"{100 * (unit > 0).mean():.1f}% | same answers on other moments: mean {null.mean():+.4f} | p {pval:.4f}")
    yr = pd.DatetimeIndex(tr.t).year
    by = tr.groupby(yr).R.agg(["size", "mean", "sum"]).round(3)
    print("by year:\n", by.to_string())
    print("by action:", tr.groupby("action").R.agg(["size", "mean"]).round(3).to_dict("index"))
    print("size 1 vs 2 (per unit):", {k: round(float((g.R / (2 if k == "2" else 1)).mean()), 3) for k, g in tr.groupby("size")})
    if len(tr) >= 30:
        q3 = pd.qcut(tr.conviction.rank(method="first"), 3, labels=["low", "mid", "high"])
        print("by conviction third (per unit):", pd.Series(unit, index=tr.index).groupby(q3, observed=True).mean().round(3).to_dict())
    always = {c[0]: round(float(tab[:, col[(c[0], "0.25", "2R")]].mean()), 4) for c in (("buy",), ("sell",))}
    print("for reference, always buy / always sell at every moment (stop 0.25, target 2R):", always)
    json.dump({"n": int(len(d)), "trades": int(trade.sum()), "mean_R": round(obs, 4), "total_R": round(float(res.sum()), 1),
               "winners": round(float((unit > 0).mean()), 3), "null_mean": round(float(null.mean()), 4), "p": round(float(pval), 4),
               "by_year": {int(k): float(v) for k, v in by["mean"].items()}, "always": always},
              open(os.path.join(run, "summary.json"), "w"), indent=1)


# ------------------------------------------------------------------------------------------ remote part (where the API key is)
def _run_dir(name):
    d = os.path.join(OUT, "runs", name)
    os.makedirs(d, exist_ok=True)
    return d


def _pick(meta, period, n):
    m = meta[meta.period == period]
    return m.head(n) if n else m


def run_sync(name, period, n, model=MODEL, effort="high", workers=3):
    """Live calls (pilot)."""
    import concurrent.futures as cf
    from llm import judge
    meta, cases = load_cases()
    todo = _pick(meta, period, n)
    cl = judge.client()
    json.dump({"model": model, "effort": effort, "period": period, "n": len(todo), "mode": "live", "kind": "vision"},
              open(os.path.join(_run_dir(name), "meta.json"), "w"), indent=1)

    def one(r):
        try:
            return {"id": r["id"], **parse(cl.messages.create(**request(model, cases[r["id"]], r["text"], effort)))}
        except Exception as e:                                   # noqa: BLE001
            return {"id": r["id"], "error": f"{type(e).__name__}: {e}"[:300]}

    spent = 0.0
    with open(os.path.join(_run_dir(name), "decisions.jsonl"), "w") as f, cf.ThreadPoolExecutor(workers) as ex:
        for res in ex.map(one, todo.to_dict("records")):
            if "error" in res:
                print("error", res["id"], res["error"], flush=True)
                continue
            spent += judge.cost(res["usage"], model)
            f.write(json.dumps(res, ensure_ascii=False) + "\n")
    d = pd.DataFrame([json.loads(x) for x in open(os.path.join(_run_dir(name), "decisions.jsonl"))])
    u = pd.DataFrame(list(d.usage))
    acts = pd.Series([a.get("action") if isinstance(a, dict) else None for a in d.answer]).value_counts(dropna=False).to_dict()
    print(f"{name}: {len(d)} answers, {spent:.2f} USD = {100 * spent / max(len(d), 1):.1f} cents per call | tokens in {u['in'].mean():.0f} "
          f"(+cache {u.cache_read.mean():.0f}) out {u.out.mean():.0f} | actions {acts} | stop reasons {d.stop_reason.value_counts().to_dict()}")


def submit(name, period, n, model=MODEL, effort="high"):
    from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
    from anthropic.types.messages.batch_create_params import Request
    from llm import judge
    meta, cases = load_cases()
    todo = _pick(meta, period, n)
    recs = todo.to_dict("records")
    cl, ids = judge.client(), []
    for k in range(0, len(recs), 300):                           # about 70 MB of images per batch
        reqs = [Request(custom_id=r["id"], params=MessageCreateParamsNonStreaming(**request(model, cases[r["id"]], r["text"], effort)))
                for r in recs[k:k + 300]]
        ids.append(cl.messages.batches.create(requests=reqs).id)
        print(f"{name}: batch {ids[-1]} submitted with {len(reqs)} requests", flush=True)
    json.dump({"model": model, "effort": effort, "period": period, "n": len(recs), "mode": "batch", "kind": "vision", "batch_ids": ids},
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
    spent, n = 0.0, 0
    with open(os.path.join(_run_dir(name), "decisions.jsonl"), "w") as f:
        for bid in m["batch_ids"]:
            for r in cl.messages.batches.results(bid):
                if r.result.type != "succeeded":
                    print("not done:", r.custom_id, r.result.type)
                    continue
                res = {"id": r.custom_id, **parse(r.result.message)}
                spent += judge.cost(res["usage"], m["model"], batch=True)
                f.write(json.dumps(res, ensure_ascii=False) + "\n")
                n += 1
    m.update(collected=n, cost_usd=round(spent, 2))
    json.dump(m, open(mp, "w"), indent=1)
    print(f"{name}: {n} results, {spent:.2f} USD")


def probe(name, n=60, model=MODEL, workers=3):
    """Leak probe: can the model tell the year from the charts and the sheet?"""
    import concurrent.futures as cf
    from llm import judge
    meta, cases = load_cases()
    meta = meta.assign(year=pd.DatetimeIndex(meta.t).year)
    todo = pd.concat([g.sample(min(len(g), max(1, n // meta.year.nunique())), random_state=0) for _, g in meta.groupby("year")])
    cl = judge.client()

    def one(r):
        try:
            a = parse(cl.messages.create(**request(model, cases[r["id"]], r["text"], "high", system=PROBE_SYSTEM, schema=PROBE_SCHEMA)))
            return {"id": r["id"], "year": int(r["year"]), "guess": (a["answer"] or {}).get("year"), "usage": a["usage"]}
        except Exception as e:                                   # noqa: BLE001
            print("error", r["id"], f"{type(e).__name__}: {e}"[:200], flush=True)
            return {"id": r["id"], "year": int(r["year"]), "guess": None, "usage": None}

    with cf.ThreadPoolExecutor(workers) as ex:
        d = pd.DataFrame(list(ex.map(one, todo.to_dict("records"))))
    d.to_json(os.path.join(_run_dir(name), "probe.jsonl"), orient="records", lines=True)
    spent = sum(judge.cost(u, model) for u in d.usage if isinstance(u, dict))
    d = d.dropna(subset=["guess"])
    rho = d.year.rank().corr(d.guess.rank())
    print(f"{name}: {len(d)} cases, {spent:.2f} USD | exact year {100 * (d.year == d.guess).mean():.0f}% | within one year "
          f"{100 * ((d.year - d.guess).abs() <= 1).mean():.0f}% | rank correlation guess~year {rho:+.2f} "
          f"({'LEAK: tighten' if rho > 0.3 else 'anonymous enough'})")


if __name__ == "__main__":
    if sys.argv[1] == "build":
        build()
    elif sys.argv[1] == "analyse":
        analyse(sys.argv[sys.argv.index("--name") + 1])
