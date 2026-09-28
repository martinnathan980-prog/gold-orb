"""Visite guidée : c'est l'utilisateur qui se promène dans son portail ; le robot regarde et note.

Le robot ne clique sur rien, ne tape rien, ne bloque rien : l'utilisateur travaille comme
d'habitude. Toutes les secondes environ, le robot relit l'écran affiché (la même lecture
que l'exploration automatique : noms des champs, boutons, onglets, colonnes des tableaux,
jamais les valeurs) et note chaque écran d'un genre nouveau, avec le clic qui y a mené.

Il note aussi la NATURE des envois de données du portail (formulaire ASP.NET, JSF,
GraphQL, API JSON...), sans leurs valeurs : c'est ce qui dira comment automatiser.

Résultat : la même carte que l'exploration automatique (carte.html, qui reste sur le
poste, et carte_a_partager.txt), sans aucun risque pour le portail.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from playwright.sync_api import Page

from . import symboles as S
from .erreurs import ErreurAutoweb
from .explorateur import (
    JS_ECRAN, JS_OUTILS, METHODES_LECTURE, Action, Ecran, Explorateur, Limites, classer_requete, decouper,
    masquer, normaliser, signature,
)
from .navigateur import Navigateur, est_onglet_parasite, site_de

journal = logging.getLogger("autoweb")


class FinVisite(Exception):
    """L'utilisateur a terminé la visite (bandeau, Entrée, fenêtre fermée)."""


# Posé dans chaque page et chaque cadre : compteur de changements (le robot relit l'écran
# quand il a changé puis s'est calmé), écoute des clics de l'utilisateur (pour savoir quel
# clic mène à quel écran), et bandeau vert qui compte les écrans notés.
JS_VISITE = r"""
() => {
  if (document.__autoweb_visite) return false;
  document.__autoweb_visite = true;
""" + JS_OUTILS + r"""
  const duRobot = n => {
    const e = n && (n.nodeType === 1 ? n : n.parentElement);
    return !!(e && e.closest && e.closest('[data-autoweb]'));
  };
  document.__autoweb_changements = 0;
  try {
    new MutationObserver(liste => {
      for (const m of liste) if (!duRobot(m.target)) { document.__autoweb_changements++; }
    // le document lui-même : au moment où ce script arrive, la page n'a parfois pas encore de <html>
    }).observe(document, { childList: true, subtree: true, attributes: true, characterData: true });
  } catch (err) {}
  const envoyer = d => { try { if (window.autowebVisite) window.autowebVisite(JSON.stringify(d)); } catch (err) {} };
  const surClic = ev => {
    let t = ev.target;
    if (t && t.nodeType !== 1) t = t.parentElement;
    if (!t || !t.closest || duRobot(t)) return;
    const e = t.closest(SELECTION) || t.closest('tbody tr, [role=row]');
    if (!e || e.matches(EXCLUS)) return;
    let d;
    try { d = decrire(e); } catch (err) { return; }
    envoyer({ type: 'clic', cible: d });
  };
  document.addEventListener('click', surClic, true);
  document.addEventListener('auxclick', surClic, true);
  if (window === window.top) {
    const poser = () => {
      if (!document.documentElement || document.getElementById('__autoweb_visite')) return;
      const b = document.createElement('div');
      b.id = '__autoweb_visite';
      b.setAttribute('data-autoweb', '1');
      b.setAttribute('style', 'position:fixed;bottom:12px;left:12px;z-index:2147483647;background:#047857;' +
        'color:#fff;font:600 12px/1.3 system-ui,-apple-system,Arial;padding:8px 11px;border-radius:6px;' +
        'box-shadow:0 2px 10px rgba(0,0,0,.35);cursor:pointer;user-select:none;max-width:330px;opacity:.93');
      b.textContent = 'Le robot regarde et note (il ne clique sur rien) - cliquez ici quand vous avez fini';
      b.addEventListener('click', ev => {
        ev.stopPropagation(); ev.preventDefault();
        b.dataset.fini = '1';
        b.textContent = 'Visite terminée : revenez à la fenêtre noire';
        envoyer({ type: 'fin' });
      }, true);
      document.documentElement.appendChild(b);
    };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', poser); else poser();
    setTimeout(poser, 500);
  }
  return true;
}
"""

