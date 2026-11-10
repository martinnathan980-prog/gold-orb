"""Context sheet ("fiche") that the robot sends to Claude when a rule fires.

Everything comes from M1 bars that are CLOSED before the decision (index < i): nothing from the future.
For the blind test on past data the sheet is anonymous: no date and no absolute price (prices are in %
or basis points from the current price, or in ATR units), so the model cannot recognise the day and
"remember" what happened next. The live robot will send the same sheet, plus the date and the news,
which only a forward test can evaluate.

    mk = Market("btcusd")                                   # research frame (FP costs), arrays prepared once
    text, feats = mk.sheet(i, side, entry, stop, ref=Market("us100"))
        i      index of the bar at whose open (or inside which) the order is filled
        text   what the model reads            feats  the same information as numbers (for a fitted baseline)
"""
import numpy as np
import pandas as pd

from goldlab import r2
from goldlab.data import LDN, NY, trading_day

ASSET = {"us100": "Nasdaq-100 index CFD", "btcusd": "Bitcoin / US dollar", "ethusd": "Ether / US dollar",
         "xauusd": "Gold / US dollar"}
N_D, N_H, N_M = 15, 36, 24          # bars printed: daily, hourly, 5-minute
MIN_FULL_DAY = 600                  # minutes of quotes for a trading day to count as complete
WD = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _f(v, fmt):
    """Format a number, 'n/a' when it does not exist (history too short, market closed)."""
    return format(v, fmt) if v is not None and np.isfinite(v) else "n/a"


def _rsi(x, n=14):
    """Simple RSI of the last n changes of series x (chronological)."""
    d = np.diff(x[-(n + 1):])
    if len(d) < n:
        return np.nan
    up, dn = d[d > 0].sum(), -d[d < 0].sum()
    return 50.0 if up + dn == 0 else 100.0 * up / (up + dn)


