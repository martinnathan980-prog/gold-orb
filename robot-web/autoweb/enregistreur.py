"""Enregistreur : le robot regarde l'utilisateur faire la tâche une fois, et note
chaque clic, chaque saisie, chaque changement de page.

Principe : un petit script est injecté dans chaque page du navigateur piloté. Il
écoute les clics, les saisies et les touches, et renvoie à Python un événement par
action, avec un sélecteur stable pour l'élément concerné. Rien n'est envoyé ailleurs :
tout reste sur le poste.

Le résultat est une liste d'étapes (mêmes actions que les scénarios écrits à la main),
que l'assistant transforme ensuite en scénario YAML en demandant d'où viennent les
valeurs (quelle colonne de l'Excel).
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from playwright.sync_api import Error as PlaywrightError, Page

from .navigateur import Navigateur
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
  if (window.__autoweb_enregistre) return;
  window.__autoweb_enregistre = true;
  const attente = [];
  let compteur = 0;
  function envoyer(e) {
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

  // Bandeau rouge : il reste affiché pendant tout l'enregistrement et sert à l'arrêter.
  const ID_BADGE = '__autoweb_badge';
  function majBadge() {
    const b = document.getElementById(ID_BADGE);
    if (b && !b.dataset.fini)
      b.textContent = compteur ? ('Enregistrement : ' + compteur + ' action(s) - cliquez ici pour terminer')
                               : 'Enregistrement en cours - cliquez ici pour terminer';
  }
  function badge() {
    if (document.getElementById(ID_BADGE) || !document.documentElement) return;
    const b = document.createElement('div');
    b.id = ID_BADGE;
    b.setAttribute('style', 'position:fixed;top:10px;right:10px;z-index:2147483647;background:#dc2626;' +
      'color:#fff;font:600 13px/1.3 system-ui,-apple-system,Arial;padding:9px 13px;border-radius:6px;' +
      'box-shadow:0 2px 10px rgba(0,0,0,.35);cursor:pointer;user-select:none;max-width:320px');
    b.textContent = 'Enregistrement en cours - cliquez ici pour terminer';
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
  const court = (s, n) => (s || '').replace(/\\s+/g, ' ').trim().slice(0, n || 60);
  const idOk = (id) => !!id && /^[A-Za-z_][\\w-]*$/.test(id) && !/\\d{4,}/.test(id) && id.length <= 40;

  function libelleDe(e) {
    if (idOk(e.id)) {
      const l = document.querySelector('label[for="' + e.id + '"]');
      if (l && l.innerText) return court(l.innerText, 80);
    }
    const p = e.closest('label');
    if (p && p.innerText) return court(p.innerText, 80);
    const al = e.getAttribute('aria-label');
    if (al) return court(al, 80);
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = document.getElementById(lb.split(' ')[0]); if (t) return court(t.innerText, 80); }
    const prev = e.previousElementSibling;
    if (prev && ['LABEL','SPAN','TD','TH','DIV'].includes(prev.tagName) && court(prev.innerText, 61).length < 60)
      return court(prev.innerText, 80);
    return '';
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

  function selecteurDe(e) {
    const tid = e.getAttribute('data-testid') || e.getAttribute('data-test') || e.getAttribute('data-qa');
    if (tid) return 'test=' + tid;
    if (idOk(e.id)) return '#' + e.id;
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || '').toLowerCase();
    const nom = e.getAttribute('name');
    if (nom) {
      if (tag === 'input' && (type === 'radio' || type === 'checkbox') && e.value)
        return tag + '[name="' + nom + '"][value="' + e.value + '"]';
      return tag + '[name="' + nom + '"]';
    }
    const role = e.getAttribute('role') || '';
    const estBouton = tag === 'button' || role === 'button' || (tag === 'input' && ['submit','button','reset'].includes(type));
    const texte = court(e.innerText || e.value || e.getAttribute('title') || '', 60);
    if (estBouton && texte) return 'role=button:' + texte;
    if ((tag === 'a' || role === 'link') && texte) return 'role=link:' + texte;
    const lib = libelleDe(e);
    if (lib && ['input','select','textarea'].includes(tag)) return 'libelle=' + lib;
    const ph = e.getAttribute('placeholder');
    if (ph) return 'placeholder=' + ph;
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
    return {
      selecteur: selecteurDe(e),
      tag: e.tagName.toLowerCase(),
      type: (e.getAttribute('type') || '').toLowerCase(),
      libelle: libelleDe(e) || court(e.innerText || e.getAttribute('title') || '', 60),
      texte: court(e.innerText || e.value || '', 60)
    };
  }

  document.addEventListener('click', (ev) => {
    // isTrusted : uniquement les vrais clics. Les pages qui fabriquent un lien
    // invisible pour declencher un telechargement emettent un clic factice.
    if (!ev.isTrusted || surBadge(ev.target)) return;
    const e = cible(ev.target);
    if (!e) return;
    const d = decrire(e);
    d.type_evenement = 'clic';
    d.bouton_droit = false;
    envoyer(d);
  }, true);

  document.addEventListener('change', (ev) => {
    const e = ev.target;
    if (!e || e.nodeType !== 1 || surBadge(e)) return;
    const tag = e.tagName.toLowerCase();
    if (!['input','select','textarea'].includes(tag) && !e.isContentEditable) return;
    const d = decrire(e);
    d.type_evenement = 'saisie';
    if (tag === 'select') {
      const opt = e.options[e.selectedIndex];
      d.valeur = e.value;
      d.libelle_valeur = opt ? court(opt.text, 80) : '';
    } else if (d.type === 'checkbox' || d.type === 'radio') {
      d.valeur = e.checked ? 'oui' : 'non';
    } else {
      d.valeur = e.value !== undefined ? String(e.value) : court(e.innerText, 200);
    }
    envoyer(d);
  }, true);

  document.addEventListener('keydown', (ev) => {
    if (ev.key !== 'Enter' && ev.key !== 'Tab' && ev.key !== 'Escape') return;
    const e = ev.target;
    if (!e || e.nodeType !== 1) return;
    if (ev.key === 'Tab') return;
    const d = decrire(e);
    d.type_evenement = 'touche';
    d.touche = ev.key;
    envoyer(d);
  }, true);

  envoyer({ type_evenement: 'page', url: location.href, titre: document.title });
}
"""


