"""Boucle principale : pour chaque ligne Excel à traiter, exécuter les étapes,
puis écrire le résultat dans l'Excel et sauvegarder.

Résilience :
- chaque ligne est indépendante : une erreur marque la ligne ERREUR et on passe
  à la suivante (sauf --arret-premiere-erreur) ;
- l'Excel est sauvegardé après chaque ligne : Ctrl+C ou plantage => on relance
  la même commande et le robot reprend là où il en était (lignes « A faire ») ;
- capture d'écran automatique dans captures/erreurs/ à chaque erreur.
"""

from __future__ import annotations

import datetime as dt
import logging
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from . import symboles as S
from .actions import Executeur
from .erreurs import (
    ArretDemande, ErreurAutoweb, ErreurEtape, ErreurExcel, ErreurGabarit, LigneIgnoree, NavigateurFerme,
)
from .excel import STATUT_ERREUR, STATUT_IGNORE, STATUT_OK, ClasseurSuivi, Ligne
from .gabarit import manquants, normaliser_cle, rendre, rendre_structure
from .navigateur import Navigateur
from .scenario import Etape, Scenario, masquer_secrets, toutes_les_etapes

journal = logging.getLogger("autoweb")

VARIABLES_SPECIALES = ("ligne", "n", "total", "aujourdhui", "maintenant", "horodatage", "fichier_telecharge")


@dataclass
class Options:
    excel: Optional[Path] = None
    simuler: bool = False
    limite: Optional[int] = None
    lignes: Optional[Set[int]] = None  # numéros de lignes Excel à traiter
    reprendre_erreurs: bool = False
    tout: bool = False  # ignorer le filtre de statut (retraiter même les OK)
    visible: Optional[bool] = None
    inspecter_si_erreur: bool = False
    arret_premiere_erreur: bool = False
    variables: Dict[str, Any] = field(default_factory=dict)
    sans_avant: bool = False
    sans_apres: bool = False
    interactif: bool = True


@dataclass
class Bilan:
    total: int = 0
    ok: int = 0
    erreurs: int = 0
    ignorees: int = 0
    interrompu: bool = False
    simule: bool = False
    message: str = ""
    lignes_fichier: int = 0  # lignes de données présentes dans l'Excel, traitées ou non
    sans_excel: bool = False  # tâche jouée une fois, sans liste

    @property
    def tout_deja_fait(self) -> bool:
        """Rien à traiter alors que le fichier a des lignes : elles sont toutes terminées."""
        return not self.simule and self.total == 0 and self.lignes_fichier > 0

    @property
    def traitees(self) -> int:
        return self.ok + self.erreurs + self.ignorees

    def resume(self) -> str:
        if self.sans_excel:
            if self.simule:
                return "Simulation : aucune action réelle effectuée."
            if self.interrompu:
                return "Tâche INTERROMPUE" + (f" — {self.message}" if self.message else "") + "."
            if self.erreurs:
                return f"Tâche en ERREUR — {self.message}"
            if self.ignorees:
                return "Tâche ignorée."
            return "Tâche réussie. Vous pouvez la relancer quand vous voulez."
        if self.simule:
            return f"Simulation : {self.total} ligne(s) à traiter, aucune action réelle effectuée."
        texte = f"{self.traitees}/{self.total} ligne(s) traitée(s) : {self.ok} OK, {self.erreurs} ERREUR, {self.ignorees} IGNORE"
        if self.interrompu:
            texte += " — INTERROMPU (relancez la même commande pour reprendre)"
        if self.message:
            texte += f" — {self.message}"
        return texte + "."


