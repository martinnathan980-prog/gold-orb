"""Track `stocks` (PROTOCOL_V3): the two validated us100 opening rules, FROZEN, on single US shares.

    python3 lab/r2/tracks/stocks/transfer.py [ticker ...]      # in-sample only (entries before 2022-01-01)

Rules and parameters: lab/r2/tracks/idx_us/strategy.py, FINALISTS["ocm4"] and FINALISTS["noise30"], untouched.
The only adaptation: the daily ATR keeps trading days with at least 300 minutes of data instead of 600 (a share
trades 390 minutes a day; the index CFD trades 23 hours). Its true range still contains the overnight gap.
Frames: data/fp/<ticker>_m1.parquet (prep_round3.py: vendor bid/ask + commission per share, split-adjusted).
Costs: slippage 1 bp per side on market fills and 2 bp on stops (r2.SPEC injected below); the x1.5 stress widens the
spread, the commission and the slippage together.
Output: results/r2/stocks/transfer_<rule>.json and trades_is_<rule>.parquet; every (rule, ticker) is logged as a trial.
"""
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, LAB)
import dl_round3  # noqa: E402
import goldlab as gl  # noqa: E402
from goldlab import r2  # noqa: E402
from goldlab.split import cut  # noqa: E402

OUT = os.path.join(LAB, "results", "r2", "stocks")
STOCK_SPEC = {"spread": 0.0, "slip_stop_bps": 2.0, "slip_mkt_bps": 1.0, "swap_long": 0.07, "swap_short": 0.03, "swap_triple": "Fri",
              "units_per_lot": 1, "min_lot": 1, "lot_step": 1, "leverage": 10, "quote": "USD"}


def _idx_us():
    sys.path.insert(0, os.path.join(LAB, "r2", "tracks", "idx_us"))
    spec = importlib.util.spec_from_file_location("r2_idx_us_strategy", os.path.join(LAB, "r2", "tracks", "idx_us", "strategy.py"))
    m = importlib.util.module_from_spec(spec)
    sys.modules["r2_idx_us_strategy"] = m
    spec.loader.exec_module(m)
    cm = m.cm

    def atr_at(m1, times, n=14):                       # same definition, a "full day" = at least 300 minutes of data
        tk, a = cm.daily_atr(m1, n, min_minutes=300)
        if len(a) == 0:
            return np.full(len(times), np.nan)
        j = np.searchsorted(tk, times, side="right") - 1
        return np.where(j >= 0, a[np.clip(j, 0, len(a) - 1)], np.nan)

    cm.atr_at = atr_at
    return m


def register(tickers):
    for t in tickers:
        r2.SPEC[t] = dict(STOCK_SPEC)


def basket(tr):
    """Basket statistics (PROTOCOL_V3 section 4) from pooled trades with columns ticker, entry_time, R, side."""
    if not len(tr):
        return {"n": 0}
    day = tr.entry_time.dt.tz_convert("America/New_York").dt.date
    ds = tr.groupby(day).R.sum()
    by_t = tr.groupby("ticker").R.agg(["sum", "mean", "size"])
    pos, neg = tr.R[tr.R > 0].sum(), -tr.R[tr.R < 0].sum()
    yr = tr.groupby(tr.entry_time.dt.year).R.sum()
    tot = float(tr.R.sum())
    return {"n": int(len(tr)), "tickers": int(len(by_t)), "trades_per_day": round(len(tr) / max(len(ds), 1), 1),
            "pf": round(float(pos / neg), 3) if neg > 0 else None, "exp_R": round(float(tr.R.mean()), 4), "win_rate": round(float((tr.R > 0).mean()), 3),
            "total_R": round(tot, 1), "t_daily_sums": round(float(ds.mean() / ds.std(ddof=1) * np.sqrt(len(ds))), 2),
            "t_per_trade_naive": round(float(tr.R.mean() / tr.R.std(ddof=1) * np.sqrt(len(tr))), 2),
            "win_days_pct": round(float((ds > 0).mean() * 100), 1), "days": int(len(ds)),
            "tickers_positive_pct": round(float((by_t["sum"] > 0).mean() * 100), 1),
            "max_ticker_share_of_profit": round(float(by_t["sum"].max() / tot), 3) if tot > 0 else None,
            "long_R": round(float(tr.R[tr.side > 0].sum()), 1), "short_R": round(float(tr.R[tr.side < 0].sum()), 1),
            "by_year_R": {int(k): round(float(v), 1) for k, v in yr.items()},
            "bps_per_trade": round(float((tr.pnl / tr.entry).mean() * 1e4), 2)}


def main(tickers):
    m = _idx_us()
    register(tickers)
    res = {}
    for rule in ("ocm4", "noise30"):
        params = m.FINALISTS[rule]["params"]
        pooled = {"fp": [], "stress": [], "gross": []}
        for tk in tickers:
            if not os.path.exists(os.path.join(LAB, "data", "fp", f"{tk}_m1.parquet")):
                continue
            m1 = r2.load(tk)
            ev = {"sym": tk}
            for mode in ("fp", "stress", "gross"):
                t = cut(r2.run(tk, m.make_orders, params, mode, True, m1), "is")
                t = t.assign(ticker=tk)
                pooled[mode].append(t[["ticker", "side", "entry_time", "exit_time", "entry", "pnl", "R", "reason"]])
                key = {"fp": "is", "stress": "is_stress", "gross": "is_gross"}[mode]
                ev[key] = gl.metrics.report(t) if hasattr(gl, "metrics") else __import__("goldlab.metrics", fromlist=["report"]).report(t)
            ev["is_bps_per_trade"] = round(float((pooled["fp"][-1].pnl / pooled["fp"][-1].entry).mean() * 1e4), 2) if len(pooled["fp"][-1]) else 0.0
            r2.log_trial("stocks", tk, {"transfer": rule, **params}, ev)
            r2.free(tk)
            print(f"{rule:8s} {tk:6s} n {ev['is'].get('n', 0):5} PF {ev['is'].get('pf', float('nan')):5.2f} R/trade {ev['is'].get('expectancy_R', float('nan')):+.3f} "
                  f"| gross PF {ev['is_gross'].get('pf', float('nan')):5.2f} | stress PF {ev['is_stress'].get('pf', float('nan')):5.2f} | bp {ev['is_bps_per_trade']:+.1f}", flush=True)
        P = {k: pd.concat(v) if v else pd.DataFrame() for k, v in pooled.items()}
        res[rule] = {"params": params, "basket": basket(P["fp"]), "basket_stress": basket(P["stress"]), "basket_gross": basket(P["gross"])}
        P["fp"].to_parquet(os.path.join(OUT, f"trades_is_{rule}.parquet"))
        json.dump(res[rule], open(os.path.join(OUT, f"transfer_{rule}.json"), "w"), indent=1)
        print(json.dumps(res[rule], indent=1), flush=True)


if __name__ == "__main__":
    main(sys.argv[1:] or dl_round3.STOCKS)
