"""Picture for the user (French): the gain per unit of swing today, in the best case of everything still being tested,
and what "double every month with falls under 20 %" would need. Figures: the ten sleeves' weekly Sharpe on 2022-2025
(2.02, judge of round 4, results/r2/round4_ideas.json), the in-sample multipliers of what still waits for a look
(K1+K2+K3 x1.123, Addendum I outcome; all five round-4 rules passing x1.12, judge), and the x4.4 gap (Addendum I outcome,
x2/x2b diagnostics).

    python3 r2/tracks/stake/gap_chart.py      (from lab/)
"""
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
OUT = os.path.join(LAB, "results", "r2", "round4", "13_ce_qui_manque.png")
SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, BLUE_T, DARK = "#2a78d6", "#9ec5f4", "#52514e"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK, "figure.facecolor": SURF, "savefig.facecolor": SURF})

TODAY = 2.02
BEST = TODAY * 1.123 * 1.12
NEED = TODAY * 4.4


def fr(v):
    return f"{v:.1f}".replace(".", ",")


def main():
    fig = plt.figure(figsize=(9, 6.2), dpi=170)
    fig.text(0.05, 0.93, "Ce qu'il manque pour doubler chaque mois", fontsize=19, fontweight="bold")
    fig.text(0.05, 0.875, "Gain pour une même secousse du compte. Plus la barre est longue, plus le compte\npeut monter vite sans grosses baisses.",
             fontsize=11, color=INK2, va="top")
    ax = fig.add_axes([0.05, 0.17, 0.90, 0.58]); ax.set_xlim(0, 10.2); ax.set_ylim(3.2, -0.4); ax.axis("off")
    rows = [(TODAY, "Aujourd'hui : les 10 règles (2022 à 2025)", BLUE, f"{fr(TODAY)}"),
            (BEST, "Si tout ce qui reste à tester réussit", BLUE_T, f"{fr(BEST)}"),
            (NEED, "Ce qu'il faudrait : ×2 par mois, baisses sous 20 %", DARK, f"{fr(NEED)}  (×4,4)")]
    for i, (v, lab, c, txt) in enumerate(rows):
        y = i * 1.05
        ax.text(0, y - 0.05, lab, fontsize=12, va="bottom", color=INK)
        ax.add_patch(Rectangle((0, y + 0.05), v, 0.42, fc=c, ec="none"))
        ax.text(v + 0.12, y + 0.26, txt, fontsize=14, fontweight="bold", va="center", color=INK)
    fig.text(0.05, 0.095, "« Si tout réussit » : les 3 ajouts en attente du test final et les 5 nouvelles règles en test, tous validés.",
             fontsize=9.6, color=INK2)
    fig.text(0.05, 0.068, "Chance estimée qu'au moins une des 5 nouvelles règles passe le test final : environ 1 sur 6.", fontsize=9.6, color=INK2)
    fig.text(0.05, 0.025, "Gain par secousse = rapport gain/variation des semaines (Sharpe annualisé). Simulation, aucun trade réel.", fontsize=8.3, color=MUTED)
    fig.savefig(OUT)
    print(OUT, round(BEST, 2), round(NEED, 2))


if __name__ == "__main__":
    main()
