"""Explorateur : parcourt un portail web SANS RIEN MODIFIER et en dresse la carte.

Le robot part de la page d'accueil (l'utilisateur s'est connecté), puis suit les
liens et clique sur les éléments de navigation (menus, onglets, lignes de tableau,
boutons de consultation). Pour chaque écran rencontré, il note les champs, les
boutons, les tableaux, et comment on y arrive.

Sécurité, en couches indépendantes :
1. il ne remplit aucun champ, n'appuie sur aucune touche, ne coche rien ;
2. il ne clique que sur des éléments de navigation ou de consultation (liste
   d'autorisation), jamais sur un élément dont le texte évoque une action (liste
   d'interdiction), ni sur un symbole sans texte (×, icône), ni dans une fenêtre
   de confirmation, ni sur un bouton qui envoie un formulaire ;
3. la vérification et le clic ont lieu dans le MÊME instant, dans la page : si
   l'écran a changé entre-temps, rien n'est cliqué ; et le clic vise l'élément
   lui-même, jamais un point de l'écran (une case à cocher posée au milieu d'une
   ligne n'est pas touchée) ;
4. dans le navigateur, toute requête qui enverrait des données (POST, PUT,
   DELETE...), toute adresse qui ressemble à une action (…/supprimer,
   ?action=del...) et toute connexion WebSocket sont bloquées avant de partir ;
5. les confirmations reçoivent « Annuler », l'impression est neutralisée, les
   téléchargements annulés, les fenêtres ouvertes refermées.

Sur une grosse base, tout visiter serait infini : un ou deux exemples par modèle
d'écran suffisent (deux fiches composant, deux pages de liste...).

Résultats, dans explorations/<date>/ :
- carte.json et carte.html : tout ce qui a été vu (restent sur le poste) ;
- carte_a_partager.txt : la structure (écrans, noms des champs, colonnes, onglets,
  menus, boutons usuels), sans valeurs, sans adresses, sans titres de page.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import logging
import os
import re
import time
import unicodedata
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple
from urllib.parse import parse_qsl, urlsplit

from playwright.sync_api import Page

from . import symboles as S
from .erreurs import ErreurAutoweb
from .navigateur import Navigateur, navigateur_ferme

journal = logging.getLogger("autoweb")


# ---------------------------------------------------------------------- vocabulaire
def normaliser(texte: str) -> str:
    """minuscules, sans accents, espaces simples : « Créer un Plan » -> « creer un plan »."""
    texte = unicodedata.normalize("NFD", str(texte or ""))
    texte = "".join(c for c in texte if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", texte.lower()).strip()


# Débuts de mots qui évoquent une action : jamais cliqués. Un préfixe (re-, dé-, in-,
# un-...) est accepté devant : « renvoyer », « dévalider », « unpublish » sont interdits.
RADICAUX_INTERDITS = (
    "supprim", "suppr", "effac", "delete", "remove", "retir", "archiver", "valid", "enregistr", "enreg",
    "sauvegard", "save", "submit", "soumettre", "envoyer", "renvoyer", "renvoi", "send", "publier", "publish", "diffuser",
    "cree", "creer", "creat", "ajout", "add", "insert", "nouveau", "nouvelle", "new", "modif",
    "edit", "import", "upload", "joindre", "attach", "dupliqu", "copier", "clon", "deplac", "affecter",
    "attribuer", "assign", "approuv", "approve", "rejet", "reject", "refus", "signer", "sign in",
    "sign up", "signup", "confirm", "annul", "cancel", "initialis", "reset", "deconnex", "deconnect",
    "disconnect", "logout", "log out", "logoff", "sign out", "signout", "quitter", "fermer", "close",
    "imprim", "impression", "print", "export", "telecharg", "download", "verrou", "lock", "clotur",
    "clore", "terminer", "transfer", "commander", "achat", "acheter", "payer", "paiement", "payment",
    "vider", "purge", "restaur", "retablir", "activer", "activate", "enable", "disable", "mettre a jour",
    "mise a jour", "update", "generer", "generate", "generation", "lancer", "execut", "run", "demarrer",
    "start", "stop", "arreter", "notif", "partag", "share", "invit", "abonn", "subscri", "vote",
    "accepter", "accept", "decline", "renomm", "rename", "fusion", "merge", "calcul", "traiter", "sync",
    "reserver", "liberer", "bloquer", "debloquer", "reviser", "indicer", "detrui", "destroy",
    "erase", "discard", "revert", "rollback", "undo", "appliqu", "apply", "release", "promouv", "promot",
    "freeze", "geler", "figer", "check in", "check out", "checkin", "checkout", "extraire", "detach",
    "dissoci", "remplac", "marquer", "obsolet", "changer", "change", "corbeille", "trash", "favori",
    "suivre", "follow", "epingl", "noter", "commenter", "comment", "repondre", "reply", "transmet",
    "afficher en tant", "retourner", "rejouer", "relire", "planifier", "schedul", "demander",
)
MOTS_ENTIERS_INTERDITS = ("del", "rm", "ok", "oui", "yes", "go", "done", "maj", "x", "star", "like", "set",
                          "pin", "unpin", "archive")
MOTIF_INTERDIT = re.compile(
    r"(?<![a-z0-9])(?:re|de|des|in|un|dis|pre|auto)?(?:" + "|".join(re.escape(m) for m in RADICAUX_INTERDITS) + ")"
    r"|(?<![a-z0-9])(?:" + "|".join(re.escape(m) for m in MOTS_ENTIERS_INTERDITS) + r")(?![a-z0-9])"
)

# Premier mot d'un bouton de simple consultation : seul cas où un bouton ordinaire est cliqué.
PREMIERS_MOTS_LECTURE = {
    "rechercher", "recherche", "chercher", "search", "filtrer", "filter", "afficher", "voir", "view",
    "consulter", "detail", "details", "suivant", "next", "precedent", "previous", "prev", "page",
    "retour", "back", "accueil", "home", "apercu", "preview", "historique", "history", "trier", "sort",
    "developper", "deplier", "replier", "agrandir", "expand", "collapse", "plus",
}
# Valeurs d'un paramètre « action » qui restent de la consultation.
VALEURS_LECTURE = PREMIERS_MOTS_LECTURE | {"list", "liste", "show", "index", "display", "read", "get", "fiche"}
CLES_ACTION = {"action", "op", "operation", "cmd", "command", "do", "task"}

EXTENSIONS_FICHIERS = (
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".xlsm", ".csv", ".zip", ".7z", ".rar", ".txt",
    ".xml", ".json", ".dwg", ".dxf", ".png", ".jpg", ".jpeg", ".gif", ".tif", ".tiff", ".ppt", ".pptx",
)
METHODES_LECTURE = ("GET", "HEAD", "OPTIONS")
# Adresses où le serveur de connexion de l'entreprise (SSO) renvoie l'utilisateur pour ouvrir
# la session : ce retour se fait en POST, mais il ne modifie aucune donnée du portail.
MOTIF_RETOUR_CONNEXION = re.compile(
    r"/(?:saml2?/(?:acs|post|consume|sso)|acs|signin-oidc|signin-saml|signin-wsfed|shibboleth\.sso/saml2?/post"
    r"|oauth2?/callback|login/oauth2?/code(?:/[^/]*)?|auth/callback|openid/callback|_trust|adfs/ls)/?$",
    re.IGNORECASE,
)
# Ressources jamais bloquées pour leur adresse : feuilles de style, polices, scripts, médias.
RESSOURCES_STATIQUES = ("stylesheet", "font", "script", "media", "manifest", "texttrack")


def mot_interdit(*textes: str) -> Optional[str]:
    """Le mot qui interdit le clic, ou None."""
    for texte in textes:
        m = MOTIF_INTERDIT.search(normaliser(texte).replace("_", " "))
        if m:
            return m.group(0)
    return None


def est_lecture(texte: str) -> bool:
    """Vrai si le libellé COMMENCE par un mot de consultation (« Voir le détail »),
    jamais pour « Tout marquer comme lu » ou « Ouvrir un ticket »."""
    mots = re.findall(r"[a-z]+", normaliser(texte))
    return bool(mots) and mots[0] in PREMIERS_MOTS_LECTURE and mot_interdit(texte) is None


def a_des_lettres(texte: str) -> bool:
    return bool(re.search(r"[a-z]{2}", normaliser(texte)))


def decouper(url: str):
    try:
        return urlsplit(url or "")
    except ValueError:
        return None


def _segment_variable(segment: str) -> bool:
    return bool(re.search(r"\d", segment)) or len(segment) > 24


def modele_url(url: str) -> str:
    """Adresse sans le serveur ni les valeurs variables : /plans/1234?onglet=2&module=plans
    -> /plans/{id}?module=plans&onglet={}. Deux adresses qui ne diffèrent que par ces
    valeurs montrent le même modèle d'écran ; module=plans et module=composants, non."""
    m = decouper(url)
    if m is None:
        return ""
    if m.scheme not in ("http", "https", "file"):
        return f"{m.scheme}:"
    chemin = "/".join("{id}" if _segment_variable(s) else s for s in m.path.split("/"))
    paires = parse_qsl(m.query, keep_blank_values=True)
    requete = "&".join(sorted(f"{k}={'{}' if (not v or _segment_variable(v)) else v}" for k, v in paires))
    fragment = m.fragment
    if fragment:
        if "=" in fragment and not fragment.startswith("/"):
            fragment = "&".join(sorted(
                f"{k}={'{}' if (not v or _segment_variable(v)) else v}"
                for k, _, v in (p.partition("=") for p in fragment.split("&"))))
        else:
            fragment = "/".join("{id}" if _segment_variable(s) else s for s in fragment.split("/"))
    return chemin + (f"?{requete}" if requete else "") + (f"#{fragment}" if fragment else "")


