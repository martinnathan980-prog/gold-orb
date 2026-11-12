import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = sys.argv[1]
d = json.load(open("results/r2/stake/x2/x2.json"))["1.0"]
SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": AXIS, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
stakes = ["1", "2", "3", "5", "7.5", "10", "15", "20"]
labs = [s.replace(".", ",") + " %" for s in stakes]
x = np.arange(len(stakes))
rows = [
    ("Le mois typique (le plus probable)", [d[s]["median_month_pct"] for s in stakes], None, lambda v: ("+" if v > 0 else "−") + f"{abs(v):.0f} %"),
    ("Chances de doubler dans le mois", [d[s]["doubles_pct"] for s in stakes], AQUA, lambda v: "0" if v < 0.05 else ("< 1 %" if v < 1 else f"{v:.0f} %")),
    ("Chances de perdre la moitié dans le mois", [d[s]["fall50_pct"] for s in stakes], ORANGE, lambda v: "0" if v < 0.05 else ("< 1 %" if v < 1 else f"{v:.0f} %")),
]
fig, axes = plt.subplots(3, 1, figsize=(6, 10.4), dpi=200)
for ax, (title, vals, col, fmt) in zip(axes, rows):
    cols = [col] * len(vals) if col else [BLUE if v >= 0 else ORANGE for v in vals]
    ax.bar(x, vals, 0.62, color=cols, zorder=3)
    m = max(abs(v) for v in vals) or 1.0
    for xx, v in zip(x, vals):
        ax.text(xx, v + (m * 0.03 if v >= 0 else -m * 0.03), fmt(v), ha="center", va="bottom" if v >= 0 else "top", fontsize=10, fontweight="bold", color=INK)
    ax.axhline(0, color=AXIS, lw=1.2, zorder=2)
    lo, hi = min(0, min(vals)), max(0, max(vals))
    ax.set_ylim(lo - m * (0.2 if lo < 0 else 0.0), hi + m * 0.22)
    ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=10.5, color=INK)
    ax.set_yticks([]); ax.tick_params(length=0)
    for sp in ("left", "bottom"):
        ax.spines[sp].set_visible(False)
    ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", pad=10)
axes[-1].set_xlabel("Part du compte risquée à chaque trade", fontsize=10, color=INK2, labelpad=8)
fig.suptitle("Avec le robot d'aujourd'hui, grossir la mise\nne fait pas doubler le compte", x=0.05, y=0.987, ha="left", fontsize=15, fontweight="bold")
fig.text(0.05, 0.028, "Premier mois, 1 000 € au départ, si le robot fait comme sur le papier (le meilleur cas).", fontsize=8.3, color=MUTED)
fig.text(0.05, 0.011, "Simulation sur les années 2022 à 2025, 2 000 tirages. Aucun trade réel.", fontsize=8.3, color=MUTED)
fig.subplots_adjust(left=0.05, right=0.97, top=0.885, bottom=0.095, hspace=0.6)
fig.savefig(f"{OUT}/11_doubler_en_un_mois.png")
print("done")
