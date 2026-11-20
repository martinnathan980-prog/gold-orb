"""Stage 2a of DIRECTION4: the mechanical selection of section 4 on the discovery tables, written as
frozen_candidates.json with its sha256 (printed, and written beside it as frozen_candidates.sha256).

    python3 -B -m scan.select [--discovery DIR] [--out DIR]

Units: ALL15, FX8, IDX4, COM3 and each market alone; a unit's markets for a rule are the unit's markets the rule runs
on (L01 is not run on oil). Figures per rule and unit, on the trades entered in the discovery years (all of them:
the bars end at the wall): n; PF net = sum of positive R / |sum of negative R| over trades; t = kit.stats.t_stat of
the unit's daily sums of net R (entry trading day, days with a trade); PF at costs x1.5; positive years = calendar
years 2013-2018 whose sum of net R is > 0 (a year without a trade is not positive); share of the unit's markets with
a positive total net R (a market without a trade is not positive); largest market share of the profit = the largest
market total / the unit total (undefined, and failing, when the unit total is <= 0).
Eligible: n >= 200 (basket) / 150 (one market); PF >= 1.10; PF x1.5 >= 1.02; >= 4 positive years of 6; basket: >= 65 %
of its markets positive and no market above 50 % of the profit (35 % for ALL15 and FX8); a sibling (grammar.siblings)
with t >= 1.0 on the same unit.
Picked: eligible baskets by t (descending; ties: rule index, then unit order), t >= 2.5, at most 12; then single
markets, t >= 3.0, at most 12; a candidate whose daily result correlates above 0.6 with one already picked (baskets
and single markets alike) is skipped. Daily result = the unit's net R summed per trading day over every business day
of the discovery calendar (zeros kept), Pearson."""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from . import discover as DS
from . import engine as E
from . import grammar as G