def adresse_action(url: str) -> Optional[str]:
    """Raison pour laquelle une adresse ressemble à une action (…/supprimer, ?action=del), ou None."""
    m = decouper(url)
    if m is None:
        return "adresse illisible"
    mot = mot_interdit(re.sub(r"[/_.\-]+", " ", m.path))
    if mot:
        return f"« {mot} » dans l'adresse"
    for cle, valeur in parse_qsl(m.query, keep_blank_values=True):
        mot = mot_interdit(re.sub(r"[_.\-]+", " ", cle), re.sub(r"[_.\-]+", " ", valeur))
        if mot:
            return f"« {mot} » dans l'adresse"
        if normaliser(cle) in CLES_ACTION and valeur and normaliser(valeur) not in VALEURS_LECTURE:
            return f"paramètre « {cle}={valeur} »"
    return None


def sans_fragment(url: str) -> str:
    return (url or "").split("#", 1)[0]


def masquer(texte: str) -> str:
    """Tout mot contenant un chiffre, et les adresses mail, sont masqués."""
    texte = re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "<email>", str(texte or ""))
    return re.sub(r"\S*\d\S*", "#", texte)


TYPES_CHAMPS = {
    "text": "texte", "number": "nombre", "checkbox": "case à cocher", "radio": "choix unique",
    "password": "mot de passe", "search": "recherche", "file": "fichier", "email": "mail",
    "tel": "téléphone", "datetime-local": "date et heure", "month": "mois", "url": "adresse web",
}


def type_champ(type_brut: str) -> str:
    return TYPES_CHAMPS.get(type_brut, type_brut)


