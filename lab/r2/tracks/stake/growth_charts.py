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
def paths(plan="FS", title="Ton compte avec le plan « rapide puis calme »", fname="1_compte_rapide_puis_calme.png"):
    cases = [("1.0", "Si le robot fait comme sur le papier"), ("0.5", "S'il fait la moitié du papier"), ("-0.5", "S'il ne vaut rien")]
    fig, axes = plt.subplots(3, 1, figsize=(6, 11.2), dpi=200)
    months = np.arange(37)
    for ax, (f, case) in zip(axes, cases):
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
        ax.set_title(case, loc="left", fontsize=13, fontweight="bold", color=INK, pad=22)
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
    fig.suptitle(title, x=0.06, y=0.992, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.06, 0.012, "Simulation sur les années 2022 à 2025, 1 000 € versés par mois. Aucun trade réel.", fontsize=8.5, color=MUTED)
    fig.subplots_adjust(left=0.13, right=0.97, top=0.86, bottom=0.055, hspace=0.42)
    fig.savefig(f"{OUT}/{fname}")
    plt.close(fig)


# ---------------------------------------------------------------- 2. the rule: risk falls as the account grows
def rule(plan="FS", fname="2_risque_qui_se_calme.png"):
    base = g["stopped"][plan]["plan"]
    thr, pct = g["schedules"][base]["thresholds_eur"], g["schedules"][base]["risk_pct"]
    arm = g["stopped"][plan]["armed_once_paid_in"]
    edges = [0.0] + list(thr) + [20000.0]
    xs, ys = [], []
    for k, v in enumerate(pct):
        xs += [edges[k], edges[k + 1]]; ys += [v, v]
    fig, ax = plt.subplots(figsize=(6, 4.3), dpi=200)
    ax.plot(xs, ys, color=BLUE, lw=2.6, solid_joinstyle="round")
    ax.fill_between(xs, ys, 0, color=BLUE, alpha=0.10, lw=0)
    top = max(pct) + 1
    for k, v in enumerate(pct):
        ax.text((edges[k] + edges[k + 1]) / 2, v + top * 0.03, (f"{v:g} %").replace(".", ","), ha="center", va="bottom", fontsize=12, fontweight="bold", color=INK)
    if arm > 0:
        ax.axvline(arm, color=INK2, lw=1.4, ls=(0, (4, 3)))
        ax.text(arm + 350, top * 0.66, f"à partir de {eur(arm)}\nversés : arrêt de\nsécurité à −25 %", fontsize=10, color=INK2, va="center")
    ax.set_xlim(0, 20000); ax.set_ylim(0, top)
    ax.set_xticks(edges); ax.set_xticklabels(["0"] + [eur(v) for v in edges[1:]])
    ax.get_xticklabels()[-1].set_ha("right")
    yt = list(range(0, int(top) + 1))
    ax.set_yticks(yt); ax.set_yticklabels(["0"] + [f"{v} %" for v in yt[1:]])
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True); ax.tick_params(length=0)
    ax.set_xlabel("taille du compte", fontsize=10)
    ax.set_title("Le risque pris à chaque trade baisse\nquand le compte grossit", loc="left", fontsize=14, fontweight="bold", pad=12)
    fig.subplots_adjust(left=0.11, right=0.96, top=0.80, bottom=0.15)
    fig.savefig(f"{OUT}/{fname}")
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


YELLOW, YELLOW_T = "#eda100", "#f6d58a"
def early(plan, f="0.5"):
    fl = R[plan][f]["falls"]
    return dict(pct=fl["fall_first_13_weeks_pct"]["median"], pct90=fl["fall_first_13_weeks_pct"]["p90"],
                eur=fl["fall_first_13_weeks_eur"]["median"], eur90=fl["fall_first_13_weeks_eur"]["p90"])


def losing_runs(plan, f="0.5"):
    """Share of three-year paths with a run of 4 losing weeks or more, and what the worst such run that starts after the
    first year costs (median over the paths that have one, % of the balance at its start)."""
    r = R[plan][f]
    return dict(share=r["shares_of_paths_pct"]["a_run_of_4_losing_weeks_or_more"], cost=r["falls"]["worst_run_cost_after_12_months_pct"]["median"])


