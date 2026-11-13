"""In-sample lab frames -> the broker's M1 bars (SPEC 7, "Data"), and the lab frame rebuilt from those bars.

    python3 -I lab/robot/check/export_frames.py [--syms xauusd,us100,btcusd,ethusd] [--from 2021-01-01] [--to 2022-01-01]
                                                [--raw-h 0] [--tag NAME]

Reads lab/data/fp/<sym>_m1.parquet with the row filter ts < 2022-01-01 (and ts >= --from) INSIDE the read call, never
a later row. Gold bars starting 17:00-17:59 New York are dropped (SPEC 2.2: the EA's mask drops them, the daily gold
closure; in sample the lab frame holds 20, all on 2012-12-31 17:00-17:58), so that the bar file and the rebuilt frame
are exactly the EA's kept bars and the references run on them (before, those 20 bars seeded the lab's GFP hour ATR of
January 2013 and three stops differed from the EA's). Writes, under lab/robot/check/out/ (git-ignored):
  bars/<SYMBOL>.r_<tag>.bin     the bars as the broker publishes them: server time (New York + 7 h), bid O/H/L/C on the
                                2-digit grid (until the Mac says otherwise), spread = round((ao - bo) / point) in points,
                                i.e. the lab's whole spread, commission included. Binary layout read by mock_replay.h:
                                b"CRB1", int32 digits, int64 n, n x <int64 time, int32 o, h, l, c, int32 spread>.
  frames/<sym>_<tag>.parquet    the lab frame rebuilt from those numbers: bid = points / 100, ask = (points + spread) / 100
                                (the nearest double of the exact decimal, as NormalizeDouble's half-away rounding gives on
                                the grid); UTC from the server time with pont.server_to_utc (independent of the EA's clock)
  manifest_<tag>.json           counts, first/last bar, rounding sizes
--raw-h N (tick-mode gold worlds, SPEC 7): raw bid = lab bid + N points and raw spread = lab spread - 2N points (clipped
  at 0), so that the EA built with h = N points sees the lab's quotes again; the rebuilt frame stays the lab's quotes.
"""
import argparse
import json
import os
import sys

os.environ.setdefault("NUMBA_CACHE_DIR", "/tmp/claude-0/-home-user-gold-orb/340d9f5a-4d28-5733-90cb-10a10699d00b/scratchpad/numba")
sys.dont_write_bytecode = True

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.dirname(HERE)
LAB = os.path.dirname(ROBOT)
OUT = os.path.join(HERE, "out")
CUT = pd.Timestamp("2022-01-01", tz="UTC")
NY = "America/New_York"
BROKER = {"xauusd": "XAUUSD.r", "us100": "US100.r", "btcusd": "BTCUSD.r", "ethusd": "ETHUSD.r"}
DIGITS = 2
REC = np.dtype([("t", "<i8"), ("o", "<i4"), ("h", "<i4"), ("l", "<i4"), ("c", "<i4"), ("s", "<i4")])
sys.path.insert(0, os.path.join(LAB, "live_ai"))


def xau_closure_bars(m1):
    """gold bars starting 17:00-17:59 New York (SPEC 2.2, the xau mask: the daily closure)"""
    return m1.index.tz_convert(NY).hour == 17


def load_lab(sym, start=None, end=None):
    """The in-sample lab frame, cut inside the read call (never a 2022+ row in memory); gold without its 17:00-17:59 New
    York bars (the EA's mask drops them: the rebuilt frame is then the EA's kept bars)."""
    hi = CUT if end is None else min(pd.Timestamp(end, tz="UTC"), CUT)
    filt = [("ts", "<", hi)]
    if start is not None:
        filt.append(("ts", ">=", pd.Timestamp(start, tz="UTC")))
    m1 = pd.read_parquet(os.path.join(LAB, "data", "fp", f"{sym}_m1.parquet"), filters=filt)
    assert len(m1) and m1.index.max() < CUT and m1.index.is_monotonic_increasing and m1.index.is_unique
    if sym == "xauusd":
        m1 = m1[~xau_closure_bars(m1)]
    return m1


def server_secs(idx):
    srv = idx.tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)          # build_fp_frames.py: FP server clock
    return srv.values.astype("datetime64[s]").astype(np.int64)


def to_points(m1, raw_h=0):
    sc = 10 ** DIGITS
    pts = {k: np.rint(m1["b" + k].to_numpy() * sc).astype(np.int64) + raw_h for k in "ohlc"}
    spread = np.rint((m1["ao"] - m1["bo"]).to_numpy() * sc).astype(np.int64) - 2 * raw_h
    spread = np.maximum(spread, 0)
    return pts, spread


