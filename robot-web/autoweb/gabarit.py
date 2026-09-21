"""Gabarits : remplacement des {{colonne}} par les valeurs de la ligne Excel.

Syntaxe :
    {{ Numéro plan }}                       valeur de la colonne « Numéro plan »
    {{ Date | date:%d/%m/%Y }}              filtre appliqué à la valeur
    {{ Commentaire | defaut:RAS }}          valeur de secours si vide/absente
    {{ Code | majuscules | sans_espaces }}  filtres chaînés

La recherche de colonne ignore la casse, les accents et les espaces en trop :
{{numero plan}} trouve la colonne « Numéro plan ».
"""

from __future__ import annotations

import datetime as dt
import re
import unicodedata
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from .erreurs import ErreurGabarit

MOTIF = re.compile(r"\{\{(.*?)\}\}", re.DOTALL)

VRAIS = {"oui", "o", "yes", "y", "true", "vrai", "v", "x", "1", "ok", "✓", "✔"}
FAUX = {"", "non", "n", "no", "false", "faux", "f", "0", "-"}

FILTRES_CONNUS = (
    "defaut", "majuscules", "minuscules", "date", "entier", "nombre", "virgule",
    "point", "sans_espaces", "tronquer", "brut", "ouinon", "texte",
)


def normaliser_cle(nom: Any) -> str:
    """« Numéro  Plan » -> « numero plan » (sans accents, sans casse, espaces réduits)."""
    texte = unicodedata.normalize("NFKD", str(nom))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", texte).strip().lower()


def formater(valeur: Any) -> str:
    """Convertit une valeur de cellule Excel en texte « naturel » pour un formulaire.

    - None -> ""            - 5.0 -> "5"           - True -> "oui"
    - datetime(2026,9,21) -> "21/09/2026" (heure ajoutée seulement si non nulle)
    """
    if valeur is None:
        return ""
    if isinstance(valeur, str):
        return valeur.strip()
    if isinstance(valeur, bool):
        return "oui" if valeur else "non"
    if isinstance(valeur, int):
        return str(valeur)
    if isinstance(valeur, float):
        if valeur.is_integer():
            return str(int(valeur))
        return repr(valeur)
    if isinstance(valeur, dt.datetime):
        if valeur.hour == 0 and valeur.minute == 0 and valeur.second == 0:
            return valeur.strftime("%d/%m/%Y")
        return valeur.strftime("%d/%m/%Y %H:%M")
    if isinstance(valeur, dt.date):
        return valeur.strftime("%d/%m/%Y")
    if isinstance(valeur, dt.time):
        return valeur.strftime("%H:%M")
    return str(valeur).strip()


def est_vrai(valeur: Any) -> bool:
    """Interprète une case Excel comme un oui/non (oui, x, 1, vrai, true... = oui)."""
    if valeur is None:
        return False
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, (int, float)):
        return valeur != 0
    texte = normaliser_cle(valeur)
    if texte in VRAIS:
        return True
    if texte in FAUX:
        return False
    return bool(texte)


