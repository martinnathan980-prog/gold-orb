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
    INDICATEURS_CHARGEMENT, JS_ECRAN, JS_OUTILS, METHODES_LECTURE, MOTIF_GARDE, MOTIF_GARDE_SOURCE, Action, Ecran,
    Explorateur, Limites, _fin_adresse, adresse_dangereuse, classer_requete, decouper, masquer, nom_de_code,
    nom_technique, normaliser, signature,
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
JS_VISITE_MODELE = r"""
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
  // Filet de sécurité : pendant la visite, les boutons de modification ne partent pas. Actif
  // seulement sur le portail, une fois la visite commencée (window.__autoweb_garde, posé par le
  // robot) : jamais sur la page de connexion de l'entreprise (Microsoft, Okta, CAS...).
  const ACTION = new RegExp("__MOTIF_GARDE__");
  const sansAccents = t => String(t || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase()
                                  .replace(/_/g, ' ').replace(/\s+/g, ' ').trim();
  const siteDe = h => {
    h = String(h || '').toLowerCase();
    if (!h || /^[\d.]+$|^\[?[0-9a-f:]+\]?$/.test(h) || !h.includes('.')) return h;
    return h.split('.').slice(-2).join('.');
  };
  const PETITS = 'button, a[href], input[type=submit], input[type=button], input[type=image], [role=button], ' +
                 '[role=menuitem], [role=menuitemradio], [role=menuitemcheckbox], [role=link], [role=tab], [role=option], ' +
                 '[onclick], summary';
  const GRANDS = ['TR', 'TBODY', 'THEAD', 'TABLE', 'FORM', 'SECTION', 'MAIN', 'ARTICLE', 'UL', 'OL', 'NAV', 'HEADER',
                  'FOOTER', 'ASIDE', 'BODY', 'HTML', 'FIELDSET'];
  const SAISIES = ['INPUT', 'SELECT', 'TEXTAREA', 'OPTION', 'LABEL'];
  // l'élément actionné : le plus proche du clic qui ressemble à un bouton (jamais une ligne, un formulaire)
  const actionneur = ev => {
    const chemin = ev.composedPath ? ev.composedPath() : [ev.target];
    for (const n of chemin) {
      if (!n || n.nodeType !== 1) continue;
      if (duRobot(n) || GRANDS.includes(n.tagName)) return null;
      if (SAISIES.includes(n.tagName) && !(n.tagName === 'INPUT' && /^(submit|button|image|reset)$/i.test(n.type || ''))) return null;
      let oui = false;
      try {
        oui = n.matches(PETITS) || n.hasAttribute('tabindex') || n.tagName.includes('-') ||
              (getComputedStyle(n).cursor === 'pointer' && !(n.parentElement && getComputedStyle(n.parentElement).cursor === 'pointer'));
      } catch (err) {}
      if (oui) return n;
    }
    return null;
  };
  // ce que dit l'élément : son texte s'il est court, ses bulles, ses images, ses icônes
  const etiquette = (e, profondeur) => {
    const morceaux = [e.getAttribute('aria-label'), e.getAttribute('title'), e.getAttribute('alt')];
    if (e.tagName === 'INPUT') morceaux.push(e.value);
    const visible = (e.innerText || e.textContent || '').replace(/\s+/g, ' ').trim();
    if (visible && visible.length <= 40) morceaux.push(visible);
    Array.from(e.querySelectorAll('img, [title], [aria-label]')).slice(0, 6).forEach(x =>
      morceaux.push(x.getAttribute('alt') || x.getAttribute('title') || x.getAttribute('aria-label')));
    Array.from(e.querySelectorAll('svg title')).slice(0, 3).forEach(x => morceaux.push(x.textContent));
    let texte = morceaux.filter(Boolean).join(' ');
    if (!visible) {  // icône seule : ses classes et sa ligature parlent (fa-trash, glyphicon-pencil, « delete »)
      const icones = [e].concat(Array.from(e.querySelectorAll('i, span, svg, use, mat-icon, img')).slice(0, 6)).map(x =>
        (typeof x.className === 'string' ? x.className : ((x.className && x.className.baseVal) || '')) + ' ' +
        (x.getAttribute('href') || x.getAttribute('xlink:href') || x.getAttribute('src') || '') + ' ' +
        (/material|mat-icon/i.test(x.tagName + ' ' + (typeof x.className === 'string' ? x.className : '')) ? x.textContent : '')).join(' ');
      if (/(trash|delete|remove|suppr|poubelle|corbeille|pencil|crayon|edit|save|floppy|disk|copy|clone|duplicat|content_copy|note_add|add_circle|plus-circle)/i.test(icones)) texte += ' supprimer';
    }
    const hote = e.getRootNode && e.getRootNode().host;  // bouton dans un composant web : le texte est sur l'hôte
    if (!texte.trim() && hote && !profondeur) texte = etiquette(hote, 1);
    return texte;
  };
  const lienSimple = e => {
    if (e.tagName !== 'A') return false;
    const href = (e.getAttribute('href') || '').trim();
    return !!href && !/^(#|javascript:)/i.test(href) && !e.hasAttribute('onclick') && !e.hasAttribute('data-method') &&
           !e.hasAttribute('data-confirm') && !e.hasAttribute('data-remote');
  };
  const dangereux = e => {
    if (!e) return false;
    const garde = window.__autoweb_garde;
    if (!garde || siteDe(location.hostname) !== garde.site) return false;
    // formulaire de connexion (mot de passe visible) : jamais bloqué, même s'il s'appelle « submit »
    const formulaire = e.closest && e.closest('form');
    if (formulaire && Array.from(formulaire.querySelectorAll('input[type=password]')).some(x => x.offsetWidth > 0)) return false;
    if (lienSimple(e)) {
      // un lien ordinaire ne fait qu'ouvrir une page : bloqué seulement si son adresse est une action
      // (…/plans/5/delete) ; son texte peut être un nom de plan (« Nouveau poste »)
      return ACTION.test(sansAccents(decodeURIComponent((e.getAttribute('href') || '').replace(/[\/_.\-?=&]+/g, ' '))));
    }
    return ACTION.test(sansAccents(etiquette(e, 0)));
  };
  const avertir = message => {
    try {
      const a = document.createElement('div');
      a.setAttribute('data-autoweb', '1');
      a.setAttribute('style', 'position:fixed;top:14px;left:50%;transform:translateX(-50%);z-index:2147483647;' +
        'background:#b45309;color:#fff;font:600 13px/1.4 system-ui,Arial;padding:10px 14px;border-radius:8px;' +
        'box-shadow:0 2px 12px rgba(0,0,0,.4);max-width:520px;pointer-events:none');
      a.textContent = message;
      (document.body || document.documentElement).appendChild(a);
      setTimeout(() => a.remove(), 6000);
    } catch (err) {}
  };
  const bloquer = (ev, compter) => {
    ev.preventDefault(); ev.stopImmediatePropagation();
    if (compter) {
      avertir("Pendant la visite, le robot bloque ce bouton, par sécurité : rien n'est parti. " +
              "Pour le faire vraiment, utilisez votre Chrome habituel.");
      envoyer({ type: 'bloque' });
    }
  };
  const gardeSouris = ev => {
    const e = actionneur(ev);
    if (dangereux(e)) bloquer(ev, ev.type === 'click' || ev.type === 'auxclick');
  };
  const gardeClavier = ev => {
    const garde = window.__autoweb_garde;
    if (!garde || siteDe(location.hostname) !== garde.site) return;
    if ((ev.ctrlKey || ev.metaKey) && (ev.key || '').toLowerCase() === 's') { bloquer(ev, true); return; }  // Ctrl+S
    if (ev.key !== 'Enter' && ev.key !== ' ') return;
    let e = ev.composedPath ? ev.composedPath()[0] : ev.target;
    if (e && e.nodeType === 1 && !SAISIES.includes(e.tagName)) {
      const x = actionneur({ composedPath: () => (ev.composedPath ? ev.composedPath() : [e]) });
      if (dangereux(x)) bloquer(ev, true);
    }
  };
  const gardeEnvoi = ev => {
    const form = ev.target;
    if (!form || form.tagName !== 'FORM') return;
    const garde = window.__autoweb_garde;
    if (!garde || siteDe(location.hostname) !== garde.site) return;
    if (Array.from(form.querySelectorAll('input[type=password]')).some(x => x.offsetWidth > 0)) return;
    // bouton qui envoie (ou, touche Entrée dans un champ, le premier bouton d'envoi du formulaire)
    const bouton = ev.submitter || form.querySelector('button:not([type]), button[type=submit], input[type=submit], input[type=image]');
    if (bouton && dangereux(bouton)) bloquer(ev, true);
  };
  const ecoutes = window.__autoweb_ecoutes || [];
  for (const [cible, type, f] of ecoutes) { try { cible.removeEventListener(type, f, true); } catch (err) {} }
  window.__autoweb_ecoutes = [];
  const ecouter = (cible, type, f) => { cible.addEventListener(type, f, true); window.__autoweb_ecoutes.push([cible, type, f]); };
  for (const type of ['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click', 'dblclick', 'auxclick']) ecouter(window, type, gardeSouris);
  ecouter(window, 'keydown', gardeClavier);
  ecouter(window, 'submit', gardeEnvoi);
  for (const type of ['click', 'auxclick']) ecouter(document, type, surClic);
  // fenêtre du robot : son titre commence par « ROBOT - », dès l'ouverture (pas la confondre)
  const titrer = () => { if (window === window.top && document.title && !document.title.startsWith('ROBOT - ')) document.title = 'ROBOT - ' + document.title; };
  titrer(); setTimeout(titrer, 800);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', titrer);
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
      texte.textContent = "Fenêtre du ROBOT. Connectez-vous si besoin, affichez l'accueil de votre portail, " +
                          "puis appuyez sur Entrée dans la fenêtre noire.";
      const boutons = document.createElement('div');
      boutons.className = '__autoweb_boutons';
      // les boutons n'apparaissent qu'une fois la visite commencée
      boutons.setAttribute('style', 'margin-top:5px;display:none;gap:6px;flex-wrap:wrap');
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

# le vocabulaire d'action du filet est le même que côté robot (explorateur.MOTIF_GARDE)
JS_VISITE = JS_VISITE_MODELE.replace('"__MOTIF_GARDE__"', json.dumps(MOTIF_GARDE_SOURCE))


# Lu à chaque tour : adresse, nombre de changements, état de chargement, type de document,
# taille du cadre, indicateur de chargement visible. Met aussi à jour le bandeau (étape, boutons),
# le titre de la fenêtre (« ROBOT - ») et arme le filet de sécurité sur ce cadre du portail.
# None si la page n'est pas (ou plus) équipée.
JS_ETAT = r"""
([n, texteEtape, derniere, cote, site]) => {
  if (!document.__autoweb_visite || !document.documentElement || !document.documentElement.__autoweb_arme) return null;
  if (!window.__autoweb_garde) window.__autoweb_garde = { site: site };
  if (window === window.top) {
    const b = document.getElementById('__autoweb_visite');
    if (b && !b.dataset.fini) {
      const cle = n + '|' + texteEtape + '|' + derniere + '|' + cote;
      if (b.dataset.cle !== cle) {
        b.dataset.cle = cle;
        const t = b.querySelector('.__autoweb_texte');
        if (t) t.textContent = texteEtape + '   (' + n + ' écran(s) noté(s) ; le robot ne clique sur rien)';
        const boutons = b.querySelector('.__autoweb_boutons');
        if (boutons) boutons.style.display = 'flex';
        const s = b.querySelector('.__autoweb_etape');
        if (s) s.style.display = derniere ? 'none' : '';
        b.style.left = cote ? 'auto' : '10px'; b.style.right = cote ? '10px' : 'auto';
      }
    }
    if (document.title && !document.title.startsWith('ROBOT - ')) document.title = 'ROBOT - ' + document.title;
  }
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width * r.height > 400; };
  let charge = false;
  try {
    for (const sel of """ + json.dumps(INDICATEURS_CHARGEMENT) + r""") {
      for (const e of document.querySelectorAll(sel)) {
        if (vis(e) && !e.closest('[data-autoweb]') && !e.querySelector('input')) { charge = true; break; }
      }
      if (charge) break;
    }
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
   Ne validez rien, n'enregistrez rien. Par sécurité, le robot bloque en plus la plupart
   des boutons et des envois de modification (Supprimer, Enregistrer, Dupliquer,
   Créer, Modifier...), mais il ne peut pas les reconnaître tous : consultez seulement.

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
        self.envois_bloques: List[str] = []  # envois de modification coupés par le robot
        self.dialogues = 0
        self.etape = 0
        self.cote = False
        self.ignores: Dict[str, int] = {}  # pages et cadres laissés de côté, et pourquoi
        self.dossier_telechargements = dossier_telechargements or (Path.home() / "Downloads")
        self._fin = False
        self._interruption = False
        self._changer_etape = 0
        self._prochain = 0.0
        self._derniere_sauvegarde = 0.0
        self._a_sauver = False
        self._clics: Dict[Any, Dict[str, Any]] = {}  # dernier clic de l'utilisateur, par onglet
        self._etats: Dict[Any, tuple] = {}  # cadre -> état vu au tour précédent
        self._lus: Dict[Any, tuple] = {}  # cadre -> état au moment de la dernière lecture
        self._stable: Dict[Any, int] = {}
        self._instable: Dict[Any, int] = {}
        self._ecran_du_cadre: Dict[Any, Ecran] = {}
        self._ecran_de_page: Dict[Any, Ecran] = {}
        self._ouvreurs: Dict[Any, Any] = {}  # onglet -> onglet qui l'a ouvert
        self._onglets_cliques: set = set()
        self._telechargements_en_cours: List[Dict[str, Any]] = []
        self._connexion_signalee = False
        self._signales = {"boutons": 0, "envois": 0, "dialogues": 0}
        self._autres: set = set()  # adresses d'autres sites déjà comptées
        self.garde_reseau = False

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
            if self.site:  # bandeau d'une page ouverte avant le début de la visite : ignoré
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
        if self.site and url_cadre and _site_adresse(url_cadre) != self.site:
            return  # clic dans un service d'un autre site (publicité, aide en ligne...) : sans rapport
        cible["_quand"] = time.monotonic()
        self._clics[page] = cible
        if cible.get("zone") == "onglet" or cible.get("role") == "tab":
            self._onglets_cliques.add(normaliser(cible.get("texte") or cible.get("aria") or ""))

    def _requete(self, requete: Any) -> None:
        """Nature des échanges du portail (jamais les valeurs)."""
        try:
            if not self.site or _site_adresse(requete.url) != self.site:
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

    def _garde_reseau(self, route: Any) -> None:
        """Seconde barrière, derrière le filet de la page : un envoi vers le portail qui ressemble à
        une modification (DELETE, « supprimer », « enregistrer », mutation GraphQL...) est coupé
        avant de partir. Les lectures, recherches et téléchargements passent."""
        try:
            requete = route.request
            raison = self._envoi_dangereux(requete) if self.garde_reseau else ""
            if raison:
                self.envois_bloques.append(raison)
                journal.debug("Envoi coupé pendant la visite : %s", raison)
                route.abort()
            else:
                route.continue_()
        except Exception as e:  # noqa: BLE001 - un gestionnaire ne doit jamais lever
            journal.debug("Garde de la visite : %s", e)

    def _envoi_dangereux(self, requete: Any) -> str:
        if not self.site or _site_adresse(requete.url) != self.site:
            return ""  # connexion d'entreprise, autres sites : jamais touchés
        methode = requete.method.upper()
        if methode in ("DELETE", "PUT", "PATCH", "MERGE"):
            return f"{methode} {_fin_adresse(requete.url)}"
        if methode in METHODES_LECTURE:
            if requete.is_navigation_request() or requete.resource_type in ("xhr", "fetch", "document"):
                mot = adresse_dangereuse(requete.url)
                return f"{methode} {_fin_adresse(requete.url)} (adresse d'action)" if mot else ""
            return ""
        nature = classer_requete(requete, MOTIF_GARDE)
        return nature if "[écriture probable]" in nature else ""

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
            if self.site:
                page.evaluate("s => { if (!window.__autoweb_garde) window.__autoweb_garde = { site: s }; }", self.site)
        except Exception:  # noqa: BLE001 - page fermée ou en cours de navigation
            pass

    def _dialogue(self, genre: str) -> None:
        """Boîte de dialogue du portail pendant la visite : le robot répond « Annuler » (ou la
        ferme), par sécurité et pour ne jamais rester bloqué sur un onglet caché."""
        self.dialogues += 1

    def _telechargement_vu(self, telechargement: Any) -> None:
        """Fichier téléchargé (un PDF de plan...) : il arrivera dans Téléchargements, comme
        d'habitude, dès qu'il est complet. Rangé au fil des tours, sans bloquer la visite."""
        try:
            page = telechargement.page
        except Exception:  # noqa: BLE001
            page = None
        self._telechargements_en_cours.append({"objet": telechargement, "page": page, "taille": -1, "calme": 0,
                                               "debut": time.monotonic(), "note": False})

    def _chemin_provisoire(self, telechargement: Any) -> Optional[Path]:
        try:
            return Path(telechargement._impl_obj._artifact.absolute_path)
        except Exception:  # noqa: BLE001
            return None

    def _ranger_telechargements(self, attente_max_s: float = 0.0) -> None:
        """Copie dans Téléchargements les fichiers complets. Un fichier dont la taille ne bouge
        plus depuis deux tours est considéré comme complet : save_as ne bloque alors pas."""
        fin = time.monotonic() + attente_max_s
        while True:
            for entree in list(self._telechargements_en_cours):
                telechargement = entree["objet"]
                if not entree["note"]:
                    entree["note"] = True
                    try:
                        nom = telechargement.suggested_filename or "fichier"
                    except Exception:  # noqa: BLE001
                        nom = "fichier"
                    entree["nom"] = nom
                    self.telechargements.append(nom)
                    origine, clic = self._origine(entree["page"]) if entree["page"] is not None else (None, None)
                    extension = nom.rsplit(".", 1)[-1].lower()[:5] if "." in nom else "?"
                    entree["extension"] = extension
                    if origine is not None and clic:
                        origine.resultats.setdefault(self._cle(clic), f"télécharge un fichier .{masquer(extension)}")
                        self._consommer(entree["page"], clic)
                provisoire = self._chemin_provisoire(telechargement)
                taille = provisoire.stat().st_size if provisoire is not None and provisoire.is_file() else -1
                if taille < 0 or taille != entree["taille"]:
                    entree["taille"], entree["calme"] = taille, 0
                    if provisoire is not None:
                        continue
                entree["calme"] += 1
                if entree["calme"] < 2 and provisoire is not None:
                    continue
                self._telechargements_en_cours.remove(entree)
                self._enregistrer_telechargement(telechargement, entree["nom"], entree["extension"])
            if not self._telechargements_en_cours or time.monotonic() >= fin:
                return
            time.sleep(0.5)

    def _enregistrer_telechargement(self, telechargement: Any, nom: str, extension: str) -> None:
        propre = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", nom).strip(" .") or "fichier"
        dossier = self.dossier_telechargements if self.dossier_telechargements.is_dir() else self.nav._dossier_telechargements()
        cible = dossier / propre
        i = 2
        while cible.exists():
            cible = dossier / f"{Path(propre).stem} ({i}){Path(propre).suffix}"
            i += 1
        try:
            telechargement.save_as(str(cible))
            # le nom du fichier peut être un numéro de plan : il n'est pas affiché
            print(f"   {S.OK} Un fichier .{masquer(extension)} est arrivé dans vos Téléchargements, comme d'habitude.",
                  flush=True)
        except Exception as e:  # noqa: BLE001
            journal.debug("Téléchargement non enregistré : %s", e)

    # ------------------------------------------------------------------ déroulement
    def visiter(self, url: str, promenade: Optional[Callable[["Visite"], None]] = None) -> None:
        """Ouvre le portail, fait confirmer la page d'accueil, puis note ce que l'utilisateur
        affiche jusqu'à ce qu'il ait fini. `promenade` : tests, gestes joués à sa place."""
        import signal

        def sur_ctrl_c(*_: Any) -> None:
            # jamais d'interruption au milieu d'un appel au navigateur : on s'arrête au prochain tour
            self._interruption = True
            print(f"\n{S.ATTENTION} Arrêt demandé : le robot termine proprement.", flush=True)

        try:
            ancien = signal.signal(signal.SIGINT, sur_ctrl_c)
        except (ValueError, OSError):
            ancien = None
        try:
            self._visiter(url, promenade)
        finally:
            if ancien is not None:
                signal.signal(signal.SIGINT, ancien)

    def _visiter(self, url: str, promenade: Optional[Callable[["Visite"], None]]) -> None:
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
            try:
                page.goto(url, wait_until="domcontentloaded")
            except Exception as e:  # noqa: BLE001 - lent, ou connexion d'entreprise : l'utilisateur prend la main
                print(f"{S.ATTENTION} La page met du temps à s'ouvrir ({str(e).splitlines()[0][:80]}).")
                print("   Si elle ne s'affiche pas, tapez l'adresse du portail dans la fenêtre du robot.")
            self._verifier_interruption()
            self._attendre(page)
            self._verifier_interruption()
            self._connexion(page, premiere_fois=True)
            self._verifier_interruption()
            page = self.nav.page_courante()
            self.site = _site_adresse(page.url)
            m = decouper(page.url)
            self.hote = m.netloc if m else ""
            self.depart = page.url
            self._clics.clear()  # les clics de la connexion ne mènent à aucun écran du portail
            self._fin = False
            self._changer_etape = 0
            self._armer()
            if promenade is not None:
                self.laisser_tourner(2 * self.releve_s + 0.5)
                promenade(self)
                self.laisser_tourner(2 * self.releve_s + 0.5)
            elif self.interactif:
                print(CONSIGNES.format(ligne=S.LIGNE))
                self._annoncer_etape()
                self._attendre_fin()
            self.arret = "visite terminée"
        except FinVisite as e:
            self.arret = str(e)
        except KeyboardInterrupt:
            self.arret = "visite arrêtée (Ctrl+C)"
        finally:
            self.complet = True
            self.garde_reseau = False
            try:
                if self.nav.pages_de_travail() and self.site:
                    self._relever(dernier=True)  # le dernier écran affiché, s'il n'a pas encore été lu
                    self._ranger_telechargements(attente_max_s=20.0)
                self._techno_cookies()
            except Exception as e:  # noqa: BLE001
                journal.debug("Dernière lecture impossible : %s", e)
            if self.site:
                self.enregistrer()
            self._expliquer_si_vide()

    def _armer(self) -> None:
        """Visite commencée : filet de sécurité dans les pages du portail, contrôle des envois."""
        contexte = self.nav.contexte
        contexte.add_init_script(f"window.__autoweb_garde = {json.dumps({'site': self.site})};")
        for ouverte in self.nav.pages_de_travail():
            for cadre in list(ouverte.frames):
                if _site_adresse(cadre.url or "") == self.site:
                    self._equiper(cadre)
        self.garde_reseau = True
        contexte.route("**/*", self._garde_reseau)
        self.nav.sur_dialogue = self._dialogue

    def _verifier_interruption(self) -> None:
        if self._interruption:
            raise FinVisite("visite arrêtée (Ctrl+C)")

    def _attendre_fin(self) -> None:
        """Jusqu'à « Terminer la visite » dans le bandeau, ou Entrée ici (confirmé : un Entrée en trop
        ne termine rien)."""
        from .console import lire_ligne, vider_clavier

        while True:
            vider_clavier()
            lire_ligne(self._pomper)
            print("   Terminer la visite ? (o/n) [o] : ", end="", flush=True)
            reponse = (lire_ligne(self._pomper) or "").strip().lower()
            if not reponse.startswith("n"):
                return
            print("   D'accord, la visite continue.", flush=True)

    def laisser_tourner(self, duree_s: float) -> None:
        """Fait tourner la visite un moment, sans attendre l'utilisateur."""
        fin = time.monotonic() + duree_s
        while time.monotonic() < fin:
            self._pomper()

    def _pomper(self) -> None:
        self.nav.pomper(250)
        self._verifier_interruption()
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
        self._signaler()
        self._ranger_telechargements()
        if time.monotonic() >= self._prochain:
            self._prochain = time.monotonic() + self.releve_s
            self._relever()
        if self._a_sauver and time.monotonic() - self._derniere_sauvegarde > 30:
            self._sauver()

    def _signaler(self) -> None:
        compteurs = {"boutons": self.boutons_bloques, "envois": len(self.envois_bloques), "dialogues": self.dialogues}
        messages = {
            "boutons": "Un bouton de modification a été bloqué par le robot : rien n'est parti.",
            "envois": "Un envoi qui ressemblait à une modification a été coupé par le robot : rien n'est parti.",
            "dialogues": "Le portail a affiché une boîte de dialogue : le robot a répondu « Annuler », par sécurité.",
        }
        for cle, nombre in compteurs.items():
            if nombre > self._signales[cle]:
                self._signales[cle] = nombre
                print(f"   {S.ATTENTION} {messages[cle]}", flush=True)

    def _sauver(self) -> None:
        self._a_sauver = False
        self._derniere_sauvegarde = time.monotonic()
        self.enregistrer()

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
        if len(self.ecrans) > 1 or not self.interactif or not self.site:
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
        if not url.startswith(("http:", "https:", "file:", "blob:")) or est_onglet_parasite(url):
            return
        if _site_adresse(url) != self.site:
            if url not in self._autres:
                self._autres.add(url)
                self._ignorer("page d'un autre site (connexion, Google, service externe)")
            return
        derniere = self.etape >= len(ETAPES) - 1
        parametres = [len(self.ecrans), self._texte_etape(), derniere, self.cote, self.site]
        etat = cadre.evaluate(JS_ETAT, parametres)
        if etat is None:
            self._equiper(cadre)
            etat = cadre.evaluate(JS_ETAT, parametres)
            if etat is None:
                return
        adresse, changements, pret, type_document, surface, charge = etat
        if cadre is not page.main_frame and surface < 2500:
            return  # cadre caché ou minuscule (maintien de session, compteur) : pas un écran
        cle = (adresse, changements, pret, type_document, bool(charge))
        precedent = self._etats.get(cadre)
        self._etats[cadre] = cle
        if self._lus.get(cadre) == cle or pret == "loading":
            return  # rien de nouveau depuis la dernière lecture, ou page en cours de chargement
        if cle == precedent:
            self._stable[cadre] = self._stable.get(cadre, 0) + 1
        else:
            self._stable[cadre] = 0
            self._instable[cadre] = self._instable.get(cadre, 0) + 1
        # un écran se lit quand il ne bouge plus depuis un tour (deux s'il affiche « chargement ») ;
        # une page qui bouge sans cesse (horloge...) est lue quand même, au bout de quelques tours
        if not dernier and self._stable[cadre] < (2 if charge else 1):
            if self._instable.get(cadre, 0) < (8 if charge else 3):
                return
        self._instable[cadre] = 0
        self._stable[cadre] = 0
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
            self._consommer(page, clic)
        print(f"   {S.OK} Document PDF affiché : noté (le robot ne lit pas son contenu).", flush=True)

    def _origine(self, page: Any):
        """(écran d'où l'on vient, dernier clic de l'utilisateur) pour un changement vu dans cet
        onglet. Le clic n'est PAS consommé ici : seulement quand il a mené quelque part."""
        origine = self._ecran_de_page.get(page)
        clic = self._clics.get(page)
        if origine is None and page in self._ouvreurs:  # nouvel onglet : il vient de son ouvreur
            ouvreur = self._ouvreurs[page]
            origine = self._ecran_de_page.get(ouvreur)
            clic = clic or self._clics.get(ouvreur)
        if clic and time.monotonic() - clic.get("_quand", 0) > 60:
            clic = None  # clic trop ancien : ce n'est pas lui qui a mené ici
        return origine, clic

    def _consommer(self, page: Any, clic: Dict[str, Any]) -> None:
        for cle in (page, self._ouvreurs.get(page)):
            if cle is not None and self._clics.get(cle) is clic:
                del self._clics[cle]

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
            # même écran qu'avant (un menu surligné, une horloge) : le clic attend l'écran suivant
            if connu is not origine and connu is not self._ecran_du_cadre.get(cadre):
                if origine is not None and clic:
                    origine.resultats.setdefault(self._cle(clic), f"mène à {connu.id}")
                    self.transitions.append({"de": origine.id, "action": self._cle(clic), "vers": connu.id})
                    self._consommer(page, clic)
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
        if clic:
            self._consommer(page, clic)
            if origine is not None:
                origine.resultats.setdefault(self._cle(clic), f"mène à {nouveau.id}")
                self.transitions.append({"de": origine.id, "action": self._cle(clic), "vers": nouveau.id})
        self._placer(page, cadre, principal, nouveau)
        self._annoncer(nouveau)
        self._a_sauver = True
        if len(self.ecrans) <= 3 or len(self.ecrans) % 5 == 0:
            self._sauver()

    def _placer(self, page: Page, cadre: Any, principal: bool, ecran: Ecran) -> None:
        self._ecran_du_cadre[cadre] = ecran
        if principal or page not in self._ecran_de_page:
            self._ecran_de_page[page] = ecran

    def _annoncer(self, ecran: Ecran) -> None:
        """Dans la fenêtre noire : la forme de l'écran seulement (ni son titre, ni ses noms
        d'objets), pour qu'une ligne recopiée ne contienne jamais de données."""
        details = []
        if ecran.champs:
            details.append(f"{len(ecran.champs)} champ(s)")
        if ecran.tableaux:
            details.append(f"{len(ecran.tableaux)} tableau(x)")
        onglets = []
        for c in ecran.cibles:
            nom = (c["texte"] or c["aria"]).strip()
            if (c["zone"] == "onglet" or c["role"] == "tab") and nom and not c.get("fermable") and not c.get("perso") \
                    and self._sur(nom) and normaliser(nom) not in self._onglets_cliques and nom not in onglets:
                onglets.append(nom)
        if onglets:
            details.append(f"{len(onglets)} onglet(s)")
        print(f"   {S.OK} Écran {ecran.id} noté (étape « {ecran.etape} »)"
              + (f" : {', '.join(details)}" if details else "")
              + ("  [cadre]" if ecran.cadre else ""), flush=True)
        if onglets:
            print(f"      Onglets à ouvrir aussi, un par un : {' ; '.join(masquer(o)[:30] for o in onglets[:8])}", flush=True)

    # ------------------------------------------------------------------ carte
    def _bilan_partage(self, r: Dict[str, Any]) -> str:
        return (f"Visite guidée : {r['ecrans']} écran(s) notés pendant la visite (c'est l'utilisateur qui a "
                f"cliqué ; le robot n'a rien fait), {self.documents} document(s) PDF affiché(s), "
                f"{self.boutons_bloques} bouton(s) et {len(self.envois_bloques)} envoi(s) de modification "
                f"bloqué(s) par sécurité, {self.dialogues} boîte(s) de dialogue fermée(s).")

    def resume(self) -> Dict[str, Any]:
        r = super().resume()
        r["documents"] = self.documents
        r["boutons_bloques"] = self.boutons_bloques
        r["envois_bloques"] = len(self.envois_bloques)
        return r


def _site_adresse(url: str) -> str:
    """Site d'une adresse ; « blob:https://portail... » (PDF ouvert par la page) : celui du portail."""
    return site_de(url[5:] if (url or "").startswith("blob:") else url)


def appel_de_lecture(url: str) -> str:
    """« GET …/search (appel de la page, paramètres : page, q) » : jamais les valeurs."""
    m = decouper(url)
    noms = [k for k, _ in parse_qsl(m.query if m else "", keep_blank_values=True)]
    propres = sorted({nom_technique(k, 30) for k in noms if nom_de_code(k)} - {"", "?"})
    autres = len({k for k in noms if not nom_de_code(k)})
    parametres = ", ".join(propres[:8]) + (f"{' + ' if propres else ''}{autres} autre(s)" if autres else "")
    return ("GET " + _fin_adresse(url) + " (appel de la page"
            + (f", paramètres : {parametres}" if parametres else "") + ") [lecture]")
