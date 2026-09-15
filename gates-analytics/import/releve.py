#!/usr/bin/env python3
"""
Transforme un export GATES en relevé hebdomadaire.

Le point important : GATES ne donne que l'état du jour. On ne peut pas
reconstituer le passé, seulement l'accumuler. Ce script archive donc un
relevé par import — c'est lui qui fabrique l'historique.

    python releve.py export.csv

Écrit / met à jour deux fichiers dans le dossier `donnees/` :
  - releves.csv   un relevé par import (comptes globaux et par ATA)
  - plans.json    l'avancement plan par plan du dernier import,
                  pour pouvoir comparer au suivant

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import csv
import datetime as dt
import json
import pathlib
import sys
import unicodedata

DOSSIER = pathlib.Path(__file__).resolve().parent / "donnees"
RELEVES = DOSSIER / "releves.csv"
PLANS = DOSSIER / "plans.json"

# Colonnes recherchées dans l'export, par mots-clés (l'ordre des colonnes
# et leur libellé exact peuvent changer d'un export à l'autre).
CLES = {
    "reference": ["reference ud", "reference"],
    "avancement": ["avancement fwd", "realisation fwd", "avancement"],
    "ata": ["ata", "chapitre"],
}


def normaliser(texte):
    """Minuscules, sans accents — pour comparer des en-têtes sans surprise."""
    texte = unicodedata.normalize("NFD", str(texte or ""))
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return " ".join(texte.lower().split())


def trouver_colonne(entetes, mots_cles):
    """Premier en-tête qui contient l'un des mots-clés, par ordre de priorité."""
    normalises = [normaliser(e) for e in entetes]
    for mot in mots_cles:
        for i, e in enumerate(normalises):
            if mot in e:
                return i
    return -1


def classer(valeur):
    """
    Quatre états, exactement comme le tableau de bord.
    « À faire » est une valeur saisie ; une cellule vide est un défaut de
    saisie. Les confondre masquerait le second.
    """
    s = normaliser(valeur)
    if s in ("", "-", "na", "n/a"):
        return "vide"
    if "a faire" in s or s == "non commence":
        return "afaire"
    try:
        n = float(s.replace("%", "").replace(",", ".").replace(" ", ""))
    except ValueError:
        n = None
    if n is not None:
        if n >= 100:
            return "termine"
        if n <= 0:
            return "afaire"
        return "encours"
    if any(m in s for m in ("termine", "acheve", "cloture", "solde", "fini")):
        return "termine"
    return "encours"


def semaine_iso(date):
    annee, semaine, _ = date.isocalendar()
    return "%d-S%02d" % (annee, semaine)


def lire_export(chemin):
    """
    Lit le CSV en trouvant la vraie ligne d'en-tête : les exports placent
    souvent un titre ou une ligne de groupes au-dessus.
    """
    with open(chemin, newline="", encoding="utf-8-sig") as f:
        echantillon = f.read(8192)
        f.seek(0)
        try:
            dialecte = csv.Sniffer().sniff(echantillon, delimiters=";,\t")
        except csv.Error:
            dialecte = csv.excel
            dialecte.delimiter = ";"
        lignes = list(csv.reader(f, dialecte))

    if not lignes:
        raise SystemExit("Export vide : %s" % chemin)

    for i, ligne in enumerate(lignes[:10]):
        if trouver_colonne(ligne, CLES["reference"]) != -1:
            return ligne, lignes[i + 1:]

    raise SystemExit(
        "Colonne « Référence UD » introuvable dans les 10 premières lignes.\n"
        "En-têtes lus : %s" % (lignes[0],)
    )


def construire_releve(entetes, lignes, date):
    idx = {k: trouver_colonne(entetes, m) for k, m in CLES.items()}
    if idx["avancement"] == -1:
        raise SystemExit(
            "Colonne d'avancement FWD introuvable.\n"
            "En-têtes lus : %s" % (entetes,)
        )

    def cellule(ligne, cle):
        i = idx[cle]
        return ligne[i] if 0 <= i < len(ligne) else ""

    releve = {
        "date": date.isoformat(),
        "semaine": semaine_iso(date),
        "total": 0, "termine": 0, "encours": 0, "afaire": 0, "vide": 0,
    }
    par_ata = {}
    plans = {}

    for ligne in lignes:
        if not any(str(c).strip() for c in ligne):
            continue                                    # ligne entièrement vide
        reference = cellule(ligne, "reference").strip()
        if not reference:
            continue
        avancement = cellule(ligne, "avancement").strip()
        etat = classer(avancement)

        releve["total"] += 1
        releve[etat] += 1
        plans[reference] = avancement

        ata = cellule(ligne, "ata").strip() or "—"
        groupe = par_ata.setdefault(ata, {"total": 0, "termine": 0})
        groupe["total"] += 1
        if etat == "termine":
            groupe["termine"] += 1

    releve["par_ata"] = json.dumps(par_ata, ensure_ascii=False, sort_keys=True)
    return releve, plans


