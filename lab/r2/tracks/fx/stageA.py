"""Stage A: frozen transfers of the lab's validated families to the 8 currency pairs (plan_A_frozen_transfers.json).
Quick runs (full=False) on IS-only frames; one trial per pair.  Output: results/r2/fx/stageA.json"""
import importlib.util
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

LAB = C.LAB


def _mod(path, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(LAB, path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[name] = m
    spec.loader.exec_module(m)
    return m


def transfers():
    tr = _mod("tracks/trend/strategy.py", "strategy_trend")
    orb = _mod("tracks/orb/strategy.py", "strategy_orb")
    cr = _mod("r2/tracks/crypto/strategy.py", "r2_crypto_strategy")
    from pivbb.tracks.run import strategy as pv
    import pandas as pd

    def crypto_fp_hours(m1, **params):  # identical to r2/recalc.py::_crypto_fp_hours
        o = cr.make_orders(m1, **params)
        if len(o):
            o = o.copy()
            o["exit_i"] = C.gl.exit_index(m1, pd.DatetimeIndex(o["sched_exit"]))
            o = o[o.exit_i > o.entry_i].reset_index(drop=True)
        return o

    return [
        ("A1_donch4h_stop", tr.make_orders, dict(tr.FINALISTS["donch4h_stop"])),
        ("A2_orb_asia_2d_buf10", orb.make_orders, dict(orb.FINALISTS["orb_asia_2d_buf10"])),
        ("A3_brk72_24h_wd", crypto_fp_hours, dict(cr.FINALISTS["brk72_24h_wd"]["params"])),
        ("A4_outer_close_ride", pv.make_orders, dict(pv.FINALISTS["outer_close_ride"])),
    ]


if __name__ == "__main__":
    out = {}
    for name, mo, params in transfers():
        t0 = time.time()
        res = C.basket(name, mo, params, full=True, save_trades=False)
        out[name] = res
        C.save(out, "stageA.json")
        print(C.short(res), f"[{time.time() - t0:.0f}s]", flush=True)
        print("   ", res["criteria"], flush=True)
        print("   ", {s: (v['n'], v['exp_R'], v['total_R']) for s, v in res['fp']['by_sym'].items()}, flush=True)
