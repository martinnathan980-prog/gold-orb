"""Picture for the user (French, phone width): the single look of PROTOCOL_V3 Addendum H, change by change, and the account
before / after. Reads ONLY the harness's own output JSON (no data, no trades file):

    python3 r2/tracks/validation_hi/look_chart.py <look or rehearsal json> <out png> [--rehearsal]

--rehearsal labels the picture as the in-sample rehearsal (CUT 2022-01-01), which is how the layout is checked before the look.
"""
import json
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle

SURF, INK, INK2, MUTED, GRID = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9"
BLUE, BLUE_T, TINT = "#2a78d6", "#9ec5f4", "#e6f0fb"
GOOD, BAD = "#1f7a4d", "#b3261e"           # status ink, always beside a word (gardée / rejetée), never alone
NB = " "                               # narrow no-break space for thousands
plt.rcParams.update({"font.family": "DejaVu Sans", "font.size": 11, "text.color": INK, "figure.facecolor": SURF,
                     "savefig.facecolor": SURF})

NAMES = {   # plain French, what the change does
    "K1": ("ETH, cassure 72 h", "sauter les signaux au stop très large"),
    "K2": ("ETH", "nouvelle règle : la cassure d'Asie de l'or"),
    "K3": ("BTC", "nouvelle règle : la cassure d'Asie de l'or"),
    "ocm4_T1": ("Nasdaq ocm4", "stop suiveur au lieu de sortir à 15 h 55"),
    "F1eth_H2": ("ETH, règle F1", "garder 2 jours de plus les trades gagnants"),
    "brk72btc_S0.75r": ("BTC, cassure 72 h", "stop plus proche (×0,75), même risque"),
    "donch4h_S0.75r": ("Or, Donchian 4 h", "stop plus proche (×0,75), même risque"),
    "orbxau_S0.75r": ("Or, cassure d'Asie", "stop plus proche (×0,75), même risque"),
}
ORDER = ["K1", "K2", "K3", "ocm4_T1", "F1eth_H2", "brk72btc_S0.75r", "donch4h_S0.75r", "orbxau_S0.75r"]


def num(v, d=2):
    return f"{v:.{d}f}".replace(".", ",").replace("-", "−")


def failed_tests(v):
    """Short French list of what failed (empty when adopted)."""
    out = []
    for c in v.get("criteria", []):
        if c.get("pass") is False:
            t = c.get("test") or ""
            crit = c.get("criterion", "")
            if t:
                out.append(t)
            elif "profit factor" in crit:
                out.append("facteur de profit")
            elif "every-signal" in crit:
                out.append("chaque signal")
            elif "years" in crit:
                out.append("années positives")
            elif "x1.5" in crit or crit.startswith("stress"):
                out.append("frais ×1,5")
            elif "weekly mean / sd" in crit:
                out.append("compte moins régulier")
            elif "skipped" in crit:
                out.append("signaux sautés")
            elif "total R" in crit:
                out.append("gain total")
            elif "expectancy" in crit:
                out.append("gain par trade")
            else:
                out.append("critère")
    seen = []
    for o in out:
        if o not in seen:
            seen.append(o)
    return seen


def key_number(cid, v):
    """(label, before, after) on the measure the change is judged on first."""
    crit = v.get("criteria", [])
    if cid == "K1":
        c = crit[0]
        return "gain par trade (R)", c["reference"], c["value"]
    if cid in ("K2", "K3"):
        c = [c for c in crit if "weekly mean / sd" in c.get("criterion", "")][0]
        r52 = 52 ** 0.5                       # weekly mean / sd x sqrt(52) = the weekly Sharpe the other rows show
        return "gain ÷ secousse du compte", c["reference"] * r52, c["value"] * r52
    s = v["values"]["fp"]["portfolio_weekly_sharpe_frozen_factor"]
    return "gain ÷ secousse du compte", s[0], s[1]


