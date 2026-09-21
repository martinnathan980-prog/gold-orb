"""Assistant interactif : construit un scénario à partir d'un relevé d'écran et
des colonnes de l'Excel, par questions/réponses dans la console.

Deux types de scénario :
  1. remplir un formulaire et enregistrer (une ligne Excel = une fiche) ;
  2. appliquer des filtres puis exporter / télécharger un fichier.

Tout se passe sur le poste de l'utilisateur : aucune donnée ne sort.
"""

from __future__ import annotations

import difflib
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import symboles as S
from .gabarit import normaliser_cle
from .releve import selecteur_suggere

MOTS_ENREGISTRER = ("enregistr", "valid", "sauvegard", "soumettre", "save", "submit", "confirm", "creer", "créer", "ajouter", "ok")
MOTS_RECHERCHER = ("recherch", "filtr", "appliquer", "search", "afficher", "actualiser", "go")
MOTS_EXPORTER = ("export", "telecharg", "télécharg", "csv", "excel", "xls", "download", "extraire", "extract")
MOTS_IGNORER_BOUTON = ("annul", "cancel", "retour", "fermer", "supprim", "delete", "reset", "reinit", "réinit", "connect", "deconnex", "déconnex")


class Dialogue:
    """Pose des questions dans la console ; `reponses` permet de les scripter (tests)."""

    def __init__(self, reponses: Optional[Iterable[str]] = None) -> None:
        self.reponses = list(reponses) if reponses is not None else None

    def dire(self, texte: str = "") -> None:
        print(texte)

    def demander(self, question: str, defaut: str = "") -> str:
        invite = f"{question} [{defaut}] : " if defaut else f"{question} : "
        if self.reponses is not None:
            reponse = self.reponses.pop(0) if self.reponses else ""
            print(invite + reponse)
        else:
            print(invite, end="", flush=True)
            try:
                reponse = input()
            except EOFError:
                reponse = ""
        reponse = reponse.strip()
        return reponse if reponse else defaut

    def oui_non(self, question: str, defaut: bool) -> bool:
        reponse = self.demander(f"{question} (o/n)", "o" if defaut else "n").lower()
        return reponse in ("o", "oui", "y", "yes")


def _etiquette(e: Dict[str, Any]) -> str:
    return (e.get("libelle") or e.get("placeholder") or e.get("name") or e.get("id") or "champ").strip().rstrip(" :*")


def _nom_colonne_propose(etiquette: str, colonnes: Sequence[str]) -> Optional[int]:
    """Index (0-based) de la colonne Excel la plus proche de l'étiquette, ou None."""
    if not colonnes:
        return None
    cible = normaliser_cle(etiquette)
    normalisees = [normaliser_cle(c) for c in colonnes]
    if cible in normalisees:
        return normalisees.index(cible)
    for i, c in enumerate(normalisees):
        if cible and (cible in c or c in cible) and min(len(c), len(cible)) >= 4:
            return i
    proches = difflib.get_close_matches(cible, normalisees, n=1, cutoff=0.7)
    return normalisees.index(proches[0]) if proches else None


def _yaml_chaine(texte: str) -> str:
    return '"' + texte.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _bouton_par_defaut(boutons: List[Dict[str, Any]], mots: Sequence[str]) -> Optional[int]:
    for i, b in enumerate(boutons):
        t = normaliser_cle(b.get("texte", ""))
        if any(m in t for m in mots) and not any(m in t for m in MOTS_IGNORER_BOUTON):
            return i
    return None


def _choisir_bouton(d: Dialogue, boutons: List[Dict[str, Any]], question: str, mots: Sequence[str]) -> Optional[str]:
    if boutons:
        d.dire(f"{S.FLECHE} {question}")
        for i, b in enumerate(boutons, start=1):
            etat = "  (désactivé pour l'instant)" if b.get("desactive") else ""
            d.dire(f"     {i}. « {b['texte']} »  ({selecteur_suggere(b)}){etat}")
        defaut = _bouton_par_defaut(boutons, mots)
        reponse = d.demander("   Numéro du bouton (0 = aucun)", str(defaut + 1) if defaut is not None else "0")
        if reponse.isdigit() and 1 <= int(reponse) <= len(boutons):
            return selecteur_suggere(boutons[int(reponse) - 1])
        return None
    reponse = d.demander(f"{S.FLECHE} {question} : sélecteur du bouton (vide = aucun)", "")
    return reponse or None


def _etape_champ(e: Dict[str, Any], sel: str, valeur: str) -> Optional[str]:
    if e.get("tag") == "select":
        return f"  - choisir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}"
    if e.get("type") == "checkbox" or e.get("role") == "checkbox":
        return f"  - cocher: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}"
    if e.get("type") == "radio":
        return f"  - cliquer: {_yaml_chaine(sel)}"
    if e.get("type") == "file":
        return f"  - televerser: {{selecteur: {_yaml_chaine(sel)}, fichier: {_yaml_chaine(valeur)}}}"
    if e.get("type") == "date":
        if valeur.startswith("{{"):
            valeur = valeur[:-2].rstrip() + " | date:%Y-%m-%d}}"
        return f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}   # champ date HTML : AAAA-MM-JJ"
    return f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}"


