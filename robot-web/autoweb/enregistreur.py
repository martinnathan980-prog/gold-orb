"""Enregistreur : le robot regarde l'utilisateur faire la tâche une fois, et note
chaque clic, chaque saisie, chaque changement de page.

Principe : un petit script est injecté dans chaque page du navigateur piloté. Il
écoute les clics, les saisies et les touches, et renvoie à Python un événement par
action, avec un sélecteur stable pour l'élément concerné. Rien n'est envoyé ailleurs :
tout reste sur le poste.

Deux précautions importantes :
- le script ne renvoie JAMAIS le contenu d'un champ de saisie comme « texte » de
  l'élément (sinon un mot de passe finirait dans un sélecteur ou dans la console) ;
- côté Python, le gestionnaire d'événements n'appelle aucune fonction Playwright :
  il est exécuté dans la boucle interne de Playwright, où tout appel bloquerait
  définitivement le programme. Les sélecteurs d'iframe sont résolus à la fin.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from urllib.parse import urlsplit

from playwright.sync_api import Page

from .navigateur import Navigateur, est_onglet_parasite
from .releve import JS_SELECTEUR_IFRAME

journal = logging.getLogger("autoweb")

# Éléments considérés comme « cliquables » : on remonte jusqu'au plus proche.
CLIQUABLES = (
    'button, a[href], [role="button"], [role="link"], [role="tab"], [role="menuitem"], '
    '[role="option"], [role="checkbox"], [role="radio"], input[type="submit"], '
    'input[type="button"], input[type="reset"], label, summary'
)

JS_ENREGISTREUR = """
(CLIQUABLES) => {
  // marque posée sur le DOCUMENT : un onglet ouvert par window.open garde la même fenêtre
  // (window) entre sa page vide de départ et la vraie page, mais pas le même document
  if (document.__autoweb_enregistre) return;
  document.__autoweb_enregistre = true;
  window.__autoweb_enregistre = true;
  const attente = [];
  let compteur = 0;

  function envoyer(e) {
    // adresse de la page : sert seulement à écarter les pages Google ou Chrome (jamais écrite)
    e.url = location.href;
    try { e.url_page = window.top.location.href; } catch (err) { e.url_page = ''; }
    const texte = JSON.stringify(e);
    if (e.type_evenement === 'clic' || e.type_evenement === 'saisie' || e.type_evenement === 'touche') {
      compteur++;
      majBadge();
    }
    if (window.autowebEvenement) { try { window.autowebEvenement(texte); return; } catch (err) {} }
    attente.push(texte);
    setTimeout(() => {
      while (attente.length && window.autowebEvenement) {
        try { window.autowebEvenement(attente.shift()); } catch (err) { break; }
      }
    }, 100);
  }

  const court = (s, n) => (s || '').replace(/\\s+/g, ' ').trim().slice(0, n || 60);
  const idOk = (id) => !!id && /^[A-Za-z_][\\w-]*$/.test(id) && !/\\d{4,}/.test(id) && id.length <= 40;
  const echapper = (s) => (s || '').replace(/\\\\/g, '\\\\\\\\').replace(/"/g, '\\\\"');

  // --- bandeau d'arrêt, en bas à gauche (coin le moins utilisé par les outils) ---
  const ID_BADGE = '__autoweb_badge';
  function majBadge() {
    const b = document.getElementById(ID_BADGE);
    if (b && !b.dataset.fini)
      b.textContent = compteur ? ('Enregistrement : ' + compteur + ' action(s) - cliquez pour terminer')
                               : 'Enregistrement en cours - cliquez pour terminer';
  }
  function badge() {
    if (document.getElementById(ID_BADGE) || !document.documentElement) return;
    const b = document.createElement('div');
    b.id = ID_BADGE;
    b.style.cssText = ('position:fixed;bottom:12px;left:12px;z-index:2147483647;background:#dc2626;' +
      'color:#fff;font:600 12px/1.2 system-ui,-apple-system,Arial;padding:8px 11px;border-radius:6px;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.35);cursor:pointer;user-select:none;max-width:300px;opacity:.93');
    b.textContent = 'Enregistrement en cours - cliquez pour terminer';
    b.addEventListener('click', function (ev) {
      ev.stopPropagation(); ev.preventDefault();
      b.dataset.fini = '1';
      b.textContent = 'Enregistrement termine - revenez au Terminal';
      b.style.background = '#16a34a';
      envoyer({ type_evenement: 'fin' });
    }, true);
    document.documentElement.appendChild(b);
    majBadge();
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', badge);
  else badge();
  setTimeout(badge, 500);
  const surBadge = (n) => !!(n && n.closest && n.closest('#' + ID_BADGE));

  // --- description des éléments ---
  function estChampSaisie(e) {
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'textarea' || e.isContentEditable) return true;
    return tag === 'input' && !['submit', 'button', 'reset', 'image', 'checkbox', 'radio', 'file'].includes(type);
  }

  // libellé d'un champ : le texte du <label> SANS les listes et champs qu'il contient
  // (sinon toutes les options d'une liste, des noms de clients..., deviendraient le « nom » du champ)
  function libelleDe(e) {
    if (idOk(e.id)) {
      const l = document.querySelector('label[for="' + e.id + '"]');
      if (l && texteSeul(l)) return texteSeul(l);
    }
    const p = e.closest('label');
    if (p && texteSeul(p)) return texteSeul(p);
    const al = e.getAttribute('aria-label');
    if (al) return court(al, 80);
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = document.getElementById(lb.split(' ')[0]); if (t) return texteSeul(t); }
    const ph = e.getAttribute('placeholder');
    if (ph) return court(ph, 80);
    const prev = e.previousElementSibling;
    if (prev && ['LABEL','SPAN','TD','TH','DIV'].includes(prev.tagName) && texteSeul(prev).length < 60)
      return texteSeul(prev);
    return '';
  }

  // Texte visible d'un element : JAMAIS la valeur d'un champ de saisie.
  function texteDe(e) {
    if (estChampSaisie(e)) return '';
    const tag = e.tagName.toLowerCase();
    if (tag === 'select') return '';   // son texte, ce sont toutes ses options
    const type = (e.getAttribute('type') || '').toLowerCase();
    if (tag === 'input' && ['submit', 'button', 'reset'].includes(type)) return court(e.value || '', 60);
    // aria-label d'abord : c'est le nom que Playwright utilisera (bouton à icône)
    return court(e.getAttribute('aria-label') || e.innerText || e.getAttribute('title') || '', 60);
  }

  function cheminCss(e) {
    const parts = [];
    let n = e;
    while (n && n.nodeType === 1 && parts.length < 6) {
      if (idOk(n.id)) { parts.unshift('#' + n.id); break; }
      const parent = n.parentElement;
      const tag = n.tagName.toLowerCase();
      if (!parent) { parts.unshift(tag); break; }
      const memes = Array.from(parent.children).filter(c => c.tagName === n.tagName);
      parts.unshift(memes.length > 1 ? tag + ':nth-of-type(' + (memes.indexOf(n) + 1) + ')' : tag);
      n = parent;
    }
    return parts.join(' > ');
  }

  // Un element dans une ligne de tableau ou de liste : on l'ancre sur le texte de
  // la ligne (numero de plan...) plutot que sur sa position, qui change tout le temps.
  function ancreLigne(e) {
    const ligne = e.closest('tr, [role="row"], li');
    if (!ligne || ligne.contains(document.getElementById(ID_BADGE))) return '';
    let texte = '';
    const cellules = ligne.querySelectorAll('td, th, [role="cell"], [role="gridcell"], a');
    for (let i = 0; i < cellules.length; i++) {
      const t = court(cellules[i].innerText, 60);
      if (t && t.length >= 3 && t.length <= 60) { texte = t; break; }
    }
    if (!texte) texte = court(ligne.innerText, 60);
    if (!texte || texte.length > 60 || texte.length < 3) return '';
    const tagLigne = ligne.tagName.toLowerCase();
    let descripteur = e.tagName.toLowerCase();
    const al = e.getAttribute('aria-label');
    const ti = e.getAttribute('title');
    if (al) descripteur = '[aria-label="' + echapper(court(al, 40)) + '"]';
    else if (ti) descripteur = '[title="' + echapper(court(ti, 40)) + '"]';
    let base = tagLigne + ':has-text("' + echapper(texte) + '") ' + descripteur;
    try {
      const memes = Array.from(ligne.querySelectorAll(descripteur));
      if (memes.length > 1) {
        const rang = memes.indexOf(e);
        if (rang >= 0) base += ' >> nth=' + rang;
      }
    } catch (err) {}
    return base;
  }

  function selecteurDe(e) {
    const tid = e.getAttribute('data-testid') || e.getAttribute('data-test') || e.getAttribute('data-qa');
    if (tid) return 'test=' + tid;
    if (idOk(e.id)) return '#' + e.id;
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || '').toLowerCase();
    const role = e.getAttribute('role') || '';
    const estBouton = tag === 'button' || role === 'button' || (tag === 'input' && ['submit','button','reset'].includes(type));
    const texte = texteDe(e);
    // Dans un tableau ou une liste, le texte et le name se répètent d'une ligne à
    // l'autre : on ancre sur le texte de la ligne (numéro de plan, référence...).
    const ancreDansLigne = ancreLigne(e);
    if (ancreDansLigne) return ancreDansLigne;
    // Pour un bouton ou un lien, le texte visible est plus sûr que l'attribut name
    // (deux boutons d'un même formulaire partagent souvent le même name).
    if (estBouton && texte) return 'role=button:' + texte;
    if ((tag === 'a' || role === 'link') && texte) return 'role=link:' + texte;
    const nom = e.getAttribute('name');
    if (nom) {
      if (tag === 'input' && (type === 'radio' || type === 'checkbox') && e.value)
        return tag + '[name="' + echapper(nom) + '"][value="' + echapper(e.value) + '"]';
      return tag + '[name="' + echapper(nom) + '"]';
    }
    const lib = libelleDe(e);
    if (lib && ['input','select','textarea'].includes(tag)) return 'libelle=' + lib;
    const ancre = ancreLigne(e);
    if (ancre) return ancre;
    if (texte && texte.length <= 40) return 'texte=' + texte;
    return cheminCss(e);
  }

  function cible(e) {
    if (!e || e.nodeType !== 1) return null;
    const c = e.closest(CLIQUABLES);
    if (c) return c;
    let n = e;
    for (let i = 0; i < 3 && n && n.nodeType === 1; i++) {
      try { if (getComputedStyle(n).cursor === 'pointer') return n; } catch (err) {}
      n = n.parentElement;
    }
    return e;
  }

  function decrire(e) {
    const tag = e.tagName.toLowerCase();
    const champ = ['input', 'select', 'textarea'].includes(tag) || e.isContentEditable;
    return {
      selecteur: selecteurDe(e),
      tag: tag,
      type: (e.getAttribute('type') || '').toLowerCase(),
      // un bouton porte son propre nom, pas celui du texte posé juste avant lui (titre d'un plan...)
      libelle: champ ? (libelleDe(e) || texteDe(e)) : (texteDe(e) || libelleDe(e)),
      texte: texteDe(e)
    };
  }

  // --- saisies : « change » n'est pas toujours emis (champs a suggestion, editeurs) ---
  let enAttente = null;   // {element, minuteur}
  function decrireSaisie(e) {
    const d = decrire(e);
    d.type_evenement = 'saisie';
    const tag = d.tag;
    if (tag === 'select') {
      const opt = e.options[e.selectedIndex];
      d.valeur = e.value;
      d.libelle_valeur = opt ? court(opt.text, 80) : '';
    } else if (d.type === 'checkbox' || d.type === 'radio') {
      d.valeur = e.checked ? 'oui' : 'non';
    } else if (e.isContentEditable) {
      d.valeur = court(e.innerText, 500);
    } else {
      d.valeur = e.value !== undefined && e.value !== null ? String(e.value) : '';
    }
    return d;
  }
  function viderEnAttente() {
    if (!enAttente) return;
    const e = enAttente.element;
    clearTimeout(enAttente.minuteur);
    enAttente = null;
    try { if (e && e.isConnected) envoyer(decrireSaisie(e)); } catch (err) {}
  }
  document.addEventListener('input', (ev) => {
    const e = ev.target;
    if (!e || e.nodeType !== 1 || surBadge(e) || !estChampSaisie(e)) return;
    if (enAttente && enAttente.element !== e) viderEnAttente();
    if (enAttente) clearTimeout(enAttente.minuteur);
    enAttente = { element: e, minuteur: setTimeout(viderEnAttente, 600) };
  }, true);

  document.addEventListener('change', (ev) => {
    const e = ev.target;
    if (!e || e.nodeType !== 1 || surBadge(e)) return;
    const tag = e.tagName.toLowerCase();
    if (!['input','select','textarea'].includes(tag) && !e.isContentEditable) return;
    if (enAttente && enAttente.element === e) { clearTimeout(enAttente.minuteur); enAttente = null; }
    envoyer(decrireSaisie(e));
  }, true);

  // --- photo de l'ecran : STRUCTURE seulement (noms des champs, rempli oui/non, jamais la valeur) ---
  let dernierePhoto = '';
  function texteSeul(n) {
    const c = n.cloneNode(true);
    c.querySelectorAll('select, option, input, textarea, button, script, style').forEach(x => x.remove());
    return court(c.textContent, 80);
  }
  function nomDuChamp(e) {
    if (idOk(e.id)) { const l = document.querySelector('label[for="' + e.id + '"]'); if (l) return texteSeul(l); }
    const p = e.closest('label'); if (p) return texteSeul(p);
    const al = e.getAttribute('aria-label'); if (al) return court(al, 80);
    const th = e.closest('th'); if (th) return texteSeul(th);
    const prev = e.previousElementSibling;
    if (prev && ['LABEL','SPAN','TD','TH','DIV','B','STRONG'].includes(prev.tagName)) {
      const t = texteSeul(prev); if (t.length < 60) return t;
    }
    return '';
  }
  const visible = (e) => {
    const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0;
  };
  function photo() {
    if (window !== window.top) return;
    const champs = [];
    for (const e of document.querySelectorAll('input, select, textarea')) {
      if (champs.length >= 80) break;
      const type = (e.getAttribute('type') || '').toLowerCase();
      if (type === 'hidden' || ['submit', 'button', 'reset', 'image'].includes(type) || !visible(e)) continue;
      // champs d'une ligne de tableau ou de liste, de l'en-tête : des données, pas le formulaire
      if (e.closest('tbody tr, [role=row], [role=grid], [role=listbox], li, header, nav, [role=banner]')) continue;
      const tag = e.tagName.toLowerCase();
      const rempli = (type === 'checkbox' || type === 'radio') ? e.checked : !!String(e.value || '').trim();
      champs.push({ libelle: nomDuChamp(e), type: tag === 'select' ? 'liste' : (tag === 'textarea' ? 'texte long' : (type || 'text')),
                    obligatoire: !!e.required, lecture_seule: !!(e.readOnly || e.disabled), rempli: rempli });
    }
    const boutons = [];
    for (const b of document.querySelectorAll('button, input[type=submit], input[type=button], [role=button]')) {
      if (boutons.length >= 30) break;
      if (surBadge(b) || !visible(b)) continue;
      // lignes, listes, en-tête (nom de l'utilisateur), listes déroulantes (qui affichent le choix fait)
      if (b.closest('tbody tr, [role=row], [role=grid], [role=listbox], li, header, nav, [role=banner]')) continue;
      if (b.hasAttribute('aria-haspopup') || b.hasAttribute('aria-expanded')) continue;
      const t = court(b.tagName === 'INPUT' ? b.value : (b.getAttribute('aria-label') || b.innerText), 40);
      if (t && !boutons.includes(t)) boutons.push(t);
    }
    const d = { champs: champs, boutons: boutons };
    const texte = JSON.stringify(d);
    if (texte === dernierePhoto) return;
    dernierePhoto = texte;
    d.type_evenement = 'ecran';
    envoyer(d);
  }
  setTimeout(() => { try { photo(); } catch (err) {} }, 800);

  function surClic(ev) {
    // isTrusted : uniquement les vrais clics. Les pages qui fabriquent un lien
    // invisible pour declencher un telechargement emettent un clic factice.
    if (!ev.isTrusted || surBadge(ev.target)) return;
    if (ev.type === 'auxclick' && ev.button !== 1) return;   // seul le clic molette compte
    viderEnAttente();   // ce qui vient d'etre tape doit etre note AVANT le clic
    try { photo(); } catch (err) {}   // l'ecran tel qu'il est au moment du clic (champs remplis ou non)
    const e = cible(ev.target);
    if (!e) return;
    const d = decrire(e);
    d.type_evenement = 'clic';
    d.ctrl = !!(ev.ctrlKey || ev.metaKey);   // Ctrl+clic : ouvre souvent un nouvel onglet
    d.maj = !!ev.shiftKey;
    d.bouton = ev.button || 0;
    envoyer(d);
  }
  document.addEventListener('click', surClic, true);
  document.addEventListener('auxclick', surClic, true);

  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' || !ev.isTrusted) return;
    const e = ev.target;
    if (!e || e.nodeType !== 1 || surBadge(e)) return;
    if (!estChampSaisie(e)) return;   // Entrée sur un bouton ou un lien : le navigateur envoie déjà un clic
    viderEnAttente();   // la valeur tapee doit precéder la touche Entree
    const d = decrire(e);
    d.type_evenement = 'touche';
    d.touche = 'Enter';
    envoyer(d);
  }, true);

  window.addEventListener('beforeunload', viderEnAttente, true);
}
"""


@dataclass
class Evenement:
    type: str
    donnees: Dict[str, Any]
    cadre: str = ""  # sélecteur de l'iframe, vide si page principale
    frame: Any = None  # objet Playwright, résolu en fin d'enregistrement seulement
    page: Any = None  # onglet d'où vient l'événement (simple référence, aucun appel Playwright)
    onglet: int = 0  # 0 = premier onglet utilisé, 1 = le suivant...


PREFIXES_NAVIGATEUR = ("chrome://", "chrome-extension://", "chrome-search://", "chrome-untrusted://",
                       "edge://", "about:")
MOTIF_HOTE_GOOGLE = re.compile(r"(?:www\.|consent\.)?google\.[a-z.]{2,6}", re.IGNORECASE)


def est_hors_tache(url: str, url_depart: str = "") -> bool:
    """Vrai pour une page du navigateur ou de Google (accueil, recherche, cookies), où
    l'utilisateur a pu cliquer pendant l'enregistrement sans que cela fasse partie de la tâche."""
    if not url:
        return False
    if est_onglet_parasite(url) or url.lower().startswith(PREFIXES_NAVIGATEUR):
        return True
    try:
        morceaux = urlsplit(url)
        hote_depart = urlsplit(url_depart).hostname or ""
    except ValueError:
        return False
    hote = morceaux.hostname or ""
    if MOTIF_HOTE_GOOGLE.fullmatch(hote_depart):
        return False  # l'outil est lui-même chez Google : on ne filtre rien
    if hote.lower().startswith("consent.") and MOTIF_HOTE_GOOGLE.fullmatch(hote):
        return True
    return bool(MOTIF_HOTE_GOOGLE.fullmatch(hote)) and morceaux.path.rstrip("/") in ("", "/search", "/webhp", "/url")


@dataclass
class EtapeEnregistree:
    """Une étape déduite de l'enregistrement, avant transformation en scénario."""

    action: str
    args: Dict[str, Any] = field(default_factory=dict)
    libelle: str = ""
    cadre: str = ""
    valeur_brute: Optional[str] = None  # valeur saisie, pour la question « quelle colonne ? »
    texte_selecteur: Optional[str] = None  # texte figé dans le sélecteur (role=link:XXX)
    type_champ: str = ""  # text, password, checkbox... pour traiter les mots de passe à part
    ecran: Optional[Dict[str, Any]] = None  # photo de l'écran au moment du geste (structure seule)

    def resume(self) -> str:
        libelle = self.libelle or self.args.get("selecteur") or ""
        if self.action == "aller":
            return f"ouvrir {self.args.get('url', '')}"
        if self.action == "attendre":
            return "attendre le chargement de la page"
        if self.action == "onglet":
            return f"passer à l'onglet {self.args.get('index')}"
        if self.action == "cliquer":
            return f"cliquer sur {libelle}" + (" (ouvre un nouvel onglet)" if self.args.get("nouvel_onglet") else "")
        if self.action == "choisir":
            return f"choisir « {self.args.get('valeur')} » dans {libelle}"
        if self.action == "cocher":
            return f"{'cocher' if self.args.get('valeur') == 'oui' else 'décocher'} {libelle}"
        if self.action == "remplir":
            valeur = "•••••" if self.type_champ == "password" else self.args.get("valeur")
            return f"écrire « {valeur} » dans {libelle}"
        if self.action == "touche":
            return f"appuyer sur {self.args.get('touche')}"
        if self.action == "telecharger":
            return f"télécharger le fichier obtenu en cliquant sur {self.libelle or self.args.get('cliquer')}"
        return self.action


