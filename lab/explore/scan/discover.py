"""Stage 1 of DIRECTION4: discovery on bars BEFORE 2019-01-01 only.

    python3 -B -m scan.discover [--procs 3] [--out DIR] [--counts-only] [--synthetic noise|planted --seed S]
                                [--markets m1,m2] [--signals T01,R07 --frames H1,H4]

The reader (`read_bars`) asks the kit for the bars with the kit's period end moved to the wall (2019-01-01 00:00 UTC),
so no row of 2019 or later is even read from the prepared files, then cuts again and asserts; `run_market` refuses
bars that reach the wall. One file per market under DIR (default ~/explore_data/scan/discovery, or .../counts with
--counts-only), written atomically; a restart skips the markets whose file is complete and gives the same tables.
--counts-only writes the number of signals per rule (after its filter) and computes no return and no trade."""
import argparse
import contextlib
import hashlib
import json
import os
import sys
import time
from concurrent.futures import ProcessPoolExecutor

import numpy as np
import pandas as pd

from kit import data as D
from kit import sim

from . import engine as E
from . import grammar as G
from . import signals as SG
from . import worlds as W

WALL = pd.Timestamp("2019-01-01", tz="UTC")
SCAN_DIR = os.path.expanduser(os.environ.get("SCAN_DIR", "~/explore_data/scan"))


class WallError(RuntimeError):
    pass


@contextlib.contextmanager
def _kit_end(t):
    """The kit's period end set to t while reading (no reader returns, and no prepared-file read asks for, a row at
    or after t); restored after."""
    old = D._STATE["end"]
    if t > old:
        raise WallError(f"the kit's period end {old} is before {t}")
    D._STATE["end"] = t
    try:
        yield
    finally:
        D._STATE["end"] = old


def cut_at_wall(bars):
    """Bars whose open is before the wall (each ends at or before it); asserts it."""
    idx = pd.DatetimeIndex(bars.index)
    out = bars[idx < WALL]
    if len(out) and not (pd.DatetimeIndex(out.index).max() + pd.Timedelta(hours=1) <= WALL):
        raise WallError("a discovery bar ends after the wall")
    return out


def read_bars(market, synthetic=None, seed=0):
    """Discovery bars of a market: real (kit.data.load_bars under the wall) or synthetic (scan.worlds), cut at the
    wall."""
    if synthetic:
        b = W.bars(market, synthetic, seed)
        att = dict(b.attrs)
        b = cut_at_wall(b)
        b.attrs.update(att)
    else:
        with _kit_end(WALL):
            b = D.load_bars(market)
            att = dict(b.attrs)
            b = cut_at_wall(b)
            b.attrs.update(att)
    if len(b) and pd.DatetimeIndex(b.index).max() >= WALL:
        raise WallError(f"{market}: a bar of 2019 or later reached discovery")
    return b


def selected_rules(signals=None, frames=None):
    """The rule list (global indices of rules.csv) of the run: the whole grammar, or a reduced one (tests)."""
    allr = G.rules()
    idx = {r["id"]: i for i, r in enumerate(allr)}
    keep = [r for r in allr if (not signals or r["signal"] in signals) and (not frames or r["frame"] in frames)]
    return keep, idx


def run_market(market, bars, rule_list, rule_index, counts_only=False):
    """Discovery of one market: dict of arrays (counts, and the per-rule aggregates unless counts_only)."""
    idx = pd.DatetimeIndex(bars.index)
    if len(idx) and idx.max() >= WALL:
        raise WallError(f"{market}: run_market refuses bars at or after {WALL}")
    rl = [r for r in rule_list if market in G.markets_of(r["signal"])]
    sf = sorted({(r["signal"], r["frame"]) for r in rl})
    t0 = time.time()
    tables = SG.signal_tables(bars, market, WALL, sig_frames=sf)
    ci, cn, ce = E.signal_counts(tables, rl, rule_index, bars.index)
    out = {"c_rule": ci, "c_signals": cn, "c_enterable": ce}
    meta = {"market": market, "n_bars": int(len(bars)), "first_bar": str(idx.min()) if len(idx) else None,
            "last_bar": str(idx.max()) if len(idx) else None, "signal_s": round(time.time() - t0, 2)}
    if not counts_only:
        t1 = time.time()
        with _kit_end(WALL):
            book = sim.Book(bars, market)
            tr = E.simulate_rules(market, book, tables, rl, rule_index)
        ag = E.aggregate(tr, None, WALL)
        out.update(ag)
        meta["sim_counts"] = E.sim_counts(tr)
        meta["sim_s"] = round(time.time() - t1, 2)
        tk = np.zeros(len(ci), np.int64)
        if len(ag["y_rule"]):
            s = pd.Series(ag["y_n"]).groupby(ag["y_rule"]).sum()
            pos = {k: i for i, k in enumerate(ci.tolist())}
            for k, v in s.items():
                tk[pos[int(k)]] = int(v)
        out["c_trades"] = tk
    out["meta"] = np.array(json.dumps(meta, sort_keys=True))
    return out


