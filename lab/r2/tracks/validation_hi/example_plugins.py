"""validation_hi -- EXAMPLES of how a new change is added before the look (not candidates, nothing here is declared).

1. A new CHANGE KIND (acts on the orders before the simulation; a skipped signal never blocks the sleeve):

       import vhi_sleeves as SL

       @SL.register_change("skip_ny_hours")
       def change(spec, mk, O, mode, ctx):       # O: the rule's orders on frame mk (oid = row number)
           ...                                   # decide from what is known at each order's activation bar
           return O_kept, {"diag": {...}}

   then, in look_spec.json:  "plugins": ["example_plugins.py"]  and a sleeve
       {"key": "noise30__us100+X", "rule": "noise30", "sym": "us100", "convention": "sB",
        "change": {"kind": "skip_ny_hours", "hours": [12, 13]}}

2. A new STAKE RULE (multiplies each trade's R; 0 = not taken, the sleeve's chain unchanged), e.g. from
   lab/r2/tracks/sizing/: a class with .stakes(trades, ctx) (see vhi_stakes.StakeRule and its ctx), referenced in a
   portfolio of look_spec.json:
       "stakes": {"noise30__us100": {"kind": "python", "module": "example_plugins.py", "factory": "HourBandStake",
                                     "args": {"bands": [[10, 12], [12, 14], [14, 16]], "m_low": 0.5}}}
   Yearly refits go through vhi_stakes.yearly_refit (a fit for year Y sees only outcomes known before
   1 January Y minus 7 days).

Then: rehearse in sample (proofs.py, or look.py --cut 2022-01-01) and compare with the lens that found the change;
declare; run the look once.
"""
import numpy as np
import pandas as pd

import vhi_sleeves as SL
import vhi_stakes as ST

NY = "America/New_York"


@SL.register_change("skip_ny_hours")
def change_skip_ny_hours(spec, mk, O, mode, ctx):
    """Example: skip every order whose activation bar starts in one of the declared New-York hours (no fit)."""
    hours = set(int(h) for h in spec["change"].get("hours", []))
    t = mk.index[np.clip(O.entry_i.to_numpy(), 0, len(mk) - 1)].tz_convert(NY)
    skip = np.isin(t.hour, list(hours))
    return O[~skip], {"diag": {"skipped": int(skip.sum()), "hours": sorted(hours)}}


class HourBandStake(ST.StakeRule):
    """Example of an Addendum I `clock` shape: stake m_low on the New-York hour band of the fill whose trades (this
    sleeve's own chain, closed before 1 January minus 7 days) earned the least, if that band's mean R is <= T and it
    has at least min_cell trades; 1 elsewhere. Refitted every 1 January."""

    def __init__(self, bands, m_low=0.5, T=0.0, min_cell=20):
        self.bands = [tuple(float(x) for x in b) for b in bands]
        self.m_low, self.T, self.min_cell = float(m_low), float(T), int(min_cell)
        self.name = "example_hour_band"
        self.fits = {}

    def band(self, ts):
        x = pd.DatetimeIndex(ts).tz_convert(NY)
        h = (x.hour + x.minute / 60.0).to_numpy()
        out = np.full(len(h), -1)
        for j, (a, b) in enumerate(self.bands):
            out[(h >= a) & (h < b)] = j
        return out

    def stakes(self, trades, ctx):
        book = ctx["book"]
        mine = book[book.sleeve == ctx["sleeve"]]
        cell_tr = self.band(trades.entry_time)

        def fit(Y, cutoff):
            tr = mine[mine.exit_time < cutoff]
            if not len(tr):
                return None
            c = self.band(tr.entry_time)
            stats = {j: (int((c == j).sum()), float(tr.R.to_numpy()[c == j].mean()) if (c == j).any() else np.nan)
                     for j in range(len(self.bands))}
            ok = {j: v for j, v in stats.items() if v[0] >= self.min_cell}
            if len(ok) < 2:
                return {"band": None, "last_outcome_used": str(tr.exit_time.max())}
            w = min(ok, key=lambda j: (ok[j][1], j))
            return {"band": int(w) if ok[w][1] <= self.T else None, "mean": ok[w][1],
                    "last_outcome_used": str(tr.exit_time.max())}

        def apply(f, sel):
            if f is None or f["band"] is None:
                return np.ones(int(sel.sum()))
            return np.where(cell_tr[sel] == f["band"], self.m_low, 1.0)

        m, fits = ST.yearly_refit(trades.entry_time, fit, apply, purge=ctx.get("purge", ST.PURGE))
        self.fits[(ctx["sleeve"], ctx["mode"], ctx["exec"])] = fits
        return m
