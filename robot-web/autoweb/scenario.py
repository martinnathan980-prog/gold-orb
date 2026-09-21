"""Chargement et validation d'un scénario YAML.

Un scénario décrit :
- `navigateur` : comment ouvrir le navigateur (Edge/Chrome déjà installé, profil...)
- `excel`      : quel fichier de suivi et quelles colonnes de statut
- `variables`  : valeurs réutilisables dans les gabarits ({{url_base}}...)
- `avant`      : étapes exécutées une fois au début (connexion...)
- `etapes`     : étapes exécutées pour CHAQUE ligne de l'Excel
- `apres`      : étapes exécutées une fois à la fin

Chaque étape est une action en français (`remplir`, `cliquer`, `attendre`...)
avec ses paramètres. Les alias anglais sont acceptés.
"""

from __future__ import annotations

import difflib
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from .erreurs import ErreurScenario

# ----------------------------------------------------------------------------- actions
# action canonique -> alias acceptés
ALIAS: Dict[str, Tuple[str, ...]] = {
    "aller": ("goto", "ouvrir", "naviguer", "url"),
    "attendre": ("wait", "wait_for", "attendre_element"),
    "patienter": ("sleep", "temporiser", "pause_ms", "delai"),
    "remplir": ("fill", "saisir", "ecrire", "renseigner"),
    "taper": ("type", "frapper", "taper_lentement"),
    "effacer": ("clear", "vider"),
    "cliquer": ("click", "appuyer", "bouton"),
    "choisir": ("select", "selectionner", "liste"),
    "cocher": ("check", "case"),
    "decocher": ("uncheck",),
    "touche": ("press", "clavier", "key"),
    "survoler": ("hover",),
    "televerser": ("upload", "joindre", "fichier_joint"),
    "telecharger": ("download",),
    "capture": ("screenshot", "capture_ecran", "photo"),
    "lire": ("read", "recuperer", "extraire_texte", "relever"),
    "verifier": ("expect", "controler", "assert", "verifier_texte"),
    "verifier_url": ("expect_url", "controler_url"),
    "journal": ("log", "message", "afficher", "note"),
    "pause": ("manuel", "attendre_utilisateur", "confirmer"),
    "inspecter": ("inspect", "debug", "inspector"),
    "executer_js": ("evaluate", "js", "script", "javascript"),
    "si": ("if", "condition"),
    "cadre": ("frame", "iframe"),
    "onglet": ("tab", "page", "fenetre"),
    "fermer_onglet": ("close_tab", "fermer_fenetre"),
    "retour": ("back", "precedent"),
    "recharger": ("reload", "rafraichir", "actualiser"),
    "ignorer": ("skip", "passer"),
    "echouer": ("fail", "erreur"),
    "arreter": ("stop", "abort", "abandonner"),
}
ACTIONS: Dict[str, str] = {}
for _canon, _alias in ALIAS.items():
    ACTIONS[_canon] = _canon
    for _a in _alias:
        ACTIONS[_a] = _canon

# clés facultatives acceptées à côté de l'action dans une étape
META_ETAPE = ("nom", "optionnel", "delai_max", "commentaire", "description", "secret")

# valeurs à masquer dans les journaux (sélecteur ou gabarit évoquant un mot de passe)
MOTIF_SECRET = re.compile(r"pass|mdp|mot.?de.?passe|pwd|secret|token|jeton|credential|identifiant", re.I)
MASQUE = "•••••"

CLES_SCENARIO = ("nom", "description", "navigateur", "excel", "variables", "avant", "etapes", "apres")
CLES_NAVIGATEUR = (
    "canal", "profil", "visible", "attacher", "delai_max", "lenteur", "largeur", "hauteur",
    "executable", "dialogues", "telechargements", "arguments", "ignorer_https",
)
CLES_EXCEL = (
    "fichier", "feuille", "ligne_entete", "colonne_statut", "colonne_message",
    "colonne_horodatage", "colonne_libelle", "traiter_si", "entre_lignes_ms",
)
CANAUX = ("auto", "msedge", "chrome", "chromium")
DIALOGUES = ("accepter", "refuser", "ignorer")

