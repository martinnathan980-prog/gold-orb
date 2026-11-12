"""validation_hi -- stakes per trade or per sleeve (PROTOCOL_V3 Addendum I), with yearly refits.

A STAKE RULE gives every trade of a sleeve a multiplier m of the base stake (0 = not taken; Addendum I bounds it to
0..2) from what is known at the trade's decision. The harness calls, for each portfolio, sleeve by sleeve:

    rule.stakes(trades, ctx) -> np.ndarray aligned with `trades`

with ctx a dict:
    cut, mode ('fp' | 'stress'), exec ('lab' | 'live'), sleeve (key), sym
    book      every sleeve's own chain in this mode and execution, BEFORE stakes (the "paper" trades: columns sleeve,
              sym, side, entry_time, exit_time, R, oid); a rule may read other sleeves' positions ("agreement")
    signals   {sleeve key: signal table} when the sleeve spec asked for one (generic_signal_table below: every order
              of the rule taken alone, its arming / fill time, side, stop distance, last mid price, riskbp, filled,
              refused, still open at the frame end, label = its own R alone, exit time alone)
    purge     pd.Timedelta (7 days): a fit for year Y may use only outcomes known before 1 January Y minus purge

A rule that should SKIP signals (re-simulating the chain, so a skipped signal frees the sleeve) is not a stake rule:
it is a change (vhi_sleeves.register_change), like K1. A stake of 0 here leaves the sleeve's chain unchanged (the
cluster lens's convention for a trade the account does not take).

Built-in rules (JSON form in a look spec: {"kind": ..., ...}):
    const              {"kind": "const", "m": 1.0}
    sleeve_year        {"kind": "sleeve_year", "table": {"<year>": m, ...}, "default": 1.0}   a stake per year for the
                       sleeve (e.g. Addendum I `weights`, fitted before each year and written into the look's text)
    trade_table        {"kind": "trade_table", "path": "<parquet with entry_time, side, stake>"}  explicit stakes
    wf_terciles        {"kind": "wf_terciles", "descriptor": "riskbp", "levels": [lo, mid, hi], "q": 0.3333,
                        "min_train": 100}   terciles of a signal-table descriptor refitted every 1 January on the
                       signals whose own outcome is known before Y - purge (Addendum I `conviction` shape)
    python             {"kind": "python", "module": "<path.py>", "factory": "<name>", "args": {...}}  any rule
                       written later (lab/r2/tracks/sizing/...), loaded from its file and called as above
`yearly_refit(...)` is the helper for rules fitted once a year.
"""
import importlib.util
import os

import numpy as np
import pandas as pd

PURGE = pd.Timedelta(days=7)


def year_start(y):
    return pd.Timestamp(f"{int(y)}-01-01", tz="UTC")


def yearly_refit(times, fit, apply, years=None, purge=PURGE):
    """For each year Y of `times` (UTC decision times of the trades to stake): model = fit(Y, cutoff) with cutoff =
    1 January Y - purge (the fit must only use outcomes known before cutoff); stakes of that year = apply(model, mask).
    Returns (stakes, {Y: model})."""
    t = pd.DatetimeIndex(times)
    yrs = t.year.to_numpy()
    m = np.ones(len(t))
    models = {}
    for Y in (sorted(set(yrs)) if years is None else years):
        sel = yrs == Y
        if not sel.any():
            continue
        cutoff = year_start(Y) - purge
        models[int(Y)] = fit(int(Y), cutoff)
        m[sel] = apply(models[int(Y)], sel)
    return m, models


class StakeRule:
    name = "stake"
    needs_signals = False

    def stakes(self, trades, ctx):
        raise NotImplementedError

    def describe(self):
        return {"name": self.name}


class Const(StakeRule):
    def __init__(self, m=1.0):
        self.m = float(m)
        self.name = f"const_{self.m:g}"

    def stakes(self, trades, ctx):
        return np.full(len(trades), self.m)


class SleeveYear(StakeRule):
    def __init__(self, table, default=1.0, time_col="entry_time"):
        self.table = {int(k): float(v) for k, v in table.items()}
        self.default = float(default)
        self.time_col = time_col
        self.name = "sleeve_year"

    def stakes(self, trades, ctx):
        y = pd.DatetimeIndex(trades[self.time_col]).year
        return np.array([self.table.get(int(v), self.default) for v in y], float)


class TradeTable(StakeRule):
    def __init__(self, path=None, frame=None, default=None):
        if frame is None:
            import vhi_guard as G
            frame = pd.read_parquet(path, filters=[("entry_time", "<", G.current_cut())])
        self.df = frame
        self.default = default
        self.name = "trade_table"

    def stakes(self, trades, ctx):
        tab = self.df
        if "sleeve" in tab:
            tab = tab[tab.sleeve == ctx["sleeve"]]
        key = pd.DatetimeIndex(tab.entry_time).tz_convert("UTC").as_unit("ns").asi8 * 4 + (tab.side.to_numpy() > 0)
        s = pd.Series(tab.stake.to_numpy(float), index=key)
        k = pd.DatetimeIndex(trades.entry_time).tz_convert("UTC").as_unit("ns").asi8 * 4 + (trades.side.to_numpy() > 0)
        m = s.reindex(k).to_numpy()
        if np.isnan(m).any():
            if self.default is None:
                raise ValueError(f"trade_table: {int(np.isnan(m).sum())} trades of {ctx['sleeve']} have no stake")
            m = np.where(np.isnan(m), float(self.default), m)
        return m