def parser_date(texte: str) -> Optional[dt.datetime]:
    """Essaie les formats de date courants (français puis ISO)."""
    texte = texte.strip()
    if not texte:
        return None
    for fmt in ("%d/%m/%Y", "%d/%m/%Y %H:%M", "%d/%m/%y", "%d-%m-%Y", "%d.%m.%Y",
                "%Y-%m-%d", "%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return dt.datetime.strptime(texte, fmt)
        except ValueError:
            continue
    return None


def chercher(nom: str, contexte: Dict[str, Any]) -> Tuple[bool, Any]:
    """Cherche une clé dans le contexte, d'abord exacte puis de façon tolérante."""
    if nom in contexte:
        return True, contexte[nom]
    cible = normaliser_cle(nom)
    for cle, valeur in contexte.items():
        if normaliser_cle(cle) == cible:
            return True, valeur
    return False, None


def _appliquer_filtre(valeur: Any, nom: str, arg: str) -> Any:
    if nom == "defaut":
        return arg if formater(valeur) == "" else valeur
    if nom == "texte":
        return formater(valeur)
    if nom == "brut":
        return "" if valeur is None else str(valeur)
    if nom == "majuscules":
        return formater(valeur).upper()
    if nom == "minuscules":
        return formater(valeur).lower()
    if nom == "sans_espaces":
        return re.sub(r"\s+", "", formater(valeur))
    if nom == "virgule":
        return formater(valeur).replace(".", ",")
    if nom == "point":
        return formater(valeur).replace(",", ".")
    if nom == "ouinon":
        return "oui" if est_vrai(valeur) else "non"
    if nom == "tronquer":
        try:
            n = int(arg)
        except ValueError:
            raise ErreurGabarit(f"Filtre tronquer : longueur invalide « {arg} » (attendu un entier).")
        return formater(valeur)[:n]
    if nom == "date":
        fmt = arg or "%d/%m/%Y"
        if isinstance(valeur, (dt.datetime, dt.date)):
            return valeur.strftime(fmt)
        texte = formater(valeur)
        if not texte:
            return ""
        date = parser_date(texte)
        if date is None:
            raise ErreurGabarit(f"Filtre date : impossible d'interpréter « {texte} » comme une date.")
        return date.strftime(fmt)
    if nom == "entier":
        texte = formater(valeur)
        if not texte:
            return ""
        try:
            return str(int(float(texte.replace(",", ".").replace(" ", ""))))
        except ValueError:
            raise ErreurGabarit(f"Filtre entier : « {texte} » n'est pas un nombre.")
    if nom == "nombre":
        texte = formater(valeur)
        if not texte:
            return ""
        try:
            decimales = int(arg) if arg else 2
            return f"{float(texte.replace(',', '.').replace(' ', '')):.{decimales}f}"
        except ValueError:
            raise ErreurGabarit(f"Filtre nombre : « {texte} » n'est pas un nombre.")
    raise ErreurGabarit(
        f"Filtre inconnu « {nom} ». Filtres disponibles : {', '.join(FILTRES_CONNUS)}."
    )


def _decouper_expression(contenu: str) -> Tuple[str, list]:
    """« Date | date:%d/%m/%Y | majuscules » -> ("Date", [("date", "%d/%m/%Y"), ("majuscules", "")])"""
    parties = [p.strip() for p in contenu.split("|")]
    nom = parties[0]
    filtres = []
    for partie in parties[1:]:
        if not partie:
            continue
        nom_filtre, _, arg = partie.partition(":")
        filtres.append((nom_filtre.strip().lower(), arg.strip()))
    return nom, filtres


def rendre(texte: str, contexte: Dict[str, Any], strict: bool = True) -> str:
    """Remplace tous les {{...}} de `texte` avec les valeurs de `contexte`.

    strict=False laisse tel quel un {{gabarit}} dont la colonne est absente
    (utile pour afficher un aperçu) au lieu de lever ErreurGabarit.
    """
    if "{{" not in texte:
        return texte

    def remplacer(m: "re.Match[str]") -> str:
        nom, filtres = _decouper_expression(m.group(1))
        if not nom:
            raise ErreurGabarit(f"Gabarit vide : « {m.group(0)} ».")
        trouve, valeur = chercher(nom, contexte)
        if not trouve:
            defauts = [arg for (f, arg) in filtres if f == "defaut"]
            if defauts:
                valeur = None
            elif not strict:
                return m.group(0)
            else:
                disponibles = ", ".join(sorted(str(c) for c in contexte.keys())) or "(aucune)"
                raise ErreurGabarit(
                    f"Colonne ou variable introuvable : « {nom} ». Disponibles : {disponibles}."
                )
        if not filtres:
            return formater(valeur)
        for nom_filtre, arg in filtres:
            valeur = _appliquer_filtre(valeur, nom_filtre, arg)
        # après un filtre, une chaîne est rendue telle quelle (« brut » ne doit pas être retouché)
        return valeur if isinstance(valeur, str) else formater(valeur)

    return MOTIF.sub(remplacer, texte)


def rendre_structure(objet: Any, contexte: Dict[str, Any], strict: bool = True) -> Any:
    """Rend récursivement les chaînes d'un dict / d'une liste. Les autres objets sont conservés."""
    if isinstance(objet, str):
        return rendre(objet, contexte, strict)
    if isinstance(objet, dict):
        return {rendre_structure(k, contexte, strict): rendre_structure(v, contexte, strict)
                for k, v in objet.items()}
    if isinstance(objet, list):
        return [rendre_structure(v, contexte, strict) for v in objet]
    return objet


def noms_utilises(objet: Any) -> Set[str]:
    """Ensemble des noms de colonnes/variables référencés par les {{...}} d'une structure."""
    noms: Set[str] = set()

    def parcourir(o: Any) -> None:
        if isinstance(o, str):
            for m in MOTIF.finditer(o):
                nom, _ = _decouper_expression(m.group(1))
                if nom:
                    noms.add(nom)
        elif isinstance(o, dict):
            for k, v in o.items():
                parcourir(k)
                parcourir(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                parcourir(v)
        elif hasattr(o, "args"):  # une Etape normalisée
            parcourir(getattr(o, "args"))

    parcourir(objet)
    return noms


def noms_avec_defaut(objet: Any) -> Set[str]:
    """Noms référencés uniquement avec un filtre `defaut` (donc tolérés absents)."""
    noms: Set[str] = set()

    def parcourir(o: Any) -> None:
        if isinstance(o, str):
            for m in MOTIF.finditer(o):
                nom, filtres = _decouper_expression(m.group(1))
                if nom and any(f == "defaut" for f, _ in filtres):
                    noms.add(nom)
        elif isinstance(o, dict):
            for k, v in o.items():
                parcourir(k)
                parcourir(v)
        elif isinstance(o, (list, tuple)):
            for v in o:
                parcourir(v)
        elif hasattr(o, "args"):
            parcourir(getattr(o, "args"))

    parcourir(objet)
    return noms


def manquants(objet: Any, disponibles: Iterable[str]) -> Set[str]:
    """Noms référencés par les gabarits qui ne correspondent à aucune colonne/variable."""
    connus = {normaliser_cle(c) for c in disponibles}
    toleres = noms_avec_defaut(objet)
    return {n for n in noms_utilises(objet)
            if normaliser_cle(n) not in connus and n not in toleres}
