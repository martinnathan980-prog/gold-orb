"""Stage B rules (plan_B_rules.json): B1 fix month-end reversal, B2 USD European-morning, B3 London-open break."""
import os, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C
import strategy as S

CFG = [
    ("B1_fix_me_rev", dict(family="fix", dec="16:00", look_min=60, exit="16:30", monthend_n=1, stop_atr=1.5), False),
    ("B2_usd_eu_am", dict(family="tod", start="07:00", end="12:00", dir="usd_long", stop_atr=2.0), True),
    ("B3_ldn_open_brk", dict(family="ldnbrk", range_start="00:00", range_end="07:00", entry_end="10:00", exit="16:00"), False),
]
if __name__ == "__main__":
    out = {}
    for name, p, pp in CFG:
        t0 = time.time()
        r = C.basket(name, S.make_orders, p, full=True, pass_pair=pp, save_trades=True)
        out[name] = r
        C.save(out, "stageB.json")
        print(C.short(r), f"[{time.time()-t0:.0f}s]", flush=True)
        print("   ", r["criteria"], flush=True)
        print("   ", {s: (v['n'], v['exp_R'], v['total_R']) for s, v in r['fp']['by_sym'].items()}, flush=True)
        print("    gross", {s: v['exp_R'] for s, v in r['gross']['by_sym'].items()}, "tD gross", r['gross']['t_daily'], flush=True)
