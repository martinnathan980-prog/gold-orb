"""Explorateur : parcourt un portail web SANS RIEN MODIFIER et en dresse la carte.

Le robot part de la page d'accueil (l'utilisateur s'est connecté), puis visite
les liens et clique sur les éléments de navigation (menus, onglets, lignes de
tableau, boutons de consultation). Pour chaque écran rencontré, il note les
champs, les boutons, les tableaux, et comment on y arrive.

Sécurité, en trois couches indépendantes :
1. il ne remplit aucun champ, n'appuie sur aucune touche, ne coche rien ;
2. il ne clique que sur des éléments de navigation ou de consultation, jamais sur
   un élément dont le texte évoque une modification (supprimer, enregistrer, valider,
   créer, modifier, exporter, déconnexion...), ni sur un bouton sans texte ;
3. toute requête qui enverrait des données au portail (POST, PUT, DELETE...) est
   bloquée dans le navigateur avant de partir, et notée : c'est le filet de sécurité
   si un bouton d'apparence anodine essaie malgré tout de modifier quelque chose.
Les boîtes de dialogue de confirmation reçoivent toujours « Annuler ».

Sur une grosse base, tout visiter serait infini : deux exemples suffisent par
modèle d'écran (deux fiches composant, deux pages de liste...).

Résultats, dans explorations/<date>/ :
- carte.json : tout ce qui a été vu (reste sur le poste : peut contenir des données) ;
- carte.html : la même chose, lisible dans le navigateur ;
- carte_a_partager.txt : la structure seule (écrans, libellés, boutons, colonnes),
  sans valeurs, sans contenu de tableau, sans titre de page ni adresse du serveur.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import logging
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import parse_qsl, urlsplit

from playwright.sync_api import Page

from . import symboles as S
from .erreurs import ErreurAutoweb
from .navigateur import Navigateur

journal = logging.getLogger("autoweb")


# ---------------------------------------------------------------------- vocabulaire
def normaliser(texte: str) -> str:
    """minuscules, sans accents, espaces simples : « Créer un Plan » -> « creer un plan »."""
    texte = unicodedata.normalize("NFD", str(texte or ""))
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texte.lower()).strip()


# Début de mot qui évoque une modification, une sortie ou un fichier : jamais cliqué.
# (« \b » : « consignes » ne contient pas le mot « sign... », « terminal » reste permis)
MOTS_INTERDITS = (
    "supprim", "effac", "delete", "remove", "retir", "archiver", "valid", "enregistr",
    "sauvegard", "save", "submit", "soumettre", "envoyer", "send", "publier", "publish", "diffuser",
    "cree", "creer", "creat", "ajout", "add", "insert", "nouveau", "nouvelle", "new", "modif",
    "edit", "import", "upload", "joindre", "dupliqu", "copier", "clon", "deplac", "affecter",
    "attribuer", "assign", "approuv", "rejet", "refus", "signer", "sign in", "sign up", "signup",
    "confirm", "annul", "cancel", "reinitialis", "reset", "deconnex", "deconnect", "disconnect",
    "logout", "log out", "logoff", "sign out", "signout", "quitter", "fermer", "close", "imprim",
    "print", "export", "telecharg", "download", "verrou", "deverrou", "lock", "unlock", "clotur",
    "transfer", "commander", "achat", "acheter", "payer", "paiement", "payment", "vider", "purge",
    "restaur", "activer", "activate", "desactiv", "deactivat", "mettre a jour", "mise a jour",
    "update", "generer", "generate", "generation", "lancer", "execut", "run", "demarrer", "start",
    "stop", "arreter", "notif", "partag", "share", "invit", "abonn", "subscri", "vote", "accepter",
    "accept", "decline", "renomm", "rename", "fusion", "merge", "calcul", "recalcul", "traiter",
    "sync", "reserver", "liberer", "debloquer", "bloquer", "reviser", "revision", "indicer",
)
MOTIF_INTERDIT = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(m) for m in MOTS_INTERDITS) + ")")

# Boutons de simple consultation : permis même hors des menus (« Rechercher », « Voir »...).
MOTS_LECTURE = (
    "rechercher", "recherche", "chercher", "search", "filtrer", "filtre", "afficher", "voir",
    "view", "consulter", "ouvrir", "open", "detail", "details", "plus", "more", "suivant",
    "next", "precedent", "previous", "prev", "page", "onglet", "actualiser", "rafraichir",
    "refresh", "reload", "developper", "deplier", "replier", "agrandir", "apercu", "preview",
    "historique", "history", "retour", "back", "accueil", "home", "trier", "sort", "tout",
)
MOTIF_LECTURE = re.compile(r"(?<![a-z0-9])(?:" + "|".join(re.escape(m) for m in MOTS_LECTURE) + r")(?![a-z])")

EXTENSIONS_FICHIERS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".csv", ".zip", ".7z", ".rar", ".txt",
    ".xml", ".json", ".dwg", ".dxf", ".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".ppt", ".pptx",
)
METHODES_LECTURE = ("GET", "HEAD", "OPTIONS")


def mot_interdit(*textes: str) -> Optional[str]:
    """Le mot qui interdit le clic, ou None."""
    for texte in textes:
        m = MOTIF_INTERDIT.search(normaliser(texte))
        if m:
            return m.group(0)
    return None


def est_lecture(texte: str) -> bool:
    return bool(MOTIF_LECTURE.search(normaliser(texte)))


def _segment_variable(segment: str) -> bool:
    return bool(re.search(r"\d", segment)) or len(segment) > 24


def modele_url(url: str) -> str:
    """Adresse sans le serveur ni les valeurs : /plans/1234?onglet=2 -> /plans/{id}?onglet={}.
    Deux adresses qui ne diffèrent que par ces valeurs montrent le même modèle d'écran."""
    try:
        m = urlsplit(url or "")
    except ValueError:
        return ""
    if m.scheme not in ("http", "https", "file"):
        return f"{m.scheme}:"
    chemin = "/".join("{id}" if _segment_variable(s) else s for s in m.path.split("/"))
    requete = "&".join(sorted(f"{k}={{}}" for k, _ in parse_qsl(m.query, keep_blank_values=True)))
    fragment = m.fragment
    if fragment:
        if "=" in fragment and not fragment.startswith("/"):
            fragment = "&".join(sorted(f"{p.split('=', 1)[0]}={{}}" for p in fragment.split("&")))
        else:
            fragment = "/".join("{id}" if _segment_variable(s) else s for s in fragment.split("/"))
    return chemin + (f"?{requete}" if requete else "") + (f"#{fragment}" if fragment else "")