class Enregistreur:
    """Session d'enregistrement : demarrer() ... puis arreter() renvoie les étapes."""

    def __init__(self, navigateur: Navigateur) -> None:
        self.nav = navigateur
        self.evenements: List[Evenement] = []
        self._cadres: Dict[Any, str] = {}
        self._pages_suivies: List[Page] = []
        self._actif = False
        self.url_depart = ""
        self.ignorees = 0  # actions faites hors de l'outil (page Google, onglet de Chrome)

    # ------------------------------------------------------------------ session
    def demarrer(self, url: Optional[str] = None) -> Page:
        contexte = self.nav.contexte
        if contexte is None:
            raise RuntimeError("le navigateur doit être ouvert avant d'enregistrer")
        contexte.expose_binding("autowebEvenement", self._recevoir)
        contexte.add_init_script(f"({JS_ENREGISTREUR})({json.dumps(CLIQUABLES)})")
        # « download » est un événement de page : il faut l'écouter sur chaque onglet,
        # y compris ceux qui s'ouvriront pendant l'enregistrement.
        for page_ouverte in contexte.pages:
            self._suivre_page(page_ouverte, initiale=True)
        contexte.on("page", self._suivre_page)
        self._actif = True
        page = self.nav.page_courante()
        self.url_depart = url or ""
        if url:
            page.goto(url)
        else:
            self._injecter(page)
        if self.nav.visible:
            self.nav.utiliser_page(page)  # l'onglet du robot devant, pas un onglet de Chrome
        # Page de départ notée ici, et non par le script injecté : celui-ci peut être
        # servi quelques dizaines de millisecondes plus tard, après les premières actions.
        self.evenements.insert(0, Evenement("page", {"url": url or page.url, "titre": ""}))
        return page

    def _suivre_page(self, page: Page, initiale: bool = False) -> None:
        if page in self._pages_suivies:
            return
        self._pages_suivies.append(page)
        if not initiale and self._actif:
            # l'onglet apparaît juste après le clic qui l'a ouvert : c'est ce clic qui sera rejoué
            # en « nouvel onglet » (même si l'utilisateur tape vite, ou n'agit jamais dans l'onglet)
            self.evenements.append(Evenement("onglet_ouvert", {}, "", None, page))
        page.on("download", self._telechargement)
        # Un onglet ouvert par window.open ne rejoue pas toujours le script d'enregistrement
        # sur sa vraie page : on le réinjecte à chaque chargement (sans doublon, voir le script).
        page.on("domcontentloaded", self._injecter)

    def _injecter(self, page: Page) -> None:
        if not self._actif:
            return
        try:
            page.evaluate(f"({JS_ENREGISTREUR})({json.dumps(CLIQUABLES)})")
        except Exception:  # noqa: BLE001 - page fermée ou en cours de navigation
            pass

    def _recevoir(self, source: Dict[str, Any], charge: str) -> None:
        """Appelé par Playwright depuis sa propre boucle : AUCUN appel Playwright ici,
        sinon le programme se bloque définitivement (l'iframe suffirait à tout figer)."""
        if not self._actif:
            return
        try:
            donnees = json.loads(charge)
        except (TypeError, ValueError):
            return
        type_evenement = donnees.pop("type_evenement", "")
        if not type_evenement:
            return
        if type_evenement == "fin":
            self._actif = False
            return
        if type_evenement not in ("clic", "saisie", "touche", "ecran"):
            return
        frame = source.get("frame") if source else None
        page = source.get("page") if source else None
        self.evenements.append(Evenement(type_evenement, donnees, "", frame, page))

    def _telechargement(self, telechargement: Any) -> None:
        if not self._actif:
            return
        try:
            nom = telechargement.suggested_filename
        except Exception:
            nom = ""
        self.evenements.append(Evenement("telechargement", {"nom": nom}))
        try:  # on ne garde pas le fichier : l'enregistrement sert à écrire le scénario
            telechargement.cancel()
        except Exception:
            pass

    # ------------------------------------------------------------------ iframes
    def _selecteur_cadre(self, frame: Any) -> str:
        """À n'appeler QUE depuis le fil principal (jamais depuis _recevoir)."""
        if frame is None:
            return ""
        if frame in self._cadres:
            return self._cadres[frame]
        selecteur = ""
        try:
            page = frame.page  # l'onglet de l'événement, pas forcément l'onglet courant
            if frame is page.main_frame:
                selecteur = ""
            elif frame.parent_frame is not page.main_frame:
                selecteur = ""  # iframe dans une iframe : un seul niveau est géré
            else:
                selecteur = frame.frame_element().evaluate(JS_SELECTEUR_IFRAME) or ""
        except Exception:
            selecteur = ""
        self._cadres[frame] = selecteur
        return selecteur

    @property
    def actif(self) -> bool:
        return self._actif

    @property
    def nb_actions(self) -> int:
        return sum(1 for e in self.evenements if e.type in ("clic", "saisie", "touche"))

    def attendre_fin(self, duree_max_ms: int = 3600000) -> None:
        """Laisse l'utilisateur travailler dans le navigateur ; revient quand il a
        cliqué sur le bandeau, tapé Entrée dans le terminal, ou fermé le navigateur."""
        from .console import touche_entree_disponible

        ecoule = 0
        while self._actif and ecoule < duree_max_ms:
            try:
                self.nav.page_courante().wait_for_timeout(300)
            except Exception:  # navigateur ou onglet fermé : l'enregistrement s'arrête
                break
            ecoule += 300
            if ecoule % 1500 == 0:
                for page in list(self._pages_suivies):
                    if not page.is_closed():
                        self._injecter(page)  # sans effet si déjà présent
            if touche_entree_disponible():
                break
        self._actif = False

    def _hors_tache(self, evenement: Evenement) -> bool:
        if evenement.type not in ("clic", "saisie", "touche", "ecran"):
            return False  # page de départ, téléchargement : notés par le robot lui-même
        d = evenement.donnees
        url, url_page = str(d.pop("url", "") or ""), str(d.pop("url_page", "") or "")
        if evenement.page is not None and evenement.page in getattr(self.nav, "parasites", []):
            return True
        if url_page:
            return est_hors_tache(url_page, self.url_depart)
        # iframe d'une autre origine : seule son adresse est connue
        return est_onglet_parasite(url)

    def arreter(self) -> List[EtapeEnregistree]:
        self._actif = False
        gardes: List[Evenement] = []
        for evenement in self.evenements:
            if evenement.type == "onglet_ouvert" and evenement.page in getattr(self.nav, "parasites", []):
                continue  # onglet ouvert par Chrome lui-même, refermé par le robot
            if self._hors_tache(evenement):
                if evenement.type != "ecran":
                    self.ignorees += 1
                continue
            gardes.append(evenement)
        if self.ignorees:
            journal.info("%d action(s) faite(s) sur une page Google ou du navigateur : ignorée(s).", self.ignorees)
        self.evenements = gardes
        ordre: List[Any] = []  # onglets dans l'ordre où l'utilisateur s'en est servi
        for evenement in self.evenements:
            if evenement.page is not None and evenement.type in ("clic", "saisie", "touche", "ecran", "onglet_ouvert"):
                if evenement.page not in ordre:
                    ordre.append(evenement.page)
                evenement.onglet = ordre.index(evenement.page)
        for evenement in self.evenements:  # résolution des iframes, hors boucle Playwright
            if evenement.frame is not None:
                evenement.cadre = self._selecteur_cadre(evenement.frame)
                evenement.frame = None
            evenement.page = None
        for page in self._pages_suivies:
            for evenement, fonction in (("download", self._telechargement), ("domcontentloaded", self._injecter)):
                try:
                    page.remove_listener(evenement, fonction)
                except Exception:
                    pass
        self._pages_suivies = []
        return construire_etapes(self.evenements)


