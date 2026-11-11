"""Track `pyramid`: the zero-edge control.

What the scheme does to the shape of the results when the parents have NO edge.

Construction (one draw):
  every parent of the window is re-entered AT MARKET at the open of a one-minute bar drawn at random among the
  bars of the same window that fall in the same New-York hour of the week as its real entry (same rule, so the
  same market; the session, the day of the week and the number of trades are kept), with
      its stop distance, trailing distance and break-even distance scaled with the price level,
      its time-exit delay in bars,
      variant "coin" (the control of criterion e): its direction drawn with a fair coin  -> no timing edge and no
                                                    market drift; the expectancy is minus the costs;
      variant "kept" (shown next to it):            its real direction                  -> no timing edge, the
                                                    market's drift over the window stays.
  The re-entered parents are simulated by the lab's simulator (FP costs, one position per rule, so a draw that
  falls while the rule is already in a trade is skipped, as in goldlab.r2.null_test), the add-ons are computed by
  the same replay as for the real parents, and the reference and the 24 configurations are accounted exactly as
  the real ones. 200 draws; draw d of rule r uses the generator seeded with (SEED, variant, r, d).
  Simplification: the real stop and limit entries become market entries at a bar open.

Reading (criterion e): G = configuration total x (reference drawdown / configuration drawdown) - reference total,
inside each draw, in base stakes; shown as 1 + G / (real reference total).
"""
import numpy as np
import pandas as pd

import pyramid as P
from goldlab.data import NY
from goldlab.sim import simulate

SEED = 20261111
VARIANTS = ("coin", "kept")


class Collector:
    """Hook for pyramid.build: draws and simulates the zero-edge parents while the prices of a market are loaded."""

    def __init__(self, wstart, wend, n_draws=200, variants=VARIANTS):
        self.wstart, self.wend, self.n, self.variants = wstart, wend, int(n_draws), tuple(variants)
        self.par = {v: [[] for _ in range(self.n)] for v in self.variants}
        self.add = {v: [[] for _ in range(self.n)] for v in self.variants}
        self.skipped = {v: 0 for v in self.variants}
        self.asked = {v: 0 for v in self.variants}

    def hook(self, sym, name, m1, q, par, of, c):
        if self.n == 0:
            return
        idx = m1.index
        keep = (par.entry_time >= self.wstart).to_numpy() & (par.entry_time < self.wend).to_numpy()
        p = par[keep]
        if not len(p):
            return
        fi = np.asarray(idx.searchsorted(p.entry_time), np.int64)
        entry = p.entry.to_numpy(float)
        side0 = p.side.to_numpy(np.int64)
        stop_rel = p.risk.to_numpy(float) / entry
        trail_rel = of["trail"][keep] / entry
        be_rel = of["be"][keep] / entry
        xe = of["xe"][keep]
        dur = np.where(xe >= 0, np.maximum(xe - fi, 1), -1)
        lo, hi = int(idx.searchsorted(self.wstart)), int(idx.searchsorted(self.wend))
        ny = idx[lo:hi].tz_convert(NY)
        how = (ny.dayofweek * 24 + ny.hour).to_numpy()
        how[-2:] = -1                                         # never the last two bars of the window
        order = np.argsort(how, kind="stable")
        bounds = np.searchsorted(how[order], np.arange(170))
        h = (idx[fi].tz_convert(NY).dayofweek * 24 + idx[fi].tz_convert(NY).hour).to_numpy()
        a, b = bounds[h], bounds[h + 1]
        assert (b > a).all()
        mid_open = (q[0] + q[4]) / 2.0
        N = len(idx)
        r_idx = [s for s in P.S.SLEEVES].index((name, sym))
        sleeve = f"{name}_{sym}"
        for vi, v in enumerate(self.variants):
            for d in range(self.n):
                rng = np.random.default_rng([SEED, vi, r_idx, d])
                ei = lo + order[a + (rng.random(len(p)) * (b - a)).astype(np.int64)]
                coin = rng.integers(0, 2, len(p)) * 2 - 1     # drawn in both variants: the same bars in both
                side = coin if v == "coin" else side0
                px = mid_open[ei]
                o = pd.DataFrame({"entry_i": ei, "side": side, "etype": 0, "stop_dist": stop_rel * px, "trail": trail_rel * px,
                                  "be": be_rel * px, "exit_i": np.where(dur >= 0, np.minimum(ei + dur, N - 1), -1)})
                t = simulate(m1, o, sym=sym, costs=c, no_overlap=True)
                t = t[t.entry_time < self.wend]
                self.asked[v] += len(p)
                self.skipped[v] += len(p) - len(t)
                fo = P.order_fields(o, t)
                rp = P.replay(m1, q, t, fo, c, P.GRID_LEVELS)
                assert (rp["x_px"] == t.exit.to_numpy()).all()
                t = t.reset_index(drop=True)
                t["sleeve"], t["sym"], t["fam"] = sleeve, sym, P.S.FAMILY[sym]
                t["pid"] = r_idx * 10_000_000 + np.arange(len(t))
                t["trail"] = fo["trail"]
                ad = P.addon_table(m1, t, rp, c, P.GRID_LEVELS)
                ad["pid"] = t.pid.to_numpy()[ad.prow.to_numpy().astype(np.int64)] if len(ad) else []
                ad["sleeve"], ad["sym"], ad["fam"] = sleeve, sym, P.S.FAMILY[sym]
                cols = ["sleeve", "sym", "fam", "pid", "side", "entry_time", "exit_time", "entry", "risk", "pnl", "R", "stop", "hold_min", "trail"]
                self.par[v][d].append(t[cols])
                self.add[v][d].append(ad)

    def results(self, last_year=None):
        """Per variant: {configuration: array [draw, (total, max_dd, worst_week, win_weeks_pct, n_addons, addon_mean_R,
        longest_red_weeks, win_days_pct)]} and the same for the reference."""
        out = {}
        for v in self.variants:
            names = ["reference"] + [n for n, _ in P.CONFIGS]
            arr = {n: np.full((self.n, 8), np.nan) for n in names}
            for d in range(self.n):
                par = pd.concat(self.par[v][d], ignore_index=True)
                add = pd.concat(self.add[v][d], ignore_index=True)
                res, _, _ = P.evaluate_all(par, add, last_year=last_year)
                for n in names:
                    x = res[n]
                    arr[n][d] = (x["total_exact"], x["max_dd"], x["worst_week"], x["win_weeks_pct"], x["n_addons"],
                                 x.get("addon_mean_R", np.nan), x["longest_red_weeks"], x["win_days_pct"])
            out[v] = arr
        return out


