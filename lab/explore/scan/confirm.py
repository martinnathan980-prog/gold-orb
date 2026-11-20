"""Stage 2b of DIRECTION4: confirmation on 2019-2021 of the FROZEN candidates only (section 5).

    python3 -B -m scan.confirm --candidates ~/explore_data/scan/frozen_candidates.json --sha256 <committed hash>
                               [--discovery DIR] [--out DIR]

The wall (section 7) and the binding of the list to its discovery, all checked before anything is computed:
- the list's sha256 must equal the hash given on the command line, which must be the hash the lead COMMITTED (run_all.sh
  takes it only from FROZEN_SHA, never from the frozen_candidates.sha256 that select.py writes);
- the list's rules_sha256 must be the sha256 of scan/rules.csv, and scan/rules.csv must be the list grammar.py makes;
- every candidate must be a rule of rules.csv (same index), on a unit of the grammar, with markets = the unit's markets
  the rule runs on;
- the selection recomputed from the discovery directory (default: `discovery` beside the list) must give this very
  list, byte for byte (so the discovery manifest and per-market digests, the figures and the picks are those of the
  discovery files: an edited, shortened or foreign list is refused);
- confirmation runs once per list: an existing confirmation.json of another list is never replaced, a second run of
  the same list must reproduce it exactly, and every run is appended to confirmation_runs.log.
For each candidate (same rule, same unit, nothing changed): the
rule's signals on the bars 2013-2021 (indicators warm up on the earlier years as in discovery), sim.simulate as in
discovery, and the trades ENTERED in 2019-01-01 .. 2021-12-31 (UTC) are judged:
t on daily sums >= 1.65; PF >= 1.08; PF at costs x1.5 >= 1.00; >= 2 positive years of 3 (a year without a trade is not
positive); a basket: >= 60 % of its markets with a positive total; the kit's random-entry null (stats.null_test, 2,000
draws, the rule's own exit and stop, mode 'every', joint same-day draws for legs decided together) at or above the
90th percentile. The same-year null (within='year') is reported, as information. The null's books are the bars from
2019-01-01 on, so its random days are confirmation days only (D20 needs 20 completed days: draws in the first weeks of
2019 have no stop and are not drawn). Nothing is computed for any rule outside the list."""
import argparse
import hashlib
import json
import math
import os
import sys

import numpy as np
import pandas as pd

from kit import data as D
from kit import sim
from kit import stats as ST

from . import discover as DS
from . import engine as E
from . import grammar as G
from . import select as SL
from . import signals as SG
from . import worlds as W

C0 = pd.Timestamp("2019-01-01", tz="UTC")
C1 = pd.Timestamp("2022-01-01", tz="UTC")
CONF_YEARS = (2019, 2020, 2021)
N_DRAWS = 2000


class HashError(RuntimeError):
    pass


class BindError(RuntimeError):
    """The candidate list is not the frozen output of this discovery, or confirmation already ran on another list."""


def read_candidates(path, sha):
    with open(path, "rb") as f:
        raw = f.read()
    got = hashlib.sha256(raw).hexdigest()
    if not sha or got != sha.strip().lower():
        raise HashError(f"{path}: sha256 {got} is not the frozen hash given ({sha}): refused")
    return json.loads(raw.decode())


def check_binding(doc, raw, ddir):
    """Section 7's wall beyond the hash: the list is the selection of the discovery in `ddir` (see the module text)."""
    rsha = G.check_rules_file()
    if doc.get("rules_sha256") != rsha:
        raise BindError(f"rules_sha256 {doc.get('rules_sha256')} of the list is not scan/rules.csv's {rsha}")
    idx = {r["id"]: i for i, r in enumerate(G.rules())}
    for c in doc.get("candidates", []):
        rid = c.get("rule")
        if rid not in idx:
            raise BindError(f"candidate {rid}: not a rule of scan/rules.csv")
        if c.get("rule_idx") != idx[rid]:
            raise BindError(f"candidate {rid}: rule_idx {c.get('rule_idx')} is not its index {idx[rid]}")
        if c.get("unit") not in G.UNITS:
            raise BindError(f"candidate {rid}: unit {c.get('unit')} is not a unit of the grammar")
        sig = G.parse(rid)[0]
        want = [m for m in G.UNITS[c["unit"]] if m in G.markets_of(sig)]
        if c.get("markets") != want:
            raise BindError(f"candidate {rid} on {c['unit']}: markets {c.get('markets')} are not the unit's {want}")
    if not os.path.isfile(os.path.join(ddir, "manifest.json")):
        raise BindError(f"{ddir}: no discovery directory to bind the list to")
    txt, _, _ = SL.frozen_text(ddir, log=lambda *a: None)
    if txt.encode() != raw:
        raise BindError(f"the list is not the selection of the discovery in {ddir} (recomputed: sha256 "
                        f"{hashlib.sha256(txt.encode()).hexdigest()}): refused")


