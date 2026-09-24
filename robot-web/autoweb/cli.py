"""Interface en ligne de commande : `python -m autoweb <commande> ...`

Commandes :
    demo         Vérifie que tout fonctionne sur ce poste (formulaire local + Excel de démo).
    lancer       Exécute un scénario sur un Excel.
    simuler      Comme lancer, mais sans navigateur : affiche ce qui serait fait.
    verifier     Contrôle le scénario et la correspondance avec les colonnes Excel.
    initialiser  Crée un dossier de départ (scénario modèle + Excel vide).
    inspecter    Ouvre le navigateur et l'inspecteur Playwright pour trouver les sélecteurs.
    enregistrer  Enregistre vos clics/saisies (codegen Playwright) pour construire un scénario.
    extraire     Extrait des champs de documents (PDF/Word/texte) vers un Excel.
"""

from __future__ import annotations

import argparse
import datetime as dt
import logging
import shutil
import subprocess
import sys
from pathlib import Path
from typing import List, Optional

from playwright.sync_api import Error as PlaywrightError

from . import __version__
from . import symboles as S
from .erreurs import ErreurAutoweb
from .excel import creer_classeur
from .navigateur import premiere_ligne

journal = logging.getLogger("autoweb")
DOSSIER_MODELES = Path(__file__).parent / "modeles"
DOSSIER_PROJET = Path(__file__).resolve().parent.parent


def prefixe_commande() -> str:
    """Comment l'utilisateur lance le robot : ./robot.command (Mac), robot (Windows) ou python -m autoweb."""
    if sys.platform == "win32":
        return "robot" if (DOSSIER_PROJET / "robot.bat").exists() else "python -m autoweb"
    if (DOSSIER_PROJET / "robot.command").exists():
        return "./robot.command"
    return "python3 -m autoweb"