def duel():
    a, b = R["FS"]["0.5"], R["A05S"]["0.5"]
    wa, wb = R["FS"]["-0.5"], R["A05S"]["-0.5"]
    ea, eb = early("FS"), early("A05S")
    e = lambda v: eur(v, True)
    pc = lambda v, x: f"−{abs(v):.0f} %\n≈ {eur(x)}"
    p1 = lambda v: f"−{abs(v):.0f} %"
    fa, fb = a["falls"]["fall_from_high_after_12_months_pct"]["median"], b["falls"]["fall_from_high_after_12_months_pct"]["median"]
    panels = [
        ("Gain après 1 an", (a["at_12_months"]["gain_median"], b["at_12_months"]["gain_median"]), None),
        ("Gain après 3 ans", (a["at_36_months"]["gain_median"], b["at_36_months"]["gain_median"]), None),
        ("Baisse des 3 premiers mois\n(le plus souvent)", (-ea["pct"], -eb["pct"]), (pc(ea["pct"], ea["eur"]), pc(eb["pct"], eb["eur"]))),
        ("Baisse des 3 premiers mois\n(une fois sur dix)", (-ea["pct90"], -eb["pct90"]), (pc(ea["pct90"], ea["eur90"]), pc(eb["pct90"], eb["eur90"]))),
        ("Baisse après la 1re année\n(le plus souvent)", (-fa, -fb), (p1(fa), p1(fb))),
        ("Si le robot ne vaut rien :\nperte avant l'arrêt", (wa["at_36_months"]["gain_median"], wb["at_36_months"]["gain_median"]), None),
    ]
    fig, axes = plt.subplots(3, 2, figsize=(6, 10.2), dpi=200)
    for ax, (title, vals, labels) in zip(axes.ravel(), panels):
        labels = labels or (e(vals[0]), e(vals[1]))
        ax.bar([0, 1], vals, 0.62, color=[AQUA, YELLOW], zorder=3)
        m = max(abs(v) for v in vals)
        for xx, v, lab in zip([0, 1], vals, labels):
            ax.text(xx, v + (m * 0.04 if v >= 0 else -m * 0.04), lab, ha="center", va="bottom" if v >= 0 else "top", fontsize=11,
                    fontweight="bold", color=INK, linespacing=1.25)
        ax.axhline(0, color=AXIS, lw=1.2, zorder=2)
        lo, hi = min(0, min(vals)), max(0, max(vals))
        ax.set_ylim(lo - m * (0.42 if lo < 0 else 0.05), hi + m * (0.24 if hi > 0 else 0.05))
        ax.set_xlim(-0.6, 1.6)
        ax.set_xticks([]); ax.set_yticks([])
        for sp in ("left", "bottom"):
            ax.spines[sp].set_visible(False)
        ax.set_title(title, loc="left", fontsize=10.5, fontweight="bold", pad=8)
    h = [plt.Rectangle((0, 0), 1, 1, color=AQUA), plt.Rectangle((0, 0), 1, 1, color=YELLOW)]
    fig.legend(h, ["Rapide puis calme (5 % par trade au départ)", "Calme tout le temps (0,5 % par trade)"], loc="upper left", bbox_to_anchor=(0.04, 0.95),
               ncol=1, frameon=False, fontsize=11, labelcolor=INK2)
    fig.suptitle("Deux plans, côte à côte", x=0.05, y=0.988, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.05, 0.044, "Gains et baisses : si le robot fait la moitié du papier.", fontsize=8.3, color=MUTED)
    fig.text(0.05, 0.028, "Les deux plans ont un arrêt de sécurité à −25 %.", fontsize=8.3, color=MUTED)
    fig.text(0.05, 0.012, "Simulation sur les années 2022 à 2025, 2 000 trajectoires de 3 ans. Aucun trade réel.", fontsize=8.3, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.97, top=0.85, bottom=0.085, hspace=0.6, wspace=0.18)
    fig.savefig(f"{OUT}/5_deux_plans.png")
    plt.close(fig)


LADDER = [("A05S", "0,5 %"), ("F1S", "1 %"), ("F2S", "2 %"), ("F3S", "3 %"), ("FS", "5 %")]
TIE = 0.05      # two plans whose median gain differs by less than this share are tied (2,000 paths: the medians are known to about 3 %)