def masquer(texte: str) -> str:
    """Pour la carte à partager : tout mot contenant un chiffre, et les adresses mail, sont masqués
    (sauf les repères d'écran E1, E2... ajoutés par le robot)."""
    texte = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", str(texte or ""))
    return re.sub(r"\S*\d\S*", lambda m: m.group(0) if re.fullmatch(r"\(?E\d+[),;.]*", m.group(0)) else "#", texte)


TYPES_CHAMPS = {
    "text": "texte", "number": "nombre", "checkbox": "case à cocher", "radio": "choix unique",
    "password": "mot de passe", "search": "recherche", "file": "fichier", "email": "mail",
    "tel": "téléphone", "datetime-local": "date et heure", "month": "mois", "url": "adresse web",
}


def type_champ(type_brut: str) -> str:
    return TYPES_CHAMPS.get(type_brut, type_brut)


# ---------------------------------------------------------------------- lecture d'un écran
JS_ECRAN = r"""
() => {
  const vis = e => {
    if (!e || !e.isConnected) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const court = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n || 80);
  const idOk = id => !!id && /^[A-Za-z_][\w-]*$/.test(id) && !/\d{3,}/.test(id) && id.length <= 40;
  const libelle = e => {
    if (idOk(e.id)) { try { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return court(l.innerText); } catch (err) {} }
    const p = e.closest('label'); if (p) return court(p.innerText);
    const al = e.getAttribute('aria-label'); if (al) return court(al);
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = document.getElementById(lb.split(' ')[0]); if (t) return court(t.innerText); }
    const ph = e.getAttribute('placeholder'); if (ph) return court(ph);
    const prev = e.previousElementSibling;
    if (prev && ['LABEL', 'SPAN', 'TD', 'TH', 'DIV', 'B', 'STRONG'].includes(prev.tagName) && court(prev.innerText, 61).length < 60) return court(prev.innerText);
    return '';
  };
  const chemin = e => {
    const parts = [];
    let n = e;
    while (n && n.nodeType === 1 && n !== document.body && n !== document.documentElement) {
      if (idOk(n.id)) {
        let unique = false;
        try { unique = document.querySelectorAll('#' + CSS.escape(n.id)).length === 1; } catch (err) {}
        if (unique) { parts.unshift('#' + CSS.escape(n.id)); return parts.join(' > '); }
      }
      let k = 1, s = n;
      while ((s = s.previousElementSibling)) if (s.tagName === n.tagName) k++;
      parts.unshift(n.tagName.toLowerCase() + ':nth-of-type(' + k + ')');
      n = n.parentElement;
    }
    return 'body > ' + parts.join(' > ');
  };
  const zone = e => {
    if (e.getAttribute('role') === 'tab' || e.closest('[role=tablist]')) return 'onglet';
    if (e.closest('tbody tr, [role=row]')) return 'tableau';
    if (e.closest('nav, [role=navigation], [role=menu], [role=menubar], header, aside, .menu, .sidebar, .navbar, .nav, .breadcrumb')) return 'menu';
    return 'page';
  };
  const ligne = e => {
    const tr = e.closest('tbody tr, [role=row]');
    if (!tr || !tr.parentElement) return -1;
    return Array.prototype.indexOf.call(tr.parentElement.children, tr);
  };
  const titres = [];
  document.querySelectorAll('h1, h2, h3, [role=heading]').forEach(h => { if (vis(h) && titres.length < 12) titres.push(court(h.innerText, 100)); });
  const champs = [];
  document.querySelectorAll('input, select, textarea, [contenteditable=true]').forEach(e => {
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden' || ['submit', 'button', 'reset', 'image'].includes(type) || !vis(e)) return;
    champs.push({
      libelle: libelle(e), nom: e.id || e.getAttribute('name') || '',
      type: tag === 'select' ? 'liste' : tag === 'textarea' ? 'texte long' : (e.isContentEditable && tag !== 'input') ? 'texte riche' : (type || 'texte'),
      obligatoire: !!e.required, lecture_seule: !!(e.readOnly || e.disabled),
      nb_options: tag === 'select' ? e.options.length : 0,
      options: tag === 'select' ? Array.from(e.options).slice(0, 15).map(o => court(o.text, 60)) : [],
      dans_tableau: !!e.closest('tbody tr'),
    });
  });
  const tableaux = [];
  document.querySelectorAll('table, [role=grid]').forEach(t => {
    if (!vis(t) || t.closest('table table')) return;
    let entetes = Array.from(t.querySelectorAll('thead th, [role=columnheader]')).map(th => court(th.innerText, 60));
    if (!entetes.length) { const tr = t.querySelector('tr'); if (tr) entetes = Array.from(tr.querySelectorAll('th')).map(th => court(th.innerText, 60)); }
    tableaux.push({ entetes: entetes, lignes: t.querySelectorAll('tbody tr, [role=row]').length, selecteur: chemin(t) });
  });
  const cibles = [];
  const vus = new Set();
  const sel = 'a[href], button, input[type=submit], input[type=button], input[type=image], [role=button], [role=tab], [role=menuitem], [role=link], [onclick], summary';
  document.querySelectorAll(sel).forEach(e => {
    if (vus.has(e) || !vis(e)) return;
    vus.add(e);
    const tag = e.tagName.toLowerCase();
    let type = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'button' && !type) type = e.closest('form') ? 'submit' : 'button';
    const tr = e.closest('tbody tr, [role=row]');
    let rang = -1;
    if (tr) rang = Array.from(tr.querySelectorAll(sel)).indexOf(e);
    const table = e.closest('table, [role=grid], [role=table]');
    cibles.push({
      texte: court(e.innerText || e.value || '', 80),
      aria: court(e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('alt') || '', 80),
      tag: tag, type: type, role: e.getAttribute('role') || '', id: e.id || '',
      href: tag === 'a' ? (e.getAttribute('href') || '') : '',
      href_absolu: (tag === 'a' && e.href) ? String(e.href) : '',
      telechargement: tag === 'a' && e.hasAttribute('download'),
      desactive: !!e.disabled || e.getAttribute('aria-disabled') === 'true',
      zone: zone(e), ligne: ligne(e), rang: rang, tableau: table ? chemin(table) : '',
      dans_formulaire: !!e.closest('form'),
      methode_formulaire: e.closest('form') ? (e.closest('form').getAttribute('method') || 'get').toLowerCase() : '',
      selecteur: chemin(e),
    });
  });
  const cadres = Array.from(document.querySelectorAll('iframe, frame')).filter(vis).map(f => f.getAttribute('src') || '');
  return {
    url: location.href, titre: court(document.title, 120), titres: titres, champs: champs,
    tableaux: tableaux, cibles: cibles, cadres: cadres,
    mot_de_passe: !!Array.from(document.querySelectorAll('input[type=password]')).find(vis),
  };
}
"""

