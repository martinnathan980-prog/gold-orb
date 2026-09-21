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

from . import __version__
from . import symboles as S
from .erreurs import ErreurAutoweb
from .excel import creer_classeur

journal = logging.getLogger("autoweb")
DOSSIER_MODELES = Path(__file__).parent / "modeles"


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
    return 0 if (bilan.erreurs == 0 and not bilan.interrompu) else 1


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
    print()
    print("Prochaines étapes :")
    print(f"  1. Remplissez {excel.name} (une ligne par élément à saisir).")
    print(f"  2. Trouvez les sélecteurs de votre outil :  python -m autoweb inspecter https://votre-outil/...")
    print(f"  3. Adaptez les étapes dans {scenario.name}.")
    print(f"  4. Testez à blanc :  python -m autoweb simuler {scenario}")
    print(f"  5. Lancez pour de vrai :  python -m autoweb lancer {scenario} --limite 1")
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
    if args.url:
        # relevé de l'écran d'abord, dans la même session
        nav = _lancer_navigateur_libre(args)
        page = nav.ouvrir()
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
    texte = construire(releve, colonnes, dialogue, nom=args.nom, fichier_excel=(Path(args.excel).name if args.excel else "suivi.xlsx"), feuille=feuille)
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
    print("Prochaines étapes :")
    print(f"  python -m autoweb verifier \"{sortie}\"")
    print(f"  python -m autoweb simuler \"{sortie}\"")
    print(f"  python -m autoweb lancer \"{sortie}\" --limite 1")
    return 0


def cmd_enregistrer(args: argparse.Namespace) -> int:
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


def _servir_dossier(dossier: Path):
    """Sert `dossier` sur http://127.0.0.1:<port libre>/ dans un thread (démo)."""
    import threading
    from functools import partial
    from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

    class _Silencieux(SimpleHTTPRequestHandler):
        def log_message(self, *args) -> None:  # pas de bruit dans la console
            pass

    serveur = ThreadingHTTPServer(("127.0.0.1", 0), partial(_Silencieux, directory=str(dossier)))
    threading.Thread(target=serveur.serve_forever, daemon=True).start()
    port = serveur.server_address[1]
    return serveur, f"http://127.0.0.1:{port}/formulaire_demo.html"


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

    p = sous.add_parser("enregistrer", help="enregistrer vos actions (playwright codegen)")
    p.add_argument("url", nargs="?")
    p.add_argument("--sortie", help="fichier .py où écrire le code généré")
    options_navigateur(p)
    commun(p)
    p.set_defaults(fonction=cmd_enregistrer)

    p = sous.add_parser("extraire", help="extraire des champs de documents vers un Excel")
    p.add_argument("regles", help="fichier YAML des règles d'extraction")
    p.add_argument("--dossier", help="dossier des documents (défaut : celui des règles ou le dossier courant)")
    p.add_argument("--sortie", help="Excel à créer (défaut : extraction.xlsx)")
    p.add_argument("--ecraser", action="store_true")
    p.add_argument("--journal", action="store_true", help="écrire aussi un fichier journal/")
    commun(p)
    p.set_defaults(fonction=cmd_extraire)

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
    args = parseur.parse_args(argv)
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
