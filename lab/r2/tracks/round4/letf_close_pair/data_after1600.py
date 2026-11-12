"""Information for configuration (6) exit 16:05 (no rule result): share of in-sample sessions on which us100 / us30 /
us500 have a bar starting at given New York minutes from 15:55 to 18:30, by year. The frames carry no quote from
16:15 to 17:59 in any year and none after the 16:00 bar in 2016-2017, so on those days (6) exits at the last close
(declared.json R10 fallback). Writes results/r2/round4/letf_close_pair/data_after1600.json."""
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common as C  # noqa: E402

MINS = [955, 959, 960, 961, 964, 965, 966, 970, 974, 975, 990, 1020, 1079, 1080, 1110]


def main():
    cal = C.calendar()
    sess = set(cal["sessions"].date)
    out = {"what": "share of the list's sessions with a bar starting at each New York minute", "by_sym": {}}
    for s in C.SYMS:
        df = C.load_is(s, cols=("bc",))
        ny = df.index.tz_convert(C.NY)
        dates = ny.date
        keep = np.array([d in sess for d in dates])
        mod = (ny.hour * 60 + ny.minute).to_numpy()[keep]
        yrs = ny.year.to_numpy()[keep]
        dd = np.array(dates)[keep]
        res = {}
        for y in np.unique(yrs):
            n_s = int(sum(1 for d in sess if d.year == y))
            m = yrs == y
            res[int(y)] = {"sessions": n_s}
            for mm in MINS:
                res[int(y)][f"{mm // 60:02d}:{mm % 60:02d}"] = round(len(np.unique(dd[m & (mod == mm)])) / n_s, 3)
        out["by_sym"][s] = res
        del df
    both = {}
    fr = C.load_frames(syms=("us100", "us30"))
    P = C.prepare(C.build_grid(fr, cal["tdays"]))
    have = np.isfinite(P["mo"])
    rows = cal["srow"]
    yrs = cal["sessions"].year.to_numpy()
    b1605 = have[0][rows, 65] & have[1][rows, 65]
    for y in np.unique(yrs):
        m = yrs == y
        both[int(y)] = {"sessions": int(m.sum()), "us100_and_us30_bar_at_16:05": int(b1605[m].sum()),
                        "us100_and_us30_any_bar_16:05-16:59": int((have[0][rows[m], 65:].any(axis=1)
                                                                   & have[1][rows[m], 65:].any(axis=1)).sum())}
    out["us100_and_us30_by_year"] = both
    out["us100_and_us30_bar_at_16:05_share_all"] = round(float(b1605.mean()), 4)
    C.jdump(out, os.path.join(C.OUT, "data_after1600.json"))
    for y, r in both.items():
        print(y, r)
    print("share with both bars at 16:05:", out["us100_and_us30_bar_at_16:05_share_all"])


if __name__ == "__main__":
    main()
