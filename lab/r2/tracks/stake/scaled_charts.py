"""Pictures for the user (French, phone width): the gain for the risk between 3 % and 10 %, PROTOCOL_V3 addendum G,
ninth clarification (2026-11-13). D2's shape scaled by its starting risk X: X % per trade below 3,000 EUR, X/2 % below
10,000, X/5 % below 20,000, X/10 % above, read on the larger of the balance and the money paid in, no plan stop and no
disaster guard. Plans S3, S5, S6, S7, S8 and S10 (S10 = D2, the user's current plan).

    python3 r2/tracks/stake/scaled_charts.py      (from lab/)

Reads only result files (no trade and no price is read, the engine is not run):
    results/r2/stake/scaled_summary.json   the declared measures per plan and case (written by scaled_summary.py)
    results/r2/stake/growth_scaled.json    the 40 sample paths and the monthly gain percentiles (picture 17), and the
                                           cross-checks of the summary figures
Writes into results/r2/stake/images/:
    15_gain_pour_le_risque.png   gain after 1 year against the typical first-year fall, one point per X, half and paper;
                                 below, the gain after 1 year if the robot does worse (quarter, covers costs, worthless)
    16_mois_pour_10000.png       months to 10,000 EUR, the chance by the end of month 6, the chance of a fall of 50 % or
                                 more (half, paper, and the three worse cases), and the deepest fall of the worst path
    17_compte_7_contre_10.png    the gain month by month in the first year at 7 % and at 10 %, half of the paper edge, with
                                 the one-in-ten line (the 40 drawn paths happen to end the year better than the 2,000)
The colours, fonts, rounding and page layout are those of plan_charts.py. Every figure printed on a picture is listed
on stdout with its source key. Nothing is chosen here: the user picks the X.
"""
import json
import os
from decimal import Decimal, ROUND_HALF_UP

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
STAKE = os.path.join(LAB, "results", "r2", "stake")
SUM = json.load(open(os.path.join(STAKE, "scaled_summary.json")))
GS = json.load(open(os.path.join(STAKE, "growth_scaled.json")))
IMG = os.path.join(STAKE, "images")

# the colours and fonts of plan_charts.py / growth_charts.py
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_T, ORANGE_T = "#9ec5f4", "#f6b99f"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
NNBSP, MINUS = " ", "−"
W, DPI = 6.0, 200
L = 0.28                                                 # left margin of the text, inches

PLANS = (("S3", 3), ("S5", 5), ("S6", 6), ("S7", 7), ("S8", 8), ("S10", 10))
CURRENT = "S10"                                          # = D2, the user's choice of 2026-11-13 (PROTOCOL_V3, addendum G)
EDGE = {"paper": "1.0", "half": "0.5", "quarter": "0.25"}  # summary case -> edge key of growth_scaled.json
PIC15, PIC16, PIC17 = "15_gain_pour_le_risque.png", "16_mois_pour_10000.png", "17_compte_7_contre_10.png"


def th(v):
    """A whole number with a narrow no-break space between the thousands (2 000)."""
    return f"{int(v):,}".replace(",", NNBSP)


SIM = "Simulation sur les trades de 2022 à 2025, aucun trade réel."
DETAIL = f"{th(2000)} trajectoires de 3 ans tirées des trades de 2022 à 2025, {th(1000)} € versés par mois."
PAPER_WORDS = ("« Comme sur le papier » : chaque règle gagne en moyenne par trade\n"
               "comme en 2022-2025 ; « la moitié du papier » : moitié moins.")
CAVEATS = ("Ce sont les années qui ont servi à valider les règles : ces chiffres sont optimistes.\n"
           "La marge du courtier sur les cryptos n'est pas simulée : aux grosses mises, il peut\n"
           "refuser des trades. Aucun arrêt de sécurité dans ces plans. Le choix du palier est le tien.")

# ---------------------------------------------------------------------------------------------------- checks of the inputs
assert SUM["check_S10_equals_stored_D2"]["identical"] is True
assert not SUM["check_per_path_file"]["failures"] and SUM["check_per_path_file"]["S10_and_D2_paths_identical"] is True
assert not SUM["check_rest_of_growth_json_reproduced"]["differences"]
assert SUM["paths"] == GS["paths"] == 2000 and SUM["months"] == GS["months"] == 36
assert SUM["period"] == GS["period"] == ["2022-01-01", "2026-01-01"] and GS["payment_eur"] == 1000.0
PAID = GS["paid_by_month"]
assert PAID == [1000.0 * max(h, 1) for h in range(GS["months"] + 1)]          # 1,000 at the start, then 1,000 a month
for _p, _x in PLANS:
    _pl = SUM["plans"][_p]
    assert _pl["thresholds_eur"] == [3000.0, 10000.0, 20000.0] and _pl["stop"] is None and _pl["x_pct"] == _x
    assert np.allclose(_pl["risk_pct"], [_x, _x / 2, _x / 5, _x / 10], rtol=0, atol=1e-12)
    assert GS["schedules"][_p] == {"thresholds_eur": _pl["thresholds_eur"], "risk_pct": _pl["risk_pct"]}
    assert _p in GS["keyed_on_max_of_balance_and_paid"] and _p not in GS["stopped"]
    for _case, _e in EDGE.items():                    # the summary figures used here are the engine's own cells
        _s, _r = SUM["summary"][_p][_case], GS["resampled"][_p][_e]
        assert _s["gain_after_1_year_eur"] == {"median": _r["at_12_months"]["gain_median"], "p10": _r["at_12_months"]["gain_p10"]}
        assert _s["first_year_fall"]["typical_pct"] == _r["falls"]["fall_first_52_weeks_pct"]["median"]
        assert _s["fall_of_50_pct_or_more_pct"] == _r["shares_of_paths_pct"]["fall_of_50_pct_or_more"]
        assert _s["reaches_zero_pct"] == _r["balance_reaches_zero_pct"]