YEARS = tuple(range(2013, 2019))
UNIT_ORDER = G.BASKETS + G.MARKETS
SHARE_CAP = {"ALL15": 0.35, "FX8": 0.35, "IDX4": 0.50, "COM3": 0.50}
DAY_AXIS = ((pd.bdate_range("2013-01-01", "2019-01-01") - E.EPOCH) // pd.Timedelta(days=1)).to_numpy(np.int64)
MAX_BASKETS, MAX_SINGLES = 12, 12
T_BASKET, T_SINGLE, CORR_MAX = 2.5, 3.0, 0.6


def _pf(pos, neg):
    if neg > 0:
        return pos / neg
    return math.inf if pos > 0 else 0.0


def _t_rows(D, N):
    """t of the daily sums per row over the days with a trade (N > 0); NaN with fewer than 2 days or sd 0."""
    m = N > 0
    k = m.sum(1)
    s = np.where(m, D, 0.0).sum(1)
    with np.errstate(invalid="ignore", divide="ignore"):
        mean = s / k
        dev = np.where(m, D - mean[:, None], 0.0)
        sd = np.sqrt((dev ** 2).sum(1) / (k - 1))
        t = mean / (sd / np.sqrt(k))
    return np.where((k >= 2) & (sd > 0), t, np.nan)


class Tables:
    """Dense per-market tables of a discovery directory."""

    def __init__(self, ddir):
        with open(os.path.join(ddir, "manifest.json")) as f:
            self.manifest = json.load(f)
        if self.manifest.get("mode") != "trades":
            raise ValueError(f"{ddir} is not a discovery run with trades")
        self.ddir = ddir
        self.markets = tuple(self.manifest["markets"])
        rl, ri = DS.selected_rules(self.manifest["signals"], self.manifest["frames"])
        self.rules = rl
        self.gidx = np.array([ri[r["id"]] for r in rl], np.int64)
        self.pos = {int(g): i for i, g in enumerate(self.gidx)}
        self.id_of = {ri[r["id"]]: r["id"] for r in rl}
        nR, nD = len(rl), len(DAY_AXIS)
        self.D, self.N, self.Y = {}, {}, {}
        self.digests = {}
        for m in self.markets:
            if not DS.is_done(ddir, m, self.manifest):
                raise RuntimeError(f"discovery of {m} is missing or incomplete in {ddir}")
            a = DS.load_market(ddir, m)
            self.digests[m] = str(a["digest"])
            r = np.array([self.pos[int(x)] for x in a["d_rule"]], np.int64)
            dpos = np.searchsorted(DAY_AXIS, a["d_day"])
            if len(dpos) and ((dpos >= nD).any() or (DAY_AXIS[np.clip(dpos, 0, nD - 1)] != a["d_day"]).any()):
                raise ValueError(f"{m}: a trading day outside the discovery calendar")
            Dm = np.zeros((nR, nD))
            Nm = np.zeros((nR, nD), np.int32)
            Dm[r, dpos] = a["d_R"]
            Nm[r, dpos] = a["d_n"]
            self.D[m], self.N[m] = Dm, Nm
            y = {}
            ry = np.array([self.pos[int(x)] for x in a["y_rule"]], np.int64)
            if len(a["y_year"]) and (a["y_year"].max() > YEARS[-1] or a["y_year"].min() < YEARS[0]):
                raise ValueError(f"{m}: a trade entered outside 2013-2018 in the discovery tables")
            yi = a["y_year"] - YEARS[0]
            for k in ("n", "pos", "neg", "pos_s", "neg_s", "R", "Rs", "Rg"):
                arr = np.zeros((nR, len(YEARS)))
                arr[ry, yi] = a["y_" + k]
                y[k] = arr
            self.Y[m] = y
        self.runs_on = np.array([[m in G.markets_of(r["signal"]) for m in self.markets] for r in rl])  # (nR, nM)

    def unit_markets(self, unit):
        return [m for m in G.UNITS[unit] if m in self.markets]

    def unit_series(self, unit, rows=None):
        ms = self.unit_markets(unit)
        sl = slice(None) if rows is None else rows
        D = sum(self.D[m][sl] for m in ms)
        N = sum(self.N[m][sl] for m in ms)
        return D, N


def unit_stats(T):
    """DataFrame: one row per rule and unit (units with at least one market of the run that the rule runs on)."""
    nR = len(T.rules)
    frames = []
    for unit in UNIT_ORDER:
        ms = T.unit_markets(unit)
        if not ms:
            continue
        mi = [T.markets.index(m) for m in ms]
        on = T.runs_on[:, mi]                                         # (nR, k) rule runs on the market
        n_mk = on.sum(1)
        D, N = T.unit_series(unit)
        t = _t_rows(D, N)
        ysum = {k: sum(T.Y[m][k] for m in ms) for k in ("n", "pos", "neg", "pos_s", "neg_s", "R", "Rs", "Rg")}
        n = ysum["n"].sum(1)
        pos, neg = ysum["pos"].sum(1), ysum["neg"].sum(1)
        pos_s, neg_s = ysum["pos_s"].sum(1), ysum["neg_s"].sum(1)
        yrs_pos = ((ysum["R"] > 0) & (ysum["n"] > 0)).sum(1)
        mk_tot = np.stack([T.Y[m]["R"].sum(1) for m in ms], 1)       # (nR, k)
        mk_pos = ((mk_tot > 0) & on).sum(1)
        tot = mk_tot.sum(1)
        with np.errstate(invalid="ignore", divide="ignore"):
            share = np.where(tot > 0, (np.where(on, mk_tot, -np.inf)).max(1) / tot, np.inf)
            frac = np.where(n_mk > 0, mk_pos / n_mk, 0.0)
            meanR = np.where(n > 0, ysum["R"].sum(1) / n, np.nan)
            meanRg = np.where(n > 0, ysum["Rg"].sum(1) / n, np.nan)
            meanRs = np.where(n > 0, ysum["Rs"].sum(1) / n, np.nan)
        frames.append(pd.DataFrame({
            "rule_idx": T.gidx, "rule": [r["id"] for r in T.rules], "signal": [r["signal"] for r in T.rules],
            "family": [r["family"] for r in T.rules], "frame": [r["frame"] for r in T.rules],
            "filter": [r["filter"] for r in T.rules], "exit_h": [r["exit_h"] for r in T.rules],
            "unit": unit, "basket": unit in G.BASKETS, "n_markets": n_mk, "n": n.astype(np.int64),
            "n_days": (N > 0).sum(1), "t": t, "PF": [_pf(a, b) for a, b in zip(pos, neg)],
            "PF_stress": [_pf(a, b) for a, b in zip(pos_s, neg_s)], "years_pos": yrs_pos,
            "markets_pos_frac": frac, "max_market_share": share, "mean_R": meanR, "mean_R_gross": meanRg,
            "mean_R_stress": meanRs}))
    st = pd.concat(frames, ignore_index=True)
    st = st[st.n_markets > 0].reset_index(drop=True)
    return add_eligibility(st)


def add_eligibility(st):
    tmap = {(r, u): t for r, u, t in zip(st.rule, st.unit, st.t)}
    b = st.basket.to_numpy()
    cap = np.array([SHARE_CAP.get(u, 1.0) for u in st.unit])
    sib = []
    for r, u in zip(st.rule, st.unit):
        ts = [tmap.get((s, u)) for s in G.siblings(r)]
        sib.append(max([x for x in ts if x is not None and np.isfinite(x)], default=np.nan))
    st["sibling_t_max"] = sib
    c = {
        "n": st.n.to_numpy() >= np.where(b, 200, 150),
        "PF": st.PF.to_numpy() >= 1.10,
        "PF_stress": st.PF_stress.to_numpy() >= 1.02,
        "years": st.years_pos.to_numpy() >= 4,
        "markets": np.where(b, st.markets_pos_frac.to_numpy() >= 0.65, True),
        "share": np.where(b, st.max_market_share.to_numpy() <= cap, True),
        "sibling": np.nan_to_num(st.sibling_t_max.to_numpy(), nan=-np.inf) >= 1.0,
    }
    ok = np.ones(len(st), bool)
    for k, v in c.items():
        st["ok_" + k] = v
        ok &= v
    st["eligible"] = ok
    return st


def _corr(a, b):
    if a.std() == 0 or b.std() == 0:
        return float("nan")
    return float(np.corrcoef(a, b)[0, 1])


def pick(T, st, log=print):
    """Section 4's picks: list of dicts (in pick order) and the list of skipped candidates (correlation)."""
    unit_rank = {u: i for i, u in enumerate(UNIT_ORDER)}
    el = st[st.eligible].copy()
    el["urank"] = el.unit.map(unit_rank)
    picked, skipped, series = [], [], []
    for stage, is_b, tmin, cap in (("basket", True, T_BASKET, MAX_BASKETS), ("single", False, T_SINGLE, MAX_SINGLES)):
        cand = el[(el.basket == is_b) & (el.t >= tmin)].sort_values(["t", "rule_idx", "urank"],
                                                                    ascending=[False, True, True], kind="mergesort")
        n_stage = 0
        for _, r in cand.iterrows():
            if n_stage >= cap:
                break
            row = T.pos[int(r.rule_idx)]
            D, _ = T.unit_series(r.unit, rows=slice(row, row + 1))
            s = D[0]
            cs = [(_corr(s, q), p["rule"], p["unit"]) for q, p in zip(series, picked)]
            bad = [x for x in cs if np.isfinite(x[0]) and x[0] > CORR_MAX]
            if bad:
                skipped.append({"rule": r.rule, "unit": r.unit, "t": float(r.t), "corr": round(bad[0][0], 4),
                                "with": f"{bad[0][1]} on {bad[0][2]}"})
                continue
            picked.append({"order": len(picked) + 1, "stage": stage, "rule": r.rule, "rule_idx": int(r.rule_idx),
                           "unit": r.unit, "markets": [m for m in G.UNITS[r.unit] if m in G.markets_of(r.signal)],
                           "discovery": {k: _num(r[k]) for k in ("n", "n_days", "t", "PF", "PF_stress", "years_pos",
                                                                 "markets_pos_frac", "max_market_share", "mean_R",
                                                                 "mean_R_gross", "sibling_t_max")},
                           "max_corr_with_picked": round(max([x[0] for x in cs if np.isfinite(x[0])], default=0.0), 4)})
            series.append(s)
            n_stage += 1
            log(f"pick {len(picked)}: {r.rule} on {r.unit}, t {r.t:.2f}")
    return picked, skipped


def _num(v):
    v = float(v)
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    if math.isnan(v):
        return None
    return round(v, 6)


def frozen_text(ddir, log=print):
    """The selection of a discovery directory: (the exact text of frozen_candidates.json, unit stats, picks). Pure
    function of the discovery files (confirm.py recomputes it to bind a candidate list to its discovery)."""
    T = Tables(ddir)
    st = unit_stats(T)
    picked, skipped = pick(T, st, log)
    doc = {"what": "DIRECTION4 section 4: frozen candidates for the confirmation on 2019-2021",
           "rules_sha256": T.manifest["rules_sha256"], "discovery_manifest": T.manifest,
           "discovery_digests": T.digests, "n_rule_units": int(len(st)), "n_eligible": int(st.eligible.sum()),
           "thresholds": {"t_basket": T_BASKET, "t_single": T_SINGLE, "corr_max": CORR_MAX,
                          "max_baskets": MAX_BASKETS, "max_singles": MAX_SINGLES},
           "nothing": len(picked) == 0, "candidates": picked, "skipped_for_correlation": skipped}
    return json.dumps(doc, indent=1, sort_keys=True) + "\n", st, picked


def run(ddir=None, out=None, log=print):
    ddir = ddir or os.path.join(DS.SCAN_DIR, "discovery")
    out = out or DS.SCAN_DIR
    os.makedirs(out, exist_ok=True)
    txt, st, picked = frozen_text(ddir, log)
    st.to_csv(os.path.join(out, "unit_stats.csv"), index=False, float_format="%.10g")
    p = os.path.join(out, "frozen_candidates.json")
    if os.path.isfile(p):
        with open(p) as f:
            if f.read() != txt:
                raise RuntimeError(f"{p} exists with other content: the frozen list is never overwritten "
                                   "(move it away only if it belongs to another run)")
    else:
        with open(p + ".tmp", "w") as f:
            f.write(txt)
        os.replace(p + ".tmp", p)
    sha = hashlib.sha256(txt.encode()).hexdigest()
    with open(os.path.join(out, "frozen_candidates.sha256"), "w") as f:
        f.write(f"{sha}  frozen_candidates.json\n")
    log(f"{len(picked)} candidates ({'nothing' if not picked else 'see the list'}); {int(st.eligible.sum())} "
        f"eligible rule-units of {len(st)}")
    log(f"frozen_candidates.json sha256 {sha}")
    return p, sha, st, picked


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--discovery")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    run(a.discovery, a.out)


if __name__ == "__main__":
    sys.exit(main())
