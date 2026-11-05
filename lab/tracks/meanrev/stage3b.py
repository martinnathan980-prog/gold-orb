"""Stage 3b (last exploration step, declared before running): the failed-breakout fade has a
small positive GROSS edge but costs eat it (tight stops).  Structural test: wider stop (1 ATR
beyond the extreme -> cost share halves) and a longer hold (fat right tail)."""
from run import ev, n_trials
S3b = [
    (dict(family="soup", tf="D", n=5, min_age=1, mode="close_inside", stop_buf=1.0, max_bars=3), "soup D n5 age1, stop 1 ATR beyond extreme"),
    (dict(family="soup", tf="1h", n=120, min_age=12, mode="close_inside", stop_buf=1.0, max_bars=72), "soup H1 n120 age12, stop 1 ATR beyond extreme"),
    (dict(family="soup", tf="1h", n=120, min_age=12, mode="close_inside", stop_buf=0.25, max_bars=110), "soup H1 n120 age12, hold ~5 days"),
]
if __name__ == "__main__":
    print("trials before:", n_trials())
    for cfg, note in S3b:
        ev(cfg, stage="S3b", note=note)
    print("trials after:", n_trials())