def _questions_champs(d: Dialogue, champs: List[Dict[str, Any]], colonnes: Sequence[str], mot: str) -> List[str]:
    """Pour chaque champ visible : quelle colonne Excel (ou valeur fixe) le remplit ?"""
    etapes: List[str] = []
    for e in champs:
        etiquette = _etiquette(e)
        sel = selecteur_suggere(e)
        if sel.startswith("("):
            d.dire(f"   ({mot} « {etiquette} » sans sélecteur fiable : ignoré, voir champs.txt)")
            continue
        genre = e.get("tag")
        if genre == "input":
            genre = f"input {e.get('type') or 'text'}"
        d.dire()
        d.dire(f"{S.FLECHE} {mot} « {etiquette} »  ({genre}, sélecteur {sel})")
        if e.get("options"):
            d.dire("   options : " + " ; ".join(e["options"][:10]) + (" ; ..." if len(e["options"]) > 10 else ""))
        if e.get("type") == "password":
            if d.oui_non("   Mot de passe : le saisir au lancement avec --var mot_de_passe=... ?", True):
                etapes.append(f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: \"{{{{mot_de_passe}}}}\"}}")
            continue
        if colonnes:
            for i, c in enumerate(colonnes, start=1):
                d.dire(f"     {i}. {c}")
            propose = _nom_colonne_propose(etiquette, colonnes)
            defaut = str(propose + 1) if propose is not None else "0"
            reponse_brute = d.demander("   Colonne Excel (numéro), v = valeur fixe, 0 = ignorer", defaut)
        else:
            reponse_brute = d.demander("   Nom de la colonne Excel (vide = ignorer, v = valeur fixe)", "")
        reponse = reponse_brute.lower()
        if reponse in ("", "0", "n", "non"):
            continue
        if reponse in ("v", "valeur", "fixe"):
            fixe = d.demander("   Valeur fixe à saisir", "")
            if not fixe:
                continue
            valeur = fixe
        elif colonnes and reponse.isdigit() and 1 <= int(reponse) <= len(colonnes):
            valeur = "{{" + colonnes[int(reponse) - 1] + "}}"
        elif not colonnes:
            valeur = "{{" + reponse_brute + "}}"
        else:
            correspondance = _nom_colonne_propose(reponse_brute, colonnes)
            if correspondance is None:
                d.dire(f"   {S.ATTENTION} « {reponse_brute} » ne correspond à aucune colonne : {mot.lower()} ignoré.")
                continue
            valeur = "{{" + colonnes[correspondance] + "}}"
        etape = _etape_champ(e, sel, valeur)
        if etape:
            etapes.append(etape)
    return etapes