def analyser_lignes(texte: str) -> Set[int]:
    """« 5,8,10-12 » -> {5, 8, 10, 11, 12} (numéros de lignes Excel)."""
    resultat: Set[int] = set()
    for morceau in str(texte).split(","):
        morceau = morceau.strip()
        if not morceau:
            continue
        if "-" in morceau:
            debut, _, fin = morceau.partition("-")
            try:
                a, b = int(debut), int(fin)
            except ValueError:
                raise ErreurAutoweb(f"Plage de lignes invalide : « {morceau} » (attendu ex. 10-20).")
            resultat.update(range(min(a, b), max(a, b) + 1))
        else:
            try:
                resultat.add(int(morceau))
            except ValueError:
                raise ErreurAutoweb(f"Numéro de ligne invalide : « {morceau} ».")
    return resultat


def chemin_excel(scenario: Scenario, options: Options) -> Path:
    if options.excel:
        chemin = Path(options.excel)
    elif scenario.excel.fichier:
        chemin = Path(scenario.excel.fichier)
    else:
        raise ErreurAutoweb(
            "Aucun fichier Excel indiqué : ajoutez « excel: fichier: suivi.xlsx » dans le scénario "
            "ou passez --excel suivi.xlsx."
        )
    if not chemin.is_absolute():
        chemin = (scenario.dossier / chemin) if not options.excel else (Path.cwd() / chemin)
        if options.excel and not chemin.exists() and (scenario.dossier / options.excel).exists():
            chemin = scenario.dossier / options.excel
    return chemin


def ouvrir_classeur(scenario: Scenario, options: Options) -> ClasseurSuivi:
    cfg = scenario.excel
    return ClasseurSuivi(
        chemin_excel(scenario, options),
        feuille=cfg.feuille,
        ligne_entete=cfg.ligne_entete,
        colonne_statut=cfg.colonne_statut,
        colonne_message=cfg.colonne_message,
        colonne_horodatage=cfg.colonne_horodatage,
        sauvegarde=not options.simuler,
    ).ouvrir()


def selectionner(classeur: ClasseurSuivi, scenario: Scenario, options: Options) -> List[Ligne]:
    """Lignes à traiter selon le statut, --lignes, --limite."""
    cfg = scenario.excel
    statuts = {normaliser_cle(s) for s in cfg.traiter_si}
    if options.reprendre_erreurs:
        statuts.add(normaliser_cle(STATUT_ERREUR))
    resultat: List[Ligne] = []
    tout = options.tout or cfg.refaire == "toujours"
    for ligne in classeur.lignes():
        if options.lignes is not None and ligne.numero not in options.lignes:
            continue
        if not tout:
            statut = ligne.valeur(cfg.colonne_statut)
            if normaliser_cle("" if statut is None else statut) not in statuts:
                continue
        resultat.append(ligne)
    if options.limite is not None:
        resultat = resultat[: max(0, options.limite)]
    return resultat


def contexte_de_base(scenario: Scenario, options: Options) -> Dict[str, Any]:
    maintenant = dt.datetime.now()
    contexte: Dict[str, Any] = {}
    contexte.update(scenario.variables)
    contexte.update(options.variables)
    contexte["aujourdhui"] = maintenant.strftime("%d/%m/%Y")
    contexte["maintenant"] = maintenant.strftime("%d/%m/%Y %H:%M")
    # pour nommer des fichiers sans jamais écraser le précédent : 20260924-143005
    contexte["horodatage"] = maintenant.strftime("%Y%m%d-%H%M%S")
    return contexte


def completer_secrets(scenario: Scenario, options: Options, contexte: Dict[str, Any]) -> None:
    """Demande à l'écran les mots de passe du scénario qui n'ont pas été fournis.

    Ils ne sont ni affichés, ni enregistrés, ni écrits dans le journal.
    """
    from .console import demander_secret
    from .scenario import MOTIF_SECRET

    for nom in scenario.variables:
        if not MOTIF_SECRET.search(nom):
            continue
        if str(contexte.get(nom) or "").strip():
            continue
        if not options.interactif:
            journal.warning("La variable « %s » est vide : ajoutez --var %s=... au lancement.", nom, nom)
            continue
        valeur = demander_secret(f"Mot de passe pour « {nom} » (il ne s'affiche pas) : ")
        if valeur:
            contexte[nom] = valeur
        else:
            journal.warning("Aucun mot de passe saisi pour « %s » : la connexion échouera probablement.", nom)


