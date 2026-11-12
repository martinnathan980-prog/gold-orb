"""Pictures for the user (French, phone width). Data: lab/results/r2/stake/growth.json (simulated, rounded in the labels)."""
import json, math, sys
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

OUT = sys.argv[1]
g = json.load(open("results/r2/stake/growth.json"))
R = g["resampled"]
SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, ORANGE, AQUA = "#2a78d6", "#eb6834", "#1baf7a"
BLUE_T, ORANGE_T, AQUA_T = "#9ec5f4", "#f6b99f", "#8fd9bd"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "axes.edgecolor": AXIS, "axes.labelcolor": INK2, "text.color": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False, "axes.spines.right": False,
                     "figure.facecolor": SURF, "axes.facecolor": SURF, "savefig.facecolor": SURF})


def r2(v):
    v = float(v)
    if v == 0:
        return 0
    d = math.floor(math.log10(abs(v)))
    q = 10 ** (d - 1)
    return int(round(v / q) * q)


def eur(v, sign=False):
    v = r2(v)
    s = f"{abs(v):,.0f}".replace(",", " ") + " €"
    if sign:
        return ("+" if v > 0 else "−" if v < 0 else "") + s
    return ("−" if v < 0 else "") + s


def keur(v, _=None):
    return (f"{v / 1000:.0f} k€" if abs(v) >= 1000 else f"{v:.0f} €").replace("-", "−")


# ---------------------------------------------------------------- 1. the plan in three cases
def paths(plan="FS"):
    cases = [("1.0", "Si le robot fait comme sur le papier"), ("0.5", "S'il fait la moitié du papier"), ("-0.5", "S'il ne vaut rien")]
    fig, axes = plt.subplots(3, 1, figsize=(6, 11.2), dpi=200)
    months = np.arange(37)
    for ax, (f, title) in zip(axes, cases):
        r = R[plan][f]
        bal = np.array(r["sample_paths"]["balance"]); pin = np.array(r["sample_paths"]["paid_in"])
        paid36 = r["at_36_months"]["paid_in_median"]
        paid = np.minimum(1000.0 * np.maximum(months, 1), paid36)               # what is typically paid in
        med = paid + np.array(r["gain_percentiles_by_month"]["50"])              # typical account = paid in + the median gain
        med[0] = 1000.0
        for k in range(len(bal)):
            ax.plot(months, bal[k], color=BLUE, lw=0.7, alpha=0.22, zorder=2)
        ax.plot(months, paid, color=INK2, lw=1.6, ls=(0, (4, 3)), zorder=3)
        ax.plot(months, med, color=BLUE, lw=2.6, zorder=4, solid_capstyle="round")
        a36 = r["at_36_months"]
        gain = a36["gain_median"]
        if f == "-0.5":
            st = r.get("stopped", {})
            sub = f"le plus probable : {eur(gain, True)}, puis le robot s'arrête"
        else:
            sub = f"le plus probable : {eur(gain, True)} en 3 ans"
        ax.set_title(title, loc="left", fontsize=13, fontweight="bold", color=INK, pad=22)
        ax.text(0, 1.035, sub, transform=ax.transAxes, fontsize=11, color=INK2, va="bottom")
        top = max(np.percentile(bal[:, -1], 92), med[-1], paid[-1]) * 1.12
        ax.set_ylim(0, top)
        ax.set_xlim(0, 36)
        ax.set_xticks([0, 12, 24, 36]); ax.set_xticklabels(["départ", "1 an", "2 ans", "3 ans"])
        tl = ax.get_xticklabels(); tl[0].set_ha("left"); tl[-1].set_ha("right")
        ax.yaxis.set_major_formatter(FuncFormatter(keur)); ax.yaxis.set_major_locator(plt.MaxNLocator(5))
        ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
        ax.tick_params(length=0)
        # end labels: the upper line's label above it, the lower line's label under it
        up = med[-1] >= paid[-1]
        off = top * 0.03
        ax.text(35.7, med[-1] + (off if up else -off), f"compte {eur(med[-1])}", ha="right", va="bottom" if up else "top", fontsize=10.5, color=INK, fontweight="bold", zorder=6)
        slope = (paid[-1] - paid[-9]) if len(paid) > 9 else 0.0                  # the paid-in line rises to the right: clear it
        ax.text(35.7, paid[-1] - (off + (slope if up else 0.0)) if up else paid[-1] + off, f"versé {eur(paid[-1])}", ha="right", va="top" if up else "bottom", fontsize=10, color=INK2, zorder=6)
    h = [plt.Line2D([], [], color=BLUE, lw=2.6), plt.Line2D([], [], color=BLUE, lw=0.9, alpha=0.5), plt.Line2D([], [], color=INK2, lw=1.6, ls=(0, (4, 3)))]
    fig.legend(h, ["le cas le plus probable", "40 trajectoires possibles", "ce que tu as versé"], loc="upper left", bbox_to_anchor=(0.06, 0.972), ncol=1,
               frameon=False, fontsize=10.5, labelcolor=INK2, handlelength=2.4)
    fig.suptitle("Ton compte avec le plan « rapide puis calme »", x=0.06, y=0.992, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.012, "Simulation sur les années 2022 à 2025, 1 000 € versés par mois. Aucun trade réel.", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.13, right=0.97, top=0.86, bottom=0.055, hspace=0.42)
    fig.savefig(f"{OUT}/1_compte_rapide_puis_calme.png")
    plt.close(fig)


