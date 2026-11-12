"""Lens `cluster`: the portfolio engine (ten sleeves, one account) and its guards. IN SAMPLE ONLY.

THE ACCOUNT (reference): every trade of the ten sleeves' own one-position chains (re-simulated in repro.py) is
offered to the account in entry order (ties in the same minute: ASCII order of "<name>_<sym>"). It is taken at one
base stake unless (i) the broker would refuse its stop (closer than 3 spreads of its fill bar), or (ii) 6 positions
are already open, or 2 on the same market (account.py LIMITS). A position is open for a new entry until its exit
time is STRICTLY before the entry time. No compounding: results are in R (multiples of the base stake).

A GUARD returns a stake multiplier g >= 0 for each trade from the state at its entry time; g = 0 means "not taken".
It is applied BEFORE the position caps (as the stake rule in account.py): a trade with g > 0 then still needs a
free slot. A trade not taken leaves its sleeve's own chain unchanged: the sleeve keeps following it on paper
(the official chains are run with no_overlap=True and never see the account).

STATE AT AN ENTRY TIME t (only what is known at t)
    paper results : every trade of the sleeves (taken or not) whose exit time is < t, in exit order
    real results  : the trades TAKEN by the account whose exit time is < t (stake x R)
    open positions: the trades taken by the account, entered before (or earlier in the same-minute order) and not
                    exited before t
Day / week = FP server day / week (New York + 7 h; weeks start Monday), of the exit time for results and of the
entry time for the trade being decided.

GUARD CODES (p1, p2 = parameters)
    0  reference                       g = 1
    1  same market, same side          g = p1 if a position of the same market and the same side is open, else 1
       (p2 = 0)  / same family (us100, gold, crypto), same side (p2 = 1) / same market, either side (p2 = 2)
    2  market day lock                 g = 0 if at least p1 TAKEN trades of this market have closed with R < 0
                                       earlier in this server day, else 1
    3  sleeve pause                    g = 0 if the last p1 PAPER trades of this sleeve closed before t are all
                                       losses (R < 0), else 1 (the pause ends with the first paper winner)
    4  sleeve on/off by trailing       g = 0 if the sleeve's PAPER trades closed in [t - p1 days, t) sum to <= 0
                                       (and there is at least one), else 1
    5  rank weights by trailing        trailing PAPER mean R per trade of each sleeve over [t - p1 days, t); the
                                       sleeves with at least p2 such trades are ranked (average ranks for ties);
                                       g = 0.5 + rank / (n_ranked - 1)  (0.5 .. 1.5, mean 1 over the ranked
                                       sleeves); g = 1 if this sleeve is not ranked or fewer than 2 are
    6  rank weights by expanding mean  same as 5 with every PAPER trade closed before t (no window): a static
                                       tilt, the control of code 5
    7  daily loss lock                 g = 0 if the REAL result booked in this server day before t is <= -p1
    8  weekly loss lock                g = 0 if the REAL result booked in this server week before t is <= -p1
    9  portfolio pause                 g = 0 if the last p1 PAPER trades of the whole portfolio closed before t
                                       are all losses, else 1 (trades with the same exit time are booked in entry
                                       order, then ASCII sleeve order)
   11  day after a bad day             g = 0 if the REAL result of the most recent earlier server day that has at
                                       least one real booking (looking back at most 7 days) is <= -p1, else 1
"""
import numpy as np
from numba import njit

NS_MIN = 60_000_000_000
NS_DAY = 86_400_000_000_000


