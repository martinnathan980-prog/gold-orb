"""What would a 1,000 EUR account have done with the ten rules of round 2, on 2022-2025?

Rules alone (no judgement by Claude), FP Markets Raw costs included, one account, compounding:
risk per trade = a fixed % of the current balance, lots rounded down to the broker's step, a trade is
skipped when even the minimum lot would risk more than that %, at most 6 positions at once and 2 per
market (the limits of the MT5 "hands"), robot stopped for good at 500 EUR (-50 %).

Read the output with three reservations: the period is the one on which these rules were kept (it
flatters them), the rules have not been through their counter-checks yet, and 2026 has not been looked at.

    python3 sim1000.py          -> results/sim1000/ (summary.json, equity_1pct.csv, starts.csv, compte_1000_euros.png)
"""
import json
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, LAB)
from goldlab import r2  # noqa: E402
from goldlab.portfolio import Spec, run_account  # noqa: E402

TRADES = os.path.join(LAB, "results", "r2", "recalc", "trades")
OUT = os.path.join(LAB, "results", "sim1000")
SLEEVES = [("noise30", "us100"), ("ocm4", "us100"), ("brk72_24h_wd", "btcusd"), ("brk72_24h_wd", "ethusd"),
           ("nq_btc_follow", "btcusd"), ("F1_brk_ridge_filter", "btcusd"), ("F1_brk_ridge_filter", "ethusd"),
           ("GOLD_FRI_PM", "xauusd"), ("donch4h_stop", "xauusd"), ("orb_asia_2d_buf10", "xauusd")]
USD_EUR = 0.89
LIMITS = dict(kill_dd=0.5, max_positions=6, max_per_sym=2)
_all = {}


def sleeves(a, b):
    out = []
    for name, sym in SLEEVES:
        if (name, sym) not in _all:
            _all[(name, sym)] = pd.read_parquet(os.path.join(TRADES, f"{name}__{sym}.parquet"))
        t = _all[(name, sym)]
        t = t[(t.entry_time >= pd.Timestamp(a, tz="UTC")) & (t.entry_time < pd.Timestamp(b, tz="UTC"))]
        s = r2.SPEC[sym]
        out.append((f"{name}_{sym}", t, Spec(sym, s["units_per_lot"], s["min_lot"], s["lot_step"], USD_EUR, s["leverage"])))
    return out


def main_run(risk=1.0):
    log = []
    curve, s = run_account(sleeves("2022-01-01", "2026-01-01"), 1000.0, risk, log=log, **LIMITS)
    daily = curve.resample("D").last().ffill()
    daily = pd.concat([pd.Series([1000.0], index=[pd.Timestamp("2021-12-31", tz="UTC")]), daily])
    L = pd.DataFrame(log)
    L["t_out"] = pd.to_datetime(L.t_out, utc=True)
    peak = daily.cummax()
    dd = 1 - daily / peak
    t_low = dd.idxmax()
    t_top = daily[:t_low].idxmax()
    back = daily[t_low:][daily[t_low:] >= peak[t_low]]
    wk = L.set_index("t_out").money.resample("W").sum()
    mo = daily.resample("ME").last().pct_change().dropna() * 100
    ye = daily.resample("YE").last()
    s.update({
        "risk_pct": risk,
        "year_end": {str(y.year): round(float(v)) for y, v in ye.items() if y.year >= 2022},
        "worst_drop": {"pct": round(float(dd.max() * 100), 1), "from": round(float(daily[t_top])), "top": str(t_top.date()),
                       "to": round(float(daily[t_low])), "bottom": str(t_low.date()),
                       "recovered": str(back.index[0].date()) if len(back) else None},
        "trades_per_week": round(len(L) / len(wk), 1), "trades_won_pct": round(float((L.money > 0).mean() * 100), 1),
        "weeks_won_pct": round(float((wk > 0).mean() * 100)), "months_won_pct": round(float((mo > 0).mean() * 100)),
        "worst_month_pct": round(float(mo.min()), 1), "best_month_pct": round(float(mo.max()), 1),
    })
    return daily, s


def start_test(risk):
    """Twelve months from each possible starting month: how often does it end badly?"""
    rows = []
    for st in pd.date_range("2022-01-01", "2025-01-01", freq="MS"):
        c, s = run_account(sleeves(str(st.date()), str((st + pd.DateOffset(months=12)).date())), 1000.0, risk, **LIMITS)
        rows.append({"risk_pct": risk, "start": st.strftime("%Y-%m"), "end": s["final"], "stopped": s["killed_at"] is not None,
                     "lowest": round(float(min(1000.0, c.min())), 2) if len(c) else 1000.0})
    return pd.DataFrame(rows)