# ---------------------------------------------------------------- 2. the rule: risk falls as the account grows
def rule():
    fig, ax = plt.subplots(figsize=(6, 4.3), dpi=200)
    xs = [0, 3000, 3000, 6000, 6000, 12000, 12000, 20000]
    ys = [5, 5, 2, 2, 1, 1, 0.5, 0.5]
    ax.plot(xs, ys, color=BLUE, lw=2.6, solid_joinstyle="round")
    ax.fill_between(xs, ys, 0, color=BLUE, alpha=0.10, lw=0)
    for x, y, t in ((1500, 5, "5 %"), (4500, 2, "2 %"), (9000, 1, "1 %"), (16000, 0.5, "0,5 %")):
        ax.text(x, y + 0.18, t, ha="center", va="bottom", fontsize=12, fontweight="bold", color=INK)
    ax.axvline(12000, color=INK2, lw=1.4, ls=(0, (4, 3)))
    ax.text(12300, 3.6, "à partir de 12 000 € versés :\narrêt de sécurité à −25 %", fontsize=10, color=INK2, va="center")
    ax.set_xlim(0, 20000); ax.set_ylim(0, 6)
    ax.set_xticks([0, 3000, 6000, 12000, 20000]); ax.set_xticklabels(["0", "3 000 €", "6 000 €", "12 000 €", "20 000 €"])
    ax.set_yticks([0, 1, 2, 3, 4, 5]); ax.set_yticklabels(["0", "1 %", "2 %", "3 %", "4 %", "5 %"])
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
    ax.set_xlabel("taille du compte", fontsize=10)
    ax.set_title("Le risque pris à chaque trade baisse\nquand le compte grossit", loc="left", fontsize=14, fontweight="bold", pad=12)
    fig.subplots_adjust(left=0.11, right=0.96, top=0.80, bottom=0.15)
    fig.savefig(f"{OUT}/2_risque_qui_se_calme.png")
    plt.close(fig)


