"""P9 (run inline once; saved): patch files vs main (unpatched) data on overlapping minutes, for
time shifts of -180..+180 min -> the patch must align at shift 0."""
import glob, numpy as np, pandas as pd
main = pd.read_parquet("data/xauusd_m1_unpatched.parquet", columns=["bc"])
mt = main.index.as_unit("ns").asi8 // 60_000_000_000
mc = main.bc.to_numpy()
files = sorted(glob.glob("../download/patch/xauusd-m1-bid-*.csv.gz"))
rng = np.random.default_rng(3)
out = []
for f in rng.choice(files, min(30, len(files)), replace=False):
    d = pd.read_csv(f)
    ft = d.timestamp.to_numpy(np.int64) // 60_000
    fc = d.close.to_numpy()
    best = None
    for sh in (-180, -120, -60, -1, 0, 1, 60, 120, 180):
        tt = ft + sh
        pos = np.clip(np.searchsorted(mt, tt), 0, len(mt) - 1)
        hit = mt[pos] == tt
        if hit.sum() < 50:
            continue
        m = np.isclose(fc[hit], mc[pos[hit]], atol=1e-3).mean()
        if best is None or m > best[1]:
            best = (sh, round(float(m), 3), int(hit.sum()))
    out.append(best)
    print(f.split("/")[-1], best)
print("shift 0 for all sampled files:", all(b[0] == 0 for b in out if b), len([b for b in out if b]))
