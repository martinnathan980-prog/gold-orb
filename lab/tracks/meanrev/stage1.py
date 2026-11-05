"""Stage 1: screen -- one canonical (literature-default) config per family, declared before running."""
from run import ev, n_trials
S1 = [
    # D1 Connors RSI(2) with 200-day trend filter, exit on SMA5 cross, 5-day time stop, 3 ATR disaster stop
    (dict(family="rsi", tf="D", rsi_n=2, lo=10, hi=90, trend_n=200, exit_ma=5, max_bars=5, stop_atr=3.0), "Connors RSI2 D canonical"),
    (dict(family="rsi", tf="D", rsi_n=2, lo=10, hi=90, trend_n=0, exit_ma=5, max_bars=5, stop_atr=3.0), "RSI2 D no trend filter"),
    # D1 Internal Bar Strength, 1-day hold
    (dict(family="ibs", lo=0.2, hi=0.8, hold=1, stop_atr=2.5, trend_n=0), "IBS D canonical"),
    (dict(family="ibs", lo=0.2, hi=0.8, hold=1, stop_atr=2.5, trend_n=200), "IBS D + SMA200 filter"),
    # D1 Bollinger fade, target = SMA20
    (dict(family="bb", tf="D", n=20, k=2.0, stop_atr=3.0, max_bars=5, target="mean"), "BB(20,2) D fade"),
    # H4
    (dict(family="rsi", tf="4h", rsi_n=2, lo=10, hi=90, trend_n=200, exit_ma=5, max_bars=30, stop_atr=3.0), "RSI2 H4 + SMA200"),
    (dict(family="rsi", tf="4h", rsi_n=2, lo=10, hi=90, trend_n=0, exit_ma=5, max_bars=30, stop_atr=3.0), "RSI2 H4 no filter"),
    (dict(family="bb", tf="4h", n=20, k=2.5, stop_atr=2.5, max_bars=12, target="mean"), "BB(20,2.5) H4 fade"),
    # H1
    (dict(family="rsi", tf="1h", rsi_n=2, lo=5, hi=95, trend_n=200, exit_ma=5, max_bars=24, stop_atr=3.0), "RSI2 H1 5/95 + SMA200"),
    (dict(family="bb", tf="1h", n=20, k=2.5, stop_atr=2.5, max_bars=24, target="mean"), "BB(20,2.5) H1 fade"),
    # intraday overextension fades (ATR = prior-day D ATR14)
    (dict(family="sess", ref="day", check="11:00", k=1.0, target_frac=0.5, stop_mode="extreme", stop_buf=0.25, exit_at="16:30"), "fade day-open overextension at 11:00 NY"),
    (dict(family="sess", ref="ldn", check="11:00", k=0.75, target_frac=0.5, stop_mode="extreme", stop_buf=0.25, exit_at="16:30"), "fade London-open overextension at 11:00 NY"),
    (dict(family="sess", ref="day", check="03:00", k=0.75, target_frac=0.5, stop_mode="extreme", stop_buf=0.25, exit_at="11:00"), "fade Asian overextension at 03:00 NY (London open)"),
    # weekend gap
    (dict(family="gap", g=0.1, delay_min=30, stop_atr=1.0, hold_h=16.0), "weekend gap fade"),
]
if __name__ == "__main__":
    print("trials before:", n_trials())
    for cfg, note in S1:
        ev(cfg, stage="S1", note=note)
    print("trials after:", n_trials())
