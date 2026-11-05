"""Stage 3a: does the failed-breakout (close back inside prior n-bar range) fade generalise to
shorter lookbacks / lower timeframes (needed for >=25 trades/yr)?  Hold ~3 days everywhere."""
from run import ev, n_trials
S3a = [
    (dict(family="soup", tf="D", n=10, min_age=2, mode="close_inside", stop_buf=0.25, max_bars=3), "soup close-inside D n10 age2"),
    (dict(family="soup", tf="D", n=5, min_age=1, mode="close_inside", stop_buf=0.25, max_bars=3), "soup close-inside D n5 age1"),
    (dict(family="soup", tf="4h", n=30, min_age=4, mode="close_inside", stop_buf=0.25, max_bars=18), "soup close-inside H4 n30 age4 (5d range)"),
    (dict(family="soup", tf="4h", n=60, min_age=6, mode="close_inside", stop_buf=0.25, max_bars=18), "soup close-inside H4 n60 age6 (10d range)"),
    (dict(family="soup", tf="1h", n=120, min_age=12, mode="close_inside", stop_buf=0.25, max_bars=72), "soup close-inside H1 n120 age12 (5d range)"),
]
if __name__ == "__main__":
    print("trials before:", n_trials())
    for cfg, note in S3a:
        ev(cfg, stage="S3a", note=note)
    print("trials after:", n_trials())
