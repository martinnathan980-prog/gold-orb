"""Track `vol` (PROTOCOL_V3 addendum A): short the front VIX future when the market is calm.

    python3 lab/r2/tracks/vol/study.py is            # the 24 pre-declared configurations, in-sample 2013-2021
    python3 lab/r2/tracks/vol/study.py val <name>    # lead only, once, for the frozen pick (logged)

Data: the exchange's public daily history of every monthly VX contract (lab/data/vx/VX_<expiry>.csv),
never read beyond 2025-12-31.  Everything is decided and traded at the daily settlement.
Position: short one unit of notional of the front contract, rolled ROLL business days before expiry.
Daily result in R:  -(S[t+1] - S[t]) / S[t] / s   (1 R = an adverse move of s), minus costs:
COST index points per round trip (half at each entry / exit, a full one at each roll), also / (s * S).
"""
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
VX = os.path.join(LAB, "data", "vx")
OUT = os.path.join(LAB, "results", "r2", "vol")
ROLL, COST = 5, 0.16
IS_END, VAL_END = "2021-12-31", "2025-12-31"

# (contango threshold or None, moving-average length or None, stop s or None) -- declared before the first run
GRID = [(None, None, None)] + \
       [(c, n, s) for s in (0.15, 0.25) for (c, n) in ((None, None), (0.0, None), (0.03, None), (0.06, None), (None, 5), (None, 10),
                                                      (None, 20), (0.0, 10), (0.03, 10), (0.03, 5), (0.03, 20), (0.06, 10))
        if not (s == 0.15 and (c, n) == (0.06, 10))]
assert len(GRID) == 24


def name(cfg):
    c, n, s = cfg
    return "always_short" if cfg == (None, None, None) else \
        f"c{'x' if c is None else int(c * 100)}_n{'x' if n is None else n}_s{int(s * 100)}"


def panel():
    """Daily table: front / second settle, the held contract's own history, days to roll."""
    cons = {}
    for f in sorted(glob.glob(os.path.join(VX, "VX_*.csv"))):
        exp = pd.Timestamp(os.path.basename(f)[3:13])
        d = pd.read_csv(f)
        d["date"] = pd.to_datetime(d["Trade Date"])
        px = d["Settle"].where(d["Settle"] > 0, d["Close"])
        s = pd.Series(px.to_numpy(float), index=d["date"])
        s = s[(s > 0) & (s.index <= pd.Timestamp(VAL_END))]
        cons[exp] = s[~s.index.duplicated()]
    exps = sorted(cons)
    days = sorted(set().union(*[set(s.index) for s in cons.values()]))
    days = [d for d in days if d >= pd.Timestamp("2013-01-02")]
    rows = []
    for t in days:
        live = [e for e in exps if np.busday_count(t.date(), e.date()) >= ROLL and t in cons[e].index]
        if len(live) < 2:
            continue
        rows.append((t, live[0], live[1], cons[live[0]][t], cons[live[1]][t]))
    p = pd.DataFrame(rows, columns=["date", "front", "second", "f1", "f2"]).set_index("date")
    nxt, ma = [], {n: [] for n in (5, 10, 20)}
    idx = list(p.index)
    for i, t in enumerate(idx):
        c = cons[p.front[t]]
        nxt.append(c[idx[i + 1]] if i + 1 < len(idx) and idx[i + 1] in c.index else np.nan)   # same contract, next day
        h = c[c.index <= t]
        for n in ma:
            ma[n].append(h.iloc[-n:].mean() if len(h) >= n else np.nan)                    # the contract's own past settles
    p["f1_next"] = nxt
    for n in ma:
        p[f"ma{n}"] = ma[n]
    p["contango"] = p.f2 / p.f1 - 1
    return p


def run(p, cfg, cost=COST):
    """Daily R series of one configuration (index = the day the result is booked)."""
    c, n, s = cfg
    s_eff = 0.25 if s is None else s
    pos, entry, held = 0, np.nan, None
    out = np.zeros(len(p))
    f1, f1n, fr = p.f1.to_numpy(), p.f1_next.to_numpy(), p.front.to_numpy()
    cg = p.contango.to_numpy()
    ma = p[f"ma{n}"].to_numpy() if n else None
    stopped_today = False
    for i in range(len(p) - 1):
        calm = (c is None or cg[i] >= c) and (n is None or (np.isfinite(ma[i]) and f1[i] <= ma[i]))
        fee = 0.0
        if pos:
            if fr[i] != held:                                  # roll at today's settlement: new contract, new reference
                fee += cost
                held, entry = fr[i], f1[i]
            hit = (s is not None) and f1[i] >= entry * (1 + s)
            if hit or not calm:
                pos, fee = 0, fee + cost / 2
                stopped_today = hit
        if not pos and calm and not stopped_today:
            pos, entry, held = 1, f1[i], fr[i]
            fee += cost / 2
        stopped_today = False
        r = 0.0
        if pos and np.isfinite(f1n[i]):
            r = -(f1n[i] - f1[i]) / f1[i] / s_eff
        out[i + 1] = r - fee / f1[i] / s_eff
    return pd.Series(out, index=p.index)