class Market:
    def __init__(self, sym, m1=None):
        m1 = r2.load(sym) if m1 is None else m1
        self.sym = sym
        self.index = m1.index
        self.tmin = (m1.index.as_unit("ms").asi8 // 60_000).astype(np.int64)      # bar start, minutes since epoch
        self.o = ((m1["bo"] + m1["ao"]) / 2).to_numpy(np.float64)
        self.h = ((m1["bh"] + m1["ah"]) / 2).to_numpy(np.float64)
        self.l = ((m1["bl"] + m1["al"]) / 2).to_numpy(np.float64)
        self.c = ((m1["bc"] + m1["ac"]) / 2).to_numpy(np.float64)
        self.spr = (m1["ac"] - m1["bc"]).to_numpy(np.float64)
        day = trading_day(m1.index).asi8                     # trading day = MT5 server day (17:00 New York)
        self.first = np.r_[0, np.flatnonzero(np.diff(day)) + 1]
        cnt = np.diff(np.r_[self.first, len(day)])
        self.day_of_bar = np.repeat(np.arange(len(self.first)), cnt)
        self.d_o = self.o[self.first]
        self.d_h = np.maximum.reduceat(self.h, self.first)
        self.d_l = np.minimum.reduceat(self.l, self.first)
        self.d_c = self.c[np.r_[self.first[1:], len(day)] - 1]
        self.d_full = cnt >= MIN_FULL_DAY

    # ------------------------------------------------------------------------------------------
    def _windows(self, i, width, n_max, look):
        """Up to n_max non-empty windows of `width` minutes ending at the decision time, most recent first.
        Rows: age (minutes from the window start to the decision), open, high, low, close."""
        b = self.tmin[i] - width * np.arange(look + 1)
        ix = np.searchsorted(self.tmin, b, side="left")       # ix[0] == i: only bars < i are ever read
        out = []
        for k in range(look):
            a, z = ix[k + 1], ix[k]
            if z > a:
                out.append((width * (k + 1), self.o[a], self.h[a:z].max(), self.l[a:z].min(), self.c[z - 1]))
                if len(out) == n_max:
                    break
        return np.array(out, np.float64).reshape(-1, 5)

    def _ago(self, i, minutes):
        """Price `minutes` before the decision (open of the first bar at/after that time), or nan."""
        t = self.tmin[i] - minutes
        j = int(np.searchsorted(self.tmin, t, side="left"))
        return self.o[j] if j < i and self.tmin[j] - t <= max(5, minutes // 4) else np.nan

    def _ny_minute(self, ny, hh, mm, back_days=0):
        """Minutes since epoch (UTC) of the New-York wall-clock time hh:mm, `back_days` calendar days earlier."""
        d = ny.tz_localize(None).normalize() - pd.Timedelta(days=back_days)
        t = pd.Timestamp(d.year, d.month, d.day, hh, mm, tz=NY)
        return int(t.timestamp() // 60), t.weekday()

    # ------------------------------------------------------------------------------------------
    def sheet(self, i, side, entry, stop, ref=None):
        """Context sheet for an order filled on bar i (data used: bars < i). Returns (text, feats) or None
        when the history is too short."""
        i, side, px = int(i), int(side), float(entry)
        k = self.day_of_bar[i]
        full = np.flatnonzero(self.d_full[:k])[-260:]            # complete trading days before today
        H = self._windows(i, 60, 72, 240)
        M = self._windows(i, 5, 36, 120)
        if len(full) < 30 or len(H) < 30:        # (no 5-minute bar yet = first minutes after a closure: allowed)
            return None
        Do, Dh, Dl, Dc = self.d_o[full], self.d_h[full], self.d_l[full], self.d_c[full]
        pct = lambda v: (v / px - 1.0) * 100.0                 # where a past price sits, in % from the current price
        bp = lambda v: (v / px - 1.0) * 1e4
        chg = lambda v: (px / v - 1.0) * 100.0                 # change of the price since a past price, in %
        f = {"side": side}

        # ---- volatility
        tr = np.maximum(Dh[1:] - Dl[1:], np.maximum(np.abs(Dh[1:] - Dc[:-1]), np.abs(Dl[1:] - Dc[:-1])))
        atr_d = float(tr[-14:].mean())
        Hc = H[::-1]                                             # chronological
        trh = np.maximum(Hc[1:, 2] - Hc[1:, 3], np.maximum(np.abs(Hc[1:, 2] - Hc[:-1, 4]), np.abs(Hc[1:, 3] - Hc[:-1, 4])))
        atr_h = float(trh[-24:].mean())
        lr = np.diff(np.log(Dc))
        rv = pd.Series(lr).rolling(20).std().to_numpy() * np.sqrt(252) * 100
        rv20 = float(rv[-1])
        past = rv[:-1][np.isfinite(rv[:-1])][-250:]
        vol_pct = float((past < rv20).mean() * 100) if len(past) >= 60 else np.nan
        spr_now = float(self.spr[i - 1] / px * 1e4)
        spr_ratio = float(self.spr[i - 1] / max(np.median(self.spr[max(0, i - 1440):i]), 1e-12))
        risk = abs(px - float(stop))
        f.update(atr_d_pct=atr_d / px * 100, atr_h_bp=atr_h / px * 1e4, rv20=rv20, vol_pct=vol_pct,
                 spr_bp=spr_now, spr_ratio=spr_ratio, stop_pct=risk / px * 100, stop_atr_d=risk / atr_d,
                 stop_atr_h=risk / atr_h)

        # ---- today (server day so far) and yesterday's levels
        a = self.first[k]
        t_o = self.o[a] if i > a else px
        t_h = max(self.h[a:i].max(), px) if i > a else px
        t_l = min(self.l[a:i].min(), px) if i > a else px
        pos_day = (px - t_l) / (t_h - t_l) if t_h > t_l else 0.5
        pdh, pdl, pdc = Dh[-1], Dl[-1], Dc[-1]
        piv = (pdh + pdl + pdc) / 3
        lev = {"prev day high": pdh, "prev day low": pdl, "prev day close": pdc, "pivot": piv,
               "R1": 2 * piv - pdl, "S1": 2 * piv - pdh, "R2": piv + (pdh - pdl), "S2": piv - (pdh - pdl),
               "20-day high": Dh[-20:].max(), "20-day low": Dl[-20:].min(),
               "1-year high": Dh.max(), "1-year low": Dl.min()}
        lev_atr = {n: (v - px) / atr_d for n, v in lev.items()}
        f.update(a_day_chg=side * chg(t_o), a_prev_close_chg=side * chg(pdc), day_range_atr=(t_h - t_l) / atr_d,
                 a_pos_day=pos_day if side > 0 else 1 - pos_day,
                 a_room_20d=(lev["20-day high"] - px) / atr_d if side > 0 else (px - lev["20-day low"]) / atr_d,
                 a_dist_prev_extreme=(px - pdh) / atr_d if side > 0 else (pdl - px) / atr_d,
                 a_dist_pivot=side * (px - piv) / atr_d)

        # ---- trend / momentum
        ret = lambda n: (px / Dc[-n] - 1.0) * 100.0 if len(Dc) >= n else np.nan
        ma = lambda n: (px / Dc[-n:].mean() - 1.0) * 100.0 if len(Dc) >= n else np.nan
        sg = np.sign(np.diff(Dc[-12:]))
        streak = 0
        for s in sg[::-1]:
            if s == sg[-1] and s != 0:
                streak += 1
            else:
                break
        streak = int(streak * sg[-1])
        hc = np.r_[Hc[:, 4], px]
        mc = np.r_[M[::-1, 4], px]
        rsi_h, rsi_m = _rsi(hc), _rsi(mc)
        b20 = Hc[-20:, 4]
        pb = (px - (b20.mean() - 2 * b20.std())) / (4 * b20.std()) if b20.std() > 0 else 0.5
        ch = (px - Hc[:, 4].min()) / (Hc[:, 4].max() - Hc[:, 4].min()) if Hc[:, 4].max() > Hc[:, 4].min() else 0.5
        m30, m60, m240 = (chg(self._ago(i, m)) * 100 for m in (30, 60, 240))      # in basis points
        f.update(a_ret5=side * ret(5), a_ret20=side * ret(20), a_ret60=side * ret(60), a_ma20=side * ma(20),
                 a_ma50=side * ma(50), a_ma200=side * ma(200), a_streak=side * streak,
                 a_rsi_h=rsi_h if side > 0 else 100 - rsi_h, a_rsi_m=rsi_m if side > 0 else 100 - rsi_m,
                 a_pb=pb if side > 0 else 1 - pb, a_ch=ch if side > 0 else 1 - ch,
                 a_m30=side * m30 / (atr_h / px * 1e4), a_m60=side * m60 / (atr_h / px * 1e4),
                 a_m240=side * m240 / (atr_h / px * 1e4))

        # ---- clock
        ts = self.index[i]
        ny, ld = ts.tz_convert(NY), ts.tz_convert(LDN)
        mny = ny.hour * 60 + ny.minute
        if ny.weekday() < 5 and 570 <= mny < 960:
            cash = f"open for {mny - 570} min, closes in {960 - mny} min"
        elif ny.weekday() < 5 and mny < 570:
            cash = f"closed, opens in {570 - mny} min"
        else:
            cash = "closed"
        wk_min = 16 * 60 + 55 if self.sym in r2.CRYPTO else 17 * 60
        to_close = ((4 - ny.weekday()) % 7) * 24 + (wk_min - mny) / 60.0
        if to_close < 0:
            to_close += 7 * 24
        f.update(ny_hour=mny / 60.0, dow=ny.weekday(), h_to_weekend=to_close)

        L = ["SIGNAL",
             f"asset: {ASSET.get(self.sym, self.sym)} | side: {'LONG (buy)' if side > 0 else 'SHORT (sell)'} | entry: at market, now",
             f"stop: {risk / px * 100:.2f}% from entry = {risk / atr_d:.2f} daily ATR = {risk / atr_h:.1f} hourly ATR",
             "", "CLOCK",
             f"New York {WD[ny.weekday()]} {ny:%H:%M} | London {WD[ld.weekday()]} {ld:%H:%M} | US cash session: {cash} | "
             f"weekly close in {to_close:.0f} h",
             "", "TODAY (trading day so far)",
             f"since the day's open {chg(t_o):+.2f}% | since the previous close {chg(pdc):+.2f}% | "
             f"range so far {(t_h - t_l) / atr_d:.2f} daily ATR | position in today's range {pos_day:.2f} (0 = low, 1 = high)"]

        # ---- US cash session block (index only)
        if self.sym == "us100" and ny.weekday() < 5 and mny >= 570:
            t_open, _ = self._ny_minute(ny, 9, 30)
            io = int(np.searchsorted(self.tmin, t_open, side="left"))
            if io < i and self.tmin[io] - t_open <= 5:
                c_o = self.o[io]
                c_h, c_l = max(self.h[io:i].max(), px), min(self.l[io:i].min(), px)
                pc = np.nan
                for back in range(1, 6):
                    t_pc, wd = self._ny_minute(ny, 16, 0, back)
                    j = int(np.searchsorted(self.tmin, t_pc, side="left")) - 1
                    if wd < 5 and j >= 0 and t_pc - self.tmin[j] <= 10:
                        pc = self.c[j]
                        break
                gap = (c_o / pc - 1) * 100 if np.isfinite(pc) else np.nan
                L.append(f"US cash session: opening gap {_f(gap, '+.2f')}% | since the 09:30 open {chg(c_o):+.2f}% | "
                         f"session high {bp(c_h):+.0f} bp, session low {bp(c_l):+.0f} bp from the current price")
                f.update(a_gap=side * gap, a_cash_chg=side * chg(c_o))

        L += ["", "LEVELS (distance from the current price in daily ATR; + = above the price)",
              " | ".join(f"{n} {v:+.2f}" for n, v in lev_atr.items()),
              "", "TREND AND MOMENTUM",
              f"5 days {ret(5):+.1f}% | 20 days {ret(20):+.1f}% | 60 days {_f(ret(60), '+.1f')}% | vs 20-day average "
              f"{ma(20):+.1f}% | vs 50-day {_f(ma(50), '+.1f')}% | vs 200-day {_f(ma(200), '+.1f')}% | "
              f"daily closes in a row {streak:+d}",
              f"hourly RSI14 {rsi_h:.0f} | hourly Bollinger %B {pb:.2f} | position in the 72-hour close channel {ch:.2f} | "
              f"5-min RSI14 {_f(rsi_m, '.0f')} | last 30 min {_f(m30, '+.0f')} bp | last 60 min {_f(m60, '+.0f')} bp | "
              f"last 4 h {_f(m240, '+.0f')} bp",
              "", "VOLATILITY AND LIQUIDITY",
              f"daily ATR14 {atr_d / px * 100:.2f}% of price | hourly ATR24 {atr_h / px * 1e4:.0f} bp | realised 20-day volatility "
              f"{rv20:.0f}% a year = percentile {_f(vol_pct, '.0f')} of the past year | spread now {spr_now:.1f} bp = "
              f"{spr_ratio:.1f} x its 24-hour median"]

        # ---- another market as backdrop (Nasdaq-100 for everything that is not the Nasdaq)
        if ref is not None and ref.sym != self.sym:
            t0 = self.tmin[i]
            j = int(np.searchsorted(ref.tmin, t0, side="left"))
            if j > 1 and t0 - ref.tmin[j - 1] <= 15:
                rp = ref.c[j - 1]
                rf = np.flatnonzero(ref.d_full[:ref.day_of_bar[j - 1]])
                d_chg = (rp / ref.d_c[rf[-1]] - 1) * 100 if len(rf) else np.nan
                j60 = int(np.searchsorted(ref.tmin, t0 - 60, side="left"))
                h_chg = (rp / ref.o[j60] - 1) * 1e4 if j60 < j and t0 - ref.tmin[j60] <= 60 else np.nan
                m_chg = (rp / ref.c[j - 2] - 1) * 1e4 if ref.tmin[j - 1] - ref.tmin[j - 2] <= 2 else np.nan
                L += ["", f"BACKDROP  {ASSET[ref.sym]}: {_f(d_chg, '+.2f')}% since its previous close | {_f(h_chg, '+.0f')} bp "
                          f"over the last 60 min | last 1-minute bar {_f(m_chg, '+.1f')} bp"]
                f.update(a_ref_day=side * d_chg, a_ref_60=side * h_chg, a_ref_1=side * m_chg)
            else:
                L += ["", f"BACKDROP  {ASSET[ref.sym]}: market closed"]

        # ---- bars
        L += ["", "DAILY BARS, oldest first (open high low close, in % from the current price; d-1 = yesterday)"]
        n = min(N_D, len(Dc))
        for q in range(n, 0, -1):
            L.append(f"d-{q}: {pct(Do[-q]):+.2f} {pct(Dh[-q]):+.2f} {pct(Dl[-q]):+.2f} {pct(Dc[-q]):+.2f}")
        L += ["", "HOURLY BARS, oldest first (start of the hour in hours before now: open high low close, in basis points "
                  "from the current price; missing hours = market closed)"]
        for r in H[:N_H][::-1]:
            L.append(f"-{r[0] / 60:.0f}h: {bp(r[1]):+.0f} {bp(r[2]):+.0f} {bp(r[3]):+.0f} {bp(r[4]):+.0f}")
        L += ["", "5-MINUTE BARS, oldest first (start in minutes before now: open high low close, in basis points)"]
        for r in M[:N_M][::-1]:
            L.append(f"-{r[0]:.0f}m: {bp(r[1]):+.1f} {bp(r[2]):+.1f} {bp(r[3]):+.1f} {bp(r[4]):+.1f}")
        return "\n".join(L), {k_: (float(v) if v is not None else np.nan) for k_, v in f.items()}
