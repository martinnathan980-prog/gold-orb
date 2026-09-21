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
from pathlib import Path
from typing import List, Optional, Tuple

from playwright.sync_api import Browser, BrowserContext, Error as PlaywrightError, Page, sync_playwright

from .erreurs import ErreurAutoweb, NavigateurFerme
from .scenario import ConfigNavigateur

journal = logging.getLogger("autoweb")

VAR_EXECUTABLE = "AUTOWEB_EXECUTABLE"

CHEMINS_WINDOWS = {
    "msedge": [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ],
    "chrome": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
}


def premiere_ligne(e: BaseException) -> str:
    texte = str(e).strip()
    return texte.splitlines()[0] if texte else e.__class__.__name__


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

    # ------------------------------------------------------------------ ouverture
    def ouvrir(self) -> Page:
        self._pw = sync_playwright().start()
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
        if not self.contexte.pages:
            self.page = self.contexte.new_page()
        else:
            self.page = self.contexte.pages[0]
        for page in self.contexte.pages:
            self._brancher_page(page)
        self.contexte.on("page", self._brancher_page)
        journal.info("Navigateur ouvert : %s", self.description)
        return self.page

    def _brancher_page(self, page: Page) -> None:
        mode = self.config.dialogues
        if mode == "ignorer":
            return  # sans gestionnaire, Playwright ferme les boîtes de dialogue automatiquement

        def gerer(dialogue) -> None:
            journal.info("Boîte de dialogue (%s) : %s -> %s", dialogue.type, dialogue.message, mode)
            try:
                if mode == "accepter":
                    dialogue.accept()
                else:
                    dialogue.dismiss()
            except PlaywrightError:
                pass

        page.on("dialog", gerer)

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

    def _candidats(self) -> List[Tuple[str, Optional[str]]]:
        """Liste (canal, executable) à essayer dans l'ordre."""
        executable = os.environ.get(VAR_EXECUTABLE) or self.config.executable
        if executable:
            return [("executable", executable)]
        canal = self.config.canal
        if canal == "auto":
            return [("msedge", None), ("chrome", None), ("chromium", None)]
        return [(canal, None)]

    def _lancer(self) -> None:
        erreurs: List[str] = []
        for canal, executable in self._candidats():
            try:
                self._lancer_canal(canal, executable)
                self.canal_utilise = canal
                return
            except PlaywrightError as e:
                erreurs.append(f"  - {canal}{' (' + executable + ')' if executable else ''} : {premiere_ligne(e)}")
                journal.debug("Échec du lancement via %s : %s", canal, premiere_ligne(e))
                if navigateur_ferme(e) and self.config.profil:
                    erreurs.append(
                        "    (un profil déjà utilisé par une autre fenêtre du navigateur provoque ce genre d'échec :"
                        " fermez l'autre instance ou changez « profil »)"
                    )
            except (FileNotFoundError, OSError) as e:
                erreurs.append(f"  - {canal} : {premiere_ligne(e)}")
        conseils = (
            "Aucun navigateur n'a pu être lancé :\n" + "\n".join(erreurs) + "\n"
            "Pistes :\n"
            "  1. Indiquez le chemin de votre Edge dans le scénario :\n"
            '       navigateur:\n         executable: "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe"\n'
            f"     (ou variable d'environnement {VAR_EXECUTABLE}).\n"
            "  2. Ou installez le chromium de Playwright (téléchargement d'un dossier, pas d'un .exe d'installation) :\n"
            "       python -m playwright install chromium\n"
            "  3. Ou branchez-vous sur un Edge déjà ouvert : navigateur.attacher: 9222 (voir README)."
        )
        raise ErreurAutoweb(conseils)

    def _options_communes(self) -> dict:
        args = list(self.config.arguments)
        if self.visible and "--start-maximized" not in args and (self.config.largeur <= 0):
            args.append("--start-maximized")
        return {
            "headless": not self.visible,
            "slow_mo": self.config.lenteur or 0,
            "args": args,
            "downloads_path": str(self._dossier_telechargements()),
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
            libelle = f"exécutable {executable}"
        elif canal == "chromium":
            libelle = "chromium de Playwright"
        else:
            options["channel"] = canal
            libelle = {"msedge": "Microsoft Edge", "chrome": "Google Chrome"}.get(canal, canal)
        if self.config.ignorer_https:
            options["ignore_https_errors"] = True

        if self.config.profil:
            profil = Path(self.config.profil)
            if not profil.is_absolute():
                profil = self.dossier / profil
            profil.mkdir(parents=True, exist_ok=True)
            self.contexte = self._pw.chromium.launch_persistent_context(
                user_data_dir=str(profil), accept_downloads=True, **self._viewport(), **options
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
            )
            self.description = f"{libelle}, session temporaire"
        if not self.visible:
            self.description += " (invisible)"

    # ------------------------------------------------------------------ pages
    def page_courante(self) -> Page:
        if self.page is None or self.page.is_closed():
            pages = [p for p in (self.contexte.pages if self.contexte else []) if not p.is_closed()]
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
                    except PlaywrightError:
                        pass
                if self.browser is not None:
                    try:
                        self.browser.close()
                    except PlaywrightError:
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
