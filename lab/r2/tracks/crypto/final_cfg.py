"""The two rules carried to the finalist decision (weekday-only form) and their all-days ancestors."""
FINAL = {
    "brk72_24h_wd": {"family": "brk", "n": 72, "stop_atr": 3.0, "hold_h": 24, "dow": "weekday"},
    "sess_8_8_13_wd": {"family": "sess", "dec_h": 8, "look_h": 8, "stop_atr": 3.0, "hold_h": 13, "dow": "weekday"},
}
ALLDAYS = {
    "brk72_24h": {"family": "brk", "n": 72, "stop_atr": 3.0, "hold_h": 24},
    "sess_8_8_13": {"family": "sess", "dec_h": 8, "look_h": 8, "stop_atr": 3.0, "hold_h": 13},
}
SYMS = ("btcusd", "ethusd")