CLES_CONDITION = ("present", "absent", "visible", "cache", "valeur", "egal", "different",
                  "contient", "vide", "non_vide", "vrai", "faux", "delai")


# ----------------------------------------------------------------------------- structures
@dataclass
class ConfigNavigateur:
    canal: str = "auto"
    profil: Optional[str] = None
    visible: bool = True
    attacher: Optional[str] = None
    delai_max: int = 15000
    lenteur: int = 0
    largeur: int = 1400
    hauteur: int = 900
    executable: Optional[str] = None
    dialogues: str = "accepter"
    telechargements: str = "telechargements"
    arguments: List[str] = field(default_factory=list)
    ignorer_https: bool = False


@dataclass
class ConfigExcel:
    fichier: Optional[str] = None
    feuille: Optional[str] = None
    ligne_entete: int = 1
    colonne_statut: str = "Statut"
    colonne_message: str = "Message"
    colonne_horodatage: str = "Horodatage"
    colonne_libelle: Optional[str] = None
    traiter_si: List[str] = field(default_factory=lambda: ["", "A faire"])
    entre_lignes_ms: int = 0


@dataclass
class Etape:
    action: str
    args: Dict[str, Any]
    nom: Optional[str] = None
    optionnel: bool = False
    delai_max: Optional[int] = None
    position: str = ""  # ex. "etapes[3]" pour les messages d'erreur
    secret: bool = False  # masquer les valeurs dans les journaux

    def resume(self) -> str:
        if self.nom:
            return self.nom
        morceaux = []
        for cle in ("selecteur", "url", "fichier", "valeur", "touche", "chemin", "message", "vers", "contient"):
            if cle in self.args and not isinstance(self.args[cle], (dict, list)):
                texte = str(self.args[cle])
                if len(texte) > 60:
                    texte = texte[:57] + "..."
                morceaux.append(f"{cle}={texte}")
        if "champs" in self.args and isinstance(self.args["champs"], dict):
            for selecteur, valeur in self.args["champs"].items():
                texte = str(valeur)
                if len(texte) > 40:
                    texte = texte[:37] + "..."
                morceaux.append(f"{selecteur} ← « {texte} »")
        return f"{self.action} " + ", ".join(morceaux) if morceaux else self.action


@dataclass
class Scenario:
    nom: str
    chemin: Path
    description: str = ""
    navigateur: ConfigNavigateur = field(default_factory=ConfigNavigateur)
    excel: ConfigExcel = field(default_factory=ConfigExcel)
    variables: Dict[str, Any] = field(default_factory=dict)
    avant: List[Etape] = field(default_factory=list)
    etapes: List[Etape] = field(default_factory=list)
    apres: List[Etape] = field(default_factory=list)

    @property
    def dossier(self) -> Path:
        return self.chemin.parent


# ----------------------------------------------------------------------------- aide
def _suggestion(nom: str, candidats: Any) -> str:
    proches = difflib.get_close_matches(str(nom), [str(c) for c in candidats], n=1, cutoff=0.6)
    return f" Vouliez-vous dire « {proches[0]} » ?" if proches else ""


def _suggestion_action(nom: str) -> str:
    """Propose d'abord un nom d'action français, puis un alias."""
    return _suggestion(nom, ALIAS.keys()) or _suggestion(nom, ACTIONS.keys())


def masquer_secrets(args_rendus: Dict[str, Any], etape: "Etape") -> Dict[str, Any]:
    """Copie des paramètres rendus où les valeurs sensibles sont remplacées par •••••.

    Une valeur est masquée si l'étape porte `secret: true`, si le sélecteur évoque
    un mot de passe (#mot-de-passe, input[name=password]...) ou si le gabarit
    d'origine référence une variable sensible ({{mdp}}, {{mot_de_passe}}...).
    """
    def sensible(selecteur: Any, brut: Any) -> bool:
        if etape.secret:
            return True
        return bool(MOTIF_SECRET.search(str(selecteur))) or bool(MOTIF_SECRET.search(str(brut)))

    resultat = dict(args_rendus)
    bruts = etape.args
    if isinstance(resultat.get("champs"), dict):
        champs_bruts = list(bruts.get("champs", {}).items()) if isinstance(bruts.get("champs"), dict) else []
        masques: Dict[str, Any] = {}
        for i, (selecteur, valeur) in enumerate(resultat["champs"].items()):
            brut = champs_bruts[i][1] if i < len(champs_bruts) else ""
            masques[selecteur] = MASQUE if sensible(selecteur, brut) else valeur
        resultat["champs"] = masques
    if "valeur" in resultat and sensible(resultat.get("selecteur", ""), bruts.get("valeur", "")):
        resultat["valeur"] = MASQUE
    if etape.secret:
        for cle in ("url", "script", "message"):
            if cle in resultat:
                resultat[cle] = MASQUE
    return resultat


