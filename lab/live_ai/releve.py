"""Relevé des vrais frais du courtier : lecture des fichiers écrits par mql5/ReleveFP.mq5 et comparaison avec le
modèle de frais du labo, aux minutes où les règles entrent.

    python3 live_ai/releve.py modele            (labo) frais du modèle aux minutes d'entrée de chaque règle
                                                -> results/live/modele_frais.json (à faire une fois, données du labo)
    python3 live_ai/releve.py [dossier]         lit le relevé (dossier MQL5/Files/claude/releve trouvé tout seul),
                                                compare au modèle -> results/live/releve_<date>.json
    python3 live_ai/releve.py sonde [marchés]   compte DÉMO seulement : un aller-retour au lot minimum par marché, pour
                                                lire la commission réelle -> results/live/sonde_<date>.json
    python3 live_ai/releve.py faux <dossier>    (test) fabrique un faux relevé à partir des données du labo

Règle fixée d'avance (panel du 2026-11-11, rang 1, étape 1) : toutes les règles ont été testées avec des frais
multipliés par 1,5. Une règle dont les frais mesurés aux minutes de ses signaux dépassent 1,5 fois le modèle passe
« sur le papier » jusqu'à ce qu'elle soit recalculée avec les frais mesurés ; sinon rien ne change.
Aucun résultat de trading n'est calculé ici : seulement des heures d'entrée et des écarts de prix.
"""
import json
import os
import sys
from io import StringIO
from pathlib import Path

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.dirname(HERE)
sys.path.insert(0, LAB)
sys.path.insert(0, HERE)
from pont import Hands, server_to_utc  # noqa: E402

OUT = os.path.join(LAB, "results", "live")
MODELE = os.path.join(OUT, "modele_frais.json")
GRILLE = os.path.join(OUT, "cost_grid.json")     # r2/cost_grid.py : ce que chaque règle supporte comme frais (2013-2021)
BASE2SYM = {"BTCUSD": "btcusd", "ETHUSD": "ethusd", "US100": "us100", "XAUUSD": "xauusd", "USDJPY": "usdjpy",
            "EURUSD": "eurusd", "US500": "us500", "GER40": "ger40"}
SYM2BASE = {v: k for k, v in BASE2SYM.items()}
# commission supposée (aller-retour, en prix par unité) tant qu'elle n'est pas lue sur un vrai aller-retour en démo :
# compte Raw = 3 USD par lot et par côté sur l'or et les devises, rien sur les indices et les cryptos
COMMISSION = {"xauusd": 0.06, "eurusd": 0.00006, "usdjpy": 0.0093}
COLS = ["bo", "bh", "bl", "bc", "ao", "ah", "al", "ac"]
FENETRES = {"USDJPY": [("fixing de Tokyo 00:50-01:00 UTC", 50, 60)], "JP225": [("séance de Tokyo 00:00-06:30 UTC", 0, 390)]}


# ---------------------------------------------------------------------------------------------- lecture du relevé
def kv(path):
    out = {}
    for ln in Path(path).read_text(encoding="latin-1").splitlines():
        if "=" in ln:
            k, v = ln.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def lire_m1(folder, base):
    """Prix vendeur / acheteur minute par minute du courtier, index UTC, colonnes du labo + n, sp_mean, sp_max."""
    df = pd.read_csv(StringIO(Path(folder, f"m1_{base}.csv").read_text(encoding="latin-1")))
    df = df.drop_duplicates("time").sort_values("time")
    df.index = server_to_utc(df.pop("time").to_numpy()).astype("datetime64[ms, UTC]")
    df.index.name = "ts"
    return df[~df.index.duplicated()]


def ecart_pb(df):
    """Écart acheteur - vendeur de chaque minute en points de base (moyenne de l'ouverture et de la clôture)."""
    mid = (df.bo + df.ao) / 2
    return ((df.ao - df.bo) + (df.ac - df.bc)) / 2 / mid * 1e4