@dataclass
class Evenement:
    type: str
    donnees: Dict[str, Any]
    cadre: str = ""  # sélecteur de l'iframe, vide si page principale


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

    def resume(self) -> str:
        if self.action == "aller":
            return f"ouvrir {self.args.get('url', '')}"
        if self.action == "attendre":
            return "attendre le chargement de la page"
        if self.action == "cliquer":
            return f"cliquer sur {self.libelle or self.args.get('selecteur')}"
        if self.action == "choisir":
            return f"choisir « {self.args.get('valeur')} » dans {self.libelle or self.args.get('selecteur')}"
        if self.action == "cocher":
            return f"{'cocher' if self.args.get('valeur') == 'oui' else 'décocher'} {self.libelle or self.args.get('selecteur')}"
        if self.action == "remplir":
            valeur = "•••••" if self.type_champ == "password" else self.args.get("valeur")
            return f"écrire « {valeur} » dans {self.libelle or self.args.get('selecteur')}"
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
            self._suivre_page(page_ouverte)
        contexte.on("page", self._suivre_page)
        self._actif = True
        page = self.nav.page_courante()
        if url:
            page.goto(url)
        else:
            self._injecter(page)
        return page

    def _suivre_page(self, page: Page) -> None:
        if page in self._pages_suivies:
            return
        self._pages_suivies.append(page)
        page.on("download", self._telechargement)

    def _injecter(self, page: Page) -> None:
        try:
            page.evaluate(f"({JS_ENREGISTREUR})({json.dumps(CLIQUABLES)})")
        except PlaywrightError:
            pass

    def _selecteur_cadre(self, frame: Any) -> str:
        if frame in self._cadres:
            return self._cadres[frame]
        selecteur = ""
        try:
            page = self.nav.page_courante()
            if frame is not page.main_frame:
                selecteur = frame.frame_element().evaluate(JS_SELECTEUR_IFRAME) or ""
        except Exception:
            selecteur = ""
        self._cadres[frame] = selecteur
        return selecteur

    def _recevoir(self, source: Dict[str, Any], charge: str) -> None:
        if not self._actif:
            return
        try:
            donnees = json.loads(charge)
        except (TypeError, ValueError):
            return
        cadre = self._selecteur_cadre(source.get("frame")) if source else ""
        type_evenement = donnees.pop("type_evenement", "")
        if not type_evenement:
            return
        if type_evenement == "fin":
            self._actif = False
            return
        self.evenements.append(Evenement(type_evenement, donnees, cadre))
        journal.debug("enregistré : %s %s", type_evenement, donnees.get("selecteur", donnees.get("url", "")))

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

    @property
    def actif(self) -> bool:
        return self._actif

    @property
    def nb_actions(self) -> int:
        return sum(1 for e in self.evenements if e.type in ("clic", "saisie", "touche"))

    def attendre_fin(self, duree_max_ms: int = 3600000) -> None:
        """Laisse l'utilisateur travailler dans le navigateur ; revient quand il a
        cliqué sur le bandeau « terminer » ou fermé le navigateur."""
        ecoule = 0
        while self._actif and ecoule < duree_max_ms:
            try:
                self.nav.page_courante().wait_for_timeout(300)
            except Exception:  # navigateur ou onglet fermé : l'enregistrement s'arrête
                break
            ecoule += 300
        self._actif = False

    def arreter(self) -> List[EtapeEnregistree]:
        self._actif = False
        for page in self._pages_suivies:
            try:
                page.remove_listener("download", self._telechargement)
            except Exception:
                pass
        self._pages_suivies = []
        return construire_etapes(self.evenements)


