"""Fetch only the missing GDELT 1.0 daily aggregates into ~/explore_data/idea_002/gdelt (3 processes), reusing fetch_gdelt.one."""
import os, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch_gdelt as fg
fg.OUT = os.path.expanduser("~/explore_data/idea_002/gdelt")
from concurrent.futures import ProcessPoolExecutor
if __name__ == "__main__":
    d0 = dt.date(2013, 4, 1)
    days = [d0 + dt.timedelta(i) for i in range((fg.END - d0).days + 1)]
    todo = [d for d in days if not os.path.exists(os.path.join(fg.OUT, d.strftime("%Y%m%d") + ".json"))]
    print("todo", len(todo), flush=True)
    with ProcessPoolExecutor(3) as ex:
        for i, _ in enumerate(ex.map(fg.one, todo, chunksize=2)):
            if i % 50 == 0:
                print(i, flush=True)
    print("DONE", flush=True)
