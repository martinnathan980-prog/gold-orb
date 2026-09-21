"""Assistant interactif : construit un scénario à partir d'un relevé d'écran et
des colonnes de l'Excel, par questions/réponses dans la console.

Tout se passe sur le poste de l'utilisateur : aucune donnée ne sort.
"""

from __future__ import annotations

import difflib
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from . import symboles as S
from .gabarit import normaliser_cle
from .releve import selecteur_suggere

MOTS_ENREGISTRER = ("enregistr", "valid", "sauvegard", "soumettre", "save", "submit", "confirm", "creer", "créer", "ajouter", "ok")
MOTS_IGNORER_BOUTON = ("annul", "cancel", "retour", "fermer", "supprim", "delete", "reset", "connect", "recherch", "search")


class Dialogue:
    """Pose des questions dans la console ; `reponses` permet de les scripter (tests)."""

    def __init__(self, reponses: Optional[Iterable[str]] = None) -> None:
        self.reponses = list(reponses) if reponses is not None else None
        self.journal: List[str] = []

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


def _bouton_par_defaut(boutons: List[Dict[str, Any]]) -> Optional[int]:
    for i, b in enumerate(boutons):
        t = normaliser_cle(b.get("texte", ""))
        if any(m in t for m in MOTS_ENREGISTRER) and not any(m in t for m in MOTS_IGNORER_BOUTON):
            return i
    return None


def construire(
    releve: Dict[str, Any],
    colonnes: Sequence[str],
    dialogue: Dialogue,
    nom: Optional[str] = None,
    fichier_excel: str = "suivi.xlsx",
    feuille: Optional[str] = None,
) -> str:
    """Pose les questions et renvoie le texte YAML du scénario."""
    elements = [e for e in releve["elements"] if e.get("visible") and not e.get("desactive")]
    champs = [e for e in elements if not e.get("bouton") and e.get("tag") != "a"]
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
    d.dire("   Pour chaque champ, indiquez la colonne Excel qui le remplit (numéro), « v » pour une valeur fixe, 0 pour l'ignorer.")
    d.dire("   Entrée = accepter la proposition entre crochets.")

    etapes: List[str] = []
    for e in champs:
        etiquette = _etiquette(e)
        sel = selecteur_suggere(e)
        if sel.startswith("("):
            d.dire(f"   (champ « {etiquette} » sans sélecteur fiable : ignoré, voir champs.txt)")
            continue
        genre = e.get("tag")
        if genre == "input":
            genre = f"input {e.get('type') or 'text'}"
        d.dire()
        d.dire(f"{S.FLECHE} Champ « {etiquette} »  ({genre}, sélecteur {sel})")
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
        valeur: Optional[str] = None
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
                d.dire(f"   {S.ATTENTION} « {reponse_brute} » ne correspond à aucune colonne : champ ignoré.")
                continue
            valeur = "{{" + colonnes[correspondance] + "}}"
        if e.get("tag") == "select":
            etapes.append(f"  - choisir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}")
        elif e.get("type") == "checkbox" or e.get("role") == "checkbox":
            etapes.append(f"  - cocher: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}")
        elif e.get("type") == "radio":
            etapes.append(f"  - cliquer: {_yaml_chaine(sel)}")
        elif e.get("type") == "file":
            etapes.append(f"  - televerser: {{selecteur: {_yaml_chaine(sel)}, fichier: {_yaml_chaine(valeur)}}}")
        elif e.get("type") == "date":
            etapes.append(f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur.replace('}}', ' | date:%Y-%m-%d}}') if valeur.startswith('{{') else valeur)}}}   # champ date HTML : format AAAA-MM-JJ")
        else:
            etapes.append(f"  - remplir: {{selecteur: {_yaml_chaine(sel)}, valeur: {_yaml_chaine(valeur)}}}")

    # bouton d'enregistrement
    d.dire()
    bouton_sel: Optional[str] = None
    if boutons:
        d.dire(f"{S.FLECHE} Quel bouton enregistre le formulaire ?")
        for i, b in enumerate(boutons, start=1):
            d.dire(f"     {i}. « {b['texte']} »  ({selecteur_suggere(b)})")
        defaut = _bouton_par_defaut(boutons)
        reponse = d.demander("   Numéro du bouton (0 = aucun clic)", str(defaut + 1) if defaut is not None else "0")
        if reponse.isdigit() and 1 <= int(reponse) <= len(boutons):
            bouton_sel = selecteur_suggere(boutons[int(reponse) - 1])
    else:
        reponse = d.demander(f"{S.FLECHE} Sélecteur du bouton qui enregistre (vide = aucun clic)", "")
        bouton_sel = reponse or None

    pause = d.oui_non(f"{S.FLECHE} Garder une pause de vérification avant le clic final (recommandé pour les premiers essais) ?", True)
    texte_succes = d.demander(f"{S.FLECHE} Texte affiché par l'outil quand l'enregistrement a réussi (vide = pas de contrôle)", "")
    sel_reference = d.demander(f"{S.FLECHE} Sélecteur de la référence attribuée à relever dans l'Excel (vide = aucune)", "")
    colonne_reference = d.demander("   Colonne Excel où l'écrire", "Référence outil") if sel_reference else ""
    connexion = d.oui_non(f"{S.FLECHE} Faut-il se connecter à la main au début (SSO, mot de passe) ?", True)
    capture = d.oui_non(f"{S.FLECHE} Faire une capture d'écran après chaque ligne ?", True)

    lignes = [
        f"# Scénario généré par « autoweb assistant » — à relire, puis :",
        f"#   python -m autoweb verifier <ce fichier>",
        f"#   python -m autoweb simuler <ce fichier>",
        f"#   python -m autoweb lancer <ce fichier> --limite 1",
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
    lignes += [
        "variables:",
        f"  url: {_yaml_chaine(releve.get('url', ''))}",
    ]
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
    if texte_succes:
        lignes.append(f"  - verifier: {{texte_page: {_yaml_chaine(texte_succes)}}}")
    if sel_reference:
        lignes.append(f"  - lire: {{selecteur: {_yaml_chaine(sel_reference)}, vers: {_yaml_chaine(colonne_reference)}}}")
    if capture:
        premiere = colonnes[0] if colonnes else "ligne"
        lignes.append(f"  - capture: \"captures/{{{{{premiere}}}}}.png\"")
    return "\n".join(lignes) + "\n"
