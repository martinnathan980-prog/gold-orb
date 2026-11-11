import sys, json, time
sys.path.insert(0, "/home/user/gold-orb/lab")
from goldlab import r2
from pivbb.tracks.run import strategy as S
OUT = "/home/user/gold-orb/lab/results/pivbb/run"
CAND = {"r2s2_touch_run": dict(levels=["D_R2", "D_S2"], entry="touch"),
        "outer_close_ride": dict(levels=["D_R2", "D_S2", "D_R3", "D_S3"], hours=[2, 12], target=None)}
res = {}
for name, prm in CAND.items():
    t0 = time.time()
    res[name] = r2.null_test("xauusd", S.make_orders, prm, n_seeds=200, mode="day")
    print(name, res[name], round(time.time() - t0), "s", flush=True)
    json.dump(res, open(OUT + "/null_test.json", "w"), indent=1)
