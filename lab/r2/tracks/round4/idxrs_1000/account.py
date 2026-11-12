"""Reported, not judged (declared.json R21): the main's in-sample pairs on a 1,000 EUR account. 1 % of the current
balance per pair, compounding; lot sizes at TODAY's price level (r2/fp_costs.json spread_ref_price), USD -> EUR 0.89,
1 lot = 1 index unit, minimum lot and step 0.1; a leg below 0.1 lot is raised to 0.1 if the pair's risk at those lots is
within 1.5 % of the balance, else the signal is skipped; pairs with us30 are skipped while the balance is below
4,000 EUR. Each leg's money result uses its own lots and its own net simple return from the trade's fills.
Writes results/r2/round4/idxrs_1000/account_1000eur.json."""
import math
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

USD_EUR = 0.89
RISK, CAP, US30_FROM = 0.01, 0.015, 4000.0


def lots_down(v, step=0.1):
    return math.floor(v / step + 1e-9) * step


def run(t, start=1000.0):
    E = start
    peak, mdd = start, 0.0
    taken, skipped = [], {"us30_below_4000": 0, "min_lot_risk_above_1.5pct": 0}
    for _, r in t.iterrows():
        if "us30" in (r.S, r.W) and E < US30_FROM:
            skipped["us30_below_4000"] += 1
            continue
        pS, pW = C.SPEC[r.S]["spread_ref_price"], C.SPEC[r.W]["spread_ref_price"]
        N = RISK * E / USD_EUR / (1.5 * r.sd_pi)
        lS, lW = lots_down(N / pS), lots_down(r.h * N / pW)
        raised = lS < 0.1 or lW < 0.1
        if raised:
            lS, lW = max(lS, 0.1), max(lW, 0.1)
            risk_eur = 1.5 * r.sd_pi * max(lS * pS, lW * pW / r.h) * USD_EUR
            if risk_eur > CAP * E:
                skipped["min_lot_risk_above_1.5pct"] += 1
                continue
        pnl = (lS * pS * (r.exit_S / r.fill_S - 1) - lW * pW * (r.exit_W / r.fill_W - 1)) * USD_EUR
        E += pnl
        peak = max(peak, E)
        mdd = max(mdd, 1 - E / peak)
        taken.append({"time": r.exit_time, "pair_type": r.pair_type, "lots_S": round(lS, 1), "lots_W": round(lW, 1),
                      "raised_to_min": raised, "pnl_eur": pnl, "balance": E,
                      "eff_hedge": (lW * pW) / (lS * pS), "h": r.h})
    tk = pd.DataFrame(taken)
    yrs = max((t.exit_time.max() - t.entry_time.min()).days / 365.25, 1e-9)
    out = {"start_eur": start, "end_eur": round(E, 2), "total_return_pct": round((E / start - 1) * 100, 1),
           "cagr_pct": round(((E / start) ** (1 / yrs) - 1) * 100, 2), "max_drawdown_pct": round(mdd * 100, 1),
           "signals": int(len(t)), "taken": int(len(tk)), "skipped": skipped}
    if len(tk):
        out["taken_by_pair_type"] = tk.groupby("pair_type").size().to_dict()
        out["pnl_eur_by_pair_type"] = {k: round(float(v), 2) for k, v in tk.groupby("pair_type").pnl_eur.sum().items()}
        out["raised_to_min_lot"] = int(tk.raised_to_min.sum())
        out["eff_hedge_over_h_median"] = round(float((tk.eff_hedge / tk.h).median()), 3)
        out["eff_hedge_over_h_p10_p90"] = [round(float(v), 3) for v in np.percentile(tk.eff_hedge / tk.h, [10, 90])]
        out["balance_by_year_end"] = {int(y): round(float(g.balance.iloc[-1]), 2)
                                      for y, g in tk.groupby(pd.to_datetime(tk.time).dt.year)}
        out["losing_trades_share"] = round(float((tk.pnl_eur < 0).mean()), 3)
        out["worst_trade_eur"] = round(float(tk.pnl_eur.min()), 2)
    return out


def main():
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main.parquet")).sort_values("entry_time")
    out = {"what": "reported, not judged: main in-sample pairs (2014-2021) on 1,000 EUR, sizes at today's prices",
           "assumptions": {"risk_per_pair": RISK, "max_risk_at_min_lot": CAP, "us30_pairs_from_eur": US30_FROM,
                           "usd_eur": USD_EUR, "today_price_per_lot_usd": {s: C.SPEC[s]["spread_ref_price"] for s in C.SYMS},
                           "min_lot": 0.1, "lot_step": 0.1, "leverage": 200},
           "run": run(t)}
    C.jdump(out, os.path.join(C.OUT, "account_1000eur.json"))
    print(out)


if __name__ == "__main__":
    main()
