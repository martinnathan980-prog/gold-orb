"""Visite guidée : c'est l'utilisateur qui se promène dans son portail ; le robot regarde et note.

Le robot ne clique sur rien et ne tape rien : l'utilisateur travaille comme d'habitude,
guidé étape par étape par le bandeau vert (recherche de plans, fiche d'un plan et ses
onglets, PDF, composants...). Toutes les secondes environ, le robot relit l'écran affiché
(la même lecture que l'exploration automatique : noms des champs, boutons, onglets,
colonnes des tableaux, jamais les valeurs) et note chaque écran d'un genre nouveau, avec
le clic qui y a mené et l'étape en cours.

Il note aussi la NATURE des échanges du portail (formulaire ASP.NET, JSF, GraphQL, API
JSON...), sans leurs valeurs : c'est ce qui dira comment automatiser.

Filet de sécurité : pendant la visite, les boutons qui ressemblent à une modification
(Supprimer, Enregistrer, Dupliquer, Créer, Modifier...) sont bloqués dans la page.

Résultat : la même carte que l'exploration automatique (carte_PRIVEE_ne_pas_envoyer.html,
qui reste sur le poste, et carte_a_partager.txt), sans aucun risque pour le portail.
"""

from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from urllib.parse import parse_qsl

from playwright.sync_api import Page

from . import symboles as S
from .explorateur import (
    JS_ECRAN, JS_OUTILS, METHODES_LECTURE, Action, Ecran, Explorateur, Limites, _fin_adresse, classer_requete,
    decouper, masquer, nom_technique, normaliser, signature,
)
from .navigateur import Navigateur, est_onglet_parasite, site_de

journal = logging.getLogger("autoweb")


class FinVisite(Exception):
    """L'utilisateur a terminé la visite (bandeau, Entrée, fenêtre fermée)."""


# Ce que l'utilisateur montre, une étape à la fois. Le libellé court est noté sur chaque
# écran vu pendant l'étape : c'est ce qui dira « E12 = la fiche d'un plan ».
ETAPES = [
    ("Accueil et menus", "la page d'accueil, puis chaque menu principal du portail, un par un"),
    ("Recherche de plans", "la recherche de plans : faites une recherche, comme d'habitude"),
    ("Fiche plan", "la fiche d'un plan, puis CHACUN de ses onglets, un par un"),
    ("PDF de plan", "un PDF de ce plan : ouvrez-le simplement"),
    ("Deuxième plan", "la fiche d'un AUTRE plan, et un ou deux de ses onglets"),
    ("Composants", "la recherche de composants, puis la fiche d'un composant et ses onglets"),
    ("Autres écrans", "tout autre écran utile à votre travail (pour consulter seulement)"),
]