def _verifier_cles(donnees: Dict[str, Any], autorisees: Tuple[str, ...], contexte: str) -> None:
    for cle in donnees:
        if cle not in autorisees:
            raise ErreurScenario(
                f"{contexte} : clé inconnue « {cle} ».{_suggestion(cle, autorisees)} "
                f"Clés possibles : {', '.join(autorisees)}."
            )


def _entier(valeur: Any, contexte: str) -> int:
    try:
        return int(valeur)
    except (TypeError, ValueError):
        raise ErreurScenario(f"{contexte} : entier attendu, reçu « {valeur} ».")


def _booleen(valeur: Any, contexte: str) -> bool:
    if isinstance(valeur, bool):
        return valeur
    if isinstance(valeur, str) and valeur.strip().lower() in ("oui", "true", "vrai", "1", "yes"):
        return True
    if isinstance(valeur, str) and valeur.strip().lower() in ("non", "false", "faux", "0", "no"):
        return False
    raise ErreurScenario(f"{contexte} : oui/non attendu, reçu « {valeur} ».")


# ----------------------------------------------------------------------------- étapes
def _normaliser_args(action: str, valeur: Any, position: str) -> Dict[str, Any]:
    """Transforme la forme courte (`cliquer: "#ok"`) en dictionnaire de paramètres."""
    if valeur is None or valeur is True:
        return {}
    if isinstance(valeur, dict):
        if action == "remplir" and "selecteur" not in valeur and "champs" not in valeur:
            # forme compacte : {"#a": "...", "#b": "..."}
            return {"champs": dict(valeur)}
        return dict(valeur)
    if isinstance(valeur, list):
        if action == "remplir":
            champs: Dict[str, Any] = {}
            for elt in valeur:
                if not isinstance(elt, dict) or "selecteur" not in elt or "valeur" not in elt:
                    raise ErreurScenario(f"{position} : chaque élément de « remplir » doit avoir selecteur et valeur.")
                champs[str(elt["selecteur"])] = elt["valeur"]
            return {"champs": champs}
        raise ErreurScenario(f"{position} : une liste n'est pas acceptée pour « {action} ».")
    # scalaire (chaîne ou nombre)
    if action == "aller":
        return {"url": str(valeur)}
    if action == "attendre":
        if isinstance(valeur, (int, float)):
            return {"ms": valeur}
        return {"selecteur": str(valeur)}
    if action == "patienter":
        return {"ms": valeur}
    if action in ("cliquer", "effacer", "survoler", "cocher", "decocher", "verifier", "lire"):
        return {"selecteur": str(valeur)}
    if action == "touche":
        return {"touche": str(valeur)}
    if action == "capture":
        return {"chemin": str(valeur)}
    if action in ("journal", "pause", "ignorer", "echouer", "arreter"):
        return {"message": str(valeur)}
    if action == "executer_js":
        return {"script": str(valeur)}
    if action == "verifier_url":
        return {"contient": str(valeur)}
    if action == "onglet":
        return {"index": valeur}
    if action == "cadre":
        return {"selecteur": str(valeur)}
    if action in ("inspecter", "recharger", "retour", "fermer_onglet"):
        return {}
    raise ErreurScenario(f"{position} : « {action} » attend un dictionnaire de paramètres, pas « {valeur} ».")