def contexte_ligne(
    base: Dict[str, Any], ligne: Ligne, n: int, total: int, noms_variables: Iterable[str] = ()
) -> Dict[str, Any]:
    contexte = dict(base)
    contexte.update(ligne.valeurs)
    contexte["ligne"] = ligne.numero
    contexte["n"] = n
    contexte["total"] = total
    # Une variable du scénario peut contenir un gabarit, par exemple
    #   variables: {url: "https://outil/fiche={{Numéro}}"}
    # On la développe ici ; les valeurs des cellules, elles, ne sont jamais relues.
    for nom in noms_variables:
        valeur = contexte.get(nom)
        for _ in range(3):
            if not isinstance(valeur, str) or "{{" not in valeur:
                break
            rendu = rendre(valeur, contexte, strict=False)
            if rendu == valeur:
                break
            valeur = rendu
        contexte[nom] = valeur
    return contexte


def libelle_ligne(ligne: Ligne, scenario: Scenario, classeur: ClasseurSuivi) -> str:
    colonne = scenario.excel.colonne_libelle or (classeur.entetes[0] if classeur.entetes else None)
    if colonne:
        valeur = ligne.valeur(colonne)
        if valeur not in (None, ""):
            return f"{colonne} = {valeur}"
        return f"{colonne} = (vide)"
    return ""


# ----------------------------------------------------------------------------- vérification
def verifier_colonnes(scenario: Scenario, classeur: ClasseurSuivi, options: Options) -> List[str]:
    """Colonnes/variables référencées dans les étapes par ligne mais absentes de l'Excel."""
    disponibles = list(classeur.entetes) + list(scenario.variables) + list(options.variables) + list(VARIABLES_SPECIALES)
    # les colonnes créées par « lire » / « executer_js vers » sont disponibles ensuite
    for etape in toutes_les_etapes(scenario.avant + scenario.etapes):
        if etape.action in ("lire", "executer_js", "telecharger") and etape.args.get("vers"):
            disponibles.append(str(etape.args["vers"]))
    # les variables peuvent elles-mêmes utiliser des colonnes
    a_verifier = [scenario.etapes, [v for v in scenario.variables.values() if isinstance(v, str)]]
    return sorted(manquants(a_verifier, disponibles))


def verifier_avant_apres(scenario: Scenario, options: Options) -> List[str]:
    disponibles = list(scenario.variables) + list(options.variables) + list(VARIABLES_SPECIALES)
    for etape in toutes_les_etapes(scenario.avant + scenario.apres):
        if etape.action in ("lire", "executer_js", "telecharger") and etape.args.get("vers"):
            disponibles.append(str(etape.args["vers"]))
    return sorted(manquants(scenario.avant + scenario.apres, disponibles))


# ----------------------------------------------------------------------------- simulation
def _decrire_etapes(etapes: List[Etape], contexte: Dict[str, Any], indent: str = "    ") -> List[str]:
    lignes: List[str] = []
    for etape in etapes:
        args = rendre_structure(etape.args, contexte, strict=False)
        lignes.append(f"{indent}- {Etape(etape.action, masquer_secrets(args, etape), nom=etape.nom).resume()}")
        for sous, titre in (("alors", "alors"), ("sinon", "sinon"), ("etapes", "dans le cadre")):
            if isinstance(args.get(sous), list):
                lignes.append(f"{indent}  {titre} :")
                lignes.extend(_decrire_etapes(args[sous], contexte, indent + "    "))
    return lignes


