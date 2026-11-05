"""Tester-like runs of the literal EA port (exact data) against the lab, per calendar year and
for the user's protocol year 2025: first-run initialisation, deadline reference, exit rule."""
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from ea_port import compare, lab_trades, run  # noqa: E402
import goldlab as gl  # noqa: E402

m1 = gl.load_m1("xauusd", start="2012-12-01", end="2026-12-31")
print("== full history 2013-2026, EA control flow but warm start (should equal the twin)")
lab_all = lab_trades(m1, "2013-03-01", "2026-10-20")
for ref, rule in (("bucket", "ea"), ("tclose", "lab")):
    ea = run(m1, "2013-03-01", "2026-10-20", first_run="warm", deadline_ref=ref, exit_rule=rule)
    un = compare(lab_all, ea, f"2013-03..2026-10 warm, deadline_ref={ref}, exit_rule={rule}")
    if len(un):
        print(un[["entry_time", "side", "_merge", "R_lab", "R_ea"]].head(6).to_string())

print("\n== one-year tester runs (EA starts flat on Jan 1 and skips the first bucket) vs lab with history")
rows = []
for y in range(2014, 2026):
    s, e = f"{y}-01-01", f"{y+1}-01-01"
    lab = lab_trades(m1, s, e)
    ea = run(m1, s, e, first_run="ea")
    un = compare(lab, ea, f"{y}: EA first-run as coded")
    if len(un):
        print(un[["entry_time", "side", "_merge", "R_lab", "R_ea"]].to_string())
    ea_w = run(m1, s, e, first_run="warm")
    unw = compare(lab, ea_w, f"{y}: EA with 21-day warm replay")
    if len(unw):
        print(unw[["entry_time", "side", "_merge", "R_lab", "R_ea"]].to_string())
    lab_flat = lab_trades(m1, s, e, flat_from=ea.entry_time.min() - pd.Timedelta(hours=4) if len(ea) else s)
    compare(lab_flat, ea, f"{y}: lab started flat at the EA start (checker fix)")