def _exiger(args: Dict[str, Any], cles: Tuple[str, ...], position: str, action: str, au_moins_une: bool = False) -> None:
    presentes = [c for c in cles if c in args and args[c] is not None]
    if au_moins_une:
        if not presentes:
            raise ErreurScenario(f"{position} : « {action} » attend au moins un de : {', '.join(cles)}.")
        return
    for cle in cles:
        if cle not in args or args[cle] is None:
            raise ErreurScenario(f"{position} : « {action} » attend le paramètre « {cle} ».")


def _valider_args(action: str, args: Dict[str, Any], position: str) -> None:
    a = action
    if a == "aller":
        _exiger(args, ("url", "fichier"), position, a, au_moins_une=True)
    elif a == "attendre":
        _exiger(args, ("selecteur", "ms", "url", "chargement"), position, a, au_moins_une=True)
    elif a == "patienter":
        _exiger(args, ("ms",), position, a)
    elif a == "remplir":
        if "champs" in args:
            if not isinstance(args["champs"], dict) or not args["champs"]:
                raise ErreurScenario(f"{position} : « remplir » : « champs » doit être un dictionnaire selecteur -> valeur.")
        else:
            _exiger(args, ("selecteur", "valeur"), position, a)
    elif a in ("taper",):
        _exiger(args, ("selecteur", "valeur"), position, a)
    elif a in ("effacer", "cliquer", "survoler", "cocher", "decocher", "cadre"):
        _exiger(args, ("selecteur",), position, a)
    elif a == "choisir":
        _exiger(args, ("selecteur",), position, a)
        _exiger(args, ("valeur", "libelle", "index"), position, a, au_moins_une=True)
    elif a == "touche":
        _exiger(args, ("touche",), position, a)
    elif a == "televerser":
        _exiger(args, ("selecteur", "fichier"), position, a)
    elif a == "telecharger":
        _exiger(args, ("cliquer",), position, a)
    elif a == "capture":
        _exiger(args, ("chemin",), position, a)
    elif a == "lire":
        _exiger(args, ("selecteur",), position, a)
        _exiger(args, ("vers",), position, a)
    elif a == "verifier":
        _exiger(args, ("selecteur", "texte_page"), position, a, au_moins_une=True)
    elif a == "verifier_url":
        _exiger(args, ("contient", "egal"), position, a, au_moins_une=True)
    elif a in ("journal", "ignorer", "echouer", "arreter"):
        _exiger(args, ("message",), position, a)
    elif a == "executer_js":
        _exiger(args, ("script",), position, a)
    elif a == "si":
        _verifier_cles({k: v for k, v in args.items() if k not in ("alors", "sinon")}, CLES_CONDITION, position + " (si)")
        if not any(k in args for k in CLES_CONDITION if k != "delai"):
            raise ErreurScenario(f"{position} : « si » attend une condition ({', '.join(CLES_CONDITION)}).")
        if "alors" not in args and "sinon" not in args:
            raise ErreurScenario(f"{position} : « si » attend « alors » et/ou « sinon » (listes d'étapes).")
    elif a == "onglet":
        _exiger(args, ("index", "titre", "url"), position, a, au_moins_une=True)
    # pause, inspecter, recharger, retour, fermer_onglet : rien d'obligatoire