# ---------------------------------------------------------------------- traduction
MOTIF_HAS_TEXT = re.compile(r':has-text\("((?:[^"\\]|\\.)*)"\)')


def _texte_du_selecteur(selecteur: str) -> Optional[str]:
    """Texte figé dans le sélecteur, qui vient peut-être d'une colonne de l'Excel."""
    for prefixe in ("role=button:", "role=link:", "texte=", "texte_exact="):
        if selecteur.startswith(prefixe):
            return selecteur[len(prefixe):]
    m = MOTIF_HAS_TEXT.search(selecteur)
    if m:
        return m.group(1).replace('\\"', '"').replace("\\\\", "\\")
    return None


def remplacer_texte_selecteur(selecteur: str, ancien: str, nouveau: str) -> str:
    """Remplace le texte repéré par _texte_du_selecteur, et lui seul."""
    for prefixe in ("role=button:", "role=link:", "texte=", "texte_exact="):
        if selecteur.startswith(prefixe) and selecteur[len(prefixe):] == ancien:
            return prefixe + nouveau
    m = MOTIF_HAS_TEXT.search(selecteur)
    if m:
        echappe = nouveau.replace("\\", "\\\\").replace('"', '\\"')
        return selecteur[:m.start()] + f':has-text("{echappe}")' + selecteur[m.end():]
    return selecteur