def simuler(scenario: Scenario, classeur: ClasseurSuivi, options: Options) -> Bilan:
    lignes = selectionner(classeur, scenario, options)
    base = contexte_de_base(scenario, options)
    bilan = Bilan(total=len(lignes), simule=True)
    absentes = verifier_colonnes(scenario, classeur, options)
    if absentes:
        journal.error("Colonnes référencées dans le scénario mais absentes de l'Excel : %s", ", ".join(absentes))
        journal.error("Colonnes disponibles : %s", ", ".join(classeur.entetes))
    journal.info("Simulation de « %s » sur %s (%d ligne(s) à traiter)", scenario.nom, classeur.chemin.name, len(lignes))
    if scenario.avant and not options.sans_avant:
        journal.info("Étapes « avant » (une fois) :")
        for texte in _decrire_etapes(scenario.avant, base):
            journal.info(texte)
    noms_variables = list(scenario.variables) + list(options.variables)
    for n, ligne in enumerate(lignes, start=1):
        contexte = contexte_ligne(base, ligne, n, len(lignes), noms_variables)
        journal.info("Ligne Excel %d (%d/%d) %s", ligne.numero, n, len(lignes), libelle_ligne(ligne, scenario, classeur))
        try:
            for texte in _decrire_etapes(scenario.etapes, contexte):
                journal.info(texte)
        except ErreurGabarit as e:
            journal.error("    %s", e)
            bilan.erreurs += 1
    if scenario.apres and not options.sans_apres:
        journal.info("Étapes « apres » (une fois) :")
        for texte in _decrire_etapes(scenario.apres, base):
            journal.info(texte)
    if absentes:
        bilan.message = f"colonnes manquantes : {', '.join(absentes)}"
    return bilan


# ----------------------------------------------------------------------------- exécution
def _sauvegarder_avec_reessai(classeur: ClasseurSuivi, options: Options) -> None:
    while True:
        try:
            classeur.sauvegarder()
            return
        except ErreurExcel as e:
            if options.interactif and sys.stdin is not None and sys.stdin.isatty():
                print(f"\n{S.ATTENTION}  {e}\n   Fermez le fichier puis appuyez sur Entrée pour réessayer : ", end="", flush=True)
                input()
                continue
            raise


def _capture_erreur(navigateur: Navigateur, scenario: Scenario, numero: int) -> Optional[Path]:
    try:
        dossier = scenario.dossier / "captures" / "erreurs"
        dossier.mkdir(parents=True, exist_ok=True)
        chemin = dossier / f"ligne-{numero}-{dt.datetime.now().strftime('%Y%m%d-%H%M%S')}.png"
        navigateur.page_courante().screenshot(path=str(chemin))
        return chemin
    except Exception:
        return None


def sans_excel(scenario: Scenario, options: Options) -> bool:
    return not options.excel and not scenario.excel.fichier


def lancer_sans_excel(scenario: Scenario, options: Options) -> Bilan:
    """Tâche sans Excel : les étapes sont jouées une fois, à CHAQUE lancement.

    Rien n'est noté nulle part, donc rien n'empêche de la relancer autant qu'on veut.
    """
    base = contexte_de_base(scenario, options)
    bilan = Bilan(total=1, lignes_fichier=1, sans_excel=True)
    if options.simuler:
        bilan.simule = True
        journal.info("Simulation de « %s » (tâche sans Excel)", scenario.nom)
        for partie, etapes in (("avant", scenario.avant), ("étapes", scenario.etapes), ("après", scenario.apres)):
            if etapes:
                journal.info("%s :", partie.capitalize())
                for texte in _decrire_etapes(etapes, base):
                    journal.info(texte)
        return bilan

    completer_secrets(scenario, options, base)
    journal.info("Tâche « %s » — lancement", scenario.nom)
    navigateur = Navigateur(scenario.navigateur, scenario.dossier, visible=options.visible)
    navigateur.ouvrir()
    debut = time.monotonic()
    try:
        if scenario.avant and not options.sans_avant:
            Executeur(navigateur, scenario, base, interactif=options.interactif).executer(scenario.avant)
        executeur = Executeur(navigateur, scenario, dict(base), interactif=options.interactif)
        try:
            executeur.executer(scenario.etapes)
            bilan.ok = 1
            journal.info("   %s Tâche terminée (%.1f s)", S.OK, time.monotonic() - debut)
        except LigneIgnoree as e:
            bilan.ignorees = 1
            journal.info("   %s IGNORE : %s", S.IGNORE, e)
        except ErreurEtape as e:
            capture = _capture_erreur(navigateur, scenario, 1)
            message = str(e) + (f" [capture : {capture}]" if capture else "")
            bilan.erreurs = 1
            bilan.message = message
            journal.error("   %s ERREUR : %s", S.ERREUR, message)
            if options.inspecter_si_erreur and navigateur.visible:
                try:
                    navigateur.page_courante().pause()
                except Exception:
                    pass
        if scenario.apres and not options.sans_apres and not bilan.erreurs:
            try:
                Executeur(navigateur, scenario, base, interactif=options.interactif).executer(scenario.apres)
            except (ErreurEtape, LigneIgnoree) as e:
                journal.error("Étapes « apres » en erreur : %s", e)
    except NavigateurFerme as e:
        journal.error("%s", e)
        bilan.interrompu = True
        bilan.message = str(e)
    except ArretDemande as e:
        journal.warning("Arrêt demandé : %s", e)
        bilan.interrompu = True
        bilan.message = str(e)
    except KeyboardInterrupt:
        journal.warning("Interruption clavier (Ctrl+C) : arrêt propre.")
        bilan.interrompu = True
    finally:
        navigateur.fermer()
    return bilan


