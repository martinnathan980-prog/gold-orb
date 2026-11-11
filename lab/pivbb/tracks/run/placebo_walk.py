"""M1 walk of a stop / target / forced-exit trade on mid prices (descriptive tables only)."""
import numba as nb
import numpy as np


@nb.njit(cache=True)
def walk(o, h, l, ei, xi, side, stop, tgt):
    R = np.empty(len(ei))
    for q in range(len(ei)):
        e = o[ei[q]]
        risk = side[q] * (e - stop[q])
        if risk <= 0:
            R[q] = np.nan
            continue
        r = np.nan
        for i in range(ei[q], xi[q]):
            if (side[q] == 1 and l[i] <= stop[q]) or (side[q] == -1 and h[i] >= stop[q]):
                r = -1.0
                break
            if np.isfinite(tgt[q]) and ((side[q] == 1 and h[i] >= tgt[q]) or (side[q] == -1 and l[i] <= tgt[q])):
                r = side[q] * (tgt[q] - e) / risk
                break
        if np.isnan(r):
            r = side[q] * (o[xi[q]] - e) / risk
        R[q] = r
    return R
