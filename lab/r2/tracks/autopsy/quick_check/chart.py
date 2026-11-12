"""Picture of the quick check (French, phone width). In sample only (results/r2/autopsy/quick_check/)."""
import json, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

OUT = sys.argv[1]
s = json.load(open("results/r2/autopsy/quick_check/summary.json"))
base = json.load(open("results/r2/autopsy/quick_check/baseline.json"))["total_R"]
SURF, INK, INK2, MUTED, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#c3c2b7"
BLUE, ORANGE, BLUE_T, ORANGE_T = "#2a78d6", "#eb6834", "#9ec5f4", "#f6b99f"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": AXIS, "text.color": INK, "xtick.color": MUTED, "ytick.color": MUTED,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})
fig, axes = plt.subplots(2, 1, figsize=(6, 9.6), dpi=200)
# 1. after 15 minutes: what the rest of the trade still earns, by how the trade stands
p = s["pooled"]["15"]
labs = ["perd\n+ de 75 €", "perd\n50 à 75 €", "perd\n25 à 50 €", "perd\n0 à 25 €", "gagne\n0 à 25 €", "gagne\n25 à 50 €", "gagne\n+ de 50 €"]
vals = [100 * p[b]["mean_rest_R"] for b in s["buckets_R"]]
wins = [100 * p[b]["share_ending_in_gain"] for b in s["buckets_R"]]
ax = axes[0]
x = np.arange(len(vals))
ax.bar(x, vals, 0.64, color=[BLUE if v >= 0 else ORANGE for v in vals], zorder=3)
for xx, v, w in zip(x, vals, wins):
    ax.text(xx, v + 0.8, f"{v:+.0f} €", ha="center", va="bottom", fontsize=10, fontweight="bold", color=INK)
    ax.text(xx, -1.2, f"{w:.0f} %", ha="center", va="top", fontsize=9, color=INK2)
ax.axhline(0, color=AXIS, lw=1.2, zorder=2)
ax.set_ylim(-4.5, max(vals) * 1.3)
ax.set_xticks(x); ax.set_xticklabels(labs, fontsize=8.6, color=INK)
ax.tick_params(axis="x", length=0, pad=4)
ax.set_yticks([]); ax.spines["left"].set_visible(False); ax.spines["bottom"].set_visible(False)
ax.set_title("Après 15 minutes, ce que la suite du trade\nrapporte encore (pour 100 € de mise)", loc="left", fontsize=12.5, fontweight="bold", pad=24)
ax.text(0, 1.02, "en gris, sous chaque barre : part des trades qui finissent gagnants", transform=ax.transAxes, fontsize=8.8, color=INK2)
# 2. the rule "cut every trade that already loses 25 € (or 50 €) of its 100 € at minute t"
ax = axes[1]
checks = [5, 15, 30, 60, 120]
v25 = [100 * s["cut_rules"][f"t{c}_x0.25"]["R_saved_total"] / base for c in checks]
v50 = [100 * s["cut_rules"][f"t{c}_x0.5"]["R_saved_total"] / base for c in checks]
x = np.arange(len(checks))
ax.bar(x - 0.2, v25, 0.38, color=ORANGE, zorder=3, label="couper s'il perd déjà 25 €")
ax.bar(x + 0.2, v50, 0.38, color=ORANGE_T, zorder=3, label="couper s'il perd déjà 50 €")
fmt = lambda v: "0 %" if abs(v) < 0.5 else f"−{abs(v):.0f} %" if v < 0 else f"+{v:.0f} %"
for xx, v in zip(x - 0.2, v25):
    ax.text(xx, v - 0.4, fmt(v), ha="center", va="top", fontsize=10, fontweight="bold", color=INK)
for xx, v in zip(x + 0.2, v50):
    ax.text(xx, v - 0.4, fmt(v), ha="center", va="top", fontsize=9.5, color=INK2)
ax.axhline(0, color=AXIS, lw=1.2, zorder=2)
ax.set_ylim(min(v25) * 1.25, 3)
ax.set_xticks(x); ax.set_xticklabels([f"après\n{c} min" if c < 60 else f"après\n{c // 60} h" for c in checks], fontsize=10, color=INK)
ax.tick_params(axis="x", length=0)
ax.set_yticks([]); ax.spines["left"].set_visible(False); ax.spines["bottom"].set_visible(False)
ax.legend(loc="lower right", frameon=False, fontsize=9.5, labelcolor=INK2)
ax.set_title("Couper tôt les trades qui partent mal :\neffet sur le gain total", loc="left", fontsize=12.5, fontweight="bold", pad=10)
fig.suptitle("Couper vite ce qui part mal\nfait perdre de l'argent", x=0.05, y=0.988, ha="left", fontsize=15, fontweight="bold")
fig.text(0.05, 0.027, "Les 8 000 trades des dix règles, années d'essai (2012 à 2021), frais compris.", fontsize=8.3, color=MUTED)
fig.text(0.05, 0.011, "Chaque trade garde son stop et sa sortie prévue. Aucun trade réel.", fontsize=8.3, color=MUTED)
fig.subplots_adjust(left=0.05, right=0.97, top=0.825, bottom=0.085, hspace=0.62)
fig.savefig(f"{OUT}/12_couper_tot.png")
print("done")