def stats(r, label=""):
    r = r.copy()
    ann = np.sqrt(252)
    eq = r.cumsum()
    dd = (eq - eq.cummax()).min()
    wk = r.groupby([r.index.isocalendar().year, r.index.isocalendar().week]).sum()
    mo = r.groupby([r.index.year, r.index.month]).sum()
    yr = r.groupby(r.index.year).sum()
    act = r[r != 0]
    return {"name": label, "days": int(len(r)), "in_market_pct": round(float((r != 0).mean() * 100), 1),
            "total_R": round(float(r.sum()), 1), "t": round(float(r.mean() / r.std(ddof=1) * np.sqrt(len(r))), 2),
            "sharpe": round(float(r.mean() / r.std(ddof=1) * ann), 2),
            "win_days_pct": round(float((act > 0).mean() * 100), 1) if len(act) else None,
            "win_weeks_pct": round(float((wk[wk != 0] > 0).mean() * 100), 1), "win_months_pct": round(float((mo[mo != 0] > 0).mean() * 100), 1),
            "worst_day_R": round(float(r.min()), 2), "worst_week_R": round(float(wk.min()), 2), "max_dd_R": round(float(dd), 1),
            "years_pos": f"{int((yr > 0).sum())}/{len(yr)}", "by_year_R": {int(k): round(float(v), 1) for k, v in yr.items()}}


def main_is():
    p = panel()
    pi = p[p.index <= pd.Timestamp(IS_END)]
    print("panel", p.index[0].date(), "->", p.index[-1].date(), "| in-sample days", len(pi),
          "| contango > 0 on", round(float((pi.contango > 0).mean() * 100), 1), "% of days | median contango", round(float(pi.contango.median() * 100), 1), "%")
    rows = []
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "trials.jsonl"), "w") as f:
        for cfg in GRID:
            st = stats(run(pi, cfg), name(cfg))
            st["t_stress"] = round(float((lambda r: r.mean() / r.std(ddof=1) * np.sqrt(len(r)))(run(pi, cfg, COST * 1.5))), 2)
            st["cfg"] = list(cfg)
            f.write(json.dumps(st) + "\n")
            rows.append(st)
    d = pd.DataFrame(rows)
    base = float(d.sharpe[d.name == "always_short"].iloc[0])
    yp = d.years_pos.map(lambda x: int(x.split("/")[0]) / int(x.split("/")[1]))
    d["pass"] = (d.t >= 2.5) & (yp >= 0.6) & (d.t_stress >= 2.0) & (d.sharpe > base) & (d.name != "always_short")
    cols = ["name", "in_market_pct", "total_R", "t", "t_stress", "sharpe", "win_days_pct", "win_weeks_pct", "win_months_pct",
            "worst_day_R", "worst_week_R", "max_dd_R", "years_pos", "pass"]
    print(d[cols].to_string(index=False))
    d.drop(columns=["by_year_R", "cfg"]).to_csv(os.path.join(OUT, "is_table.csv"), index=False)
    ok = d[d["pass"]]
    if not len(ok):
        print("NO configuration passes the in-sample criteria")
        json.dump({"pick": None}, open(os.path.join(OUT, "pick.json"), "w"))
        return
    pick = ok.sort_values("t", ascending=False).iloc[0]
    c0, n0, s0 = pick.cfg
    def near(a, b, grid):
        return a == b or (a in grid and b in grid and abs(grid.index(a) - grid.index(b)) == 1)
    nb = d[d.cfg.map(lambda g: g != pick.cfg and g != [None, None, None] and
                     sum([g[0] != c0, g[1] != n0, g[2] != s0]) == 1 and near(g[0], c0, [None, 0.0, 0.03, 0.06]) and
                     near(g[1], n0, [None, 5, 10, 20]) and near(g[2], s0, [0.15, 0.25]))]
    res = {"pick": pick["name"], "cfg": pick.cfg, "is": {k: pick[k] for k in cols[1:-1]}, "by_year_R": pick.by_year_R,
           "always_short_sharpe": base, "neighbours": nb.name.tolist(), "neighbours_median_sharpe": round(float(nb.sharpe.median()), 2) if len(nb) else None,
           "neighbours_ok": bool(len(nb) and nb.sharpe.median() >= 0.7 * pick.sharpe)}
    json.dump(res, open(os.path.join(OUT, "pick.json"), "w"), indent=1, default=str)
    print(json.dumps(res, indent=1, default=str))


def main_val(nm):
    cfg = next(g for g in GRID if name(g) == nm)
    with open(os.path.join(LAB, "results", "val_access.log"), "a") as f:
        f.write(f"{pd.Timestamp.utcnow().isoformat()} track=vol label={nm}:val n=daily\n")
    p = panel()
    r = run(p, cfg)
    rs = run(p, cfg, COST * 1.5)
    v = (r.index > pd.Timestamp(IS_END))
    res = {"name": nm, "val": stats(r[v], nm), "val_stress": stats(rs[v], nm + ":stress"), "val_always_short": stats(run(p, GRID[0])[v], "always_short")}
    json.dump(res, open(os.path.join(OUT, f"val_{nm}.json"), "w"), indent=1)
    r.to_csv(os.path.join(OUT, f"daily_R_{nm}.csv"))
    print(json.dumps(res, indent=1))


if __name__ == "__main__":
    if sys.argv[1] == "is":
        main_is()
    else:
        main_val(sys.argv[2])
