"""H1, H4 and D1 frames from the kit's hourly bars (GRAMMAR.md 'Frames').

The session clock is New York + 7 h (17:00 New York = 00:00 of the clock), as kit.data.trading_day. A D1 bar is one
day of that clock (17:00 to 17:00 New York); an H4 bar is one of its six 4-hour blocks (17-21, 21-01, 01-05, 05-09,
09-13, 13-17 New York). An hourly bar belongs to the block that holds its OPEN.

known_at of an H4 / D1 bar = the scheduled end of its block (17:00, 21:00, ... New York). For every block whose last
hourly bar ends at the block's end (the normal case) this is the end of its last hourly bar, the text of DIRECTION4;
a block whose bars stop earlier (an early close, a data hole) is not known to be complete before its scheduled end,
so it is known then (never earlier than the end of its last hourly bar). A frame is built for a given `now` (the
time of the build): a block is emitted only if its scheduled end is <= now, so a build on bars cut at time c with
now = c never sees a partial block.

The H1 frame is the bars themselves, known at open + 1 h."""
import numpy as np
import pandas as pd

NY = "America/New_York"
H = pd.Timedelta(hours=1)
FRAMES = ("H1", "H4", "D1")


def _clock(idx):
    """Naive session clock (New York wall time + 7 h) of each bar open."""
    return pd.DatetimeIndex(idx).tz_convert(NY).tz_localize(None) + pd.Timedelta(hours=7)


def _to_utc(naive_clock):
    """Session-clock naive times -> UTC (back to New York wall time, then localised; DST changes happen on Sunday
    02:00 New York, inside the weekend closure)."""
    ny = pd.DatetimeIndex(naive_clock) - pd.Timedelta(hours=7)
    return ny.tz_localize(NY, ambiguous=np.ones(len(ny), bool), nonexistent="shift_forward").tz_convert("UTC")


def block_ends(idx, frame):
    """Scheduled UTC end of the block holding each bar (the bar's own end for H1)."""
    idx = pd.DatetimeIndex(idx)
    if frame == "H1":
        return idx + H
    s = _clock(idx)
    if frame == "H4":
        start = s.floor("4h")
        return _to_utc(start + pd.Timedelta(hours=4))
    if frame == "D1":
        return _to_utc(s.normalize() + pd.Timedelta(days=1))
    raise ValueError(frame)


def build(h1, frame, now):
    """Frame bars from hourly bars: DataFrame with integer index 0..n-1 and columns open high low close, start (UTC
    open of the first hourly bar), last_end (UTC end of the last hourly bar), known_at (UTC), n_bars, hour_ny (New
    York hour of the bar's open, for the session filters). Only blocks complete at `now` (scheduled end <= now)."""
    now = pd.Timestamp(now)
    idx = pd.DatetimeIndex(h1.index)
    if idx.tz is None:
        raise ValueError("bars need a UTC index")
    if not idx.is_monotonic_increasing or not idx.is_unique:
        raise ValueError("bars index must be increasing and unique")
    if len(idx) and (idx + H).max() > now:
        raise ValueError(f"a bar ends after now={now}: the bars and now disagree")
    o, h, l, c = (h1[k].to_numpy(float) for k in ("open", "high", "low", "close"))
    end = block_ends(idx, frame)
    if frame == "H1":
        out = pd.DataFrame({"open": o, "high": h, "low": l, "close": c, "start": idx, "last_end": idx + H,
                            "known_at": end, "n_bars": np.ones(len(idx), np.int64)})
    else:
        key = end.as_unit("ns").asi8
        brk = np.r_[True, key[1:] != key[:-1]] if len(key) else np.zeros(0, bool)
        if len(key) and (np.diff(key) < 0).any():
            raise ValueError("block ends not increasing")
        g = np.cumsum(brk) - 1
        first = np.flatnonzero(brk)
        last = np.r_[first[1:] - 1, len(key) - 1] if len(first) else first
        out = pd.DataFrame({
            "open": o[first], "high": np.maximum.reduceat(h, first) if len(first) else h[:0],
            "low": np.minimum.reduceat(l, first) if len(first) else l[:0], "close": c[last],
            "start": idx[first], "last_end": idx[last] + H, "known_at": end[first],
            "n_bars": np.bincount(g).astype(np.int64) if len(first) else np.zeros(0, np.int64)})
    out = out[out["known_at"] <= now].reset_index(drop=True)
    if len(out):
        assert (out["known_at"] >= out["last_end"]).all(), "a frame value known before its last hourly bar closed"
    out["hour_ny"] = pd.DatetimeIndex(out["start"]).tz_convert(NY).hour.to_numpy() if len(out) else np.zeros(0, int)
    out.attrs["frame"] = frame
    return out


def all_frames(h1, now):
    return {f: build(h1, f, now) for f in FRAMES}
