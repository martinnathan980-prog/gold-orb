"""Ouverture du navigateur avec Playwright, adaptée à un poste d'entreprise.

Priorités (aucun téléchargement d'exécutable nécessaire) :
1. `attacher`   : se brancher sur un Edge/Chrome DÉJÀ ouvert avec le port de
                  débogage (voir README : `msedge --remote-debugging-port=9222`).
                  On profite alors des sessions déjà connectées (SSO...).
2. `canal`      : lancer le Edge (`msedge`) ou le Chrome (`chrome`) installé sur
                  le poste. `auto` essaie msedge, puis chrome, puis le chromium
                  de Playwright s'il a été installé (`python -m playwright install chromium`).
3. `executable` : chemin explicite vers un msedge.exe / chrome.exe.

`profil` : dossier de profil persistant (cookies, sessions) => on se connecte
une fois à la main, et les exécutions suivantes restent connectées.
"""

from __future__ import annotations

import logging
import os
import re
import socket
from contextlib import contextmanager
import sys
import time
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple
from urllib.parse import urlsplit

from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, Page, sync_playwright

from .erreurs import ErreurAutoweb, NavigateurFerme
from .scenario import ConfigNavigateur

journal = logging.getLogger("autoweb")

VAR_EXECUTABLE = "AUTOWEB_EXECUTABLE"

# Onglets que Chrome (ou Edge) ouvre de lui-même : nouveautés, bienvenue, présentation...
# Ils n'ont rien à voir avec la tâche et passent devant l'onglet du robot.
MOTIF_ONGLET_PARASITE = re.compile(
    r"^(?:"
    r"(?:chrome|edge)://(?:whats-new|welcome|welcome-win10|intro|privacy-sandbox-dialog"
    r"|settings/reset|managed-user-profile-notice)"
    r"|https?://(?:www\.)?google\.[a-z.]{2,6}/(?:intl/[^/]+/)?chrome(?:[/?#]|$)"
    r"|https?://microsoftedgewelcome\.microsoft\.com/"
    r"|chrome-extension://"  # page de bienvenue d'une extension imposée, ouverte à son installation
    r")",
    re.IGNORECASE,
)
# Onglet vide : ouvert par l'utilisateur (Ctrl+T) ou encore en cours d'ouverture. Jamais fermé.
MOTIF_ONGLET_VIDE = re.compile(
    r"^(?:about:blank|chrome://new-?tab(?:-page)?/?|chrome-search://local-ntp|edge://newtab)",
    re.IGNORECASE,
)
# Réglages par défaut de Playwright qui éloignent le Chrome du robot du Chrome habituel :
# sans eux, les extensions imposées par l'entreprise (connexion automatique Microsoft, Okta...)
# ne peuvent ni s'installer ni fonctionner, et le portail redemande le mot de passe.
ARGUMENTS_RETIRES = ("--disable-extensions", "--disable-background-networking")
# Le Chrome du robot : un seul profil pour la carte, les enregistrements et les relances.
PROFIL_ROBOT = Path(__file__).resolve().parent.parent / "profils" / "chrome_robot"
NOMS_PROFIL_ROBOT = ("robot", "chrome_robot")
MESSAGE_PROFIL_OUVERT = (
    "Le Chrome du robot est déjà ouvert : une autre fenêtre du robot, ou celle ouverte avec le\n"
    "choix 10 du menu. Fermez toutes ses fenêtres (et les autres fenêtres noires du robot),\n"
    "puis recommencez."
)
# Extension de connexion automatique Microsoft (Entra) : sa présence est vérifiée, rien d'autre.
EXTENSION_SSO_MICROSOFT = "ppnbnpeolgkicgegkbkbjmhlideopiji"
# Onglets sans lien avec l'outil ouverts juste après le démarrage (extension imposée par
# l'entreprise, page de présentation...) : fermés s'ils arrivent dans ce délai.
FENETRE_DEMARRAGE_S = 15.0


def est_onglet_parasite(url: str) -> bool:
    return bool(MOTIF_ONGLET_PARASITE.match(url or ""))


def est_onglet_vide(url: str) -> bool:
    return not url or bool(MOTIF_ONGLET_VIDE.match(url))