@njit(cache=False)
def run_engine(t_in, t_out, R, sl, mk, fam, side, dy_in, dy_out, wk_in, wk_out, ok_broker, order_out,
               n_sleeves, n_days, n_weeks, code, p1, p2, cap_total, cap_mkt):
    n = len(R)
    m = np.zeros(n)
    why = np.zeros(n, np.int64)            # 0 taken, 1 guard, 2 position cap, 3 broker (stop < 3 spreads)
    open_total = 0
    open_mkt = np.zeros(4, np.int64)
    open_md = np.zeros((4, 2), np.int64)
    open_fd = np.zeros((3, 2), np.int64)
    dres = np.zeros(n_days)
    wres = np.zeros(n_weeks)
    mdl = np.zeros((n_days, 4), np.int64)
    cl = np.zeros(n_sleeves, np.int64)     # consecutive paper losses per sleeve
    port_cl = 0                            # consecutive paper losses of the portfolio
    # paper record per sleeve, in exit order: for the trailing windows
    rec_t = np.zeros((n_sleeves, n), np.int64)
    rec_R = np.zeros((n_sleeves, n))
    rec_n = np.zeros(n_sleeves, np.int64)
    w0 = np.zeros(n_sleeves, np.int64)
    ws = np.zeros(n_sleeves)
    wc = np.zeros(n_sleeves, np.int64)
    es = np.zeros(n_sleeves)
    ec = np.zeros(n_sleeves, np.int64)
    dcount = np.zeros(n_days, np.int64)    # real bookings per server day (code 11)
    win_ns = np.int64(p1 * NS_DAY) if (code == 4 or code == 5) else np.int64(0)
    j = 0
    for i in range(n):
        ti = t_in[i]
        while j < n and t_out[order_out[j]] < ti:
            k = order_out[j]
            j += 1
            s = sl[k]
            # paper updates (every trade of the sleeves)
            if R[k] < 0.0:
                cl[s] += 1
                port_cl += 1
            else:
                cl[s] = 0
                port_cl = 0
            q = rec_n[s]
            rec_t[s, q] = t_out[k]
            rec_R[s, q] = R[k]
            rec_n[s] = q + 1
            ws[s] += R[k]
            wc[s] += 1
            es[s] += R[k]
            ec[s] += 1
            # real updates (taken trades only)
            if m[k] > 0.0:
                sd = 1 if side[k] > 0 else 0
                open_total -= 1
                open_mkt[mk[k]] -= 1
                open_md[mk[k], sd] -= 1
                open_fd[fam[k], sd] -= 1
                dres[dy_out[k]] += m[k] * R[k]
                wres[wk_out[k]] += m[k] * R[k]
                dcount[dy_out[k]] += 1
                if R[k] < 0.0:
                    mdl[dy_out[k], mk[k]] += 1
        if not ok_broker[i]:
            why[i] = 3
            continue
        s = sl[i]
        sd = 1 if side[i] > 0 else 0
        g = 1.0
        if code == 1:
            if p2 == 0:
                c = open_md[mk[i], sd]
            elif p2 == 1:
                c = open_fd[fam[i], sd]
            else:
                c = open_mkt[mk[i]]
            if c >= 1:
                g = p1
        elif code == 2:
            if mdl[dy_in[i], mk[i]] >= p1:
                g = 0.0
        elif code == 3:
            if cl[s] >= p1:
                g = 0.0
        elif code == 4 or code == 5:
            lo = ti - win_ns
            for u in range(n_sleeves):
                while w0[u] < rec_n[u] and rec_t[u, w0[u]] < lo:
                    ws[u] -= rec_R[u, w0[u]]
                    wc[u] -= 1
                    w0[u] += 1
            if code == 4:
                if wc[s] > 0 and ws[s] <= 0.0:
                    g = 0.0
            else:
                g = _rank_weight(ws, wc, s, p2)
        elif code == 6:
            g = _rank_weight(es, ec, s, p2)
        elif code == 7:
            if dres[dy_in[i]] <= -p1:
                g = 0.0
        elif code == 8:
            if wres[wk_in[i]] <= -p1:
                g = 0.0
        elif code == 9:
            if port_cl >= p1:
                g = 0.0
        elif code == 11:
            q = dy_in[i] - 1
            while q >= 0 and q >= dy_in[i] - 7 and dcount[q] == 0:
                q -= 1
            if q >= 0 and q >= dy_in[i] - 7 and dres[q] <= -p1:
                g = 0.0
        if g <= 0.0:
            why[i] = 1
            continue
        if open_total >= cap_total or open_mkt[mk[i]] >= cap_mkt:
            why[i] = 2
            continue
        m[i] = g
        open_total += 1
        open_mkt[mk[i]] += 1
        open_md[mk[i], sd] += 1
        open_fd[fam[i], sd] += 1
    return m, why


@njit(cache=False)
def _rank_weight(sums, cnts, s, min_n):
    if cnts[s] < min_n:
        return 1.0
    nr = 0
    for u in range(len(cnts)):
        if cnts[u] >= min_n:
            nr += 1
    if nr < 2:
        return 1.0
    mine = sums[s] / cnts[s]
    below = 0.0
    ties = 0.0
    for u in range(len(cnts)):
        if cnts[u] >= min_n and u != s:
            v = sums[u] / cnts[u]
            if v < mine:
                below += 1.0
            elif v == mine:
                ties += 1.0
    rank = below + 0.5 * ties              # average rank, 0 = lowest
    return 0.5 + rank / (nr - 1)