def _stats(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    if not len(x):
        return {"n": 0}
    return {"n": int(len(x)), "mediane": round(float(np.median(x)), 3), "moyenne": round(float(x.mean()), 3),
            "p90": round(float(np.quantile(x, 0.9)), 3)}


# ---------------------------------------------------------------------------------------------- règles du labo
def regles():
    """[(nom, marché, make_orders, paramètres)] des règles validées dont les signaux se recalculent sur un simple
    cadre de prix (les deux règles qui ont besoin d'un autre marché ou d'un modèle sont couvertes par leurs
    voisines : mêmes marchés, mêmes cassures)."""
    sys.path.insert(0, os.path.join(LAB, "r2"))
    import recalc
    out = []
    for track, name, sym, mk, params in recalc.sleeves():
        if name in ("nq_btc_follow", "F1_brk_ridge_filter"):
            continue
        out.append((name, sym, mk, params))
    return out


def minutes_entree(frame, sym, mk, params):
    """Heures d'entrée de la règle sur ce cadre (aucun résultat n'est gardé)."""
    from goldlab import r2
    from goldlab.sim import simulate
    t = simulate(frame, mk(frame, **params), sym=sym, costs=r2.GROSS, no_overlap=True)
    return pd.DatetimeIndex(t["entry_time"])


# ---------------------------------------------------------------------------------------------- 1. modèle (labo)
def modele():
    from goldlab import r2
    out = {}
    for sym in sorted({s for _, s, _, _ in regles()} | {"btcusd", "ethusd"}):
        m1 = r2.load(sym)
        sp = ecart_pb(m1)
        last = sp[sp.index >= pd.Timestamp("2025-01-01", tz="UTC")]
        out[f"marche:{sym}"] = {"ecart_pb_2025": _stats(last),
                                "par_heure_utc_2025": {int(h): round(float(v), 3) for h, v in last.groupby(last.index.hour).median().items()}}
        for name in sorted({n for n, s, _, _ in regles() if s == sym} | ({"nq_btc_follow"} if sym == "btcusd" else set())
                           | ({"F1_brk_ridge_filter"} if sym in ("btcusd", "ethusd") else set())):
            p = os.path.join(LAB, "results", "r2", "recalc", "trades", f"{name}__{sym}.parquet")
            if not os.path.exists(p):
                continue
            t = pd.read_parquet(p)
            x = sp.reindex(pd.DatetimeIndex(t.entry_time))
            hours = pd.Series(pd.DatetimeIndex(t.entry_time).hour).value_counts(normalize=True).sort_index()
            out[f"{name}:{sym}"] = {"ecart_pb_aux_entrees": _stats(x.to_numpy()),
                                    "ecart_pb_aux_entrees_2025": _stats(x[x.index >= pd.Timestamp("2025-01-01", tz="UTC")].to_numpy()),
                                    "heures_utc": {int(h): round(float(v), 4) for h, v in hours.items()},
                                    "trades": int(len(t))}
        r2.free()
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(MODELE, "w"), indent=1)
    for k, v in out.items():
        print(k, v.get("ecart_pb_aux_entrees") or v.get("ecart_pb_2025"))


# ---------------------------------------------------------------------------------------------- 2. relevé
def verdict(ratio, rows):
    """ratio = frais mesurés / frais du modèle. Jusqu'à 1,5 : déjà couvert par le test de résistance. Au-delà : on lit
    dans la grille (calculée d'avance sur 2013-2021) si la règle passe encore ses critères à ce niveau de frais."""
    if ratio <= 1.5:
        return "dans la marge"
    if not rows:
        return "AU-DESSUS de 1,5 fois le modèle : sur le papier (grille absente)"
    above = [r for r in rows if r["m"] >= ratio]
    if not above:
        return f"AU-DESSUS de {rows[-1]['m']:g} fois le modèle : sur le papier"
    r = above[0]
    if r["passes_is_bars"]:
        return f"au-dessus de 1,5 fois, mais la règle tient encore avec des frais x{r['m']:g} (PF {r['base']['pf']:.2f})"
    return f"NE TIENT PLUS avec des frais x{r['m']:g} (PF {r['base']['pf']:.2f}, t {r['base']['t_stat']:.2f}) : sur le papier"