# ---------------------------------------------------------------------- lecture d'un écran
# Outils communs aux deux scripts : la description d'un élément doit être calculée
# EXACTEMENT de la même façon au moment de la lecture et au moment du clic.
JS_OUTILS = r"""
  const vis = e => {
    if (!e || !e.isConnected || !e.getBoundingClientRect) return false;
    const s = getComputedStyle(e);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = e.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const court = (s, n) => (s || '').replace(/\s+/g, ' ').trim().slice(0, n || 80);
  const idOk = id => !!id && /^[A-Za-z_][\w-]*$/.test(id) && !/\d{3,}/.test(id) && id.length <= 40;
  // texte d'un libellé ou d'une entête SANS les listes et champs qu'il contient (options = données)
  const texteSeul = n => {
    const c = n.cloneNode(true);
    c.querySelectorAll('select, option, optgroup, datalist, input, textarea, button, script, style').forEach(x => x.remove());
    return court(c.textContent, 80);
  };
  const libelle = e => {
    if (idOk(e.id)) {
      try { const l = document.querySelector('label[for="' + CSS.escape(e.id) + '"]'); if (l) return [texteSeul(l), 'label']; } catch (err) {}
    }
    const p = e.closest('label'); if (p) return [texteSeul(p), 'label'];
    const al = e.getAttribute('aria-label'); if (al) return [court(al), 'aria'];
    const lb = e.getAttribute('aria-labelledby');
    if (lb) { const t = document.getElementById(lb.split(' ')[0]); if (t) return [texteSeul(t), 'aria']; }
    const th = e.closest('th'); if (th) return [texteSeul(th), 'entete'];
    const prev = e.previousElementSibling;
    if (prev && ['LABEL', 'SPAN', 'TD', 'TH', 'DIV', 'B', 'STRONG'].includes(prev.tagName)) {
      const t = texteSeul(prev); if (t.length < 60) return [t, 'voisin'];
    }
    const ph = e.getAttribute('placeholder'); if (ph) return [court(ph), 'exemple'];
    return ['', ''];
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
  const FENETRE = '[role=dialog], [role=alertdialog], dialog[open], [aria-modal=true], .modal, .modal-dialog, ' +
                  '.swal2-popup, .ui-dialog, .popup, .popin, .lightbox, .blockUI';
  const dansFenetre = e => {
    if (e.closest(FENETRE)) return true;
    // voile maison : un ancêtre fixe qui couvre une grande partie de l'écran
    for (let n = e.parentElement; n && n !== document.body; n = n.parentElement) {
      const s = getComputedStyle(n);
      if (s.position === 'fixed') {
        const r = n.getBoundingClientRect();
        if (r.width * r.height > 0.3 * innerWidth * innerHeight) return true;
      }
    }
    return false;
  };
  // arborescence et fil d'Ariane : souvent des données (dossiers, projets) ; menu latéral : navigation
  const ARBRE = '[role=tree], .tree, .breadcrumb, [aria-label*=readcrumb], [aria-label*="Fil d"]';
  const LATERAL = 'aside, .sidebar, .side-bar, .sidenav, .side-nav';
  const zone = e => {
    if (dansFenetre(e)) return 'fenetre';
    if (e.getAttribute('role') === 'tab' || e.closest('[role=tablist]')) return 'onglet';
    if (e.closest('tbody tr, [role=row]')) return 'tableau';
    if (e.closest(ARBRE) || e.getAttribute('role') === 'treeitem') return 'arbre';
    if (e.closest(LATERAL)) return 'lateral';
    if (e.closest('nav, [role=navigation], [role=menu], [role=menubar], header, .menu, .navbar, .nav')) return 'menu';
    return 'page';
  };
  const conteneurDe = (e, z) => {
    if (z === 'tableau') return e.closest('tbody, [role=rowgroup], table, [role=grid], [role=table]') || e.parentElement;
    if (z === 'arbre') return e.closest(ARBRE) || e.parentElement;
    if (z === 'lateral') return e.closest(LATERAL) || e.parentElement;
    return null;
  };
  const SELECTION = 'a[href], button, input[type=submit], input[type=button], input[type=image], input[type=reset], ' +
                    '[role=button], [role=tab], [role=menuitem], [role=link], [role=treeitem], [onclick], summary';
  const EXCLUS = 'input:not([type=submit]):not([type=button]):not([type=image]):not([type=reset]), select, option, ' +
                 'textarea, label, [role=checkbox], [role=radio], [role=switch], [role=option], [contenteditable=true]';
  const cache = new Map();
  const indexes = new Map();
  const indexLigne = tr => {
    const parent = tr.parentElement;
    if (!parent) return -1;
    let m = indexes.get(parent);
    if (!m) { m = new Map(); Array.prototype.forEach.call(parent.children, (x, i) => m.set(x, i)); indexes.set(parent, m); }
    const i = m.get(tr);
    return i === undefined ? -1 : i;
  };
  const rangDans = (conteneur, e) => {
    let liste = cache.get(conteneur);
    if (!liste) { liste = Array.from(conteneur.querySelectorAll(SELECTION)).filter(x => !x.matches(EXCLUS)); cache.set(conteneur, liste); }
    return liste.indexOf(e);
  };
  const decrire = e => {
    const tag = e.tagName.toLowerCase();
    let type = (e.getAttribute('type') || '').toLowerCase();
    const formulaire = e.form || null;
    if (tag === 'button' && !['submit', 'button', 'reset'].includes(type)) type = formulaire ? 'submit' : 'button';
    const soumet = !!formulaire && (type === 'submit' || type === 'image');
    const methode = soumet ? (e.getAttribute('formmethod') || formulaire.getAttribute('method') || 'get').toLowerCase() : '';
    const z = zone(e);
    let ligne = -1, rang = -1, conteneur = '';
    const cont = conteneurDe(e, z);
    if (cont) {
      if (z === 'tableau') {
        const tr = e.closest('tbody tr, [role=row]');
        ligne = tr ? indexLigne(tr) : -1;
        rang = tr ? (tr === e ? 0 : Array.from(tr.querySelectorAll(SELECTION)).filter(x => !x.matches(EXCLUS)).indexOf(e) + 1) : -1;
      } else {
        ligne = rangDans(cont, e);
      }
      conteneur = chemin(cont);
    }
    return {
      texte: court(tag === 'input' ? (e.value || '') : (e.innerText || ''), 80),
      aria: court(e.getAttribute('aria-label') || e.getAttribute('title') || e.getAttribute('alt') || '', 80),
      tag: tag, type: type, role: e.getAttribute('role') || '', id: e.id || '',
      href: tag === 'a' ? (e.getAttribute('href') || '') : '',
      href_absolu: (tag === 'a' && e.href) ? String(e.href) : '',
      telechargement: tag === 'a' && e.hasAttribute('download'),
      desactive: !!e.disabled || e.getAttribute('aria-disabled') === 'true',
      zone: z, ligne: ligne, rang: rang, conteneur: conteneur,
      soumet: soumet, methode: methode, selecteur: chemin(e),
    };
  };
"""

JS_ECRAN = r"""
([exemples, maxCibles]) => {
""" + JS_OUTILS + r"""
  const titres = [];
  document.querySelectorAll('h1, h2, h3, [role=heading]').forEach(h => { if (vis(h) && titres.length < 12) titres.push(court(h.innerText, 100)); });
  const champs = [];
  document.querySelectorAll('input, select, textarea, [contenteditable=true]').forEach(e => {
    const tag = e.tagName.toLowerCase();
    const type = (e.getAttribute('type') || '').toLowerCase();
    if (type === 'hidden' || ['submit', 'button', 'reset', 'image'].includes(type) || !vis(e) || champs.length >= 200) return;
    const tr = e.closest('tbody tr');
    if (tr && indexLigne(tr) >= exemples) return;
    const [lib, source] = libelle(e);
    champs.push({
      libelle: lib, source: source, nom: e.id || e.getAttribute('name') || '',
      type: tag === 'select' ? 'liste' : tag === 'textarea' ? 'texte long' : (e.isContentEditable && tag !== 'input') ? 'texte riche' : (type || 'text'),
      obligatoire: !!e.required, lecture_seule: !!(e.readOnly || e.disabled),
      nb_options: tag === 'select' ? e.options.length : 0,
      options: tag === 'select' ? Array.from(e.options).slice(0, 15).map(o => court(o.text, 60)) : [],
      dans_tableau: !!tr, zone: zone(e),
    });
  });
  const tableaux = [];
  document.querySelectorAll('table, [role=grid]').forEach(t => {
    if (!vis(t) || t.parentElement.closest('table')) return;
    let entetes = Array.from(t.querySelectorAll('thead th, [role=columnheader]')).map(texteSeul);
    if (!entetes.length) { const tr = t.querySelector('tr'); if (tr) entetes = Array.from(tr.querySelectorAll('th')).map(texteSeul); }
    tableaux.push({ entetes: entetes.slice(0, 40), lignes: t.querySelectorAll('tbody tr, [role=row]').length });
  });
  const cibles = [];
  let tronque = false;
  for (const e of document.querySelectorAll(SELECTION)) {
    const tr = e.closest('tbody tr, [role=row]');
    if (tr && indexLigne(tr) >= exemples) continue;   // une ligne ressemble aux autres : les premières suffisent
    if (e.matches(EXCLUS) || !vis(e)) continue;
    if (cibles.length >= maxCibles) { tronque = true; break; }
    cibles.push(decrire(e));
  }
  const cadres = Array.from(document.querySelectorAll('iframe, frame')).filter(vis).map(f => String(f.src || ''));
  const motDePasse = !!Array.from(document.querySelectorAll('input[type=password]')).find(vis);
  const identifiant = !!Array.from(document.querySelectorAll('input[type=email], input[autocomplete=username], ' +
      'input[name*=user i], input[name*=login i], input[id*=user i], input[id*=login i], input[name*=identifiant i]')).find(vis);
  const fenetre = !!Array.from(document.querySelectorAll(FENETRE)).find(vis);
  return {
    url: location.href, titre: court(document.title, 120), titres: titres, champs: champs,
    tableaux: tableaux, cibles: cibles, tronque: tronque, cadres: cadres,
    mot_de_passe: motDePasse, identifiant: identifiant, fenetre: fenetre,
  };
}
"""