# L'écran est prêt quand plus rien ne bouge depuis 600 ms ET qu'aucun indicateur de
# chargement n'est visible (« Chargement... », sablier, aria-busy) ; 10 s au plus.
JS_CALME = r"""
() => new Promise(fini => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const charge = () => {
    if (document.readyState !== 'complete') return true;
    const indices = document.querySelectorAll('[aria-busy=true], .loading, .spinner, .loader, .chargement, #chargement, #loading, [class*=spinner], [class*=loading]');
    for (const e of indices) if (vis(e)) return true;
    for (const e of document.querySelectorAll('div, span, p')) {
      if (e.children.length) continue;
      const t = (e.textContent || '').trim().toLowerCase();
      if (t.length < 40 && /^(chargement|loading|veuillez patienter|please wait)/.test(t) && vis(e)) return true;
    }
    return false;
  };
  let derniere = Date.now();
  const obs = new MutationObserver(() => { derniere = Date.now(); });
  obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  const debut = Date.now();
  const tic = setInterval(() => {
    const fin = Date.now() - debut > 10000;
    if (fin || (Date.now() - derniere > 600 && !charge())) { clearInterval(tic); obs.disconnect(); fini(!fin); }
  }, 100);
})
"""


# ---------------------------------------------------------------------- modèle de la carte
@dataclass
class Action:
    """Un pas pour atteindre un écran : ouvrir une adresse, ou cliquer sur un élément."""

    type: str  # "aller" | "clic"
    url: str = ""
    selecteur: str = ""
    texte: str = ""
    tag: str = ""
    zone: str = ""
    tableau: str = ""
    ligne: int = -1
    rang: int = -1

    def libelle(self) -> str:
        if self.type == "aller":
            return f"ouvrir {modele_url(self.url)}"
        if self.zone == "tableau":
            return f"ligne {self.ligne + 1} du tableau"
        return self.texte or "(élément sans texte)"


@dataclass
class Ecran:
    id: str
    url: str
    modele: str
    signature: str
    chemin: List[Action]
    titre: str = ""
    titres: List[str] = field(default_factory=list)
    champs: List[Dict[str, Any]] = field(default_factory=list)
    tableaux: List[Dict[str, Any]] = field(default_factory=list)
    cibles: List[Dict[str, Any]] = field(default_factory=list)
    cadres: List[str] = field(default_factory=list)
    profondeur: int = 0
    # ce qui a été fait de chaque élément : texte -> « mène à E4 », « non cliqué : ... »...
    resultats: Dict[str, str] = field(default_factory=dict)