def normaliser_etape(brut: Any, position: str) -> Etape:
    """Transforme une étape YAML en `Etape` (action canonique + paramètres validés)."""
    if isinstance(brut, str):
        # `- recharger` ou `- inspecter`
        action = ACTIONS.get(brut.strip().lower())
        if action is None:
            raise ErreurScenario(
                f"{position} : action inconnue « {brut} ».{_suggestion_action(brut)}"
            )
        return Etape(action=action, args=_normaliser_args(action, None, position), position=position)
    if not isinstance(brut, dict) or not brut:
        raise ErreurScenario(
            f"{position} : une étape doit être de la forme « - action: paramètres » (reçu : {brut!r})."
        )
    cles_action = [k for k in brut if k not in META_ETAPE]
    if len(cles_action) != 1:
        if not cles_action:
            raise ErreurScenario(f"{position} : aucune action trouvée dans l'étape {brut!r}.")
        raise ErreurScenario(
            f"{position} : une seule action par étape ({', '.join(map(str, cles_action))}). "
            "Mettez chaque action sur sa propre ligne commençant par « - »."
        )
    cle = str(cles_action[0])
    action = ACTIONS.get(cle.strip().lower())
    if action is None:
        raise ErreurScenario(
            f"{position} : action inconnue « {cle} ».{_suggestion_action(cle)} "
            f"Actions possibles : {', '.join(sorted(ALIAS))}."
        )
    args = _normaliser_args(action, brut[cle], position)
    # sous-étapes (si / cadre)
    for sous in ("alors", "sinon", "etapes"):
        if sous in args:
            if not isinstance(args[sous], list):
                raise ErreurScenario(f"{position} : « {sous} » doit être une liste d'étapes.")
            args[sous] = [normaliser_etape(e, f"{position}.{sous}[{i + 1}]") for i, e in enumerate(args[sous])]
    _valider_args(action, args, position)
    if action == "cadre" and "etapes" not in args:
        raise ErreurScenario(f"{position} : « cadre » attend « etapes » (liste d'étapes à exécuter dans l'iframe).")

    optionnel = _booleen(brut.get("optionnel", False), position + " (optionnel)")
    secret = _booleen(brut.get("secret", False), position + " (secret)")
    delai_max = _entier(brut["delai_max"], position + " (delai_max)") if brut.get("delai_max") is not None else None
    nom = brut.get("nom") or brut.get("description") or None
    return Etape(action=action, args=args, nom=str(nom) if nom else None,
                 optionnel=optionnel, delai_max=delai_max, position=position, secret=secret)


def normaliser_etapes(brut: Any, section: str) -> List[Etape]:
    if brut is None:
        return []
    if not isinstance(brut, list):
        raise ErreurScenario(f"« {section} » doit être une liste d'étapes (chaque étape commence par « - »).")
    return [normaliser_etape(e, f"{section}[{i + 1}]") for i, e in enumerate(brut)]


# ----------------------------------------------------------------------------- chargement
def charger_config_navigateur(donnees: Any) -> ConfigNavigateur:
    if donnees is None:
        return ConfigNavigateur()
    if not isinstance(donnees, dict):
        raise ErreurScenario("« navigateur » doit être un dictionnaire de réglages.")
    _verifier_cles(donnees, CLES_NAVIGATEUR, "navigateur")
    cfg = ConfigNavigateur()
    if "canal" in donnees:
        canal = str(donnees["canal"]).strip().lower()
        if canal == "edge":
            canal = "msedge"
        if canal not in CANAUX:
            raise ErreurScenario(f"navigateur.canal : « {canal} » inconnu. Possibles : {', '.join(CANAUX)}.")
        cfg.canal = canal
    if donnees.get("profil"):
        cfg.profil = str(donnees["profil"])
    if "visible" in donnees:
        cfg.visible = _booleen(donnees["visible"], "navigateur.visible")
    if donnees.get("attacher"):
        cfg.attacher = str(donnees["attacher"])
    if "delai_max" in donnees:
        cfg.delai_max = _entier(donnees["delai_max"], "navigateur.delai_max")
    if "lenteur" in donnees:
        cfg.lenteur = _entier(donnees["lenteur"], "navigateur.lenteur")
    if "largeur" in donnees:
        cfg.largeur = _entier(donnees["largeur"], "navigateur.largeur")
    if "hauteur" in donnees:
        cfg.hauteur = _entier(donnees["hauteur"], "navigateur.hauteur")
    if donnees.get("executable"):
        cfg.executable = str(donnees["executable"])
    if "dialogues" in donnees:
        d = str(donnees["dialogues"]).strip().lower()
        if d not in DIALOGUES:
            raise ErreurScenario(f"navigateur.dialogues : « {d} » inconnu. Possibles : {', '.join(DIALOGUES)}.")
        cfg.dialogues = d
    if donnees.get("telechargements"):
        cfg.telechargements = str(donnees["telechargements"])
    if "arguments" in donnees:
        if not isinstance(donnees["arguments"], list):
            raise ErreurScenario("navigateur.arguments doit être une liste de chaînes.")
        cfg.arguments = [str(a) for a in donnees["arguments"]]
    if "ignorer_https" in donnees:
        cfg.ignorer_https = _booleen(donnees["ignorer_https"], "navigateur.ignorer_https")
    return cfg