def main():
    src, out = sys.argv[1], sys.argv[2]
    rehearsal = "--rehearsal" in sys.argv
    d = json.load(open(src))
    years = d["windows"]["years"] if isinstance(d.get("windows"), dict) and "years" in d["windows"] else None
    span = f"{years[0]}–{years[-1]}" if years else "?"
    cf = d.get("check_first", {})
    V = d["verdicts"]
    kept = [c for c in ORDER if V.get(c, {}).get("adopted") is True]

    fig = plt.figure(figsize=(6, 13.4), dpi=200)
    W, H = fig.get_size_inches()
    L = 0.055
    title = "Le test final des 8 corrections" if not rehearsal else "Répétition du test (années de recherche)"
    fig.text(L, 0.975, title, fontsize=15.5, fontweight="bold", va="top")
    sub = (f"Trades de {span}, que ces corrections n'ont jamais vus." if not rehearsal
           else f"Trades de {span} : les années qui ont servi à choisir les corrections.")
    fig.text(L, 0.948, sub, fontsize=10.5, color=INK2, va="top")
    fig.text(L, 0.930, f"{len(kept)} gardée{'s' if len(kept) > 1 else ''} sur 8.", fontsize=12.5, fontweight="bold", va="top")
    if cf and not cf.get("passed", False):
        fig.text(L, 0.912, "Contrôle de départ ÉCHOUÉ : rien n'est jugé.", fontsize=11, color=BAD, fontweight="bold", va="top")

    # ---------------------------------------------------------------- the eight rows
    top, row_h = 0.892, 0.066
    for i, cid in enumerate(ORDER):
        v = V.get(cid, {})
        y = top - i * row_h
        ok = v.get("adopted") is True
        market, what = NAMES[cid]
        fig.patches.append(Rectangle((L - 0.012, y - row_h + 0.008), 1 - 2 * L + 0.024, row_h - 0.008, transform=fig.transFigure,
                                     facecolor=TINT if ok else SURF, edgecolor=GRID, lw=0.8, zorder=0))
        fig.text(L, y - 0.010, market, fontsize=11, fontweight="bold", va="top")
        fig.text(L, y - 0.028, what, fontsize=10, color=INK2, va="top")
        mark = "✓ gardée" if ok else "✗ rejetée"
        fig.text(1 - L, y - 0.010, mark, fontsize=11, fontweight="bold", color=GOOD if ok else BAD, ha="right", va="top")
        lab, b, a = key_number(cid, v)
        fig.text(L, y - 0.047, f"{lab} : {num(b)} → {num(a)}", fontsize=9.6, color=INK2, va="top")
        if not ok:
            ft = failed_tests(v)
            if ft:
                fig.text(1 - L, y - 0.047, "raté : " + ", ".join(ft[:3]), fontsize=9, color=INK2, ha="right", va="top")

    # ---------------------------------------------------------------- the account, before / after
    y0 = top - 8 * row_h - 0.026
    fig.text(L, y0, "Le compte entier : gain ÷ secousse", fontsize=12.5, fontweight="bold", va="top")
    fig.text(L, y0 - 0.020, "par semaine, à secousse égale (plus haut = mieux)", fontsize=9.6, color=INK2, va="top")
    groups = []
    comp = d.get("comparisons", {}).get("P2_vs_P0", {}).get("fp/lab/sum")
    if comp:
        groups.append(("Les 3 changements crypto (K1, K2 et K3 ensemble)", comp["ref"]["weekly_sharpe"], comp["var_equal_swing"]["weekly_sharpe"],
                       "avec les 3"))
    sa = d.get("synthesis_A", {}).get("together_vs_unchanged_headline", {}).get("fp", {})
    if sa.get("weekly_sharpe_unchanged_vs_together_equal_swing"):
        u, t = sa["weekly_sharpe_unchanged_vs_together_equal_swing"]
        n = len(sa.get("passing", []))
        if n:
            groups.append((f"Les stops et sorties gardés ({n} sur 5, ensemble)", u, t, "avec"))
        else:
            groups.append(("Les stops et sorties : aucun gardé", u, u, "avec"))
    allv = [x for g_ in groups for x in g_[1:3]]
    mx = max(allv) * 1.16 if allv else 1.0
    y = y0 - 0.052
    gh = 0.082
    for gi, (head, before, after, lab_after) in enumerate(groups):
        fig.text(L, y, head, fontsize=10.2, fontweight="bold", va="top")
        ax = fig.add_axes([L + 0.13, y - 0.074, 1 - 2 * L - 0.20, 0.052])
        for j, (lab, val, col) in enumerate((("sans", before, BLUE_T), (lab_after, after, BLUE))):
            yy = 1 - j
            ax.barh(yy, val, height=0.62, color=col, zorder=3)
            ax.text(val + mx * 0.015, yy, num(val), va="center", fontsize=10.5, fontweight="bold", color=INK)
            ax.text(-0.015, yy, lab, transform=ax.get_yaxis_transform(), ha="right", va="center", fontsize=9.6, color=INK2)
        ax.set_xlim(0, mx)
        ax.set_ylim(-0.55, 1.55)
        ax.axis("off")
        y -= gh
    fig.text(L, y + 0.004, "« sans » = les 10 règles d'aujourd'hui, mesurées par chaque famille à sa façon.\n"
             "Les deux familles ensemble ne sont pas mesurées par ce test.", fontsize=8.6, color=MUTED, va="top", linespacing=1.3)
    foot = ("Coûts FP Markets du labo, 1 R par trade. Ce sont des simulations, aucun trade réel :\n"
            "ce qui est gardé passe d'abord par le compte démo.")
    if rehearsal:
        foot = "RÉPÉTITION sur les années de recherche : sert seulement à vérifier l'image.\n" + foot
    fig.text(L, 0.012, foot, fontsize=8.4, color=MUTED, va="bottom", linespacing=1.35)
    fig.savefig(out)
    plt.close(fig)
    print("kept:", kept)


if __name__ == "__main__":
    main()