CELLULES = ":is(td,th,a,[role=cell],[role=gridcell])"


def ancrer_exactement(selecteur: str, ancien: str, gabarit: str) -> str:
    """Remplace le texte figé par une valeur qui change (« {{plan}} »), en exigeant une
    cellule dont le texte est EXACTEMENT cette valeur : PL-1 ne désigne jamais la ligne PL-10."""
    for prefixe, exact in (("role=button:", "role=button:"), ("role=link:", "role=link:"),
                           ("texte=", "texte_exact="), ("texte_exact=", "texte_exact=")):
        if selecteur.startswith(prefixe) and selecteur[len(prefixe):] == ancien:
            return exact + re.sub(r"\s*\|\s*echapper\s*(?=\}\})", "", gabarit)
    m = MOTIF_HAS_TEXT.search(selecteur)
    if m and m.group(1).replace('\\"', '"').replace("\\\\", "\\") == ancien:
        return selecteur[:m.start()] + f':has({CELLULES}:text-is("{gabarit}"))' + selecteur[m.end():]
    return remplacer_texte_selecteur(selecteur, ancien, gabarit)


def construire_etapes(evenements: List[Evenement], url_depart: str = "") -> List[EtapeEnregistree]:
    """Transforme les événements bruts en étapes propres (fusion, nettoyage)."""
    etapes: List[EtapeEnregistree] = []
    derniere_url: Optional[str] = None
    ecran: Optional[Dict[str, Any]] = None
    onglet_courant, onglet_max = 0, 0
    for ev in evenements:
        d = ev.donnees
        if ev.type == "ecran":
            ecran = {"champs": d.get("champs") or [], "boutons": d.get("boutons") or []}
            continue
        if ev.type == "onglet_ouvert":
            gestes = [e for e in etapes if e.action != "attendre"]
            if ev.onglet > onglet_max and gestes and gestes[-1].action == "cliquer":
                gestes[-1].args["nouvel_onglet"] = True
                onglet_courant, onglet_max = ev.onglet, ev.onglet
            continue
        if ev.type in ("clic", "saisie", "touche") and ev.onglet != onglet_courant:
            gestes = [e for e in etapes if e.action != "attendre"]
            if ev.onglet > onglet_max and gestes and gestes[-1].action == "cliquer":
                gestes[-1].args["nouvel_onglet"] = True  # ce clic a ouvert l'onglet où l'on continue
            else:
                etapes.append(EtapeEnregistree("onglet", {"index": ev.onglet + 1}))
            onglet_courant, onglet_max = ev.onglet, max(onglet_max, ev.onglet)
        nb_avant = len(etapes)
        _traduire(ev, d, etapes, derniere_url)
        if ev.type == "page":
            derniere_url = str(d.get("url", "")) or derniere_url
        for etape in etapes[nb_avant:]:
            etape.ecran = ecran
    while etapes and etapes[-1].action == "attendre":
        etapes.pop()
    if etapes and etapes[0].action != "aller":
        depart = url_depart or (derniere_url or "")
        if depart:
            etapes.insert(0, EtapeEnregistree("aller", {"url": depart}))
    return etapes


