"""Hand check of night_fade (PROTOCOL_V3 Addendum L) from the RAW quotes (data/raw_r6/*.csv.gz), IN SAMPLE ONLY (L33).

The first main order of 2013, 2015, 2017, 2019 and 2021 (the earliest entry bar of the main configuration's orders in that
UTC year over the twelve crosses, ties in basket order; it is always a trade: every earlier trade of its cross exits by
21:30 New York of an earlier evening) is recomputed with plain code that uses neither common.py's frames, calendar, bars,
bands nor the lab simulator:
  - raw minutes read with Python's csv module, rows with timestamp >= 2022-01-01 skipped inside the read loop;
  - bid and ask joined on the minute; flat bid minutes (open = high = low = close = previous joined bid close) and
    minutes with zero volume on both sides dropped; crossed minutes dropped; minutes outside Sunday 17:00 - Friday 17:00
    New York dropped (zoneinfo); commission folded in: h = 0.5 x c x 1e-4 x mid close, bid - h, ask + h;
  - calendar from the `holidays` package's NYSE calendar (an independent source; the special closure 2018-12-05 is a
    normal day) plus the 24 December - 1 January rule; warm-up = distinct UTC hours with a minute, ended by 17:15 New York;
  - M5 buckets = timestamp // 300 s, close = mid of the bucket's last minute, the 20 existing buckets ending at the signal
    bucket, plain sequential sums for the mean and the population standard deviation, the 120-minute span rule;
  - entry = first minute at or after the decision time (at most 5 minutes late), the refused-target check, the fill at
    ask open x (1 + 0.1 bp) or bid open x (1 - 0.1 bp); stop = fill -/+ 2 x the mean (mid high - mid low) of the last 480
    completed UTC hours; target = the middle band; the 21:00 New York exit minute (30-minute gap rule) after the entry.
For every cross the evenings of the year are scanned in order, up to the engine's evening, so the 'first order of the
year' is itself recomputed by hand.

    python3 -I handcheck.py entry   # entry side (allowed before the run): results/r2/round6/night_fade/handcheck_entry.json
    python3 -I handcheck.py exit    # exit side, AFTER the declared run: handcheck_exit.json (refuses without the run)
"""
import csv
import datetime as dt
import gzip
import math
import os
import sys
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402  (used for the engine's orders, the output folder and the commission table only)

import holidays  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

NYZ = ZoneInfo("America/New_York")
UTC = dt.timezone.utc
CUT_MS = 1640995200000                                   # 2022-01-01 00:00 UTC
MIN_MS, H_MS, B5_MS = 60_000, 3_600_000, 300_000
YEARS_CHECKED = (2013, 2015, 2017, 2019, 2021)
NYSE = holidays.financial_holidays("NYSE", years=range(2012, 2023))
SLIP_MKT, SLIP_STOP = 0.1e-4, 0.3e-4


def raw_rows(cross, side, year):
    """(timestamp ms, open, high, low, close, volume) of one raw file; rows >= 2022-01-01 skipped in the read loop."""
    p = os.path.join(C.RAW6, f"{cross}-m1-{side}-{year}.csv.gz")
    out = {}
    with gzip.open(p, "rt", newline="") as f:
        rd = csv.reader(f)
        head = next(rd)
        assert head == ["timestamp", "open", "high", "low", "close", "volume"], head
        for r in rd:
            ts = int(r[0])
            if ts >= CUT_MS:
                continue
            if ts not in out:                              # first occurrence kept
                out[ts] = (float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[5]))
    return out


def ny_time(ms):
    return dt.datetime.fromtimestamp(ms / 1000, UTC).astimezone(NYZ)


def ms_of(date, hh, mm):
    return int(dt.datetime(date.year, date.month, date.day, hh, mm, tzinfo=NYZ).astimezone(UTC).timestamp()) * 1000


def show(ms):
    u = dt.datetime.fromtimestamp(ms / 1000, UTC)
    return {"utc": u.strftime("%Y-%m-%d %H:%M"), "new_york": u.astimezone(NYZ).strftime("%Y-%m-%d %H:%M %Z")}


