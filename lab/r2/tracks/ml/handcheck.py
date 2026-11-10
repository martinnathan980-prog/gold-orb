"""Independent slow re-computation of a few candidates (features, entry, stop, exit) straight from the M1 rows,
to check the vectorised generator and the engine fills (in-sample frame only)."""
import json
import sys

sys.path.insert(0, "/home/user/gold-orb/lab/r2/tracks/ml")
from research import *  # noqa

GEN = {"stop_k": 2.0, "hold_h": 13.0}
out = []
rng = np.random.default_rng(11)
for sym in ["btcusd", "ethusd"]:
    m1 = is_frame(sym)
    c = S.candidates(m1, **GEN)
    t = r2.run(sym, S.make_orders, GEN, "fp", no_overlap=False, m1=m1).set_index("cid")
    # slow H1 bars: pandas resample of the BID columns
    h = m1[["bo", "bh", "bl", "bc"]].resample("1h", label="left", closed="left").agg({"bo": "first", "bh": "max", "bl": "min", "bc": "last"}).dropna()
    ny = h.index.tz_convert("America/New_York")
    h = h[(ny.hour >= 2) & (ny.hour <= 15) & (ny.dayofweek < 5)]
    for k in rng.choice(len(c), 6, replace=False):
        row = c.iloc[k]
        t_dec = pd.Timestamp(row["t_dec"])
        bar_start = t_dec - pd.Timedelta(hours=1)
        hist = h[h.index <= bar_start]
        cur = hist.iloc[-1]
        assert hist.index[-1] == bar_start
        prev14 = hist.iloc[-15:-1]
        A = float((hist.bh - hist.bl).iloc[-70:].mean())
        A_long = float((hist.bh - hist.bl).iloc[-280:].mean())
        up = cur.bc > prev14.bh.max()
        dn = cur.bc < prev14.bl.min()
        side = 1 if up else -1
        assert up or dn
        feats = {
            "brk": ((cur.bc - prev14.bh.max()) if up else (prev14.bl.min() - cur.bc)) / A,
            "bar": (cur.bh - cur.bl) / A,
            "body": side * (cur.bc - cur.bo) / A,
            "ret4": side * (cur.bc - hist.bc.iloc[-5]) / A,
            "ret14": side * (cur.bc - hist.bc.iloc[-15]) / A,
            "ret70": side * (cur.bc - hist.bc.iloc[-71]) / A,
            "chan": (prev14.bh.max() - prev14.bl.min()) / A,
            "vol": A / A_long,
        }
        l280 = hist.iloc[-280:]
        feats["pos"] = ((cur.bc - l280.bl.min()) if up else (l280.bh.max() - cur.bc)) / (l280.bh.max() - l280.bl.min())
        # same / opposite breakouts among the previous 14 session bars
        su = sd_ = 0
        for j in range(2, 16):
            b = hist.iloc[-j]
            pv = hist.iloc[-j - 14:-j]
            su += int(b.bc > pv.bh.max())
            sd_ += int(b.bc < pv.bl.min())
        feats["seq"] = su if up else sd_
        feats["opp"] = sd_ if up else su
        nyd = hist.index.tz_convert("America/New_York").normalize()
        today = nyd[-1]
        prev_day = hist[nyd == nyd[nyd < today].max()]
        feats["pdd"] = ((cur.bc - prev_day.bh.max()) if up else (prev_day.bl.min() - cur.bc)) / A
        feats["dret"] = side * (cur.bc - prev_day.bc.iloc[-1]) / A
        feats["hour"] = t_dec.tz_convert("America/New_York").hour
        feats["dow"] = t_dec.tz_convert("America/New_York").dayofweek
        maxdiff = max(abs(float(row[f]) - float(v)) for f, v in feats.items())
        # entry / stop / exit against the engine trade
        tr = t.loc[int(t_dec.value // 1)] if int(t_dec.value) in t.index else t.loc[pd.Timestamp(t_dec).as_unit("ns").value]
        ei = int(m1.index.searchsorted(t_dec))
        bar = m1.iloc[ei]
        slip = r2.SPEC[sym]["slip_mkt_bps"] * 1e-4
        fill = bar.ao * (1 + slip) if side > 0 else bar.bo * (1 - slip)
        stop = fill - side * 2.0 * A
        x_time = t_dec.tz_convert("America/New_York").normalize() + pd.Timedelta(hours=15, minutes=55)
        res = {"sym": sym, "t_dec": str(t_dec), "side": int(side), "feat_maxdiff": float(maxdiff), "side_ok": bool(side == row["side"]),
               "A_diff": float(abs(A - row["A"])), "entry_time_engine": str(tr.entry_time), "entry_bar": str(m1.index[ei]),
               "fill_diff": float(abs(fill - tr.entry)), "stop_diff": float(abs(stop - tr.stop)), "reason": tr.reason,
               "exit_time_engine": str(tr.exit_time), "scheduled_exit_utc": str(x_time.tz_convert("UTC")), "R": round(float(tr.R), 3)}
        # recompute the exit by hand
        seg = m1.iloc[ei:]
        xi = int(m1.index.searchsorted(x_time.tz_convert("UTC")))
        path = m1.iloc[ei:xi]
        hit = (path.bl <= stop) if side > 0 else (path.ah >= stop)
        if hit.any():
            j = int(np.argmax(hit.to_numpy()))
            b = path.iloc[j]
            sl = r2.SPEC[sym]["slip_stop_bps"] * 1e-4
            px = (stop if j == 0 else min(stop, b.bo)) * (1 - sl) if side > 0 else (stop if j == 0 else max(stop, b.ao)) * (1 + sl)
            res["hand_exit"] = "stop"
        else:
            b = m1.iloc[xi]
            px = b.bo * (1 - slip) if side > 0 else b.ao * (1 + slip)
            res["hand_exit"] = "time"
        res["hand_R"] = round(float(side * (px - fill) / (2.0 * A)), 3)
        res["R_diff"] = round(abs(res["hand_R"] - res["R"]), 4)
        out.append(res)
        print(res)
    r2.free()
json.dump(out, open(os.path.join(RES, "handcheck.json"), "w"), indent=1)
print("max feature diff", max(r["feat_maxdiff"] for r in out), "max fill diff", max(r["fill_diff"] for r in out),
      "max stop diff", max(r["stop_diff"] for r in out), "max R diff", max(r["R_diff"] for r in out))