# Posé dans chaque page et chaque cadre : compteur de changements (le robot relit l'écran
# quand il a changé puis s'est calmé), écoute des clics de l'utilisateur (quel clic mène à
# quel écran), filet de sécurité sur les boutons de modification, bandeau vert.
# Rejouable sans doublon : après un document.open(), les écoutes disparaissent et sont reposées.
JS_VISITE = r"""
() => {
  if (!document.__autoweb_visite) {
    document.__autoweb_visite = true;
    document.__autoweb_changements = 0;
    const ignorer = n => {
      const e = n && (n.nodeType === 1 ? n : n.parentElement);
      return !e || !e.closest || !!e.closest('[data-autoweb], title');
    };
    try {
      // le document lui-même : au moment où ce script arrive, la page n'a parfois pas encore de <html>
      new MutationObserver(liste => {
        for (const m of liste) if (!ignorer(m.target)) { document.__autoweb_changements++; }
      }).observe(document, { childList: true, subtree: true, attributes: true, characterData: true });
    } catch (err) {}
  }
  const racine = document.documentElement;
  if (racine && racine.__autoweb_arme) return false;
  if (racine) racine.__autoweb_arme = true;
""" + JS_OUTILS + r"""
  const duRobot = n => {
    const e = n && (n.nodeType === 1 ? n : n.parentElement);
    return !!(e && e.closest && e.closest('[data-autoweb]'));
  };
  const envoyer = d => { try { if (window.autowebVisite) window.autowebVisite(JSON.stringify(d)); } catch (err) {} };
  const cible = ev => {
    let t = (ev.composedPath && ev.composedPath()[0]) || ev.target;
    if (t && t.nodeType !== 1) t = t.parentElement;
    return (t && t.closest && !duRobot(t)) ? t : null;
  };
  const surClic = ev => {
    const t = cible(ev);
    if (!t) return;
    cache.clear(); indexes.clear(); racinesCache = null;  // la page a pu être redessinée depuis
    let e = t.closest(SELECTION) || t.closest('tbody tr, [role=row]');
    if (!e) {  // élément « maison » cliquable : main au survol, ou atteignable au clavier
      for (let x = t, i = 0; x && x !== document.body && i < 6; x = x.parentElement, i++) {
        if (x.hasAttribute('tabindex') || getComputedStyle(x).cursor === 'pointer') { e = x; break; }
      }
    }
    if (!e || e.matches(EXCLUS)) return;
    let d;
    try { d = decrire(e); } catch (err) { return; }
    envoyer({ type: 'clic', cible: d });
  };
  // Filet de sécurité : pendant la visite, les boutons de modification ne partent pas.
  const DANGER = /(supprim|delete|remove|effac|enregistr|sauvegard|\bsave|dupliqu|copier|clon|\bcreer|\bcreate|nouve(au|lle)|\bnew\b|ajout|\badd\b|modifi|\bedit|publi|approuv|verrou|\block|check.?(in|out)|envoy|\bsend|submit|soumettre|import|upload|renomm|rename|deplac|\bmove\b|archiv|diffus|signer|transfer|restaur|purge|vider)/;
  const PERMIS = /(annul|fermer|close|cancel|telecharg|download|export|imprim|print|retour|back|recherch|search|voir|afficher|filtr|consult)/;
  const texteDe = e => ((e.innerText || e.value || '') + ' ' + (e.getAttribute('aria-label') || '') + ' ' +
                        (e.getAttribute('title') || '') + ' ' + (e.id || '') + ' ' + (e.getAttribute('name') || ''))
                        .slice(0, 200).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const avertir = message => {
    try {
      const a = document.createElement('div');
      a.setAttribute('data-autoweb', '1');
      a.setAttribute('style', 'position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2147483647;' +
        'background:#b45309;color:#fff;font:600 13px/1.4 system-ui,Arial;padding:10px 14px;border-radius:8px;' +
        'box-shadow:0 2px 12px rgba(0,0,0,.4);max-width:520px;pointer-events:none');
      a.textContent = message;
      (document.body || document.documentElement).appendChild(a);
      setTimeout(() => a.remove(), 5000);
    } catch (err) {}
  };
  const garde = ev => {
    const t = cible(ev);
    if (!t) return;
    const e = t.closest(SELECTION);
    if (!e) return;
    // menus, onglets, arborescence : de la navigation (« Mes modifications » est un menu, pas une action)
    if (['menu', 'onglet', 'lateral', 'arbre'].includes(zone(e))) return;
    const href = e.tagName === 'A' ? (e.getAttribute('href') || '').toLowerCase() : '';
    const lien = href && !/^(#|javascript:)/.test(href);
    if (lien && !DANGER.test(href)) return;  // simple lien : bloqué seulement si son adresse est une action
    const texte = texteDe(e) + ' ' + href;
    if (!DANGER.test(texte) || PERMIS.test(texteDe(e))) return;
    ev.preventDefault(); ev.stopImmediatePropagation();
    if (ev.type === 'click') {
      avertir("Pendant la visite, le robot bloque ce bouton : rien n'est parti. " +
              "Pour le faire vraiment, utilisez votre Chrome habituel.");
      envoyer({ type: 'bloque' });
    }
  };
  const ecoutes = window.__autoweb_ecoutes || [];
  for (const [type, f] of ecoutes) { window.removeEventListener(type, f, true); document.removeEventListener(type, f, true); }
  window.__autoweb_ecoutes = [];
  for (const type of ['pointerdown', 'mousedown', 'mouseup', 'click', 'dblclick']) {
    window.addEventListener(type, garde, true);
    window.__autoweb_ecoutes.push([type, garde]);
  }
  for (const type of ['click', 'auxclick']) {
    document.addEventListener(type, surClic, true);
    window.__autoweb_ecoutes.push([type, surClic]);
  }
  if (window === window.top) {
    const poser = () => {
      if (!document.body || document.getElementById('__autoweb_visite')) return;
      const b = document.createElement('div');
      b.id = '__autoweb_visite';
      b.setAttribute('data-autoweb', '1');
      b.setAttribute('style', 'position:fixed;bottom:10px;left:10px;z-index:2147483647;background:#047857;' +
        'color:#fff;font:600 12px/1.35 system-ui,-apple-system,Arial;padding:7px 10px;border-radius:7px;' +
        'box-shadow:0 2px 10px rgba(0,0,0,.35);user-select:none;max-width:430px;opacity:.95');
      const texte = document.createElement('div');
      texte.className = '__autoweb_texte';
      texte.textContent = 'Le robot regarde et note (il ne clique sur rien).';
      const boutons = document.createElement('div');
      boutons.setAttribute('style', 'margin-top:5px;display:flex;gap:6px;flex-wrap:wrap');
      const bouton = (libelle, type) => {
        const x = document.createElement('span');
        x.textContent = libelle;
        x.className = '__autoweb_' + type;
        x.setAttribute('style', 'background:#fff;color:#065f46;border-radius:4px;padding:2px 8px;cursor:pointer');
        x.addEventListener('click', ev => {
          ev.stopPropagation(); ev.preventDefault();
          if (type === 'fin' && !x.dataset.sur) {  // une seule fausse manœuvre ne termine rien
            x.dataset.sur = '1'; x.textContent = 'Sûr ? Cliquez encore pour terminer';
            setTimeout(() => { delete x.dataset.sur; x.textContent = libelle; }, 5000);
            return;
          }
          if (type === 'fin') { b.dataset.fini = '1'; texte.textContent = 'Visite terminée : revenez à la fenêtre noire.'; boutons.remove(); }
          envoyer({ type: type });
        }, true);
        return x;
      };
      boutons.appendChild(bouton('Étape suivante ▸', 'etape'));
      boutons.appendChild(bouton('Terminer la visite', 'fin'));
      boutons.appendChild(bouton('⇆', 'cote'));
      b.appendChild(texte); b.appendChild(boutons);
      document.documentElement.appendChild(b);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', poser); else poser();
    setTimeout(poser, 500);
  }
  return true;
}
"""