def site_de(url: str) -> str:
    """« entreprise.fr » pour https://outil.entreprise.fr/... : deux onglets du même site
    appartiennent à la même tâche (outil, connexion d'entreprise, lien ouvert à part)."""
    try:
        hote = (urlsplit(url or "").hostname or "").lower()
    except ValueError:
        return ""
    if not hote or re.fullmatch(r"[\d.]+|\[?[0-9a-f:]+\]?", hote) or "." not in hote:
        return hote
    return ".".join(hote.split(".")[-2:])


def _a_un_ouvreur(page: Page) -> bool:
    """Vrai si l'onglet a été ouvert par une page (lien, window.open).

    page.opener() répond None quand la page d'origine s'est refermée entre-temps
    (portail qui ouvre l'application puis se ferme) : l'objet interne, lui, s'en souvient.
    """
    try:
        if page.opener() is not None:
            return True
    except Exception:  # noqa: BLE001
        pass
    interne = getattr(page, "_impl_obj", None)
    return getattr(interne, "_opener", None) is not None


def chemin_profil(profil: str, dossier: Path) -> Path:
    """Dossier du profil. « robot » : le Chrome du robot. Les tâches enregistrées en version 18
    (taches/profils/<tâche>, un Chrome à connecter par tâche) utilisent désormais le même."""
    if str(profil).strip().lower() in NOMS_PROFIL_ROBOT:
        return PROFIL_ROBOT
    chemin = Path(profil)
    if not chemin.is_absolute():
        chemin = Path(dossier) / chemin
    if chemin.parent.name == "profils" and chemin.parent.parent.name == "taches":
        return PROFIL_ROBOT
    return chemin


def reprendre_ancien_profil(profil_robot: Path = PROFIL_ROBOT) -> None:
    """Le Chrome du robot n'a jamais servi : on reprend le profil de la carte de la version 18
    (profils/explorateur), sinon le plus récent des tâches de la version 18, pour garder la
    connexion déjà faite dedans. Rien n'est copié depuis le Chrome habituel."""
    profil_robot = Path(profil_robot)
    if (profil_robot / "Default").is_dir():
        return
    racine = profil_robot.parent.parent
    taches = racine / "taches" / "profils"
    anciens = [racine / "profils" / "explorateur"]
    if taches.is_dir():
        anciens += sorted((d for d in taches.iterdir() if d.is_dir()), key=lambda d: d.stat().st_mtime, reverse=True)
    for ancien in anciens:
        if not (ancien / "Default").is_dir() or profil_verrouille(ancien):
            continue
        try:
            if profil_robot.exists():
                profil_robot.rmdir()  # dossier vide laissé par un démarrage raté ; sinon OSError : on garde
            profil_robot.parent.mkdir(parents=True, exist_ok=True)
            ancien.rename(profil_robot)
            journal.info("Chrome du robot : connexion reprise de %s", ancien.name)
            return
        except OSError as e:
            journal.debug("Reprise de %s impossible : %s", ancien, e)


def profil_verrouille(profil: Path) -> bool:
    """Vrai si un Chrome se sert déjà de ce profil (Chrome refuse d'en ouvrir un second)."""
    profil = Path(profil)
    if sys.platform == "win32":
        verrou = profil / "lockfile"
        if not verrou.exists():
            return False
        try:
            with open(verrou, "a"):  # Chrome le garde ouvert sans partage tant qu'il tourne
                return False
        except PermissionError:
            return True
        except OSError:
            return False
    try:
        cible = os.readlink(profil / "SingletonLock")  # « machine-1234 »
    except OSError:
        return False
    machine, _, pid = cible.rpartition("-")
    if not pid.isdigit() or (machine and machine != socket.gethostname()):
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def adresse_courte(url: str) -> str:
    """Hôte et chemin seulement : la suite d'une adresse peut contenir un jeton de session."""
    try:
        morceaux = urlsplit(url or "")
    except ValueError:
        return "?"
    if morceaux.scheme in ("http", "https"):
        return f"{morceaux.netloc}{morceaux.path}"
    return f"{morceaux.scheme}://{morceaux.netloc}{morceaux.path}"