def comparer(avant, maintenant):
    """Ce qui a bougé depuis l'import précédent."""
    if not avant:
        return None
    d = {"avances": [], "recules": [], "nouveaux": [], "disparus": [], "renseignes": []}

    def pourcent(v):
        if classer(v) == "termine":
            return 100.0
        if classer(v) in ("vide", "afaire"):
            return 0.0
        try:
            return float(normaliser(v).replace("%", "").replace(",", ".").replace(" ", ""))
        except ValueError:
            return 50.0

    for ref, valeur in maintenant.items():
        if ref not in avant:
            d["nouveaux"].append(ref)
            continue
        if classer(avant[ref]) == "vide" and classer(valeur) != "vide":
            d["renseignes"].append(ref)
        ecart = pourcent(valeur) - pourcent(avant[ref])
        if ecart > 0:
            d["avances"].append(ref)
        elif ecart < 0:
            d["recules"].append(ref)

    d["disparus"] = [r for r in avant if r not in maintenant]
    return d


COLONNES_RELEVE = ["date", "semaine", "total", "termine", "encours", "afaire", "vide", "par_ata"]


def archiver(releve):
    """
    Un relevé par semaine ISO : réimporter le même jour met la ligne à jour
    au lieu d'en empiler une seconde.
    """
    DOSSIER.mkdir(parents=True, exist_ok=True)
    anciens = []
    if RELEVES.exists():
        with open(RELEVES, newline="", encoding="utf-8") as f:
            anciens = [l for l in csv.DictReader(f) if l.get("semaine") != releve["semaine"]]

    with open(RELEVES, "w", newline="", encoding="utf-8") as f:
        ecrivain = csv.DictWriter(f, fieldnames=COLONNES_RELEVE)
        ecrivain.writeheader()
        for ligne in sorted(anciens + [releve], key=lambda l: l["semaine"]):
            ecrivain.writerow({c: ligne.get(c, "") for c in COLONNES_RELEVE})

    return len(anciens) + 1


def main():
    parseur = argparse.ArgumentParser(description="Archive un export GATES en relevé hebdomadaire.")
    parseur.add_argument("export", help="le CSV exporté depuis GATES")
    parseur.add_argument("--date", help="date du relevé (AAAA-MM-JJ), aujourd'hui par défaut")
    args = parseur.parse_args()

    date = dt.date.fromisoformat(args.date) if args.date else dt.date.today()
    entetes, lignes = lire_export(args.export)
    releve, plans = construire_releve(entetes, lignes, date)

    avant = json.loads(PLANS.read_text(encoding="utf-8")) if PLANS.exists() else None
    delta = comparer(avant, plans)

    nb = archiver(releve)
    DOSSIER.mkdir(parents=True, exist_ok=True)
    PLANS.write_text(json.dumps(plans, ensure_ascii=False, indent=1), encoding="utf-8")

    pct = round(releve["termine"] / releve["total"] * 100) if releve["total"] else 0
    print("Relevé %s archivé (%d au total)" % (releve["semaine"], nb))
    print("  %d plans : %d terminés (%d %%), %d en cours, %d à faire, %d non renseignés"
          % (releve["total"], releve["termine"], pct, releve["encours"],
             releve["afaire"], releve["vide"]))
    if delta is None:
        print("  premier import : le comparatif apparaîtra au prochain")
    else:
        print("  depuis le dernier import : %d ont avancé, %d ont reculé, "
              "%d viennent d'être renseignés, %d nouveaux, %d disparus"
              % (len(delta["avances"]), len(delta["recules"]), len(delta["renseignes"]),
                 len(delta["nouveaux"]), len(delta["disparus"])))
        if delta["recules"]:
            print("  ATTENTION, avancement en recul : %s"
                  % ", ".join(sorted(delta["recules"])[:10]))
    print("\n  %s\n  %s" % (RELEVES, PLANS))


if __name__ == "__main__":
    sys.exit(main())