# ---------------------------------------------------------------- 3. falls and waiting time, three plans
def falls():
    plans = [("A", "1 % tout\nle temps", BLUE, BLUE_T), ("C2", "Départ rapide\nsans frein", ORANGE, ORANGE_T), ("FS", "Rapide\npuis calme", AQUA, AQUA_T)]
    fig, axes = plt.subplots(2, 1, figsize=(6, 8.2), dpi=200)
    specs = [("fall_from_high_after_12_months_pct", "La pire baisse depuis le plus haut,\naprès la première année", lambda v: f"−{v:.0f} %".replace(".", ",")),
             ("weeks_under_highest_balance", "Semaines avant de revoir le plus haut du compte\n(avec tes versements)", lambda v: f"{v:.0f} sem.")]
    for ax, (key, title, fmt) in zip(axes, specs):
        x = np.arange(len(plans)); w = 0.36
        for i, (p, lab, c, ct) in enumerate(plans):
            v = R[p]["0.5"]["falls"][key]
            b1 = ax.bar(i - w / 2 - 0.02, v["median"], w, color=c, zorder=3)
            b2 = ax.bar(i + w / 2 + 0.02, v["p90"], w, color=ct, zorder=3)
            ax.text(i - w / 2 - 0.02, v["median"], fmt(v["median"]), ha="center", va="bottom", fontsize=11, fontweight="bold", color=INK)
            ax.text(i + w / 2 + 0.02, v["p90"], fmt(v["p90"]), ha="center", va="bottom", fontsize=11, color=INK2)
        ax.set_xticks(x); ax.set_xticklabels([p[1] for p in plans], fontsize=10.5, color=INK)
        ax.set_yticks([]); ax.spines["left"].set_visible(False); ax.tick_params(length=0)
        ax.set_ylim(0, max(R[p[0]]["0.5"]["falls"][key]["p90"] for p in plans) * 1.22)
        ax.set_title(title, loc="left", fontsize=12.5, fontweight="bold", pad=10)
    h = [plt.Rectangle((0, 0), 1, 1, color=INK2), plt.Rectangle((0, 0), 1, 1, color=AXIS)]
    fig.legend(h, ["le plus souvent", "une fois sur dix"], loc="upper left", bbox_to_anchor=(0.05, 0.935), ncol=2, frameon=False, fontsize=10.5, labelcolor=INK2)
    fig.suptitle("Si le robot fait la moitié du papier", x=0.05, y=0.985, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.05, 0.012, "Simulation sur les années 2022 à 2025, 2 000 trajectoires de 3 ans. Aucun trade réel.", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.97, top=0.83, bottom=0.10, hspace=0.66)
    fig.savefig(f"{OUT}/3_baisses_et_attente.png")
    plt.close(fig)


# ---------------------------------------------------------------- 4. the price: gain after three years, three plans, three cases
def gains():
    plans = [("A", "1 % tout le temps", BLUE), ("C2", "Départ rapide sans frein", ORANGE), ("FS", "Rapide puis calme", AQUA)]
    cases = [("1.0", "comme sur\nle papier"), ("0.5", "la moitié"), ("-0.5", "il ne vaut\nrien")]
    fig, ax = plt.subplots(figsize=(6, 5.6), dpi=200)
    w = 0.26
    vals = [[R[p][f]["at_36_months"]["gain_median"] for f, _ in cases] for p, _, _ in plans]
    top = max(max(v) for v in vals); low = min(min(v) for v in vals)
    for i, (p, lab, c) in enumerate(plans):
        for j, v in enumerate(vals[i]):
            xx = j + (i - 1) * (w + 0.03)
            ax.bar(xx, v, w, color=c, zorder=3)
            k = r2(v) / 1000.0
            lab_ = ("+" if k > 0 else "−") + (f"{abs(k):.1f}".replace(".", ",") if abs(k) < 10 else f"{abs(k):.0f}") + " k€"
            ax.text(xx, v + (top * 0.015 if v >= 0 else -top * 0.015), lab_, ha="center", va="bottom" if v >= 0 else "top",
                    fontsize=9.6, color=INK, fontweight="bold" if p == "FS" else "normal")
    ax.axhline(0, color=AXIS, lw=1.2, zorder=2)
    ax.set_xticks(range(len(cases))); ax.set_xticklabels([c[1] for c in cases], fontsize=11, color=INK)
    ax.set_yticks([]); ax.spines["left"].set_visible(False); ax.spines["bottom"].set_visible(False); ax.tick_params(length=0)
    ax.set_ylim(low - top * 0.16, top * 1.12)
    h = [plt.Rectangle((0, 0), 1, 1, color=c) for _, _, c in plans]
    ax.legend(h, [lab for _, lab, _ in plans], loc="upper right", frameon=False, fontsize=10.5, labelcolor=INK2)
    ax.set_title("Gain ou perte du robot après 3 ans, en euros\n(36 000 € mis de côté)", loc="left", fontsize=14, fontweight="bold", pad=12)
    fig.text(0.05, 0.015, "Le cas le plus probable de chaque plan. Simulation, aucun trade réel.", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.97, top=0.83, bottom=0.14)
    fig.savefig(f"{OUT}/4_gains_apres_3_ans.png")
    plt.close(fig)


paths(); rule(); falls(); gains()
print("done")