@dataclass
class Limites:
    ecrans: int = 150
    profondeur: int = 6
    minutes: float = 60.0
    delai_ms: int = 500
    exemples: int = 2  # écrans visités par modèle d'adresse, et lignes essayées par tableau


class ArretExploration(Exception):
    pass


def signature(lecture: Dict[str, Any]) -> str:
    """Empreinte de la STRUCTURE d'un écran (jamais des données) : deux fiches de
    composants différents ont la même empreinte."""
    menus = sorted({normaliser(c["texte"] or c["aria"]) for c in lecture["cibles"] if c["zone"] in ("menu", "onglet")})
    boutons = sorted({normaliser(c["texte"] or c["aria"]) for c in lecture["cibles"]
                      if c["zone"] not in ("tableau",) and c["tag"] != "a"})
    champs = sorted({(normaliser(c["libelle"]), c["type"]) for c in lecture["champs"] if not c["dans_tableau"]})
    # une liste vide et la même liste remplie (après « Rechercher ») sont deux écrans différents
    tableaux = sorted((tuple(normaliser(e) for e in t["entetes"]), t["lignes"] > 0) for t in lecture["tableaux"])
    base = modele_url(lecture["url"]).split("?")[0]
    brut = json.dumps([base, menus, boutons, champs, tableaux], ensure_ascii=False)
    return hashlib.sha1(brut.encode("utf-8")).hexdigest()[:12]


