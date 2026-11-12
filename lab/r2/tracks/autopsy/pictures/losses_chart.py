"""Picture for the user (French): where the losses come from, why a trade cannot be sorted early, and why a loss does not
announce the next one. In sample only (entries 2018-02-01..2021-12-31, the ten sleeves, FP costs), read from the path
lens (anatomy_trades.parquet) and the cluster lens (summary.json, runs within sleeves).

    python3 r2/tracks/autopsy/pictures/losses_chart.py      (from lab/)
"""
import json
import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
import pandas as pd

LAB = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "..", ".."))
RES = os.path.join(LAB, "results", "r2", "autopsy")
OUT = os.path.join(RES, "images", "13_pourquoi_on_perd.png")

SURF, INK, INK2, MUTED, GRID, AXIS = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"
BLUE, BLUE_T = "#2a78d6", "#9ec5f4"
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK, "figure.facecolor": SURF,
                     "axes.facecolor": SURF, "savefig.facecolor": SURF})


def numbers():
    t = pd.read_parquet(os.path.join(RES, "path", "anatomy_trades.parquet"))
    c = t[t.period == "2018-2021"]
    w, l = c[c.win], c[~c.win]
    stop = l.reason.isin(["stop", "trail"])
    s = json.load(open(os.path.join(RES, "cluster", "summary.json")))
    rw = [r for r in s["anatomy"]["runs_within_sleeves"] if r["window"] == "common"]
    nl = sum(r["after_1plus_losses_n"] for r in rw)
    nw = sum(r["n"] - 1 - r["after_1plus_losses_n"] for r in rw)
    n3 = sum(r["after_3plus_losses_n"] for r in rw)
    return {
        "n": len(c),
        "stop_share": 100 * l[stop].R.sum() / l.R.sum(), "stop_mean": -100 * l[stop].R.mean(), "time_mean": -100 * l[~stop].R.mean(),
        "win_dipped": 100 * (w.mae <= -0.25).mean(), "loss_was_up": 100 * (l.mfe >= 0.25).mean(),
        "p_after_win": 100 * sum(r["p_loss_after_win"] * (r["n"] - 1 - r["after_1plus_losses_n"]) for r in rw) / nw,
        "p_after_loss": 100 * sum(r["p_loss_after_loss"] * r["after_1plus_losses_n"] for r in rw) / nl,
        "p_after_3": 100 * sum(r["after_3plus_losses_p_loss"] * r["after_3plus_losses_n"] for r in rw) / n3,
    }


def pct(v):
    return f"{v:.0f} %"


