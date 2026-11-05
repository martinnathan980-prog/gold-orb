"""Part B - market choice sanity check (IS only).

Three generic rule families with ONE fixed, untuned parameter set each (fixed before any run),
applied identically to the 6 instruments -> 18 logged configs.  Question: is there a market where
simple rules work clearly better than on gold?

  orb      London-open range 08:00-09:00 London, OCO stops until 16:00, stop = other side,
           exit 20:00 London
  channel  H4 Donchian 20 close-breakout, stop 2 ATR(14,H4), trailing 2 ATR, max 5 trading days
  rsi2     daily RSI(2) <10 long / >90 short, exit first close beyond SMA5 or 5 days, stop 2 ATR(14,D)

Also prints a cost / volatility table (round-trip cost in units of ATR(H1) and ATR(D)).
NB: instruments other than gold are bid-only with a FIXED synthetic spread -> indicative only.
"""
import json
import sys

import numpy as np
import pandas as pd

from common import SYMS, free_m1, gl, load_bars, run_and_log
import strategy as S

FIXED = {
    "orb": dict(rule="orb", start_min=480, range_min=60, expiry_min=960, exit_min=1200),
    "channel": dict(rule="channel", rule_tf="4h", n=20, atr_n=14, stop_atr=2.0, trail_atr=2.0, max_days=5),
    "rsi2": dict(rule="rsi2", rsi_n=2, lo=10.0, hi=90.0, sma_n=5, atr_n=14, stop_atr=2.0, max_days=5),
    # 4th family added after the gross-vs-net diagnostic (cost-light: R unit = 2 daily ATR)
    "channel_d": dict(rule="channel", rule_tf="D", n=20, atr_n=14, stop_atr=2.0, trail_atr=2.0, max_days=5),
}


def cost_table():
    rows = []
    for s in SYMS:
        h1 = load_bars(s, "1h")
        d1 = load_bars(s, "D")
        h1 = h1[h1.index < pd.Timestamp("2022-01-01", tz="UTC")]
        d1 = d1[d1.index < pd.Timestamp("2022-01-01")]
        c = gl.COSTS[s]
        spr = (h1.ac - h1.bc).median()
        px = h1.c.median()
        rt = spr + 2 * c.slip_bps * 1e-4 * px + c.commission
        rows.append({"sym": s, "median_px": round(px, 4), "spread": round(spr, 5),
                     "rt_cost": round(rt, 5), "rt_cost_bp": round(rt / px * 1e4, 2),
                     "atrH1": round(gl.atr(h1, 14).median(), 5), "atrD": round(gl.atr(d1, 14).median(), 5),
                     "cost/atrH1_%": round(rt / gl.atr(h1, 14).median() * 100, 1),
                     "cost/atrD_%": round(rt / gl.atr(d1, 14).median() * 100, 1)})
    print(pd.DataFrame(rows).to_string(index=False))
    return rows


def main(only=None, pairs=None, tag=None):
    out = []
    for s in SYMS:
        if only and s not in only:
            continue
        if pairs and not any(ps == s for ps, _ in pairs):
            continue
        m1 = gl.load_m1(s)
        bars = {"channel": load_bars(s, "4h"), "rsi2": load_bars(s, "D"), "orb": None, "channel_d": load_bars(s, "D")}
        for name, p in FIXED.items():
            if pairs and (s, name) not in pairs:
                continue
            o = S.make_orders(m1, rule=p["rule"], bars=bars[name], **{k: v for k, v in p.items() if k != "rule"})
            cfg = {"part": "B", "sym": s, **p}
            if tag:
                cfg["rerun"] = tag
            t, rep, rs, crit = run_and_log(m1, o, cfg, sym=s)
            out.append({"sym": s, "rule": name, "n": rep.get("n"), "tpy": rep.get("trades_per_year"),
                        "pf": rep.get("pf"), "t": rep.get("t_stat"), "expR": rep.get("expectancy_R"),
                        "win": rep.get("win_rate"), "yrs+": rep.get("years_pos"), "stressPF": rs.get("pf"),
                        "longR": rep.get("long_R"), "shortR": rep.get("short_R"), "maxDD": rep.get("max_dd_R"),
                        "pass": crit.get("pass")})
        free_m1(s)
        del m1
    df = pd.DataFrame(out)
    print(df.to_string(index=False))
    df.to_csv(f"{S.LAB}/results/crossasset/partb_table{'_' + tag if tag else ''}.csv", index=False)
    return df


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "costs":
        cost_table()
    elif len(sys.argv) > 1 and sys.argv[1] == "daily":
        main(pairs=[(s, "channel_d") for s in SYMS], tag="family4")
    elif len(sys.argv) > 1 and sys.argv[1] == "fix":
        pr = [(s, "rsi2") for s in SYMS] + [("deuidxeur", "channel")]
        main(pairs=pr, tag="bugfix-hold-cap")
    else:
        main(sys.argv[1:] or None)
