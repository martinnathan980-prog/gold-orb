"""No-future test of the context sheets (both versions: first one and scale-free one): for a random sample of
cases, the sheet built from the full frame must be identical to the sheet built from a frame that stops at the decision (the entry bar itself and
everything after it are destroyed; the backdrop market is cut at the same instant).

    python3 llm/test_no_future.py [cases per sleeve, default 25]
"""
import os
import sys

import numpy as np
import pandas as pd

LAB = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, LAB)
from goldlab import r2  # noqa: E402
from llm.context import Market  # noqa: E402
from llm.experiment import SLEEVES, TRADES  # noqa: E402

BACK = 520_000          # bars kept before the decision (more than the 260 trading days the sheet can read)


def main(per_sleeve=25):
    ref_m1 = r2.load("us100")
    ref = Market("us100", ref_m1)
    bad = n = 0
    for name, sym in SLEEVES:
        m1 = ref_m1 if sym == "us100" else r2.load(sym)
        mk = ref if sym == "us100" else Market(sym, m1)
        t = pd.read_parquet(os.path.join(TRADES, f"{name}__{sym}.parquet")).sample(per_sleeve, random_state=3)
        for r in t.itertuples(index=False):
            i = int(m1.index.searchsorted(r.entry_time))
            full = mk.sheet(i, r.side, r.entry, r.stop, ref=ref)
            blind = mk.sheet_blind(i, r.side, r.entry, r.stop, ref=ref)
            cut = m1.iloc[max(0, i - BACK): i + 1].copy()
            cut.iloc[-1] = np.nan                                    # the entry bar: its prices must never be read
            j = int(ref_m1.index.searchsorted(r.entry_time))
            rcut = ref_m1.iloc[max(0, j - BACK): j]                  # backdrop: bars that started before the decision
            mk_cut, ref_cut = Market(sym, cut), Market("us100", rcut)
            trunc = mk_cut.sheet(len(cut) - 1, r.side, r.entry, r.stop, ref=ref_cut)
            trunc_blind = mk_cut.sheet_blind(len(cut) - 1, r.side, r.entry, r.stop, ref=ref_cut)
            n += 1
            if (full is None) != (trunc is None) or (full is not None and full[0] != trunc[0]) or blind != trunc_blind:
                bad += 1
                print("DIFFERENT:", name, sym, r.entry_time)
        if sym != "us100":
            r2.free(sym)
        print(f"{name} {sym}: checked", flush=True)
    print(f"{n} sheets compared, {bad} differ ->", "FAIL" if bad else "OK: no sheet reads the future")
    return bad


if __name__ == "__main__":
    sys.exit(1 if main(int(sys.argv[1]) if len(sys.argv) > 1 else 25) else 0)