# Vérifie ET clique dans le même instant : si l'élément n'est plus exactement celui qui a
# été approuvé, rien n'est cliqué. Le clic est envoyé à l'élément lui-même (pas à un
# point de l'écran) : ce qui est posé dessus ou dedans n'est jamais touché.
JS_CLIC = r"""
([selecteur, attendu]) => {
""" + JS_OUTILS + r"""
  let e = null;
  try { e = document.querySelector(selecteur); } catch (err) { return 'sélecteur illisible'; }
  if (!e) return 'absent';
  if (e.matches(EXCLUS) || !vis(e)) return 'plus cliquable';
  const d = decrire(e);
  for (const k of Object.keys(attendu)) {
    if (String(d[k]) !== String(attendu[k])) return 'changé (' + k + ')';
  }
  const options = { bubbles: true, cancelable: true, view: window };
  e.dispatchEvent(new MouseEvent('mouseover', options));
  e.dispatchEvent(new MouseEvent('mousedown', options));
  e.dispatchEvent(new MouseEvent('mouseup', options));
  e.click();
  return 'ok';
}
"""

# L'écran est prêt quand presque plus rien ne bouge et qu'aucun indicateur de chargement
# n'est visible (voile « Veuillez patienter », aria-busy, barre de progression).
JS_CALME = r"""
(maximum) => new Promise(fini => {
  const vis = e => { const s = getComputedStyle(e); if (s.display === 'none' || s.visibility === 'hidden') return false;
                     const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  const aire = e => { const r = e.getBoundingClientRect(); return r.width * r.height; };
  const charge = () => {
    if (document.readyState !== 'complete') return true;
    for (const e of document.querySelectorAll('[aria-busy=true], [role=progressbar], .blockUI, .blockOverlay')) if (vis(e)) return true;
    for (const e of document.querySelectorAll('.loading, .spinner, .loader, .chargement, #chargement, #loading')) {
      if (vis(e) && !e.querySelector('input') && aire(e) > 400) return true;
    }
    for (const e of document.querySelectorAll('div, span, p, h1, h2, h3')) {
      if (e.children.length) continue;
      const t = (e.textContent || '').trim().toLowerCase();
      if (t.length < 40 && /^(chargement|loading|veuillez patienter|please wait|patientez)(\s+en cours)?\s*(\.\.\.|…)?$/.test(t) && vis(e)) return true;
    }
    return false;
  };
  const activite = [];
  let courant = 0;
  const obs = new MutationObserver(l => { courant += l.length; });
  obs.observe(document.documentElement, { childList: true, subtree: true, attributes: true, characterData: true });
  const debut = Date.now();
  const tic = setInterval(() => {
    activite.push(courant); courant = 0;
    const calme = activite.length >= 3 && activite.slice(-3).every(n => n <= 2);
    const fin = Date.now() - debut > maximum;
    if (fin || (calme && !charge())) { clearInterval(tic); obs.disconnect(); fini(!fin); }
  }, 200);
})
"""

# Injecté dans chaque page : l'impression ouvrirait une fenêtre qui bloque tout.
JS_NEUTRALISER = "window.print = function () {}; window.showModalDialog = function () {};"


# ---------------------------------------------------------------------- modèle de la carte
@dataclass
class Action:
    """Un pas pour atteindre un écran : ouvrir une adresse, ou cliquer sur un élément."""

    type: str  # "aller" | "clic"
    url: str = ""
    selecteur: str = ""
    texte: str = ""
    zone: str = ""
    ligne: int = -1
    attendu: Dict[str, Any] = field(default_factory=dict)
    partage: str = ""  # libellé sans données, pour la carte à partager

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
    tronque: bool = False
    fenetre: bool = False
    profondeur: int = 0
    resultats: Dict[str, str] = field(default_factory=dict)


@dataclass
class Limites:
    ecrans: int = 150
    profondeur: int = 6
    minutes: float = 60.0
    delai_ms: int = 500
    exemples: int = 2  # écrans visités par modèle d'adresse, lignes essayées par tableau
    max_cibles: int = 400  # éléments cliquables lus par écran


class ArretExploration(Exception):
    pass


def _norm_chiffres(texte: str) -> str:
    return re.sub(r"\d+", "#", normaliser(texte))