def qualifies(plan):
    """The rule fixed in the sixth clarification: a fall of 50 % or more in at most one path in twenty, on paper and at half edge."""
    return all(R[plan][f]["shares_of_paths_pct"]["fall_of_50_pct_or_more"] <= 5.0 for f in ("1.0", "0.5"))


def best_of_ladder(tie_break=True):
    """The qualifying plan with the highest median gain after 12 months at half edge. `tie_break` (added AFTER the run, see the
    outcome in PROTOCOL_V3): among the qualifying plans within TIE of that gain, the one with the smallest typical fall of the
    first 13 weeks."""
    if any(p_ not in R for p_, _ in LADDER):
        return None
    gain = lambda p_: R[p_]["0.5"]["at_12_months"]["gain_median"]
    ok = [p_ for p_, _ in LADDER if qualifies(p_)]
    if not ok:
        return None
    top = max(ok, key=gain)
    if not tie_break:
        return top
    tied = [p_ for p_ in ok if gain(p_) >= gain(top) * (1 - TIE)]
    return min(tied, key=lambda p_: R[p_]["0.5"]["falls"]["fall_first_13_weeks_pct"]["median"])


def runs():
    mid = best_of_ladder() or "FS"
    plans = [("A", "1 % tout\nle temps", BLUE), (mid, f"Départ à {dict(LADDER)[mid]}\npuis calme", AQUA), ("A05S", "Calme tout\nle temps", YELLOW)]
    RUNS = {p_: losing_runs(p_) for p_, _, _ in plans}
    fig, axes = plt.subplots(2, 1, figsize=(6, 7.6), dpi=200)
    for ax, key, title, fmt in ((axes[0], "share", "Chances d'avoir au moins une série de 4 semaines\nperdantes en 3 ans", lambda v: f"{v:.0f} %"),
                                (axes[1], "cost", "Ce que coûte la pire de ces séries, après la\npremière année (part du compte)", lambda v: f"−{v:.0f} %")):
        for i, (p_, lab, c) in enumerate(plans):
            v = RUNS[p_][key]
            ax.bar(i, v, 0.6, color=c, zorder=3)
            ax.text(i, v, fmt(v), ha="center", va="bottom", fontsize=12, fontweight="bold", color=INK)
        ax.set_xticks(range(len(plans))); ax.set_xticklabels([p_[1] for p_ in plans], fontsize=10.5, color=INK)
        ax.set_yticks([]); ax.spines["left"].set_visible(False); ax.tick_params(length=0)
        ax.set_ylim(0, max(RUNS[p_[0]][key] for p_ in plans) * 1.25)
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=10)
    fig.suptitle("Les séries de pertes : aussi fréquentes,\nmais deux fois moins chères", x=0.05, y=0.985, ha="left", fontsize=15, fontweight="bold")
    fig.text(0.05, 0.012, "Si le robot fait la moitié du papier. Simulation, 2 000 trajectoires de 3 ans. Aucun trade réel.", fontsize=8.3, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.97, top=0.80, bottom=0.11, hspace=0.66)
    fig.savefig(f"{OUT}/6_series_de_pertes.png")
    plt.close(fig)