def construire(
    releve: Dict[str, Any],
    colonnes: Sequence[str],
    dialogue: Dialogue,
    nom: Optional[str] = None,
    fichier_excel: str = "suivi.xlsx",
    feuille: Optional[str] = None,
) -> str:
    """Pose les questions et renvoie le texte YAML du scénario."""
    elements = [e for e in releve["elements"] if e.get("visible")]
    champs = [e for e in elements if not e.get("bouton") and e.get("tag") != "a" and not e.get("desactive")]
    boutons = [e for e in elements if e.get("bouton") and e.get("texte")]
    nom = nom or releve.get("nom") or releve.get("titre") or "scenario"
    base = re.sub(r"[^a-z0-9_-]+", "_", nom.lower()).strip("_") or "outil"
    d = dialogue

    d.dire()
    d.dire(f"{S.LIGNE} Assistant de scénario : « {nom} »")
    d.dire(f"   Écran relevé : {releve.get('titre', '')}  ({releve.get('url', '')})")
    d.dire(f"   {len(champs)} champ(s) visible(s), {len(boutons)} bouton(s).")
    if colonnes:
        d.dire("   Colonnes Excel : " + ", ".join(colonnes))
    d.dire("   Entrée = accepter la proposition entre crochets.")
    d.dire()
    d.dire(f"{S.FLECHE} Que doit faire ce scénario ?")
    d.dire("     1. Remplir un formulaire et enregistrer (une ligne Excel = une fiche)")
    d.dire("     2. Appliquer des filtres puis exporter / télécharger un fichier (une ligne Excel = un export)")
    export = d.demander("   Choix", "1").startswith("2")
    url = d.demander(f"{S.FLECHE} Adresse ouverte pour chaque ligne (vous pouvez y insérer {{{{Colonne}}}})", releve.get("url", ""))

    d.dire()
    if export:
        d.dire("   Pour chaque filtre, indiquez la colonne Excel qui donne sa valeur (numéro), « v » pour une valeur fixe, 0 pour ne pas y toucher.")
    else:
        d.dire("   Pour chaque champ, indiquez la colonne Excel qui le remplit (numéro), « v » pour une valeur fixe, 0 pour l'ignorer.")
    etapes = _questions_champs(d, champs, colonnes, "Filtre" if export else "Champ")
    d.dire()

    premiere = colonnes[0] if colonnes else "ligne"
    lignes_fin: List[str] = []
    if export:
        bouton_recherche = _choisir_bouton(d, boutons, "Quel bouton applique les filtres / lance la recherche ?", MOTS_RECHERCHER)
        bouton_export = _choisir_bouton(d, boutons, "Quel bouton exporte / télécharge ?", MOTS_EXPORTER)
        dossier = d.demander(f"{S.FLECHE} Dossier où enregistrer les fichiers (ex. exports, ou %USERPROFILE%\\Desktop)", "exports")
        renommer = d.demander(f"{S.FLECHE} Nom du fichier, sans extension (vide = nom donné par l'outil)", f"export_{{{{{premiere}}}}}" if colonnes else "")
        convertir = d.oui_non(f"{S.FLECHE} Convertir un export CSV en Excel (.xlsx) ?", True)
        vers_colonne = d.demander(f"{S.FLECHE} Colonne Excel où écrire le chemin du fichier obtenu (vide = aucune)", "Fichier export")
        connexion = d.oui_non(f"{S.FLECHE} Faut-il se connecter à la main au début (SSO, mot de passe) ?", True)
        pause = False
        if bouton_recherche:
            lignes_fin.append(f"  - cliquer: {_yaml_chaine(bouton_recherche)}")
            lignes_fin.append("  - attendre: {chargement: reseau, delai: 5000}   # laisse les résultats se charger")
            lignes_fin.append("    optionnel: true")
        if bouton_export:
            options = [f"cliquer: {_yaml_chaine(bouton_export)}", f"vers: {_yaml_chaine(dossier.rstrip('/') + '/')}"]
            if renommer:
                options.append(f"renommer: {_yaml_chaine(renommer)}")
            if convertir:
                options.append("convertir_excel: true")
            if vers_colonne:
                options.append(f"vers_colonne: {_yaml_chaine(vers_colonne)}")
            lignes_fin.append("  - telecharger: {" + ", ".join(options) + "}")
        else:
            lignes_fin.append("  # - telecharger: {cliquer: \"role=button:Exporter\", vers: \"exports/\", convertir_excel: true}")
        capture = False
        texte_succes = ""
        sel_reference = ""
        colonne_reference = ""
        bouton_sel = None
    else:
        bouton_sel = _choisir_bouton(d, boutons, "Quel bouton enregistre le formulaire ?", MOTS_ENREGISTRER)
        pause = d.oui_non(f"{S.FLECHE} Garder une pause de vérification avant le clic final (recommandé pour les premiers essais) ?", True)
        texte_succes = d.demander(f"{S.FLECHE} Texte affiché par l'outil quand l'enregistrement a réussi (vide = pas de contrôle)", "")
        sel_reference = d.demander(f"{S.FLECHE} Sélecteur de la référence attribuée à relever dans l'Excel (vide = aucune)", "")
        colonne_reference = d.demander("   Colonne Excel où l'écrire", "Référence outil") if sel_reference else ""
        connexion = d.oui_non(f"{S.FLECHE} Faut-il se connecter à la main au début (SSO, mot de passe) ?", True)
        capture = d.oui_non(f"{S.FLECHE} Faire une capture d'écran après chaque ligne ?", True)

    lignes = [
        "# Scénario généré par « autoweb assistant » — à relire, puis :",
        "#   python -m autoweb verifier <ce fichier>",
        "#   python -m autoweb simuler <ce fichier>",
        "#   python -m autoweb lancer <ce fichier> --limite 1",
        f"nom: {_yaml_chaine(nom)}",
        "navigateur:",
        "  canal: chrome",
        f"  profil: profils/{base}",
        "  visible: true",
        "  delai_max: 15000",
        "excel:",
        f"  fichier: {_yaml_chaine(fichier_excel)}",
    ]
    if feuille:
        lignes.append(f"  feuille: {_yaml_chaine(feuille)}")
    if colonnes:
        lignes.append(f"  colonne_libelle: {_yaml_chaine(colonnes[0])}")
    lignes += ["variables:", f"  url: {_yaml_chaine(url)}"]
    if connexion:
        lignes += [
            "avant:",
            "  - aller: \"{{url}}\"",
            "  - pause: \"Connectez-vous dans le navigateur si nécessaire, puis appuyez sur Entrée\"",
        ]
    lignes += ["etapes:", "  - aller: \"{{url}}\""]
    lignes += etapes
    if pause:
        lignes.append("  - pause: \"Vérifiez le formulaire à l'écran puis appuyez sur Entrée (stop pour arrêter)\"   # à retirer une fois validé")
    if bouton_sel:
        lignes.append(f"  - cliquer: {_yaml_chaine(bouton_sel)}")
    lignes += lignes_fin
    if texte_succes:
        lignes.append(f"  - verifier: {{texte_page: {_yaml_chaine(texte_succes)}}}")
    if sel_reference:
        lignes.append(f"  - lire: {{selecteur: {_yaml_chaine(sel_reference)}, vers: {_yaml_chaine(colonne_reference)}}}")
    if capture:
        lignes.append(f"  - capture: \"captures/{{{{{premiere}}}}}.png\"")
    return "\n".join(lignes) + "\n"