def signature(lecture: Dict[str, Any]) -> str:
    """Empreinte de la STRUCTURE d'un écran : ni données, ni menus changeants (récents,
    arborescence), ni chiffres. Deux fiches de composants différents ont la même empreinte."""
    onglets = sorted({_norm_chiffres(c["texte"] or c["aria"]) for c in lecture["cibles"] if c["zone"] == "onglet"})
    boutons = sorted({_norm_chiffres(c["texte"] or c["aria"]) for c in lecture["cibles"]
                      if c["zone"] in ("page", "fenetre") and c["tag"] != "a"})
    champs = sorted({(_norm_chiffres(c["libelle"]) if c["source"] in ("label", "aria", "entete") else "", c["type"])
                     for c in lecture["champs"] if not c["dans_tableau"] and c["zone"] not in ("arbre", "lateral")})
    tableaux = sorted((tuple(_norm_chiffres(e) for e in t["entetes"]), t["lignes"] > 0) for t in lecture["tableaux"])
    brut = json.dumps([modele_url(lecture["url"]), onglets, boutons, champs, tableaux, lecture.get("fenetre", False)],
                      ensure_ascii=False)
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
        self._clics_globaux: Dict[str, int] = {}
        self.transitions: List[Dict[str, str]] = []
        self.bloquees: List[Tuple[str, str]] = []  # (méthode, modèle d'adresse) : envois empêchés
        self.websockets = 0
        self.telechargements: List[str] = []
        self.externes: List[str] = []
        self.formulaires_bloques = 0
        self.essais = 0
        self.hote = ""
        self.depart = ""
        self.garde_active = False
        self.arret = ""
        self.complet = False
        self._debut = 0.0
        self._relogins = 0
        self._echecs_consecutifs = 0
        self._calme_max = 8000
        self._delais_depasses = 0
        self._urls_sures: Set[str] = set()
        self._nouvelles_pages: List[Page] = []
        self._fenetres_a_voir: List[str] = []
        self._interrompu: List[int] = []
        self._depuis_sauvegarde = 0

    # ------------------------------------------------------------------ sécurité réseau
    def _garde(self, route: Any) -> None:
        """Toute requête qui enverrait des données, ou dont l'adresse ressemble à une action,
        est bloquée avant de partir. Exception : les adresses que le robot ouvre lui-même
        (page de départ, liens déjà vérifiés)."""
        try:
            requete = route.request
            methode = requete.method.upper()
            raison = ""
            if methode not in METHODES_LECTURE:
                m = decouper(requete.url)
                if not (methode == "POST" and m is not None and MOTIF_RETOUR_CONNEXION.search(m.path)):
                    raison = methode
            elif requete.resource_type not in RESSOURCES_STATIQUES:
                if not (requete.is_navigation_request() and sans_fragment(requete.url) in self._urls_sures):
                    raison = adresse_action(requete.url) or ""
            if self.garde_active and raison:
                self.bloquees.append((methode, modele_url(requete.url)))
                journal.debug("Requête bloquée (%s) : %s %s", raison, methode, modele_url(requete.url))
                route.abort()
            else:
                route.continue_()
        except Exception as e:  # noqa: BLE001 - un gestionnaire ne doit jamais lever
            journal.debug("Garde : %s", e)

    def _garde_websocket(self, ws: Any) -> None:
        """Aucune connexion WebSocket ne part vers le serveur (rien n'est relayé)."""
        self.websockets += 1

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

        def sur_ctrl_c(*_: Any) -> None:
            if self._interrompu:  # second Ctrl+C : sortie immédiate, la carte est sauvée
                try:
                    self.arret = "arrêt immédiat (second Ctrl+C)"
                    self.enregistrer()
                finally:
                    os._exit(130)
            self._interrompu.append(1)
            print(f"\n{S.ATTENTION} Arrêt demandé : le robot termine l'action en cours puis s'arrête "
                  "(Ctrl+C encore une fois pour arrêter tout de suite).", flush=True)

        try:
            ancien = signal.signal(signal.SIGINT, sur_ctrl_c)
        except (ValueError, OSError):
            ancien = None
        try:
            self._explorer(url)
        finally:
            if ancien is not None:
                signal.signal(signal.SIGINT, ancien)

    def _explorer(self, url: str) -> None:
        contexte = self.nav.contexte
        page = self.nav.page_courante()
        contexte.route("**/*", self._garde)
        if hasattr(contexte, "route_web_socket"):
            try:
                contexte.route_web_socket(re.compile(".*"), self._garde_websocket)
            except Exception as e:  # noqa: BLE001
                journal.debug("WebSocket non contrôlés : %s", e)
        contexte.add_init_script(JS_NEUTRALISER)
        contexte.on("page", self._nouvelle_page)
        page.on("download", self._telechargement)
        self._debut = time.monotonic()
        self._urls_sures.add(sans_fragment(url))
        try:
            page.goto(url, wait_until="domcontentloaded")
        except Exception as e:  # noqa: BLE001
            raise ErreurAutoweb(f"Impossible d'ouvrir {url} : {str(e).splitlines()[0]}")
        self._attendre(page)
        self._connexion(page, premiere_fois=True)
        page = self.nav.page_courante()
        try:
            page.evaluate(JS_NEUTRALISER)
        except Exception:  # noqa: BLE001
            pass
        m = decouper(page.url)
        self.hote = m.netloc if m else ""
        self.depart = page.url
        self._urls_sures.add(sans_fragment(page.url))
        self.garde_active = True
        premier = self._observer(page, [Action("aller", url=page.url, partage="page de départ")], 0)
        if premier is None:
            raise ErreurAutoweb("La page de départ n'a pas pu être lue.")
        self._visites_modele[premier.modele] = 1
        a_traiter = [premier]
        try:
            while a_traiter:
                ecran = a_traiter.pop(0)
                if ecran.profondeur < self.limites.profondeur:
                    for cible in self._cibles_a_essayer(ecran):
                        self._verifier_limites()
                        nouveau = self._essayer_sans_planter(ecran, cible)
                        if nouveau is not None:
                            a_traiter.append(nouveau)
                            self._sauvegarde_periodique()
                for adresse in self._fenetres_a_voir:  # fenêtres ouvertes par l'outil : vues à part
                    self._verifier_limites()
                    nouveau = self._essayer_sans_planter(ecran, self._pseudo_lien(adresse, "fenêtre"))
                    if nouveau is not None:
                        a_traiter.append(nouveau)
                self._fenetres_a_voir = []
            self.complet = True
            self.arret = "tout ce qui était accessible sans rien modifier a été vu"
        except ArretExploration as e:
            self.arret = str(e)
        except KeyboardInterrupt:
            self.arret = "arrêt demandé (Ctrl+C)"
        finally:
            self.garde_active = False
            if self.formulaires_bloques >= 3:
                self.complet = False
                self.arret += (" ; attention : ce portail navigue en envoyant des formulaires, bloqués par "
                               "sécurité : la carte est incomplète")
            try:
                contexte.unroute("**/*", self._garde)
            except Exception:  # noqa: BLE001
                pass
            self.enregistrer()

    def _essayer_sans_planter(self, ecran: Ecran, cible: Dict[str, Any]) -> Optional[Ecran]:
        """Une erreur sur un élément ne doit pas arrêter toute l'exploration."""
        try:
            return self._essayer(ecran, cible)
        except (ArretExploration, KeyboardInterrupt):
            raise
        except Exception as e:  # noqa: BLE001
            if navigateur_ferme(e):
                raise ArretExploration("le navigateur a été fermé")
            ecran.resultats[self._cle(cible)] = "erreur pendant l'essai"
            journal.debug("Erreur sur %s : %s", self._cle(cible), e)
            return None

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
        Ensuite : seulement si la session a expiré."""
        if self.connexion is not None:
            self.connexion(page)
            self._attendre(page)
            return
        if not self.interactif:
            if premiere_fois:
                return
            raise ArretExploration("la session a expiré (connexion redemandée) : carte incomplète")
        from .console import lire_ligne, vider_clavier

        if not premiere_fois:
            self._relogins += 1
            if self._relogins > 3:
                raise ArretExploration("la connexion est redemandée sans cesse : carte incomplète")
        print()
        if premiere_fois:
            print(f"{S.PAUSE}  Dans la fenêtre du robot : connectez-vous si besoin, puis allez sur la page")
            print("   d'ACCUEIL du portail (celle d'où part l'exploration).")
        else:
            print(f"{S.PAUSE}  Le portail redemande la connexion : reconnectez-vous dans la fenêtre du robot,")
            print("   sans rien faire d'autre.")
        print("   Puis revenez ici et appuyez sur Entrée : ", end="", flush=True)
        actif, self.garde_active = self.garde_active, False  # la connexion envoie des données : permis
        try:
            with self.nav.pause_manuelle():
                lire_ligne(self.nav.pomper)
        finally:
            self.garde_active = actif
            vider_clavier()  # un second Entrée ne doit pas arrêter l'exploration
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
            calme = page.evaluate(JS_CALME, self._calme_max)
            if calme is False:
                self._delais_depasses += 1
                if self._delais_depasses >= 3:
                    self._calme_max = 3000  # page qui bouge sans cesse : on n'attend plus autant
            else:
                self._delais_depasses = 0
        except Exception:  # noqa: BLE001 - la page a changé pendant l'attente
            pass
        if self.limites.delai_ms:
            page.wait_for_timeout(self.limites.delai_ms)

    def _lire(self, page: Page) -> Optional[Dict[str, Any]]:
        for _ in range(2):
            try:
                return page.evaluate(JS_ECRAN, [self.limites.exemples, self.limites.max_cibles])
            except Exception:  # noqa: BLE001 - navigation en cours : on réessaie une fois
                self._attendre(page)
        return None

    # ------------------------------------------------------------------ fenêtres, session
    def _fermer_fenetres_en_trop(self) -> List[str]:
        """Toute fenêtre autre que celle du robot est notée puis refermée."""
        adresses = []
        for autre in list(self.nav.contexte.pages):
            if autre is self.nav.page or autre.is_closed():
                continue
            try:
                adresses.append(autre.url)
                autre.close()
            except Exception:  # noqa: BLE001
                pass
        self._nouvelles_pages = []
        return adresses

    def _connexion_perdue(self, lecture: Dict[str, Any], apres_aller: bool) -> bool:
        """Écran de connexion, ou renvoi vers un autre serveur (SSO) après avoir ouvert
        une adresse connue du portail : la session a probablement expiré."""
        m = decouper(lecture["url"])
        if apres_aller and m is not None and m.netloc != self.hote:
            return True
        menus = sum(1 for c in lecture["cibles"] if c["zone"] in ("menu", "lateral", "arbre"))
        if menus >= 3:
            return False  # « Mon compte / changer le mot de passe » : un écran normal du portail
        if lecture["mot_de_passe"]:
            return True
        chemin = normaliser(m.path if m else "")
        return lecture["identifiant"] and bool(re.search(r"login|signin|sso|saml|oauth|authorize|connexion|logon", chemin))

    # ------------------------------------------------------------------ écrans
    def _observer(self, page: Page, chemin: List[Action], profondeur: int,
                  lecture: Optional[Dict[str, Any]] = None) -> Optional[Ecran]:
        """Lit l'écran courant ; renvoie un Ecran s'il est NOUVEAU, sinon None."""
        lecture = lecture or self._lire(page)
        if lecture is None:
            return None
        sig = signature(lecture)
        if sig in self._par_signature:
            return None
        ecran = Ecran(
            id=f"E{len(self.ecrans) + 1}", url=lecture["url"], modele=modele_url(lecture["url"]), signature=sig,
            chemin=list(chemin), titre=lecture["titre"], titres=lecture["titres"],
            champs=lecture["champs"], tableaux=lecture["tableaux"], cibles=lecture["cibles"],
            cadres=lecture["cadres"], tronque=lecture["tronque"], fenetre=lecture["fenetre"], profondeur=profondeur,
        )
        self.ecrans.append(ecran)
        self._par_signature[sig] = ecran
        journal.info("   %s %s : « %s » — %d champ(s), %d élément(s) cliquable(s), %d tableau(x)",
                     S.OK, ecran.id, (ecran.titres[0] if ecran.titres else ecran.titre)[:60],
                     len(ecran.champs), len(ecran.cibles), len(ecran.tableaux))
        return ecran

    def _decision(self, cible: Dict[str, Any]) -> Tuple[str, str]:
        """(« aller » | « clic » | « non », raison). Tout ce qui n'est pas explicitement de la
        navigation ou de la consultation est refusé."""
        texte = cible["texte"] or cible["aria"]
        if cible["desactive"]:
            return "non", "désactivé"
        if cible["zone"] == "fenetre":
            return "non", "dans une fenêtre de confirmation ou de saisie"
        interdit = mot_interdit(cible["aria"], cible["id"], cible["href"],
                                "" if cible["tag"] == "tr" else texte)  # texte d'une ligne entière = données
        if interdit:
            return "non", f"risque (« {interdit} »)"
        href = cible["href"].strip()
        if cible["tag"] == "a" and href and not href.startswith(("#", "javascript:")):
            m = decouper(cible["href_absolu"])
            if m is None:
                return "non", "lien illisible"
            if m.scheme in ("mailto", "tel"):
                return "non", "adresse mail / téléphone"
            if m.scheme not in ("http", "https", "file"):
                return "non", "lien spécial"
            if cible["telechargement"] or m.path.lower().endswith(EXTENSIONS_FICHIERS):
                self.telechargements.append(modele_url(cible["href_absolu"]))
                return "non", "fichier à télécharger"
            if m.netloc != self.hote:
                self.externes.append(m.netloc)
                return "non", "lien vers un autre site"
            action = adresse_action(cible["href_absolu"])
            if action:
                return "non", f"adresse qui ressemble à une action ({action})"
            return "aller", ""
        if cible["tag"] == "tr":
            return "clic", ""  # ligne entière cliquable : le clic va à la ligne, pas à ce qu'elle contient
        if not a_des_lettres(texte):
            return "non", "symbole ou icône sans texte : on ne sait pas ce qu'il fait"
        if cible["soumet"]:
            if cible["methode"] != "get" or not est_lecture(texte):
                return "non", "bouton qui envoie un formulaire"
            return "clic", ""
        if cible["tag"] == "a" and len(href) > 1 and href.startswith("#") and href != "#!":
            return "clic", ""  # lien de navigation interne (#fiche=..., #/plans)
        if cible["zone"] == "tableau" and cible["tag"] == "a" and cible["rang"] == 1:
            return "clic", ""  # premier lien d'une ligne : ouvre la fiche (son texte, ce sont des données)
        if cible["zone"] in ("menu", "lateral", "onglet", "arbre") or cible["role"] in ("tab", "menuitem", "treeitem"):
            return "clic", ""
        if cible["tag"] == "summary" or est_lecture(texte):
            return "clic", ""
        return "non", "bouton d'action (à me montrer si utile)"

    def _cle(self, cible: Dict[str, Any]) -> str:
        if cible["zone"] == "tableau":
            if cible["rang"] <= 0:
                return f"ligne {cible['ligne'] + 1} du tableau"
            return f"ligne {cible['ligne'] + 1} du tableau, élément {cible['rang']}"
        if cible.get("pseudo"):
            return cible["texte"]
        return cible["texte"] or cible["aria"] or cible["selecteur"]

    def _pseudo_lien(self, adresse: str, nature: str) -> Dict[str, Any]:
        return {"texte": f"{nature} {modele_url(adresse)}", "aria": "", "tag": "a", "type": "", "role": "",
                "id": "", "href": adresse, "href_absolu": adresse, "telechargement": False, "desactive": False,
                "zone": "page", "ligne": -1, "rang": -1, "conteneur": "", "soumet": False, "methode": "",
                "selecteur": "", "pseudo": nature}

    def _cibles_a_essayer(self, ecran: Ecran) -> List[Dict[str, Any]]:
        retenues: List[Dict[str, Any]] = []
        deja: set = set()
        cibles = list(ecran.cibles)
        cibles += [self._pseudo_lien(src, "cadre") for src in ecran.cadres if src.startswith(("http", "file"))]
        for cible in cibles:
            if cible["zone"] == "tableau" and not (0 <= cible["ligne"] < self.limites.exemples):
                continue
            if cible["zone"] == "arbre" and cible["ligne"] >= self.limites.exemples:
                ecran.resultats.setdefault(self._cle(cible), "déjà vu (autre élément de l'arborescence)")
                continue
            if cible["zone"] == "lateral" and cible["ligne"] >= 25:
                ecran.resultats.setdefault(self._cle(cible), "non essayé (menu latéral très long)")
                continue
            action, raison = self._decision(cible)
            cle = self._cle(cible)
            if action == "non":
                ecran.resultats.setdefault(cle, f"non cliqué : {raison}")
                continue
            if action == "aller":
                modele = modele_url(cible["href_absolu"])
                if sans_fragment(cible["href_absolu"]) == sans_fragment(ecran.url) and "#" not in cible["href"]:
                    continue  # lien vers la page elle-même
                if self._visites_modele.get(modele, 0) >= self.limites.exemples or (action, modele) in deja:
                    ecran.resultats.setdefault(cle, "déjà vu (même genre de page)")
                    continue
                deja.add((action, modele))
            else:
                globale = self._cle_globale(ecran, cible)
                if globale and self._clics_globaux.get(globale, 0) >= 1:
                    ecran.resultats.setdefault(cle, "déjà essayé depuis un autre écran")
                    continue
                if (action, cle) in deja:
                    continue
                deja.add((action, cle))
            retenues.append(cible)
        return retenues

    @staticmethod
    def _cle_globale(ecran: Ecran, cible: Dict[str, Any]) -> str:
        """Un même menu se retrouve sur tous les écrans : un seul essai suffit."""
        if cible["zone"] in ("menu", "lateral"):
            return f"menu|{_norm_chiffres(cible['texte'] or cible['aria'])}"
        if cible["zone"] == "onglet":
            return f"onglet|{ecran.modele}|{_norm_chiffres(cible['texte'] or cible['aria'])}"
        return ""

    @staticmethod
    def _attendu(cible: Dict[str, Any]) -> Dict[str, Any]:
        """Ce qui doit être IDENTIQUE au moment du clic pour que le clic ait lieu."""
        cles = ["tag", "type", "role", "id", "zone", "soumet", "methode", "aria", "href"]
        if not (cible["zone"] == "tableau" and cible["tag"] in ("tr", "a")):
            cles.append("texte")  # le texte d'une ligne ou d'un lien de ligne, ce sont des données
        if cible["zone"] in ("tableau", "arbre", "lateral"):
            cles += ["ligne", "rang", "conteneur"]
        return {k: cible[k] for k in cles}

    def _essayer(self, ecran: Ecran, cible: Dict[str, Any]) -> Optional[Ecran]:
        cle = self._cle(cible)
        action, _ = self._decision(cible)
        self._fermer_fenetres_en_trop()
        page = self.nav.page_courante()
        if action == "aller":
            pas = Action("aller", url=cible["href_absolu"], partage="un lien" if not cible.get("pseudo") else cible["pseudo"])
            modele = modele_url(pas.url)
            self._visites_modele[modele] = self._visites_modele.get(modele, 0) + 1
            chemin = [pas]
        else:
            if not self._restaurer(ecran):
                ecran.resultats[cle] = "écran impossible à retrouver"
                return None
            page = self.nav.page_courante()
            pas = Action("clic", selecteur=cible["selecteur"], texte=cible["texte"] or cible["aria"],
                         zone=cible["zone"], ligne=cible["ligne"], attendu=self._attendu(cible),
                         partage=self._libelle_partage(cible))
            chemin = ecran.chemin + [pas]
            globale = self._cle_globale(ecran, cible)
            if globale:
                self._clics_globaux[globale] = self._clics_globaux.get(globale, 0) + 1
        nb_bloquees, nb_fichiers = len(self.bloquees), len(self.telechargements)
        self._nouvelles_pages = []
        self.essais += 1
        resultat = self._jouer(page, pas)
        if resultat != "ok":
            ecran.resultats[cle] = f"non cliqué : {resultat}"
            return None
        page = self.nav.page_courante()
        notes = []
        for adresse in self._fermer_fenetres_en_trop():
            m = decouper(adresse)
            notes.append(f"ouvre une nouvelle fenêtre ({modele_url(adresse)})")
            if m is not None and m.netloc == self.hote and adresse not in self._fenetres_a_voir:
                self._fenetres_a_voir.append(adresse)
        if len(self.bloquees) > nb_bloquees:
            notes.append("a voulu ENVOYER des données : bloqué")
        if len(self.telechargements) > nb_fichiers:
            notes.append("lance un téléchargement (annulé)")
        lecture = self._lire(page)
        if lecture is None:
            ecran.resultats[cle] = " ; ".join(notes + ["écran illisible"])
            return None
        if lecture["url"].startswith(("chrome-error:", "about:blank")):
            self.formulaires_bloques += 1
            ecran.resultats[cle] = " ; ".join(notes + ["navigation par envoi de formulaire : bloquée"])
            return None
        # un nouveau lien qui mène ailleurs sort simplement du portail ; seul un écran de
        # connexion signale ici une session expirée (le renvoi SSO est vu en revenant sur un écran connu)
        if self._connexion_perdue(lecture, apres_aller=False):
            ecran.resultats[cle] = "connexion redemandée"
            self._connexion(page)
            return None
        m = decouper(lecture["url"])
        if m is None or m.netloc != self.hote:
            if m is not None:
                self.externes.append(m.netloc)
            ecran.resultats[cle] = " ; ".join(notes + ["sort du portail"])
            return None
        nouveau = self._observer(page, chemin, ecran.profondeur + 1, lecture)
        if nouveau is not None:
            notes.insert(0, f"mène à {nouveau.id}")
            self.transitions.append({"de": ecran.id, "action": cle, "vers": nouveau.id})
        else:
            vers = self._par_signature.get(signature(lecture))
            notes.insert(0, f"mène à {vers.id}" if vers else "rien de nouveau")
            if vers and vers is not ecran:
                self.transitions.append({"de": ecran.id, "action": cle, "vers": vers.id})
        ecran.resultats[cle] = " ; ".join(notes)
        return nouveau

    def _restaurer(self, ecran: Ecran) -> bool:
        """Revient sur l'écran : il suffit parfois d'y être déjà, sinon on rejoue le chemin."""
        page = self.nav.page_courante()
        lecture = self._lire(page)
        if lecture is not None and signature(lecture) == ecran.signature and lecture["url"] == ecran.url:
            return True
        for essai in range(2):
            ok = True
            for pas in ecran.chemin:
                if self._jouer(self.nav.page_courante(), pas) != "ok":
                    ok = False
                    break
                self._fermer_fenetres_en_trop()
            lecture = self._lire(self.nav.page_courante()) if ok else None
            if lecture is not None and self._connexion_perdue(lecture, apres_aller=True) and essai == 0:
                self._connexion(self.nav.page_courante())
                continue
            if lecture is not None and signature(lecture) == ecran.signature:
                self._echecs_consecutifs = 0
                return True
            break
        self._echecs_consecutifs += 1
        if self._echecs_consecutifs >= 6:
            raise ArretExploration("les écrans ne se retrouvent plus (session expirée ?) : carte incomplète")
        return False

    def _jouer(self, page: Page, pas: Action) -> str:
        """« ok », ou la raison pour laquelle rien n'a été fait."""
        try:
            if pas.type == "aller":
                self._urls_sures.add(sans_fragment(pas.url))
                page.goto(pas.url, wait_until="domcontentloaded")
            else:
                try:
                    resultat = page.evaluate(JS_CLIC, [pas.selecteur, pas.attendu])
                except Exception as e:  # noqa: BLE001
                    texte = str(e)
                    if "context was destroyed" in texte or "navigat" in texte:
                        resultat = "ok"  # le clic a déclenché un changement de page
                    else:
                        raise
                if resultat != "ok":
                    return f"l'élément a changé ({resultat})"
        except (ArretExploration, KeyboardInterrupt):
            raise
        except Exception as e:  # noqa: BLE001
            if navigateur_ferme(e):
                raise ArretExploration("le navigateur a été fermé")
            journal.debug("Action impossible (%s) : %s", pas.libelle(), str(e).splitlines()[0])
            return "action impossible"
        self._attendre(self.nav.page_courante())
        return "ok"

    # ------------------------------------------------------------------ résultats
    def resume(self) -> Dict[str, Any]:
        return {
            "ecrans": len(self.ecrans),
            "essais": self.essais,
            "bloquees": len(self.bloquees),
            "websockets": self.websockets,
            "telechargements": len(set(self.telechargements)),
            "arret": self.arret,
            "complet": self.complet,
            "duree_s": round(time.monotonic() - self._debut) if self._debut else 0,
        }

    def _sauvegarde_periodique(self) -> None:
        self._depuis_sauvegarde += 1
        if self._depuis_sauvegarde >= 5:
            self._depuis_sauvegarde = 0
            self.enregistrer()

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

    # ------------------------------------------------------------------ carte à partager
    # Liste d'AUTORISATION : seuls les textes de l'interface qui ne sont presque jamais des
    # données sont repris (noms de champs, entêtes de colonnes, onglets et menus courts,
    # boutons usuels). Tout le reste est remplacé par sa nature : « (bouton) », « un lien ».
    @staticmethod
    def _court(texte: str, mots: int = 3) -> bool:
        return 0 < len(normaliser(texte).split()) <= mots

    def _texte_bouton(self, cible: Dict[str, Any]) -> str:
        texte = cible["texte"] or cible["aria"]
        if est_lecture(texte) or (mot_interdit(texte) and self._court(texte, 4)):
            return masquer(texte)
        return "(bouton)"

    def _libelle_partage(self, cible: Dict[str, Any]) -> str:
        texte = cible["texte"] or cible["aria"]
        if cible["zone"] == "tableau":
            return f"ligne {cible['ligne'] + 1} du tableau"
        if cible["zone"] == "arbre":
            return "un élément de l'arborescence"
        noms = {"onglet": "onglet", "menu": "menu"}
        if cible["zone"] in noms and self._court(texte) and \
                (cible["tag"] == "a" or cible["role"] in ("tab", "menuitem") or cible["zone"] == "onglet"):
            return f"{noms[cible['zone']]} « {masquer(texte)} »"
        if cible["zone"] == "lateral":
            return "un élément du menu latéral"
        if cible["tag"] == "a":
            return "un lien"
        return f"bouton « {self._texte_bouton(cible)} »" if self._texte_bouton(cible) != "(bouton)" else "un bouton"

    def _libelle_champ(self, champ: Dict[str, Any]) -> str:
        if champ["type"] in ("checkbox", "radio"):
            return "(case)"
        if champ["source"] in ("label", "aria", "entete") and self._court(champ["libelle"], 5):
            return masquer(champ["libelle"])
        if champ["source"] == "voisin" and champ["libelle"].rstrip().endswith(":") and self._court(champ["libelle"], 5):
            return masquer(champ["libelle"])
        return "(sans nom)"

    def _texte_partage(self) -> str:
        r = self.resume()
        ids = {e.id for e in self.ecrans}

        def resultat(texte: str) -> str:
            texte = re.sub(r"\([^)]*\)", "", texte)  # adresses, mots entre parenthèses : retirés
            return " ".join(m if m.rstrip(",;") in ids else masquer(m) for m in texte.split())

        lignes = [
            "CARTE DU PORTAIL - VERSION A PARTAGER",
            "=" * 60,
            "Ce fichier décrit la STRUCTURE du portail : écrans, noms des champs, colonnes des",
            "tableaux, onglets et menus courts, boutons usuels. Il ne contient ni valeurs, ni contenu",
            "de tableau, ni titres de page, ni adresses. Les mots contenant un chiffre sont remplacés",
            "par #, les autres textes par leur nature, par exemple « (bouton) ».",
            "Un nom d'onglet, de menu ou de colonne peut malgré tout être un nom de client, de projet",
            "ou de personne : RELISEZ-LE et remplacez ce qui vous semble sensible avant de l'envoyer.",
            "",
            f"{r['ecrans']} écran(s) vus, {r['essais']} élément(s) essayés, "
            f"{r['bloquees']} envoi(s) de données bloqué(s). "
            f"{'Exploration complète.' if r['complet'] else 'Exploration INCOMPLÈTE.'}",
            "",
        ]
        for e in self.ecrans:
            lignes.append(f"{e.id}" + ("   (fenêtre ouverte par-dessus l'écran)" if e.fenetre else ""))
            lignes.append(f"     accès : {' › '.join(p.partage or 'un clic' for p in e.chemin)}")
            onglets = sorted({masquer(c["texte"]) for c in e.cibles
                              if c["zone"] == "onglet" and self._court(c["texte"])})
            if onglets:
                lignes.append(f"     onglets : {' ; '.join(onglets)}")
            menus = sorted({masquer(c["texte"]) for c in e.cibles if c["zone"] == "menu" and self._court(c["texte"])
                            and (c["tag"] == "a" or c["role"] == "menuitem")})
            if menus:
                lignes.append(f"     menus : {' ; '.join(menus)}")
            lateral = sum(1 for c in e.cibles if c["zone"] == "lateral")
            if lateral:
                # souvent « consultés récemment », dossiers, projets : noms non repris
                lignes.append(f"     menu latéral : {lateral} entrée(s), noms non repris")
            champs = [f"{self._libelle_champ(c)} [{type_champ(c['type'])}"
                      + (f", {c['nb_options']} choix" if c["type"] == "liste" else "")
                      + (", obligatoire" if c["obligatoire"] else "")
                      + (", lecture seule" if c["lecture_seule"] else "") + "]"
                      for c in e.champs if not c["dans_tableau"] and c["zone"] not in ("arbre", "lateral")]
            if champs:
                lignes.append(f"     champs : {' ; '.join(champs)}")
            boutons = []
            for c in e.cibles:
                if c["zone"] not in ("page", "fenetre") or c["tag"] == "a":
                    continue
                res = e.resultats.get(self._cle(c), "")
                boutons.append(self._texte_bouton(c) + (f" → {resultat(res)}" if res else ""))
            if boutons:
                lignes.append(f"     boutons : {' ; '.join(boutons)}")
            for t in e.tableaux:
                lignes.append(f"     tableau : [{masquer(' | '.join(t['entetes']))}] ({t['lignes']} lignes)")
            for k, v in sorted((k, v) for k, v in e.resultats.items() if k.startswith("ligne ")):
                lignes.append(f"     {k} → {resultat(v)}")
            liens = sum(1 for c in e.cibles if c["tag"] == "a" and c["zone"] in ("page", "arbre"))
            liens += sum(1 for c in e.cibles if c["zone"] == "menu" and not self._court(c["texte"]))
            if liens:
                lignes.append(f"     autres liens : {liens}")
            if e.tronque:
                lignes.append("     (écran très chargé : seuls les premiers éléments ont été lus)")
            lignes.append("")
        if self.bloquees:
            lignes.append(f"ENVOIS DE DONNEES BLOQUES : {len(self.bloquees)} "
                          "(le détail des adresses est dans carte.html, sur votre poste)")
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
                res = e.resultats.get(self._cle(c), "")
                classe = "rouge" if ("bloqu" in res or res.startswith("non")) else ("vert" if res.startswith("mène") else "gris")
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