class WFTerciles(StakeRule):
    """Stake by tercile of a descriptor of the trade's signal, terciles refitted every 1 January on the signals whose
    own outcome (taken alone) is known before 1 January minus the purge."""
    needs_signals = True

    def __init__(self, descriptor, levels=(1.0, 1.0, 1.0), q=1 / 3, min_train=100):
        self.d = descriptor
        self.levels = tuple(float(x) for x in levels)
        self.q = float(q)
        self.min_train = int(min_train)
        self.name = f"wf_terciles_{descriptor}"
        self.fits = {}

    def stakes(self, trades, ctx):
        s = ctx["signals"][ctx["sleeve"]]
        use = (s.filled & ~s.refused & ~s.boundary & np.isfinite(s.label)).to_numpy()
        x_all = s[self.d].to_numpy(float)
        xo = pd.Series(x_all, index=s.oid.to_numpy())
        x_tr = xo.reindex(trades.oid.to_numpy()).to_numpy()
        ex = pd.DatetimeIndex(s.exit_alone)

        def fit(Y, cutoff):
            tr = use & np.asarray(ex < cutoff)
            if tr.sum() < self.min_train:
                return None
            lo, hi = np.quantile(x_all[tr], [self.q, 1 - self.q])
            return {"q_lo": float(lo), "q_hi": float(hi), "n_train": int(tr.sum()),
                    "last_outcome_used": str(ex[tr].max())}

        def apply(f, sel):
            if f is None:
                return np.full(int(sel.sum()), 1.0)
            x = x_tr[sel]
            with np.errstate(invalid="ignore"):
                return np.where(x <= f["q_lo"], self.levels[0], np.where(x >= f["q_hi"], self.levels[2], self.levels[1]))

        m, fits = yearly_refit(trades.entry_time, fit, apply, purge=ctx.get("purge", PURGE))
        self.fits[(ctx["sleeve"], ctx["mode"], ctx["exec"])] = fits
        return m


def generic_signal_table(mk, O, sym, mode, sim_alone):
    """Every order of a rule taken alone (sim_alone(orders) -> trades with oid, no_overlap=False): arming time (start
    of its entry bar), fill time, side, stop distance at the fill, P = mid close of the last bar starting before the
    arming time, riskbp = 1e4 x stop distance / P, filled, refused (stop under 3 spreads of the fill bar, or crossed),
    boundary (still open at the last bar), label = R alone (NaN when boundary), exit time alone."""
    es = sim_alone(O)
    idx = mk.index
    last = idx[-1]
    t_arm = idx[np.clip(O.entry_i.to_numpy(), 0, len(idx) - 1)]
    s = pd.DataFrame({"oid": O.oid.to_numpy(), "t_arm": t_arm, "side": O.side.to_numpy()})
    e = es.set_index("oid")
    s["filled"] = s.oid.isin(e.index)
    s["fill_time"] = pd.to_datetime(e.entry_time.reindex(s.oid).to_numpy(), utc=True) if len(e) else pd.NaT
    s["exit_alone"] = pd.to_datetime(e.exit_time.reindex(s.oid).to_numpy(), utc=True) if len(e) else pd.NaT
    risk = e.risk.reindex(s.oid).to_numpy(float) if len(e) else np.full(len(s), np.nan)
    spr = (mk["ao"].to_numpy() - mk["bo"].to_numpy())
    fi = np.searchsorted(idx.values, pd.DatetimeIndex(s.fill_time).tz_convert("UTC").tz_localize(None).values.astype(idx.values.dtype)) \
        if len(e) else np.zeros(len(s), np.int64)
    fi = np.clip(fi, 0, len(idx) - 1)
    reason = e.reason.reindex(s.oid).to_numpy() if len(e) else np.full(len(s), None)
    s["refused"] = s.filled.to_numpy() & ((risk < 3.0 * spr[fi]) | (reason == "gap"))
    s["boundary"] = s.filled.to_numpy() & (pd.DatetimeIndex(s.exit_alone) >= last)
    lab = e.R.reindex(s.oid).to_numpy(float) if len(e) else np.full(len(s), np.nan)
    s["label"] = np.where(s.boundary, np.nan, lab)
    j = np.searchsorted(idx.values, t_arm.tz_localize(None).values.astype(idx.values.dtype), side="left") - 1
    mid = (mk["bc"].to_numpy(np.float64) + mk["ac"].to_numpy(np.float64)) / 2
    s["P"] = np.where(j >= 0, mid[np.maximum(j, 0)], np.nan)
    s["stop_dist"] = risk
    s["riskbp"] = 1e4 * s.stop_dist / s.P
    s["year"] = pd.DatetimeIndex(s.t_arm).year
    return s


def from_spec(d):
    """A stake rule from its JSON form (see module docstring)."""
    if d is None:
        return None
    k = d["kind"]
    if k == "const":
        return Const(d.get("m", 1.0))
    if k == "sleeve_year":
        return SleeveYear(d["table"], d.get("default", 1.0))
    if k == "trade_table":
        return TradeTable(path=d["path"], default=d.get("default"))
    if k == "wf_terciles":
        return WFTerciles(d["descriptor"], d.get("levels", (1, 1, 1)), d.get("q", 1 / 3), d.get("min_train", 100))
    if k == "python":
        import vhi_guard as G
        path = d["module"]
        if not os.path.isabs(path):
            path = os.path.join(os.path.dirname(G.LAB), path) if path.startswith("lab/") else \
                os.path.join(os.path.dirname(os.path.abspath(__file__)), path)
        G.check_path(path)
        spec = importlib.util.spec_from_file_location(f"vhi_stake_{abs(hash(path))}", path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return getattr(mod, d["factory"])(**d.get("args", {}))
    raise ValueError(k)


def check_bounds(m, lo=0.0, hi=2.0):
    m = np.asarray(m, float)
    return bool(np.isfinite(m).all() and (m >= lo).all() and (m <= hi).all())