def write_bin(path, t, pts, spread):
    rec = np.empty(len(t), REC)
    rec["t"] = t
    for k in "ohlc":
        assert (pts[k] > 0).all() and (pts[k] < 2**31).all()
        rec[k] = pts[k]
    rec["s"] = spread
    with open(path, "wb") as f:
        f.write(b"CRB1")
        f.write(np.int32(DIGITS).tobytes())
        f.write(np.int64(len(t)).tobytes())
        f.write(rec.tobytes())


def read_bin(path):
    with open(path, "rb") as f:
        assert f.read(4) == b"CRB1"
        digits = int(np.frombuffer(f.read(4), "<i4")[0])
        n = int(np.frombuffer(f.read(8), "<i8")[0])
        rec = np.frombuffer(f.read(n * REC.itemsize), REC)
    return digits, rec


def rebuild(rec, digits=DIGITS, raw_h=0):
    """The lab frame from the broker bars: bid = points / 10^d - h, ask = (points + spread) / 10^d + h."""
    import pont
    sc = 10 ** digits
    out = {}
    for k in "ohlc":
        p = rec[k].astype(np.int64)
        out["b" + k] = (p - raw_h) / sc
        out["a" + k] = (p + rec["s"].astype(np.int64) + raw_h) / sc
    utc = pont.server_to_utc(rec["t"].astype(np.int64))
    return pd.DataFrame({k: out[k] for k in ("bo", "bh", "bl", "bc", "ao", "ah", "al", "ac")},
                        index=pd.DatetimeIndex(utc).rename("ts"))


def export(sym, start=None, end=None, raw_h=0, tag=None):
    m1 = load_lab(sym, start, end)
    assert sym != "xauusd" or not xau_closure_bars(m1).any()
    tag = tag or f"{(start or 'start')}_{(end or '2022-01-01')}".replace("-", "")
    t = server_secs(m1.index)
    assert (np.diff(t) > 0).all(), "server time not strictly increasing"
    pts, spread = to_points(m1, raw_h)
    os.makedirs(os.path.join(OUT, "bars"), exist_ok=True)
    os.makedirs(os.path.join(OUT, "frames"), exist_ok=True)
    pb = os.path.join(OUT, "bars", f"{BROKER[sym]}_{tag}.bin")
    write_bin(pb, t, pts, spread)
    digits, rec = read_bin(pb)
    fr = rebuild(rec, digits, raw_h)
    assert (fr.index == m1.index.as_unit(fr.index.unit)).all(), "server -> UTC round trip"
    fr.index = m1.index                                     # the official index object's unit
    pf = os.path.join(OUT, "frames", f"{sym}_{tag}.parquet")
    fr.to_parquet(pf)
    sp_lab = np.rint((m1["ao"] - m1["bo"]).to_numpy() * 10 ** DIGITS)
    return {"sym": sym, "broker": BROKER[sym], "tag": tag, "bars": int(len(m1)), "first": str(m1.index[0]), "last": str(m1.index[-1]),
            "bin": os.path.relpath(pb, ROBOT), "frame": os.path.relpath(pf, ROBOT), "raw_h": raw_h,
            "max_abs_bid_rounding": float((fr["bo"] - m1["bo"]).abs().max()) if raw_h == 0 else None,
            "max_abs_ask_rounding": float((fr["ao"] - m1["ao"]).abs().max()) if raw_h == 0 else None,
            "spread_points_median": float(np.median(sp_lab)), "spread_clipped_at_0": int((sp_lab - 2 * raw_h < 0).sum())}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--syms", default="xauusd,us100,btcusd,ethusd")
    ap.add_argument("--from", dest="start")
    ap.add_argument("--to", dest="end")
    ap.add_argument("--raw-h", type=int, default=0)
    ap.add_argument("--tag")
    a = ap.parse_args(argv)
    if a.end and pd.Timestamp(a.end, tz="UTC") > CUT:
        raise SystemExit("--to after 2022-01-01 is refused: in-sample data only")
    rows = [export(s, a.start, a.end, a.raw_h, a.tag) for s in a.syms.split(",")]
    tag = rows[0]["tag"]
    with open(os.path.join(OUT, f"manifest_{tag}.json"), "w") as f:
        json.dump(rows, f, indent=1)
    for r in rows:
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