def _traduire(ev: Evenement, d: Dict[str, Any], etapes: List[EtapeEnregistree], derniere_url: Optional[str]) -> None:
    """Ajoute à `etapes` ce que produit un événement (rien, une étape, ou une fusion)."""
    if ev.type == "page":
        url = str(d.get("url", ""))
        if url and url == derniere_url:
            return  # même page : le script injecté l'annonce une seconde fois
        derniere_url = url
        if not etapes:
            etapes.append(EtapeEnregistree("aller", {"url": url}, libelle=str(d.get("titre", ""))))
        elif etapes[-1].action != "attendre":
            etapes.append(EtapeEnregistree("attendre", {"chargement": "reseau", "delai": 8000}))
        return
    if ev.type == "telechargement":
        for etape in reversed(etapes):
            if etape.action == "cliquer":
                etape.action = "telecharger"
                etape.args = {"cliquer": etape.args["selecteur"], "nom_propose": d.get("nom", "")}
                break
        return

    selecteur = str(d.get("selecteur") or "")
    if not selecteur:
        return
    libelle = str(d.get("libelle") or d.get("texte") or "")
    tag = str(d.get("tag") or "")
    type_champ = str(d.get("type") or "")

    if ev.type == "clic":
        if tag in ("input", "textarea", "select") and type_champ not in ("checkbox", "radio", "submit", "button", "reset"):
            return  # simple clic dans un champ : la saisie suffit
        args_clic: Dict[str, Any] = {"selecteur": selecteur}
        if d.get("ctrl"):
            args_clic["ctrl"] = True
        if d.get("maj"):
            args_clic["maj"] = True
        if d.get("bouton") == 1:
            args_clic["bouton"] = "middle"
        etapes.append(EtapeEnregistree(
            "cliquer", args_clic, libelle=libelle, cadre=ev.cadre,
            texte_selecteur=_texte_du_selecteur(selecteur),
        ))
    elif ev.type == "saisie":
        valeur = "" if d.get("valeur") is None else str(d["valeur"])
        if tag == "select":
            action = "choisir"
            args = {"selecteur": selecteur, "valeur": valeur or str(d.get("libelle_valeur") or "")}
        elif type_champ in ("checkbox", "radio"):
            action, args = "cocher", {"selecteur": selecteur, "valeur": valeur}
        else:
            action, args = "remplir", {"selecteur": selecteur, "valeur": valeur}
        # On ne fusionne qu'avec la saisie qui précède IMMÉDIATEMENT sur le même
        # champ (l'utilisateur corrige ce qu'il vient de taper). Deux champs
        # éloignés qui partagent un sélecteur restent deux étapes distinctes.
        precedente = etapes[-1] if etapes else None
        if (precedente is not None and precedente.action in ("remplir", "choisir", "cocher")
                and precedente.args.get("selecteur") == selecteur and precedente.cadre == ev.cadre):
            precedente.action = action
            precedente.args = args
            precedente.valeur_brute = args.get("valeur")
            precedente.type_champ = type_champ
        else:
            etapes.append(EtapeEnregistree(action, args, libelle=libelle, cadre=ev.cadre,
                                           valeur_brute=args.get("valeur"), type_champ=type_champ))
    elif ev.type == "touche" and str(d.get("touche") or "") == "Enter":
        etapes.append(EtapeEnregistree("touche", {"selecteur": selecteur, "touche": "Enter"},
                                       libelle=libelle, cadre=ev.cadre))