# Lu à chaque tour : adresse, nombre de changements, état de chargement, type de document,
# taille du cadre, indicateur de chargement visible. Met aussi à jour le bandeau et le titre
# de la fenêtre (« ROBOT - ») pour ne pas la confondre avec le Chrome habituel.
# None si la page n'est pas (ou plus) équipée.
JS_ETAT = r"""
([n, texteEtape, derniere, cote]) => {
  if (!document.__autoweb_visite || !document.documentElement || !document.documentElement.__autoweb_arme) return null;
  if (window === window.top) {
    const b = document.getElementById('__autoweb_visite');
    if (b && !b.dataset.fini) {
      const cle = n + '|' + texteEtape + '|' + cote;
      if (b.dataset.cle !== cle) {
        b.dataset.cle = cle;
        const t = b.querySelector('.__autoweb_texte');
        if (t) t.textContent = texteEtape + '   (' + n + ' écran(s) noté(s) ; le robot ne clique sur rien)';
        const s = b.querySelector('.__autoweb_etape');
        if (s) s.style.display = derniere ? 'none' : '';
        b.style.left = cote ? 'auto' : '10px'; b.style.right = cote ? '10px' : 'auto';
      }
    }
    if (document.title && !document.title.startsWith('ROBOT - ')) document.title = 'ROBOT - ' + document.title;
  }
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  let charge = false;
  try {
    for (const e of document.querySelectorAll('[aria-busy=true], [role=progressbar], .blockUI, .blockOverlay, .x-mask, ' +
                                              '.k-loading-mask, .sapUiLocalBusyIndicator')) if (vis(e)) { charge = true; break; }
  } catch (err) {}
  return [location.href, document.__autoweb_changements || 0, document.readyState, document.contentType || '',
          innerWidth * innerHeight, charge];
}
"""