def analyser(folder):
    folder = Path(folder)
    fini = kv(folder / "fini.txt") if (folder / "fini.txt").exists() else {}
    fiches = pd.read_csv(StringIO((folder / "fiches.csv").read_text(encoding="latin-1")))
    mod = json.load(open(MODELE)) if os.path.exists(MODELE) else {}
    grille = json.load(open(GRILLE)) if os.path.exists(GRILLE) else {}
    commission = dict(COMMISSION)
    lue = commissions_mesurees()
    commission.update(lue)
    res_com = "lue sur un aller-retour en démo" if lue else "supposée (pas encore de sonde)"
    res = {"serveur": fini.get("server"), "demo": fini.get("demo"), "commission": res_com, "fiches": {}, "marches": {}, "regles": {}}
    print("FICHES DES MARCHÉS")
    for _, f in fiches.iterrows():
        if not isinstance(f["name"], str) or f["name"] == "INTROUVABLE":
            print(f"  {f['base']}: introuvable chez ce courtier")
            continue
        d = {k: (None if pd.isna(f[k]) else f[k].item() if hasattr(f[k], "item") else f[k]) for k in
             ("name", "path", "contract_size", "vol_min", "vol_step", "swap_mode", "swap_long", "swap_short", "margin_1lot",
              "ccy_profit", "bid", "ask", "digits")}
        res["fiches"][f["base"]] = d
        print(f"  {f['base']} -> {d['name']}: lot minimum {d['vol_min']:g} (pas {d['vol_step']:g}), contrat {d['contract_size']:g}, "
              f"marge pour 1 lot {d['margin_1lot']:.0f}, swaps {d['swap_long']:g} / {d['swap_short']:g} (mode {d['swap_mode']})")
    frames = {}
    print("\nÉCART ACHETEUR - VENDEUR MESURÉ (points de base du prix ; médiane, moyenne, 9e décile)")
    for p in sorted(folder.glob("m1_*.csv")):
        base = p.stem[3:]
        df = lire_m1(folder, base)
        if len(df) < 100:
            continue
        frames[base] = df
        sp = ecart_pb(df)
        mid = float(((df.bo + df.ao) / 2).iloc[-1])
        m = {"du": str(df.index[0]), "au": str(df.index[-1]), "minutes": int(len(df)), "prix": mid, "ecart_pb": _stats(sp),
             "ecart_prix_median": round(float(np.median(sp) * mid / 1e4), 6),
             "par_heure_utc": {int(h): round(float(v), 3) for h, v in sp.groupby(sp.index.hour).median().items()}}
        sym = BASE2SYM.get(base)
        ref = mod.get(f"marche:{sym}", {}).get("ecart_pb_2025", {}).get("mediane") if sym else None
        com = commission.get(sym, 0.0) / mid * 1e4 if sym else 0.0
        m["commission_pb"] = round(com, 3)
        m["modele_pb"] = ref
        for label, a, b in FENETRES.get(base, []):
            k = (df.index.hour * 60 + df.index.minute >= a) & (df.index.hour * 60 + df.index.minute < b)
            m[label] = _stats(sp[k])
        res["marches"][base] = m
        s = m["ecart_pb"]
        txt = f"  {base:7s} {s['mediane']:7.2f} {s['moyenne']:7.2f} {s['p90']:7.2f}   ({m['ecart_prix_median']:g} en prix"
        txt += f", + commission {com:.2f}" if com else ""
        txt += f" ; modèle tout compris {ref:.2f}" if ref else ""
        print(txt + f") sur {m['minutes']} minutes du {df.index[0]:%d/%m} au {df.index[-1]:%d/%m}")
        for label, a, b in FENETRES.get(base, []):
            print(f"          {label}: {m[label]}")
    print(f"\nFRAIS AUX MINUTES OÙ LES RÈGLES ENTRENT (mesuré, commission {res_com} comprise, contre le modèle)")
    try:
        rg = regles()
    except Exception as e:  # sans le code du labo : estimation par heure seulement
        rg = []
        print("  (règles du labo indisponibles :", e, ")")
    done = set()
    for name, sym, mk, params in rg:
        base = SYM2BASE.get(sym)
        key = f"{name}:{sym}"
        if base not in frames:
            continue
        done.add(key)
        df = frames[base]
        sp = ecart_pb(df)
        mid = (df.bo + df.ao) / 2
        com = commission.get(sym, 0.0) / mid * 1e4
        r = {"modele": mod.get(key, {}).get("ecart_pb_aux_entrees", {})}
        try:
            te = minutes_entree(df[COLS], sym, mk, params)
            x = (sp + com).reindex(te).to_numpy()
            r["mesure_aux_signaux"] = _stats(x)
            r["pire_ecart_de_la_minute_pb"] = _stats(((df.sp_max / mid * 1e4) + com).reindex(te).to_numpy())
        except Exception as e:
            r["erreur"] = repr(e)[:200]
        hh = mod.get(key, {}).get("heures_utc", {})
        if hh:
            byh = (sp + com).groupby(sp.index.hour).median()
            r["mesure_ponderee_par_heure"] = round(float(sum(float(w) * byh.get(int(h), np.nan) for h, w in hh.items()
                                                             if int(h) in byh.index) / max(sum(float(w) for h, w in hh.items() if int(h) in byh.index), 1e-9)), 3)
        ref = r["modele"].get("mediane")
        got = r.get("mesure_aux_signaux", {})
        mes = got.get("mediane") if got.get("n", 0) >= 10 else r.get("mesure_ponderee_par_heure")
        r["source"] = "signaux rejoués" if got.get("n", 0) >= 10 else "pondération par heure"
        if ref and mes:
            r["ratio"] = round(mes / ref, 2)
            r["verdict"] = verdict(r["ratio"], grille.get(key))
        res["regles"][key] = r
        print(f"  {key:28s} modèle {ref if ref else float('nan'):6.2f} pb | mesuré {mes if mes else float('nan'):6.2f} pb "
              f"({r['source']}, {got.get('n', 0)} signaux) | ratio {r.get('ratio', float('nan')):.2f} -> {r.get('verdict', 'non calculable')}")
    os.makedirs(OUT, exist_ok=True)
    stamp = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    json.dump(res, open(os.path.join(OUT, f"releve_{stamp}.json"), "w"), indent=1, default=str)
    return res


