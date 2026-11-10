"""Hand-check of random IS trades of the candidate against raw M1 rows (independent recomputation of the signal)."""
from common import *
from goldlab.split import cut
F = {"rule": "xlead", "leader": "us100", "pred": "lead", "sess": "uscash", "dirn": 1, "k": 1, "z": 6, "hold": 60, "stop": 2.0}
use("btcusd")
m1 = r2.load("btcusd")
t = cut(r2.run("btcusd", strategy.make_orders, F, "fp", True, m1), "is")
L = pd.read_parquet(os.path.join(LAB, "data", "fp", "us100_m1.parquet"), columns=["bc", "ac"])
L = L[L.index < pd.Timestamp("2022-01-01", tz="UTC")]
lmid = (L.bc + L.ac) / 2
rng = np.random.default_rng(7)
for i in sorted(rng.choice(len(t), 6, replace=False)):
    tr = t.iloc[i]
    et = tr.entry_time                       # BTC entry bar start
    dec = et - pd.Timedelta(minutes=1)       # decision bar label (us100 bar that just closed)
    # independent signal: us100 close[dec] / close[dec - 1min]
    c0 = lmid.get(dec); c1 = lmid.get(dec - pd.Timedelta(minutes=1))
    r = np.log(c0 / c1)
    # trailing sigma: RMS of us100 1-min log returns (consecutive-minute bars only) over the 20 days before the decision bar
    w = lmid[(lmid.index >= dec - pd.Timedelta(days=20)) & (lmid.index < dec)]
    # grid-based returns as in the strategy: return at minute m needs a bar at m and a close within 3 minutes before m-1
    full = w.reindex(pd.date_range(dec - pd.Timedelta(days=20), dec - pd.Timedelta(minutes=1), freq="1min"))
    ff = full.ffill(limit=3)
    rr = np.log(ff / ff.shift(1))[full.notna()]
    rr = rr.dropna()
    # strategy uses x[g-28800 .. g-1] where x needs hasL -> same set
    sig = float(np.sqrt((rr ** 2).mean()))
    z = r / sig
    b = m1.loc[et]
    xb_t = tr.exit_time
    ny = dec.tz_convert("America/New_York")
    exp_entry = b.ao * (1 + 0.5e-4) if tr.side > 0 else b.bo * (1 - 0.5e-4)
    print(f"trade {i}: decision bar {dec} (NY {ny.strftime('%H:%M')}) us100 {c1:.2f}->{c0:.2f} r={r*1e4:+.2f}bp sigma={sig*1e4:.2f}bp z={z:+.2f} | side {int(tr.side)} "
          f"| entry {et} px {tr.entry:.2f} (expected {exp_entry:.2f}) | stop {tr.stop:.2f} dist {abs(tr.entry-tr.stop):.1f} | exit {xb_t} px {tr.exit:.2f} reason {tr.reason} "
          f"| hold {tr.hold_min:.0f} min | pnl {tr.pnl:+.2f} R {tr.R:+.3f}")
    assert abs(z) >= 6 - 1e-6 and np.sign(z) == tr.side, "signal mismatch"
    assert abs(tr.entry - exp_entry) < 1e-6 * tr.entry, "entry mismatch"
    if tr.reason == "time":
        xb = m1.loc[xb_t]
        exp_exit = xb.bo * (1 - 0.5e-4) if tr.side > 0 else xb.ao * (1 + 0.5e-4)
        assert abs(tr.exit - exp_exit) < 1e-6 * tr.exit, "exit mismatch"
        assert tr.hold_min == 60
print("all hand-checks OK")