def summary(arr, real_ref_total):
    """One variant: the zero-edge reading of every configuration."""
    f = lambda x, d=2: round(float(x), d)
    ref = arr["reference"]
    out = {"reference": {"draws": int(len(ref)), "total_mean": f(ref[:, 0].mean()), "total_p05_p95": [f(np.percentile(ref[:, 0], 5)), f(np.percentile(ref[:, 0], 95))],
                         "max_dd_median": f(np.median(ref[:, 1])), "worst_week_median": f(np.median(ref[:, 2])),
                         "win_weeks_pct_mean": f(ref[:, 3].mean()), "win_days_pct_mean": f(ref[:, 7].mean()),
                         "longest_red_weeks_mean": f(ref[:, 6].mean())}}
    for name, _ in P.CONFIGS:
        x = arr[name]
        G = x[:, 0] * ref[:, 1] / x[:, 1] - ref[:, 0]
        n = len(G)
        se = G.std(ddof=1) / np.sqrt(n)
        req = 1.0 + G / real_ref_total
        out[name] = {
            "addons_mean": f(x[:, 4].mean(), 1),
            "addon_mean_R_mean": f(np.nanmean(x[:, 5]), 4) if np.isfinite(x[:, 5]).any() else None,
            "addons_total_mean": f((x[:, 0] - ref[:, 0]).mean()),
            "total_mean": f(x[:, 0].mean()), "total_p05_p95": [f(np.percentile(x[:, 0], 5)), f(np.percentile(x[:, 0], 95))],
            "max_dd_vs_ref_mean": f((x[:, 1] / ref[:, 1]).mean(), 3),
            "worst_week_vs_ref_median": f(np.median(x[:, 2] / ref[:, 2]), 3),
            "win_weeks_pct_mean": f(x[:, 3].mean()), "win_days_pct_mean": f(x[:, 7].mean()),
            "longest_red_weeks_mean": f(x[:, 6].mean()),
            "G_mean": f(G.mean()), "G_median": f(np.median(G)), "G_p2.5_p97.5": [f(np.percentile(G, 2.5)), f(np.percentile(G, 97.5))],
            "G_ci95_of_mean": [f(G.mean() - 1.96 * se), f(G.mean() + 1.96 * se)],
            "share_of_draws_with_gain": f((G > 0).mean(), 3),
            "ratio_equivalent_mean": f(req.mean(), 4),
            "ratio_equivalent_ci95_of_mean": [f(1.0 + (G.mean() - 1.96 * se) / real_ref_total, 4), f(1.0 + (G.mean() + 1.96 * se) / real_ref_total, 4)],
            "ratio_equivalent_p2.5_p97.5": [f(np.percentile(req, 2.5), 4), f(np.percentile(req, 97.5), 4)],
        }
    return out