def digest(arrs):
    """sha256 of a market file's tables (every array but meta, in name order)."""
    h = hashlib.sha256()
    for k in sorted(arrs):
        if k == "meta":
            continue
        a = np.ascontiguousarray(arrs[k])
        h.update(k.encode())
        h.update(str(a.dtype).encode())
        h.update(a.tobytes())
    return h.hexdigest()


def _path(out, market):
    return os.path.join(out, f"{market}.npz")


def load_market(out, market):
    with np.load(_path(out, market), allow_pickle=False) as z:
        return {k: z[k] for k in z.files}


def is_done(out, market, manifest):
    p = _path(out, market)
    if not os.path.isfile(p):
        return False
    try:
        a = load_market(out, market)
    except Exception:
        return False
    return str(a.get("manifest_sha", "")) == manifest_sha(manifest) and str(a.get("digest", "")) == digest(
        {k: v for k, v in a.items() if k not in ("digest", "manifest_sha")})


def manifest_sha(manifest):
    return hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()


def _work(args):
    market, out, manifest, counts_only, synthetic, seed, signals, frames = args
    rl, ri = selected_rules(signals, frames)
    t0 = time.time()
    b = read_bars(market, synthetic, seed)
    arrs = run_market(market, b, rl, ri, counts_only)
    dg = digest(arrs)
    arrs["digest"] = np.array(dg)
    arrs["manifest_sha"] = np.array(manifest_sha(manifest))
    tmp = _path(out, market) + f".tmp{os.getpid()}.npz"
    np.savez(tmp, **arrs)
    os.replace(tmp, _path(out, market))
    import resource
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss // 1024
    return market, dg, f"{time.time() - t0:.1f} s, peak {rss} MB"


def make_manifest(counts_only, synthetic, seed, signals, frames, markets):
    return {"stage": "discovery", "mode": "counts" if counts_only else "trades", "wall": str(WALL),
            "rules_sha256": G.sha256_text(G.csv_text()),
            "source": f"synthetic:{synthetic}:{seed}" if synthetic else "real (kit.data.load_bars, cut at the wall)",
            "signals": sorted(signals) if signals else None, "frames": sorted(frames) if frames else None,
            "markets": list(markets), "max_wait_h": E.MAX_WAIT_H, "stop": list(G.STOP)}


def run(out=None, procs=1, counts_only=False, synthetic=None, seed=0, markets=None, signals=None, frames=None,
        log=print):
    markets = tuple(markets or G.MARKETS)
    out = out or os.path.join(SCAN_DIR, "counts" if counts_only else "discovery")
    os.makedirs(out, exist_ok=True)
    if not synthetic:
        G.check_rules_file()
    man = make_manifest(counts_only, synthetic, seed, signals, frames, markets)
    mp = os.path.join(out, "manifest.json")
    if os.path.isfile(mp):
        with open(mp) as f:
            old = json.load(f)
        if old != man:
            raise RuntimeError(f"{out} holds another run ({mp}); use another --out or remove it")
    else:
        with open(mp + ".tmp", "w") as f:
            json.dump(man, f, indent=1, sort_keys=True)
        os.replace(mp + ".tmp", mp)
    todo = [m for m in markets if not is_done(out, m, man)]
    for m in markets:
        if m not in todo:
            log(f"discover {m}: done already, skipped")
    jobs = [(m, out, man, counts_only, synthetic, seed, signals, frames) for m in todo]
    if procs <= 1 or len(jobs) <= 1:
        for j in jobs:
            m, dg, s = _work(j)
            log(f"discover {m}: {s}, digest {dg[:16]}")
    else:
        with ProcessPoolExecutor(max_workers=procs) as ex:
            for m, dg, s in ex.map(_work, jobs):
                log(f"discover {m}: {s}, digest {dg[:16]}")
    dg = {m: str(load_market(out, m)["digest"]) for m in markets}
    with open(os.path.join(out, "digests.json"), "w") as f:
        json.dump(dg, f, indent=1, sort_keys=True)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out")
    ap.add_argument("--procs", type=int, default=1)
    ap.add_argument("--counts-only", action="store_true")
    ap.add_argument("--synthetic", choices=("noise", "planted", "fat"))
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--markets")
    ap.add_argument("--signals")
    ap.add_argument("--frames")
    a = ap.parse_args(argv)
    sp = lambda s: tuple(x for x in s.split(",") if x) if s else None  # noqa: E731
    t0 = time.time()
    out = run(a.out, a.procs, a.counts_only, a.synthetic, a.seed, sp(a.markets), sp(a.signals), sp(a.frames))
    print(f"discovery written to {out} in {time.time() - t0:.0f} s", flush=True)


if __name__ == "__main__":
    sys.exit(main())