def _runs_log(out, entry):
    with open(os.path.join(out, "confirmation_runs.log"), "a") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")


def _source(doc):
    src = doc["discovery_manifest"]["source"]
    if src.startswith("synthetic:"):
        _, world, seed = src.split(":")
        return world, int(seed)
    return None, 0


def full_bars(market, world, seed):
    if world:
        b = W.bars(market, world, seed)
        att = dict(b.attrs)
        b = b[pd.DatetimeIndex(b.index) < C1]
        b.attrs.update(att)
        return b
    return D.load_bars(market)              # the kit's lock: rows strictly before 2022-01-01


def _pf(R):
    return ST.pf(np.asarray(R, float))


def _num(v):
    if v is None:
        return None
    v = float(v)
    if math.isinf(v):
        return "inf" if v > 0 else "-inf"
    return None if math.isnan(v) else round(v, 6)


def confirm_one(cand, world, seed, cache):
    rid = cand["rule"]
    r = dict(zip(("signal", "frame", "filter", "exit_h"), G.parse(rid)))
    r["id"] = rid
    markets = cand["markets"]
    trades, books_null = [], {}
    for m in markets:
        if m not in cache:
            cache[m] = full_bars(m, world, seed)
        b = cache[m]
        tabs = SG.signal_tables(b, m, C1 if world else D.period_end(), sig_frames=[(r["signal"], r["frame"])])
        sig = SG.rule_signals(tabs, [r], {rid: 0})
        if len(sig) == 0:
            continue
        sig["market"] = m
        tr = sim.simulate(sig, {m: sim.Book(b, m)}, exit=("hours", r["exit_h"]), stop=G.STOP, mode="one",
                          max_wait_h=E.MAX_WAIT_H)
        et = pd.DatetimeIndex(tr["entry_time"])
        tr = tr[np.asarray((et >= C0) & (et < C1))]
        if len(tr):
            trades.append(tr)
            bn = b[pd.DatetimeIndex(b.index) >= C0]
            bn.attrs.update(b.attrs)
            books_null[m] = sim.Book(bn, m)
    t = pd.concat(trades, ignore_index=True).sort_values(["entry_time", "market"], kind="mergesort").reset_index(
        drop=True) if trades else pd.DataFrame()
    basket = cand["unit"] in G.BASKETS
    res = {"rule": rid, "unit": cand["unit"], "markets": markets, "order": cand["order"], "stage": cand["stage"],
           "n": int(len(t))}
    if len(t) == 0:
        res.update(confirmed=False, bars={"trades": False}, note="no trade entered in 2019-2021")
        return res
    ds = ST.daily_sums(t)
    yr = ST.by_year(t)
    years_pos = int(sum(1 for y in CONF_YEARS if y in yr.index and yr[y] > 0))
    mk = t.groupby("market")["R"].sum()
    mpos = sum(1 for m in markets if m in mk.index and mk[m] > 0) / len(markets)
    ex, stop = ("hours", r["exit_h"]), G.STOP
    null = ST.null_test(t, books_null, exit=ex, stop=stop, n_draws=N_DRAWS)
    try:
        nyear = ST.null_test(t, books_null, exit=ex, stop=stop, n_draws=N_DRAWS, within="year")
        ny = {"percentile": _num(nyear.get("percentile")), "year_room_share": _num(nyear.get("year_room_share")),
              "year_no_room": bool(nyear.get("year_no_room", False))}
    except ValueError as e:
        ny = {"percentile": None, "error": str(e)[:200]}
    fig = {"t_daily": ST.t_stat(ds), "PF": _pf(t.R), "PF_stress": _pf(t.R_stress), "years_pos": years_pos,
           "by_year_R": {int(k): float(v) for k, v in yr.items()}, "markets_pos_frac": mpos,
           "by_market_R": {k: float(v) for k, v in mk.items()}, "mean_R": float(t.R.mean()),
           "mean_R_gross": float(t.R_gross.mean()), "null_pct": float(null["percentile"]),
           "null_joint_groups": int(null.get("joint_groups", 0))}
    bars = {"t_daily>=1.65": bool(np.isfinite(fig["t_daily"]) and fig["t_daily"] >= 1.65),
            "PF>=1.08": fig["PF"] >= 1.08, "PF_stress>=1.00": fig["PF_stress"] >= 1.00,
            "years_pos>=2of3": years_pos >= 2, "null>=90": fig["null_pct"] >= 90.0}
    if basket:
        bars["markets_pos>=60%"] = mpos >= 0.60
    res.update({k: (_num(v) if isinstance(v, float) else v) for k, v in fig.items()})
    res["null_same_year_information"] = ny
    res["bars"] = {k: bool(v) for k, v in bars.items()}
    res["confirmed"] = all(res["bars"].values())
    return res


