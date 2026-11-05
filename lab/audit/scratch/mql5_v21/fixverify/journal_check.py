"""Scratch: v2.10 journal rows (Journal() lines 278-295) -> compare_journal.read_journal."""
import sys
sys.path.insert(0, "/home/user/gold-orb/lab/live")
import importlib.util
spec = importlib.util.spec_from_file_location("cj", "/home/user/gold-orb/lab/live/compare_journal.py")
cj = importlib.util.module_from_spec(spec); spec.loader.exec_module(cj)

hdr = ";".join(["time_utc", "event", "side", "price", "stop", "atr", "R", "note", "paris", "server",
                "offset_rule_h", "offset_measured_h", "replay"])
def row(t, ev, side, price, R, note, rep="0"):
    return ";".join([t, ev, str(side), f"{price:.2f}", "0.00", "10.00", f"{R:.3f}", note,
                     "2025.01.02 10:00", "2025.01.02 11:00", "2.0", "0.00", rep])
rows = [hdr,
        row("2025.01.02 09:00:00", "LEVELS", 0, 2650, 0, "until 2025.01.02 12:00"),
        row("2025.01.02 09:13:00", "ENTRY", 1, 2651, 0, "deadline 2025.01.09 13:55"),
        row("2025.01.02 15:41:00", "EXIT", 1, 2671, 1.0, "suiveur"),
        row("2025.01.03 04:00:00", "ENTRY", -1, 2600, 0, "deadline 2025.01.10 08:55"),
        row("2025.01.03 05:00:00", "GAP_RESET", -1, 0, 0, "last M1 2025.01.03 04:59"),   # no EXIT
        row("2025.01.06 08:02:00", "ENTRY", 1, 2700, 0, "deadline 2025.01.13 08:55", "1"),
        row("2025.01.06 09:30:00", "EXIT", 1, 2690, -0.5, "stop", "1"),
        row("2025.01.07 12:00:00", "ENTRY", 1, 2720, 0, "deadline 2025.01.14 12:55")]   # cut-off run
open(sys.argv[1], "w").write("\r\n".join(rows) + "\r\n")
print(cj.read_journal(sys.argv[1]).to_string())