def ladder():
    """One picture for the choice: the same plan with a start at 0.5, 1, 2, 3 and 5 % per trade, at half of the paper edge."""
    if any(p_ not in R for p_, _ in LADDER):
        return
    best = best_of_ladder()
    x = np.arange(len(LADDER))
    half = [R[p_]["0.5"] for p_, _ in LADDER]
    rows = [
        ("Gain après 1 an", [h["at_12_months"]["gain_median"] for h in half], None, BLUE, lambda v: eur(v, True)),
        ("Pire baisse des 3 premiers mois\n(le plus souvent, et une fois sur dix)", [-h["falls"]["fall_first_13_weeks_pct"]["median"] for h in half],
         [-h["falls"]["fall_first_13_weeks_pct"]["p90"] for h in half], ORANGE, lambda v: f"−{abs(v):.0f} %"),
        ("Chances de perdre la moitié du compte", [h["shares_of_paths_pct"]["fall_of_50_pct_or_more"] for h in half], None, ORANGE,
         lambda v: ("0" if v < 0.05 else "< 1 %" if v < 1 else f"{v:.0f} %") if v < 0.05 or v >= 1 or True else ""),
        ("Gain après 3 ans", [h["at_36_months"]["gain_median"] for h in half], None, BLUE, lambda v: eur(v, True)),
    ]
    fig, axes = plt.subplots(4, 1, figsize=(6, 12.4), dpi=200)
    for ax, (title, v1, v2, col, fmt) in zip(axes, rows):
        if best is not None:
            k = [p_ for p_, _ in LADDER].index(best)
            ax.axvspan(k - 0.46, k + 0.46, color=AQUA_T, alpha=0.38, zorder=1, lw=0)
        if v2 is None:
            ax.bar(x, v1, 0.6, color=col, zorder=3)
            m = max(abs(v) for v in v1) or 1.0
            for xx, v in zip(x, v1):
                ax.text(xx, v + (m * 0.04 if v >= 0 else -m * 0.04), fmt(v), ha="center", va="bottom" if v >= 0 else "top", fontsize=10.5,
                        fontweight="bold", color=INK)
            lo, hi = min(0, min(v1)), max(0, max(v1))
            ax.set_ylim(lo - m * (0.22 if lo < 0 else 0.0), hi + m * 0.24)
        else:
            tint = ORANGE_T if col == ORANGE else BLUE_T
            ax.bar(x - 0.23, v1, 0.36, color=col, zorder=3, label="le plus souvent")
            ax.bar(x + 0.23, v2, 0.36, color=tint, zorder=3, label="une fois sur dix")
            m = max(abs(v) for v in v1 + v2) or 1.0
            for xx, v in zip(x - 0.23, v1):
                ax.text(xx, v - m * 0.04, fmt(v), ha="center", va="top", fontsize=8.6, fontweight="bold", color=INK)
            for xx, v in zip(x + 0.23, v2):
                ax.text(xx, v - m * 0.04, fmt(v), ha="center", va="top", fontsize=8.6, color=INK2)
            ax.set_ylim(min(v1 + v2) - m * 0.2, 0)
            ax.legend(loc="lower left", frameon=False, fontsize=9.5, labelcolor=INK2, handlelength=1.2, borderaxespad=0.2)
        ax.axhline(0, color=AXIS, lw=1.2, zorder=2)
        ax.set_xticks(x); ax.set_xticklabels([lab for _, lab in LADDER], fontsize=10.5, color=INK)
        ax.set_yticks([]); ax.tick_params(length=0)
        for sp in ("left", "bottom"):
            ax.spines[sp].set_visible(False)
        ax.set_xlim(-0.6, len(LADDER) - 0.4)
        ax.set_title(title, loc="left", fontsize=12, fontweight="bold", pad=9)
    axes[-1].set_xlabel("Risque par trade au départ (il baisse ensuite jusqu'à 0,5 %)", fontsize=10, color=INK2, labelpad=8)
    fig.suptitle("Plus le départ est rapide,\nplus le début secoue", x=0.05, y=0.988, ha="left", fontsize=15, fontweight="bold")
    if best is not None:
        fig.text(0.05, 0.917, "En vert, mon conseil : presque le gain du plus rapide, presque jamais −50 %.", fontsize=9.8, color=INK2)
    fig.text(0.05, 0.026, "Si le robot fait la moitié du papier. Arrêt de sécurité à −25 % dans tous les plans.", fontsize=8.3, color=MUTED)
    fig.text(0.05, 0.01, "Simulation sur les années 2022 à 2025, 2 000 trajectoires de 3 ans. Aucun trade réel.", fontsize=8.3, color=MUTED)
    fig.subplots_adjust(left=0.05, right=0.97, top=0.875, bottom=0.085, hspace=0.62)
    fig.savefig(f"{OUT}/7_echelle_des_departs.png")
    plt.close(fig)


paths(); rule(); falls(); gains(); duel(); runs(); ladder()
best = best_of_ladder()
if best is not None:
    paths(best, f"Ton compte avec un départ à {dict(LADDER)[best]}", "8_compte_plan_conseille.png")
    rule(best, "9_risque_plan_conseille.png")
print("done", "| rule alone:", best_of_ladder(False), "| with the tie-break:", best)