def lancer(scenario: Scenario, options: Options) -> Bilan:
    """Point d'entrée : exécute le scénario (sur chaque ligne de l'Excel s'il y en a un)."""
    if sans_excel(scenario, options):
        return lancer_sans_excel(scenario, options)
    classeur = ouvrir_classeur(scenario, options)
    try:
        if options.simuler:
            return simuler(scenario, classeur, options)

        absentes = verifier_colonnes(scenario, classeur, options)
        if absentes:
            raise ErreurAutoweb(
                "Le scénario utilise des colonnes absentes de l'Excel : "
                + ", ".join(f"« {c} »" for c in absentes)
                + f". Colonnes disponibles : {', '.join(classeur.entetes)}."
            )
        lignes = selectionner(classeur, scenario, options)
        bilan = Bilan(total=len(lignes), lignes_fichier=len(classeur.lignes()))
        base = contexte_de_base(scenario, options)
        if lignes:
            completer_secrets(scenario, options, base)
        journal.info("Scénario « %s » — Excel %s — %d ligne(s) à traiter", scenario.nom, classeur.chemin.name, len(lignes))
        if classeur.chemin_sauvegarde:
            journal.info("Copie de sauvegarde : %s", classeur.chemin_sauvegarde)
        if not lignes:
            toutes = classeur.lignes()
            if not toutes:
                journal.warning(
                    "Votre fichier Excel ne contient aucune ligne de données, seulement les titres "
                    "de colonnes.\n   Ouvrez %s, écrivez au moins une ligne SOUS les titres "
                    "(une ligne = une exécution),\n   enregistrez, fermez le fichier, puis relancez.",
                    classeur.chemin,
                )
            else:
                faits = sum(1 for l in toutes if str(l.valeur(scenario.excel.colonne_statut) or "").strip())
                journal.info(
                    "Rien à faire : les %d ligne(s) du fichier sont déjà traitées (colonne %s remplie).\n"
                    "   Ajoutez de nouvelles lignes, ou videz la colonne %s de celles à refaire.\n"
                    "   Depuis le menu, le choix « Reprendre aussi les lignes en erreur » traite les ERREUR.",
                    faits, scenario.excel.colonne_statut, scenario.excel.colonne_statut,
                )
            return bilan

        navigateur = Navigateur(scenario.navigateur, scenario.dossier, visible=options.visible)
        navigateur.ouvrir()
        try:
            if scenario.avant and not options.sans_avant:
                journal.info("Étapes « avant » :")
                Executeur(navigateur, scenario, base, interactif=options.interactif).executer(scenario.avant)
            _boucle(scenario, classeur, options, navigateur, lignes, base, bilan)
            if scenario.apres and not options.sans_apres and not bilan.interrompu:
                journal.info("Étapes « apres » :")
                try:
                    Executeur(navigateur, scenario, base, interactif=options.interactif).executer(scenario.apres)
                except (ErreurEtape, LigneIgnoree) as e:
                    journal.error("Étapes « apres » en erreur : %s", e)
        except NavigateurFerme as e:
            journal.error("%s", e)
            bilan.interrompu = True
            bilan.message = str(e)
        except ArretDemande as e:
            journal.warning("Arrêt demandé : %s", e)
            bilan.interrompu = True
            bilan.message = str(e)
        except KeyboardInterrupt:
            journal.warning("Interruption clavier (Ctrl+C) : arrêt propre.")
            bilan.interrompu = True
        finally:
            navigateur.fermer()
            _sauvegarder_avec_reessai(classeur, options)
        journal.info("Bilan : %s", bilan.resume())
        return bilan
    finally:
        classeur.fermer()


