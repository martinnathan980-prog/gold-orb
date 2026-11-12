"""Picture for the user (French): start at 1 % (F1S) or at 2 % (F2S) per trade, side by side, from growth.json
(2,000 resampled 36-month paths of the 2022-2025 validation trades). Drawn after the independent review of the sixth
clarification (results/r2/stake/growth_sixth_review.json), which asked that both be put to the user with the case of
each figure said.

    python3 r2/tracks/stake/start_choice_chart.py      (from lab/)
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", ".."))
G = json.load(open(os.path.join(LAB, "results", "r2", "stake", "growth.json")))["resampled"]
OUT = os.path.join(LAB, "results", "r2", "stake", "images", "12_depart_1_ou_2.png")

SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, TINT = "#2a78d6", "#e6f0fb"
plt.rcParams.update({"font.family": "DejaVu Sans", "text.color": INK, "figure.facecolor": SURF, "savefig.facecolor": SURF})


def eur(v, sign=True):
    s = f"{abs(v):,.0f}".replace(",", " ")
    return (("+" if v >= 0 else "−") if sign else "") + s + " €"


def r100(v):
    """Round to the nearest hundred euros for display (the medians are known to about 70-100 EUR)."""
    return round(v / 100.0) * 100


def pct(v):
    return f"{v:.0f} %".replace("-", "−")


def row_values():
    a, b = G["F1S"], G["F2S"]
    def g(p, sc, k):
        return p[sc][k]
    rows = []
    rows.append(("Gain après 1 an", "si le robot fait comme sur le papier",
                 eur(r100(g(a, "1.0", "at_12_months")["gain_median"])), eur(r100(g(b, "1.0", "at_12_months")["gain_median"])), 1))
    rows.append(("Gain après 1 an", "s'il fait la moitié du papier",
                 eur(r100(g(a, "0.5", "at_12_months")["gain_median"])), eur(r100(g(b, "0.5", "at_12_months")["gain_median"])), 1))
    rows.append(("Gain après 3 ans", "s'il fait la moitié du papier",
                 eur(r100(g(a, "0.5", "at_36_months")["gain_median"])), eur(r100(g(b, "0.5", "at_36_months")["gain_median"])), 1))
    fa, fb = a["0.5"]["falls"]["fall_first_52_weeks_pct"], b["0.5"]["falls"]["fall_first_52_weeks_pct"]
    ea, eb = a["0.5"]["falls"]["fall_first_52_weeks_eur"], b["0.5"]["falls"]["fall_first_52_weeks_eur"]
    rows.append(("Pire baisse de la 1re année", "le plus souvent (moitié du papier)",
                 f"−{fa['median']:.0f} %  ({eur(r100(ea['median']), False)})", f"−{fb['median']:.0f} %  ({eur(r100(eb['median']), False)})", 0))
    rows.append(("Pire baisse de la 1re année", "une fois sur dix (moitié du papier)",
                 f"−{fa['p90']:.0f} %  ({eur(r100(ea['p90']), False)})", f"−{fb['p90']:.0f} %  ({eur(r100(eb['p90']), False)})", 0))
    rows.append(("Une baisse de 30 % ou plus", "en 3 ans (moitié du papier)",
                 f"{a['0.5']['shares_of_paths_pct']['fall_of_30_pct_or_more']:.0f} fois sur 100",
                 f"{b['0.5']['shares_of_paths_pct']['fall_of_30_pct_or_more']:.0f} fois sur 100", 0))
    rows.append(("Perdre la moitié du compte", "si le robot couvre juste ses frais",
                 f"{a['0.0']['shares_of_paths_pct']['fall_of_50_pct_or_more']:.0f} fois sur 100",
                 f"{b['0.0']['shares_of_paths_pct']['fall_of_50_pct_or_more']:.0f} fois sur 100", 0))
    rows.append(("Perdre la moitié du compte", "si le robot ne vaut rien",
                 f"{a['-0.5']['shares_of_paths_pct']['fall_of_50_pct_or_more']:.1f} fois sur 100".replace(".", ","),
                 f"{b['-0.5']['shares_of_paths_pct']['fall_of_50_pct_or_more']:.0f} fois sur 100", 0))
    rows.append(("4 semaines perdantes de suite", "au moins une fois en 3 ans (moitié)",
                 f"{a['0.5']['shares_of_paths_pct']['a_run_of_4_losing_weeks_or_more']:.0f} fois sur 100",
                 f"{b['0.5']['shares_of_paths_pct']['a_run_of_4_losing_weeks_or_more']:.0f} fois sur 100", None))
    rows.append(("S'il ne vaut rien", "arrêt de sécurité vers la fin de la 1re année",
                 eur(r100(a["-0.5"]["at_36_months"]["gain_median"])), eur(r100(b["-0.5"]["at_36_months"]["gain_median"])), None))
    return rows


def main():
    rows = row_values()
    for r in rows:
        print(r)
    fig = plt.figure(figsize=(9, 11.2), dpi=170)
    fig.text(0.05, 0.965, "Démarrer à 1 % ou à 2 % par trade ?", fontsize=19, fontweight="bold")
    fig.text(0.05, 0.942, "Ensuite la mise baisse : ½ % pour les deux dès 12 000 €. Même arrêt de sécurité.",
             fontsize=11, color=INK2)
    ax = fig.add_axes([0.05, 0.09, 0.90, 0.83]); ax.set_xlim(0, 1); ax.set_ylim(len(rows) + 0.6, -0.9); ax.axis("off")
    xa, xb = 0.66, 0.88
    ax.text(xa, -0.45, "Départ 1 %", ha="center", fontsize=13.5, fontweight="bold")
    ax.text(xb, -0.45, "Départ 2 %", ha="center", fontsize=13.5, fontweight="bold")
    for i, (lab, sub, va, vb, better) in enumerate(rows):
        y = i + 0.5
        if i:
            ax.plot([0, 1], [i, i], color=GRID, lw=0.8)
        ax.text(0.0, y - 0.13, lab, fontsize=12.2, va="center", color=INK)
        ax.text(0.0, y + 0.2, sub, fontsize=9.8, va="center", color=INK2)
        # better = 0 -> the 1 % column is better, 1 -> the 2 % column, None -> the same
        for j, (x, v) in enumerate(((xa, va), (xb, vb))):
            hi = (better == j)
            if hi:
                ax.add_patch(FancyBboxPatch((x - 0.105, y - 0.36), 0.21, 0.72, boxstyle="round,pad=0,rounding_size=0.02",
                                            fc=TINT, ec="none", mutation_aspect=0.9))
            ax.text(x, y, v, ha="center", va="center", fontsize=11.8 if len(v) < 16 else 10.6,
                    fontweight="bold" if hi else "normal", color=BLUE if hi else INK)
    fig.text(0.05, 0.062, "Case bleue : le meilleur des deux. « Papier » : comme les trades de 2022 à 2025 ; « moitié » : le cas du milieu.",
             fontsize=9.6, color=INK2)
    fig.text(0.05, 0.042, "Le robot actuel ne sait pas encore faire seul ces paliers ni cet arrêt : ce sera ajouté.", fontsize=9.6, color=INK2)
    fig.text(0.05, 0.015, "Simulation : 2 000 trajectoires de 3 ans tirées des trades de 2022 à 2025, 1 000 € versés par mois. Aucun trade réel.",
             fontsize=8.3, color=MUTED)
    fig.savefig(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
