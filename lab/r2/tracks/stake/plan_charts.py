"""Pictures for the user (French, phone width) drawn after the independent review of the sixth clarification
(results/r2/stake/growth_sixth_review.json: critique -> picture_defects, left_out, recommendation_assessment) and the
outcome written in PROTOCOL_V3, Addendum G: F1S (a start at 1 %) is the advised plan, F2S (2 %) the alternative.

    python3 r2/tracks/stake/plan_charts.py      (from lab/)

Reads results/r2/stake/growth.json only (the engine is not run again, no trade or price is read). Writes into
results/r2/stake/images/:
    7_echelle_des_departs.png    the ladder 0.5 / 1 / 2 / 3 / 5 % at half edge (replaces the old picture 7)
    8_compte_plan_conseille.png  the robot's GAIN with the 1 % start, four cases on one scale
    9_risque_plan_conseille.png  the 1 % start's risk per trade, what its thresholds read, when the stop exists
    8b_compte_depart_2.png       the same as 8 for the 2 % start
    9b_risque_depart_2.png       the same as 9 for the 2 % start
Every figure printed on a picture is read from growth.json here and listed on stdout with its key.
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
G = json.load(open(os.path.join(LAB, "results", "r2", "stake", "growth.json")))
R = G["resampled"]
IMG = os.path.join(LAB, "results", "r2", "stake", "images")

# the colours and fonts of growth_charts.py
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_T, ORANGE_T, AQUA_T = "#9ec5f4", "#f6b99f", "#8fd9bd"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
NNBSP, MINUS = " ", "−"
W, DPI = 6.0, 200
L = 0.28                                                 # left margin of the text, inches

LADDER = (("A05S", "0,5 %"), ("F1S", "1 %"), ("F2S", "2 %"), ("F3S", "3 %"), ("FS", "5 %"))
ADVISED, ALTERNATIVE = "F1S", "F2S"
HALF, PAPER, COSTS, WORTHLESS = "0.5", "1.0", "0.0", "-0.5"
CASES = ((PAPER, "Si le robot fait comme sur le papier"), (HALF, "S'il fait la moitié du papier"),
         (COSTS, "S'il couvre juste ses frais"), (WORTHLESS, "S'il ne vaut rien"))
assert [p for p, _ in LADDER] == G["ladder_of_starts"]
SIM = "Simulation sur les trades de 2022 à 2025, aucun trade réel."
HANDS = "Le robot actuel ne sait pas encore faire seul ces paliers ni cet arrêt."     # as in picture 12 (hands 1.11)
DETAIL = "2 000 trajectoires de 3 ans tirées des trades de 2022 à 2025, 1 000 € versés par mois."
assert G["paths"] == 2000 and G["months"] == 36 and G["payment_eur"] == 1000.0 and G["period"] == ["2022-01-01", "2026-01-01"]

SHOWN = []      # (picture, key in growth.json, value read, text printed)


def get(pic, *keys):
    """A value of growth.json["resampled"], recorded with its key for the report."""
    v = R
    for k in keys:
        v = v[k]
    SHOWN.append((pic, "resampled/" + "/".join(keys), v, None))
    return v


def note(pic, key, v, text):
    SHOWN.append((pic, key, v, text))


# ---------------------------------------------------------------------------------------------------- formatting
def half_up(v, step=1):
    """Rounded to the nearest multiple of `step`, halves away from zero (2.5 -> 3, 40.5 -> 41, 1,245 -> 1,250)."""
    q = (Decimal(repr(float(v))) / Decimal(step)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return int(q) * step


def eur(v, sign=False, step=10):
    """Euros rounded to `step` (10 EUR by default), narrow no-break space between thousands, ' €'."""
    r = half_up(v, step)
    s = f"{abs(r):,}".replace(",", NNBSP) + " €"
    if r < 0:
        return MINUS + s
    return ("+" + s) if (sign and r > 0) else s


def pct(v, minus=False):
    """A percentage: whole numbers rounded half up; one decimal below 1 so that a small risk is not shown as 0."""
    v = float(v)
    if v == 0:
        s = "0"
    elif abs(v) < 1:
        s = str(Decimal(repr(abs(v))).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)).replace(".", ",")
    else:
        s = str(half_up(abs(v)))
    return (MINUS if minus and v != 0 else "") + s + " %"


def sur100(v):
    return pct(v).replace(" %", " fois sur 100")


def risk_txt(v):
    return (f"{v:g}".replace(".", ",")) + " %"


def mix(c, a):
    """The opaque colour of `c` laid at strength a over the surface."""
    c1, c0 = matplotlib.colors.to_rgb(c), matplotlib.colors.to_rgb(SURF)
    return tuple(a * x + (1 - a) * y for x, y in zip(c1, c0))


# ---------------------------------------------------------------------------------------------------- page layout
class Page:
    """Positions in inches from the top-left corner of a 6-inch-wide picture."""

    def __init__(self, h):
        self.h = h
        self.fig = plt.figure(figsize=(W, h), dpi=DPI)

    def fx(self, x):
        return x / W

    def fy(self, y):
        return 1.0 - y / self.h

    def text(self, x, y, s, **kw):
        kw.setdefault("va", "top")
        return self.fig.text(self.fx(x), self.fy(y), s, **kw)

    def axes(self, x, y, w, h):
        return self.fig.add_axes([self.fx(x), self.fy(y + h), w / W, h / self.h])

    def swatch(self, x, y, color, w=0.22, h=0.13, kind="patch", lw=2.6, ls="-", alpha=1.0):
        """A legend mark whose top-left corner is at (x, y) inches."""
        if kind == "patch":
            self.fig.patches.append(Rectangle((self.fx(x), self.fy(y + h)), w / W, h / self.h, transform=self.fig.transFigure,
                                              color=color, lw=0, alpha=alpha))
        elif kind == "line":
            self.fig.lines.append(Line2D([self.fx(x), self.fx(x + w)], [self.fy(y + h / 2)] * 2, transform=self.fig.transFigure,
                                         color=color, lw=lw, ls=ls, alpha=alpha, solid_capstyle="butt"))
        else:                                                    # a dot
            self.fig.lines.append(Line2D([self.fx(x + w / 2)], [self.fy(y + h / 2)], transform=self.fig.transFigure, marker="o",
                                         ms=6.5, color=color, mec=SURF, mew=1.0, ls="none"))

    def check(self, name):
        """Every text inside the picture, and no two texts overlapping (a tolerance of half a point)."""
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
        assert not bad, f"{name}: " + "; ".join(bad)

    def save(self, name):
        self.check(name)
        path = os.path.join(IMG, name)
        self.fig.savefig(path, dpi=DPI)
        plt.close(self.fig)
        print("written", path)
        return path


def lines_h(n, size, spacing=1.3):
    """Height in inches of n lines of text at `size` points."""
    return n * size * spacing / 72.0


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


def advice_band(ax, k, left_in, right_in):
    """The tint behind the advised row, from `left_in` inches left of the axes to `right_in` inches right of it."""
    wa = ax.get_position().width * W
    ax.axhspan(k - 0.5, k + 0.5, xmin=-left_in / wa, xmax=1 + right_in / wa, color=AQUA_T, alpha=0.38, lw=0, zorder=0, clip_on=False)


# ---------------------------------------------------------------------------------------------------- picture 7
def qualifies(p):
    """The rule fixed before the run (sixth clarification): a fall of 50 % or more in at most 1 path in 20, on paper and at half edge."""
    return all(R[p][f]["shares_of_paths_pct"]["fall_of_50_pct_or_more"] <= 5.0 for f in (PAPER, HALF))


def rule_winner():
    """Among the qualifying plans, the highest median gain after 12 months at half edge (no tie-break)."""
    ok = [p for p, _ in LADDER if qualifies(p)]
    return max(ok, key=lambda p: R[p][HALF]["at_12_months"]["gain_median"])


def stop_words(plans):
    """The stop as growth.py codes it (engine: `ref = max(ref + payment, balance after it)`, stop when the closed balance
    <= ref x (1 - kill), checked only once `paid >= kill_arm`): ref = money paid in + the best gain seen at a payment."""
    arm = {G["stopped"][p]["armed_once_paid_in"] for p in plans if p != "A05S"}
    kill = {G["stopped"][p]["stop_at_fall_of_reference"] for p in plans}
    assert len(arm) == 1 and len(kill) == 1
    arm, kill = arm.pop(), kill.pop()
    return arm, kill, int(round(arm / G["payment_eur"]))


def ladder():
    pic = "7_echelle_des_departs.png"
    plans = [p for p, _ in LADDER]
    names = [n for _, n in LADDER]
    n = len(plans)
    k_adv = plans.index(ADVISED)
    winner = rule_winner()
    assert winner == "F3S", winner                       # as PROTOCOL_V3 reports; the footer says it
    g12 = [get(pic, p, HALF, "at_12_months", "gain_median") for p in plans]
    g36 = [get(pic, p, HALF, "at_36_months", "gain_median") for p in plans]
    paid36 = {get(pic, p, HALF, "at_36_months", "paid_in_median") for p in plans}
    assert len(paid36) == 1
    paid36 = paid36.pop()
    f_med = [get(pic, p, HALF, "falls", "fall_first_52_weeks_pct", "median") for p in plans]
    f_p90 = [get(pic, p, HALF, "falls", "fall_first_52_weeks_pct", "p90") for p in plans]
    e_med = [get(pic, p, HALF, "falls", "fall_first_52_weeks_eur", "median") for p in plans]
    e_p90 = [get(pic, p, HALF, "falls", "fall_first_52_weeks_eur", "p90") for p in plans]
    half50 = [get(pic, p, HALF, "shares_of_paths_pct", "fall_of_50_pct_or_more") for p in plans]
    zero50 = [get(pic, p, WORTHLESS, "shares_of_paths_pct", "fall_of_50_pct_or_more") for p in plans]
    gap = R[winner][HALF]["at_12_months"]["gain_median"] - R[ALTERNATIVE][HALF]["at_12_months"]["gain_median"]
    note(pic, f"resampled/{winner}/0.5/at_12_months/gain_median - resampled/{ALTERNATIVE}/0.5/at_12_months/gain_median", gap, f"{gap:.0f} €")
    arm, kill, nth = stop_words(plans)
    assert G["stopped"]["A05S"]["armed_once_paid_in"] == 0
    floor_pct = {G["schedules"][G["stopped"][p]["plan"]]["risk_pct"][-1] for p in plans}
    assert len(floor_pct) == 1
    floor_pct = floor_pct.pop()

    BX, RM = 0.86, 0.2
    BW = W - RM - BX
    BL, BR = BX - L + 0.04, RM - L + 0.04                 # the advice band runs from the left text margin to the right one
    ROW, ROW2 = 0.27, 0.42
    pg = Page(14.1)
    y = 0.2
    pg.text(L, y, "Plus le départ est rapide,\nplus le début secoue", fontsize=15, fontweight="bold", linespacing=1.18)
    y += lines_h(2, 15, 1.18) + 0.12
    pg.text(L, y, "Si le robot fait la moitié du papier", fontsize=13.5, fontweight="bold")
    y += lines_h(1, 13.5) + 0.07
    pg.text(L, y, SIM, fontsize=10.5, color=INK2)
    y += lines_h(1, 10.5) + 0.12
    pg.swatch(L, y + 0.01, AQUA_T, w=0.32, h=0.19, alpha=0.38)     # as the band behind the advised row
    pg.text(L + 0.4, y, f"{names[k_adv]} = mon conseil : les baisses restent proches\nde ce que tu acceptes", fontsize=10.5, color=INK)
    y += lines_h(2, 10.5) + 0.1
    pg.text(L, y, f"À gauche, le risque par trade au départ ; il baisse ensuite\njusqu'à {risk_txt(floor_pct)} pour tous.", fontsize=10, color=INK2)
    y += lines_h(2, 10) + 0.28

    def title(y, t, sub):
        pg.text(L, y, t, fontsize=12, fontweight="bold")
        pg.text(L, y + 0.235, sub, fontsize=9.5, color=INK2)
        return y + 0.235 + lines_h(1, 9.5) + 0.12

    # 1. gain after one year
    y = title(y, "Gain après 1 an", "la trajectoire du milieu : la moitié font moins bien")
    ax = pg.axes(BX, y, BW, ROW * n)
    xmax = max(g12) * 1.3
    hbar_axes(ax, n, xmax, names, k_adv)
    ax.barh(range(n), g12, height=0.62, color=BLUE, lw=0, zorder=3)
    txt = [eur(v, True) + (" *" if p == winner else "") for v, p in zip(g12, plans)]
    labs = bar_labels(ax, range(n), g12, txt, xmax)
    fit_labels(ax, labs, xmax)
    advice_band(ax, k_adv, BL, BR)
    y += ROW * n + 0.3

    # 2. deepest fall of the first year
    y = title(y, "Pire baisse de la 1re année", "depuis le plus haut, versements mis à part")
    pg.swatch(BX, y + 0.02, ORANGE, w=0.2, h=0.13)
    pg.text(BX + 0.27, y, "au milieu (la moitié font pire)", fontsize=9.5, color=INK2)
    pg.swatch(BX + 2.6, y + 0.02, ORANGE_T, w=0.2, h=0.13)
    pg.text(BX + 2.87, y, "une fois sur dix", fontsize=9.5, color=INK2)
    y += lines_h(1, 9.5) + 0.1
    ax = pg.axes(BX, y, BW, ROW2 * n)
    xmax = max(f_p90) * 1.6
    hbar_axes(ax, n, xmax, names, k_adv)
    hb = 0.36
    ya, yb = np.arange(n) - hb / 2 - 0.012, np.arange(n) + hb / 2 + 0.012       # a 2 px surface gap between the pair
    ax.barh(ya, f_med, height=hb, color=ORANGE, lw=0, zorder=3)
    ax.barh(yb, f_p90, height=hb, color=ORANGE_T, lw=0, zorder=3)
    t1 = [f"{pct(v, True)}  ({eur(e)})" for v, e in zip(f_med, e_med)]
    t2 = [f"{pct(v, True)}  ({eur(e)})" for v, e in zip(f_p90, e_p90)]
    labs = bar_labels(ax, ya, f_med, t1, xmax, size=9.5) + bar_labels(ax, yb, f_p90, t2, xmax, bold=False, size=9.5)
    fit_labels(ax, labs, xmax)
    advice_band(ax, k_adv, BL, BR)
    y += ROW2 * n + 0.3

    # 3. chances of losing half the account in three years, half edge and worthless side by side
    y = title(y, "Perdre la moitié du compte en 3 ans", "une baisse de 50 % ou plus depuis le plus haut, versements mis à part")
    gapw = 0.28
    sw = (BW - gapw) / 2
    pg.text(BX, y, "s'il fait la moitié du papier", fontsize=10.5, fontweight="bold")
    pg.text(BX + sw + gapw, y, "s'il ne vaut rien", fontsize=10.5, fontweight="bold")
    y += lines_h(1, 10.5) + 0.08
    for j, (vals, x0) in enumerate(((half50, BX), (zero50, BX + sw + gapw))):
        ax = pg.axes(x0, y, sw, ROW * n)
        hbar_axes(ax, n, 100.0, names if j == 0 else [""] * n, k_adv if j == 0 else None)
        ax.barh(range(n), vals, height=0.62, color=ORANGE, lw=0, zorder=3)
        labs = bar_labels(ax, range(n), vals, [pct(v) for v in vals], 100.0)
        fit_labels(ax, labs, 100.0)
        advice_band(ax, k_adv, BL if j == 0 else gapw / 2, gapw / 2 if j == 0 else BR)
    y += ROW * n + 0.3

    # 4. gain after three years
    y = title(y, "Gain après 3 ans", f"la trajectoire du milieu ; {eur(paid36)} versés en 3 ans")
    ax = pg.axes(BX, y, BW, ROW * n)
    xmax = max(g36) * 1.3
    hbar_axes(ax, n, xmax, names, k_adv)
    ax.barh(range(n), g36, height=0.62, color=BLUE, lw=0, zorder=3)
    labs = bar_labels(ax, range(n), g36, [eur(v, True) for v in g36], xmax)
    fit_labels(ax, labs, xmax)
    advice_band(ax, k_adv, BL, BR)
    y += ROW * n + 0.32

    # footer
    s1 = (f"* La règle fixée avant le test classait {dict(LADDER)[winner]} premier : {gap:.0f} € de plus que\n"
          f"{dict(LADDER)[ALTERNATIVE]} sur le gain après 1 an. C'est une égalité, dans le bruit de la simulation.")
    pg.text(L, y, s1, fontsize=9, color=INK2, linespacing=1.35)
    y += lines_h(2, 9, 1.35) + 0.08
    s2 = (f"Arrêt de sécurité. Départ à {names[0]} : dès le début. Autres départs : seulement à partir du\n"
          f"{nth}e versement ({eur(arm)} versés). Il arrête alors le robot pour de bon si le solde tombe à\n"
          f"{half_up(100 * (1 - kill))} % de la référence = l'argent versé + le meilleur gain constaté au moment d'un\n"
          f"versement. Il ne limite donc pas les baisses à {MINUS}{half_up(100 * kill)} %.")
    pg.text(L, y, s2, fontsize=9, color=INK2, linespacing=1.35)
    note(pic, "stopped (all five plans)", {p: G["stopped"][p] for p in plans}, s2.replace("\n", " "))
    y += lines_h(4, 9, 1.35) + 0.08
    pg.text(L, y, DETAIL, fontsize=8.6, color=MUTED)
    y += lines_h(1, 8.6) + 0.12
    assert y <= pg.h, y
    return pg.save(pic)


# ---------------------------------------------------------------------------------------------------- pictures 8 / 8b
def stop_points(bal, pin, paid_full):
    """Sample paths stopped by the safety stop: no more payments, the balance frozen. Returns [(path, first frozen month)]."""
    out = []
    for k in range(len(bal)):
        if pin[k, -1] >= paid_full:
            assert (pin[k] == np.array(G["paid_by_month"])).all()        # never stopped: paid every month
            continue
        m = len(bal[k]) - 1
        while m > 0 and bal[k, m - 1] == bal[k, -1] and pin[k, m - 1] == pin[k, -1]:
            m -= 1
        out.append((k, m))
    return out


def gain_scale(plans):
    """One y range for all the cases of both pictures (8 and 8b), every sample path and median line inside it."""
    lo, hi = 0.0, 0.0
    for p in plans:
        for f, _ in CASES:
            if f not in R[p]:
                continue
            r = R[p][f]
            gain = np.array(r["sample_paths"]["balance"]) - np.array(r["sample_paths"]["paid_in"])
            med = np.array(r["gain_percentiles_by_month"]["50"])
            lo, hi = min(lo, gain.min(), med.min()), max(hi, gain.max(), med.max())
    top = np.ceil(hi * 1.03 / 10000.0) * 10000.0
    bottom = -20000.0
    assert lo > bottom * 0.55, (lo, bottom)             # room under the lowest line for its label
    return bottom, top, lo, hi


def gains_picture(plan, pic, title, other):
    months = np.arange(G["months"] + 1)
    paid_full = G["paid_by_month"][-1]
    arm, kill, nth = stop_words((plan,))
    t_arm = nth - 1                                       # payments at months 0, 1, 2, ...: the nth one is made at month n-1
    bottom, top, lo, hi = gain_scale((ADVISED, ALTERNATIVE))
    note(pic, "y range: every sample path and median of F1S and F2S in cases 1.0 / 0.5 / 0.0 / -0.5", (lo, hi), f"{bottom:.0f} .. {top:.0f}")
    cases = [(f, c) for f, c in CASES if f in R[plan]]
    missing = [f for f, _ in CASES if f not in R[plan]]
    if missing:
        print(f"{pic}: case(s) missing from growth.json for {plan}: {missing}")

    PX, PR = 1.0, 0.3
    PW, AH = W - PX - PR, 1.72
    texts = []
    for f, case in cases:
        g36 = get(pic, plan, f, "at_36_months", "gain_median")
        p10 = get(pic, plan, f, "at_36_months", "gain_p10")
        loss = get(pic, plan, f, "at_36_months", "in_loss_pct")
        st = get(pic, plan, f, "stopped", "paths_pct")
        st_m = get(pic, plan, f, "stopped", "median_month")
        paid_med = get(pic, plan, f, "at_36_months", "paid_in_median")
        s = f"Après 3 ans : {eur(g36, True)} au milieu ; une fois sur dix, {eur(p10, True)} ou pire."
        if st >= 50:                     # paid_in_median: over all the paths at month 36 (a stopped robot is no longer paid)
            s += (f"\nEn perte après 3 ans : {sur100(loss)}. Versé en 3 ans : {eur(paid_med)} (au milieu)."
                  f"\nRobot arrêté par la sécurité {sur100(st)}, au bout de {st_m:.0f} mois environ.")   # months since the start
        else:
            s += f"\nEn perte après 3 ans : {sur100(loss)}. Arrêté par la sécurité : {sur100(st)}."
        texts.append(s)
    head = 2.3
    body = sum(0.25 + lines_h(t.count("\n") + 1, 9.5, 1.32) + 0.1 + AH + 0.24 + 0.28 for t in texts)
    pg = Page(head + body + 0.75)
    y = 0.2
    pg.text(L, y, title, fontsize=15, fontweight="bold")
    y += lines_h(1, 15) + 0.08
    pg.text(L, y, "Ton gain = ton solde moins tout ce que tu as versé (1 000 € par mois).", fontsize=10.5, color=INK)
    y += lines_h(1, 10.5) + 0.04
    pg.text(L, y, f"{SIM}\nLes 4 cas sont sur la même échelle, {other}.", fontsize=10.5, color=INK2)
    y += lines_h(2, 10.5) + 0.14
    legend = ((dict(kind="line", lw=2.6), BLUE, 1.0, "la trajectoire du milieu (la moitié font moins bien)"),
              (dict(kind="line", lw=0.9), BLUE, 0.6, "40 trajectoires possibles, parmi les 2 000 simulées"),
              (dict(kind="dot"), ORANGE, 1.0, "robot arrêté par la sécurité : ensuite son trait reste plat"),
              (dict(kind="line", lw=1.0, ls=(0, (1.5, 2.0))), INK2, 1.0, f"{nth}e versement ({eur(arm)} versés) : la sécurité s'arme"))
    for kw, c, a, s in legend:
        pg.swatch(L, y + 0.035, c, w=0.36, alpha=a, **kw)
        pg.text(L + 0.48, y, s, fontsize=10, color=INK2)
        y += 0.23
    y = max(y + 0.12, head)

    for i, ((f, case), s) in enumerate(zip(cases, texts)):
        bal = np.array(get(pic, plan, f, "sample_paths", "balance"))
        pin = np.array(get(pic, plan, f, "sample_paths", "paid_in"))
        gain = bal - pin
        med = np.array(get(pic, plan, f, "gain_percentiles_by_month", "50"))
        stops = stop_points(bal, pin, paid_full)
        note(pic, f"resampled/{plan}/{f}/sample_paths (stopped = paid_in at month 36 < {paid_full:.0f}, then frozen)", len(stops),
             f"{len(stops)} of {len(bal)} drawn paths marked as stopped")
        pg.text(L, y, case, fontsize=12.5, fontweight="bold")
        y += 0.25
        pg.text(L, y, s, fontsize=9.5, color=INK2, linespacing=1.32)
        y += lines_h(s.count("\n") + 1, 9.5, 1.32) + 0.1
        ax = pg.axes(PX, y, PW, AH)
        ax.axhspan(bottom, 0, color=ORANGE_T, alpha=0.13, lw=0, zorder=0)
        for k in range(len(gain)):
            ax.plot(months, gain[k], color=BLUE, lw=0.6, alpha=0.3, zorder=2, solid_joinstyle="round")
        ax.axhline(0, color=INK2, lw=1.0, zorder=3)
        ax.axvline(t_arm, color=INK2, lw=1.0, ls=(0, (1.5, 2.0)), zorder=3)
        ax.plot(months, med, color=BLUE, lw=2.6, zorder=5, solid_capstyle="round", solid_joinstyle="round")
        if stops:
            ax.scatter([m for _, m in stops], [gain[k, m] for k, m in stops], s=20, color=ORANGE, edgecolor=SURF, lw=0.8, zorder=6)
        up = med[-1] >= 0
        ax.annotate(eur(med[-1], True), (months[-1], med[-1]), xytext=(-2, 7 if up else -7), textcoords="offset points",
                    ha="right", va="bottom" if up else "top", fontsize=10.5, fontweight="bold", color=INK, zorder=7,
                    bbox=dict(boxstyle="round,pad=0.18", fc=SURF, ec="none", alpha=0.85))
        note(pic, f"resampled/{plan}/{f}/gain_percentiles_by_month/50 [36]", med[-1], eur(med[-1], True))
        ax.text(0.6, -1500, "perte", fontsize=8.5, color=INK2, va="top", ha="left", zorder=7)
        ax.set_xlim(0, months[-1])
        ax.set_ylim(bottom, top)
        ax.set_xticks([0, 12, 24, 36])
        ax.set_xticklabels(["départ", "1 an", "2 ans", "3 ans"], fontsize=9)
        tl = ax.get_xticklabels()
        tl[0].set_ha("left")
        tl[-1].set_ha("right")
        yt = np.arange(bottom, top + 1, 20000.0)
        ax.set_yticks(yt)
        ax.set_yticklabels([eur(v, step=1000) if v else "0 €" for v in yt], fontsize=8.5)
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        ax.tick_params(length=0)
        ax.spines["left"].set_visible(False)
        ax.spines["bottom"].set_color(AXIS)
        y += AH + 0.24 + 0.28

    y -= 0.12
    pg.text(L, y, "La trajectoire du milieu relie, mois par mois, le gain du milieu des 2 000 trajectoires :\n"
                  "aucun compte ne la suit exactement. Un point est placé au premier mois après l'arrêt.",
            fontsize=8.8, color=INK2, linespacing=1.35)
    y += lines_h(2, 8.8, 1.35) + 0.03
    pg.text(L, y, HANDS, fontsize=8.8, color=INK2)
    y += lines_h(1, 8.8, 1.35) + 0.06
    pg.text(L, y, DETAIL, fontsize=8.6, color=MUTED)
    assert y + lines_h(1, 8.6) <= pg.h, (y, pg.h)
    print(pic, 'content ends at', round(y + lines_h(1, 8.6), 2), 'of', pg.h)
    return pg.save(pic)


# ---------------------------------------------------------------------------------------------------- pictures 9 / 9b
def schedule(plan):
    base = G["stopped"][plan]["plan"]
    assert base in G["keyed_on_max_of_balance_and_paid"]
    s = G["schedules"][base]
    return list(s["thresholds_eur"]), list(s["risk_pct"])


SHADE = {2.0: 0.62, 1.0: 0.34, 0.5: 0.12}               # the higher the risk, the deeper the orange tint
H_MONTHS = 14


def euro_top():
    top = 0.0
    for p in (ADVISED, ALTERNATIVE):
        top = max(top, max(R[p][HALF]["percentiles_by_month"]["90"][:H_MONTHS + 1]))
    return np.ceil(top * 1.08 / 6000.0) * 6000.0


def risk_picture(plan, pic, title):
    thr, rp = schedule(plan)
    arm, kill, nth = stop_words((plan,))
    pay = G["payment_eur"]
    t_arm = nth - 1
    hs = np.arange(H_MONTHS + 1)
    pm = np.array(G["paid_by_month"][:H_MONTHS + 1])
    top_eur = euro_top()
    risk_top = 2.5
    PX, PR = 1.0, 0.3
    PW = W - PX - PR

    pg = Page(10.92)
    y = 0.2
    pg.text(L, y, title, fontsize=15, fontweight="bold", linespacing=1.18)
    y += lines_h(2, 15, 1.18) + 0.1
    pg.text(L, y, SIM, fontsize=10.5, color=INK2)
    y += lines_h(1, 10.5) + 0.25

    # 1. the rule
    pg.text(L, y, "La règle (la même dans tous les cas)", fontsize=12, fontweight="bold")
    y += 0.26
    pg.text(L, y, "Le risque se lit sur le plus grand des deux : ton solde ou l'argent\nque tu as versé. Le pourcentage s'applique ensuite à ton solde.",
            fontsize=10, color=INK2)
    y += lines_h(2, 10) + 0.15
    ax = pg.axes(PX, y, PW, 1.45)
    edges = [0.0] + thr + [top_eur]
    for k, v in enumerate(rp):
        ax.fill_between([edges[k], edges[k + 1]], [v, v], 0, color=mix(ORANGE_T, SHADE[v]), lw=0, zorder=1)
        ax.plot([edges[k], edges[k + 1]], [v, v], color=ORANGE, lw=2.4, zorder=3, solid_capstyle="butt")
        if k + 1 < len(rp):
            ax.plot([edges[k + 1]] * 2, [rp[k + 1], v], color=ORANGE, lw=2.4, zorder=3)
        ax.text((edges[k] + edges[k + 1]) / 2, v + 0.12, risk_txt(v), ha="center", va="bottom", fontsize=11.5, fontweight="bold", color=INK)
    note(pic, f"schedules/{G['stopped'][plan]['plan']}", (thr, rp), " / ".join(risk_txt(v) for v in rp))
    ax.set_xlim(0, top_eur)
    ax.set_ylim(0, risk_top)
    xt = np.arange(0, top_eur + 1, 6000.0)
    ax.set_xticks(xt)
    ax.set_xticklabels([eur(v, step=1000) if v else "0" for v in xt], fontsize=9)
    ax.get_xticklabels()[-1].set_ha("right")
    yt = [0.0, 0.5, 1.0, 2.0]
    ax.set_yticks(yt)
    ax.set_yticklabels(["0"] + [risk_txt(v) for v in yt[1:]], fontsize=9)
    ax.grid(axis="y", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    ax.set_xlabel("le plus grand des deux : ton solde ou l'argent que tu as versé", fontsize=10, color=INK2, labelpad=6)
    ax.set_ylabel("risque maximal\npar trade", fontsize=9.5, color=INK2, labelpad=6)
    y += 1.45 + 0.68

    # 2. in time, half of the paper edge
    pg.text(L, y, "Dans le temps, si le robot fait la moitié du papier", fontsize=12, fontweight="bold")
    y += 0.27
    drops = [(rp[k + 1], int(round(thr[k] / pay))) for k in range(len(thr))]      # (risk, the payment that brings it for good)
    sub = (f"Même si ton compte ne grossit pas, tes versements font baisser\nle risque : {risk_txt(drops[0][0])} au plus tard au "
           f"{drops[0][1]}e versement" + "".join(f", {risk_txt(r_)} au {n_}e" for r_, n_ in drops[1:]) + ".")
    pg.text(L, y, sub, fontsize=10, color=INK2)
    y += lines_h(2, 10) + 0.1
    legend = ((dict(kind="line", lw=2.4), BLUE, 1.0, "ton solde : la trajectoire du milieu (la moitié font moins bien)"),
              (dict(kind="patch", h=0.13), BLUE_T, 0.6, "chaque mois, 8 trajectoires sur 10 sont dans cette bande"),
              (dict(kind="line", lw=1.4), INK2, 1.0, f"l'argent versé : {eur(pay)} par mois (chaque versement remonte le solde)"))
    for kw, c, a, s in legend:
        pg.swatch(L, y + 0.03, c, w=0.34, alpha=a, **kw)
        pg.text(L + 0.45, y, s, fontsize=9.5, color=INK2)
        y += 0.215
    y += 0.1
    AH = 3.05
    ax = pg.axes(PX, y, PW, AH)
    # risk zones in (time, balance): the risk is rp[k] while both the balance and the money paid in are under thr[k]
    ax.add_patch(Rectangle((0, 0), H_MONTHS, top_eur, color=mix(ORANGE_T, SHADE[rp[-1]]), lw=0, zorder=0))
    for k in range(len(thr) - 1, -1, -1):
        t_k = int(round(thr[k] / pay)) - 1                    # the month of the payment that brings the money paid in to thr[k]
        ax.add_patch(Rectangle((0, 0), t_k, thr[k], color=mix(ORANGE_T, SHADE[rp[k]]), lw=0, zorder=0))
        ax.plot([0, t_k, t_k], [thr[k], thr[k], 0], color=ORANGE, lw=1.0, zorder=1)

    def saw(v):
        """Month-end values (taken just before the payment of that month) drawn with the payment's jump: from the value at
        month h-1 plus one payment down or up to the value at month h, then up by one payment."""
        xs, ys = [0.0], [v[0]]
        for h in range(1, len(v)):
            xs += [h, h] if h < len(v) - 1 else [h]
            ys += [v[h], v[h] + pay] if h < len(v) - 1 else [v[h]]
        return np.array(xs, float), np.array(ys, float)

    p10 = np.array(get(pic, plan, HALF, "percentiles_by_month", "10")[:H_MONTHS + 1])
    p50 = np.array(get(pic, plan, HALF, "percentiles_by_month", "50")[:H_MONTHS + 1])
    p90 = np.array(get(pic, plan, HALF, "percentiles_by_month", "90")[:H_MONTHS + 1])
    xs, lo_ = saw(p10)
    _, hi_ = saw(p90)
    _, mid = saw(p50)
    xp, paid_line = saw(pm)                                   # growth.json paid_by_month: flat between payments, +1,000 at each
    assert paid_line[0] == paid_line[1] and (paid_line[2::2] == paid_line[3::2]).all()        # flat between two payments
    ax.fill_between(xs, lo_, hi_, color=BLUE_T, alpha=0.55, lw=0, zorder=2)
    ax.plot(xp, paid_line, color=INK2, lw=1.4, zorder=3)
    ax.plot(xs, mid, color=BLUE, lw=2.4, zorder=4, solid_joinstyle="miter")
    ax.axvline(t_arm, color=INK2, lw=1.0, ls=(0, (1.5, 2.0)), zorder=5)
    ax.text(t_arm - 0.15, top_eur * 0.975, f"{nth}e versement :\nla sécurité s'arme", ha="right", va="top", fontsize=9, color=INK,
            zorder=6, linespacing=1.25)
    for k in range(len(thr)):                                 # where the middle path's risk drops (month ends), for the report
        h_mid = next(int(h) for h in hs if max(p50[h], pm[h]) >= thr[k])
        note(pic, f"resampled/{plan}/0.5/percentiles_by_month/50: first month end with max(balance, paid) >= {thr[k]:.0f}", h_mid,
             "(not printed)")
    lab = dict(fontsize=10, fontweight="bold", color=INK, zorder=6, ha="left", va="center")
    if len(thr) == 1:
        ax.text(0.3, thr[0] * 0.8, f"{risk_txt(rp[0])} par trade", **lab)
    else:
        ax.text(0.1, thr[0] - 150, f"{risk_txt(rp[0])}\npar trade", fontsize=9.5, fontweight="bold", color=INK, zorder=6, ha="left",
                va="top", linespacing=1.15)
        ax.text(0.3, (thr[0] + thr[1]) / 2 + 900, f"{risk_txt(rp[1])} par trade", **lab)
    ax.text(0.3, thr[-1] + (top_eur - thr[-1]) * 0.75, f"{risk_txt(rp[-1])} par trade", **lab)
    ax.text(t_arm + 0.22, thr[-1] * 0.42, f"{risk_txt(rp[-1])}\npour de bon", fontsize=9.5, fontweight="bold", color=INK, zorder=6,
            ha="left", va="center", linespacing=1.2)
    # the risk can go back up while the money paid in is under a threshold
    if len(thr) == 1:
        msg = f"Avant le {nth}e versement, un solde qui\nrepasse sous {eur(thr[0], step=1000)} remet le risque\nà {risk_txt(rp[0])}."
        targets = [(t_arm - 1.6, thr[0])]
    else:
        n1 = int(round(thr[0] / pay))
        msg = (f"Le risque peut remonter : avant le {n1}e\nversement, à {risk_txt(rp[0])} si le solde repasse sous\n"
               f"{eur(thr[0], step=1000)} ; avant le {nth}e, à {risk_txt(rp[1])} sous {eur(thr[1], step=1000)}.")
        targets = [(n1 - 1 - 0.8, thr[0]), (t_arm - 1.6, thr[1])]
    ty = thr[-1] + (top_eur - thr[-1]) * 0.4
    box = ax.text(0.3, ty, msg, fontsize=9, color=INK, zorder=7, ha="left", va="center", linespacing=1.28,
                  bbox=dict(boxstyle="round,pad=0.3", fc=SURF, ec="none", alpha=0.92))
    pg.fig.canvas.draw()
    bb = box.get_bbox_patch().get_window_extent(pg.fig.canvas.get_renderer()).transformed(ax.transData.inverted())
    for (x_, y_) in targets:
        ax.annotate("", xy=(x_, y_), xytext=(min(x_ - 0.4, bb.x1 - 0.5), bb.y0), zorder=6,
                    arrowprops=dict(arrowstyle="-|>", color=INK, lw=0.9, shrinkA=0, shrinkB=1.5, mutation_scale=8))
    ax.set_xlim(0, H_MONTHS)
    ax.set_ylim(0, top_eur)
    ax.set_xticks([0, 3, 6, 9, 12])
    ax.set_xticklabels(["départ", "3 mois", "6 mois", "9 mois", "1 an"], fontsize=9)
    ax.get_xticklabels()[0].set_ha("left")
    yt = np.arange(0, top_eur + 1, 6000.0)
    ax.set_yticks(yt)
    ax.set_yticklabels([eur(v, step=1000) if v else "0 €" for v in yt], fontsize=9)
    ax.tick_params(length=0)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    y += AH + 0.45

    # 3. the stop, in words
    stop = (f"L'arrêt de sécurité n'existe qu'à partir du {nth}e versement ({eur(arm)} versés).\n"
            f"Ensuite, le robot s'arrête pour de bon, et tu ne verses plus rien, si ton\n"
            f"solde tombe à {half_up(100 * (1 - kill))} % de la référence. La référence = tout l'argent versé\n"
            f"+ le meilleur gain constaté au moment d'un versement. Ce n'est donc pas\n"
            f"{MINUS}{half_up(100 * kill)} % depuis le plus haut. Avant le {nth}e versement, rien n'arrête le robot.")
    note(pic, f"stopped/{plan}", G["stopped"][plan], stop.replace("\n", " "))
    pg.text(L, y, stop, fontsize=10, color=INK, linespacing=1.36)
    y += lines_h(5, 10, 1.36) + 0.12
    pg.text(L, y, "Le risque affiché est un maximum : la règle de la semaine peut le réduire.\n" + HANDS, fontsize=8.8, color=INK2,
            linespacing=1.35)
    y += lines_h(2, 8.8, 1.35) + 0.06
    pg.text(L, y, DETAIL, fontsize=8.6, color=MUTED)
    assert y + lines_h(1, 8.6) <= pg.h, (y, pg.h)
    print(pic, 'content ends at', round(y + lines_h(1, 8.6), 2), 'of', pg.h)
    return pg.save(pic)


# ---------------------------------------------------------------------------------------------------- main
def main():
    a, b = dict(LADDER)[ADVISED], dict(LADDER)[ALTERNATIVE]
    ladder()
    gains_picture(ADVISED, "8_compte_plan_conseille.png", f"Départ à {a} (mon conseil) : ton gain", f"comme pour le départ à {b}")
    risk_picture(ADVISED, "9_risque_plan_conseille.png", f"Départ à {a} (mon conseil) :\ncombien tu risques par trade")
    gains_picture(ALTERNATIVE, "8b_compte_depart_2.png", f"Départ à {b} (l'autre choix) : ton gain", f"comme pour le départ à {a}")
    risk_picture(ALTERNATIVE, "9b_risque_depart_2.png", f"Départ à {b} (l'autre choix) :\ncombien tu risques par trade")
    print("\nfigures used, with their key in growth.json:")
    for pic, key, v, t in SHOWN:
        if key.endswith(("sample_paths/balance", "sample_paths/paid_in")) or (key.endswith(("/10", "/50", "/90")) and "percentiles" in key):
            continue
        print(f"  {pic:30s} {key:95s} {str(v):>14s}  {t or ''}")


if __name__ == "__main__":
    main()
