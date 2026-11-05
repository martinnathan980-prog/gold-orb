"""Stage 2: rationale-driven additions (declared before running).
 - ranging-regime filter (ADX<20) on the three main fade families of stage 1
 - failed-breakout fade (Connors-Raschke Turtle Soup) canonical forms
 - multi-day return-extreme reversal (n=3 variant is EDA-driven: flagged)"""
from run import ev, n_trials
S2 = [
    (dict(family="rsi", tf="D", rsi_n=2, lo=10, hi=90, trend_n=0, exit_ma=5, max_bars=5, stop_atr=3.0, adx_max=20), "RSI2 D + ADX(D)<20 ranging filter"),
    (dict(family="bb", tf="4h", n=20, k=2.5, stop_atr=2.5, max_bars=12, target="mean", adx_max=20), "BB H4 fade + ADX(H4)<20"),
    (dict(family="sess", ref="ldn", check="11:00", k=0.75, target_frac=0.5, stop_mode="extreme", stop_buf=0.25, exit_at="16:30", adx_max=20), "London-open overextension fade + ADX(D)<20"),
    (dict(family="soup", n=20, min_age=4, mode="stop_entry", stop_buf=0.25, max_bars=3), "Turtle Soup Plus One (20d)"),
    (dict(family="soup", n=20, min_age=4, mode="close_inside", stop_buf=0.25, max_bars=3), "Turtle Soup same-day close back inside (20d)"),
    (dict(family="soup", n=10, min_age=4, mode="stop_entry", stop_buf=0.25, max_bars=3), "Turtle Soup Plus One (10d)"),
    (dict(family="ret", n=5, k=2.0, vol_n=60, hold=5, stop_atr=3.0), "5-day return z<-2/>2 reversal"),
    (dict(family="ret", n=3, k=2.0, vol_n=60, hold=3, stop_atr=3.0), "3-day return z reversal (EDA-driven)"),
]
if __name__ == "__main__":
    print("trials before:", n_trials())
    for cfg, note in S2:
        ev(cfg, stage="S2", note=note)
    print("trials after:", n_trials())