class RawCross:
    """The minutes of one cross from the raw files of the given years, built by hand."""

    def __init__(self, cross, years):
        self.cross = cross
        bid, ask = {}, {}
        for y in years:
            b, a = raw_rows(cross, "bid", y), raw_rows(cross, "ask", y)
            for k, v in b.items():
                bid.setdefault(k, v)
            for k, v in a.items():
                ask.setdefault(k, v)
        keys = sorted(set(bid) & set(ask))
        c = C.COMM_BP[cross]
        ts, bo, bh, bl, bc, ao, ah, al, ac = ([] for _ in range(9))
        prev_bc = None
        self.dropped = {"flat_or_zero_volume": 0, "crossed": 0, "weekday": 0}
        for k in keys:
            b, a = bid[k], ask[k]
            flat = (b[0] == b[1] == b[2] == b[3]) and prev_bc is not None and b[3] == prev_bc
            prev_bc = b[3]                                   # the previous JOINED minute (before any drop)
            if flat or (b[4] <= 0 and a[4] <= 0):
                self.dropped["flat_or_zero_volume"] += 1
                continue
            if a[3] < b[3] or a[1] < b[1] or a[2] < b[2]:
                self.dropped["crossed"] += 1
                continue
            if (ny_time(k) + dt.timedelta(hours=7)).weekday() >= 5:
                self.dropped["weekday"] += 1
                continue
            h = 0.5 * c * 1e-4 * ((b[3] + a[3]) / 2)
            ts.append(k)
            bo.append(b[0] - h); bh.append(b[1] - h); bl.append(b[2] - h); bc.append(b[3] - h)  # noqa: E702
            ao.append(a[0] + h); ah.append(a[1] + h); al.append(a[2] + h); ac.append(a[3] + h)  # noqa: E702
        self.ts = np.array(ts, np.int64)
        self.bo, self.bh, self.bl, self.bc = bo, bh, bl, bc
        self.ao, self.ah, self.al, self.ac = ao, ah, al, ac
        self.raw_bid, self.raw_ask = bid, ask
        # M5 buckets: id -> index of the bucket's last minute
        last = {}
        for i, k in enumerate(ts):
            last[k // B5_MS] = i
        self.b_ids = sorted(last)
        self.b_last = [last[b] for b in self.b_ids]
        self.b_pos = {b: j for j, b in enumerate(self.b_ids)}
        # UTC hours: id -> (max bh, max ah, min bl, min al)
        hrs = {}
        for i, k in enumerate(ts):
            hid = k // H_MS
            if hid not in hrs:
                hrs[hid] = [bh[i], ah[i], bl[i], al[i]]
            else:
                x = hrs[hid]
                x[0] = max(x[0], bh[i]); x[1] = max(x[1], ah[i]); x[2] = min(x[2], bl[i]); x[3] = min(x[3], al[i])  # noqa: E702
        self.h_ids = sorted(hrs)
        self.h_rng = [((hrs[h][0] + hrs[h][1]) / 2) - ((hrs[h][2] + hrs[h][3]) / 2) for h in self.h_ids]

    def mid_close(self, i):
        return (self.bc[i] + self.ac[i]) / 2

    def first_at_or_after(self, t):
        i = int(np.searchsorted(self.ts, t, side="left"))
        return i if i < len(self.ts) else None

    def completed_hours(self, t):
        """Indices (into h_ids) of the UTC hours ended by t."""
        return [j for j, h in enumerate(self.h_ids) if (h + 1) * H_MS <= t]

    def decision(self, E, t, k_band=2.0, mult=2.0, n_h1=480, span_min=120):
        """Every entry-side quantity of the decision at t (ms UTC) on evening E, by hand."""
        r = {"decision": show(t), "decision_ms": int(t)}
        b = (t - B5_MS) // B5_MS
        if b not in self.b_pos:
            r["status"] = "no_signal_bar"
            return r
        j = self.b_pos[b]
        if j < 19:
            r["status"] = "band_not_usable"
            return r
        win = self.b_ids[j - 19:j + 1]
        if win[0] * B5_MS < (b * B5_MS + B5_MS) - span_min * MIN_MS:
            r["status"] = "band_not_usable"
            return r
        xs = [self.mid_close(self.b_last[self.b_pos[q]]) for q in win]
        s = 0.0
        for x in xs:
            s += x
        mu = s / 20
        v = 0.0
        for x in xs:
            d = x - mu
            v += d * d
        sd = math.sqrt(v / 20)
        close = xs[-1]
        il = self.b_last[j]
        C_ = self.ac[il] - self.bc[il]
        side = 1 if close < mu - k_band * sd else (-1 if close > mu + k_band * sd else 0)
        D = abs(close - mu)
        r.update({"signal_bucket_last_minute": show(int(self.ts[il])), "mu": mu, "sigma": sd, "close_mid": close,
                  "side": side, "D": D, "C": C_, "D_over_C": D / C_ if C_ > 0 else None})
        if side == 0:
            r["status"] = "no_band_crossing"
            return r
        if not D >= mult * C_:
            r["status"] = "cost_filter"
            return r
        ie = self.first_at_or_after(t)
        if ie is None or int(self.ts[ie]) - t > 5 * MIN_MS:
            r["status"] = "entry_late_over_5min"
            return r
        if (side > 0 and self.ao[ie] >= mu) or (side < 0 and self.bo[ie] <= mu):
            r["status"] = "open_already_at_target"
            return r
        hs = self.completed_hours(t)
        assert len(hs) >= n_h1
        w = [self.h_rng[q] for q in hs[-n_h1:]]
        s = 0.0
        for x in w:
            s += x
        mean_rng = s / n_h1
        fill = self.ao[ie] * (1 + SLIP_MKT) if side > 0 else self.bo[ie] * (1 - SLIP_MKT)
        stop = fill - side * 2.0 * mean_rng
        t21 = ms_of(E, 21, 0)
        ix = self.first_at_or_after(t21)
        if ix is None or int(self.ts[ix]) - t21 > 30 * MIN_MS:
            ix = (ix if ix is not None else len(self.ts)) - 1
        if not ix > ie:
            r["status"] = "exit_bar_not_after_entry_bar"
            return r
        r.update({"status": "order", "entry_bar": show(int(self.ts[ie])), "entry_ms": int(self.ts[ie]),
                  "entry_delay_min": (int(self.ts[ie]) - t) / MIN_MS,
                  "ask_open_base": self.ao[ie], "bid_open_base": self.bo[ie],
                  "raw_ask_open": self.raw_ask[int(self.ts[ie])][0], "raw_bid_open": self.raw_bid[int(self.ts[ie])][0],
                  "h1_window_first": show(self.h_ids[hs[-n_h1]] * H_MS), "h1_window_last": show(self.h_ids[hs[-1]] * H_MS),
                  "h1_mean_range": mean_rng, "stop_distance": 2.0 * mean_rng, "fill": fill, "stop": stop, "target": mu,
                  "stop_distance_pips": 2.0 * mean_rng / 1e-4, "target_distance_pips": abs(mu - fill) / 1e-4,
                  "exit21_bar": show(int(self.ts[ix])), "exit21_i_hand": ix, "entry_i_hand": ie})
        return r


def calendar_ok(E):
    """Independent calendar: Monday-Thursday, not 24 December - 1 January, E and E+1 not NYSE full holidays."""
    if E.weekday() > 3:
        return False
    if (E.month == 12 and E.day >= 24) or (E.month == 1 and E.day == 1):
        return False
    hol = lambda d: d in NYSE and d != dt.date(2018, 12, 5)  # noqa: E731
    return not (hol(E) or hol(E + dt.timedelta(days=1)))


def hand_first_order(rc, year, until):
    """First order of the year on this cross by hand, scanning evenings of `year` up to the date `until`."""
    d = dt.date(year, 1, 1)
    scanned = 0
    while d <= until:
        if calendar_ok(d) and len(rc.completed_hours(ms_of(d, 17, 15))) >= 480:
            scanned += 1
            for k in range(33):
                t = ms_of(d, 17, 15) + k * B5_MS
                r = rc.decision(d, t)
                if r["status"] == "order":
                    r["evening"] = str(d)
                    r["k"] = k
                    return r, scanned
        d += dt.timedelta(days=1)
    return None, scanned


def engine_first_orders():
    """The engine's first main order of each checked year (common.make_orders on the in-sample base frames)."""
    p = C.CONFIG["main"]["params"]
    rows = []
    for c in C.CROSSES:
        bk = C.Book(C.load_base(c), c)
        o, _ = C.make_orders(bk, p)
        o = o.copy()
        o["entry_time"] = pd.to_datetime(bk.ns[o.entry_i.to_numpy()], unit="ns", utc=True)
        o["year"] = o.entry_time.dt.year
        o["fill"] = np.where(o.side > 0, bk.ao[o.entry_i.to_numpy()] * (1 + 0.1 * 1e-4),
                             bk.bo[o.entry_i.to_numpy()] * (1 - 0.1 * 1e-4))
        o["stop_level"] = o.fill - o.side * o.stop_dist
        o["basket_pos"] = C.CROSSES.index(c)
        for y in YEARS_CHECKED:
            s = o[o.year == y]
            if len(s):
                rows.append(s.iloc[0])
        del bk
    df = pd.DataFrame(rows).sort_values(["year", "entry_time", "basket_pos"], kind="stable")
    return {int(y): g.iloc[0] for y, g in df.groupby("year")}, df


def entry_main():
    first, cand = engine_first_orders()
    rows, worst = [], 0.0
    for y in YEARS_CHECKED:
        e = first[y]
        until = pd.Timestamp(e.evening).date()
        years = [y] if y == 2013 else [y - 1, y]
        hand = {}
        for c in C.CROSSES:
            rc = RawCross(c, years)
            r, scanned = hand_first_order(rc, y, until)
            hand[c] = (r, scanned, dict(rc.dropped))
            del rc                                              # one cross's raw minutes in memory at a time
        found = [(r["entry_ms"], C.CROSSES.index(c), c) for c, (r, _, _) in hand.items() if r is not None]
        assert found, f"no hand order in {y} up to {until}"
        _, _, hc = min(found)
        h, scanned, dropped = hand[hc]
        eng = {"cross": e.cross, "evening": str(pd.Timestamp(e.evening).date()), "k": int(e.k_dec),
               "decision_utc": str(e.dec_utc), "side": int(e.side), "mu": float(e.mu), "sigma": float(e.sigma),
               "D": float(e.D), "C": float(e.C), "entry_bar_utc": str(e.entry_time), "fill": float(e.fill),
               "stop_distance": float(e.stop_dist), "stop": float(e.stop_level), "target": float(e.target_px),
               "h1_mean_range": float(e.h1_mean_range)}
        diffs = {k: abs(eng[k2] - h[k1]) for k, k1, k2 in (("mu", "mu", "mu"), ("sigma", "sigma", "sigma"), ("D", "D", "D"),
                                                         ("C", "C", "C"), ("fill", "fill", "fill"),
                                                         ("stop_distance", "stop_distance", "stop_distance"),
                                                         ("stop", "stop", "stop"), ("target", "target", "target"))}
        same_entry = pd.Timestamp(h["entry_ms"], unit="ms", tz="UTC") == pd.Timestamp(e.entry_time)
        ok = (hc == e.cross and h["evening"] == eng["evening"] and h["k"] == eng["k"] and h["side"] == eng["side"]
              and same_entry and all(v <= 1e-12 for v in diffs.values()))
        worst = max(worst, max(diffs.values()))
        rows.append({"year": y, "cross": hc, "evenings_scanned_on_this_cross": scanned,
                     "calendar_ok_independent": calendar_ok(pd.Timestamp(e.evening).date()),
                     "raw_minutes_dropped_by_hand": dropped, "hand": h, "engine": eng,
                     "abs_diff": diffs, "exactly_equal": {k: v == 0.0 for k, v in diffs.items()},
                     "hand_first_orders_by_cross": {c: (None if r is None else {"evening": r["evening"], "k": r["k"],
                                                                               "entry": r["entry_bar"]["utc"]})
                                                    for c, (r, _, _) in hand.items()},
                     "match": bool(ok)})
        print(y, hc, h["evening"], h["entry_bar"], "side", h["side"], "match", ok, "max diff", max(diffs.values()), flush=True)
    out = {"what": "entry side (signal, mu, sigma, D, C, entry bar, fill, stop and target levels) of the first main order "
                   "of 2013, 2015, 2017, 2019 and 2021, recomputed from the raw csv.gz quotes; exits are checked after the run",
           "n_checked": len(rows), "all_match": all(r["match"] for r in rows), "max_abs_diff_price": worst,
           "engine_candidates_by_cross": int(len(cand)), "rows": rows, "code_sha256": C.code_hashes()}
    C.jdump(out, os.path.join(C.OUT, "handcheck_entry.json"))
    return out


def hand_exit(rc, h, side):
    """Exit of a trade by a plain bar-by-bar scan from the entry minute (resting target, stop first, gaps, 21:00 exit)."""
    ie, ix = h["entry_i_hand"], h["exit21_i_hand"]
    fill, stop, tgt = h["fill"], h["stop"], h["target"]
    for i in range(ie, ix):
        first = i == ie
        if side > 0:
            hit_s, hit_t = rc.bl[i] <= stop, rc.bh[i] >= tgt
            if hit_s:
                px = stop if first else min(stop, rc.bo[i])
                return "stop", int(rc.ts[i]) + MIN_MS, px * (1 - SLIP_STOP)
            if hit_t:
                return "target", int(rc.ts[i]) + MIN_MS, tgt if first else max(tgt, rc.bo[i])
        else:
            hit_s, hit_t = rc.ah[i] >= stop, rc.al[i] <= tgt
            if hit_s:
                px = stop if first else max(stop, rc.ao[i])
                return "stop", int(rc.ts[i]) + MIN_MS, px * (1 + SLIP_STOP)
            if hit_t:
                return "target", int(rc.ts[i]) + MIN_MS, tgt if first else min(tgt, rc.ao[i])
    px = rc.bo[ix] * (1 - SLIP_MKT) if side > 0 else rc.ao[ix] * (1 + SLIP_MKT)
    return "time", int(rc.ts[ix]), px


def exit_main():
    decl, sha = C.declared()
    hce = __import__("json").load(open(os.path.join(C.OUT, "handcheck_entry.json"), encoding="utf-8"))
    t = pd.read_parquet(os.path.join(C.OUT, "trades_01_main_base.parquet"))
    rows = []
    for r in hce["rows"]:
        y, c, h = r["year"], r["cross"], r["hand"]
        rc = RawCross(c, [y] if y == 2013 else [y - 1, y])
        hh = rc.decision(dt.date.fromisoformat(h["evening"]), h["decision_ms"])
        assert hh["status"] == "order" and hh["entry_ms"] == h["entry_ms"]
        hh.update({"evening": h["evening"]})
        reason, x_ms, x_px = hand_exit(rc, hh, hh["side"])
        R = hh["side"] * (x_px - hh["fill"]) / abs(hh["fill"] - hh["stop"])
        e = t[(t.cross == c) & (t.entry_time == pd.Timestamp(hh["entry_ms"], unit="ms", tz="UTC"))]
        assert len(e) == 1, (y, c, len(e))
        e = e.iloc[0]
        ok = (e.reason == reason and pd.Timestamp(e.exit_time) == pd.Timestamp(x_ms, unit="ms", tz="UTC")
              and abs(float(e.exit) - x_px) <= 1e-12 and abs(float(e.R) - R) <= 1e-9)
        rows.append({"year": y, "cross": c, "hand": {"reason": reason, "exit_time": show(x_ms), "exit_price": x_px, "R": R},
                     "engine": {"reason": e.reason, "exit_time": str(e.exit_time), "exit_price": float(e.exit), "R": float(e.R)},
                     "match": bool(ok)})
    out = {"declared_sha256": sha, "what": "exit side of the five hand-checked main trades, from the raw quotes",
           "n_checked": len(rows), "all_match": all(r["match"] for r in rows), "rows": rows}
    C.jdump(out, os.path.join(C.OUT, "handcheck_exit.json"))
    return out


if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else ""
    if what == "entry":
        o = entry_main()
        print("checked", o["n_checked"], "all match", o["all_match"], "max |diff|", o["max_abs_diff_price"])
    elif what == "exit":
        o = exit_main()
        print("checked", o["n_checked"], "all match", o["all_match"])
    else:
        raise SystemExit("usage: handcheck.py entry|exit")
