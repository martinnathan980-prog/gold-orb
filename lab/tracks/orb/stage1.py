"""Stage 1 screening: one canonical config per opening-range idea (pre-declared before any P&L)."""
from research import run, n_trials

BASE = dict(entry="stop", stop_mode="opp", target_R=None, exit_time="16:00", exit_tz="NY")
S1 = {
    "S1_asia_00-07ldn": dict(tz="LDN", range_start="00:00", range_end="07:00", entry_end="12:00"),
    "S2_ldn_08-0830": dict(tz="LDN", range_start="08:00", range_end="08:30", entry_end="12:00"),
    "S3_ldn_08-09": dict(tz="LDN", range_start="08:00", range_end="09:00", entry_end="12:00"),
    "S4_comex_0820-0835": dict(tz="NY", range_start="08:20", range_end="08:35", entry_end="12:00"),
    "S5_comex_0820-0850": dict(tz="NY", range_start="08:20", range_end="08:50", entry_end="12:00"),
    "S6_us_0930-0945": dict(tz="NY", range_start="09:30", range_end="09:45", entry_end="12:00"),
    "S7_zarattini_0820_5m": dict(tz="NY", range_start="08:20", range_end="08:25", entry_end="12:00",
                                 entry="first_bar", target_R=10.0),
}
if __name__ == "__main__":
    for k, v in S1.items():
        run(k, {**BASE, **v}, stage="1-screen")
    print("trials so far:", n_trials())