def charger_config_excel(donnees: Any) -> ConfigExcel:
    if donnees is None:
        return ConfigExcel()
    if not isinstance(donnees, dict):
        raise ErreurScenario("« excel » doit être un dictionnaire de réglages.")
    _verifier_cles(donnees, CLES_EXCEL, "excel")
    cfg = ConfigExcel()
    if donnees.get("fichier"):
        cfg.fichier = str(donnees["fichier"])
    if donnees.get("feuille"):
        cfg.feuille = str(donnees["feuille"])
    if "ligne_entete" in donnees:
        cfg.ligne_entete = _entier(donnees["ligne_entete"], "excel.ligne_entete")
        if cfg.ligne_entete < 1:
            raise ErreurScenario("excel.ligne_entete doit être >= 1.")
    for cle in ("colonne_statut", "colonne_message", "colonne_horodatage"):
        if donnees.get(cle):
            setattr(cfg, cle, str(donnees[cle]))
    if donnees.get("colonne_libelle"):
        cfg.colonne_libelle = str(donnees["colonne_libelle"])
    if "traiter_si" in donnees:
        brut = donnees["traiter_si"]
        if isinstance(brut, str):
            brut = [brut]
        if not isinstance(brut, list):
            raise ErreurScenario("excel.traiter_si doit être une liste de statuts (ex. [\"\", \"A faire\"]).")
        cfg.traiter_si = ["" if v is None else str(v) for v in brut]
    if "entre_lignes_ms" in donnees:
        cfg.entre_lignes_ms = _entier(donnees["entre_lignes_ms"], "excel.entre_lignes_ms")
    return cfg


def charger(chemin: Path) -> Scenario:
    """Charge et valide un scénario YAML. Lève ErreurScenario avec un message clair."""
    chemin = Path(chemin)
    if not chemin.exists():
        raise ErreurScenario(f"Scénario introuvable : {chemin}")
    try:
        with open(chemin, "r", encoding="utf-8") as f:
            donnees = yaml.safe_load(f)
    except yaml.YAMLError as e:
        raise ErreurScenario(f"YAML invalide dans {chemin.name} : {e}")
    except UnicodeDecodeError:
        raise ErreurScenario(f"{chemin.name} n'est pas en UTF-8. Enregistrez-le en UTF-8 (sans BOM de préférence).")
    return depuis_dict(donnees, chemin)


def depuis_dict(donnees: Any, chemin: Path) -> Scenario:
    if not isinstance(donnees, dict):
        raise ErreurScenario(f"{chemin.name} : le scénario doit être un dictionnaire YAML (nom:, etapes:, ...).")
    _verifier_cles(donnees, CLES_SCENARIO, chemin.name)
    if "etapes" not in donnees:
        raise ErreurScenario(f"{chemin.name} : il manque la section « etapes » (liste des étapes par ligne).")
    variables = donnees.get("variables") or {}
    if not isinstance(variables, dict):
        raise ErreurScenario(f"{chemin.name} : « variables » doit être un dictionnaire nom -> valeur.")
    scenario = Scenario(
        nom=str(donnees.get("nom") or chemin.stem),
        chemin=chemin.resolve(),
        description=str(donnees.get("description") or "").strip(),
        navigateur=charger_config_navigateur(donnees.get("navigateur")),
        excel=charger_config_excel(donnees.get("excel")),
        variables={str(k): v for k, v in variables.items()},
        avant=normaliser_etapes(donnees.get("avant"), "avant"),
        etapes=normaliser_etapes(donnees.get("etapes"), "etapes"),
        apres=normaliser_etapes(donnees.get("apres"), "apres"),
    )
    if not scenario.etapes:
        raise ErreurScenario(f"{chemin.name} : la section « etapes » est vide.")
    return scenario


def toutes_les_etapes(etapes: List[Etape]) -> List[Etape]:
    """Aplatit les étapes (y compris alors/sinon/etapes imbriquées)."""
    resultat: List[Etape] = []
    for e in etapes:
        resultat.append(e)
        for sous in ("alors", "sinon", "etapes"):
            if isinstance(e.args.get(sous), list):
                resultat.extend(toutes_les_etapes(e.args[sous]))
    return resultat