# Lu à chaque tour : adresse, nombre de changements, état de chargement, type de document.
# Met aussi à jour le compteur du bandeau. None si la page n'est pas encore équipée.
JS_ETAT = r"""
(n) => {
  if (!document.__autoweb_visite) return null;
  const b = document.getElementById('__autoweb_visite');
  if (b && !b.dataset.fini && b.dataset.n !== String(n)) {
    b.dataset.n = String(n);
    b.textContent = 'Le robot regarde et note (il ne clique sur rien) : ' + n + ' écran(s) noté(s)' +
                    ' - cliquez ici quand vous avez fini';
  }
  return [location.href, document.__autoweb_changements || 0, document.readyState, document.contentType || ''];
}
"""

CONSIGNES = """
{ligne} VISITE GUIDÉE : c'est VOUS qui conduisez, le robot regarde et note
   Le robot ne clique sur rien, ne tape rien, ne modifie rien. Il note seulement
   comment chaque écran est construit (noms des champs, boutons, onglets, colonnes),
   jamais ce qui est écrit dedans.

   Promenez-vous dans votre portail comme d'habitude, en restant 2 ou 3 secondes
   sur chaque écran. En bas à gauche, le bandeau vert compte les écrans notés.
   Pour une bonne carte, affichez par exemple :
     1. la recherche de plans, et faites une recherche ;
     2. la fiche d'un plan, puis CHACUN de ses onglets, un par un ;
     3. un PDF de ce plan (ouvrez-le simplement) ;
     4. la recherche de composants, puis la fiche d'un composant et ses onglets ;
     5. chaque menu principal du portail.
   Ne validez rien pendant la visite : pas d'Enregistrer, pas de Supprimer.

   Quand vous avez fini : cliquez sur le bandeau vert, ou revenez ici et appuyez sur Entrée.
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
    ) -> None:
        super().__init__(nav, dossier, limites or Limites(ecrans=1000, minutes=240.0, delai_ms=0),
                         interactif, connexion)
        self.mode = "visite"
        self.releve_s = releve_s
        self.site = ""
        self.documents = 0
        self._fin = False
        self._prochain = 0.0
        self._clics: Dict[Any, Dict[str, Any]] = {}  # dernier clic de l'utilisateur, par onglet
        self._etats: Dict[Any, tuple] = {}  # cadre -> état vu au tour précédent
        self._lus: Dict[Any, tuple] = {}  # cadre -> état au moment de la dernière lecture
        self._instable: Dict[Any, int] = {}
        self._ecran_du_cadre: Dict[Any, Ecran] = {}
        self._ecran_de_page: Dict[Any, Ecran] = {}
        self._ouvreurs: Dict[Any, Any] = {}  # onglet -> onglet qui l'a ouvert
        self._onglets_cliques: set = set()
        self._connexion_signalee = False

    # ------------------------------------------------------------------ événements (fil Playwright)
    def _recevoir(self, source: Dict[str, Any], charge: str) -> None:
        """Appelé par Playwright depuis sa propre boucle : AUCUN appel Playwright ici."""
        try:
            donnees = json.loads(charge)
        except (TypeError, ValueError):
            return
        if not isinstance(donnees, dict):
            return
        if donnees.get("type") == "fin":
            self._fin = True
            return
        cible = donnees.get("cible")
        page = source.get("page") if source else None
        if donnees.get("type") == "clic" and isinstance(cible, dict) and page is not None:
            cible["_quand"] = time.monotonic()
            self._clics[page] = cible
            if cible.get("zone") == "onglet" or cible.get("role") == "tab":
                self._onglets_cliques.add(normaliser(cible.get("texte") or cible.get("aria") or ""))

    def _requete(self, requete: Any) -> None:
        """Nature des envois de données du portail (jamais les valeurs). Rien n'est bloqué."""
        try:
            if not self.site or requete.method.upper() in METHODES_LECTURE:
                return
            if site_de(requete.url) != self.site:
                return  # mesure d'audience, service d'un autre site : sans rapport avec le portail
            self._noter_envoi(classer_requete(requete))
        except Exception as e:  # noqa: BLE001 - un gestionnaire ne doit jamais lever
            journal.debug("Envoi non classé : %s", e)

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
        """Fichier proposé au téléchargement : noté (sa nature), pas gardé."""
        try:
            nom = telechargement.suggested_filename or ""
            page = telechargement.page
        except Exception:  # noqa: BLE001
            nom, page = "", None
        self.telechargements.append(nom)
        origine = self._ecran_de_page.get(page)
        clic = self._clics.pop(page, None) if page is not None else None
        if origine is not None and clic:
            extension = nom.rsplit(".", 1)[-1].lower()[:5] if "." in nom else "?"
            origine.resultats.setdefault(self._cle(clic), f"télécharge un fichier .{masquer(extension)}")
        journal.info("   %s Fichier proposé au téléchargement : noté (le robot ne le garde pas).", S.OK)
        try:
            telechargement.cancel()
        except Exception:  # noqa: BLE001
            pass

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
        for ouverte in contexte.pages:
            self._suivre(ouverte)
        contexte.on("page", self._suivre)
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001
            raise ErreurAutoweb(f"Impossible d'ouvrir {url} : {str(e).splitlines()[0]}")
        self._attendre(page)
        self._connexion(page, premiere_fois=True)
        page = self.nav.page_courante()
        self.site = site_de(page.url)
        m = decouper(page.url)
        self.hote = m.netloc if m else ""
        self.depart = page.url
        self._clics.clear()  # les clics de la connexion ne mènent à aucun écran du portail
        self._fin = False
        try:
            if promenade is not None:
                self.laisser_tourner(2 * self.releve_s + 0.5)
                promenade(self)
                self.laisser_tourner(2 * self.releve_s + 0.5)
            elif self.interactif:
                from .console import lire_ligne

                print(CONSIGNES.format(ligne=S.LIGNE))
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
            except Exception as e:  # noqa: BLE001
                journal.debug("Dernière lecture impossible : %s", e)
            self.enregistrer()

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
        if time.monotonic() >= self._prochain:
            self._prochain = time.monotonic() + self.releve_s
            self._relever()

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
            return  # connexion d'entreprise, Google, service d'un autre site : pas le portail
        etat = cadre.evaluate(JS_ETAT, len(self.ecrans))
        if etat is None:
            self._equiper(cadre)
            etat = cadre.evaluate(JS_ETAT, len(self.ecrans))
            if etat is None:
                return
        etat = tuple(etat)
        precedent = self._etats.get(cadre)
        self._etats[cadre] = etat
        if self._lus.get(cadre) == etat or etat[2] == "loading":
            return  # rien de nouveau depuis la dernière lecture, ou page en cours de chargement
        if precedent != etat and not dernier:
            # l'écran bouge encore : on attend qu'il se calme (une page qui bouge sans cesse,
            # une horloge par exemple, est lue quand même au troisième tour)
            self._instable[cadre] = self._instable.get(cadre, 0) + 1
            if self._instable[cadre] < 3:
                return
        self._instable[cadre] = 0
        self._lus[cadre] = etat
        if "pdf" in str(etat[3]).lower():
            self._document(page)
            return
        lecture = cadre.evaluate(JS_ECRAN, [self.limites.exemples, self.limites.max_cibles])
        self._noter(page, cadre, lecture)

    def _document(self, page: Page) -> None:
        origine, clic = self._origine(page)
        self.documents += 1
        if origine is not None and clic:
            origine.resultats.setdefault(self._cle(clic), "ouvre un document PDF")
        journal.info("   %s Document PDF affiché : noté (le robot ne lit pas son contenu).", S.OK)

    def _origine(self, page: Page):
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
                journal.info("   Écran de connexion : pas noté (il ne fait pas partie de la carte).")
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
            pas = Action("clic", selecteur=clic.get("selecteur", ""), texte=clic.get("texte") or clic.get("aria") or "",
                         zone=clic.get("zone", ""), ligne=clic.get("ligne", -1) if isinstance(clic.get("ligne"), int) else -1,
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
                f"cliqué ; le robot n'a rien fait), {self.documents} document(s) PDF affiché(s).")

    def resume(self) -> Dict[str, Any]:
        r = super().resume()
        r["documents"] = self.documents
        return r