def main():
    v = numbers()
    print(v)
    n_txt = f"{v['n']:,}".replace(",", "\u202f")
    fig = plt.figure(figsize=(9, 12.4), dpi=170)
    fig.text(0.06, 0.968, "Pourquoi les règles perdent", fontsize=19, fontweight="bold", color=INK)
    fig.text(0.06, 0.945, f"{n_txt} trades des années de recherche (2018 à 2021), pour 100 € risqués par trade", fontsize=11.5, color=INK2)

    # 1. where the money lost comes from
    fig.text(0.06, 0.895, "1. Les pertes viennent surtout des stops", fontsize=14, fontweight="bold")
    fig.text(0.06, 0.835, f"{v['stop_share']:.0f} €", fontsize=40, fontweight="bold", color=BLUE, va="center")
    fig.text(0.32, 0.852, "sur 100 € perdus viennent des trades qui touchent leur stop", fontsize=12, color=INK, va="center")
    fig.text(0.32, 0.828, f"(environ −{v['stop_mean']:.0f} € chacun). Le reste vient des trades sortis", fontsize=10.5, color=INK2, va="center")
    fig.text(0.32, 0.810, f"à l'heure prévue : −{v['time_mean']:.0f} € en moyenne.", fontsize=10.5, color=INK2, va="center")
    ax = fig.add_axes([0.06, 0.755, 0.88, 0.03]); ax.set_xlim(0, 100); ax.set_ylim(0, 1); ax.axis("off")
    s = v["stop_share"]
    ax.add_patch(Rectangle((0, 0), s - 0.3, 1, fc=BLUE, ec="none"))
    ax.add_patch(Rectangle((s + 0.3, 0), 100 - s - 0.3, 1, fc=AXIS, ec="none"))
    ax.text(1, 0.5, "stop touché", fontsize=10, color="white", va="center", fontweight="bold")
    ax.text(s + 1.4, 0.5, "sortie à l'heure", fontsize=10, color=INK, va="center")

    # 2. the start does not tell
    fig.text(0.06, 0.69, "2. Le début d'un trade ne dit pas comment il finira", fontsize=14, fontweight="bold")
    ax = fig.add_axes([0.06, 0.47, 0.88, 0.195]); ax.set_xlim(0, 100); ax.set_ylim(-0.1, 2.25)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.set_yticks([]); ax.tick_params(length=0, colors=MUTED)
    ax.set_xticks([0, 25, 50, 75, 100]); ax.set_xticklabels(["0 %", "25 %", "50 %", "75 %", "100 %"], fontsize=9.5)
    ax.grid(axis="x", color=GRID, lw=0.8); ax.set_axisbelow(True)
    rows = [(1.3, v["win_dipped"], "des trades GAGNANTS sont d'abord passés par −25 €"),
            (0.15, v["loss_was_up"], "des trades PERDANTS ont d'abord été à +25 €")]
    for y, val, lab in rows:
        ax.add_patch(Rectangle((0, y), val, 0.42, fc=BLUE, ec="none", zorder=3))
        ax.text(val + 1.2, y + 0.21, pct(val), fontsize=15, fontweight="bold", va="center", color=INK)
        ax.text(0, y + 0.62, lab, fontsize=11.5, va="center", color=INK)
    fig.text(0.06, 0.428, f"Couper tout trade à −25 € couperait aussi {v['win_dipped']:.0f} gagnants sur 100 :", fontsize=10.5, color=INK2)
    fig.text(0.06, 0.410, "c'est pour ça que couper vite fait perdre de l'argent avec ces règles.", fontsize=10.5, color=INK2)

    # 3. a loss does not announce the next one
    fig.text(0.06, 0.355, "3. Une perte n'annonce pas la suivante", fontsize=14, fontweight="bold")
    fig.text(0.06, 0.335, "Chance de perdre le trade suivant de la même règle", fontsize=11, color=INK2)
    ax = fig.add_axes([0.06, 0.10, 0.88, 0.205]); ax.set_xlim(-0.6, 2.6); ax.set_ylim(0, 100)
    for sp in ax.spines.values():
        sp.set_visible(False)
    ax.tick_params(length=0, colors=MUTED); ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_yticklabels(["0 %", "25 %", "50 %", "75 %", "100 %"], fontsize=9.5)
    ax.grid(axis="y", color=GRID, lw=0.8); ax.set_axisbelow(True)
    cols = [("après un gain", v["p_after_win"]), ("après une perte", v["p_after_loss"]), ("après 3 pertes de suite", v["p_after_3"])]
    for i, (lab, val) in enumerate(cols):
        ax.add_patch(Rectangle((i - 0.28, 0), 0.56, val, fc=BLUE, ec="none", zorder=3))
        ax.text(i, val + 2.5, pct(val), ha="center", va="bottom", fontsize=15, fontweight="bold", color=INK)
    ax.set_xticks(range(3)); ax.set_xticklabels([c[0] for c in cols], fontsize=11.5, color=INK)
    fig.text(0.06, 0.045, "Il n'y a pas de série à casser : chaque trade repart à zéro.", fontsize=10.5, color=INK2)
    fig.text(0.06, 0.012, "Années de recherche seulement, coûts FP Markets compris. Aucun trade réel.", fontsize=8.5, color=MUTED)
    fig.savefig(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