# ----------------------------------------------------------------------------- journalisation
class _FormatConsole(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        heure = dt.datetime.fromtimestamp(record.created).strftime("%H:%M:%S")
        message = record.getMessage()
        texte = message.lstrip(" ")
        indentation = message[: len(message) - len(texte)]
        prefixe = {"WARNING": f"{S.ATTENTION} ", "ERROR": f"{S.ERREUR} ", "CRITICAL": f"{S.ERREUR} "}.get(record.levelname, "")
        if texte.startswith(S.TOUS):
            prefixe = ""  # le message porte déjà son symbole
        return f"{heure}  {indentation}{prefixe}{texte}"


def configurer_journal(dossier: Optional[Path], verbeux: bool = False) -> Optional[Path]:
    journal.setLevel(logging.DEBUG)
    for h in list(journal.handlers):
        journal.removeHandler(h)
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(logging.DEBUG if verbeux else logging.INFO)
    console.setFormatter(_FormatConsole())
    journal.addHandler(console)
    chemin = None
    if dossier is not None:
        try:
            dossier_journal = Path(dossier) / "journal"
            dossier_journal.mkdir(parents=True, exist_ok=True)
            chemin = dossier_journal / f"autoweb-{dt.datetime.now():%Y%m%d}.log"
            fichier = logging.FileHandler(chemin, encoding="utf-8")
            fichier.setLevel(logging.DEBUG)
            fichier.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s"))
            journal.addHandler(fichier)
        except OSError:
            chemin = None
    journal.propagate = False
    return chemin


def _preparer_console() -> None:
    """Sous Windows, force l'UTF-8 pour afficher correctement les accents."""
    for flux in (sys.stdout, sys.stderr):
        try:
            if flux is not None and hasattr(flux, "reconfigure"):
                flux.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


# ----------------------------------------------------------------------------- commandes
def _options_depuis(args: argparse.Namespace):
    from .runner import Options, analyser_lignes

    variables = {}
    for paire in args.var or []:
        nom, sep, valeur = paire.partition("=")
        if not sep:
            raise ErreurAutoweb(f"--var attend nom=valeur (reçu « {paire} »).")
        variables[nom.strip()] = valeur
    visible = None
    if getattr(args, "visible", False):
        visible = True
    if getattr(args, "cache", False):
        visible = False
    return Options(
        excel=Path(args.excel) if args.excel else None,
        simuler=getattr(args, "simuler", False),
        limite=args.limite,
        lignes=analyser_lignes(args.lignes) if args.lignes else None,
        reprendre_erreurs=args.reprendre_erreurs,
        tout=args.tout,
        visible=visible,
        inspecter_si_erreur=getattr(args, "inspecter_si_erreur", False),
        arret_premiere_erreur=getattr(args, "arret_premiere_erreur", False),
        variables=variables,
        sans_avant=getattr(args, "sans_avant", False),
        sans_apres=getattr(args, "sans_apres", False),
        interactif=not getattr(args, "sans_pause", False),
    )


def cmd_lancer(args: argparse.Namespace) -> int:
    from .runner import lancer
    from .scenario import charger

    scenario = charger(Path(args.scenario))
    fichier_journal = configurer_journal(scenario.dossier, args.verbeux)
    if fichier_journal:
        journal.debug("Journal : %s", fichier_journal)
    options = _options_depuis(args)
    bilan = lancer(scenario, options)
    print()
    print(bilan.resume())
    if bilan.simule:
        return 2 if bilan.message else 0
    if bilan.tout_deja_fait:
        return CODE_TOUT_DEJA_FAIT
    return 0 if (bilan.erreurs == 0 and not bilan.interrompu) else 1


CODE_TOUT_DEJA_FAIT = 3  # « lancer » n'avait rien à faire : toutes les lignes sont déjà OK


def cmd_verifier(args: argparse.Namespace) -> int:
    from .runner import Options, ouvrir_classeur, selectionner, verifier_avant_apres, verifier_colonnes
    from .scenario import charger, toutes_les_etapes

    scenario = charger(Path(args.scenario))
    configurer_journal(None, args.verbeux)
    print(f"{S.OK} Scénario « {scenario.nom} » valide ({len(scenario.etapes)} étape(s) par ligne, "
          f"{len(scenario.avant)} avant, {len(scenario.apres)} après).")
    actions = sorted({e.action for e in toutes_les_etapes(scenario.avant + scenario.etapes + scenario.apres)})
    print(f"  Actions utilisées : {', '.join(actions)}")
    options = Options(excel=Path(args.excel) if args.excel else None, simuler=True)
    problemes = verifier_avant_apres(scenario, options)
    if problemes:
        print(f"{S.ERREUR} Variables absentes dans avant/apres : {', '.join(problemes)}")
    code = 0
    if not options.excel and not scenario.excel.fichier:
        print(f"{S.OK} Tâche sans Excel : elle sera rejouée en entier à chaque lancement.")
        return 1 if problemes else 0
    try:
        classeur = ouvrir_classeur(scenario, options)
    except ErreurAutoweb as e:
        print(f"{S.ATTENTION} Excel non vérifié : {e}")
        return 1 if problemes else 0
    try:
        print(f"{S.OK} Excel {classeur.chemin.name}, feuille « {classeur.nom_feuille} » : {len(classeur.lignes())} ligne(s) de données.")
        print(f"  Colonnes : {', '.join(classeur.entetes)}")
        absentes = verifier_colonnes(scenario, classeur, options)
        if absentes:
            print(f"{S.ERREUR} Colonnes utilisées par le scénario mais absentes de l'Excel : {', '.join(absentes)}")
            code = 1
        a_traiter = selectionner(classeur, scenario, options)
        print(f"  {len(a_traiter)} ligne(s) seraient traitées (statut {' / '.join(repr(s) for s in scenario.excel.traiter_si)}).")
        for colonne in (scenario.excel.colonne_statut, scenario.excel.colonne_message, scenario.excel.colonne_horodatage):
            if not classeur.colonne_existe(colonne):
                print(f"  (la colonne « {colonne} » sera créée automatiquement)")
    finally:
        classeur.fermer()
    return 1 if (problemes or code) else 0


def cmd_initialiser(args: argparse.Namespace) -> int:
    configurer_journal(None, args.verbeux)
    dossier = Path(args.dossier)
    dossier.mkdir(parents=True, exist_ok=True)
    nom = args.nom or dossier.name
    base = "".join(c if c.isalnum() or c in "-_" else "_" for c in nom.strip().lower().replace(" ", "_")) or "mon_outil"
    scenario = dossier / f"{base}.yaml"
    excel = dossier / (args.excel or "suivi.xlsx")
    if scenario.exists() and not args.ecraser:
        raise ErreurAutoweb(f"{scenario} existe déjà (ajoutez --ecraser pour le remplacer).")
    modele = (DOSSIER_MODELES / "modele_scenario.yaml").read_text(encoding="utf-8")
    modele = modele.replace("__NOM__", nom).replace("__EXCEL__", excel.name).replace("__PROFIL__", f"profils/{base}")
    scenario.write_text(modele, encoding="utf-8")
    colonnes = [c.strip() for c in (args.colonnes or "Numéro plan,Titre,Type,Date,Urgent,Commentaire").split(",") if c.strip()]
    if not excel.exists() or args.ecraser:
        creer_classeur(excel, colonnes, feuille="Suivi")
        print(f"{S.OK} Excel créé : {excel} (colonnes : {', '.join(colonnes)} + Statut/Message/Horodatage)")
    else:
        print(f"  Excel conservé : {excel}")
    (dossier / ".gitignore").write_text(
        "# données de session du navigateur (cookies !) et fichiers générés : ne jamais partager\n"
        "profils/\ncaptures/\njournal/\nsauvegardes/\ntelechargements/\n",
        encoding="utf-8",
    )
    print(f"{S.OK} Scénario modèle créé : {scenario}")
    prefixe = prefixe_commande()
    print()
    print("Prochaines étapes :")
    print(f"  1. Remplissez {excel.name} (une ligne par élément à saisir).")
    print(f"  2. Construisez le scénario :  {prefixe} assistant https://votre-outil/... --excel {excel}")
    print(f"     (ou adaptez à la main les étapes de {scenario.name})")
    print(f"  3. Testez à blanc :  {prefixe} simuler {scenario}")
    print(f"  4. Lancez pour de vrai :  {prefixe} lancer {scenario} --limite 1")
    return 0


def _normaliser_url(url: Optional[str]) -> Optional[str]:
    """Adresse web, ou chemin d'un fichier local (ex. demo\\formulaire_demo.html) -> URL."""
    if not url:
        return None
    if url.lower().startswith(("http://", "https://", "file:")):
        return url
    chemin = Path(url)
    if chemin.exists():
        return chemin.resolve().as_uri()
    return "https://" + url


def _lancer_navigateur_libre(args: argparse.Namespace):
    from .navigateur import Navigateur
    from .scenario import ConfigNavigateur

    visible = not getattr(args, "cache", False)
    cfg = ConfigNavigateur(canal=args.canal or "auto", profil=args.profil, visible=visible)
    if args.executable:
        cfg.executable = args.executable
    if args.attacher:
        cfg.attacher = args.attacher
    nav = Navigateur(cfg, Path.cwd(), visible=visible)
    return nav


def cmd_releve(args: argparse.Namespace) -> int:
    from .releve import relever

    configurer_journal(None, args.verbeux)
    interactif = not args.sans_pause and sys.stdin is not None and sys.stdin.isatty()
    nav = _lancer_navigateur_libre(args)
    page = nav.ouvrir()
    dossiers: List[Path] = []
    try:
        url = _normaliser_url(args.url)
        if url:
            page.goto(url)
        while True:
            if interactif:
                print()
                print("Dans le navigateur : connectez-vous si besoin et naviguez jusqu'à l'écran à automatiser.")
                print("Puis revenez ici et appuyez sur Entrée pour relever cet écran (ou tapez « stop ») : ", end="", flush=True)
                if input().strip().lower() in ("stop", "q", "quit"):
                    break
            page = nav.page_courante()
            dossier = relever(page, Path(args.sortie or "releves"), nom=args.nom)
            dossiers.append(dossier)
            print(f"{S.OK} Relevé enregistré dans {dossier}")
            print("     champs.txt      : liste des champs avec les sélecteurs à utiliser")
            print("     brouillon.yaml  : début de scénario à compléter")
            print("     capture.png / page.html : à relire avant envoi (peuvent contenir des données)")
            if not interactif:
                break
            print("Relever un autre écran ? (o/N) : ", end="", flush=True)
            if input().strip().lower() not in ("o", "oui", "y"):
                break
    finally:
        nav.fermer()
    if dossiers:
        print()
        print(f"Envoyez à Claude le contenu de : {', '.join(str(d) for d in dossiers)}")
    return 0


def cmd_inspecter(args: argparse.Namespace) -> int:
    configurer_journal(None, args.verbeux)
    nav = _lancer_navigateur_libre(args)
    page = nav.ouvrir()
    try:
        url = _normaliser_url(args.url)
        if url:
            page.goto(url)
        print()
        print("Inspecteur Playwright ouvert.")
        print("  - Cliquez sur « Pick locator » (icône de visée) puis sur un élément de la page : le sélecteur s'affiche.")
        print("  - Préférez les sélecteurs stables : #id, [name=...], libelle=..., role=button:Texte, texte=...")
        print("  - Pour finir : cliquez sur « Resume » (bouton lecture) ou fermez le navigateur.")
        page.pause()
    finally:
        nav.fermer()
    return 0


def cmd_assistant(args: argparse.Namespace) -> int:
    from .assistant import Dialogue, construire
    from .excel import ClasseurSuivi
    from .releve import charger_releve, dernier_releve, relever

    configurer_journal(None, args.verbeux)
    interactif = sys.stdin is not None and sys.stdin.isatty()
    dossier_releve: Optional[Path] = Path(args.releve) if args.releve else None
    canal = args.canal or "chrome"
    if args.url:
        # relevé de l'écran d'abord, dans la même session
        nav = _lancer_navigateur_libre(args)
        page = nav.ouvrir()
        canal = nav.canal_utilise or canal
        try:
            page.goto(_normaliser_url(args.url))
            if interactif and not args.sans_pause:
                print()
                print("Dans le navigateur : connectez-vous si besoin et affichez l'écran à automatiser (le formulaire vide).")
                print("Puis revenez ici et appuyez sur Entrée : ", end="", flush=True)
                input()
            dossier_releve = relever(nav.page_courante(), Path(args.sortie_releve or "releves"), nom=args.nom)
            print(f"{S.OK} Relevé enregistré dans {dossier_releve}")
        finally:
            nav.fermer()
    if dossier_releve is None:
        dossier_releve = dernier_releve(Path(args.sortie_releve or "releves"))
        if dossier_releve is None:
            raise ErreurAutoweb(
                "Aucun relevé trouvé. Lancez d'abord :  python -m autoweb releve https://adresse-de-l-outil --canal chrome\n"
                "ou donnez l'adresse directement :  python -m autoweb assistant https://adresse-de-l-outil --excel suivi.xlsx"
            )
        print(f"Relevé utilisé : {dossier_releve}")
    try:
        releve = charger_releve(dossier_releve)
    except FileNotFoundError as e:
        raise ErreurAutoweb(str(e))

    colonnes: List[str] = []
    feuille = None
    if args.excel:
        classeur = ClasseurSuivi(Path(args.excel), feuille=args.feuille, sauvegarde=False).ouvrir()
        try:
            colonnes = [c for c in classeur.entetes if c not in ("Statut", "Message", "Horodatage")]
            feuille = classeur.nom_feuille
        finally:
            classeur.fermer()
    else:
        print(f"{S.ATTENTION} Pas d'Excel indiqué (--excel suivi.xlsx) : vous taperez les noms de colonnes à la main.")

    dialogue = Dialogue()
    texte = construire(
        releve, colonnes, dialogue, nom=args.nom,
        fichier_excel=(Path(args.excel).name if args.excel else "suivi.xlsx"),
        feuille=feuille, canal=canal,
    )
    nom = args.nom or releve.get("nom") or "scenario"
    base = "".join(c if c.isalnum() or c in "-_" else "_" for c in nom.strip().lower().replace(" ", "_")) or "scenario"
    sortie = Path(args.sortie) if args.sortie else Path(f"{base}.yaml")
    if args.excel and not args.sortie:
        sortie = Path(args.excel).resolve().parent / f"{base}.yaml"
    if sortie.exists() and not args.ecraser:
        sortie = sortie.with_name(f"{sortie.stem}-{dt.datetime.now():%Y%m%d-%H%M%S}{sortie.suffix}")
    sortie.write_text(texte, encoding="utf-8")
    print()
    print(f"{S.OK} Scénario écrit : {sortie}")
    prefixe = prefixe_commande()
    print("Prochaines étapes :")
    print(f"  {prefixe} verifier \"{sortie}\"")
    print(f"  {prefixe} simuler \"{sortie}\"")
    print(f"  {prefixe} lancer \"{sortie}\" --limite 1")
    return 0


def _colonnes_et_lignes(chemin_excel: Optional[str], feuille: Optional[str]):
    """Colonnes utiles de l'Excel (hors colonnes de suivi) et valeurs des premières lignes."""
    from .excel import ClasseurSuivi

    if not chemin_excel:
        return [], [], None
    classeur = ClasseurSuivi(Path(nettoyer_chemin(chemin_excel)), feuille=feuille, sauvegarde=False).ouvrir()
    try:
        suivi = {classeur.colonne_statut, classeur.colonne_message, classeur.colonne_horodatage}
        colonnes = [c for c in classeur.entetes if c not in suivi]
        lignes = [l.valeurs for l in classeur.lignes()[:30]]
        return colonnes, lignes, classeur.nom_feuille
    finally:
        classeur.fermer()


def nettoyer_chemin(texte: str) -> str:
    """Enlève les guillemets ajoutés par l'explorateur Windows autour d'un chemin collé."""
    texte = (texte or "").strip()
    if len(texte) >= 2 and texte[0] == texte[-1] and texte[0] in "\"'":
        texte = texte[1:-1].strip()
    return texte


def _chemin_scenario(nom: str, excel: Optional[str], sortie: Optional[str], ecraser: bool) -> Path:
    """Les tâches vivent toujours dans robot-web/taches/ : elles y sont retrouvées par le menu."""
    base = "".join(c if c.isalnum() or c in "-_" else "_" for c in nom.strip().lower().replace(" ", "_")) or "tache"
    chemin = Path(sortie) if sortie else DOSSIER_PROJET / "taches" / f"{base}.yaml"
    if chemin.exists() and not ecraser:
        chemin = chemin.with_name(f"{chemin.stem}-{dt.datetime.now():%Y%m%d-%H%M%S}{chemin.suffix}")
    return chemin


def cmd_enregistrer(args: argparse.Namespace) -> int:
    """Le robot regarde l'utilisateur faire la tâche, puis écrit le scénario."""
    from .assistant import Dialogue, construire_depuis_enregistrement, nom_de_base
    from .enregistreur import Enregistreur

    configurer_journal(None, args.verbeux)
    colonnes, lignes_excel, feuille = _colonnes_et_lignes(args.excel, args.feuille)
    # Sans Excel : la tâche rejoue exactement les gestes, à chaque lancement.
    if args.excel and not lignes_excel:
        raise ErreurAutoweb(
            f"Le fichier {Path(args.excel).name} ne contient aucune ligne de données, seulement les titres.\n"
            "   Sans exemple, le robot ne peut pas deviner quelle colonne remplit quel champ,\n"
            "   et il n'aurait de toute façon rien à traiter.\n"
            f"   Ouvrez le fichier, écrivez au moins une ligne SOUS les titres (par exemple le contrat\n"
            "   que vous allez utiliser pendant l'enregistrement), enregistrez, fermez-le, puis recommencez."
        )
    nom = args.nom or "ma tache"
    url = _normaliser_url(args.url)
    if not url:
        raise ErreurAutoweb("Indiquez l'adresse de l'outil : autoweb enregistrer https://mon-outil/...")

    sortie = _chemin_scenario(nom, args.excel, args.sortie, args.ecraser)
    if not args.profil:
        # même profil que la tâche relancée plus tard : la connexion faite ici est gardée
        args.profil = str(sortie.parent.resolve() / "profils" / nom_de_base(nom))
    nav = _lancer_navigateur_libre(args)
    nav.ouvrir()
    canal = nav.canal_utilise or (args.canal or "chrome")
    enregistreur = Enregistreur(nav)
    try:
        try:
            enregistreur.demarrer(url)
        except PlaywrightError as e:
            raise ErreurAutoweb(
                f"Impossible d'ouvrir {url} :\n   {premiere_ligne(e)}\n"
                "Vérifiez l'adresse (elle doit commencer par http), votre connexion au réseau de\n"
                "l'entreprise, et que la page s'ouvre bien dans votre navigateur habituel."
            )
        print()
        print(f"{S.LIGNE} ENREGISTREMENT EN COURS")
        print("   1. Dans le navigateur qui vient de s'ouvrir, faites votre tâche normalement,")
        if args.excel:
            print("      une seule fois, avec les valeurs de la PREMIÈRE ligne de votre Excel.")
        else:
            print("      une seule fois, exactement comme d'habitude (connexion comprise si l'outil la demande).")
        print("   2. Quand c'est fini, cliquez sur le bandeau rouge en bas à gauche de la page")
        print("      (« Enregistrement ... cliquez pour terminer »).")
        print("   Le robot note chaque clic et chaque saisie. Rien ne sort de votre poste.")
        print()
        print("   Si le bandeau gêne ou ne répond pas : appuyez simplement sur Entrée ICI,")
        print("   dans le Terminal. Fermer la fenêtre du navigateur arrête aussi l'enregistrement.")
        print("   Si une page Google ou Chrome apparaît : ne l'utilisez pas, revenez sur l'onglet")
        print("   de votre outil (le robot ne rejoue pas ce qui est fait sur Google ou Chrome).")
        enregistreur.attendre_fin()
        etapes = enregistreur.arreter()
    finally:
        nav.fermer()
    if enregistreur.ignorees:
        print()
        print(f"{S.ATTENTION} {enregistreur.ignorees} action(s) faite(s) sur une page Google ou Chrome, hors de")
        print("   votre outil : elles sont ignorées et ne seront pas rejouées.")

    if not etapes:
        print(f"{S.ATTENTION} Aucune action enregistrée : rien à écrire.")
        return 1
    sortie.parent.mkdir(parents=True, exist_ok=True)
    # chemin de l'Excel : relatif s'il est à côté du scénario, absolu sinon
    if args.excel:
        excel_absolu = Path(nettoyer_chemin(args.excel)).resolve()
        reference = excel_absolu.name if excel_absolu.parent == sortie.parent.resolve() else str(excel_absolu)
    else:
        reference = None  # tâche sans Excel : rejouée en entier à chaque lancement
    # les fichiers téléchargés arrivent à côté de l'Excel, là où l'utilisateur les cherche
    base_exports = Path(nettoyer_chemin(args.excel)).resolve().parent if args.excel else DOSSIER_PROJET
    texte = construire_depuis_enregistrement(
        etapes, colonnes, lignes_excel, Dialogue(), nom=nom,
        fichier_excel=reference, feuille=feuille, canal=canal, url_depart=url,
        dossier_exports=str(base_exports / "exports"),
    )
    sortie.write_text(texte, encoding="utf-8")
    prefixe = prefixe_commande()
    print()
    print(f"{S.OK} Tâche enregistrée : {sortie}")
    print()
    print("Pour la relancer, maintenant ou plus tard, autant de fois que vous voulez :")
    print("   menu, choix 2, puis le numéro de la tâche")
    print(f"   ou directement :  {prefixe} lancer \"{sortie}\"")
    return 0


def lister_scenarios(racine: Optional[Path] = None) -> List[Path]:
    """Scénarios trouvés dans robot-web/taches/, puis dans le dossier de travail (2 niveaux)."""
    ignores = {"venv", "releves", "profils", "captures", "journal", "sauvegardes", "modeles",
               "corbeille", "__pycache__", "demo"}  # « demo » : le scénario de vérification, pas une tâche
    dossiers = [DOSSIER_PROJET / "taches", Path(racine or Path.cwd())]
    trouves: List[Path] = []
    vus = set()
    for dossier in dossiers:
        if not dossier.is_dir():
            continue
        for chemin in sorted(dossier.glob("*.yaml")) + sorted(dossier.glob("*/*.yaml")):
            if any(part in ignores for part in chemin.parts) or chemin.resolve() in vus:
                continue
            try:
                texte = chemin.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if "etapes:" in texte:
                vus.add(chemin.resolve())
                trouves.append(chemin)
    return trouves


def _decrire_scenario(chemin: Path) -> str:
    from .scenario import charger

    try:
        scenario = charger(chemin)
    except ErreurAutoweb as e:
        return f"(scénario illisible : {str(e)[:60]})"
    morceaux = [f"{len(scenario.etapes)} étape(s)"]
    if scenario.excel.fichier:
        morceaux.append(f"Excel {scenario.excel.fichier}")
    else:
        morceaux.append("rejouée en entier à chaque lancement")
    return ", ".join(morceaux)


def _tache_sans_excel(chemin: Path) -> bool:
    from .scenario import charger

    try:
        return not charger(chemin).excel.fichier
    except ErreurAutoweb:
        return False  # illisible : « lancer » affichera l'erreur complète


def cmd_scenarios(args: argparse.Namespace) -> int:
    configurer_journal(None, args.verbeux)
    scenarios = lister_scenarios(Path(args.dossier) if args.dossier else None)
    if not scenarios:
        print("Aucune tâche enregistrée pour l'instant.")
        print(f"Pour en créer une :  {prefixe_commande()} menu   puis choix 1")
        return 0
    print(f"{len(scenarios)} tâche(s) :")
    for i, chemin in enumerate(scenarios, start=1):
        print(f"  {i}. {chemin}")
        print(f"     {_decrire_scenario(chemin)}")
    return 0


def cmd_supprimer(args: argparse.Namespace) -> int:
    configurer_journal(None, args.verbeux)
    chemin = Path(args.scenario)
    if not chemin.exists():
        raise ErreurAutoweb(f"Fichier introuvable : {chemin}")
    corbeille = chemin.parent / "corbeille"
    corbeille.mkdir(exist_ok=True)
    cible = corbeille / f"{chemin.stem}-{dt.datetime.now():%Y%m%d-%H%M%S}{chemin.suffix}"
    shutil.move(str(chemin), str(cible))
    print(f"{S.OK} Tâche retirée. Le fichier est conservé dans {cible} au cas où.")
    return 0


def cmd_codegen(args: argparse.Namespace) -> int:
    configurer_journal(None, args.verbeux)
    commande: List[str] = [sys.executable, "-m", "playwright", "codegen", "--target", "python"]
    canal = args.canal or "msedge"
    if args.executable:
        print(f"{S.ATTENTION} codegen ne prend pas de chemin d'exécutable ; utilisation du canal", canal)
    if canal != "chromium":
        commande += ["--channel", canal]
    if args.profil:
        commande += ["--user-data-dir", str(Path(args.profil).resolve())]
    if args.sortie:
        commande += ["-o", str(args.sortie)]
    if args.url:
        commande.append(_normaliser_url(args.url))
    print("Enregistreur Playwright : faites vos actions dans le navigateur, le code Python apparaît dans la fenêtre.")
    print("Les sélecteurs affichés (get_by_label, get_by_role...) se traduisent dans le scénario par :")
    print("  page.get_by_label('Titre')            -> libelle=Titre")
    print("  page.get_by_role('button', name='OK') -> role=button:OK")
    print("  page.get_by_text('Enregistrer')       -> texte=Enregistrer")
    print("  page.locator('#champ')                -> #champ")
    print()
    try:
        return subprocess.call(commande)
    except FileNotFoundError:
        raise ErreurAutoweb("Impossible de lancer playwright codegen (module playwright absent ?).")


def cmd_extraire(args: argparse.Namespace) -> int:
    from .extraction import charger_regles, extraire

    configurer_journal(Path.cwd() if args.journal else None, args.verbeux)
    regles = charger_regles(Path(args.regles))
    dossier = Path(args.dossier or regles.dossier or ".")
    sortie = Path(args.sortie or "extraction.xlsx")
    bilan = extraire(regles, dossier, sortie, ecraser=args.ecraser)
    print()
    print(f"{bilan.fichiers} document(s) : {bilan.reussis} extrait(s), {bilan.incomplets} à vérifier, {bilan.illisibles} illisible(s).")
    print(f"Résultat : {sortie}")
    return 0 if bilan.illisibles == 0 else 1


def _ns(**kw) -> argparse.Namespace:
    """Namespace avec toutes les options connues, pour appeler les commandes depuis le menu."""
    defauts = dict(
        verbeux=False, canal=None, profil=None, executable=None, attacher=None, cache=False,
        visible=False, excel=None, feuille=None, sortie=None, nom=None, ecraser=False, url=None,
        dossier=None, limite=None, lignes=None, reprendre_erreurs=False, tout=False, var=None,
        sans_avant=False, sans_apres=False, inspecter_si_erreur=False, arret_premiere_erreur=False,
        sans_pause=False, simuler=False, scenario=None, port=8765, sans_attente=False, fichier=False,
        releve=None, sortie_releve=None, colonnes=None, regles=None, journal=False,
    )
    defauts.update(kw)
    return argparse.Namespace(**defauts)


def _demander(question: str, defaut: str = "") -> str:
    invite = f"{question} [{defaut}] : " if defaut else f"{question} : "
    print(invite, end="", flush=True)
    try:
        reponse = input().strip()
    except EOFError:
        return defaut
    return reponse or defaut


def _choisir_scenario(action: str) -> Optional[Path]:
    scenarios = lister_scenarios()
    if not scenarios:
        print("Aucune tâche enregistrée. Choisissez d'abord « 1 » pour en créer une.")
        return None
    print()
    print(f"Quelle tâche voulez-vous {action} ?")
    for i, chemin in enumerate(scenarios, start=1):
        print(f"  {i}. {chemin}   ({_decrire_scenario(chemin)})")
    reponse = _demander("  Numéro (0 = revenir au menu)", "1")
    if reponse.isdigit() and 1 <= int(reponse) <= len(scenarios):
        return scenarios[int(reponse) - 1]
    if reponse not in ("0", ""):
        print(f"   {S.ATTENTION} « {reponse} » ne correspond à aucune tâche de la liste : retour au menu.")
    return None


def cmd_menu(args: argparse.Namespace) -> int:
    configurer_journal(None, getattr(args, "verbeux", False))
    while True:
        print()
        print("=" * 62)
        print("   ROBOT WEB   -   que voulez-vous faire ?")
        print("=" * 62)
        print("   1. Enregistrer une nouvelle tache (vous la montrez au robot)")
        print("   2. Lancer une tache enregistree")
        print("   3. Voir mes taches")
        print("   4. Supprimer une tache")
        print("   5. Creer un fichier Excel de pilotage (facultatif)")
        print("   6. M'entrainer sur la fausse base de demonstration")
        print("   7. Verifier que tout fonctionne")
        print("   0. Quitter")
        print()
        choix = _demander("   Votre choix", "0")
        try:
            if choix == "1":
                url = nettoyer_chemin(_demander("   Adresse de l'outil (elle commence par http)"))
                if not url:
                    continue
                nom = _demander("   Nom de cette tache", "ma tache")
                print()
                print("   Faut-il repeter la tache pour chaque ligne d'un fichier Excel ?")
                print("   (en cas de doute, repondez n : la tache sera simplement rejouee")
                print("    telle quelle, a chaque fois que vous la lancerez)")
                excel = None
                if _demander("   Avec un fichier Excel ? (o/n)", "n").lower().startswith("o"):
                    excel = nettoyer_chemin(_demander("   Chemin du fichier Excel"))
                    if not excel:
                        continue
                    if not Path(excel).exists() and Path(excel + ".xlsx").exists():
                        excel += ".xlsx"   # « contrats » au lieu de « contrats.xlsx »
                    if not Path(excel).exists():
                        print(f"   {S.ERREUR} Fichier introuvable : {excel}")
                        print("   Donnez son nom complet avec .xlsx, ou son chemin entier.")
                        continue
                cmd_enregistrer(_ns(url=url, excel=excel, nom=nom))
            elif choix == "2":
                chemin = _choisir_scenario("lancer")
                if chemin is None:
                    continue
                if _tache_sans_excel(chemin):
                    # rien à choisir : la tâche est rejouée en entier, à chaque fois
                    cmd_lancer(_ns(scenario=str(chemin)))
                    continue
                print()
                print("   1. Une seule ligne, pour tester")
                print("   2. Toutes les lignes a faire")
                print("   3. Reprendre aussi les lignes en erreur")
                print("   4. Tout refaire, meme les lignes deja faites (tache a refaire souvent)")
                mode = _demander("   Votre choix", "1")
                options = {
                    "1": dict(limite=1), "2": {}, "3": dict(reprendre_erreurs=True), "4": dict(tout=True),
                }.get(mode, dict(limite=1))
                code = cmd_lancer(_ns(scenario=str(chemin), **options))
                if code == CODE_TOUT_DEJA_FAIT:
                    print()
                    print("   Toutes les lignes de l'Excel sont deja faites (Statut OK). Le robot ne")
                    print("   refait jamais une ligne terminee : c'est pour ne rien faire deux fois.")
                    if _demander("   Les refaire quand meme maintenant ? (o/n)", "o").lower().startswith("o"):
                        options = dict(options)
                        options["tout"] = True
                        cmd_lancer(_ns(scenario=str(chemin), **options))
            elif choix == "3":
                cmd_scenarios(_ns())
            elif choix == "4":
                chemin = _choisir_scenario("supprimer")
                if chemin is None:
                    continue
                if _demander(f"   Confirmer la suppression de {chemin.name} ? (o/n)", "n").lower().startswith("o"):
                    cmd_supprimer(_ns(scenario=str(chemin)))
            elif choix == "5":
                nom_fichier = nettoyer_chemin(_demander("   Nom du fichier Excel à créer", "suivi.xlsx"))
                if not nom_fichier.lower().endswith((".xlsx", ".xlsm")):
                    nom_fichier += ".xlsx"
                colonnes = _demander("   Colonnes, séparées par des virgules", "Numéro,Titre,Date")
                liste = [c.strip() for c in colonnes.split(",") if c.strip()]
                chemin = Path(nom_fichier)
                if chemin.exists():
                    print(f"   {S.ATTENTION} {chemin} existe déjà : il n'a pas été touché.")
                    continue
                print()
                print("   Ajoutez maintenant les lignes : une ligne = une exécution du robot.")
                print("   Un fichier sans ligne ne sert à rien, le robot n'aurait rien à traiter.")
                if len(liste) > 1:
                    print(f"   Séparez les valeurs par des virgules, dans l'ordre : {', '.join(liste)}")
                donnees = []
                while True:
                    reponse = _demander(f"   Ligne {len(donnees) + 1} (Entrée pour terminer)", "")
                    if not reponse:
                        break
                    separateur = ";" if ";" in reponse else ","
                    valeurs = [v.strip() for v in reponse.split(separateur)][: len(liste)]
                    donnees.append(valeurs)
                creer_classeur(chemin, liste, donnees, feuille="Suivi")
                print(f"   {S.OK} Créé : {chemin.resolve()}  ({len(donnees)} ligne(s))")
                if donnees:
                    print("   Vous pouvez passer au choix 1 pour enregistrer la tâche.")
                else:
                    print(f"   {S.ATTENTION} Aucune ligne : ouvrez le fichier, écrivez vos valeurs SOUS les")
                    print("   titres, enregistrez et fermez-le avant de passer au choix 1.")
            elif choix == "6":
                print()
                print("   La fausse base va demarrer. Suivez ensuite DEMARRAGE_MAC.txt (Mac)")
                print("   ou EXERCICE_MAISON.txt (Windows), partie « fausse base documentaire ».")
                cmd_base_demo(_ns())
            elif choix == "7":
                cmd_demo(_ns(sans_pause=True))
            elif choix in ("0", "q", "quitter"):
                print("   A bientot.")
                return 0
            else:
                print("   Tapez un chiffre de 0 a 7.")
        except ErreurAutoweb as e:
            print()
            print(f"{S.ERREUR} {e}")
        except KeyboardInterrupt:
            print()
            print("   Interrompu.")
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    from .runner import Options, lancer
    from .scenario import charger

    dossier = Path(args.dossier or "demo")
    dossier.mkdir(parents=True, exist_ok=True)
    for nom in ("formulaire_demo.html", "demo.yaml"):
        shutil.copyfile(DOSSIER_MODELES / nom, dossier / nom)
    excel = dossier / "demo_suivi.xlsx"
    aujourdhui = dt.datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    creer_classeur(
        excel,
        ["Numéro plan", "Titre", "Type", "Date", "Urgent", "Commentaire"],
        [
            ["PL-2026-001", "Rez-de-chaussée", "Architecture", aujourdhui, "oui", "Première saisie"],
            ["PL-2026-002", "Charpente", "STR", aujourdhui, "non", None],
            [None, "Plan sans numéro (erreur attendue)", "ELE", None, None, None],
            ["PL-2026-004", "Réseau électrique", "Électricité", aujourdhui, "x", "Vérifier les cotes"],
        ],
        feuille="Plans",
    )
    scenario = charger(dossier / "demo.yaml")
    configurer_journal(scenario.dossier, args.verbeux)
    print(f"Démo dans {dossier.resolve()} : 4 lignes, dont 1 en erreur volontaire (numéro manquant).")
    visible = not args.cache
    options = Options(visible=visible, interactif=not args.sans_pause)
    serveur = None
    if not args.fichier:
        # page servie en http local : plus proche d'un vrai outil, et certaines
        # politiques d'entreprise bloquent les adresses file://
        serveur, url = _servir_dossier(dossier)
        options.variables = {"url_demo": url}
        print(f"Formulaire de démonstration servi sur {url}")
    try:
        bilan = lancer(scenario, options)
    finally:
        if serveur is not None:
            serveur.shutdown()
            serveur.server_close()
    print()
    print(bilan.resume())
    print(f"Ouvrez {excel} : les colonnes Statut / Message / Référence outil ont été remplies.")
    attendu = bilan.ok == 3 and bilan.erreurs == 1
    if attendu:
        print(f"{S.OK} La démo s'est déroulée comme prévu : votre poste est prêt.")
    else:
        print(f"{S.ATTENTION} Résultat inattendu : envoyez le contenu du dossier journal/ à Claude.")
    return 0 if attendu else 1


def _servir_dossier(dossier: Path, fichier: str = "formulaire_demo.html", port: int = 0):
    """Sert `dossier` sur http://127.0.0.1:<port>/ dans un thread ; renvoie (serveur, url du fichier)."""
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class _Silencieux(SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:  # pas de bruit dans la console
            pass

    serveur = ThreadingHTTPServer(("127.0.0.1", port), partial(_Silencieux, directory=str(dossier)))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    port = serveur.server_address[1]
    return serveur, f"http://127.0.0.1:{port}/{fichier}"


def preparer_bac_a_sable(dossier: Path) -> None:
    """Copie la fausse base documentaire et crée les Excel d'exercice (sans écraser les existants)."""
    dossier.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(DOSSIER_MODELES / "base_demo.html", dossier / "base_demo.html")
    (dossier / "exports").mkdir(exist_ok=True)
    if not (dossier / "contrats.xlsx").exists():
        creer_classeur(dossier / "contrats.xlsx", ["Contrat"], [["HDK"], ["QRS"]], feuille="Contrats")
    if not (dossier / "fiches.xlsx").exists():
        creer_classeur(
            dossier / "fiches.xlsx",
            ["Numéro", "Nouveau statut", "Indice", "Commentaire"],  # « Statut » est réservé au suivi du robot
            [
                ["HDK-ARC-001", "Diffusé", "B", "Vérifié par le robot"],
                ["HDK-STR-002", "Archivé", "C", "Ancien indice"],
                ["LMN-ELE-001", "En cours", "12", "Indice volontairement faux : erreur attendue"],
            ],
            feuille="Fiches",
        )


def cmd_base_demo(args: argparse.Namespace) -> int:
    configurer_journal(None, args.verbeux)
    dossier = Path(args.dossier or "bac_a_sable")
    preparer_bac_a_sable(dossier)
    try:
        serveur, url = _servir_dossier(dossier, "base_demo.html", port=args.port)
    except OSError as e:
        raise ErreurAutoweb(
            f"Impossible d'ouvrir le port {args.port} ({e}). Un autre serveur tourne peut-être déjà : "
            "fermez-le ou relancez avec --port 8766."
        )
    print(f"{S.OK} Fausse base documentaire en ligne : {url}")
    print(f"   Dossier de travail : {dossier.resolve()}")
    print("   Identifiant demo / mot de passe demo. 60 plans répartis sur les contrats HDK, LMN, QRS, TUV.")
    print("   Excel d'exercice : contrats.xlsx (exports par contrat) et fiches.xlsx (modification de fiches).")
    print()
    print("Laissez cette fenêtre ouverte et travaillez dans une AUTRE fenêtre de terminal, par exemple :")
    print(f"   {prefixe_commande()} assistant {url} --excel {dossier / 'contrats.xlsx'} --nom \"export contrat\"")
    print()
    if args.sans_attente:
        serveur.shutdown()
        serveur.server_close()
        return 0
    try:
        print("Appuyez sur Entrée (ou Ctrl+C) pour arrêter le serveur... ", end="", flush=True)
        input()
    except (KeyboardInterrupt, EOFError):
        pass
    finally:
        serveur.shutdown()
        serveur.server_close()
    print("Serveur arrêté.")
    return 0


# ----------------------------------------------------------------------------- analyseur
def construire_parseur() -> argparse.ArgumentParser:
    parseur = argparse.ArgumentParser(
        prog="python -m autoweb",
        description="Robot de saisie web piloté par Excel (Playwright + openpyxl).",
    )
    parseur.add_argument("--version", action="version", version=f"autoweb {__version__}")
    sous = parseur.add_subparsers(dest="commande", metavar="commande")
    sous.required = True

    def commun(p: argparse.ArgumentParser) -> None:
        p.add_argument("-v", "--verbeux", action="store_true", help="affiche le détail (debug)")

    def options_navigateur(p: argparse.ArgumentParser) -> None:
        p.add_argument("--canal", choices=["auto", "msedge", "chrome", "chromium"], help="navigateur à utiliser")
        p.add_argument("--profil", help="dossier de profil persistant (garde la session connectée)")
        p.add_argument("--executable", help="chemin vers msedge.exe / chrome.exe")
        p.add_argument("--attacher", help="port ou URL d'un navigateur déjà ouvert (ex. 9222)")

    def options_execution(p: argparse.ArgumentParser) -> None:
        p.add_argument("scenario", help="fichier de scénario YAML")
        p.add_argument("--excel", help="fichier Excel (remplace excel.fichier du scénario)")
        p.add_argument("--limite", type=int, help="ne traiter que N lignes")
        p.add_argument("--lignes", help="numéros de lignes Excel à traiter, ex. 5,8,10-12")
        p.add_argument("--reprendre-erreurs", action="store_true", help="retraiter aussi les lignes en ERREUR")
        p.add_argument("--tout", action="store_true", help="retraiter toutes les lignes, quel que soit leur statut")
        p.add_argument("--var", action="append", metavar="NOM=VALEUR", help="variable supplémentaire pour les gabarits")
        p.add_argument("--sans-avant", action="store_true", help="ne pas exécuter la section « avant »")
        p.add_argument("--sans-apres", action="store_true", help="ne pas exécuter la section « apres »")

    p = sous.add_parser("lancer", help="exécuter un scénario sur un Excel")
    options_execution(p)
    p.add_argument("--visible", action="store_true", help="forcer le navigateur visible")
    p.add_argument("--cache", action="store_true", help="forcer le navigateur invisible (headless)")
    p.add_argument("--inspecter-si-erreur", action="store_true", help="ouvrir l'inspecteur à chaque erreur")
    p.add_argument("--arret-premiere-erreur", action="store_true", help="s'arrêter dès la première ligne en erreur")
    p.add_argument("--sans-pause", action="store_true", help="ne jamais attendre l'utilisateur (étapes « pause » ignorées)")
    p.add_argument("--simuler", action="store_true", help="ne rien faire, afficher les étapes rendues")
    commun(p)
    p.set_defaults(fonction=cmd_lancer)

    p = sous.add_parser("simuler", help="afficher ce qui serait fait, sans navigateur")
    options_execution(p)
    commun(p)
    p.set_defaults(fonction=cmd_lancer, simuler=True)

    p = sous.add_parser("verifier", help="contrôler un scénario et ses colonnes Excel")
    p.add_argument("scenario")
    p.add_argument("--excel")
    commun(p)
    p.set_defaults(fonction=cmd_verifier)

    p = sous.add_parser("initialiser", help="créer un dossier de départ (scénario + Excel)")
    p.add_argument("dossier")
    p.add_argument("--nom", help="nom de l'outil / du scénario")
    p.add_argument("--excel", help="nom du fichier Excel à créer (défaut : suivi.xlsx)")
    p.add_argument("--colonnes", help="colonnes de l'Excel, séparées par des virgules")
    p.add_argument("--ecraser", action="store_true")
    commun(p)
    p.set_defaults(fonction=cmd_initialiser)

    p = sous.add_parser("inspecter", help="ouvrir une page et l'inspecteur pour trouver les sélecteurs")
    p.add_argument("url", nargs="?")
    options_navigateur(p)
    commun(p)
    p.set_defaults(fonction=cmd_inspecter)

    p = sous.add_parser("releve", help="relever un écran (capture + champs + brouillon de scénario) pour Claude")
    p.add_argument("url", nargs="?")
    p.add_argument("--sortie", help="dossier des relevés (défaut : releves/)")
    p.add_argument("--nom", help="nom de l'écran (utilisé dans le nom du dossier et du scénario)")
    p.add_argument("--sans-pause", action="store_true", help="relever immédiatement sans attendre l'utilisateur")
    p.add_argument("--cache", action="store_true", help="navigateur invisible (tests)")
    options_navigateur(p)
    commun(p)
    p.set_defaults(fonction=cmd_releve)

    p = sous.add_parser("assistant", help="construire un scénario par questions/réponses (relevé + colonnes Excel)")
    p.add_argument("url", nargs="?", help="adresse de l'écran à relever d'abord (sinon : dernier relevé de releves/)")
    p.add_argument("--releve", help="dossier d'un relevé existant (releves/<date>-<nom>)")
    p.add_argument("--excel", help="Excel de suivi : ses colonnes sont proposées pour chaque champ")
    p.add_argument("--feuille", help="feuille de l'Excel")
    p.add_argument("--sortie", help="fichier YAML à écrire (défaut : <nom>.yaml à côté de l'Excel)")
    p.add_argument("--sortie-releve", help="dossier des relevés (défaut : releves/)")
    p.add_argument("--nom", help="nom du scénario")
    p.add_argument("--ecraser", action="store_true")
    p.add_argument("--sans-pause", action="store_true", help="relever l'écran immédiatement (tests)")
    p.add_argument("--cache", action="store_true", help="navigateur invisible (tests)")
    options_navigateur(p)
    commun(p)
    p.set_defaults(fonction=cmd_assistant)

    p = sous.add_parser("menu", help="menu simple : tout faire sans retenir de commande")
    commun(p)
    p.set_defaults(fonction=cmd_menu)

    p = sous.add_parser("enregistrer", help="montrer une tâche au robot : il la refera seul")
    p.add_argument("url", help="adresse de l'outil (ou chemin d'un fichier local)")
    p.add_argument("--excel", help="Excel qui pilote la tâche (une ligne = une exécution)")
    p.add_argument("--feuille", help="feuille de l'Excel")
    p.add_argument("--nom", help="nom de la tâche")
    p.add_argument("--sortie", help="fichier YAML à écrire (défaut : <nom>.yaml à côté de l'Excel)")
    p.add_argument("--ecraser", action="store_true")
    options_navigateur(p)
    commun(p)
    p.set_defaults(fonction=cmd_enregistrer)

    p = sous.add_parser("scenarios", help="lister les tâches enregistrées")
    p.add_argument("--dossier", help="dossier où chercher (défaut : le dossier courant)")
    commun(p)
    p.set_defaults(fonction=cmd_scenarios)

    p = sous.add_parser("supprimer", help="retirer une tâche (le fichier part dans corbeille/)")
    p.add_argument("scenario")
    commun(p)
    p.set_defaults(fonction=cmd_supprimer)

    p = sous.add_parser("codegen", help="enregistreur Playwright (avancé, produit du code Python)")
    p.add_argument("url", nargs="?")
    p.add_argument("--sortie", help="fichier .py où écrire le code généré")
    options_navigateur(p)
    commun(p)
    p.set_defaults(fonction=cmd_codegen)

    p = sous.add_parser("extraire", help="extraire des champs de documents vers un Excel")
    p.add_argument("regles", help="fichier YAML des règles d'extraction")
    p.add_argument("--dossier", help="dossier des documents (défaut : celui des règles ou le dossier courant)")
    p.add_argument("--sortie", help="Excel à créer (défaut : extraction.xlsx)")
    p.add_argument("--ecraser", action="store_true")
    p.add_argument("--journal", action="store_true", help="écrire aussi un fichier journal/")
    commun(p)
    p.set_defaults(fonction=cmd_extraire)

    p = sous.add_parser("base-demo", help="lancer la fausse base documentaire (bac à sable pour s'entraîner)")
    p.add_argument("--dossier", help="dossier de travail (défaut : ./bac_a_sable)")
    p.add_argument("--port", type=int, default=8765, help="port local (défaut : 8765)")
    p.add_argument("--sans-attente", action="store_true", help="préparer le dossier et s'arrêter (tests)")
    commun(p)
    p.set_defaults(fonction=cmd_base_demo)

    p = sous.add_parser("demo", help="vérifier l'installation avec un formulaire local")
    p.add_argument("--dossier", help="dossier de la démo (défaut : ./demo)")
    p.add_argument("--cache", action="store_true", help="navigateur invisible")
    p.add_argument("--sans-pause", action="store_true")
    p.add_argument("--fichier", action="store_true", help="ouvrir la page en file:// au lieu d'un serveur http local")
    commun(p)
    p.set_defaults(fonction=cmd_demo)
    return parseur


def main(argv: Optional[List[str]] = None) -> int:
    _preparer_console()
    parseur = construire_parseur()
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments:  # sans rien taper : le menu, pour ne rien avoir à retenir
        arguments = ["menu"]
    args = parseur.parse_args(arguments)
    try:
        return int(args.fonction(args) or 0)
    except ErreurAutoweb as e:
        if not journal.handlers:
            configurer_journal(None)
        journal.error("%s", e)
        return 2
    except KeyboardInterrupt:
        print("\nInterrompu.")
        return 130


if __name__ == "__main__":
    sys.exit(main())