# ---------------------------------------------------------------------------------------------- 3. sonde (démo)
def sonde(bases=("XAUUSD", "US100", "BTCUSD", "ETHUSD", "EURUSD", "USDJPY"), h=None, pause=1.0):
    """Aller-retour au lot minimum, sur un compte DÉMO uniquement, pour lire ce que les fiches ne disent pas : la
    commission réellement prélevée et le prix réellement obtenu. Refuse de tourner sur un compte réel.
    Les marchés doivent figurer dans le réglage InpSymbols de ClaudeMains."""
    import time
    h = h or Hands.find()
    a = h.account()
    if not a["demo"]:
        raise SystemExit("Compte RÉEL : la sonde ne passe d'ordres que sur un compte démo.")
    out = {"serveur": a["server"], "devise": a["currency"], "marches": {}}
    for base in bases:
        s = h.symbols()
        if base not in s.index or not isinstance(s.loc[base, "name"], str):
            out["marches"][base] = {"erreur": "marché absent de ClaudeMains (réglage InpSymbols)"}
            continue
        r = s.loc[base]
        bid, ask, dg = float(r["bid"]), float(r["ask"]), int(r["digits"])
        per_price = float(r["vol_min"]) * float(r["tick_value_loss"] or r["tick_value"]) / float(r["tick_size"])
        dist = 0.004 * a["balance"] / per_price                      # stop à 0,4 % du solde pour le lot minimum
        dist = min(dist, 0.015 * bid)
        floor = max(8 * (ask - bid), float(r["stops_level"]) * float(r["point"]) + 2 * (ask - bid))
        if dist < floor:
            out["marches"][base] = {"erreur": f"lot minimum trop gros pour un stop à 0,4 % du solde (écart {ask - bid:g})"}
            continue
        h.alive()
        o = h.open(base, "buy", volume=float(r["vol_min"]), sl=round(bid - dist, dg), ttl_min=3, tag="sonde")
        if not o["ok"]:
            out["marches"][base] = {"erreur": o.get("reason")}
            continue
        time.sleep(pause)
        h.alive()
        c = h.close(o["ticket"])
        d = None
        for _ in range(int(90 / pause) + 1):                          # au pire deals.csv n'est réécrit qu'une fois par minute
            time.sleep(pause)
            h.alive()
            d = h.deals()
            d = d[d["position"] == o["ticket"]]
            if d["entry"].isin([1, 3]).any():                         # la transaction de sortie est arrivée
                break
        if d is None or not d["entry"].isin([1, 3]).any():
            out["marches"][base] = {"erreur": "sortie non vue dans deals.csv", "ticket": o["ticket"], "fermeture_ok": c.get("ok")}
            continue
        fee = d["fee"] if "fee" in d.columns else 0.0                  # certains courtiers facturent en « fee »
        com = -float((d["commission"] + fee).sum())
        vol = float(o["volume"])
        com_price = com / vol / float(r["tick_value"]) * float(r["tick_size"])
        out["marches"][base] = {
            "nom": r["name"], "volume": vol, "prix_obtenu_achat": o["price"], "prix_obtenu_vente": c.get("price"),
            "ecart_realise": round(o["price"] - c["price"], 8) if c.get("price") else None,
            "fermeture_ok": c["ok"], "transactions": int(len(d)),
            "commission_aller_retour": round(com, 4), "commission_par_lot": round(com / vol, 4),
            "commission_en_prix": round(com_price, 8), "commission_pb": round(com_price / ask * 1e4, 3),
            "resultat": round(float(d["profit"].sum()), 2)}
        m = out["marches"][base]
        print(f"  {base}: {vol:g} lot acheté {o['price']}, revendu {c.get('price')} ; commission aller-retour "
              f"{com:.2f} {a['currency']} = {m['commission_par_lot']:.2f} par lot = {m['commission_pb']:.2f} pb")
    os.makedirs(OUT, exist_ok=True)
    stamp = pd.Timestamp.now("UTC").strftime("%Y-%m-%d")
    json.dump(out, open(os.path.join(OUT, f"sonde_{stamp}.json"), "w"), indent=1, default=str)
    return out


