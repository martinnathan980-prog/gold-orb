"""Power check of idea 024 from the page views alone (no price, no return): days with z >= 2 per page, and the
distinct entry days (one signal per page and entry day, before the one-position filter), in market-tradable years
(crypto from 2017-08-17, Binance's start)."""
import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
import pandas as pd
import common as M

tot = 0
for page, (files, mk) in M.PAGES.items():
    s = M.raw_views(page)
    if s is None:
        print(f"{page:16s} {mk}: NOT FETCHED"); continue
    vk = M.views_known(page)
    z = M.zscores(vk)
    days = z.index[(z >= 2).to_numpy()]
    if mk in ("btcusd", "ethusd"):
        days = days[days >= pd.Timestamp("2017-08-17")]
    ent = M.entry_time(days)
    # entries at least 3 business days apart, a rough count of what one position per market can take
    n_sep, last = 0, None
    for t in ent:
        if last is None or t >= last + pd.offsets.BDay(3):
            n_sep += 1; last = t
    tot += len(set(ent))
    print(f"{page:16s} {mk}: days {s.index.min().date()}..{s.index.max().date()} median views {s.median():.0f}; "
          f"z>=2 days {len(days)}, distinct entries {len(set(ent))}, ~non-overlapping {n_sep}")
print("total distinct entries", tot)