def chart(daily, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.ticker import FixedLocator, FuncFormatter, NullLocator
    surface, ink, ink2, grid, blue = "#fcfcfb", "#0b0b0b", "#52514e", "#e4e3df", "#2a78d6"
    eur = lambda v: f"{v:,.0f}".replace(",", " ") + " €"
    fig, ax = plt.subplots(figsize=(7.2, 8.4), dpi=150)
    fig.patch.set_facecolor(surface)
    ax.set_facecolor(surface)
    ax.plot(daily.index, daily.to_numpy(), color=blue, lw=2, solid_joinstyle="round", solid_capstyle="round", zorder=3)
    ax.set_yscale("log")
    ax.set_ylim(400, 30000)
    ax.yaxis.set_major_locator(FixedLocator([500, 1000, 2000, 5000, 10000, 20000]))
    ax.yaxis.set_minor_locator(NullLocator())
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: eur(v)))
    ax.set_xlim(pd.Timestamp("2021-12-15", tz="UTC"), pd.Timestamp("2026-04-20", tz="UTC"))
    ax.set_xticks([pd.Timestamp(f"{y}-01-01", tz="UTC") for y in range(2022, 2027)])
    ax.set_xticklabels([str(y) for y in range(2022, 2027)])
    ax.grid(axis="y", color=grid, lw=1)
    ax.grid(axis="x", visible=False)
    for sp in ("top", "right", "left"):
        ax.spines[sp].set_visible(False)
    ax.spines["bottom"].set_color(grid)
    ax.tick_params(colors=ink2, labelsize=11, length=0)
    ax.axhline(1000, color=ink2, lw=1, zorder=2)
    ax.axhline(500, color=ink2, lw=1, zorder=2)
    ax.text(pd.Timestamp("2025-12-28", tz="UTC"), 1060, "mise de départ", color=ink2, fontsize=10, ha="right", va="bottom")
    ax.text(pd.Timestamp("2025-12-28", tz="UTC"), 530, "arrêt du robot (−50 %)", color=ink2, fontsize=10, ha="right", va="bottom")

    def mark(t, label, dx, dy, ha="left"):
        v = float(daily[:t].iloc[-1])
        ax.plot([t], [v], "o", ms=8, color=blue, mec=surface, mew=2, zorder=4)
        ax.annotate(label, (t, v), xytext=(dx, dy), textcoords="offset points", color=ink, fontsize=11, ha=ha, va="center")

    low = daily.loc["2022-08-01":"2023-08-31"].idxmin()
    mark(low, f"point bas : {eur(daily[low])}\n(mars 2023)", 8, -22)
    mark(pd.Timestamp("2023-12-31", tz="UTC"), f"fin 2023 : {eur(daily[:'2023-12-31'].iloc[-1])}", 12, -16)
    mark(pd.Timestamp("2024-12-31", tz="UTC"), f"fin 2024 : {eur(daily[:'2024-12-31'].iloc[-1])}", -10, 16, ha="right")
    mark(daily.index[-1], f"fin 2025 :\n{eur(daily.iloc[-1])}", 9, 0)
    ax.text(pd.Timestamp("2022-01-20", tz="UTC"), 1420, "20 mois sans gain : le compte\nreste entre 835 € et 1 255 €", color=ink2,
            fontsize=10, ha="left", va="bottom")
    fig.suptitle("1 000 € au départ, 1 % risqué par trade", x=0.06, y=0.975, ha="left", fontsize=16, color=ink, fontweight="bold")
    fig.text(0.06, 0.925, "Simulation sur le passé (2022-2025) avec nos 10 règles, frais compris.\n"
                          "Règles pas encore contre-vérifiées : ce n'est pas une promesse.", ha="left", va="top", fontsize=11, color=ink2)
    fig.text(0.06, 0.03, "Échelle : chaque doublement du compte a la même hauteur.", ha="left", fontsize=9.5, color=ink2)
    fig.subplots_adjust(left=0.17, right=0.86, top=0.84, bottom=0.09)
    fig.savefig(path, facecolor=surface)
    plt.close(fig)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    daily, s = main_run(1.0)
    daily.to_csv(os.path.join(OUT, "equity_1pct.csv"), header=["equity"])
    starts = pd.concat([start_test(r) for r in (1.0, 2.0, 3.0)])
    starts.to_csv(os.path.join(OUT, "starts.csv"), index=False)
    agg = {f"{r:g}%": {"starts": int(len(g)), "stopped_at_minus_50": int(g.stopped.sum()), "ended_below_1000": int((g.end < 1000).sum()),
                       "median_end": round(float(g.end.median())), "worst_end": round(float(g.end.min())),
                       "best_end": round(float(g.end.max())), "lowest_point_worst": round(float(g.lowest.min()))}
           for r, g in starts.groupby("risk_pct")}
    other = {f"{r:g}%": {k: run_account(sleeves("2022-01-01", "2026-01-01"), 1000.0, r, **LIMITS)[1].get(k)
                         for k in ("n", "final", "max_dd_pct", "killed_at")} for r in (2.0, 3.0)}
    json.dump({"main_1pct": s, "other_stakes_2022_2025": other, "twelve_months_from_each_start": agg},
              open(os.path.join(OUT, "summary.json"), "w"), indent=1, default=str)
    chart(daily, os.path.join(OUT, "compte_1000_euros.png"))
    print(json.dumps({"main_1pct": {k: s[k] for k in ("final", "year_end", "worst_drop", "trades_per_week", "trades_won_pct",
                                                      "weeks_won_pct", "months_won_pct", "worst_month_pct", "best_month_pct")},
                      "other_stakes_2022_2025": other, "twelve_months_from_each_start": agg}, indent=1, default=str))