# ---------------------------------------------------------------------- traduction
def _texte_du_selecteur(selecteur: str) -> Optional[str]:
    for prefixe in ("role=button:", "role=link:", "texte=", "texte_exact="):
        if selecteur.startswith(prefixe):
            return selecteur[len(prefixe):]
    return None


def construire_etapes(evenements: List[Evenement]) -> List[EtapeEnregistree]:
    """Transforme les événements bruts en étapes propres (fusion, nettoyage)."""
    etapes: List[EtapeEnregistree] = []
    premiere_page = True
    for i, ev in enumerate(evenements):
        d = ev.donnees
        if ev.type == "page":
            url = str(d.get("url", ""))
            if premiere_page:
                etapes.append(EtapeEnregistree("aller", {"url": url}, libelle=str(d.get("titre", ""))))
                premiere_page = False
            else:
                # une nouvelle page est apparue : on laisse le temps au chargement
                if not (etapes and etapes[-1].action == "attendre"):
                    etapes.append(EtapeEnregistree("attendre", {"chargement": "reseau", "delai": 8000}))
            continue
        if ev.type == "telechargement":
            # le clic précédent a déclenché un téléchargement
            for etape in reversed(etapes):
                if etape.action == "cliquer":
                    etape.action = "telecharger"
                    etape.args = {"cliquer": etape.args["selecteur"], "nom_propose": d.get("nom", "")}
                    break
            continue

        selecteur = str(d.get("selecteur") or "")
        if not selecteur:
            continue
        libelle = str(d.get("libelle") or d.get("texte") or "")
        tag = str(d.get("tag") or "")
        type_champ = str(d.get("type") or "")

        if ev.type == "clic":
            if tag in ("input", "textarea", "select") and type_champ not in ("checkbox", "radio", "submit", "button", "reset"):
                continue  # simple clic dans un champ : la saisie suffit
            etapes.append(EtapeEnregistree(
                "cliquer", {"selecteur": selecteur}, libelle=libelle, cadre=ev.cadre,
                texte_selecteur=_texte_du_selecteur(selecteur),
            ))
        elif ev.type == "saisie":
            valeur = "" if d.get("valeur") is None else str(d["valeur"])
            if tag == "select":
                action, args = "choisir", {"selecteur": selecteur, "valeur": valeur or str(d.get("libelle_valeur") or "")}
            elif type_champ in ("checkbox", "radio"):
                action, args = ("cocher", {"selecteur": selecteur, "valeur": valeur})
            else:
                action, args = "remplir", {"selecteur": selecteur, "valeur": valeur}
            # une nouvelle saisie sur le même champ remplace la précédente
            for etape in reversed(etapes):
                if etape.action in ("remplir", "choisir", "cocher") and etape.args.get("selecteur") == selecteur:
                    etape.args = args
                    etape.valeur_brute = args.get("valeur")
                    break
            else:
                etapes.append(EtapeEnregistree(action, args, libelle=libelle, cadre=ev.cadre,
                                               valeur_brute=args.get("valeur"), type_champ=type_champ))
        elif ev.type == "touche":
            touche = str(d.get("touche") or "")
            if touche == "Enter":
                etapes.append(EtapeEnregistree("touche", {"selecteur": selecteur, "touche": "Enter"},
                                               libelle=libelle, cadre=ev.cadre))
    # un « attendre » en toute fin n'apporte rien
    while etapes and etapes[-1].action == "attendre":
        etapes.pop()
    return etapes