SHOWN = []      # (picture, source key, value read, text printed)


def record(pic, key, v, text=None):
    if not any(a == pic and b == key for a, b, _, _ in SHOWN):
        SHOWN.append((pic, key, v, text))


def S(pic, plan, case, *keys):
    """A value of scaled_summary.json["summary"], recorded with its key for the report."""
    v = SUM["summary"][plan][case]
    for k in keys:
        v = v[k]
    record(pic, f"scaled_summary.json summary/{plan}/{case}/" + "/".join(keys), v)
    return v


def R(pic, plan, edge, *keys):
    """A value of growth_scaled.json["resampled"], recorded with its key for the report."""
    v = GS["resampled"][plan][edge]
    for k in keys:
        v = v[k]
    record(pic, f"growth_scaled.json resampled/{plan}/{edge}/" + "/".join(keys), v)
    return v


# ---------------------------------------------------------------------------------------------------- formatting
def half_up(v, step=1):
    """Rounded to the nearest multiple of `step`, halves away from zero (2.5 -> 3, 40.5 -> 41, 1,245 -> 1,250)."""
    q = (Decimal(repr(float(v))) / Decimal(step)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(q) * step


def eur(v, sign=False, step=10):
    """Euros rounded half up to `step` (10 EUR by default), narrow no-break space between thousands, ' €'."""
    r = half_up(v, step)
    s = th(abs(r)) + " €"
    if r < 0:
        return MINUS + s
    return ("+" + s) if (sign and r > 0) else s


def pct(v, minus=False):
    """A percentage: whole numbers rounded half up; one decimal below 1 and between 99 and 100, so that a small share is
    not shown as 0 and a share short of all the paths is not shown as 100."""
    v = float(v)
    if v == 0:
        s = "0"
    elif abs(v) < 1 or 99 < abs(v) < 100:
        s = str(Decimal(repr(abs(v))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)).replace(".", ",")
    else:
        s = str(half_up(abs(v)))
    return (MINUS if minus and v != 0 else "") + s + " %"


def risk_txt(v):
    return (f"{v:g}".replace(".", ",")) + " %"


def months_txt(m):
    return "pas en 3 ans" if m is None else f"{m} mois"


# ---------------------------------------------------------------------------------------------------- page layout
def lines_h(n, size, spacing=1.3):
    """Height in inches of n lines of text at `size` points."""
    return n * size * spacing / 72.0


class Page:
    """Positions in inches from the top-left corner of a 6-inch-wide picture."""

    def __init__(self, h):
        self.h = h
        self.fig = plt.figure(figsize=(W, h), dpi=DPI)
        self.guarded = []            # (texts, axes, data lines) : these texts must not cover those lines or their dots

    def fx(self, x):
        return x / W

    def fy(self, y):
        return 1.0 - y / self.h

    def text(self, x, y, s, **kw):
        kw.setdefault("va", "top")
        return self.fig.text(self.fx(x), self.fy(y), s, **kw)

    def axes(self, x, y, w, h):
        return self.fig.add_axes([self.fx(x), self.fy(y + h), w / W, h / self.h])

    def swatch(self, x, y, color, w=0.22, h=0.13, kind="patch", lw=2.6, alpha=1.0, ls="-"):
        """A legend mark whose top-left corner is at (x, y) inches."""
        if kind == "patch":
            self.fig.patches.append(Rectangle((self.fx(x), self.fy(y + h)), w / W, h / self.h, transform=self.fig.transFigure,
                                              color=color, lw=0, alpha=alpha))
            return
        self.fig.lines.append(Line2D([self.fx(x), self.fx(x + w)], [self.fy(y + h / 2)] * 2, transform=self.fig.transFigure,
                                     color=color, lw=lw, alpha=alpha, ls=ls, solid_capstyle="butt", dash_capstyle="butt"))
        if kind == "linedot":
            self.fig.lines.append(Line2D([self.fx(x + w / 2)], [self.fy(y + h / 2)], transform=self.fig.transFigure, marker="o",
                                         ms=7, mfc=color, mec=SURF, mew=1.4, ls="none"))

    def check(self, name):
        """Every text inside the picture, no two texts overlapping (a tolerance of half a point), and the guarded texts
        clear of the data lines and dots they sit next to."""
        self.fig.canvas.draw()
        r = self.fig.canvas.get_renderer()
        items = [t for t in self.fig.texts]
        for ax in self.fig.axes:
            items += list(ax.texts) + ax.get_xticklabels() + ax.get_yticklabels() + [ax.xaxis.label, ax.yaxis.label]
        items = [t for t in items if t.get_visible() and t.get_text().strip()]
        boxes = [(t, t.get_window_extent(r)) for t in items]
        fw, fh = W * DPI, self.h * DPI
        tol = 0.5 * DPI / 72.0
        bad = []
        for t, b in boxes:
            if b.x0 < -tol or b.y0 < -tol or b.x1 > fw + tol or b.y1 > fh + tol:
                bad.append(f"outside the picture: {t.get_text()[:40]!r}")
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                (t1, b1), (t2, b2) = boxes[i], boxes[j]
                if min(b1.x1, b2.x1) - max(b1.x0, b2.x0) > tol and min(b1.y1, b2.y1) - max(b1.y0, b2.y0) > tol:
                    bad.append(f"overlap: {t1.get_text()[:40]!r} / {t2.get_text()[:40]!r}")
        for texts, ax, lines in self.guarded:
            frame = ax.get_window_extent(r)
            for t in texts:
                b = t.get_window_extent(r)
                if b.x0 < frame.x0 - tol or b.x1 > frame.x1 + tol or b.y0 < frame.y0 - tol or b.y1 > frame.y1 + tol:
                    bad.append(f"label outside its plot: {t.get_text()[:30]!r}")
                for ln in lines:
                    xy = ax.transData.transform(np.column_stack(ln.get_data()))
                    dots = ln.get_marker() not in (None, "None", "none", "")
                    if dots:                                   # each dot's square, its ring included
                        rad = (ln.get_markersize() / 2 + ln.get_markeredgewidth()) * DPI / 72.0
                        for px, py in xy:
                            if min(b.x1, px + rad) - max(b.x0, px - rad) > tol and min(b.y1, py + rad) - max(b.y0, py - rad) > tol:
                                bad.append(f"label on a dot: {t.get_text()[:30]!r}")
                    if ln.get_linestyle() not in ("None", "none", ""):
                        half = ln.get_linewidth() / 2 * DPI / 72.0
                        for (x0, y0), (x1, y1) in zip(xy[:-1], xy[1:]):
                            s = np.linspace(0, 1, 200)
                            px, py = x0 + s * (x1 - x0), y0 + s * (y1 - y0)
                            inside = ((px > b.x0 - half + tol) & (px < b.x1 + half - tol) & (py > b.y0 - half + tol) & (py < b.y1 + half - tol))
                            if inside.any():
                                bad.append(f"label on a line: {t.get_text()[:30]!r}")
                                break
        assert not bad, f"{name}: " + "; ".join(sorted(set(bad)))

    def save(self, name):
        try:
            self.check(name)
        except AssertionError:
            if os.environ.get("SCALED_CHARTS_DEBUG"):           # keep the faulty picture for a look, outside the repository
                self.fig.savefig(os.path.join(os.environ["SCALED_CHARTS_DEBUG"], name), dpi=DPI)
            raise
        path = os.path.join(IMG, name)
        self.fig.savefig(path, dpi=DPI)
        plt.close(self.fig)
        print("written", path, f"({W:g} x {self.h:g} inches at {DPI} dpi)")
        return path


def draw(build, name, bottom=0.2):
    """Lay the picture out once on a tall page to learn where its content ends, then draw it on a page of that height."""
    pg = Page(60.0)
    end = build(pg)
    plt.close(pg.fig)
    pg = Page(round(end + bottom, 2))
    assert abs(build(pg) - end) < 1e-9
    return pg.save(name)


# ---------------------------------------------------------------------------------------------------- bars (picture 16)
def hbar_axes(ax, n, xmax, ticklabels, bold_row=None):
    ax.set_xlim(0, xmax)
    ax.set_ylim(n - 0.5, -0.5)
    ax.set_yticks(range(n))
    ax.set_yticklabels(ticklabels, fontsize=10.5, color=INK)
    if bold_row is not None:
        ax.get_yticklabels()[bold_row].set_fontweight("bold")
    ax.set_xticks([])
    ax.tick_params(length=0, pad=7)
    for sp in ("top", "right", "bottom", "left"):
        ax.spines[sp].set_visible(False)
    ax.axvline(0, color=AXIS, lw=1.2, zorder=4)


def bar_labels(ax, ys, vals, texts, xmax, bold=True, size=10):
    out = []
    for y, v, s in zip(ys, vals, texts):
        t = ax.text(v + xmax * 0.012, y, s, va="center", ha="left", fontsize=size, color=INK if bold else INK2,
                    fontweight="bold" if bold else "normal", zorder=6)
        t._bar_end = v
        out.append(t)
    return out


def fit_labels(ax, labels, xmax, pad_in=0.06):
    """Widen the x range until every bar-end label lies inside the axes (with `pad_in` inches to spare)."""
    fig = ax.figure
    for _ in range(40):
        fig.canvas.draw()
        r = fig.canvas.get_renderer()
        box = ax.get_window_extent(r)
        right = box.x1 - pad_in * DPI
        worst = max(t.get_window_extent(r).x1 for t in labels)
        if worst <= right:
            return xmax
        xmax *= 1.0 + (worst - right) / box.width + 0.01
        ax.set_xlim(0, xmax)
        for t in labels:                       # a label sits a fixed share of the range after its bar
            t.set_x(t._bar_end + xmax * 0.012)
    raise RuntimeError("labels do not fit")


def pair_bars(ax, dark, light, c_dark, c_light, texts_dark, texts_light, xmax):
    """Two bars per row, the main case (dark) above its lighter companion, a 2 px surface gap between them."""
    n = len(dark)
    hb = 0.36
    ya, yb = np.arange(n) - hb / 2 - 0.012, np.arange(n) + hb / 2 + 0.012
    ax.barh(ya, dark, height=hb, color=c_dark, lw=0, zorder=3)
    ax.barh(yb, light, height=hb, color=c_light, lw=0, zorder=3)
    labs = bar_labels(ax, ya, dark, texts_dark, xmax, size=9.5) + bar_labels(ax, yb, light, texts_light, xmax, bold=False, size=9.5)
    return fit_labels(ax, labs, xmax)


# ---------------------------------------------------------------------------------------------------- the worse cases
WORSE = (("quarter", "un quart du papier"), ("covers_costs", "couvre juste ses frais"), ("worthless", "ne vaut rien"))
XCOLS = (2.28, 2.972, 3.664, 4.356, 5.048, 5.74)        # right edge of each X column of the small tables, inches


def x_table(pg, pic, y, rows, size=9, row_h=0.26):
    """A small table, one row per case and one column per starting risk X (10 % in bold, as in the other tables).
    rows = [(label, [text for each X])]. Returns the y below it."""
    pg.text(L, y, "départ à", fontsize=9, color=INK2)
    for (p, x), c in zip(PLANS, XCOLS):
        pg.text(c, y, f"{x} %", fontsize=9, color=INK2, ha="right", fontweight="bold" if p == CURRENT else "normal")
    y += lines_h(1, 9) + 0.06
    for label, texts in rows:
        pg.fig.lines.append(Line2D([pg.fx(L), pg.fx(XCOLS[-1])], [pg.fy(y)] * 2, transform=pg.fig.transFigure, color=GRID, lw=0.8))
        yy = y + 0.055
        pg.text(L, yy, label, fontsize=size, color=INK)
        for (p, x), c, s in zip(PLANS, XCOLS, texts):
            pg.text(c, yy, s, fontsize=size, color=INK, ha="right", fontweight="bold" if p == CURRENT else "normal")
        record(pic, f"worse-case row {label}", None, " | ".join(texts))
        y += row_h
    pg.fig.lines.append(Line2D([pg.fx(L), pg.fx(XCOLS[-1])], [pg.fy(y)] * 2, transform=pg.fig.transFigure, color=GRID, lw=0.8))
    return y + 0.1


# ---------------------------------------------------------------------------------------------------- picture 15
def picture_15(pg):
    pic = PIC15
    xs = [x for _, x in PLANS]
    k_cur = [p for p, _ in PLANS].index(CURRENT)
    hg = [S(pic, p, "half", "gain_after_1_year_eur", "median") for p, _ in PLANS]
    hp = [S(pic, p, "half", "gain_after_1_year_eur", "p10") for p, _ in PLANS]
    hf = [S(pic, p, "half", "first_year_fall", "typical_pct") for p, _ in PLANS]
    ag = [S(pic, p, "paper", "gain_after_1_year_eur", "median") for p, _ in PLANS]
    af = [S(pic, p, "paper", "first_year_fall", "typical_pct") for p, _ in PLANS]
    qg = [S(pic, p, "quarter", "gain_after_1_year_eur", "median") for p, _ in PLANS]
    k_q = int(np.argmax(qg))                                  # the footnote says: no more gain past this X, if a quarter
    assert all(qg[i] >= qg[i + 1] for i in range(k_q, len(qg) - 1)), qg

    y = 0.2
    pg.text(L, y, "Ce que rapporte chaque palier de risque,\net ce qu'il coûte", fontsize=15, fontweight="bold", linespacing=1.18)
    y += lines_h(2, 15, 1.18) + 0.1
    pg.text(L, y, SIM, fontsize=10.5, color=INK2)
    y += lines_h(1, 10.5) + 0.08
    pg.text(L, y, f"Chaque point est un départ à X % par trade. Le risque baisse ensuite :\n"
                  f"X/2 dès {th(3000)} €, X/5 dès {th(10000)} €, X/10 dès {th(20000)} € (ton solde ou l'argent\n"
                  f"versé, le plus grand des deux). 10 % = ton choix actuel.", fontsize=10, color=INK2, linespacing=1.3)
    y += lines_h(3, 10) + 0.14
    for c, s in ((BLUE, "s'il fait la moitié du papier"), (BLUE_T, "s'il fait comme sur le papier")):
        pg.swatch(L, y + 0.025, c, w=0.4, h=0.14, kind="linedot", lw=2.2)
        pg.text(L + 0.52, y, s, fontsize=10.5, color=INK2)
        y += 0.25
    y += 0.12

    # the chart: gain after one year (up) against the typical deepest fall of the first year (right)
    AX, AW, AH = 1.02, W - 1.02 - 0.24, 4.1
    pg.text(L, y, "Gain après 1 an (au milieu)", fontsize=11.5, fontweight="bold")
    y += lines_h(1, 11.5) + 0.06
    ax = pg.axes(AX, y, AW, AH)
    allf = hf + af
    x0 = np.floor((min(allf) - 7) / 5.0) * 5.0
    x1 = np.ceil((max(allf) + 8) / 5.0) * 5.0
    ytop = np.ceil(max(hg + ag) * 1.08 / 1000.0) * 1000.0
    ax.set_xlim(x0, x1)
    ax.set_ylim(0, ytop)
    l_a, = ax.plot(af, ag, color=BLUE_T, lw=2.2, zorder=3, solid_joinstyle="round", solid_capstyle="round")
    d_a, = ax.plot(af, ag, ls="none", marker="o", ms=7.5, mfc=BLUE_T, mec=SURF, mew=1.6, zorder=4)
    l_h, = ax.plot(hf, hg, color=BLUE, lw=2.2, zorder=5, solid_joinstyle="round", solid_capstyle="round")
    d_h, = ax.plot(hf, hg, ls="none", marker="o", ms=7.5, mfc=BLUE, mec=SURF, mew=1.6, zorder=6)
    labels = []
    for x, f, g in zip(xs, hf, hg):                           # half: below and to the right of the dot (the line climbs)
        labels.append(ax.annotate(f"{x} %", (f, g), xytext=(6, -6), textcoords="offset points", ha="left", va="top",
                                  fontsize=10.5, fontweight="bold", color=INK, zorder=8))
    for x, f, g in zip(xs, af, ag):                           # paper: above and to the left
        labels.append(ax.annotate(f"{x} %", (f, g), xytext=(-6, 5), textcoords="offset points", ha="right", va="bottom",
                                  fontsize=10, color=INK2, zorder=8))
    pg.guarded.append((labels, ax, [l_a, d_a, l_h, d_h]))
    xt = np.arange(np.ceil(x0 / 10.0) * 10.0, x1 + 0.1, 10.0)
    ax.set_xticks(xt)
    ax.set_xticklabels([pct(v, True) for v in xt], fontsize=9)
    yt = np.arange(0, ytop + 1, 5000.0)
    ax.set_yticks(yt)
    ax.set_yticklabels([eur(v, step=1000) for v in yt], fontsize=9)
    ax.grid(axis="both", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0, pad=5)
    ax.spines["left"].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    y += AH + 0.3
    pg.text(AX, y, "Pire baisse de la 1re année (au milieu)", fontsize=10.5, fontweight="bold")
    pg.text(AX + AW, y, "plus de risque →", fontsize=10, color=INK2, ha="right")
    y += lines_h(1, 10.5) + 0.04
    pg.text(AX, y, "depuis le plus haut, versements mis à part", fontsize=9.5, color=INK2)
    y += lines_h(1, 9.5) + 0.32

    # the figures as a table: the main case in black, its companion in grey
    cols = (2.02, 3.02, 3.86, 4.98, 5.74)                    # right edge of each column, inches
    g1, g2 = 1.08, 3.92                                       # left edges of the two groups
    pg.swatch(g1, y + 0.03, BLUE, w=0.3, h=0.14, kind="linedot", lw=2.0)
    pg.text(g1 + 0.38, y, "la moitié du papier", fontsize=10, fontweight="bold")
    pg.swatch(g2, y + 0.03, BLUE_T, w=0.3, h=0.14, kind="linedot", lw=2.0)
    pg.text(g2 + 0.38, y, "comme sur le papier", fontsize=10, color=INK2)
    y += lines_h(1, 10) + 0.05
    heads = ("gain après\n1 an", "une fois\nsur dix", "pire\nbaisse", "gain après\n1 an", "pire\nbaisse")
    pg.text(L, y, "départ", fontsize=9, color=INK2)
    for c, s in zip(cols, heads):
        pg.text(c, y, s, fontsize=9, color=INK2, ha="right", linespacing=1.15)
    y += lines_h(2, 9, 1.15) + 0.06
    ROW = 0.27
    for i, (x, a, b, c, d, e) in enumerate(zip(xs, hg, hp, hf, ag, af)):
        pg.fig.lines.append(Line2D([pg.fx(L), pg.fx(cols[-1])], [pg.fy(y)] * 2, transform=pg.fig.transFigure, color=GRID, lw=0.8))
        wt = "bold" if i == k_cur else "normal"
        yy = y + 0.055
        pg.text(L, yy, f"{x} %", fontsize=10, fontweight=wt)
        vals = (eur(a, True), eur(b, True), pct(c, True), eur(d, True), pct(e, True))
        for j, (col, s) in enumerate(zip(cols, vals)):
            pg.text(col, yy, s, fontsize=10, fontweight=wt, color=INK if j < 3 else INK2, ha="right")
        record(pic, f"table row {x} %", None, " | ".join(vals))
        y += ROW
    pg.fig.lines.append(Line2D([pg.fx(L), pg.fx(cols[-1])], [pg.fy(y)] * 2, transform=pg.fig.transFigure, color=GRID, lw=0.8))
    y += 0.1
    pg.text(L, y, "Gain après 1 an et pire baisse : au milieu (la moitié des trajectoires font moins\n"
                  "bien). « Une fois sur dix » : une trajectoire sur dix fait encore moins bien que ce gain.",
            fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(2, 9, 1.35) + 0.24

    # the worst cases, which the half and paper cases do not show: a robot that does worse than half the paper
    worse = {c: [S(pic, p, c, "gain_after_1_year_eur", "median") for p, _ in PLANS] for c, _ in WORSE}
    assert worse["quarter"] == qg
    # rounded to 100 EUR: the stored figures are whole euros, so a 10 EUR rounding of a figure ending in 5 cannot be
    # settled (covers costs at 5 % is -805, worthless at 10 % is -7,235); none ends in 50, so 100 EUR is unambiguous
    assert all(abs(v) % 100 != 50 for vs in worse.values() for v in vs)
    assert all(a > b for a, b in zip(worse["worthless"], worse["worthless"][1:]))      # the loss grows with X
    assert PAID[12] == 12000.0
    pg.text(L, y, "S'il fait moins bien que la moitié du papier", fontsize=11.5, fontweight="bold")
    y += lines_h(1, 11.5) + 0.04
    pg.text(L, y, f"gain après 1 an, au milieu, pour {th(PAID[12])} € versés (arrondi à 100 €)", fontsize=9.5, color=INK2)
    y += lines_h(1, 9.5) + 0.12
    y = x_table(pg, pic, y, [(lab, [eur(v, True, step=100) for v in worse[c]]) for c, lab in WORSE])
    s = (f"Au quart du papier, le gain baisse au-delà de {xs[k_q]} %. S'il ne vaut rien, plus le\n"
         "départ est haut, plus la perte est grande.")
    pg.text(L, y, s, fontsize=9.5, color=INK, linespacing=1.35)
    record(pic, "worse-case note", None, s.replace("\n", " "))
    y += lines_h(2, 9.5, 1.35) + 0.14
    pg.text(L, y, PAPER_WORDS, fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(2, 9, 1.35) + 0.08
    pg.text(L, y, CAVEATS, fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(3, 9, 1.35) + 0.08
    pg.text(L, y, DETAIL, fontsize=8.6, color=MUTED)
    return y + lines_h(1, 8.6)


# ---------------------------------------------------------------------------------------------------- picture 16
def picture_16(pg):
    pic = PIC16
    names = [f"{x} %" for _, x in PLANS]
    n = len(names)
    k_cur = [p for p, _ in PLANS].index(CURRENT)
    m_h = [S(pic, p, "half", "months_to_10000_eur", "median_month") for p, _ in PLANS]
    m_a = [S(pic, p, "paper", "months_to_10000_eur", "median_month") for p, _ in PLANS]
    b6_h = [S(pic, p, "half", "months_to_10000_eur", "by_month_6_pct") for p, _ in PLANS]
    b6_a = [S(pic, p, "paper", "months_to_10000_eur", "by_month_6_pct") for p, _ in PLANS]
    f_h = [S(pic, p, "half", "fall_of_50_pct_or_more_pct") for p, _ in PLANS]
    f_a = [S(pic, p, "paper", "fall_of_50_pct_or_more_pct") for p, _ in PLANS]
    b9_h = [S(pic, p, "half", "months_to_10000_eur", "by_month_9_pct") for p, _ in PLANS]
    b9_a = [S(pic, p, "paper", "months_to_10000_eur", "by_month_9_pct") for p, _ in PLANS]
    # the footnote's claims, checked: by month 9 every smaller X is there at least as often as 10 %; no account at zero
    assert all(v >= b9_a[k_cur] for v in b9_a) and all(v >= b9_h[k_cur] for v in b9_h)
    zeros = [SUM["summary"][p][c]["reaches_zero_pct"] for p, _ in PLANS for c in SUM["summary"][p]]
    assert len(zeros) == 6 * len(PLANS) and not any(zeros)
    record(pic, "scaled_summary.json summary/S3..S10/<all 6 cases>/reaches_zero_pct", zeros, "aucun compte ne tombe à zéro")
    assert all(m is not None for m in m_h + m_a)

    BX, RM = 0.86, 0.2
    BW = W - RM - BX
    ROW2 = 0.42
    y = 0.2
    pg.text(L, y, f"Combien de temps pour atteindre {th(10000)} €,\net le risque de perdre la moitié", fontsize=15,
            fontweight="bold", linespacing=1.18)
    y += lines_h(2, 15, 1.18) + 0.1
    pg.text(L, y, SIM, fontsize=10.5, color=INK2)
    y += lines_h(1, 10.5) + 0.08
    pg.text(L, y, f"{th(10000)} € = ton solde, versements compris ({th(6000)} € versés au bout de 6 mois).\n"
                  f"À gauche, le risque par trade au départ. 10 % = ton choix actuel.", fontsize=10, color=INK2, linespacing=1.3)
    y += lines_h(2, 10) + 0.14
    for cs, s in (((BLUE, ORANGE), "foncé : s'il fait la moitié du papier"), ((BLUE_T, ORANGE_T), "clair : s'il fait comme sur le papier")):
        pg.swatch(L, y + 0.02, cs[0], w=0.2, h=0.14)
        pg.swatch(L + 0.24, y + 0.02, cs[1], w=0.2, h=0.14)
        pg.text(L + 0.56, y, s, fontsize=10.5, color=INK2)
        y += 0.25
    y += 0.2

    def title(y, t, sub):
        pg.text(L, y, t, fontsize=12, fontweight="bold")
        pg.text(L, y + 0.235, sub, fontsize=9.5, color=INK2)
        return y + 0.235 + lines_h(1, 9.5) + 0.12

    # 1. months to 10,000 EUR
    y = title(y, f"Mois pour atteindre {th(10000)} €", "le mois où la moitié des comptes y sont arrivés")
    ax = pg.axes(BX, y, BW, ROW2 * n)
    xmax = 12.0
    hbar_axes(ax, n, xmax, names, k_cur)
    pair_bars(ax, m_h, m_a, BLUE, BLUE_T, [months_txt(v) for v in m_h], [months_txt(v) for v in m_a], xmax)
    y += ROW2 * n + 0.34

    # 2. side by side: there by the end of month 6 / a fall of 50 % or more in 3 years
    gapw = 0.3
    sw = (BW - gapw) / 2
    xl, xr = BX, BX + sw + gapw
    pg.text(xl, y, f"Atteindre {th(10000)} €\nen 6 mois ou moins", fontsize=11, fontweight="bold", linespacing=1.18)
    pg.text(xr, y, "Perdre la moitié\ndu compte en 3 ans", fontsize=11, fontweight="bold", linespacing=1.18)
    y += lines_h(2, 11, 1.18) + 0.05
    pg.text(xl, y, f"chances sur 100 que ton\nsolde ait atteint {th(10000)} €\nà la fin du 6e mois", fontsize=9, color=INK2,
            linespacing=1.3)
    pg.text(xr, y, "chances sur 100 d'une baisse\nde 50 % ou plus depuis le plus\nhaut, versements mis à part", fontsize=9,
            color=INK2, linespacing=1.3)
    y += lines_h(3, 9, 1.3) + 0.1
    for j, (dark, light, cd, cl, x0) in enumerate(((b6_h, b6_a, BLUE, BLUE_T, xl), (f_h, f_a, ORANGE, ORANGE_T, xr))):
        ax = pg.axes(x0, y, sw, ROW2 * n)
        hbar_axes(ax, n, 100.0, names if j == 0 else [""] * n, k_cur if j == 0 else None)
        pair_bars(ax, dark, light, cd, cl, [pct(v) for v in dark], [pct(v) for v in light], 100.0)
    y += ROW2 * n + 0.32

    # the worst cases, which the half and paper bars do not show: the chance of losing half if the robot does worse
    f_w = {c: [S(pic, p, c, "fall_of_50_pct_or_more_pct") for p, _ in PLANS] for c, _ in WORSE}
    pg.text(L, y, "S'il fait moins bien que la moitié du papier", fontsize=11.5, fontweight="bold")
    y += lines_h(1, 11.5) + 0.04
    pg.text(L, y, "chances sur 100 de perdre la moitié du compte en 3 ans", fontsize=9.5, color=INK2)
    y += lines_h(1, 9.5) + 0.12
    y = x_table(pg, pic, y, [(lab, [pct(v) for v in f_w[c]]) for c, lab in WORSE])
    y += 0.1

    # footer
    s1 = (f"Au bout de 9 mois, chaque palier plus petit a atteint {th(10000)} € au moins aussi\n"
          f"souvent que 10 % : comme sur le papier, {pct(b9_a[0])} à {PLANS[0][1]} % contre {pct(b9_a[k_cur])} à 10 % ;\n"
          f"s'il fait la moitié du papier, {pct(b9_h[0])} à {PLANS[0][1]} % contre {pct(b9_h[k_cur])} à 10 %.")
    pg.text(L, y, s1, fontsize=9.5, color=INK, linespacing=1.35)
    record(pic, "month-9 note", None, s1.replace("\n", " "))
    y += lines_h(3, 9.5, 1.35) + 0.1
    # no account reaches zero, but the worst of the 2,000 paths loses almost everything: say both
    worst = {p: R(pic, p, EDGE["half"], "falls", "fall_from_high_pct", "worst") for p in ("S7", CURRENT)}
    assert all(abs(v * 10 - round(v * 10)) < 1e-9 and round(v * 10) % 10 != 5 and 50 < v < 100 for v in worst.values())
    s2 = (f"Aucun compte simulé ne tombe à zéro, quel que soit le palier. Mais le pire des\n"
          f"{th(GS['paths'])} comptes perd {pct(worst['S7'])} depuis son plus haut à 7 % et {pct(worst[CURRENT])} à 10 %\n"
          f"(versements mis à part, s'il fait la moitié du papier).")
    pg.text(L, y, s2, fontsize=9.5, color=INK, linespacing=1.35)
    record(pic, "zero note", None, s2.replace("\n", " "))
    y += lines_h(3, 9.5, 1.35) + 0.12
    pg.text(L, y, PAPER_WORDS, fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(2, 9, 1.35) + 0.08
    pg.text(L, y, CAVEATS, fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(3, 9, 1.35) + 0.08
    pg.text(L, y, DETAIL, fontsize=8.6, color=MUTED)
    return y + lines_h(1, 8.6)


# ---------------------------------------------------------------------------------------------------- picture 17
H17 = 12                                                  # months shown


def gains_17(pic, plan):
    bal = np.array(R(pic, plan, "0.5", "sample_paths", "balance"), float)
    pin = np.array(R(pic, plan, "0.5", "sample_paths", "paid_in"), float)
    assert bal.shape == pin.shape == (40, GS["months"] + 1)
    assert (pin == np.array(PAID)).all()                  # no stop in these plans: every drawn path is paid every month
    med = np.array(R(pic, plan, "0.5", "gain_percentiles_by_month", "50"), float)
    p10 = np.array(R(pic, plan, "0.5", "gain_percentiles_by_month", "10"), float)
    return (bal - pin)[:, :H17 + 1], med[:H17 + 1], p10[:H17 + 1]


def picture_17(pg):
    pic = PIC17
    plans = ("S7", CURRENT)
    months = np.arange(H17 + 1)
    data = {p: gains_17(pic, p) for p in plans}
    lo = min(min(g.min(), m.min(), q.min()) for g, m, q in data.values())
    hi = max(max(g.max(), m.max(), q.max()) for g, m, q in data.values())
    top = np.ceil(hi * 1.04 / 5000.0) * 5000.0
    bottom = np.floor(lo * 1.25 / 5000.0) * 5000.0
    record(pic, "y range: the 40 sample paths, the middle and one-in-ten lines of S7 and S10, half edge, months 0-12",
           (lo, hi), f"{bottom:.0f} .. {top:.0f} (one scale for both)")
    texts, luck = {}, {}
    for p in plans:
        g12 = R(pic, p, "0.5", "at_12_months", "gain_median")
        p10 = R(pic, p, "0.5", "at_12_months", "gain_p10")
        loss = R(pic, p, "0.5", "at_12_months", "in_loss_pct")
        assert g12 == data[p][1][12] and p10 == data[p][2][12]
        texts[p] = (f"Après 1 an : {eur(g12, True)} au milieu ; une fois sur dix, {eur(p10, True)} ou pire.\n"
                    f"En perte après 1 an : {pct(loss).replace(' %', '')} fois sur 100.")
        # the 40 drawn paths are the first 40 of the 2,000 draws; say how they end the year against all the paths
        luck[p] = (int((data[p][0][:, H17] < 0).sum()), pct(loss).replace(" %", ""))
        record(pic, f"drawn paths of {p} in loss after 1 year (of 40) / all paths per 100", None, f"{luck[p][0]} / {luck[p][1]}")

    PX, PR = 1.0, 0.3
    PW, AH = W - PX - PR, 2.55
    y = 0.2
    pg.text(L, y, "Ton gain la 1re année :\ndépart à 7 % ou à 10 %", fontsize=15, fontweight="bold", linespacing=1.18)
    y += lines_h(2, 15, 1.18) + 0.1
    pg.text(L, y, "Si le robot fait la moitié du papier", fontsize=13.5, fontweight="bold")
    y += lines_h(1, 13.5) + 0.07
    pg.text(L, y, SIM, fontsize=10.5, color=INK2)
    y += lines_h(1, 10.5) + 0.08
    pg.text(L, y, f"Ton gain = ton solde moins tout ce que tu as versé ({th(1000)} € par mois).\n"
                  f"Les deux cas jouent les mêmes 40 tirages de trades, sur la même échelle.\n"
                  f"Les paliers se lisent sur le plus grand des deux : ton solde ou l'argent versé.", fontsize=10, color=INK2,
            linespacing=1.3)
    y += lines_h(3, 10) + 0.14
    DASH = (0, (4, 2.5))
    legend = ((BLUE, 2.6, 1.0, "-", "la trajectoire du milieu (la moitié font moins bien)"),
              (ORANGE, 1.8, 1.0, DASH, "une fois sur dix, ton gain est sous cette ligne"),
              (BLUE, 0.9, 0.6, "-", f"40 trajectoires possibles, parmi les {th(2000)} simulées"))
    for c, lw, a, ls, s in legend:
        pg.swatch(L, y + 0.035, c, w=0.36, kind="line", lw=lw, alpha=a, ls=ls)
        pg.text(L + 0.48, y, s, fontsize=10, color=INK2)
        y += 0.23
    y += 0.16

    for p in plans:
        rp = SUM["plans"][p]["risk_pct"]
        record(pic, f"scaled_summary.json plans/{p}/risk_pct", rp, " / ".join(risk_txt(v) for v in rp))
        head = f"Départ à {risk_txt(rp[0])} par trade" + ("  (ton choix actuel)" if p == CURRENT else "")
        pg.text(L, y, head, fontsize=12.5, fontweight="bold")
        y += 0.25
        pg.text(L, y, f"puis {risk_txt(rp[1])} dès {th(3000)} €, {risk_txt(rp[2])} dès {th(10000)} €, "
                      f"{risk_txt(rp[3])} dès {th(20000)} €", fontsize=9.5, color=INK2)
        y += lines_h(1, 9.5) + 0.02
        pg.text(L, y, texts[p], fontsize=9.5, color=INK, linespacing=1.32)
        record(pic, f"panel text {p}", None, texts[p].replace("\n", " "))
        y += lines_h(2, 9.5, 1.32) + 0.22
        gain, med, q10 = data[p]
        ax = pg.axes(PX, y, PW, AH)
        ax.axhspan(bottom, 0, color=ORANGE_T, alpha=0.13, lw=0, zorder=0)
        for k in range(len(gain)):
            ax.plot(months, gain[k], color=BLUE, lw=0.6, alpha=0.3, zorder=2, solid_joinstyle="round")
        ax.axhline(0, color=INK2, lw=1.0, zorder=3)
        ax.plot(months, q10, color=ORANGE, lw=1.8, ls=DASH, zorder=4, dash_capstyle="butt", dash_joinstyle="round")
        record(pic, f"growth_scaled.json resampled/{p}/0.5/gain_percentiles_by_month/10 [0..12] (dashed line)",
               [float(v) for v in q10], None)
        ax.plot(months, med, color=BLUE, lw=2.6, zorder=5, solid_capstyle="round", solid_joinstyle="round")
        up = med[-1] >= 0
        ax.annotate(eur(med[-1], True), (months[-1], med[-1]), xytext=(-2, 7 if up else -7), textcoords="offset points",
                    ha="right", va="bottom" if up else "top", fontsize=10.5, fontweight="bold", color=INK, zorder=7,
                    bbox=dict(boxstyle="round,pad=0.18", fc=SURF, ec="none", alpha=0.85))
        record(pic, f"growth_scaled.json resampled/{p}/0.5/gain_percentiles_by_month/50 [12]", med[-1], eur(med[-1], True))
        ax.text(0.15, -(top - bottom) * 0.03, "perte", fontsize=8.5, color=INK2, va="top", ha="left", zorder=7)
        ax.set_xlim(0, months[-1])
        ax.set_ylim(bottom, top)
        ax.set_xticks([0, 3, 6, 9, 12])
        ax.set_xticklabels(["départ", "3 mois", "6 mois", "9 mois", "1 an"], fontsize=9)
        tl = ax.get_xticklabels()
        tl[0].set_ha("left")
        tl[-1].set_ha("right")
        yt = np.arange(bottom, top + 1, 10000.0)
        ax.set_yticks(yt)
        ax.set_yticklabels([eur(v, step=1000) if v else "0 €" for v in yt], fontsize=8.5)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        y += AH + 0.27 + 0.3

    y -= 0.14
    (n7, l7), (n10, l10) = luck["S7"], luck[CURRENT]
    s = (f"Les 40 trajectoires dessinées, prises au hasard, finissent l'année mieux que\n"
         f"l'ensemble : en perte après 1 an, {n7} sur 40 à 7 % et {n10} sur 40 à 10 %,\n"
         f"contre {l7} et {l10} sur 100 sur les {th(2000)} trajectoires.")
    pg.text(L, y, s, fontsize=9.5, color=INK, linespacing=1.35)
    record(pic, "drawn-paths note", None, s.replace("\n", " "))
    y += lines_h(3, 9.5, 1.35) + 0.1
    pg.text(L, y, f"La trajectoire du milieu et la ligne « une fois sur dix » relient, mois par mois,\n"
                  f"les chiffres des {th(2000)} trajectoires : aucun compte ne les suit exactement.", fontsize=9,
            color=INK2, linespacing=1.35)
    y += lines_h(2, 9, 1.35) + 0.08
    pg.text(L, y, PAPER_WORDS, fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(2, 9, 1.35) + 0.08
    pg.text(L, y, CAVEATS, fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(3, 9, 1.35) + 0.08
    pg.text(L, y, DETAIL, fontsize=8.6, color=MUTED)
    return y + lines_h(1, 8.6)


# ---------------------------------------------------------------------------------------------------- main
def main():
    draw(picture_15, PIC15)
    draw(picture_16, PIC16)
    draw(picture_17, PIC17)
    print("\nfigures used, with their source key:")
    for pic, key, v, t in SHOWN:
        if key.endswith(("sample_paths/balance", "sample_paths/paid_in", "gain_percentiles_by_month/50", "gain_percentiles_by_month/10")):
            continue
        print(f"  {pic:28s} {key:92s} {'' if v is None else str(v):>12s}  {t or ''}")


if __name__ == "__main__":
    main()