def _boucle(
    scenario: Scenario,
    classeur: ClasseurSuivi,
    options: Options,
    navigateur: Navigateur,
    lignes: List[Ligne],
    base: Dict[str, Any],
    bilan: Bilan,
) -> None:
    total = len(lignes)
    noms_variables = list(scenario.variables) + list(options.variables)
    for n, ligne in enumerate(lignes, start=1):
        libelle = libelle_ligne(ligne, scenario, classeur)
        journal.info("%s Ligne Excel %d (%d/%d) %s", S.LIGNE, ligne.numero, n, total, libelle)
        contexte = contexte_ligne(base, ligne, n, total, noms_variables)
        executeur = Executeur(navigateur, scenario, contexte, classeur, ligne.numero, interactif=options.interactif)
        debut = time.monotonic()
        try:
            executeur.executer(scenario.etapes)
            classeur.marquer(ligne.numero, STATUT_OK, "")
            bilan.ok += 1
            journal.info("   %s OK (%.1f s)", S.OK, time.monotonic() - debut)
        except LigneIgnoree as e:
            classeur.marquer(ligne.numero, STATUT_IGNORE, str(e))
            bilan.ignorees += 1
            journal.info("   %s IGNORE : %s", S.IGNORE, e)
        except ErreurEtape as e:
            capture = _capture_erreur(navigateur, scenario, ligne.numero)
            message = str(e)
            if capture:
                message += f" [capture : {capture.name}]"
            classeur.marquer(ligne.numero, STATUT_ERREUR, message)
            bilan.erreurs += 1
            journal.error("   %s ERREUR : %s", S.ERREUR, message)
            if options.inspecter_si_erreur and navigateur.visible:
                journal.info("   Inspecteur ouvert (--inspecter-si-erreur) : cliquez sur Resume pour continuer.")
                try:
                    navigateur.page_courante().pause()
                except Exception:
                    pass
            if options.arret_premiere_erreur:
                bilan.interrompu = True
                bilan.message = "arrêt à la première erreur (--arret-premiere-erreur)"
                _sauvegarder_avec_reessai(classeur, options)
                return
        except NavigateurFerme:
            classeur.marquer(ligne.numero, STATUT_ERREUR, "navigateur fermé pendant le traitement de cette ligne")
            bilan.erreurs += 1
            _sauvegarder_avec_reessai(classeur, options)
            raise
        except (ArretDemande, KeyboardInterrupt):
            classeur.marquer(ligne.numero, STATUT_ERREUR, "traitement interrompu pendant cette ligne (à refaire)")
            bilan.erreurs += 1
            _sauvegarder_avec_reessai(classeur, options)
            raise
        _sauvegarder_avec_reessai(classeur, options)
        if scenario.excel.entre_lignes_ms > 0 and n < total:
            time.sleep(scenario.excel.entre_lignes_ms / 1000.0)