CHEMINS_WINDOWS = {
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "msedge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\Edge\Application\msedge.exe"),
    ],
    "chromium": [
        os.path.expandvars(r"%LOCALAPPDATA%\Chromium\Application\chrome.exe"),
        r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    ],
}

CHEMINS_MAC = {
    "chrome": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        os.path.expanduser("~/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
        "/Applications/Google Chrome Beta.app/Contents/MacOS/Google Chrome Beta",
    ],
    "msedge": [
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
        os.path.expanduser("~/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ],
    "chromium": [
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
        "/Applications/Vivaldi.app/Contents/MacOS/Vivaldi",
    ],
}

CHEMINS_LINUX = {
    "chrome": ["/usr/bin/google-chrome", "/usr/bin/google-chrome-stable", "/opt/google/chrome/chrome"],
    "msedge": ["/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable"],
    "chromium": ["/usr/bin/chromium", "/usr/bin/chromium-browser", "/snap/bin/chromium"],
}

NOM_NAVIGATEUR = {"msedge": "Microsoft Edge", "chrome": "Google Chrome", "chromium": "Chromium"}


def premiere_ligne(e: BaseException) -> str:
    texte = str(e).strip()
    return texte.splitlines()[0] if texte else e.__class__.__name__


MESSAGE_STRATEGIE = (
    "Le poste interdit d'exécuter les programmes rangés dans votre compte utilisateur\n"
    "(stratégie de groupe, erreur 1260). Playwright s'appuie sur un petit programme de ce\n"
    "type, il ne peut donc pas démarrer ici.\n"
    "Deux pistes :\n"
    "  1. Demander au service informatique d'autoriser ces deux dossiers :\n"
    "       %LOCALAPPDATA%\\ms-playwright\n"
    "       le dossier « playwright\\driver » des bibliothèques Python\n"
    "     (ce sont des fichiers déposés dans votre profil, sans installation ni droits admin).\n"
    "  2. En attendant, dites-le moi : il existe une solution qui pilote votre Chrome\n"
    "     déjà installé, sans aucun programme supplémentaire."
)


def blocage_strategie(e: BaseException) -> bool:
    """Vrai si l'erreur vient d'une stratégie d'entreprise qui interdit d'exécuter un programme."""
    texte = f"{e}".lower()
    return (
        "1260" in texte
        or "stratégie de groupe" in texte
        or "strategie de groupe" in texte
        or "blocked by group policy" in texte
        or "this program is blocked" in texte
    )


def navigateur_introuvable(e: BaseException) -> bool:
    """Vrai si l'erreur dit seulement que ce navigateur n'est pas installé sur le poste. Seule la
    première ligne compte (la suite est le journal du navigateur, plein de « No such file »)."""
    if navigateur_ferme(e):
        return False
    texte = premiere_ligne(e)
    return any(m in texte for m in ("is not found at", "Executable doesn't exist at", "distribution '",
                                    "is not installed"))


def navigateur_ferme(e: BaseException) -> bool:
    """Vrai si l'erreur Playwright signifie que la page / le navigateur a été fermé."""
    texte = str(e)
    return any(m in texte for m in (
        "has been closed", "Target closed", "Target page, context or browser has been closed",
        "browser has disconnected", "Browser closed", "Connection closed", "Target crashed",
    ))


class Navigateur:
    """Cycle de vie du navigateur : ouvrir() -> page ; fermer()."""

    def __init__(self, config: ConfigNavigateur, dossier: Path, visible: Optional[bool] = None) -> None:
        self.config = config
        self.dossier = Path(dossier)
        self.visible = config.visible if visible is None else visible
        self._pw = None
        self.browser: Optional[Browser] = None
        self.contexte: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        self.attache = False
        self.description = ""
        self.canal_utilise: Optional[str] = None  # msedge / chrome / chromium / executable
        self.parasites: List[Page] = []  # onglets ouverts par Chrome lui-même, fermés par le robot
        self._creation = False  # vrai pendant que le robot ouvre lui-même un onglet
        self._ouvert_a = 0.0
        self._en_pause = False  # l'utilisateur a la main : ses boîtes de dialogue sont à lui
        # options supplémentaires du contexte (ex. l'explorateur bloque les service workers,
        # qui échapperaient à son contrôle des requêtes)
        self.options_contexte: dict = {}
        self.options_lancement: dict = {}  # ex. handle_sigint=False : Ctrl+C géré par l'appelant
        # quand l'utilisateur a la main (visite, enregistrement) : Chrome demande avant de renvoyer
        # un formulaire (F5 ou Retour après « Dupliquer ») au lieu de le renvoyer en silence
        self.confirmer_renvoi = False
        # décide de la réponse à une boîte de dialogue (« accepter », « refuser », ou None : le réglage)
        self.decider_dialogue: Optional[Any] = None
        self._dialogues_differes: List[Any] = []

    # ------------------------------------------------------------------ ouverture
    def ouvrir(self) -> Page:
        try:
            self._pw = sync_playwright().start()
        except Exception as e:
            if blocage_strategie(e):
                raise ErreurAutoweb(MESSAGE_STRATEGIE)
            raise
        try:
            if self.config.attacher:
                self._attacher(self.config.attacher)
            else:
                self._lancer()
        except Exception:
            self._pw.stop()
            self._pw = None
            raise
        assert self.contexte is not None
        self.contexte.set_default_timeout(self.config.delai_max)
        self.contexte.set_default_navigation_timeout(max(self.config.delai_max, 30000))
        self._ouvert_a = time.monotonic()
        if not self.attache:
            # branché AVANT tout : un onglet que Chrome ajoute dans la seconde qui suit est vu
            self.contexte.on("page", self._surveiller_onglet)
        if not self.contexte.pages:
            self._creation = True
            try:
                self.page = self.contexte.new_page()
            finally:
                self._creation = False
        elif self.attache:
            self.page = self.contexte.pages[0]
        else:
            self.page = self._garder_un_seul_onglet()
        for page in self.contexte.pages:
            self._brancher_page(page)
        self.contexte.on("page", self._brancher_page)
        if not self.attache and self.visible:
            self.utiliser_page(self.page)
        journal.info("Navigateur ouvert : %s", self.description)
        return self.page

    # ------------------------------------------------------------------ onglets parasites
    def _garder_un_seul_onglet(self) -> Page:
        """Au démarrage, seul l'onglet vide demandé par le robot compte.

        Avec un profil conservé, Chrome peut ajouter ses propres onglets (session
        précédente, nouveautés, pages imposées par l'entreprise) et l'ordre de la liste
        ne dit pas lequel est devant. Le robot garde l'onglet vide et ferme les autres :
        personne n'a encore rien fait, ce ne sont donc que des onglets de Chrome.
        """
        pages = [p for p in self.contexte.pages if not p.is_closed()]
        travail = next((p for p in pages if est_onglet_vide(p.url)), pages[0])
        for page in pages:
            if page is not travail:
                self._fermer_parasite(page)
        return travail

    def _surveiller_onglet(self, page: Page) -> None:
        """Onglet ouvert après le démarrage : fermé s'il vient de Chrome et non de l'outil.

        Exécuté par Playwright pendant un appel du robot : les appels Playwright sont
        permis ici, mais aucune exception ne doit s'échapper (Playwright la relancerait
        plus tard, au milieu d'une étape sans rapport).
        """
        try:
            if self._creation or page is self.page or page.is_closed():
                return
            if _a_un_ouvreur(page):
                return  # fenêtre ouverte par l'outil (lien, export, connexion) : on la garde
            if est_onglet_vide(page.url):
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
            url = page.url
            recent = time.monotonic() - self._ouvert_a < FENETRE_DEMARRAGE_S
            # un onglet du même site que l'outil (clic molette, Ctrl+clic...) fait partie de la tâche
            sites_outil = {site_de(p.url) for p in self.pages_de_travail() if p is not page} - {""}
            etranger = site_de(url) not in sites_outil
            if est_onglet_parasite(url) or (recent and etranger and not est_onglet_vide(url)):
                self._fermer_parasite(page)
                if self.visible and self.page is not None and not self.page.is_closed():
                    self.page.bring_to_front()
        except Exception as e:  # noqa: BLE001 - voir la docstring
            journal.debug("Surveillance d'onglet : %s", e)

    def _fermer_parasite(self, page: Page) -> None:
        if page is self.page:
            return
        ouvertes = [p for p in self.contexte.pages if not p.is_closed()] if self.contexte else []
        if len(ouvertes) <= 1:
            return  # fermer le dernier onglet fermerait la fenêtre
        self.parasites.append(page)
        journal.info("Onglet ouvert par le navigateur lui-même, fermé : %s", adresse_courte(page.url))
        try:
            page.close()
        except Exception as e:  # noqa: BLE001
            journal.debug("Fermeture d'onglet impossible : %s", e)

    def pages_de_travail(self) -> List[Page]:
        """Onglets ouverts, sans ceux que Chrome a ouverts de lui-même."""
        if self.contexte is None:
            return []
        return [
            p for p in self.contexte.pages
            if not p.is_closed() and p not in self.parasites and not est_onglet_parasite(p.url)
        ]

    def pomper(self, duree_ms: int = 250) -> None:
        """Laisse Playwright traiter ses événements (fermeture des onglets parasites...)
        pendant que le robot attend l'utilisateur."""
        try:
            self.page_courante().wait_for_timeout(duree_ms)
        except Exception:  # noqa: BLE001 - navigateur fermé : l'étape suivante le dira
            time.sleep(duree_ms / 1000)

    def _brancher_page(self, page: Page) -> None:
        page.on("dialog", self._gerer_dialogue)

    def _gerer_dialogue(self, dialogue: Any) -> None:
        if self._en_pause:
            # pause manuelle : la boîte reste à l'écran, c'est l'utilisateur qui répond
            self._dialogues_differes.append(dialogue)
            return
        self._repondre_dialogue(dialogue)

    def _repondre_dialogue(self, dialogue: Any) -> None:
        mode = self.config.dialogues
        if self.decider_dialogue is not None:
            try:
                mode = self.decider_dialogue(dialogue) or mode
            except Exception:  # noqa: BLE001
                pass
        try:
            if mode == "ignorer":
                # comme Playwright sans gestionnaire : on ferme (on quitte la page si c'est demandé)
                if dialogue.type == "beforeunload":
                    dialogue.accept()
                else:
                    dialogue.dismiss()
                return
            journal.info("Boîte de dialogue (%s) : %s -> %s", dialogue.type, dialogue.message, mode)
            if mode == "accepter":
                dialogue.accept()
            else:
                dialogue.dismiss()
        except Exception:  # noqa: BLE001 - déjà fermée (par l'utilisateur) ou page fermée
            pass

    @contextmanager
    def pause_manuelle(self) -> Iterator[None]:
        """Pendant une pause, le navigateur continue de tourner mais ne répond pas aux
        boîtes de dialogue à la place de l'utilisateur. Celles qu'il a laissées ouvertes
        sont traitées normalement à la reprise."""
        self._en_pause = True
        try:
            yield
        finally:
            self._en_pause = False
            differes, self._dialogues_differes = self._dialogues_differes, []
            for dialogue in differes:
                self._repondre_dialogue(dialogue)

    def _attacher(self, url: str) -> None:
        if not url.startswith("http"):
            url = f"http://localhost:{url}" if url.isdigit() else f"http://{url}"
        try:
            self.browser = self._pw.chromium.connect_over_cdp(url, timeout=10000)
        except PlaywrightError as e:
            raise ErreurAutoweb(
                f"Impossible de se brancher sur le navigateur à {url} ({premiere_ligne(e)}).\n"
                "Lancez d'abord Edge avec le port de débogage, par exemple :\n"
                '  start msedge --remote-debugging-port=9222 --user-data-dir="%LOCALAPPDATA%\\autoweb-edge"\n'
                "puis relancez le robot."
            )
        contextes = self.browser.contexts
        self.contexte = contextes[0] if contextes else self.browser.new_context(accept_downloads=True)
        self.attache = True
        self.description = f"attaché à {url}"

    def _chemins_connus(self, canaux: List[str]) -> List[Tuple[str, str]]:
        """Navigateurs réellement présents sur ce poste, aux emplacements habituels."""
        if sys.platform == "darwin":
            table = CHEMINS_MAC
        elif sys.platform == "win32":
            table = CHEMINS_WINDOWS
        else:
            table = CHEMINS_LINUX
        trouves: List[Tuple[str, str]] = []
        vus = set()
        for canal in canaux:
            for chemin in table.get(canal, []):
                if chemin and chemin not in vus and Path(chemin).exists():
                    vus.add(chemin)
                    trouves.append((canal, chemin))
        return trouves

    def _candidats(self) -> List[Tuple[str, Optional[str]]]:
        """Liste (canal, executable) à essayer dans l'ordre. executable=None : canal Playwright."""
        executable = os.environ.get(VAR_EXECUTABLE) or self.config.executable
        if executable:
            return [("executable", executable)]
        canal = self.config.canal
        if canal == "auto":
            # Chrome d'abord : c'est le navigateur de travail le plus répandu.
            candidats: List[Tuple[str, Optional[str]]] = [("chrome", None), ("msedge", None)]
            candidats += list(self._chemins_connus(["chrome", "msedge", "chromium"]))
            candidats.append(("chromium", None))
            return candidats
        candidats = [(canal, None)]
        if canal != "chromium":
            candidats += list(self._chemins_connus([canal]))
        return candidats

    def _lancer(self) -> None:
        erreurs: List[str] = []
        if self.config.profil and profil_verrouille(chemin_profil(self.config.profil, self.dossier)):
            raise ErreurAutoweb(MESSAGE_PROFIL_OUVERT)
        for canal, executable in self._candidats():
            try:
                self._lancer_canal(canal, executable)
                self.canal_utilise = canal
                return
            except PlaywrightError as e:
                erreurs.append(f"  - {canal}{' (' + executable + ')' if executable else ''} : {premiere_ligne(e)}")
                journal.debug("Échec du lancement via %s : %s", canal, premiere_ligne(e))
                if self.config.profil and not navigateur_introuvable(e):
                    # Chrome est là mais n'a pas démarré sur ce profil (déjà ouvert, trop lent...) :
                    # surtout ne pas l'ouvrir avec un autre navigateur (Edge ou Chromium abîmeraient
                    # le profil de Chrome et sa connexion)
                    if navigateur_ferme(e):
                        raise ErreurAutoweb(MESSAGE_PROFIL_OUVERT + "\n(détail : " + premiere_ligne(e) + ")")
                    raise ErreurAutoweb(
                        f"{NOM_NAVIGATEUR.get(canal, canal)} n'a pas pu démarrer ({premiere_ligne(e)}).\n"
                        "Fermez les fenêtres du robot et recommencez ; si cela se répète, envoyez-moi ce message."
                    )
            except (FileNotFoundError, OSError) as e:
                erreurs.append(f"  - {canal} : {premiere_ligne(e)}")
        raise ErreurAutoweb(
            "Aucun navigateur n'a pu être lancé :\n" + "\n".join(erreurs) + "\n" + self._pistes()
        )

    def _pistes(self) -> str:
        """Conseils adaptés au système : ce qui débloque la situation ici."""
        if sys.platform == "darwin":
            return (
                "Ce Mac n'a ni Google Chrome ni Microsoft Edge installé, aux emplacements habituels.\n"
                "Pistes, de la plus simple à la plus technique :\n"
                "  1. Installez Google Chrome (gratuit, aucune autorisation spéciale) :\n"
                "       https://www.google.com/chrome\n"
                "     Glissez Google Chrome dans le dossier Applications, puis relancez le robot.\n"
                "  2. Si Chrome est installé ailleurs, donnez son chemin dans le scénario :\n"
                "       navigateur:\n"
                '         executable: "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"\n'
                f"     (ou variable d'environnement {VAR_EXECUTABLE}).\n"
                "  3. Le navigateur de secours de Playwright (python -m playwright install chromium)\n"
                "     n'existe pas pour macOS 12 et antérieur : sur ces Mac, il faut installer Chrome.\n"
                "  4. Ou branchez-vous sur un Chrome déjà ouvert : lancez chrome_debug.command,\n"
                "     puis dans le scénario : navigateur: attacher: 9222"
            )
        if sys.platform == "win32":
            return (
                "Pistes :\n"
                "  1. Indiquez le chemin de votre navigateur dans le scénario :\n"
                '       navigateur:\n         executable: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"\n'
                f"     (ou variable d'environnement {VAR_EXECUTABLE}).\n"
                "  2. Ou installez le chromium de Playwright (un dossier, pas un programme à installer) :\n"
                "       python -m playwright install chromium\n"
                "  3. Ou branchez-vous sur un Chrome déjà ouvert : lancez chrome_debug.bat,\n"
                "     puis dans le scénario : navigateur: attacher: 9222"
            )
        return (
            "Pistes :\n"
            "  1. Installez un navigateur (google-chrome, chromium) ou donnez son chemin :\n"
            f"       navigateur: executable: /usr/bin/google-chrome   (ou {VAR_EXECUTABLE}).\n"
            "  2. Ou : python -m playwright install chromium"
        )

    def _options_communes(self) -> dict:
        args = list(self.config.arguments)
        if self.visible and "--start-maximized" not in args and (self.config.largeur <= 0):
            args.append("--start-maximized")
        return {
            "headless": not self.visible,
            "slow_mo": self.config.lenteur or 0,
            "args": args,
            "downloads_path": str(self._dossier_telechargements()),
            "ignore_default_args": list(ARGUMENTS_RETIRES)
                                   + (["--disable-prompt-on-repost"] if self.confirmer_renvoi else []),
            # sans bac à sable, Chrome affiche un bandeau jaune inquiétant (« indicateur de ligne de
            # commande non pris en charge : --no-sandbox ») ; sous Linux (serveurs, tests en root)
            # le bac à sable n'est pas toujours possible
            "chromium_sandbox": sys.platform in ("win32", "darwin"),
            **self.options_lancement,
        }

    def _dossier_telechargements(self) -> Path:
        chemin = Path(self.config.telechargements)
        if not chemin.is_absolute():
            chemin = self.dossier / chemin
        chemin.mkdir(parents=True, exist_ok=True)
        return chemin

    def _viewport(self) -> dict:
        if self.config.largeur <= 0 or self.config.hauteur <= 0:
            return {"no_viewport": True}
        return {"viewport": {"width": self.config.largeur, "height": self.config.hauteur}}

    def _lancer_canal(self, canal: str, executable: Optional[str]) -> None:
        options = self._options_communes()
        if executable:
            if not Path(executable).exists():
                raise FileNotFoundError(f"exécutable introuvable : {executable}")
            options["executable_path"] = executable
            libelle = f"{NOM_NAVIGATEUR.get(canal, canal)} ({executable})"
        elif canal == "chromium":
            libelle = "chromium de Playwright"
        else:
            options["channel"] = canal
            libelle = NOM_NAVIGATEUR.get(canal, canal)
        if self.config.ignorer_https:
            options["ignore_https_errors"] = True

        if self.config.profil:
            profil = chemin_profil(self.config.profil, self.dossier)
            if profil == PROFIL_ROBOT:
                reprendre_ancien_profil(profil)
            profil.mkdir(parents=True, exist_ok=True)
            if "--hide-crash-restore-bubble" not in options["args"]:
                # sinon, après un arrêt brutal : bulle « Restaurer les pages ? » par-dessus l'outil
                options["args"] = list(options["args"]) + ["--hide-crash-restore-bubble"]
            self.contexte = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(profil), accept_downloads=True, **self._viewport(), **options,
                **self.options_contexte,
            )
            self.browser = None
            self.description = f"{libelle}, profil {profil}"
        else:
            options_lancement = {k: v for k, v in options.items() if k != "ignore_https_errors"}
            self.browser = self._pw.chromium.launch(**options_lancement)
            self.contexte = self.browser.new_context(
                accept_downloads=True,
                ignore_https_errors=self.config.ignorer_https,
                **self._viewport(),
                **self.options_contexte,
            )
            self.description = f"{libelle}, session temporaire"
        if not self.visible:
            self.description += " (invisible)"

    # ------------------------------------------------------------------ pages
    def page_courante(self) -> Page:
        if self.page is None or self.page.is_closed():
            pages = self.pages_de_travail()
            if not pages:
                raise NavigateurFerme("Toutes les pages du navigateur sont fermées.")
            self.page = pages[-1]
        return self.page

    def utiliser_page(self, page: Page) -> None:
        self.page = page
        try:
            page.bring_to_front()
        except PlaywrightError:
            pass

    # ------------------------------------------------------------------ fermeture
    def fermer(self) -> None:
        try:
            if self.attache:
                # on ne ferme jamais le navigateur de l'utilisateur, on se déconnecte seulement
                pass
            else:
                if self.contexte is not None:
                    try:
                        self.contexte.close()
                    except Exception:  # noqa: BLE001 - navigateur déjà fermé (Ctrl+C...)
                        pass
                if self.browser is not None:
                    try:
                        self.browser.close()
                    except Exception:  # noqa: BLE001
                        pass
        finally:
            if self._pw is not None:
                try:
                    self._pw.stop()
                except Exception:
                    pass
            self._pw = None
            self.contexte = None
            self.browser = None
            self.page = None


# ---------------------------------------------------------------------- diagnostic de connexion
def _politique_chrome(nom: str) -> Optional[Any]:
    """Valeur d'une stratégie Chrome de l'entreprise (registre Windows), ou None."""
    if sys.platform != "win32":
        return None
    import winreg  # type: ignore

    for racine in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
        try:
            with winreg.OpenKey(racine, r"SOFTWARE\Policies\Google\Chrome") as cle:
                return winreg.QueryValueEx(cle, nom)[0]
        except OSError:
            pass
        try:  # liste : une sous-clé du même nom, valeurs 1, 2, 3...
            with winreg.OpenKey(racine, rf"SOFTWARE\Policies\Google\Chrome\{nom}") as cle:
                valeurs, i = [], 0
                while True:
                    try:
                        valeurs.append(str(winreg.EnumValue(cle, i)[1]))
                    except OSError:
                        break
                    i += 1
                if valeurs:
                    return valeurs
        except OSError:
            pass
    return None


def diagnostic_connexion(profil: Optional[Path] = None) -> List[Tuple[str, str]]:
    """Réglages du poste qui décident si le Chrome du robot entre directement dans le portail,
    comme le Chrome habituel : des oui / non, jamais d'identifiant ni d'adresse."""
    lignes: List[Tuple[str, str]] = []
    try:
        from importlib.metadata import version

        lignes.append(("version de Playwright", version("playwright")))
    except Exception:  # noqa: BLE001
        pass
    if sys.platform == "win32":
        oui_non = lambda v: "oui" if v else "non"  # noqa: E731
        lignes.append(("connexion Microsoft automatique (CloudAPAuthEnabled)",
                       oui_non(_politique_chrome("CloudAPAuthEnabled") == 1)))
        lignes.append(("connexion Windows automatique pour certains sites (AuthServerAllowlist)",
                       oui_non(_politique_chrome("AuthServerAllowlist"))))
        imposees = _politique_chrome("ExtensionInstallForcelist") or []
        lignes.append(("extensions imposées par l'entreprise", str(len(imposees))))
        lignes.append(("dont la connexion Microsoft (Single Sign On)",
                       oui_non(any(EXTENSION_SSO_MICROSOFT in str(v) for v in imposees))))
        lignes.append(("pilotage de Chrome interdit par l'entreprise (RemoteDebuggingAllowed)",
                       oui_non(_politique_chrome("RemoteDebuggingAllowed") == 0)))
        lignes.append(("connexion à Chrome obligatoire (BrowserSignin)",
                       oui_non(_politique_chrome("BrowserSignin") == 2)))
    if profil is not None:
        lignes.append(("Chrome du robot déjà utilisé", "oui" if (Path(profil) / "Default").is_dir() else "non"))
        extensions = Path(profil) / "Default" / "Extensions"
        lignes.append(("extension de connexion Microsoft installée dans le Chrome du robot",
                       "oui" if (extensions / EXTENSION_SSO_MICROSOFT).is_dir() else "non"))
    return lignes