def commissions_mesurees():
    """Commission en prix par unité (aller-retour) lue par la dernière sonde, par marché du labo."""
    import glob
    files = sorted(glob.glob(os.path.join(OUT, "sonde_*.json")))
    if not files:
        return {}
    out = {}
    for base, m in json.load(open(files[-1]))["marches"].items():
        if "commission_en_prix" in m and np.isfinite(m["commission_en_prix"]) and base in BASE2SYM:
            out[BASE2SYM[base]] = float(m["commission_en_prix"])
    return out


# ---------------------------------------------------------------------------------------------- 4. faux relevé (test)
def faux(folder, days=45):
    """Fabrique les fichiers qu'écrirait ReleveFP.mq5, à partir des cadres du labo (fin 2025), heure du serveur."""
    from goldlab import r2
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    rows = ["base,name,path,description,digits,point,tick_size,tick_value,tick_value_loss,contract_size,vol_min,vol_step,vol_max,"
            "calc_mode,exe_mode,spread_float,spread_points,stops_level,swap_mode,swap_long,swap_short,swap_3days,margin_initial,"
            "margin_1lot,ccy_base,ccy_profit,ccy_margin,bid,ask,tick_time,sessions"]
    fini = ["version=1.00", "server=TEST", "demo=1"]
    for base in ("BTCUSD", "ETHUSD", "US100", "XAUUSD"):
        sym = BASE2SYM[base]
        m1 = r2.load(sym)
        m1 = m1[m1.index >= m1.index[-1] - pd.Timedelta(days=days)]
        utc = m1.index.tz_convert("UTC").tz_localize(None)
        ny = m1.index.tz_convert("America/New_York").tz_localize(None)
        srv = (ny + pd.Timedelta(hours=7)).astype("datetime64[s]").astype("int64")
        d = pd.DataFrame({"time": srv})
        for c in COLS:
            d[c] = m1[c].to_numpy()
        d["n"] = 10
        d["sp_mean"] = ((m1.ao - m1.bo) + (m1.ac - m1.bc)).to_numpy() / 2
        d["sp_max"] = np.maximum(m1.ao - m1.bo, m1.ac - m1.bc).to_numpy()
        d.iloc[::-1].to_csv(folder / f"m1_{base}.csv", index=False)
        rows.append(f"{base},{base},Test\\{base},test,2,0.01,0.01,1,1,1,0.01,0.01,100,0,0,1,10,0,1,-5,-1,3,0,100,USD,USD,USD,"
                    f"{m1.bc.iloc[-1]:.2f},{m1.ac.iloc[-1]:.2f},{int(srv[-1])},1:0-1440|")
        fini.append(f"{base}={base} jours={days} minutes={len(d)}")
        r2.free()
        assert len(utc) == len(d)
    (folder / "fiches.csv").write_text("\n".join(rows) + "\n", encoding="latin-1")
    (folder / "fini.txt").write_text("\n".join(fini) + "\n", encoding="latin-1")
    print("faux relevé écrit dans", folder)


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "modele":
        modele()
    elif a and a[0] == "faux":
        faux(a[1])
    elif a and a[0] == "sonde":
        sonde(tuple(a[1:]) or ("XAUUSD", "US100", "BTCUSD", "ETHUSD", "EURUSD", "USDJPY"))
    else:
        analyser(a[0] if a else Hands.find().dir / "releve")