def run(cand_path, sha, out=None, log=print, ddir=None):
    with open(cand_path, "rb") as f:
        raw = f.read()
    doc = read_candidates(cand_path, sha)
    sha = sha.strip().lower()
    out = out or os.path.dirname(os.path.abspath(cand_path))
    ddir = ddir or os.path.join(os.path.dirname(os.path.abspath(cand_path)), "discovery")
    check_binding(doc, raw, ddir)
    os.makedirs(out, exist_ok=True)
    p = os.path.join(out, "confirmation.json")
    old = None
    if os.path.isfile(p):
        with open(p) as f:
            old = f.read()
        prev = json.loads(old).get("candidates_sha256")
        if prev != sha:
            _runs_log(out, {"at": pd.Timestamp.now(tz="UTC").isoformat(), "candidates_sha256": sha,
                            "event": f"refused: confirmation.json holds the list {prev}"})
            raise BindError(f"{p} holds the confirmation of another list ({prev}): confirmation runs once, refused")
    _runs_log(out, {"at": pd.Timestamp.now(tz="UTC").isoformat(), "candidates_sha256": sha, "event": "start",
                    "again": old is not None})
    world, seed = _source(doc)
    cache, results = {}, []
    for c in doc["candidates"]:
        res = confirm_one(c, world, seed, cache)
        results.append(res)
        log(f"confirm {c['rule']} on {c['unit']}: n {res['n']}, t {res.get('t_daily')}, PF {res.get('PF')}, "
            f"null {res.get('null_pct')}: {'CONFIRMED' if res['confirmed'] else 'not confirmed'}")
    rep = {"what": "DIRECTION4 section 5: confirmation on trades entered in 2019-2021",
           "candidates_sha256": sha, "source": doc["discovery_manifest"]["source"],
           "n_candidates": len(doc["candidates"]), "n_confirmed": sum(r["confirmed"] for r in results),
           "nothing": doc["nothing"], "results": results}
    txt = json.dumps(rep, indent=1, sort_keys=True)
    rsha = hashlib.sha256(txt.encode()).hexdigest()
    if old is not None and old != txt:
        _runs_log(out, {"at": pd.Timestamp.now(tz="UTC").isoformat(), "candidates_sha256": sha,
                        "event": "refused: a second run differs from confirmation.json", "result_sha256": rsha})
        raise BindError(f"{p}: a second run of the same list gives other results (not deterministic): kept the first")
    if old is None:
        with open(p + ".tmp", "w") as f:
            f.write(txt)
        os.replace(p + ".tmp", p)
    _runs_log(out, {"at": pd.Timestamp.now(tz="UTC").isoformat(), "candidates_sha256": sha, "event": "done",
                    "n_confirmed": rep["n_confirmed"], "result_sha256": rsha})
    log(f"{rep['n_confirmed']} confirmed of {rep['n_candidates']}; written {p} (sha256 {rsha})")
    return rep


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates", default=os.path.join(DS.SCAN_DIR, "frozen_candidates.json"))
    ap.add_argument("--sha256", required=True, help="the hash of the list as COMMITTED by the lead")
    ap.add_argument("--discovery", help="discovery directory (default: 'discovery' beside the list)")
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    run(a.candidates, a.sha256, a.out, ddir=a.discovery)


if __name__ == "__main__":
    sys.exit(main())