# ---------------------------------------------------------------------- explorateur
class Explorateur:
    def __init__(
        self,
        nav: Navigateur,
        dossier: Path,
        limites: Optional[Limites] = None,
        interactif: bool = True,
        connexion: Optional[Callable[[Page], None]] = None,
    ) -> None:
        self.nav = nav
        self.dossier = Path(dossier)
        self.limites = limites or Limites()
        self.interactif = interactif
        self.connexion = connexion  # tests : se connecter sans intervention
        self.ecrans: List[Ecran] = []
        self._par_signature: Dict[str, Ecran] = {}
        self._visites_modele: Dict[str, int] = {}
        self.transitions: List[Dict[str, str]] = []
        self.bloquees: List[Tuple[str, str]] = []  # (méthode, modèle d'adresse) : envois empêchés
        self.telechargements: List[str] = []
        self.externes: List[str] = []
        self.essais = 0
        self.hote = ""
        self.garde_active = False
        self._interrompu: List[int] = []
        self.arret = ""  # raison de fin d'exploration
        self._debut = 0.0
        self._relogins = 0
        self._nouvelles_pages: List[Page] = []

    # ------------------------------------------------------------------ sécurité réseau
    def _garde(self, route: Any) -> None:
        """Toute requête qui enverrait des données au portail est bloquée avant de partir."""
        try:
            requete = route.request
            methode = requete.method.upper()
            dangereuse = methode not in METHODES_LECTURE
            if not dangereuse and requete.is_navigation_request():
                # une simple adresse peut aussi modifier : /plans/7/supprimer, ?action=delete...
                m = urlsplit(requete.url)
                dangereuse = mot_interdit(m.path.replace("/", " ").replace("-", " ").replace("_", " "),
                                          m.query.replace("&", " ").replace("=", " ")) is not None
            if self.garde_active and dangereuse:
                self.bloquees.append((methode, modele_url(requete.url)))
                journal.debug("Requête bloquée : %s %s", methode, modele_url(requete.url))
                route.abort()
            else:
                route.continue_()
        except Exception as e:  # noqa: BLE001 - un gestionnaire ne doit jamais lever
            journal.debug("Garde : %s", e)

    def _telechargement(self, telechargement: Any) -> None:
        try:
            self.telechargements.append(telechargement.suggested_filename)
            telechargement.cancel()
        except Exception:  # noqa: BLE001
            pass

    def _nouvelle_page(self, page: Page) -> None:
        if page is not self.nav.page:
            self._nouvelles_pages.append(page)

    # ------------------------------------------------------------------ déroulement
    def explorer(self, url: str) -> None:
        import signal

        # Ctrl+C reçu au milieu d'un appel Playwright rendrait le navigateur impossible à
        # fermer : on le note, et l'exploration s'arrête proprement entre deux actions.
        try:
            ancien = signal.signal(signal.SIGINT, lambda *_: self._interrompu.append(1))
        except (ValueError, OSError):
            ancien = None
        try:
            self._explorer(url)
        finally:
            if ancien is not None:
                signal.signal(signal.SIGINT, ancien)

    def _explorer(self, url: str) -> None:
        page = self.nav.page_courante()
        self.nav.contexte.route("**/*", self._garde)
        self.nav.contexte.on("page", self._nouvelle_page)
        page.on("download", self._telechargement)
        self._debut = time.monotonic()
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001
            raise ErreurAutoweb(f"Impossible d'ouvrir {url} : {str(e).splitlines()[0]}")
        self._attendre(page)
        self._connexion(page, premiere_fois=True)
        page = self.nav.page_courante()
        self.hote = urlsplit(page.url).netloc
        self.garde_active = True
        depart = self._observer(page, [Action("aller", url=page.url)], 0)
        if depart is None:
            raise ErreurAutoweb("La page de départ n'a pas pu être lue.")
        self._visites_modele[depart.modele] = 1
        a_traiter = [depart]
        try:
            while a_traiter:
                ecran = a_traiter.pop(0)
                if ecran.profondeur >= self.limites.profondeur:
                    continue
                for cible in self._cibles_a_essayer(ecran):
                    self._verifier_limites()
                    nouveau = self._essayer(ecran, cible)
                    if nouveau is not None:
                        a_traiter.append(nouveau)
                        self.enregistrer()
            self.arret = self.arret or "tout ce qui était accessible sans rien modifier a été vu"
        except ArretExploration as e:
            self.arret = str(e)
        except KeyboardInterrupt:
            self.arret = "arrêt demandé (Ctrl+C)"
        finally:
            self.garde_active = False
            try:
                self.nav.contexte.unroute("**/*", self._garde)
            except Exception:  # noqa: BLE001
                pass
            self.enregistrer()

    def _verifier_limites(self) -> None:
        from .console import touche_entree_disponible

        if self._interrompu:
            raise ArretExploration("arrêt demandé (Ctrl+C)")
        if len(self.ecrans) >= self.limites.ecrans:
            raise ArretExploration(f"limite de {self.limites.ecrans} écrans atteinte")
        if time.monotonic() - self._debut > self.limites.minutes * 60:
            raise ArretExploration(f"limite de {self.limites.minutes:g} minutes atteinte")
        if touche_entree_disponible():
            raise ArretExploration("arrêt demandé (Entrée)")

    def _connexion(self, page: Page, premiere_fois: bool = False) -> None:
        """Première fois : l'utilisateur se connecte et choisit la page de départ.
        Ensuite : seulement si la session a expiré (un mot de passe est redemandé)."""
        if self.connexion is not None:
            self.connexion(page)
            self._attendre(page)
            return
        if not self.interactif:
            if premiere_fois:
                return
            raise ArretExploration("la session a expiré (connexion redemandée)")
        from .console import lire_ligne

        self._relogins += 0 if premiere_fois else 1
        if self._relogins > 3:
            raise ArretExploration("la connexion est redemandée sans cesse")
        print()
        if premiere_fois:
            print(f"{S.PAUSE}  Dans la fenêtre du robot : connectez-vous si besoin, puis allez sur la page")
            print("   d'ACCUEIL du portail (celle d'où part l'exploration).")
        else:
            print(f"{S.PAUSE}  Le portail redemande la connexion : reconnectez-vous dans la fenêtre du robot.")
        print("   Puis revenez ici et appuyez sur Entrée : ", end="", flush=True)
        actif, self.garde_active = self.garde_active, False  # la connexion envoie des données : permis
        try:
            with self.nav.pause_manuelle():
                lire_ligne(self.nav.pomper)
        finally:
            self.garde_active = actif
        self._attendre(self.nav.page_courante())

    def _attendre(self, page: Page) -> None:
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
        except Exception:  # noqa: BLE001
            pass
        try:
            page.wait_for_load_state("networkidle", timeout=4000)
        except Exception:  # noqa: BLE001
            pass
        try:
            page.evaluate(JS_CALME)
        except Exception:  # noqa: BLE001 - la page a changé pendant l'attente
            pass
        if self.limites.delai_ms:
            page.wait_for_timeout(self.limites.delai_ms)

    def _lire(self, page: Page) -> Optional[Dict[str, Any]]:
        for _ in range(2):
            try:
                return page.evaluate(JS_ECRAN)
            except Exception:  # noqa: BLE001 - navigation en cours : on réessaie une fois
                self._attendre(page)
        return None

    # ------------------------------------------------------------------ écrans
    def _observer(self, page: Page, chemin: List[Action], profondeur: int) -> Optional[Ecran]:
        """Lit l'écran courant ; renvoie un Ecran s'il est NOUVEAU, sinon None."""
        lecture = self._lire(page)
        if lecture is None:
            return None
        if lecture["mot_de_passe"] and self.ecrans:
            self._connexion(page)
            return None
        sig = signature(lecture)
        if sig in self._par_signature:
            return None
        modele = modele_url(lecture["url"])
        ecran = Ecran(
            id=f"E{len(self.ecrans) + 1}", url=lecture["url"], modele=modele, signature=sig,
            chemin=list(chemin), titre=lecture["titre"], titres=lecture["titres"],
            champs=lecture["champs"], tableaux=lecture["tableaux"], cibles=lecture["cibles"],
            cadres=lecture["cadres"], profondeur=profondeur,
        )
        self.ecrans.append(ecran)
        self._par_signature[sig] = ecran
        journal.info("   %s %s : « %s » — %d champ(s), %d élément(s) cliquable(s), %d tableau(x)",
                     S.OK, ecran.id, (ecran.titres[0] if ecran.titres else ecran.titre)[:60],
                     len(ecran.champs), len(ecran.cibles), len(ecran.tableaux))
        return ecran

    def _decision(self, cible: Dict[str, Any]) -> Tuple[str, str]:
        """(« aller » | « clic » | « non », raison). Aucune action risquée ne passe."""
        texte = cible["texte"] or cible["aria"]
        if cible["desactive"]:
            return "non", "désactivé"
        # une ligne de tableau entière : son texte, ce sont des données (« Archivé »...), pas une action
        interdit = mot_interdit(cible["aria"], cible["id"], cible["href"],
                                "" if cible["tag"] == "tr" else texte)
        if interdit:
            return "non", f"risque (« {interdit} »)"
        href = cible["href"].strip()
        if cible["tag"] == "a" and href and not href.startswith(("#", "javascript:")):
            absolu = cible["href_absolu"]
            m = urlsplit(absolu)
            if m.scheme in ("mailto", "tel"):
                return "non", "adresse mail / téléphone"
            if m.scheme not in ("http", "https", "file"):
                return "non", "lien spécial"
            if cible["telechargement"] or m.path.lower().endswith(EXTENSIONS_FICHIERS):
                self.telechargements.append(modele_url(absolu))
                return "non", "fichier à télécharger"
            if m.netloc != self.hote:
                self.externes.append(m.netloc)
                return "non", "lien vers un autre site"
            return "aller", ""
        if not texte.strip():
            return "non", "élément sans texte (icône) : on ne sait pas ce qu'il fait"
        if cible["type"] == "submit" and not est_lecture(texte):
            return "non", "bouton qui envoie un formulaire"
        if cible["zone"] in ("menu", "onglet") or cible["role"] in ("tab", "menuitem", "link") \
                or cible["tag"] in ("a", "summary") or cible["zone"] == "tableau" or est_lecture(texte):
            return "clic", ""
        return "non", "bouton d'action (à me montrer si utile)"

    def _cibles_a_essayer(self, ecran: Ecran) -> List[Dict[str, Any]]:
        retenues: List[Dict[str, Any]] = []
        deja: set = set()
        for cible in ecran.cibles:
            if cible["zone"] == "tableau" and not (0 <= cible["ligne"] < self.limites.exemples):
                continue  # une ligne de tableau ressemble aux autres : deux exemples suffisent
            action, raison = self._decision(cible)
            cle = self._cle(cible)
            if action == "non":
                ecran.resultats.setdefault(cle, f"non cliqué : {raison}")
                continue
            if action == "aller":
                modele = modele_url(cible["href_absolu"])
                if cible["href_absolu"].split("#")[0] == ecran.url.split("#")[0] and "#" not in cible["href"]:
                    continue  # lien vers la page elle-même
                if self._visites_modele.get(modele, 0) >= self.limites.exemples or (action, modele) in deja:
                    ecran.resultats.setdefault(cle, f"déjà vu ({modele})")
                    continue
                deja.add((action, modele))
            else:
                if (action, cle) in deja:
                    continue
                deja.add((action, cle))
            retenues.append(cible)
        return retenues

    @staticmethod
    def _cle(cible: Dict[str, Any]) -> str:
        if cible["zone"] == "tableau":
            return f"ligne {cible['ligne'] + 1} du tableau, élément {cible['rang'] + 1}"
        return cible["texte"] or cible["aria"] or cible["selecteur"]

    def _essayer(self, ecran: Ecran, cible: Dict[str, Any]) -> Optional[Ecran]:
        page = self.nav.page_courante()
        cle = self._cle(cible)
        if not self._restaurer(page, ecran):
            ecran.resultats[cle] = "écran impossible à retrouver"
            return None
        action, _ = self._decision(cible)
        if action == "aller":
            pas = Action("aller", url=cible["href_absolu"])
            modele = modele_url(pas.url)
            self._visites_modele[modele] = self._visites_modele.get(modele, 0) + 1
        else:
            pas = Action("clic", selecteur=cible["selecteur"], texte=cible["texte"] or cible["aria"],
                         tag=cible["tag"], zone=cible["zone"], tableau=cible["tableau"],
                         ligne=cible["ligne"], rang=cible["rang"])
        nb_bloquees, nb_fichiers = len(self.bloquees), len(self.telechargements)
        self._nouvelles_pages = []
        self.essais += 1
        if not self._jouer(page, pas):
            ecran.resultats[cle] = "clic impossible"
            return None
        page = self.nav.page_courante()
        notes = [f"ouvre une nouvelle fenêtre ({m})" for m in self._fermer_nouvelles_pages()]
        if len(self.bloquees) > nb_bloquees:
            notes.append("a voulu ENVOYER des données : bloqué")
        if len(self.telechargements) > nb_fichiers:
            notes.append("lance un téléchargement")
        if urlsplit(page.url).netloc != self.hote:
            self.externes.append(urlsplit(page.url).netloc)
            ecran.resultats[cle] = "sort du portail"
            return None
        chemin = [pas] if pas.type == "aller" else ecran.chemin + [pas]
        nouveau = self._observer(page, chemin, ecran.profondeur + 1)
        if nouveau is not None:
            notes.insert(0, f"mène à {nouveau.id}")
            self.transitions.append({"de": ecran.id, "action": cle, "vers": nouveau.id})
        else:
            sig = signature(self._lire(page) or {"url": page.url, "cibles": [], "champs": [], "tableaux": []})
            vers = self._par_signature.get(sig)
            notes.insert(0, f"mène à {vers.id}" if vers else "rien de nouveau")
            if vers and vers is not ecran:
                self.transitions.append({"de": ecran.id, "action": cle, "vers": vers.id})
        ecran.resultats[cle] = " ; ".join(notes)
        return nouveau

    def _fermer_nouvelles_pages(self) -> List[str]:
        """Les fenêtres ouvertes par un clic sont notées puis refermées."""
        modeles = []
        for autre in self._nouvelles_pages:
            if autre is self.nav.page:
                continue
            try:
                modeles.append(modele_url(autre.url))
                autre.close()
            except Exception:  # noqa: BLE001
                pass
        self._nouvelles_pages = []
        return modeles

    def _restaurer(self, page: Page, ecran: Ecran) -> bool:
        """Revient sur l'écran : il suffit parfois d'y être déjà, sinon on rejoue le chemin."""
        lecture = self._lire(page)
        if lecture is not None and signature(lecture) == ecran.signature and lecture["url"] == ecran.url:
            return True
        for pas in ecran.chemin:
            if not self._jouer(page, pas):
                return False
            page = self.nav.page_courante()
        lecture = self._lire(page)
        if lecture is not None and lecture["mot_de_passe"]:
            self._connexion(page)
            return self._restaurer(self.nav.page_courante(), ecran)
        return lecture is not None and signature(lecture) == ecran.signature

    def _jouer(self, page: Page, pas: Action) -> bool:
        try:
            if pas.type == "aller":
                page.goto(pas.url, wait_until="domcontentloaded")
            else:
                selecteur = self._retrouver(page, pas)
                if not selecteur:
                    return False
                page.locator(selecteur).first.click(timeout=5000)
        except ArretExploration:
            raise
        except Exception as e:  # noqa: BLE001
            journal.debug("Action impossible (%s) : %s", pas.libelle(), str(e).splitlines()[0])
            return False
        self._attendre(self.nav.page_courante())
        return True

    def _retrouver(self, page: Page, pas: Action) -> str:
        """Le même élément qu'à l'aller, revérifié : même texte, et toujours sans risque."""
        lecture = self._lire(page)
        if lecture is None:
            return ""
        candidates = [c for c in lecture["cibles"] if c["selecteur"] == pas.selecteur
                      and (c["texte"] or c["aria"]) == pas.texte]
        if not candidates and pas.zone == "tableau":
            candidates = [c for c in lecture["cibles"] if c["tableau"] == pas.tableau
                          and c["ligne"] == pas.ligne and c["rang"] == pas.rang]
        if not candidates:
            candidates = [c for c in lecture["cibles"] if c["tag"] == pas.tag and c["zone"] == pas.zone
                          and pas.texte and normaliser(c["texte"] or c["aria"]) == normaliser(pas.texte)]
        if len(candidates) != 1 and not (candidates and candidates[0]["selecteur"] == pas.selecteur):
            return ""
        cible = candidates[0]
        if self._decision(cible)[0] != "clic":
            return ""  # l'élément a changé de sens entre-temps : on ne clique pas
        return cible["selecteur"]

    # ------------------------------------------------------------------ résultats
    def resume(self) -> Dict[str, Any]:
        return {
            "ecrans": len(self.ecrans),
            "essais": self.essais,
            "bloquees": len(self.bloquees),
            "telechargements": len(set(self.telechargements)),
            "arret": self.arret,
            "duree_s": round(time.monotonic() - self._debut) if self._debut else 0,
        }

    def enregistrer(self) -> None:
        self.dossier.mkdir(parents=True, exist_ok=True)
        donnees = {
            "genere": dt.datetime.now().isoformat(timespec="seconds"),
            "resume": self.resume(),
            "ecrans": [asdict(e) for e in self.ecrans],
            "transitions": self.transitions,
            "envois_bloques": sorted({f"{m} {u}" for m, u in self.bloquees}),
            "telechargements": sorted(set(self.telechargements)),
            "sites_externes": sorted(set(self.externes)),
        }
        (self.dossier / "carte.json").write_text(json.dumps(donnees, ensure_ascii=False, indent=1), encoding="utf-8")
        (self.dossier / "carte.html").write_text(self._html(), encoding="utf-8")
        (self.dossier / "carte_a_partager.txt").write_text(self._texte_partage(), encoding="utf-8")

    def _acces(self, ecran: Ecran) -> str:
        return " › ".join(p.libelle() for p in ecran.chemin)

    def _texte_partage(self) -> str:
        r = self.resume()
        lignes = [
            "CARTE DU PORTAIL - VERSION A PARTAGER",
            "=" * 60,
            "Ce fichier ne contient que la STRUCTURE du portail : noms des champs, des boutons,",
            "des colonnes et des menus. Pas de valeurs, pas de contenu de tableau, pas de titre",
            "de page, pas d'adresse de serveur. Les mots contenant un chiffre sont remplacés par #.",
            "RELISEZ-LE avant de l'envoyer : si un mot vous semble sensible, remplacez-le.",
            "",
            f"{r['ecrans']} écran(s) vus, {r['essais']} élément(s) essayés, "
            f"{r['bloquees']} envoi(s) de données bloqué(s). Fin : {r['arret']}.",
            "",
        ]
        for e in self.ecrans:
            lignes.append(f"{e.id}   adresse : {masquer(e.modele)}")
            acces = " › ".join(
                (f"ouvrir {masquer(modele_url(p.url))}" if p.type == "aller"
                 else p.libelle() if p.zone == "tableau" else masquer(p.libelle()))
                for p in e.chemin)
            lignes.append(f"     accès : {acces}")
            menus = sorted({c["texte"] for c in e.cibles if c["zone"] in ("menu", "onglet") and c["texte"]})
            if menus:
                lignes.append(f"     menus / onglets : {masquer(', '.join(menus))}")
            champs = [f"{masquer(c['libelle'] or c['nom'] or '?')} [{type_champ(c['type'])}"
                      + (f", {c['nb_options']} choix" if c["type"] == "liste" else "")
                      + (", obligatoire" if c["obligatoire"] else "")
                      + (", lecture seule" if c["lecture_seule"] else "") + "]"
                      for c in e.champs if not c["dans_tableau"]]
            if champs:
                lignes.append(f"     champs : {' ; '.join(champs)}")
            boutons = []
            for c in e.cibles:
                if c["zone"] == "tableau" or c["tag"] == "a":
                    continue
                nom = c["texte"] or c["aria"] or "(icône)"
                resultat = e.resultats.get(self._cle(c), "")
                boutons.append(f"{nom}" + (f" ({resultat})" if resultat else ""))
            if boutons:
                lignes.append(f"     boutons : {masquer(' ; '.join(boutons))}")
            for t in e.tableaux:
                lignes.append(f"     tableau : [{masquer(' | '.join(t['entetes']))}] ({t['lignes']} lignes)")
            lignes_tableau = sorted((k, v) for k, v in e.resultats.items() if k.startswith("ligne "))
            for k, v in lignes_tableau[:2]:
                lignes.append(f"     {k} : {masquer(v)}")
            if e.cadres:
                lignes.append(f"     cadres (iframes) : {len(e.cadres)}, non explorés")
            lignes.append("")
        if self.bloquees:
            lignes.append("ENVOIS DE DONNEES BLOQUES (ce que certains boutons auraient modifié) :")
            for envoi in sorted({f"{m} {masquer(u)}" for m, u in self.bloquees}):
                lignes.append(f"   {envoi}")
        return "\n".join(lignes) + "\n"

    def _html(self) -> str:
        r = self.resume()
        h = html.escape
        morceaux = [
            "<!doctype html><html lang=fr><meta charset=utf-8><title>Carte du portail</title>",
            "<style>body{font:14px/1.45 system-ui,Arial;margin:24px;max-width:1100px;color:#1f2937}"
            "h1{font-size:22px}h2{font-size:17px;margin:28px 0 6px;border-top:1px solid #ddd;padding-top:14px}"
            "table{border-collapse:collapse;margin:6px 0}td,th{border:1px solid #ddd;padding:3px 8px;text-align:left;"
            "vertical-align:top}th{background:#f3f4f6}.gris{color:#6b7280}.rouge{color:#b91c1c}"
            ".vert{color:#15803d}code{background:#f3f4f6;padding:1px 4px}</style>",
            "<h1>Carte du portail</h1>",
            f"<p>{r['ecrans']} écran(s) vus · {r['essais']} élément(s) essayés · "
            f"<span class=rouge>{r['bloquees']} envoi(s) de données bloqué(s)</span> · {r['duree_s']} s<br>"
            f"<span class=gris>Fin : {h(r['arret'])}. Ce fichier reste sur votre poste : il peut contenir des données.</span></p>",
        ]
        for e in self.ecrans:
            morceaux.append(f"<h2 id={e.id}>{e.id} — {h((e.titres[0] if e.titres else e.titre) or '(sans titre)')}</h2>")
            morceaux.append(f"<p class=gris>Adresse : <code>{h(e.modele)}</code><br>Accès : {h(self._acces(e))}</p>")
            if e.champs:
                morceaux.append("<table><tr><th>Champ</th><th>Type</th><th>Détails</th></tr>")
                for c in e.champs:
                    details = []
                    if c["obligatoire"]:
                        details.append("obligatoire")
                    if c["lecture_seule"]:
                        details.append("lecture seule")
                    if c["type"] == "liste":
                        details.append(f"{c['nb_options']} choix : " + ", ".join(c["options"][:15]))
                    morceaux.append(f"<tr><td>{h(c['libelle'] or c['nom'] or '?')}</td><td>{h(type_champ(c['type']))}</td>"
                                    f"<td>{h(' ; '.join(details))}</td></tr>")
                morceaux.append("</table>")
            for t in e.tableaux:
                morceaux.append(f"<p>Tableau ({t['lignes']} lignes) : <b>{h(' | '.join(t['entetes']))}</b></p>")
            morceaux.append("<table><tr><th>Élément</th><th>Où</th><th>Résultat</th></tr>")
            for c in e.cibles:
                cle = self._cle(c)
                if c["zone"] == "tableau" and c["ligne"] >= self.limites.exemples:
                    continue
                res = e.resultats.get(cle, "")
                classe = "rouge" if ("bloqué" in res or res.startswith("non")) else ("vert" if res.startswith("mène") else "gris")
                liens = re.sub(r"\b(E\d+)\b", r"<a href=#\1>\1</a>", h(res))
                morceaux.append(f"<tr><td>{h(c['texte'] or c['aria'] or '(icône)')}</td><td>{h(c['zone'])}</td>"
                                f"<td class={classe}>{liens}</td></tr>")
            morceaux.append("</table>")
        if self.bloquees:
            morceaux.append("<h2>Envois de données bloqués</h2><ul>")
            for envoi in sorted({f"{m} {u}" for m, u in self.bloquees}):
                morceaux.append(f"<li><code>{h(envoi)}</code></li>")
            morceaux.append("</ul>")
        return "".join(morceaux) + "</html>\n"