CONSIGNES = """
{ligne} VISITE GUIDÉE : c'est VOUS qui conduisez, le robot regarde et note
   Le robot ne clique sur rien, ne tape rien, ne modifie rien. Il note seulement
   comment chaque écran est construit (noms des champs, boutons, onglets, colonnes),
   jamais ce qui est écrit dedans. La fenêtre du robot a un titre qui commence par
   « ROBOT - » et un bandeau vert en bas : c'est dans CELLE-LÀ qu'il faut cliquer.

   Le bandeau vert vous guide, une étape à la fois. Restez 2 ou 3 secondes sur chaque
   écran. Une étape qui n'existe pas chez vous : « Étape suivante ».
   Ne validez rien : par sécurité, le robot bloque pendant la visite les boutons
   Supprimer, Enregistrer, Dupliquer, Créer, Modifier...

   Quand vous avez fini : « Terminer la visite » dans le bandeau, ou Entrée ici.
"""


class Visite(Explorateur):
    """Même carte que l'exploration automatique ; mais c'est l'utilisateur qui clique."""

    def __init__(
        self,
        nav: Navigateur,
        dossier: Path,
        limites: Optional[Limites] = None,
        interactif: bool = True,
        connexion: Optional[Callable[[Page], None]] = None,
        releve_s: float = 1.2,
        dossier_telechargements: Optional[Path] = None,
    ) -> None:
        super().__init__(nav, dossier, limites or Limites(ecrans=1000, minutes=240.0, delai_ms=0),
                         interactif, connexion)
        self.mode = "visite"
        self.releve_s = releve_s
        self.site = ""
        self.documents = 0
        self.boutons_bloques = 0
        self.etape = 0
        self.cote = False
        self.ignores: Dict[str, int] = {}  # pages et cadres laissés de côté, et pourquoi
        self.dossier_telechargements = dossier_telechargements or (Path.home() / "Downloads")
        self._fin = False
        self._changer_etape = 0
        self._prochain = 0.0
        self._clics: Dict[Any, Dict[str, Any]] = {}  # dernier clic de l'utilisateur, par onglet
        self._etats: Dict[Any, tuple] = {}  # cadre -> état vu au tour précédent
        self._lus: Dict[Any, tuple] = {}  # cadre -> état au moment de la dernière lecture
        self._instable: Dict[Any, int] = {}
        self._ecran_du_cadre: Dict[Any, Ecran] = {}
        self._ecran_de_page: Dict[Any, Ecran] = {}
        self._ouvreurs: Dict[Any, Any] = {}  # onglet -> onglet qui l'a ouvert
        self._onglets_cliques: set = set()
        self._telechargements_en_cours: List[Any] = []
        self._connexion_signalee = False
        self._bloques_signales = 0
        self._autres: set = set()  # adresses d'autres sites déjà comptées

    # ------------------------------------------------------------------ événements (fil Playwright)
    def _recevoir(self, source: Dict[str, Any], charge: str) -> None:
        """Appelé par Playwright depuis sa propre boucle : AUCUN appel Playwright ici
        (frame.url et page ne sont que des valeurs déjà connues)."""
        try:
            donnees = json.loads(charge)
        except (TypeError, ValueError):
            return
        if not isinstance(donnees, dict):
            return
        genre = donnees.get("type")
        if genre == "fin":
            self._fin = True
            return
        if genre == "etape":
            self._changer_etape += 1
            return
        if genre == "cote":
            self.cote = not self.cote
            return
        if genre == "bloque":
            self.boutons_bloques += 1
            return
        cible = donnees.get("cible")
        page = source.get("page") if source else None
        cadre = source.get("frame") if source else None
        if genre != "clic" or not isinstance(cible, dict) or page is None:
            return
        try:
            url_cadre = cadre.url if cadre is not None else ""
        except Exception:  # noqa: BLE001
            url_cadre = ""
        if self.site and url_cadre and site_de(url_cadre) != self.site:
            return  # clic dans un service d'un autre site (publicité, aide en ligne...) : sans rapport
        cible["_quand"] = time.monotonic()
        self._clics[page] = cible
        if cible.get("zone") == "onglet" or cible.get("role") == "tab":
            self._onglets_cliques.add(normaliser(cible.get("texte") or cible.get("aria") or ""))

    def _requete(self, requete: Any) -> None:
        """Nature des échanges du portail (jamais les valeurs). Rien n'est bloqué."""
        try:
            if not self.site or site_de(requete.url) != self.site:
                return  # connexion, mesure d'audience, service d'un autre site : sans rapport avec le portail
            self._techno_adresse(requete.url)
            methode = requete.method.upper()
            if methode in METHODES_LECTURE:
                if methode == "GET" and requete.resource_type in ("xhr", "fetch"):
                    self._noter_envoi(appel_de_lecture(requete.url))
                return
            self._noter_envoi(classer_requete(requete))
        except Exception as e:  # noqa: BLE001 - un gestionnaire ne doit jamais lever
            journal.debug("Échange non classé : %s", e)

    def _suivre(self, page: Page) -> None:
        try:
            ouvreur = page.opener()
        except Exception:  # noqa: BLE001
            ouvreur = None
        if ouvreur is not None:
            self._ouvreurs[page] = ouvreur
        page.on("download", self._telechargement_vu)
        # un onglet ouvert par window.open ne reçoit pas toujours le script : on le repose
        page.on("domcontentloaded", self._equiper)

    def _equiper(self, page: Any) -> None:
        try:
            page.evaluate(f"({JS_VISITE})()")
        except Exception:  # noqa: BLE001 - page fermée ou en cours de navigation
            pass

    def _telechargement_vu(self, telechargement: Any) -> None:
        """Fichier téléchargé (un PDF de plan...) : il arrive dans Téléchargements, comme
        d'habitude. Enregistré au prochain tour, hors de ce gestionnaire."""
        self._telechargements_en_cours.append(telechargement)

    def _ranger_telechargements(self) -> None:
        while self._telechargements_en_cours:
            telechargement = self._telechargements_en_cours.pop(0)
            try:
                nom = telechargement.suggested_filename or "fichier"
                page = telechargement.page
            except Exception:  # noqa: BLE001
                nom, page = "fichier", None
            self.telechargements.append(nom)
            origine, clic = self._origine(page) if page is not None else (None, None)
            extension = nom.rsplit(".", 1)[-1].lower()[:5] if "." in nom else "?"
            if origine is not None and clic:
                origine.resultats.setdefault(self._cle(clic), f"télécharge un fichier .{masquer(extension)}")
            propre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nom).strip(" .") or "fichier"
            dossier = self.dossier_telechargements if self.dossier_telechargements.is_dir() else self.nav._dossier_telechargements()
            cible = dossier / propre
            i = 2
            while cible.exists():
                cible = dossier / f"{Path(propre).stem} ({i}){Path(propre).suffix}"
                i += 1
            try:
                telechargement.save_as(str(cible))
                print(f"   {S.OK} Fichier téléchargé, comme d'habitude : {cible}", flush=True)
            except Exception as e:  # noqa: BLE001
                journal.debug("Téléchargement non enregistré : %s", e)

    # ------------------------------------------------------------------ déroulement
    def visiter(self, url: str, promenade: Optional[Callable[["Visite"], None]] = None) -> None:
        """Ouvre le portail, fait confirmer la page d'accueil, puis note ce que l'utilisateur
        affiche jusqu'à ce qu'il ait fini. `promenade` : tests, gestes joués à sa place."""
        contexte = self.nav.contexte
        page = self.nav.page_courante()
        self.url_demandee = url
        self._debut = time.monotonic()
        contexte.expose_binding("autowebVisite", self._recevoir)
        contexte.add_init_script(f"({JS_VISITE})()")
        contexte.on("request", self._requete)
        contexte.on("response", self._reponse)
        for ouverte in contexte.pages:
            self._suivre(ouverte)
        contexte.on("page", self._suivre)
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001 - lent, ou connexion d'entreprise : l'utilisateur prend la main
            print(f"{S.ATTENTION} La page met du temps à s'ouvrir ({str(e).splitlines()[0][:80]}).")
            print("   Si elle ne s'affiche pas, tapez l'adresse du portail dans la fenêtre du robot.")
        self._attendre(page)
        self._connexion(page, premiere_fois=True)
        page = self.nav.page_courante()
        self.site = site_de(page.url)
        m = decouper(page.url)
        self.hote = m.netloc if m else ""
        self.depart = page.url
        self._clics.clear()  # les clics de la connexion ne mènent à aucun écran du portail
        self._fin = False
        self._changer_etape = 0
        try:
            if promenade is not None:
                self.laisser_tourner(2 * self.releve_s + 0.5)
                promenade(self)
                self.laisser_tourner(2 * self.releve_s + 0.5)
            elif self.interactif:
                from .console import lire_ligne

                print(CONSIGNES.format(ligne=S.LIGNE))
                self._annoncer_etape()
                with self.nav.pause_manuelle():  # ses boîtes de dialogue sont à lui
                    lire_ligne(self._pomper)
            self.arret = "visite terminée"
        except FinVisite as e:
            self.arret = str(e)
        except KeyboardInterrupt:
            self.arret = "visite arrêtée (Ctrl+C)"
        finally:
            self.complet = True
            try:
                if self.nav.pages_de_travail():
                    self._relever(dernier=True)  # le dernier écran affiché, s'il n'a pas encore été lu
                    self._ranger_telechargements()
                self._techno_cookies()
            except Exception as e:  # noqa: BLE001
                journal.debug("Dernière lecture impossible : %s", e)
            self.enregistrer()
            self._expliquer_si_vide()

    def laisser_tourner(self, duree_s: float) -> None:
        """Fait tourner la visite un moment, sans attendre l'utilisateur."""
        fin = time.monotonic() + duree_s
        while time.monotonic() < fin:
            self._pomper()

    def _pomper(self) -> None:
        self.nav.pomper(250)
        if self._fin:
            raise FinVisite("visite terminée")
        if not [p for p in self.nav.contexte.pages if not p.is_closed()]:
            raise FinVisite("visite terminée (fenêtre du robot fermée)")
        if time.monotonic() - self._debut > self.limites.minutes * 60:
            raise FinVisite(f"durée maximum de {self.limites.minutes:g} minutes atteinte")
        if len(self.ecrans) >= self.limites.ecrans:
            raise FinVisite(f"limite de {self.limites.ecrans} écrans atteinte")
        while self._changer_etape:
            self._changer_etape -= 1
            if self.etape < len(ETAPES) - 1:
                self.etape += 1
                self._annoncer_etape()
        if self.boutons_bloques > self._bloques_signales:
            self._bloques_signales = self.boutons_bloques
            print(f"   {S.ATTENTION} Un bouton de modification a été bloqué par le robot : rien n'est parti.", flush=True)
        self._ranger_telechargements()
        if time.monotonic() >= self._prochain:
            self._prochain = time.monotonic() + self.releve_s
            self._relever()

    def _texte_etape(self) -> str:
        return f"Étape {self.etape + 1}/{len(ETAPES)} : affichez {ETAPES[self.etape][1]}."

    def _annoncer_etape(self) -> None:
        print()
        print(f"   {S.FLECHE} {self._texte_etape()}", flush=True)
        if self.etape < len(ETAPES) - 1:
            print("      (puis « Étape suivante » dans le bandeau vert)", flush=True)
        else:
            print("      (puis « Terminer la visite » dans le bandeau vert, ou Entrée ici)", flush=True)

    def _expliquer_si_vide(self) -> None:
        if len(self.ecrans) > 1 or not self.interactif:
            return
        print()
        print(f"{S.ATTENTION} Le robot n'a noté que {len(self.ecrans)} écran(s).")
        print("   Avez-vous bien cliqué dans la fenêtre du ROBOT (titre « ROBOT - ... », bandeau vert en bas),")
        print("   et pas dans votre Chrome habituel ? Restez aussi 2 ou 3 secondes sur chaque écran.")
        if self.ignores:
            raisons = " ; ".join(f"{n} × {r}" for r, n in sorted(self.ignores.items(), key=lambda x: -x[1]))
            print(f"   Pages laissées de côté : {raisons}.")

    def _ignorer(self, raison: str) -> None:
        self.ignores[raison] = self.ignores.get(raison, 0) + 1

    # ------------------------------------------------------------------ lecture des écrans
    def _relever(self, dernier: bool = False) -> None:
        for page in self.nav.pages_de_travail():
            try:
                cadres = list(page.frames)
            except Exception:  # noqa: BLE001
                continue
            for cadre in cadres:
                try:
                    self._relever_cadre(page, cadre, dernier)
                except (FinVisite, KeyboardInterrupt):
                    raise
                except Exception as e:  # noqa: BLE001 - cadre détaché, navigation en cours
                    journal.debug("Lecture d'un cadre impossible : %s", e)

    def _relever_cadre(self, page: Page, cadre: Any, dernier: bool) -> None:
        url = cadre.url or ""
        if not url.startswith(("http:", "https:", "file:")) or est_onglet_parasite(url):
            return
        if site_de(url) != self.site:
            if url not in self._autres:
                self._autres.add(url)
                self._ignorer("page d'un autre site (connexion, Google, service externe)")
            return
        derniere = self.etape >= len(ETAPES) - 1
        etat = cadre.evaluate(JS_ETAT, [len(self.ecrans), self._texte_etape(), derniere, self.cote])
        if etat is None:
            self._equiper(cadre)
            etat = cadre.evaluate(JS_ETAT, [len(self.ecrans), self._texte_etape(), derniere, self.cote])
            if etat is None:
                return
        etat = tuple(etat)
        adresse, changements, pret, type_document, surface, charge = etat
        if cadre is not page.main_frame and surface < 2500:
            return  # cadre caché ou minuscule (maintien de session, compteur) : pas un écran
        cle = (adresse, changements, pret, type_document)
        precedent = self._etats.get(cadre)
        self._etats[cadre] = cle
        if self._lus.get(cadre) == cle or pret == "loading":
            return  # rien de nouveau depuis la dernière lecture, ou page en cours de chargement
        if (precedent != cle or charge) and not dernier:
            # l'écran bouge encore, ou affiche « chargement » : on attend qu'il se calme
            # (une page qui bouge sans cesse, une horloge par exemple, est lue quand même)
            self._instable[cadre] = self._instable.get(cadre, 0) + 1
            if self._instable[cadre] < (8 if charge else 3):
                return
        self._instable[cadre] = 0
        self._lus[cadre] = cle
        if "pdf" in str(type_document).lower():
            self._document(page)
            return
        lecture = cadre.evaluate(JS_ECRAN, [self.limites.exemples, self.limites.max_cibles])
        self._noter(page, cadre, lecture)

    def _document(self, page: Page) -> None:
        origine, clic = self._origine(page)
        self.documents += 1
        if origine is not None and clic:
            origine.resultats.setdefault(self._cle(clic), "ouvre un document PDF")
        print(f"   {S.OK} Document PDF affiché : noté (le robot ne lit pas son contenu).", flush=True)

    def _origine(self, page: Any):
        """(écran d'où l'on vient, clic qui y a mené) pour un changement vu dans cet onglet."""
        origine = self._ecran_de_page.get(page)
        clic = self._clics.pop(page, None)
        if origine is None and page in self._ouvreurs:  # nouvel onglet : il vient de son ouvreur
            ouvreur = self._ouvreurs[page]
            origine = self._ecran_de_page.get(ouvreur)
            clic = clic or self._clics.pop(ouvreur, None)
        if clic and time.monotonic() - clic.get("_quand", 0) > 60:
            clic = None  # clic trop ancien : ce n'est pas lui qui a mené ici
        return origine, clic

    def _noter(self, page: Page, cadre: Any, lecture: Optional[Dict[str, Any]]) -> None:
        if not lecture:
            return
        principal = cadre is page.main_frame
        menus = sum(1 for c in lecture["cibles"] if c["zone"] in ("menu", "lateral", "arbre"))
        if lecture["mot_de_passe"] and menus < 3:
            if not self._connexion_signalee:
                self._connexion_signalee = True
                print("   Écran de connexion : pas noté (il ne fait pas partie de la carte).", flush=True)
            return
        origine, clic = self._origine(page)
        if not principal:
            origine = self._ecran_du_cadre.get(cadre) or origine
        connu = self._par_signature.get(signature(lecture))
        if connu is not None:
            if origine is not None and clic and connu is not origine:
                origine.resultats.setdefault(self._cle(clic), f"mène à {connu.id}")
                self.transitions.append({"de": origine.id, "action": self._cle(clic), "vers": connu.id})
            self._placer(page, cadre, principal, connu)
            return
        if clic:
            ligne = clic.get("ligne", -1)
            pas = Action("clic", selecteur=clic.get("selecteur", ""), texte=clic.get("texte") or clic.get("aria") or "",
                         zone=clic.get("zone", ""), ligne=ligne if isinstance(ligne, int) else -1,
                         partage=self._libelle_partage(clic))
        else:
            pas = Action("aller", url=lecture["url"],
                         partage="page de départ" if not self.ecrans else "adresse ouverte sans clic noté")
        chemin = ((origine.chemin if origine is not None else []) + [pas])[-8:]
        profondeur = (origine.profondeur + 1) if origine is not None else 0
        nouveau = self._observer(cadre, chemin, profondeur, lecture, annoncer=False)
        if nouveau is None:
            return
        nouveau.cadre = not principal
        nouveau.etape = ETAPES[self.etape][0]
        if origine is not None and clic:
            origine.resultats.setdefault(self._cle(clic), f"mène à {nouveau.id}")
            self.transitions.append({"de": origine.id, "action": self._cle(clic), "vers": nouveau.id})
        self._placer(page, cadre, principal, nouveau)
        self._annoncer(nouveau)
        self.enregistrer()

    def _placer(self, page: Page, cadre: Any, principal: bool, ecran: Ecran) -> None:
        self._ecran_du_cadre[cadre] = ecran
        if principal or page not in self._ecran_de_page:
            self._ecran_de_page[page] = ecran

    def _annoncer(self, ecran: Ecran) -> None:
        titre = (ecran.titres[0] if ecran.titres else ecran.titre) or "(sans titre)"
        details = []
        if ecran.champs:
            details.append(f"{len(ecran.champs)} champ(s)")
        if ecran.tableaux:
            details.append(f"{len(ecran.tableaux)} tableau(x)")
        print(f"   {S.OK} Écran {ecran.id} noté : « {titre[:60]} »"
              + (f"  ({', '.join(details)})" if details else "")
              + ("  [cadre]" if ecran.cadre else ""), flush=True)
        onglets = []
        for c in ecran.cibles:
            nom = (c["texte"] or c["aria"]).strip()
            if (c["zone"] == "onglet" or c["role"] == "tab") and nom and normaliser(nom) not in self._onglets_cliques \
                    and nom not in onglets:
                onglets.append(nom)
        if onglets:
            print(f"      Onglets à ouvrir aussi, un par un : {' ; '.join(o[:30] for o in onglets[:8])}", flush=True)

    # ------------------------------------------------------------------ carte
    def _bilan_partage(self, r: Dict[str, Any]) -> str:
        return (f"Visite guidée : {r['ecrans']} écran(s) notés pendant la visite (c'est l'utilisateur qui a "
                f"cliqué ; le robot n'a rien fait), {self.documents} document(s) PDF affiché(s), "
                f"{self.boutons_bloques} bouton(s) de modification bloqué(s) par sécurité.")

    def resume(self) -> Dict[str, Any]:
        r = super().resume()
        r["documents"] = self.documents
        r["boutons_bloques"] = self.boutons_bloques
        return r


def appel_de_lecture(url: str) -> str:
    """« GET …/search (appel de la page, paramètres : page, q) » : jamais les valeurs."""
    m = decouper(url)
    noms = sorted({nom_technique(k, 30) for k, _ in parse_qsl(m.query if m else "", keep_blank_values=True)} - {""})
    return ("GET " + _fin_adresse(url) + " (appel de la page"
            + (f", paramètres : {', '.join(noms[:8])}" if noms else "") + ") [lecture]")
