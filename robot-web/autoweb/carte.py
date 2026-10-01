"""Repères de la carte (E5, C1, K7) : traduits, sur le poste, en éléments précis du portail.

Le fichier à partager ne cite que des repères. Une tâche écrite à partir de ce fichier dit par
exemple « carte=20261001-101500/E5/C1 » (le champ C1 de l'écran E5 de cette carte) ; le robot
retrouve dans SA carte (carte.json, qui reste sur le poste) l'élément précis : identifiant,
nom technique, libellé, texte du bouton. Les noms techniques ne quittent donc jamais le poste.

« ecran: 20261001-101500/E5 » rejoue le chemin noté pendant l'exploration pour revenir sur
l'écran E5 (menus, onglets, recherche).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .erreurs import ErreurEtape

DOSSIER_EXPLORATIONS = Path(__file__).resolve().parent.parent / "explorations"
# « 20261001-101500/E5/C1 », « E5/K7 » (dernière carte), « 20261001-101500/E5 »
MOTIF_REPERE = re.compile(r"^(?:(?P<carte>[\w.-]+)/)?(?P<ecran>E\d+)(?:/(?P<element>[CKT]\d+))?$", re.IGNORECASE)
PREFIXE = "carte="

_cache: Dict[Path, Tuple[float, Dict[str, Any]]] = {}


def est_repere(selecteur: Any) -> bool:
    return str(selecteur or "").strip().lower().startswith(PREFIXE)


def _fichiers_cartes(dossier: Optional[Path] = None) -> List[Path]:
    racine = dossier or DOSSIER_EXPLORATIONS
    return sorted(racine.glob("*/carte.json")) if racine.is_dir() else []


def charger_carte(ident: Optional[str] = None, dossier: Optional[Path] = None) -> Dict[str, Any]:
    """La carte nommée (dossier de l'exploration), sinon la plus récente qui a des repères."""
    racine = dossier or DOSSIER_EXPLORATIONS
    if ident:
        chemin = racine / ident / "carte.json"
        if not chemin.is_file():
            raise ErreurEtape(f"la carte « {ident} » n'est pas sur ce poste (dossier explorations). "
                              "Refaites la carte (menu, choix 8) ou demandez une tâche pour la carte actuelle.")
        candidats = [chemin]
    else:
        candidats = list(reversed(_fichiers_cartes(racine)))
        if not candidats:
            raise ErreurEtape("aucune carte du portail sur ce poste : faites d'abord la carte (menu, choix 8).")
    for chemin in candidats:
        try:
            date = chemin.stat().st_mtime
            if chemin in _cache and _cache[chemin][0] == date:
                return _cache[chemin][1]
            donnees = json.loads(chemin.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if ident or donnees.get("reperes"):
            donnees.setdefault("id", chemin.parent.name)
            _cache[chemin] = (date, donnees)
            return donnees
    raise ErreurEtape("aucune carte avec des repères (E5, C1...) sur ce poste : refaites la carte (menu, choix 8).")


def decouper_repere(texte: str) -> Tuple[Optional[str], str, Optional[str]]:
    brut = str(texte or "").strip()
    if brut.lower().startswith(PREFIXE):
        brut = brut[len(PREFIXE):].strip()
    m = MOTIF_REPERE.match(brut)
    if not m:
        raise ErreurEtape(f"repère de carte illisible : « {texte} » (attendu par exemple carte=E5/C1).")
    return m.group("carte"), m.group("ecran").upper(), (m.group("element") or "").upper() or None


def ecran_de(carte: Dict[str, Any], ident: str) -> Dict[str, Any]:
    for ecran in carte.get("ecrans", []):
        if str(ecran.get("id", "")).upper() == ident:
            return ecran
    raise ErreurEtape(f"l'écran {ident} n'existe pas dans la carte {carte.get('id', '')}.")


def _guillemets(valeur: str) -> str:
    return '"' + str(valeur).replace("\\", "\\\\").replace('"', '\\"') + '"'


def selecteur_champ(champ: Dict[str, Any]) -> str:
    nom = str(champ.get("nom") or "").strip()
    if nom:
        return f"[id={_guillemets(nom)}], [name={_guillemets(nom)}]"
    if champ.get("libelle") and champ.get("source") in ("label", "aria"):
        return f"libelle={champ['libelle']}"
    if champ.get("chemin"):
        return str(champ["chemin"])
    raise ErreurEtape("ce champ n'a ni identifiant ni libellé : montrez-le au robot (menu, choix 1).")


def selecteur_cible(cible: Dict[str, Any]) -> str:
    ident = str(cible.get("id") or "").strip()
    if ident and re.fullmatch(r"[A-Za-z_][\w:.-]*", ident) and not re.search(r"\d{4,}", ident):
        return f"[id={_guillemets(ident)}]"
    technique = str(cible.get("testid") or "").strip()
    if technique:
        g = _guillemets(technique)
        return f"[data-testid={g}], [data-test={g}], [name={g}]"
    texte = str(cible.get("texte") or cible.get("aria") or "").strip()
    if texte and cible.get("zone") != "tableau":
        role = cible.get("role") or ""
        if role in ("tab", "menuitem", "treeitem", "option", "link", "button"):
            return f"role={role}:{texte}"
        if cible.get("tag") == "a":
            return f"role=link:{texte}"
        if cible.get("tag") in ("button", "input"):
            return f"role=button:{texte}"
        return f"texte_exact={texte}"
    if cible.get("selecteur"):
        return str(cible["selecteur"])
    raise ErreurEtape("cet élément ne peut pas être retrouvé (composant web) : montrez-le au robot (menu, choix 1).")


def selecteur(repere: str, dossier: Optional[Path] = None) -> str:
    """« carte=E5/C1 » -> sélecteur utilisable par le robot (« [id="txtNum"], [name="txtNum"] »)."""
    ident, ecran_id, element = decouper_repere(repere)
    if not element:
        raise ErreurEtape(f"« {repere} » désigne un écran, pas un champ ou un bouton (ajoutez /C1, /K7...).")
    carte = charger_carte(ident, dossier)
    ecran = ecran_de(carte, ecran_id)
    rang = int(element[1:]) - 1
    if element[0] == "C":
        champs = ecran.get("champs") or []
        if not 0 <= rang < len(champs):
            raise ErreurEtape(f"le champ {element} n'existe pas sur l'écran {ecran_id}.")
        return selecteur_champ(champs[rang])
    if element[0] == "K":
        cibles = ecran.get("cibles") or []
        if not 0 <= rang < len(cibles):
            raise ErreurEtape(f"l'élément {element} n'existe pas sur l'écran {ecran_id}.")
        return selecteur_cible(cibles[rang])
    if element[0] == "T":  # un tableau : pour « si: {tableau: carte=E9/T1, colonne: Statut, ligne_contient: Validé} »
        tableaux = ecran.get("tableaux") or []
        if not 0 <= rang < len(tableaux) or not tableaux[rang].get("selecteur"):
            raise ErreurEtape(f"le tableau {element} n'existe pas sur l'écran {ecran_id} (ou il n'a pas de repère).")
        return str(tableaux[rang]["selecteur"])
    raise ErreurEtape(f"repère « {element} » inconnu.")


def chemin_vers(repere: str, dossier: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Les pas notés pendant l'exploration pour arriver sur l'écran (aller, clic, chercher)."""
    ident, ecran_id, _ = decouper_repere(repere)
    carte = charger_carte(ident, dossier)
    return list(ecran_de(carte, ecran_id).get("chemin") or [])
