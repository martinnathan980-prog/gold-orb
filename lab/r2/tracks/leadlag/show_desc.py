import sys, os, glob
import numpy as np, pandas as pd
OUT = "/home/user/gold-orb/lab/results/r2/leadlag/descriptive"
pd.set_option("display.width", 250); pd.set_option("display.max_columns", 40); pd.set_option("display.max_rows", 500)
files = sys.argv[1:] or sorted(glob.glob(os.path.join(OUT, "*_to_*.csv")))
for f in files:
    if not f.endswith(".csv"):
        f = os.path.join(OUT, f + ".csv")
    r = pd.read_csv(f)
    L, F = r.L.iloc[0], r.F.iloc[0]
    print(f"================ {L} -> {F}")
    for (sn, pn), g in r.groupby(["sess", "pred"], sort=False):
        c1 = g["cost_1%"].mean(); c01 = g["cost_0.1%"].mean()
        print(f"--- {sn:7s} {pn:9s} | n={int(g.n.max())} | RT cost at 1% tail {c1:.2f} bp, at 0.1% tail {c01:.2f} bp")
        def piv(col):
            p = g.pivot(index="k", columns="h", values=col)
            return p
        a = piv("fwd_1%"); ta = piv("t_1%"); b = piv("fwd_0.1%"); tb = piv("t_0.1%"); sl = piv("t_slope")
        ax = g.groupby("k")["absx_1%"].first(); bx = g.groupby("k")["absx_0.1%"].first()
        gp = g.groupby("k")["gap_1%"].first(); gp2 = g.groupby("k")["gap_0.1%"].first()
        n1 = g.groupby("k")["n_1%"].first(); d1 = g.groupby("k")["days_1%"].first()
        for k in a.index:
            s1 = "  ".join(f"h{h}:{a.loc[k,h]:+.2f}(t{ta.loc[k,h]:+.1f})" for h in a.columns)
            s2 = "  ".join(f"h{h}:{b.loc[k,h]:+.2f}(t{tb.loc[k,h]:+.1f})" for h in b.columns)
            s3 = " ".join(f"{sl.loc[k,h]:+.1f}" for h in sl.columns)
            print(f"   k={k:2d} |x|1%={ax[k]:6.1f}bp gap {gp[k]:+.2f} n={n1[k]}/{d1[k]}d | tail1%: {s1}")
            print(f"         |x|.1%={bx[k]:6.1f}bp gap {gp2[k]:+.2f}            | tail.1%: {s2} | slope t: {s3}")
