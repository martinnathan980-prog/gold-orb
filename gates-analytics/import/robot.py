#!/usr/bin/env python3
"""
Le robot du Suivi FWD (débrief 28) : il regarde une fois comment on fait un
export, puis le refait tout seul chaque matin et dépose les fichiers dans le
tableau de bord.

    python robot.py preparer     une fois : se connecter à Google, CHILDNéo, SEE
    python robot.py apprendre    montrer un export (GATES d'un contrat, SEE…)
    python robot.py essayer      le robot refait les exports appris, devant vous
    python robot.py lancer       exports + dépôt dans le tableau de bord
    python robot.py activer      Windows le lance tout seul, une fois par jour, à partir de
                                 14 h (ou à l'ouverture de session / au retour devant
                                 l'écran, s'il n'est pas encore passé)
    python robot.py desactiver   plus de lancement automatique
    python robot.py etat         ce que le robot sait, et son dernier passage
    python robot.py navigateur   Chrome ou Edge (Edge reconnaît la session Windows)

Débrief 30 : tout se règle dans le tableau de bord (Administration → Contrats).
Chaque jour, le robot lit dans la fenêtre d'import les contrats du jour — ceux
qui ont un onglet, et ceux qu'on vient d'ajouter (« prévus ») — avec le nom
exact de leur tranche dans GATES, exporte GATES pour chacun, SEE une seule
fois, dépose tout, puis dit au tableau de bord ce qu'il a fait (son compte
rendu, contrat par contrat). Ses exports appris avant (« GATES HDK », « SEE
HDK » et « SEE ») se rangent tout seuls : rien à réapprendre.

Tout tient dans la bibliothèque standard de Python, plus piloter_chrome.py (à
côté). Le robot a son propre Chrome et son propre profil : vos onglets ne
sont jamais touchés, et il ne voit ni ne garde aucun mot de passe (un champ
« mot de passe » n'est jamais enregistré).

Ses fichiers vivent dans %LOCALAPPDATA%\\SuiviFWD (ailleurs : ~/.suivi-fwd) :
    robot.json          la configuration (adresse du tableau, exports appris)
    robot.avant-rangement.json  la même, telle qu'avant le rangement du débrief 30
    exports/*.json      un export appris = la suite des gestes
    chrome/             le profil du Chrome du robot (connexions gardées)
    telechargements/    où ses fichiers arrivent
    journal.txt         ce qu'il a fait, jour par jour
    dernier-passage.txt le passage du jour (« ok » : plus rien jusqu'à demain)
    essais-du-jour.txt  combien de passages ratés aujourd'hui (trois au plus, à 20 min)
    en-cours.txt        le verrou d'un passage en route (tombe de lui-même si le robot s'arrête)
"""

import base64
import contextlib
import datetime
import json
import os
import pathlib
import re
import select
import shutil
import subprocess
import sys
import threading
import time
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from piloter_chrome import SANS_PROXY, Chrome, ErreurPilote, _Canal  # noqa: E402

PORT = 9333
ADRESSES = {
    '1': ('CHILDNéo (GATES)', 'https://childneo.eu.eurocopter.corp/childneo-web/'),
    '2': ('SEE', 'https://see-v5-report-viewer.apps.studio.airbushelicopters.com/'),
}


# ---------------------------------------------------------------- lieux
def racine():
    base = os.environ.get('LOCALAPPDATA')
    r = pathlib.Path(base) / 'SuiviFWD' if base else pathlib.Path.home() / '.suivi-fwd'
    for sous in ('exports', 'telechargements', 'chrome', 'deposes'):
        (r / sous).mkdir(parents=True, exist_ok=True)
    return r


def config():
    f = racine() / 'robot.json'
    if f.exists():
        try:
            return json.loads(f.read_text(encoding='utf-8'))
        except ValueError:
            pass
    return {'tableau': '', 'exports': []}


def garder(cfg):
    (racine() / 'robot.json').write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding='utf-8')


def noter(texte):
    ligne = '%s  %s' % (datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), texte)
    print(texte)
    with open(racine() / 'journal.txt', 'a', encoding='utf-8') as f:
        f.write(ligne + '\n')


@contextlib.contextmanager
def verrou(silencieux=False):
    """Un seul robot à la fois : un passage automatique qui part pendant qu'on
    apprend un export, ou deux déclenchements presque ensemble, se
    marcheraient dessus (même fenêtre, même profil). Le second voit le
    passage en route et s'en va.

    Le verrou est celui du système (Windows : msvcrt.locking ; ailleurs :
    flock), posé sur en-cours.txt : il tombe de lui-même dès que le robot
    s'arrête, de quelque façon que ce soit — fenêtre noire fermée par sa
    croix, ordinateur éteint en plein passage. (Un simple fichier posé puis
    effacé restait derrière un robot arrêté net, et bloquait tout.)"""
    f = racine() / 'en-cours.txt'
    fh = open(f, 'a+')
    try:
        try:
            if os.name == 'nt':
                import msvcrt
                fh.seek(0)
                msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            if not silencieux:
                try:
                    age = int((time.time() - f.stat().st_mtime) // 60) + 1
                except OSError:
                    age = 0
                print('Le robot travaille déjà (depuis %d min) : sa fenêtre est ouverte. Réessayez quand il a fini.' % age)
            yield False
            return
        with contextlib.suppress(OSError):
            os.utime(f)                        # l'heure du début, pour « depuis … min »
        try:
            yield True
        finally:
            with contextlib.suppress(OSError):
                if os.name == 'nt':
                    import msvcrt
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_UN)
    finally:
        fh.close()


def nom_de_fichier(nom):
    return re.sub(r'[^A-Za-z0-9._-]+', '-', nom.strip()).strip('-').lower() or 'export'


def navigateur():
    """Le navigateur du robot : Chrome, ou Edge (il reconnaît de lui-même la
    session Windows, ce que certaines connexions demandent)."""
    return 'edge' if config().get('navigateur') == 'edge' else 'chrome'


def chemin_edge():
    for var in ('PROGRAMFILES(X86)', 'PROGRAMFILES', 'LOCALAPPDATA'):
        base = os.environ.get(var)
        if base:
            p = pathlib.Path(base) / 'Microsoft' / 'Edge' / 'Application' / 'msedge.exe'
            if p.exists():
                return str(p)
    return ''


def nom_navigateur():
    return 'Edge' if navigateur() == 'edge' else 'Chrome'


def chrome(visible=True, grand=True):
    r = racine()
    edge = navigateur() == 'edge'
    if edge and not os.environ.get('SUIVI_FWD_CHROME'):
        exe = chemin_edge()
        if not exe:
            raise ErreurPilote('Edge est introuvable sur ce poste : double-cliquez « Choisir le navigateur » '
                               'et reprenez Chrome.')
        os.environ['SUIVI_FWD_CHROME'] = exe
    options = ['--disable-features=DownloadBubble,DownloadBubbleV2,CalculateNativeWinOcclusion', '--hide-crash-restore-bubble',
               # Derrière d'autres fenêtres, la page du robot travaille au même pas (pas de ralenti).
               '--disable-backgrounding-occluded-windows', '--disable-renderer-backgrounding',
               '--disable-background-timer-throttling']
    options += ['--start-maximized'] if grand else ['--window-size=1280,900', '--window-position=40,40']
    options += json.loads(os.environ.get('SUIVI_FWD_OPTIONS_CHROME', '[]'))
    return Chrome(port=PORT, telechargements=str(r / 'telechargements'), lancer=True,
                  profil=str(r / ('edge' if edge else 'chrome')), sans_fenetre=not visible, delai=60, options=options)


# ---------------------------------------------------------------- le nom d'un champ
# Un champ se reconnaît à son NOM, pas à ce qu'on y a tapé : appris rempli
# (« 4530 »), il est vide le lendemain. Son nom : son <label>, son
# aria-labelledby, sinon le court intitulé posé juste avant lui (« PSN »).
# Le même calcul sert au guetteur (apprendre) et à la recherche (rejouer).
ETIQUETTE_JS = r"""
  var etiquetteDe = function (e) {
    var court = function (s) { var t = String(s || '').split('\n').map(function (x) { return x.trim(); }).filter(Boolean)[0] || '';
                               return t.length <= 40 ? t.replace(/\s+/g, ' ').replace(/\s*[:*]+\s*$/, '') : ''; };
    var t = '';
    try {
      if (e.labels && e.labels.length) t = court(e.labels[0].innerText);
      if (!t && e.getAttribute('aria-labelledby')) {
        var racine = e.getRootNode ? e.getRootNode() : document;
        t = court(e.getAttribute('aria-labelledby').split(/\s+/).map(function (id) {
          var x = racine.getElementById ? racine.getElementById(id) : document.getElementById(id); return x ? x.innerText : ''; }).join(' '));
      }
      for (var p = e, k = 0; !t && p && k < 4; k++, p = p.parentElement) {
        for (var s = p.previousElementSibling; !t && s; s = s.previousElementSibling) {
          if (s.matches && s.matches('input,select,textarea,button')) break;
          t = court(s.innerText);
          if (s.querySelector && s.querySelector('input,select,textarea')) t = '';
        }
      }
    } catch (x) {}
    return t;
  };
  var estChamp = function (e) { return !!(e && e.matches && e.matches('input:not([type]),input[type=text],input[type=search],input[type=email],input[type=number],input[type=date],input[type=tel],textarea,select')); };
  /* Un bouton sans texte (une icône) : son nom est souvent dans une bulle
     d'aide posée en attribut (mattooltip, ptooltip, data-tooltip,
     data-original-title…), son dessin dans une icône (data-icon, fa-…,
     pi-…, mdi-…, <use href="#…">), parfois un identifiant de test. */
  var bulleDe = function (e) {
    var at = e.attributes || [];
    for (var i = 0; i < at.length; i++) {
      var n = at[i].name, v = String(at[i].value || '').trim();
      if (/tooltip|^data-(original-)?title$|^aria-description$/i.test(n) && v && v.length <= 80 && !/^[\[{(]/.test(v)) return v;
    }
    return '';
  };
  var iconeDe = function (e) {
    var x = e.querySelector && e.querySelector('svg[data-icon],use,mat-icon,i[class],span[class*="icon"],[class*="fa-"],[class*="pi-"],[class*="mdi-"]');
    if (!x) return '';
    var b = x.tagName.toLowerCase();
    if (x.getAttribute('data-icon')) return x.getAttribute('data-icon');
    if (b === 'use') return String(x.getAttribute('href') || x.getAttribute('xlink:href') || '').replace(/^.*#/, '');
    if (b === 'mat-icon') return String(x.getAttribute('svgicon') || x.getAttribute('fonticon') || x.textContent || '').trim();
    return String(x.getAttribute('class') || '').split(/\s+/).filter(function (k) {
      return /^(fa|pi|mdi|bi|icon|glyphicon|material-icons)-[a-z0-9-]+$/i.test(k) && !/^(fa|pi|mdi|bi)-(fw|lg|xs|sm|\dx|solid|regular|light|spin|pulse)$/i.test(k);
    }).join(' ');
  };
  var testidDe = function (e) {
    var a = function (n) { return e.getAttribute(n) || ''; };
    return a('data-testid') || a('data-test-id') || a('data-test') || a('data-cy') || a('data-qa') || a('data-automation-id');
  };
"""


# ---------------------------------------------------------------- le guetteur
# Injecté dans chaque page : il dit au robot chaque clic, chaque champ rempli,
# chaque choix dans une liste ; il garde tout dans le même onglet (un lien
# « nouvel onglet » s'ouvre ici) pour que le robot puisse suivre — sauf sur
# les pages de connexion et dans les cadres, laissés tels quels : une
# connexion (Keycloak, SSO…) s'ouvre parfois dans une petite fenêtre qui
# doit rester à part, sinon la page reste blanche.
GUETTEUR = r"""
(function () {
  if (window.__suiviFwdGuette) return; window.__suiviFwdGuette = true;
  var envoyer = function (o) { try { window.__suiviFwd(JSON.stringify(o)); } catch (e) {} };
/*ETIQUETTE*/
  /* Ce qu'on tape s'écrit dès la frappe (« input ») : une liste de suggestions
     (taper 4530, puis cliquer « 4530 » dans la liste) ne laisse souvent
     passer aucun « change ». La frappe est regroupée, et toujours écrite
     AVANT le geste suivant, pour garder l'ordre. */
  var frappe = null;
  var vider = function () { if (frappe) { var f = frappe; frappe = null; clearTimeout(f.m); envoyer(f.geste); } };
  var dire = function (o) { vider(); envoyer(o); };
  /* La vraie cible, même dans un composant à racine fantôme (shadow DOM). */
  var cibleDe = function (ev) { var p = ev.composedPath ? ev.composedPath() : []; return (p[0] && p[0].nodeType === 1) ? p[0] : ev.target; };
  /* La première ligne seulement : un menu « GATES » qui contient ses sous-menus
     se décrit « GATES », pas « GATES Données MK1 Données MK2… ». */
  var premiere = function (s) { return String(s || '').split('\n').map(function (x) { return x.trim(); }).filter(Boolean)[0] || ''; };
  var texte = function (e) { return premiere(e.innerText || e.value).replace(/\s+/g, ' ').slice(0, 90); };
  var stable = function (id) { return id && !/\d{3,}|[:.]|^(mat|ng|ui|ext|gwt|react|ember|cdk|mui)[-_]/i.test(id); };
  var chemin = function (e) {
    var p = [];
    while (e && e.nodeType === 1 && p.length < 8) {
      var t = e.tagName.toLowerCase();
      if (stable(e.id)) { p.unshift(t + '#' + CSS.escape(e.id)); break; }
      var i = 1, s = e; while ((s = s.previousElementSibling)) if (s.tagName === e.tagName) i++;
      p.unshift(t + ':nth-of-type(' + i + ')'); e = e.parentElement;
    }
    return p.join(' > ');
  };
  var decrire = function (e) {
    var a = function (n) { return e.getAttribute(n) || ''; };
    var saisie = estChamp(e) && !e.matches('select');      // son contenu change : ce n'est pas son nom
    return { balise: e.tagName.toLowerCase(), id: stable(e.id) ? e.id : '', nom: a('name'), role: a('role'), type: a('type'),
             label: a('aria-label'), titre: a('title'), texte: saisie ? '' : texte(e), placeholder: a('placeholder'), href: a('href'),
             etiquette: estChamp(e) ? etiquetteDe(e) : '', bulle: bulleDe(e), icone: saisie || texte(e) ? '' : iconeDe(e),
             testid: testidDe(e), chemin: chemin(e), page: location.host + location.pathname };
  };
  var FORT = 'a,button,input,select,textarea,label,summary,option,[role=button],[role=link],[role=menuitem],[role=option],' +
             '[role=tab],[role=checkbox],[role=radio],[role=treeitem]';
  var FAIBLE = '[onclick],[role=gridcell],[role=row],td,th,li';
  /* Ce qu'on a cliqué : un bouton, un lien… ; sinon le mot lui-même s'il est
     court (un intitulé de menu) ; sinon sa case, sa ligne. */
  var cliquable = function (t) {
    var fort = t.closest && t.closest(FORT);
    if (fort) return fort;
    var mot = String(t.innerText || '').trim();
    if (mot && mot.length <= 40 && mot.indexOf('\n') === -1) return t;
    /* Une icône (un dessin svg) cliquée : le bouton qui la porte — le plus
       proche élément « à main » (cursor: pointer), pas le trait du dessin. */
    var svg = t.closest && t.closest('svg');
    if (svg) { while (svg.parentElement && svg.parentElement.closest('svg')) svg = svg.parentElement.closest('svg'); t = svg.parentElement || t; }
    for (var p = t, k = 0; p && p.nodeType === 1 && k < 4 && p !== document.body; k++, p = p.parentElement) {
      try { if (getComputedStyle(p).cursor === 'pointer') return p; } catch (x) {}
    }
    return (t.closest && t.closest(FAIBLE)) || t;
  };
  var CONNEXION = /keycloak|login|signin|sso|\/auth\b|oauth|adfs|openid-connect|saml|authorize/i;
  var libre = function (u) { return window.top === window && !CONNEXION.test(location.href) && !CONNEXION.test(String(u || '')); };
  var champ = function (e) { return estChamp(e) && !e.matches('select'); };
  document.addEventListener('click', function (ev) {
    if (!ev.isTrusted) return;            // un clic de la page elle-même (lien de téléchargement…)
    vider();
    var e = cliquable(cibleDe(ev));
    var a = ev.target.closest && ev.target.closest('a[target]');
    if (a && a.target !== '_self' && libre(a.href)) a.target = '_self';
    if (champ(e) || (e.matches && e.matches('select,input[type=password]'))) return;
    dire({ faire: 'cliquer', cible: decrire(e) });
  }, true);
  document.addEventListener('input', function (ev) {
    var e = cibleDe(ev); if (!champ(e) || !ev.isTrusted) return;
    if (frappe && frappe.e !== e) vider();
    if (frappe) clearTimeout(frappe.m);
    frappe = { e: e, geste: { faire: 'remplir', cible: decrire(e), texte: e.value } };
    frappe.m = setTimeout(vider, 800);
  }, true);
  document.addEventListener('change', function (ev) {
    var e = cibleDe(ev); if (!e.matches || e.matches('input[type=password]')) return;
    if (e.matches('select')) dire({ faire: 'choisir', cible: decrire(e), valeur: e.value, option: (e.options[e.selectedIndex] || {}).text || '' });
    else if (champ(e)) dire({ faire: 'remplir', cible: decrire(e), texte: e.value });
  }, true);
  document.addEventListener('keydown', function (ev) {
    var e = cibleDe(ev);
    if (ev.key === 'Enter' && champ(e)) { dire({ faire: 'remplir', cible: decrire(e), texte: e.value }); dire({ faire: 'entree', cible: decrire(e) }); }
  }, true);
  var ouvrir = window.open;
  window.open = function (u) {
    if (!libre(u)) return ouvrir.apply(window, arguments);
    if (u) location.href = u; return window;
  };
})();
"""

GUETTEUR = GUETTEUR.replace('/*ETIQUETTE*/', ETIQUETTE_JS)

# Retrouver un élément décrit, dans la page et ses cadres de même origine ;
# rend ses coordonnées à l'écran (pour un vrai clic de souris).
TROUVER = r"""
(function (d) {
/*ETIQUETTE*/
  var norm = function (s) { return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase(); };
  var premiere = function (s) { return String(s || '').split('\n').map(function (x) { return x.trim(); }).filter(Boolean)[0] || ''; };
  var vus = [];
  var visible = function (e) { var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  var parcourir = function (doc, dx, dy) {
    var liste = [].slice.call(doc.querySelectorAll(d.balise || '*'));
    liste.forEach(function (e) { vus.push({ e: e, dx: dx, dy: dy }); });
    /* Les composants à racine fantôme (shadow DOM) : leurs champs aussi. */
    [].slice.call(doc.querySelectorAll('*')).forEach(function (h) { if (h.shadowRoot) parcourir(h.shadowRoot, dx, dy); });
    [].slice.call(doc.querySelectorAll('iframe,frame')).forEach(function (f) {
      try { var r = f.getBoundingClientRect(); if (f.contentDocument) parcourir(f.contentDocument, dx + r.left, dy + r.top); } catch (x) {}
    });
  };
  parcourir(document, 0, 0);
  var parChemin = null;
  try { parChemin = d.chemin ? document.querySelector(d.chemin) : null; } catch (x) {}
  var meilleur = null, note = 0;
  vus.forEach(function (v) {
    var e = v.e; if (!visible(e)) return;
    var n = 0, a = function (k) { return e.getAttribute(k) || ''; };
    if (d.id && e.id === d.id) n += 10;
    if (d.nom && a('name') === d.nom) n += 6;
    if (d.label && a('aria-label') === d.label) n += 6;
    var lu = norm(premiere(e.innerText || e.value));
    /* Un export fait pour chaque contrat : l'élément qui portait le nom du
       contrat appris doit porter celui du contrat demandé, en mot entier —
       sinon il n'est jamais pris (pas de clic sur un autre contrat). */
    if (d.contient) {
      var c = norm(d.contient), i = lu.indexOf(c), bord = function (k) { return k < 0 || k >= lu.length || !/[a-z0-9]/.test(lu.charAt(k)); };
      if (i === -1 || !bord(i - 1) || !bord(i + c.length)) return;
      n += 4;
    }
    if (d.texte && lu === norm(d.texte)) n += 6;
    else if (d.texte && lu && norm(d.texte).indexOf(lu) === 0) n += 3;   // appris avec ses sous-menus ouverts
    if (d.etiquette && estChamp(e) && norm(etiquetteDe(e)) === norm(d.etiquette)) n += 6;   // le champ « PSN »
    if (d.titre && a('title') === d.titre) n += 4;
    if (d.placeholder && a('placeholder') === d.placeholder) n += 4;
    if (d.bulle && bulleDe(e) === d.bulle) n += 5;                    // « Export all », en bulle d'aide
    if (d.testid && testidDe(e) === d.testid) n += 8;
    if (d.icone && iconeDe(e) === d.icone) n += 3;
    if (d.href && a('href') === d.href) n += 3;
    if (d.role && a('role') === d.role) n += 1;
    if (d.type && a('type') === d.type) n += 1;
    if (parChemin === e) n += 4;
    if (n > note) { note = n; meilleur = v; }
  });
  if (!meilleur || note < 4) return null;
  var e = meilleur.e; e.scrollIntoView({ block: 'center', inline: 'center' });
  var r = e.getBoundingClientRect();
  window.__suiviCible = e;
  /* Pas encore prêt : grisé, dans une zone qui charge, ou couvert (un voile
     de chargement par-dessus) — le robot attend avant de cliquer. */
  var gris = e.disabled === true || e.getAttribute('aria-disabled') === 'true' || !!(e.closest && e.closest('[aria-busy="true"]'));
  var couvert = false;
  if (d.dessus && !meilleur.dx && !meilleur.dy && (!e.getRootNode || e.getRootNode() === document)) {
    var h = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    couvert = !!h && h !== e && !e.contains(h) && !h.contains(e);
  }
  return { x: meilleur.dx + r.left + r.width / 2, y: meilleur.dy + r.top + r.height / 2, note: note,
           attendre: gris || couvert, pourquoi: gris ? 'grisé' : couvert ? 'couvert' : '' };
})(%s)
"""
TROUVER = TROUVER.replace('/*ETIQUETTE*/', ETIQUETTE_JS)

# Les requêtes en cours de la page (XMLHttpRequest et fetch), comptées : une
# page qui calcule (SEE, une trentaine de secondes après « Submit ») n'est pas
# prête. Les sondes qui ne s'arrêtent jamais (mesure d'audience, attente
# longue) ne comptent pas.
RESEAU_JS = r"""
(function () {
  if (window.__suiviReseau) return; window.__suiviReseau = true; window.__suiviEnVol = 0;
  var sonde = /signalr|socket|poll|heartbeat|keepalive|analytics|collect|telemetry|matomo|piwik|dynatrace|newrelic|appdynamics|beacon|\/rb_/i;
  var debut = function (u) { if (sonde.test(String(u || ''))) return false; window.__suiviEnVol++; return true; };
  var fin = function () { window.__suiviEnVol = Math.max(0, window.__suiviEnVol - 1); };
  var ouvrir = XMLHttpRequest.prototype.open, envoyer = XMLHttpRequest.prototype.send;
  XMLHttpRequest.prototype.open = function (m, u) { this.__suiviUrl = u; return ouvrir.apply(this, arguments); };
  XMLHttpRequest.prototype.send = function () {
    if (debut(this.__suiviUrl)) { var x = this, fait = false; x.addEventListener('loadend', function () { if (!fait) { fait = true; fin(); } }); }
    return envoyer.apply(this, arguments);
  };
  if (window.fetch) {
    var chercher = window.fetch;
    window.fetch = function (r) {
      var compte = debut(typeof r === 'string' ? r : r && r.url), p = chercher.apply(this, arguments);
      if (compte) p.then(fin, fin);
      return p;
    };
  }
})();
"""

# La page est-elle calme ? Aucune requête en cours, aucun signe de chargement
# visible (aria-busy, barre de progression sans valeur, roue « spinner »,
# « loading », « loader »…).
CALME_JS = r"""
(function () {
  var vu = function (e) { var r = e.getBoundingClientRect(), s = getComputedStyle(e);
    return r.width > 0 && r.height > 0 && s.visibility !== 'hidden' && s.display !== 'none' && parseFloat(s.opacity || '1') > 0.05; };
  var roue = /(^|[-_])(spinner|loader|loading|busy|spinning)($|[-_])/i, pas = /container|wrapper|nested|blur|done|finished/i;
  var occupe = [].slice.call(document.querySelectorAll('[aria-busy="true"],[role="progressbar"]:not([aria-valuenow]),[class*="spin"],[class*="load"],[class*="busy"]'))
    .some(function (e) {
      if (e.matches('[aria-busy="true"],[role="progressbar"]')) return vu(e);
      return String(e.getAttribute('class') || '').split(/\s+/).some(function (k) { return roue.test(k) && !pas.test(k); }) && vu(e);
    });
  return { enVol: window.__suiviEnVol || 0, occupe: occupe };
})()
"""

# Les boutons visibles, avec leur nom : dit dans l'erreur quand un bouton
# n'est pas retrouvé.
BOUTONS_VISIBLES = r"""
(function () {
/*ETIQUETTE*/
  var vus = [];
  [].slice.call(document.querySelectorAll('button,a,[role=button],[role=menuitem],[role=option],[role=tab]')).forEach(function (e) {
    var r = e.getBoundingClientRect();
    if (r.width > 0 && r.height > 0 && vus.length < 20) {
      var nom = String(e.innerText || '').split('\n')[0].trim() || e.getAttribute('aria-label') || e.getAttribute('title') || bulleDe(e) ||
                (iconeDe(e) ? 'icône ' + iconeDe(e) : '');
      if (nom && vus.indexOf('« ' + nom.slice(0, 40) + ' »') === -1) vus.push('« ' + nom.slice(0, 40) + ' »');
    }
  });
  return vus;
})()
""".replace('/*ETIQUETTE*/', ETIQUETTE_JS)

# Les champs visibles de la page, avec leur nom : dit dans l'erreur quand un
# champ n'est pas retrouvé, pour comprendre sans y être.
CHAMPS_VISIBLES = r"""
(function () {
/*ETIQUETTE*/
  var vus = [], parcourir = function (doc) {
    [].slice.call(doc.querySelectorAll('input,textarea,select')).forEach(function (e) {
      var r = e.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && estChamp(e)) vus.push(e);
    });
    [].slice.call(doc.querySelectorAll('*')).forEach(function (h) { if (h.shadowRoot) parcourir(h.shadowRoot); });
    [].slice.call(doc.querySelectorAll('iframe,frame')).forEach(function (f) { try { if (f.contentDocument) parcourir(f.contentDocument); } catch (x) {} });
  };
  parcourir(document);
  return vus.slice(0, 12).map(function (e) {
    var a = function (n) { return e.getAttribute(n) || ''; };
    return '« ' + (etiquetteDe(e) || a('aria-label') || a('placeholder') || a('name') || e.id || '?') + ' »' +
           (a('placeholder') ? ' [' + a('placeholder') + ']' : '') + (a('name') ? ' (' + a('name') + ')' : '');
  });
})()
""".replace('/*ETIQUETTE*/', ETIQUETTE_JS)


# ---------------------------------------------------------------- outils CDP
def lire_evenements(c, duree):
    """Les messages de Chrome pendant `duree` secondes (sans rien envoyer)."""
    fin = time.time() + duree
    sortie = []
    canal = c._canal
    while time.time() < fin:
        if not canal._reste:
            pret, _, _ = select.select([canal.prise], [], [], max(0.0, min(0.25, fin - time.time())))
            if not pret:
                continue
        sortie.append(json.loads(canal.recevoir()))
    return sortie


def fichiers(c):
    return {n for n in c.fichiers_presents() if not n.endswith(('.crdownload', '.tmp', '.part'))}


def attendre_page(c, delai=60):
    fin = time.time() + delai
    while time.time() < fin:
        try:
            if c.evaluer('document.readyState') == 'complete':
                return
        except ErreurPilote:
            pass
        time.sleep(0.4)


def nouvel_onglet(url):
    demande = urllib.request.Request('http://127.0.0.1:%d/json/new?%s' % (PORT, url), method='PUT')
    SANS_PROXY.open(demande, timeout=10).read()


def page_actuelle(c):
    try:
        return c.evaluer('location.host + location.pathname') or ''
    except ErreurPilote:
        return ''


# Les pages de connexion (Keycloak, SSO…) : le matin, la session est souvent
# encore ouverte et la page ne s'affiche pas — ses gestes sont alors sautés.
CONNEXION = re.compile(r'keycloak|login|signin|sso|/auth/|oauth|adfs|openid-connect|saml|authorize', re.I)


# ---------------------------------------------------------------- préparer
def preparer():
    cfg = config()
    print('\n=== Préparer le robot (une seule fois) ===\n')
    print('Une fenêtre %s va s\'ouvrir : c\'est celle du robot, avec trois onglets.' % nom_navigateur())
    print('Dans chacun, connectez-vous comme d\'habitude :')
    print('  1. le tableau de bord Suivi FWD (votre compte Google @airbus.com)')
    print('  2. CHILDNéo')
    print('  3. SEE (bouton « SEE-AH-PROD »)')
    if not cfg.get('tableau'):
        adr = input('\nCollez ici l\'adresse du tableau de bord (celle qui finit par /exec), puis Entrée :\n> ').strip()
        cfg['tableau'] = adr
        garder(cfg)
    with chrome(True) as c:
        c.ouvrir(cfg['tableau'])
        for _, (nom, url) in sorted(ADRESSES.items()):
            nouvel_onglet(url)
        input('\nQuand les trois onglets sont ouverts et connectés, revenez ici et appuyez sur Entrée.')
    noter('Robot préparé (tableau : %s).' % cfg['tableau'])
    print('\nC\'est noté. Le robot garde ces connexions dans son propre %s.' % nom_navigateur())


def court(url):
    return str(url or '').split('?')[0][:110]


def souci_reseau(methode, p, adresses):
    """Ce qui a échoué pendant le chargement (une réponse 401, 403, 500…, une
    demande refusée, une erreur de la page), en une ligne — ou ''. Montré
    pendant l'apprentissage : c'est ce qui dit pourquoi une page reste vide."""
    if methode == 'Network.responseReceived':
        r = p.get('response') or {}
        if int(r.get('status') or 0) >= 400 and not court(r.get('url')).endswith('favicon.ico'):
            return 'réponse %s de %s' % (r.get('status'), court(r.get('url')))
    elif methode == 'Network.loadingFailed' and not p.get('canceled') and p.get('errorText') != 'net::ERR_ABORTED':
        motif = (p.get('corsErrorStatus') or {}).get('corsError') or p.get('blockedReason') or p.get('errorText') or '?'
        return 'refusé (%s) : %s' % (motif, court(adresses.get(p.get('requestId'))))
    elif methode == 'Log.entryAdded':
        e = p.get('entry') or {}
        if e.get('level') == 'error':
            return 'erreur de la page : %s' % str(e.get('text', '')).split('\n')[0][:140]
    elif methode == 'Runtime.exceptionThrown':
        d = p.get('exceptionDetails') or {}
        texte = (d.get('exception') or {}).get('description') or d.get('text') or ''
        return 'erreur de la page : %s' % str(texte).split('\n')[0][:140]
    return ''


# ---------------------------------------------------------------- apprendre
def apprendre():
    cfg = config()
    print('\n=== Apprendre un export ===\n')
    print('Lequel ?')
    print('  1 = GATES : montrez UN contrat, le robot fera tous les autres de la même façon')
    print('  2 = SEE')
    print('  3 = un autre (une adresse à coller)')
    choix = input('> ').strip() or '1'
    if choix == '2':
        sorte, nom, depart = 'see', 'SEE', ADRESSES['2'][1]
    elif choix == '3':
        sorte = 'autre'
        depart = input('\nL\'adresse où il commence :\n> ').strip()
        nom = input('Son nom :\n> ').strip() or 'Export'
    else:
        sorte, nom, depart = 'gates', 'GATES', ADRESSES['1'][1]
    pas, stop = [], threading.Event()
    with chrome(True) as c:
        c.envoyer('Runtime.addBinding', name='__suiviFwd')
        c.envoyer('Page.addScriptToEvaluateOnNewDocument', source=GUETTEUR)
        avant = fichiers(c)
        for domaine in ('Network.enable', 'Log.enable'):
            try:
                c.envoyer(domaine)
            except ErreurPilote:
                pass
        adresses, signales = {}, set()
        c.ouvrir(depart)
        try:
            c.evaluer(GUETTEUR)
        except ErreurPilote:
            pass
        print('\nLa fenêtre du robot est ouverte. Faites votre export comme d\'habitude, jusqu\'au')
        print('fichier téléchargé. Le robot regarde (il ne garde aucun mot de passe).')
        if sorte == 'gates':
            print('Un seul contrat suffit (par exemple HDK) : tapez son nom comme d\'habitude.')
        print('Quand le fichier est arrivé, revenez ici et appuyez sur Entrée.\n')
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
        recus, apres = set(), None
        while not stop.is_set():
            try:
                for m in lire_evenements(c, 0.5):
                    if m.get('method') == 'Network.requestWillBeSent':
                        adresses[m['params'].get('requestId')] = (m['params'].get('request') or {}).get('url', '')
                    souci = souci_reseau(m.get('method'), m.get('params') or {}, adresses)
                    if souci and souci not in signales and len(signales) < 30:
                        signales.add(souci)
                        print('  ⚠ %s' % souci)
                    if m.get('method') == 'Page.frameNavigated' and not m['params']['frame'].get('parentId'):
                        print('  → page %s' % m['params']['frame'].get('url', '').split('?')[0][:110])
                    if m.get('method') == 'Runtime.bindingCalled' and m['params'].get('name') == '__suiviFwd':
                        geste = json.loads(m['params']['payload'])
                        if ajouter_geste(pas, geste):
                            print('  ✓ %s %s' % (geste['faire'], dire_geste(geste)))
            except ErreurPilote:
                print('La fenêtre du robot s\'est fermée.')
                break
            nouveaux = fichiers(c) - avant - recus
            for n in sorted(nouveaux):
                if not recus:
                    apres = len(pas)                 # le fichier est venu après ce geste (avant un éventuel log out)
                recus.add(n)
                print('  ✓ fichier reçu : %s' % n)
        if not recus:
            print('\nAucun fichier n\'est arrivé : l\'export n\'a pas été enregistré. Recommencez quand vous voulez.')
            return
        print('\nJe regarde les cases de la fenêtre d\'import du tableau de bord…')
        cases = cases_du_tableau(c, cfg)
    fichier = sorted(recus)[-1]
    extension = pathlib.Path(fichier).suffix or '.xlsx'
    scenario = {'nom': nom, 'depart': depart, 'etapes': pas, 'fichier': '*' + extension, 'telechargement_apres': apres,
                'appris': datetime.datetime.now().isoformat(timespec='seconds')}
    entree = {'nom': nom}
    anciens = cfg.get('exports', [])
    if sorte == 'gates':
        contrats = contrats_du_tableau(cases)
        appris, contrat = reperer_contrat(pas, contrats)
        if not appris:
            print('\nJe ne trouve pas le nom du contrat dans ce que vous avez fait : rien n\'est enregistré.')
            print('Recommencez en tapant le nom du contrat dans GATES, comme d\'habitude.')
            return
        noms = cfg.setdefault('noms_gates', {})
        if contrat and norm(appris) != norm(contrat):
            noms[contrat] = appris
        # Débrief 30 : le nom de chaque contrat dans GATES se donne dans sa fiche,
        # au tableau de bord : plus de question ici.
        print('\nLes noms dans GATES se règlent dans le tableau de bord : Administration → Contrats.')
        scenario['modele'] = {'appris': appris}
        entree['modele'] = True
        # Un seul export GATES, pour tous les contrats : ceux appris un par un avant s'en vont.
        remplaces = [e['nom'] for e in anciens if e.get('nom') != nom and str(e.get('case', '')).upper().startswith('GATES')]
        anciens = [e for e in anciens if e['nom'] not in remplaces]
        if remplaces:
            print('\nRemplacés par celui-ci, qui fait tous les contrats : %s.' % ', '.join(remplaces))
        if contrats:
            print('\nChaque jour, le robot refera cet export pour : %s.' % ', '.join(
                c + ('' if norm(noms.get(c, c)) == norm(c) else ' (« %s » dans GATES)' % noms[c]) for c in contrats))
        print('Un contrat ajouté plus tard au tableau de bord sera pris tout seul, sous son nom.')
    elif sorte == 'see':
        autres = [n for n in cases if not n.upper().startswith('GATES')]
        entree['case'] = autres[0] if len(autres) == 1 else choisir_case(cases, 'SEE')
    else:
        entree['case'] = choisir_case(cases, nom if nom.upper().startswith('GATES') else 'GATES ' + nom)
    if entree.get('case'):
        # Débrief 30 : l'export qu'on vient de montrer passe en premier pour sa case
        # (les autres de la même case restent en secours).
        (cfg.get('reussis') or {}).pop(norm(entree['case']), None)
    f = racine() / 'exports' / (nom_de_fichier(nom) + '.json')
    f.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding='utf-8')
    entree['scenario'] = f.name
    # Ses secours (les autres exportations de la même case) ne se perdent pas.
    remplacee = next((e for e in anciens if e.get('nom') == nom and norm(e.get('case')) == norm(entree.get('case'))), None)
    secours = [s for s in (remplacee or {}).get('secours') or [] if s != f.name]
    if secours and not entree.get('modele'):
        entree['secours'] = secours
    cfg['exports'] = [e for e in anciens if e.get('nom') != nom] + [entree]
    garder(cfg)
    noter('Appris : %s (%d gestes, fichier %s%s).' % (nom, len(pas), fichier,
          ', tous les contrats, appris sur « %s »' % scenario['modele']['appris'] if entree.get('modele') else ', case %s' % entree['case']))
    if input('\nLe robot essaie tout de suite, devant vous ? (o/n) ').strip().lower().startswith('o'):
        essayer([nom])


def ajouter_geste(pas, geste):
    """Un geste vu pendant qu'on apprend. La frappe qui continue dans le même
    champ remplace la précédente ; le même texte redit à la sortie du champ
    (« change » après la frappe) n'est pas un geste de plus. Rend True si
    quelque chose a changé."""
    meme = lambda x: x.get('faire') == 'remplir' and (x.get('cible') or {}).get('chemin') == (geste.get('cible') or {}).get('chemin')   # noqa: E731
    if geste.get('faire') == 'remplir':
        if pas and meme(pas[-1]):
            if pas[-1].get('texte') == geste.get('texte'):
                return False
            pas[-1] = geste
            return True
        if any(meme(x) and x.get('texte') == geste.get('texte') for x in pas[-3:]):
            return False
    pas.append(geste)
    return True


def norm(t):
    return re.sub(r'\s+', ' ', str(t or '')).strip().lower()


def contrats_du_tableau(cases):
    """« GATES HDK », « GATES THS »… → HDK, THS : les contrats que la fenêtre
    d'import du tableau de bord connaît aujourd'hui."""
    return [n[6:].strip() for n in cases if n.upper().startswith('GATES ') and n[6:].strip()]


def candidats_contrat(pas):
    """Les mots des gestes qui peuvent désigner un contrat : ce qu'on a tapé,
    choisi dans une liste ou cliqué (60 caractères au plus)."""
    candidats = []
    for g in pas or []:
        faire = g.get('faire')
        for t in ((g.get('texte'),) if faire == 'remplir' else (g.get('option'), g.get('valeur')) if faire == 'choisir'
                  else ((g.get('cible') or {}).get('texte'),) if faire == 'cliquer' else ()):
            t = str(t or '').strip()
            if t and len(t) <= 60 and t not in candidats:
                candidats.append(t)
    return candidats


def valeur_de(dico, cle):
    """dico[cle], la clé comparée sans tenir compte de la casse ni des espaces."""
    for k, v in (dico or {}).items():
        if norm(k) == norm(cle):
            return v
    return None


def mot_du_contrat(etapes, contrat, noms):
    """Débrief 30 : dans les gestes d'un export appris pour un seul contrat
    (« GATES HDK »), le mot qui le désigne — son nom, ou celui que le robot
    avait retenu pour lui dans GATES. '' s'il n'y est pas. Aucune question."""
    autre = norm(valeur_de(noms, contrat) or '')
    for t in candidats_contrat(etapes):
        if norm(t) == norm(contrat) or (autre and norm(t) == autre):
            return t
    # Sinon, un seul mot TAPÉ qui en est tout proche (« THSA » pour THS : le
    # même début, quatre lettres d'écart au plus).
    c = norm(contrat)
    proches = [t for t in candidats_contrat([g for g in etapes or [] if g.get('faire') == 'remplir'])
               if c and (norm(t).startswith(c) or c.startswith(norm(t))) and len(norm(t)) >= 2 and abs(len(norm(t)) - len(c)) <= 4]
    return proches[0] if len(proches) == 1 else ''


def reperer_contrat(pas, contrats):
    """Dans les gestes appris, le mot qui désigne le contrat : tapé dans un
    champ, choisi dans une liste, ou cliqué. Il est retrouvé seul quand il est
    le nom d'un contrat du tableau ; sinon on demande. Rend (le mot appris,
    le contrat du tableau qu'il désigne — ou '' si le tableau n'a rien dit)."""
    candidats = candidats_contrat(pas)
    for t in candidats:
        for c in contrats:
            if norm(t) == norm(c):
                return t, c
    tapes = [str(g.get('texte') or '').strip() for g in pas if g['faire'] == 'remplir' and str(g.get('texte') or '').strip()]
    tapes = [t for i, t in enumerate(tapes) if t not in tapes[:i]] or candidats[:12]
    if not tapes:
        return '', ''
    print('\nLequel de ces mots est le nom du contrat, tel que vous l\'avez tapé dans GATES ?')
    for i, t in enumerate(tapes, 1):
        print('  %d = %s' % (i, t))
    print('  0 = aucun')
    while True:
        r = input('> ').strip()
        if r == '0':
            return '', ''
        if r.isdigit() and 1 <= int(r) <= len(tapes):
            appris = tapes[int(r) - 1]
            break
        print('Un numéro entre 0 et %d, s\'il vous plaît.' % len(tapes))
    if not contrats:
        return appris, ''
    print('\nC\'est quel contrat du tableau de bord ?')
    for i, c in enumerate(contrats, 1):
        print('  %d = %s' % (i, c))
    while True:
        r = input('> ').strip()
        if r.isdigit() and 1 <= int(r) <= len(contrats):
            return appris, contrats[int(r) - 1]
        print('Un numéro entre 1 et %d, s\'il vous plaît.' % len(contrats))


def pour_le_contrat(scenario, appris, contrat, nom_gates):
    """Le scénario appris sur un contrat, refait pour un autre : le mot
    appris devient le nom du contrat demandé partout où il paraissait — le
    champ tapé, l'option choisie, le texte de ce qu'on cliquait. Ce qui le
    portait doit porter le nouveau nom (« contient ») : faute de quoi le robot
    s'arrête, plutôt que d'exporter un autre contrat à sa place."""
    motif = re.compile(r'(?<![A-Za-z0-9])' + re.escape(appris) + r'(?![A-Za-z0-9])', re.I)   # en mot entier
    sub = lambda t: motif.sub(lambda m: nom_gates, t) if isinstance(t, str) else t   # noqa: E731
    etapes = []
    for g in scenario['etapes']:
        g2 = dict(g)
        cible = dict(g.get('cible') or {})
        # Ce qu'on clique ou choisit doit porter le nouveau nom ; un champ où l'on
        # TAPE le nom, lui, est vide quand le robot arrive : rien à exiger de lui.
        if g.get('faire') != 'remplir' and motif.search(str(cible.get('texte') or '')):
            cible['contient'] = nom_gates
        for k in ('texte', 'label', 'titre'):
            if k in cible:
                cible[k] = sub(cible[k])
        g2['cible'] = cible
        for k in ('texte', 'valeur', 'option'):
            if k in g2:
                g2[k] = sub(g2[k])
        etapes.append(g2)
    return dict(scenario, etapes=etapes, nom='GATES ' + contrat)


# Débrief 30 : ce que la fenêtre d'import dit de ses cases — leurs étiquettes
# (« GATES HDK », « SEE »), et pour chaque case GATES son contrat, le nom
# exact de sa tranche dans GATES (la fiche du tableau de bord) et s'il est
# « prévu » (ajouté dans le tableau de bord, pas encore d'onglet). Une
# fenêtre d'avant n'a pas ces attributs : contrat vide, on se rabat sur les
# étiquettes.
TABLEAU_JS = ('(function(){var t=function(e){return e?e.textContent.replace(/\\s+/g," ").trim():"";};'
              'return {cases:[].map.call(document.querySelectorAll(".case:not(.nouvelle) .etiquette"),t),'
              'contrats:[].map.call(document.querySelectorAll(".case.gates:not(.nouvelle)"),function(k){'
              'return {contrat:k.getAttribute("data-contrat")||"",case:t(k.querySelector(".etiquette")),'
              'nom_gates:k.getAttribute("data-nom-gates")||"",prevu:k.getAttribute("data-prevu")==="1"};})};})()')


def adresse_import(cfg):
    return cfg['tableau'] + ('&' if '?' in cfg['tableau'] else '?') + 'page=import'


def lire_tableau(c, cfg):
    """La fenêtre d'import du tableau de bord, lue : {'cases': les étiquettes
    (« GATES HDK », « GATES HDK Tranche 2 »…, et celle de SEE), 'contrats':
    [{'contrat', 'case', 'nom_gates', 'prevu'}]}. Vide si la fenêtre ne
    s'ouvre pas."""
    vide = {'cases': [], 'contrats': []}
    if not cfg.get('tableau'):
        return vide
    try:
        c.ouvrir(adresse_import(cfg))
        cadre, ctx = cadre_import(c, delai=60)
        try:
            time.sleep(2)
            lu = dans_le_cadre(cadre, ctx, TABLEAU_JS) or {}
        finally:
            cadre._canal.fermer()
    except (ErreurPilote, OSError, ValueError):
        return vide
    return {'cases': [n for n in (lu.get('cases') or []) if n],
            'contrats': [k for k in (lu.get('contrats') or []) if isinstance(k, dict)]}


def cases_du_tableau(c, cfg):
    """Les cases de la fenêtre d'import, comme elles s'y lisent : le fichier
    appris ira dans l'une d'elles, choisie dans la liste plutôt que tapée
    (une lettre de travers, et le dépôt ne la trouvait pas). Vide si la
    fenêtre ne s'ouvre pas : on demande alors le nom, comme avant."""
    return lire_tableau(c, cfg)['cases']


def en_contrat(k):
    """Un contrat du jour, toujours sous la même forme : une chaîne (« HDK »,
    comme avant) devient {'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates':
    '', 'prevu': False}."""
    if isinstance(k, dict):
        contrat = str(k.get('contrat') or '').strip()
        return {'contrat': contrat, 'case': str(k.get('case') or '').strip() or 'GATES ' + contrat,
                'nom_gates': str(k.get('nom_gates') or '').strip(), 'prevu': bool(k.get('prevu'))}
    return {'contrat': str(k).strip(), 'case': 'GATES ' + str(k).strip(), 'nom_gates': '', 'prevu': False}


def contrats_lus(tableau):
    """Les contrats du jour, lus dans la fenêtre : ceux dont la case dit son
    contrat (data-contrat) ; avec une fenêtre d'avant, tirés des étiquettes
    « GATES … »."""
    lus = [en_contrat(k) for k in tableau.get('contrats') or [] if str(k.get('contrat') or '').strip()]
    if lus:
        return lus
    return [en_contrat(k) for k in contrats_du_tableau(tableau.get('cases') or [])]


def nom_gates_de(cfg, k):
    """Ce que le robot tape dans GATES pour ce contrat : le nom de sa fiche
    dans le tableau de bord d'abord (c'est là qu'il se règle), sinon ce que
    le robot avait retenu (noms_gates), sinon le nom du contrat."""
    k = en_contrat(k)
    if k['nom_gates']:
        return k['nom_gates']
    for cle, v in (cfg.get('noms_gates') or {}).items():
        if norm(cle) == norm(k['contrat']) and str(v or '').strip():
            return str(v).strip()
    return k['contrat']


def choisir_case(cases, proposee):
    if not cases:
        return input('\nDans quelle case du tableau ce fichier va-t-il ? (Entrée = « %s ») :\n> ' % proposee).strip() or proposee
    print('\nDans quelle case du tableau de bord ce fichier va-t-il ? Tapez son numéro :')
    for i, n in enumerate(cases, 1):
        print('  %d = %s' % (i, n))
    defaut = next((i for i, n in enumerate(cases, 1) if n.lower() == proposee.lower()), None)
    while True:
        rep = input('> ' + ('(Entrée = %d) ' % defaut if defaut else '')).strip()
        if not rep and defaut:
            return cases[defaut - 1]
        if rep.isdigit() and 1 <= int(rep) <= len(cases):
            return cases[int(rep) - 1]
        print('Un numéro entre 1 et %d, s\'il vous plaît.' % len(cases))


# ---------------------------------------------------------------- rejouer
def souris(c, x, y):
    """Un clic comme une main : la souris arrive sur l'élément et s'y pose
    un instant (les menus qui s'ouvrent au survol, les bulles d'aide), puis
    le bouton gauche s'enfonce et se relâche."""
    c.envoyer('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y, buttons=0)
    time.sleep(0.3)
    c.envoyer('Input.dispatchMouseEvent', type='mousePressed', x=x, y=y, button='left', buttons=1, clickCount=1)
    time.sleep(0.08)
    c.envoyer('Input.dispatchMouseEvent', type='mouseReleased', x=x, y=y, button='left', buttons=0, clickCount=1)
    time.sleep(0.05)


DELAI_TROUVER = 300   # secondes pour qu'un élément paraisse et soit prêt (SEE calcule de 10 s à plus d'une minute)
DELAI_CALME = 300     # secondes au plus pour qu'une page finisse de calculer
DELAI_FICHIER = 1800  # secondes au plus pour qu'un gros fichier soit prêt et arrivé
DELAI_SUITE = 45      # secondes : après un clic, la suite doit paraître, sinon le robot réessaie autrement


def trouver(c, cible, delai=120):
    """Retrouve ce que décrit « cible » ; attend qu'il paraisse, puis qu'il
    soit prêt (ni grisé ni couvert par un voile de chargement). Prêt ou pas,
    au bout du délai il est pris quand même : le geste suivant dira si le
    clic n'a rien fait."""
    fin = time.time() + delai
    vu, dit = None, False
    while time.time() < fin:
        try:
            r = c.evaluer(TROUVER % json.dumps(cible))
            if r and not r.get('attendre'):
                return r
            if r:
                vu = r
                if not dit:
                    print('    (attente : %s %s)' % (nom_de_cible(cible), r.get('pourquoi')))
                    dit = True
        except ErreurPilote:
            pass
        time.sleep(0.5)
    if vu:
        return vu
    champ = cible.get('balise') in ('input', 'textarea', 'select')
    quoi = ('le champ « %s »' % (cible.get('etiquette') or cible.get('label') or cible.get('placeholder') or cible.get('nom') or '?')
            if champ else nom_de_cible(cible) or '« %s »' % cible.get('chemin'))
    try:
        vus = c.evaluer(CHAMPS_VISIBLES if champ else BOUTONS_VISIBLES) or []
    except ErreurPilote:
        vus = []
    raise ErreurPilote('Je ne retrouve plus %s sur la page %s. La page a peut-être changé : refaites '
                       '« Apprendre » pour cet export.%s' % (quoi, cible.get('page'),
                                                            ('\n  %s visibles à ce moment : ' % ('Champs' if champ else 'Boutons')) + ', '.join(vus) if vus else ''))


def nom_de_cible(cible):
    """Ce qu'on clique, dit en clair : son texte, son nom, sa bulle d'aide,
    son icône — « Export all », « icône file-excel » ; un champ, par son nom."""
    if cible.get('balise') in ('input', 'textarea', 'select'):
        return 'le champ « %s »' % (cible.get('etiquette') or cible.get('label') or cible.get('placeholder') or cible.get('nom') or '?')
    texte = cible.get('texte') or ''
    if texte and not re.search(r'\w', texte):   # un simple symbole (« ⇩ », « ⋮ ») : son vrai nom d'abord
        texte = cible.get('label') or cible.get('titre') or cible.get('bulle') or texte
    nom = texte or cible.get('label') or cible.get('titre') or cible.get('bulle')
    if nom:
        return '« %s »' % nom
    if cible.get('icone'):
        return '« icône %s »' % cible['icone']
    if cible.get('testid'):
        return '« %s »' % cible['testid']
    return ''


def attendre_calme(c, delai=None):
    """Après un clic : la page a fini de calculer — plus aucune requête en
    cours, plus de roue de chargement —, et le reste une seconde et demie.
    Au bout du délai, on continue quand même."""
    delai = DELAI_CALME if delai is None else delai
    fin, calme_depuis, dit = time.time() + delai, None, False
    while time.time() < fin:
        try:
            e = c.evaluer(CALME_JS) or {}
        except ErreurPilote:
            e = {}
        if not e.get('enVol') and not e.get('occupe'):
            calme_depuis = calme_depuis or time.time()
            if time.time() - calme_depuis >= 1.5:
                return True
        else:
            calme_depuis = None
            if not dit and time.time() > fin - delai + 3:
                print('    (la page calcule, le robot attend…)')
                dit = True
        time.sleep(0.5)
    return False


def vider_telechargements():
    """Le dossier de téléchargement du robot, vidé avant chaque export : un
    fichier du même nom qu'hier serait sinon écrasé sans se voir arriver."""
    for f in (racine() / 'telechargements').iterdir():
        try:
            f.unlink() if f.is_file() else shutil.rmtree(f)
        except OSError:
            pass


# Un clic qui ne fait rien (le menu « Export all » qui ne s'ouvre pas) : les
# autres façons d'appuyer, essayées l'une après l'autre jusqu'à ce que la
# suite paraisse.
APPUI_JS = r"""
(function (e) {
  var r = e.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height / 2;
  var o = { bubbles: true, cancelable: true, composed: true, clientX: x, clientY: y, button: 0, buttons: 1, view: window,
            pointerId: 1, pointerType: 'mouse', isPrimary: true };
  var tirer = function (t) { e.dispatchEvent(/^pointer/.test(t) && window.PointerEvent ? new PointerEvent(t, o) : new MouseEvent(t, o)); };
  ['pointerover', 'pointerenter', 'mouseover', 'mouseenter', 'pointerdown', 'mousedown'].forEach(tirer);
  if (e.focus) e.focus();
  o.buttons = 0;
  ['pointerup', 'mouseup', 'click'].forEach(tirer);
})(window.__suiviCible)
"""


# Le bouton cliqué ouvre-t-il un menu ? (aria-haspopup, aria-expanded, une
# classe « dropdown », « menu », « toggle », « split », « caret »)
EST_MENU_JS = r"""
(function (e) {
  if (!e) return false;
  var cls = String(e.getAttribute('class') || '') + ' ' + String((e.parentElement && e.parentElement.getAttribute('class')) || '');
  return !!(e.getAttribute('aria-haspopup') || e.hasAttribute('aria-expanded') || /dropdown|menu|toggle|split|caret/i.test(cls));
})(window.__suiviCible)
"""


def ouvre_un_menu(c, g, suivant):
    """Réessayer un clic n'est permis que pour un bouton qui ouvre un menu
    (« Export all » → « XLSX ») : recliquer « Submit » relancerait le calcul,
    ou créerait deux documents."""
    if not suivant:
        return False
    attendu = suivant.get('cible') or {}
    if MOT_FICHIER.search(nom_de_cible(g.get('cible') or {})):
        return True
    if attendu.get('balise') in ('li', 'option') or attendu.get('role') in ('menuitem', 'option', 'menuitemradio') or \
            re.search(r'menu|dropdown|popover|popup|overlay', attendu.get('chemin') or '', re.I):
        return True
    try:
        return bool(c.evaluer(EST_MENU_JS))
    except ErreurPilote:
        return False


def touche(c, nom, code, texte=None):
    for t in ('keyDown', 'keyUp'):
        c.envoyer('Input.dispatchKeyEvent', type=t, key=nom, code=nom if nom != ' ' else 'Space', windowsVirtualKeyCode=code,
                  nativeVirtualKeyCode=code, **({'text': texte} if texte and t == 'keyDown' else {}))


def present(c, cible):
    """La cible est-elle à l'écran (prête ou pas) ?"""
    try:
        return bool(c.evaluer(TROUVER % json.dumps(cible)))
    except ErreurPilote:
        return False


def attendre_presence(c, cible, delai):
    fin = time.time() + delai
    while time.time() < fin:
        if present(c, cible):
            return True
        time.sleep(0.5)
    return False


def verifier_clic(c, g, cible, suivant):
    """Après un clic, la suite doit paraître (le menu « XLSX » après
    « Export all »). Sinon, et si le bouton est toujours là (le clic n'a rien
    fait), le robot réessaie : un second clic, des événements envoyés au
    bouton lui-même, la touche Entrée, la flèche bas, Espace. Rien n'y fait :
    il le dit tout de suite, plutôt que de rester figé."""
    if not suivant or CONNEXION.search((suivant.get('cible') or {}).get('page', '')):
        return
    attendu = dict(suivant.get('cible') or {})
    if attendre_presence(c, attendu, DELAI_SUITE):
        return
    facons = [('un second clic', lambda r: souris(c, r['x'], r['y'])),
              ('un appui envoyé au bouton lui-même', lambda r: c.evaluer(APPUI_JS)),
              ('la touche Entrée', lambda r: (c.evaluer('window.__suiviCible.focus()'), touche(c, 'Enter', 13, '\r'))),
              ('la flèche bas', lambda r: (c.evaluer('window.__suiviCible.focus()'), touche(c, 'ArrowDown', 40))),
              ('la touche Espace', lambda r: (c.evaluer('window.__suiviCible.focus()'), touche(c, ' ', 32, ' ')))]
    for nom, faire in facons:
        try:
            r = c.evaluer(TROUVER % json.dumps(cible))
        except ErreurPilote:
            r = None
        if not r:
            break                                   # le bouton est parti : le clic a fait quelque chose, on attend la suite
        print('    (%s n\'est pas apparu : le robot réessaie, %s)' % (nom_de_cible(attendu) or 'la suite', nom))
        faire(r)
        time.sleep(0.4)
        attendre_calme(c, 60)
        if attendre_presence(c, attendu, 15):
            noter('    (« %s » : il a fallu %s)' % (nom_de_cible(cible).strip('« »') or 'ce bouton', nom))
            return
    else:
        try:
            vus = c.evaluer(BOUTONS_VISIBLES) or []
        except ErreurPilote:
            vus = []
        raise ErreurPilote('Après %s, %s n\'est jamais apparu (six façons d\'appuyer essayées).%s'
                           % (nom_de_cible(cible) or 'le clic', nom_de_cible(attendu) or 'la suite',
                              '\n  Boutons visibles à ce moment : ' + ', '.join(vus) if vus else ''))


def faire_geste(c, g, suivant=None):
    """Un geste appris, refait dans la fenêtre du robot (souris et clavier
    envoyés à la page elle-même : ni la souris ni le clavier de la personne).
    « suivant » : le geste d'après, pour vérifier qu'un clic a bien fait
    paraître la suite. Rend False pour une page de connexion inutile ce
    jour-là (sautée)."""
    cible = dict(g.get('cible') or {})
    if g['faire'] == 'cliquer':
        cible['dessus'] = True                       # un clic : rien ne doit couvrir le bouton
    facultatif = bool(CONNEXION.search(cible.get('page', '')))
    try:
        r = trouver(c, cible, delai=12 if facultatif else DELAI_TROUVER)
    except ErreurPilote:
        if facultatif and not CONNEXION.search(page_actuelle(c)):
            return False
        raise
    if g['faire'] == 'cliquer':
        menu = ouvre_un_menu(c, g, suivant)          # avant le clic : le bouton est encore celui-là
        souris(c, r['x'], r['y'])
        time.sleep(0.4)
        attendre_calme(c)                            # SEE calcule (« Submit ») : on attend qu'il ait fini
        if menu:
            try:
                verifier_clic(c, g, cible, suivant)
            except ErreurPilote as err:
                err.introuvable = False              # l'élément était là : c'est sa suite qui n'est pas venue
                raise
    elif g['faire'] == 'remplir':
        souris(c, r['x'], r['y'])                    # comme une personne : un clic dans le champ, d'abord
        c.evaluer('(function(e){e.focus(); if (e.select) e.select();})(window.__suiviCible)')
        c.envoyer('Input.insertText', text=g.get('texte', ''))
        # Une touche « Fin » : réveille les listes de suggestions qui écoutent le clavier.
        for t in ('keyDown', 'keyUp'):
            c.envoyer('Input.dispatchKeyEvent', type=t, key='End', code='End', windowsVirtualKeyCode=35, nativeVirtualKeyCode=35)
        c.evaluer('window.__suiviCible.dispatchEvent(new Event("change",{bubbles:true}))')
    elif g['faire'] == 'choisir':
        pris = c.evaluer('(function(e,v,t){var o=[].slice.call(e.options).filter(function(x){return x.value===v;})[0]'
                         '||[].slice.call(e.options).filter(function(x){return x.text===t;})[0]; if(!o) return false; e.value=o.value;'
                         'e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));return true;})'
                         '(window.__suiviCible,%s,%s)' % (json.dumps(g.get('valeur', '')), json.dumps(g.get('option', ''))))
        if pris is False:      # rien de choisi : la page garderait le choix d'avant (un autre contrat ?)
            raise ErreurPilote('Le choix « %s » n\'existe pas dans la liste « %s ».'
                               % (g.get('option') or g.get('valeur'), cible.get('etiquette') or cible.get('label') or cible.get('texte') or cible.get('nom') or '?'))
    elif g['faire'] == 'entree':
        c.evaluer('window.__suiviCible.focus()')
        for t in ('keyDown', 'keyUp'):
            c.envoyer('Input.dispatchKeyEvent', type=t, key='Enter', code='Enter', windowsVirtualKeyCode=13,
                      nativeVirtualKeyCode=13, **({'text': '\r'} if t == 'keyDown' else {}))
        time.sleep(0.4)
        attendre_calme(c)
    return True


def dire_geste(g):
    cible = g.get('cible') or {}
    if g['faire'] == 'remplir':
        return '« %s » dans le champ « %s »' % (g.get('texte', ''), cible.get('etiquette') or cible.get('label') or cible.get('placeholder') or cible.get('nom') or '?')
    if g['faire'] == 'choisir':
        return '« %s »' % (g.get('option') or g.get('valeur') or '')
    return nom_de_cible(cible) or '(un élément sans nom)'


MOT_FICHIER = re.compile(r'xlsx|xls|csv|excel|export|t[ée]l[ée]charg|download', re.I)


def indice_telechargement(scenario):
    """Après quel geste le fichier arrive-t-il ? Appris : noté au moment où le
    fichier est arrivé. Un export appris avant : le dernier geste qui parle
    de fichier (« XLSX », « Export »…). Sinon : à la fin."""
    etapes = scenario.get('etapes') or []
    k = scenario.get('telechargement_apres')
    if isinstance(k, int) and 1 <= k <= len(etapes):
        return k
    for i in range(len(etapes), 0, -1):
        g = etapes[i - 1]
        if g.get('faire') in ('cliquer', 'choisir') and MOT_FICHIER.search(dire_geste(g)):
            return i
    return len(etapes)


def rejouer(c, scenario, dossier_sortie):
    """Les gestes appris, un par un ; le fichier est attendu juste après le
    geste qui le fait venir — un gros fichier met du temps à se préparer,
    et le « log out » qui suit ne part qu'une fois le fichier arrivé."""
    vider_telechargements()
    avant = set()
    with contextlib.suppress(ErreurPilote):
        c.envoyer('Page.addScriptToEvaluateOnNewDocument', source=RESEAU_JS)   # chaque page : ses requêtes comptées
    c.ouvrir(scenario['depart'])
    for js in (GUETTEUR, RESEAU_JS):   # même onglet pour les liens « nouvel onglet » ; requêtes comptées
        with contextlib.suppress(ErreurPilote):
            c.evaluer(js)
    etapes = scenario['etapes']
    n, k_fichier, chemin = len(etapes), indice_telechargement(scenario), None
    for i, g in enumerate(etapes, 1):
        # Débrief 30 : une erreur dit sur quel geste elle est venue (err.geste) :
        # un clic qui exigeait le nom du contrat et ne l'a pas trouvé, c'est
        # GATES qui ne montre pas cette tranche.
        try:
            fait = faire_geste(c, g, etapes[i] if i < n and i != k_fichier else None)
        except ErreurPilote as err:
            if getattr(err, 'geste', None) is None:
                err.geste = g
            raise
        if not fait:
            print('  %d/%d (page de connexion inutile ce matin : sautée)' % (i, n))
            continue
        print('  %d/%d %s %s' % (i, n, g['faire'], dire_geste(g)))
        if i == k_fichier:
            print('    (le fichier se prépare : le robot attend qu\'il soit arrivé…)')
            try:
                chemin = c.attendre_telechargement(avant=avant, delai=DELAI_FICHIER, motif=scenario.get('fichier'))
            except ErreurPilote as err:
                err.geste, err.introuvable = g, False
                raise
            print('    ✓ fichier arrivé : %s' % chemin.name)
            attendre_calme(c, 60)
        time.sleep(1.2)
        attendre_page(c)
    if chemin is None:
        chemin = c.attendre_telechargement(avant=avant, delai=DELAI_FICHIER, motif=scenario.get('fichier'))
    dest = pathlib.Path(dossier_sortie) / (nom_de_fichier(scenario['nom']) + chemin.suffix)
    shutil.copy2(chemin, dest)
    return dest


def exports_choisis(noms=None):
    cfg = config()
    ranger_exports(cfg)
    liste = cfg.get('exports', [])
    if noms:
        liste = [e for e in liste if e['nom'] in noms]
    return cfg, liste


# ---------------------------------------------------------------- ranger les exports
# Débrief 30 : le robot range tout seul ce qu'il a appris, pour que personne
# n'ait rien à réapprendre :
# — un ancien export GATES fait pour un seul contrat (« GATES HDK », appris
#   avant le modèle « tous les contrats ») devient le modèle de tous, si le
#   nom du contrat se retrouve dans ses gestes ; à côté d'un modèle, il
#   s'efface (le nom qu'il tapait est gardé) ;
# — deux exportations pour la même case (« SEE HDK » et « SEE », toutes deux
#   dans la case SEE) : une seule est faite chaque jour, la plus récente (ou
#   celle qui a marché la dernière fois), l'autre reste en secours.
# Aucun fichier d'export n'est effacé ; robot.json est d'abord copié dans
# robot.avant-rangement.json (une fois).
_DEJA_DIT = set()


def lire_scenario(nom):
    """Le scénario d'un export appris (exports/<nom>), ou None s'il est illisible."""
    try:
        s = json.loads((racine() / 'exports' / str(nom or '')).read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return None
    return s if isinstance(s, dict) and isinstance(s.get('etapes', []), list) else None


def date_apprise(nom, scenario=None):
    """Quand cet export a été appris : sa date « appris », sinon celle de son fichier."""
    s = scenario if scenario is not None else lire_scenario(nom)
    if s and s.get('appris'):
        return str(s['appris'])
    try:
        return datetime.datetime.fromtimestamp((racine() / 'exports' / str(nom or '')).stat().st_mtime).isoformat(timespec='seconds')
    except OSError:
        return ''


def case_de(e):
    return str(e.get('case') or e.get('nom') or '').strip()


def est_gates(e):
    return bool(e.get('modele')) or case_de(e).upper().startswith('GATES')


def ranger_exports(cfg):
    """Range cfg['exports'] (voir plus haut). Rend True si quelque chose a
    changé. Un second appel ne change plus rien."""
    lus = []                                    # [entrée, scénario, date]
    for e in cfg.get('exports') or []:
        s = lire_scenario(e.get('scenario')) if isinstance(e, dict) else None
        lus.append([e, s, date_apprise(e.get('scenario'), s) if s is not None else ''])
    if not lus:
        return False
    avant = json.dumps(cfg, sort_keys=True, ensure_ascii=False)
    noms = dict(cfg.get('noms_gates') or {})
    dits, partent = [], []

    def retenir_nom(e, s):
        contrat = case_de(e)[6:].strip()
        mot = mot_du_contrat(s.get('etapes'), contrat, noms) if contrat else ''
        if mot and norm(mot) != norm(contrat) and valeur_de(noms, contrat) is None:
            noms[contrat] = mot

    # 1. GATES : un seul export, le modèle de tous les contrats.
    gates = sorted([x for x in lus if x[1] is not None and est_gates(x[0])], key=lambda x: x[2], reverse=True)
    modeles = [x for x in gates if x[0].get('modele')]
    anciens = [x for x in gates if not x[0].get('modele')]
    if modeles:
        partent = modeles[1:] + anciens
    elif anciens:
        x = anciens[0]
        e, s = x[0], x[1]
        contrat = case_de(e)[6:].strip()
        mot = mot_du_contrat(s.get('etapes'), contrat, noms) if contrat else ''
        if mot:
            s['modele'] = {'appris': mot, 'contrat': contrat, 'migre': True}
            (racine() / 'exports' / e['scenario']).write_text(json.dumps(s, ensure_ascii=False, indent=2), encoding='utf-8')
            x[0] = {'nom': 'GATES', 'scenario': e['scenario'], 'modele': True}
            if norm(mot) != norm(contrat) and valeur_de(noms, contrat) is None:
                noms[contrat] = mot
            dits.append('« %s » devient l’export GATES de tous les contrats (appris sur « %s »)' % (e.get('nom'), mot))
            partent = anciens[1:]
        elif e.get('scenario') not in _DEJA_DIT:
            _DEJA_DIT.add(e.get('scenario'))
            noter('%s : le nom du contrat n’est pas retrouvé dans ses gestes ; il reste l’export de %s seul.' % (case_de(e), contrat))
    for x in partent:
        if not x[0].get('modele'):
            retenir_nom(x[0], x[1])
        dits.append('« %s » n’est plus fait : l’export GATES de tous les contrats le remplace' % x[0].get('nom'))
    lus = [x for x in lus if not any(x is p for p in partent)]

    # 2. Une seule exportation par case ; les autres en secours.
    groupes = {}
    for x in lus:
        if x[1] is not None and not x[0].get('modele'):
            groupes.setdefault(norm(case_de(x[0])), []).append(x)
    for cle, xs in groupes.items():
        if len(xs) < 2:
            continue
        xs = sorted(xs, key=lambda x: x[2], reverse=True)
        reussi = (cfg.get('reussis') or {}).get(cle)
        principal = next((x for x in xs if x[0].get('scenario') == reussi), xs[0])
        autres = [x for x in xs if x is not principal]
        fichiers = []
        for x in [principal] + autres:
            for f in ([] if x is principal else [x[0].get('scenario')]) + list(x[0].get('secours') or []):
                if f and f != principal[0].get('scenario') and f not in fichiers:
                    fichiers.append(f)
        fichiers.sort(key=lambda f: date_apprise(f), reverse=True)
        principal[0] = dict(principal[0], secours=fichiers)
        dits.append('case %s : une seule exportation chaque jour, « %s » ; %s en secours' % (
            case_de(principal[0]), principal[0].get('nom'), ', '.join('« %s »' % x[0].get('nom') for x in autres)))
        lus = [x for x in lus if not any(x is a for a in autres)]

    cfg['exports'] = [x[0] for x in lus]
    if noms or 'noms_gates' in cfg:
        cfg['noms_gates'] = noms
    if json.dumps(cfg, sort_keys=True, ensure_ascii=False) == avant:
        return False
    f, copie = racine() / 'robot.json', racine() / 'robot.avant-rangement.json'
    if f.exists() and not copie.exists():
        shutil.copy2(f, copie)
    garder(cfg)
    noter('Exports rangés : %s. (Rien n’est effacé : la configuration d’avant est dans %s.)' % (' ; '.join(dits) or 'noms dans GATES retenus', copie.name))
    return True


def photo(c):
    """Ce que montrait la fenêtre du robot quand il a calé : une image et
    l'adresse de la page, pour comprendre sans y être."""
    try:
        image = c.envoyer('Page.captureScreenshot', format='png').get('data') or ''
        f = racine() / 'photo-du-robot.png'
        f.write_bytes(base64.b64decode(image))
        return '%s (page : %s)' % (f, page_actuelle(c))
    except (ErreurPilote, OSError, ValueError):
        return ''


def a_faire(cfg, liste, contrats):
    """Les exports du jour, un par case : l'export GATES appris sur un
    contrat devient un export par contrat du tableau de bord — ceux
    d'aujourd'hui, un contrat ajouté hier compris (« prévu », sans onglet
    encore) —, chacun dans sa case « GATES <contrat> », avec le nom de sa
    tranche dans GATES (celui de sa fiche d'abord). `contrats` : des noms,
    ou ce que lit contrats_lus. Une exportation qui a des secours les
    emporte (e['secours'] : [(fichier, scénario)], dans l'ordre où les
    essayer). Rend [(entrée, scénario)]."""
    travaux = []
    contrats = [en_contrat(k) for k in contrats or []]
    for e in liste:
        if not e.get('modele'):
            # La dernière qui a marché d'abord, puis la principale, puis les secours.
            fichiers = [e['scenario']] + [f for f in e.get('secours') or [] if f != e['scenario']]
            reussi = (cfg.get('reussis') or {}).get(norm(case_de(e)))
            if reussi in fichiers:
                fichiers.remove(reussi)
                fichiers.insert(0, reussi)
            charges = [(f, lire_scenario(f)) for f in fichiers]
            charges = [(f, s) for f, s in charges if s is not None]
            if not charges:
                raise ErreurPilote('L\'export appris « %s » est illisible (exports\\%s) : refaites « Apprendre » pour lui.' % (e.get('nom'), e['scenario']))
            tache = dict(e, fichier=charges[0][0], secours=charges[1:])
            travaux.append((tache, charges[0][1]))
            continue
        scenario = json.loads((racine() / 'exports' / e['scenario']).read_text(encoding='utf-8'))
        if not scenario.get('modele'):
            travaux.append((e, scenario))
            continue
        if not contrats:
            raise ErreurPilote('Je ne connais aucun contrat : la fenêtre d\'import du tableau de bord n\'en montre aucun.')
        appris = scenario['modele']['appris']
        for k in contrats:
            ng = nom_gates_de(cfg, k)
            travaux.append(({'nom': 'GATES ' + k['contrat'], 'case': k['case'] or 'GATES ' + k['contrat'], 'contrat': k['contrat'],
                             'nom_gates': ng, 'prevu': k['prevu']}, pour_le_contrat(scenario, appris, k['contrat'], ng)))
    return travaux


class Rate(str):
    """Un export raté, dit « nom : raison » comme avant ; il garde aussi son
    code (gates-introuvable…) et son contrat, pour le compte rendu."""
    code, contrat = '', ''


def rate(texte, code='', contrat=''):
    r = Rate(texte)
    r.code, r.contrat = code, contrat
    return r


def code_gates(err, nom_gates):
    """L'export GATES d'un contrat a calé : est-ce que GATES ne montre pas
    cette tranche (un élément qui devait porter son nom, introuvable), ou
    autre chose ?"""
    g = getattr(err, 'geste', None) or {}
    if getattr(err, 'introuvable', True) is not False:
        contient = (g.get('cible') or {}).get('contient')
        choix = ' '.join(str(g.get(k) or '') for k in ('option', 'valeur')) if g.get('faire') == 'choisir' else ''
        if contient or (nom_gates and norm(nom_gates) in norm(choix)):
            return 'gates-introuvable'
    return 'gates-export'


def faire_les_exports(c, cfg, liste, dossier, contrats):
    """Chaque export, l'un après l'autre. Un contrat qui cale n'arrête pas
    les autres : ce qui est sorti est rendu, et les ratés avec leur raison.
    Une exportation qui rate essaie ses secours ; celle qui marche est
    retenue pour la prochaine fois. Rend (sortis, ratés, comptes) — comptes :
    ce que le compte rendu au tableau de bord dira de chaque contrat GATES."""
    sortis, rates, comptes = [], [], []
    for e, scenario in a_faire(cfg, liste, contrats):
        noter('Export « %s »…' % e['nom'])
        essais = [(e.get('fichier'), scenario)] + list(e.get('secours') or [])
        premiere = None
        for i, (fichier, s) in enumerate(essais):
            if i:
                noter('  … son secours « %s »' % fichier)
            try:
                sortis.append((e, rejouer(c, s, dossier)))
            except ErreurPilote as err:
                vue = photo(c)
                noter('  ✗ %s%s' % (err, '\n  Photo de la fenêtre du robot : ' + vue if vue else ''))
                premiere = premiere or err
                continue
            noter('  ✓ %s' % sortis[-1][1].name)
            if i and fichier:
                cfg.setdefault('reussis', {})[norm(case_de(e))] = fichier
                garder(cfg)
                noter('  (la prochaine fois, « %s » passe en premier pour la case %s)' % (fichier, case_de(e)))
            break
        else:
            raison = str(premiere).split('\n')[0]
            if e.get('contrat'):
                ng = e.get('nom_gates') or e['contrat']
                code = code_gates(premiere, ng)
                message = ('GATES ne montre pas « %s » : vérifiez le « Nom exact de la tranche dans GATES » de ce contrat '
                           '(tableau de bord → Administration → Contrats).' % ng if code == 'gates-introuvable'
                           else 'L’export GATES de %s n’a pas abouti : %s' % (e['contrat'], raison))
                comptes.append({'contrat': e['contrat'], 'gates': {'ok': False, 'code': code, 'message': message, 'tape': ng}})
                rates.append(rate('%s : %s' % (e['nom'], raison), code, e['contrat']))
            else:
                rates.append(rate('%s : %s' % (e['nom'], raison)))
            continue
        if e.get('contrat'):
            # Réussi : le robot dit seulement ce qu'il a tapé ; c'est la fenêtre
            # d'import qui dira si l'export s'est bien importé.
            comptes.append({'contrat': e['contrat'], 'gates': {'tape': e.get('nom_gates') or e['contrat']}})
    return sortis, rates, comptes


def attendre_tableau(c, cfg, delai):
    """Le tableau de bord d'abord : ses cases disent les contrats du jour.
    Au retour devant l'écran, Google met parfois longtemps à répondre (le
    réseau de l'entreprise se remet en place) : le robot attend, sans
    compter d'essai raté, jusqu'à « delai » secondes. Rend ce que lit
    lire_tableau."""
    if not cfg.get('tableau'):
        raise ErreurPilote('Le robot ne connaît pas encore l\'adresse du tableau de bord : double-cliquez « 1 - Preparer ».')
    fin = time.time() + delai
    while True:
        tableau = lire_tableau(c, cfg)
        if tableau['cases']:
            return tableau
        if time.time() >= fin:
            raise ErreurPilote('Le tableau de bord ne répond pas (Google pas encore joignable, ou connexion Google à refaire : '
                               'double-cliquez « 1 - Preparer »).')
        noter('Le tableau de bord ne répond pas encore : nouvel essai dans 2 minutes.')
        time.sleep(120)


def essayer(noms=None):
    cfg, liste = exports_choisis(noms)
    if not liste:
        print('Aucun export appris : lancez d\'abord « apprendre ».')
        return
    dossier = racine() / 'deposes' / ('essai-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S'))
    dossier.mkdir(parents=True, exist_ok=True)
    with chrome(True) as c:
        try:
            contrats = contrats_lus(attendre_tableau(c, cfg, 120)) if any(e.get('modele') for e in liste) else []
            sortis, rates, _ = faire_les_exports(c, cfg, liste, dossier, contrats)
        except ErreurPilote as err:
            noter('✗ Essai interrompu : %s' % err)
            input('\nAppuyez sur Entrée pour fermer la fenêtre du robot.')
            return
        if rates:
            noter('✗ Essai : %d export(s) raté(s) — %s' % (len(rates), ' ; '.join(rates)))
            input('\nAppuyez sur Entrée pour fermer la fenêtre du robot.')
            return
    noter('Essai réussi : les fichiers sont dans %s' % dossier)
    print('\nTout est bon : le robot sait refaire %s.' % ', '.join(e['nom'] for e, _ in sortis))


# ---------------------------------------------------------------- déposer
def cadre_import(c, delai=90):
    """Le cadre de la fenêtre d'import dans la page du tableau de bord (Apps
    Script la sert dans un iframe d'une autre origine) : son canal, et le
    contexte JavaScript où vit la page d'import."""
    fin = time.time() + delai
    while time.time() < fin:
        for cible in json.loads(SANS_PROXY.open('http://127.0.0.1:%d/json/list' % PORT, timeout=5).read().decode()):
            if cible.get('type') != 'iframe' or 'googleusercontent' not in cible.get('url', ''):
                continue
            cadre = Chrome(port=PORT, delai=60)
            cadre._canal = _Canal(cible['webSocketDebuggerUrl'], 60)
            arbre = cadre.envoyer('Page.getFrameTree')['frameTree']
            pile = [arbre]
            while pile:
                f = pile.pop()
                pile.extend(f.get('childFrames', []))
                ctx = cadre.envoyer('Page.createIsolatedWorld', frameId=f['frame']['id'], worldName='robot')['executionContextId']
                r = cadre.envoyer('Runtime.evaluate', expression='!!document.getElementById("importer")', contextId=ctx, returnByValue=True)
                if r.get('result', {}).get('value'):
                    return cadre, ctx
            cadre._canal.fermer()
        time.sleep(2)
    raise ErreurPilote('La fenêtre d\'import du tableau de bord ne s\'est pas ouverte (connexion Google à refaire ? '
                       'lancez « preparer »).')


def dans_le_cadre(cadre, ctx, js, objet=False):
    r = cadre.envoyer('Runtime.evaluate', expression=js, contextId=ctx, returnByValue=not objet, awaitPromise=True)
    if r.get('exceptionDetails'):
        raise ErreurPilote('La fenêtre d\'import a répondu par une erreur : %s' % r['exceptionDetails'].get('text'))
    return r['result'] if objet else r['result'].get('value')


# Débrief 30 : les erreurs « de fiche » se corrigent dans le tableau de bord
# (Administration → Contrats) : un nouvel essai du robot n'y changerait rien.
# (« gates-introuvable » n'en est une que si un autre export GATES a marché
# dans le même passage : sinon c'est GATES ou CHILDNéo qui a changé.)
CODES_DE_FICHE = ('gates-introuvable', 'colonne-elec', 'colonne-harnais', 'see-aucune', 'douteux')
MESSAGE_MAX = 400          # caractères d'un message du compte rendu (le serveur en garde autant)
PASSAGE_MAX = 200          # caractères du résumé d'un passage

# La case où va un fichier : celle de son contrat (data-contrat), sinon par
# son étiquette, comme avant (une fenêtre d'avant n'a pas data-contrat).
CASE_JS = r"""
(function (contrat, nom) {
  var norm = function (s) { return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase(); };
  var k = null;
  if (contrat) k = [].slice.call(document.querySelectorAll('.case.gates:not(.nouvelle)')).filter(function (x) {
    return norm(x.getAttribute('data-contrat')) === norm(contrat); })[0] || null;
  if (!k && norm(nom) === 'see') { var s = document.querySelector('#case-see input.fichier'); if (s) return s; }
  if (!k) k = [].slice.call(document.querySelectorAll('.case')).filter(function (x) {
    var t = x.querySelector('.etiquette'); return t && norm(t.textContent) === norm(nom); })[0] || null;
  return k ? k.querySelector('input.fichier') : null;
})(%s, %s)
"""

# Les lectures sont-elles finies ? (plus de case en attente ou en lecture,
# plus de nom ni de PSN en cours de vérification)
LECTURES_FINIES_JS = '!document.querySelector(\'.case[data-etat="attente"], .case[data-etat="lecture"], [data-occupe]\')'

# Les cases dont la lecture a échoué (fichier illisible, colonne ELEC de la
# fiche absente de l'export…) : ce qu'elles disent, puis leur fichier retiré
# — les autres s'importent quand même.
ERREURS_JS = r"""
[].slice.call(document.querySelectorAll('.case[data-etat="erreur"]')).map(function (k) {
  var t = function (s) { var e = k.querySelector(s); return e ? e.textContent.replace(/\s+/g, ' ').trim() : ''; };
  var o = { see: k.classList.contains('see'), contrat: k.getAttribute('data-contrat') || '', etiquette: t('.etiquette'),
            code: k.getAttribute('data-code') || '', message: t('.lu').replace(/^✗\s*/, ''),
            porteurs: [].map.call(k.querySelectorAll('.porteur'), function (li) { return li.getAttribute('data-contrat') || ''; }) };
  var r = k.querySelector('button.retirer');
  if (r) r.click();
  return o;
})
"""

# Le doute de la fenêtre d'import (« seulement 3 plans sur 186 en commun avec
# « HDK » : est-ce bien son export ? ») : à la main, on regarde ; le robot,
# lui, n'importe pas ce fichier-là.
DOUTEUX_JS = r"""
[].slice.call(document.querySelectorAll('.case')).filter(function (k) {
  var n = k.querySelector('.note'); return n && !n.hidden && n.textContent.trim(); }).map(function (k) {
  var o = { contrat: k.getAttribute('data-contrat') || '', etiquette: k.querySelector('.etiquette').textContent.replace(/\s+/g, ' ').trim(),
            note: k.querySelector('.note').textContent.trim() };
  var r = k.querySelector('button.retirer'); if (r && !r.hidden) r.click();
  return o;
})
"""

# La fin de l'import : la consigne « ne pas fermer » est partie, « Fermer » revient.
FIN_IMPORT_JS = 'document.getElementById("consigne").hidden && !document.getElementById("fermer").disabled'

# Ce que dit la fenêtre à la fin : son bilan, s'il est en erreur, si son
# compte rendu est arrivé au serveur (data-rapport) et ses codes en échec.
BILAN_JS = r"""
(function () {
  var e = document.getElementById('etat');
  return { texte: e.innerText || '', erreur: e.classList.contains('erreur') || !!e.querySelector('.erreur'),
           rapport: e.getAttribute('data-rapport'), codes: e.hasAttribute('data-codes') ? e.getAttribute('data-codes') : null };
})()
"""

# Le pont : le robot (dans son monde isolé, sans google.script.run) écrit son
# compte rendu dans la fenêtre et clique « envoyer » : la fenêtre l'envoie au
# serveur pour lui.
PONT_JS = r"""
(function (t) {
  var p = document.getElementById('pont-robot'), a = document.getElementById('pont-robot-rapport'), b = document.getElementById('pont-robot-envoyer');
  if (!p || !a || !b) return false;
  p.setAttribute('data-etat', ''); p.removeAttribute('data-message');
  a.value = t; b.click();
  return true;
})(%s)
"""
PONT_ETAT_JS = ('(function(){var p=document.getElementById("pont-robot");'
                'return p ? {etat: p.getAttribute("data-etat") || "", message: p.getAttribute("data-message") || ""} : null;})()')


def coupe(texte, n):
    texte = re.sub(r'\s+', ' ', str(texte or '')).strip()
    return texte if len(texte) <= n else texte[:n - 1].rstrip() + '…'


def ouvrir_import(c, cfg):
    """La fenêtre d'import du tableau de bord, ouverte par le robot : son cadre,
    marqué « robot » (son compte rendu dira source « robot »)."""
    c.ouvrir(adresse_import(cfg))
    cadre, ctx = cadre_import(c)
    try:
        time.sleep(3)
        dans_le_cadre(cadre, ctx, 'document.body.setAttribute("data-robot","1")')
    except ErreurPilote:
        cadre._canal.fermer()
        raise
    return cadre, ctx


def envoyer_rapport(cadre, ctx, rapport, delai=60):
    """Le compte rendu du robot, envoyé au tableau de bord par le pont de la
    fenêtre d'import. Rend True s'il est arrivé ; une fenêtre d'avant (sans
    pont) rend False, sans erreur."""
    js = PONT_JS % json.dumps(json.dumps(rapport, ensure_ascii=False))
    fin = time.time() + delai
    try:
        if not dans_le_cadre(cadre, ctx, js):
            noter('  (la fenêtre d\'import n\'a pas de pont : pas de compte rendu au tableau de bord)')
            return False
        while time.time() < fin:
            time.sleep(1)
            e = dans_le_cadre(cadre, ctx, PONT_ETAT_JS) or {}
            if e.get('etat') == 'ok':
                return True
            if e.get('etat') == 'erreur':
                noter('  ✗ Compte rendu refusé par le tableau de bord : %s' % (e.get('message') or '?'))
                return False
            if e.get('etat') == 'occupe':           # la fenêtre finit un import : on renvoie un peu plus tard
                time.sleep(3)
                dans_le_cadre(cadre, ctx, js)
    except ErreurPilote as err:
        noter('  ✗ Compte rendu non envoyé : %s' % str(err).split('\n')[0])
        return False
    noter('  ✗ Compte rendu non envoyé : le tableau de bord n\'a pas répondu en %d s.' % delai)
    return False


def comptes_par_contrat(comptes):
    """Une entrée par contrat ; ce qui en est dit deux fois (ce qu'il a tapé,
    puis l'erreur de sa case) se réunit, messages coupés à MESSAGE_MAX."""
    vus, liste = {}, []
    for k in comptes:
        cle = norm(k.get('contrat'))
        if not cle:
            continue
        if cle not in vus:
            vus[cle] = {'contrat': k['contrat']}
            liste.append(vus[cle])
        for partie in ('gates', 'see'):
            if isinstance(k.get(partie), dict):
                d = vus[cle].setdefault(partie, {})
                d.update(k[partie])
                if 'message' in d:
                    d['message'] = coupe(d['message'], MESSAGE_MAX)
    return liste


def rapport_du_robot(cfg, debut, comptes, techniques, nb_fiche):
    """Le compte rendu d'un passage, tel que le tableau de bord le lit
    (importRapport) : le passage (réussi ou non, en une phrase), et ce qui
    est dit de chaque contrat."""
    return {'source': 'robot',
            'passage': {'ok': not techniques, 'message': coupe(' ; '.join(techniques), PASSAGE_MAX), 'heure': heure_du_robot(cfg),
                        'debut': debut, 'erreursFiche': nb_fiche},
            'contrats': comptes_par_contrat(comptes)}


def nb_de_fiche(comptes):
    return sum(1 for k in comptes_par_contrat(comptes) for p in ('gates', 'see')
               if (k.get(p) or {}).get('ok') is False and (k.get(p) or {}).get('code') in CODES_DE_FICHE)


def rendre_compte(c, cfg, comptes, debut, techniques):
    """Rien à déposer (tous les exports ont calé) : la fenêtre d'import est
    ouverte quand même, pour que le tableau de bord sache pourquoi."""
    res = {'douteux': [], 'techniques': [], 'fiche': [], 'rapport': False}
    try:
        cadre, ctx = ouvrir_import(c, cfg)
    except (ErreurPilote, OSError, ValueError) as err:
        noter('  ✗ Compte rendu non envoyé : %s' % str(err).split('\n')[0])
        return res
    try:
        n = nb_de_fiche(comptes) - sum(1 for r in techniques if getattr(r, 'code', '') in CODES_DE_FICHE)
        res['rapport'] = envoyer_rapport(cadre, ctx, rapport_du_robot(cfg, debut, comptes, [str(r) for r in techniques], max(0, n)))
    finally:
        cadre._canal.fermer()
    return res


def deposer(c, cfg, sortis, comptes=(), debut='', rates_techniques=()):
    """Les fichiers du jour, chacun dans sa case de la fenêtre d'import, puis
    l'import, puis le compte rendu du robot (par le pont). Une case qui ne
    s'importe pas (fichier illisible, colonne de la fiche absente, export
    douteux) est retirée : les autres s'importent. Rend {'douteux',
    'techniques' (ce qu'un nouvel essai pourrait réparer), 'fiche' (ce qui
    se corrige dans le tableau de bord), 'rapport' (le compte rendu est-il
    arrivé ?)}."""
    comptes = list(comptes)
    douteux, techniques, fiche, fiche_fenetre = [], [], [], 0
    cadre, ctx = ouvrir_import(c, cfg)
    try:
        try:
            cadre.envoyer('DOM.enable')
            for e, chemin in sortis:
                case = e.get('case') or e['nom']
                obj = dans_le_cadre(cadre, ctx, CASE_JS % (json.dumps(e.get('contrat') or ''), json.dumps(case)), objet=True)
                if not obj.get('objectId'):
                    dit = 'Pas de case « %s » dans la fenêtre d\'import du tableau de bord.' % case
                    noter('  ✗ ' + dit)
                    techniques.append(dit)
                    if e.get('contrat'):
                        comptes.append({'contrat': e['contrat'], 'gates': {'ok': False, 'code': 'autre', 'message': dit}})
                    continue
                cadre.envoyer('DOM.setFileInputFiles', files=[str(chemin)], objectId=obj['objectId'])
                noter('  ↑ %s → case « %s »' % (chemin.name, case))
            time.sleep(1)
            fin = time.time() + 600
            while time.time() < fin and not dans_le_cadre(cadre, ctx, LECTURES_FINIES_JS):
                time.sleep(1)
            # Les cases qui ne s'importent pas : dites, puis retirées.
            for k in dans_le_cadre(cadre, ctx, ERREURS_JS) or []:
                code = k.get('code') or 'lecture'
                qui = k.get('contrat') or k.get('etiquette') or '?'
                noter('  ✗ Pas importé : %s — %s' % (k.get('etiquette'), k.get('message')))
                if k.get('see'):
                    dit = 'L’extract %s ne se lit pas : %s' % (k.get('etiquette') or 'SEE', k.get('message'))
                    techniques.append(dit)
                    comptes.extend({'contrat': p, 'see': {'ok': False, 'code': code, 'message': dit}} for p in k.get('porteurs') or [] if p)
                    continue
                comptes.append({'contrat': qui, 'gates': {'ok': False, 'code': code, 'message': k.get('message') or 'Ce fichier ne se lit pas.'}})
                (fiche if code in CODES_DE_FICHE else techniques).append('%s : %s' % (k.get('etiquette'), k.get('message')))
            douteux = dans_le_cadre(cadre, ctx, DOUTEUX_JS) or []
            for d in douteux:
                noter('  ✗ Pas importé, par prudence : %s — %s' % (d.get('etiquette'), d.get('note')))
                comptes.append({'contrat': d.get('contrat') or d.get('etiquette'), 'gates': {'ok': False, 'code': 'douteux', 'message': d.get('note')}})
                fiche.append('%s : %s' % (d.get('etiquette'), d.get('note')))
            time.sleep(2)
            actifs = dans_le_cadre(cadre, ctx, 'document.querySelectorAll(\'.case[data-etat="lu"]\').length') or 0
            if not actifs:
                noter('  Rien à importer : aucun fichier ne s\'importe aujourd\'hui.')
            elif dans_le_cadre(cadre, ctx, 'document.getElementById("importer").disabled'):
                dit = 'La fenêtre d\'import refuse les fichiers : %s' % dans_le_cadre(cadre, ctx, 'document.getElementById("blocage").innerText')
                noter('  ✗ ' + dit)
                techniques.append(dit)
            else:
                dans_le_cadre(cadre, ctx, 'document.getElementById("importer").click()')
                fin = time.time() + 1800
                fini = False
                while time.time() < fin:
                    time.sleep(3)
                    if dans_le_cadre(cadre, ctx, FIN_IMPORT_JS):
                        fini = True
                        break
                b = dans_le_cadre(cadre, ctx, BILAN_JS) or {}
                noter(('✗ ' if b.get('erreur') else '✓ ') + 'Dépôt : ' + str(b.get('texte') or '').replace('\n', ' · ')[:600])
                codes = [x for x in str(b.get('codes') or '').split(',') if x]
                if not fini:
                    techniques.append('l’import n’a pas fini en 30 minutes')
                for x in codes:
                    if x == 'colonne-harnais':          # un avertissement : l'import est fait, le site le dit
                        noter('  ⚠ la colonne de la validation harnais d\'un contrat n\'est pas dans son export (voir le tableau de bord)')
                        continue
                    (fiche if x in CODES_DE_FICHE else techniques).append('la fenêtre d’import signale « %s »' % x)
                    if x in CODES_DE_FICHE:
                        fiche_fenetre += 1
                ligne = next((l.strip() for l in str(b.get('texte') or '').split('\n') if l.strip().startswith('✗')), '')
                codes = [x for x in codes if x != 'colonne-harnais']
                if b.get('erreur') and not codes:
                    techniques.append('le dépôt a signalé une erreur' + (' : ' + ligne.lstrip('✗ ') if ligne else ''))
                elif (b.get('erreur') or codes) and b.get('rapport') != 'ok':
                    techniques.append('le compte rendu de la fenêtre d’import n’est pas arrivé au tableau de bord')
        except ErreurPilote as err:
            dit = str(err).split('\n')[0]
            noter('  ✗ Dépôt interrompu : %s' % dit)
            techniques.append(dit)
        tech = [str(r) for r in rates_techniques] + techniques
        n = nb_de_fiche(comptes) + fiche_fenetre - sum(1 for r in rates_techniques if getattr(r, 'code', '') in CODES_DE_FICHE)
        rapport = envoyer_rapport(cadre, ctx, rapport_du_robot(cfg, debut, comptes, tech, max(0, n)))
    finally:
        cadre._canal.fermer()
    return {'douteux': douteux, 'techniques': techniques, 'fiche': fiche, 'rapport': rapport}


# ---------------------------------------------------------------- lancer
ESSAIS_PAR_JOUR = 3        # passages ratés au plus par jour, en automatique
ATTENTE_AUTO = 90          # secondes, avant le premier : laisser Windows et le réseau se poser
PAUSE_ESSAIS = 20 * 60     # secondes entre deux passages ratés, en automatique
ATTENTE_GOOGLE = 45 * 60   # secondes : le tableau de bord met parfois longtemps à répondre au réveil
HEURE_DEFAUT = '14:00'     # pas avant : le matin, l'ordinateur met une demi-heure à tout lancer


def heure_du_robot(cfg=None):
    h = str((cfg if cfg is not None else config()).get('heure') or HEURE_DEFAUT)
    return h if re.match(r'^([01]\d|2[0-3]):[0-5]\d$', h) else HEURE_DEFAUT


def trop_tot(cfg=None):
    return datetime.datetime.now().strftime('%H:%M') < heure_du_robot(cfg)


def fait_aujourd_hui():
    etat = racine() / 'dernier-passage.txt'
    return etat.exists() and etat.read_text(encoding='utf-8').startswith(datetime.date.today().isoformat() + ' ok')


def essais_du_jour():
    f = racine() / 'essais-du-jour.txt'
    try:
        jour, n = f.read_text(encoding='utf-8').split()
        return int(n) if jour == datetime.date.today().isoformat() else 0
    except (OSError, ValueError):
        return 0


def compter_essai():
    n = essais_du_jour() + 1
    (racine() / 'essais-du-jour.txt').write_text('%s %d' % (datetime.date.today().isoformat(), n), encoding='utf-8')
    return n


def prevenir(texte):
    """Un passage automatique raté : une petite fenêtre le dit (Windows), au
    lieu d'un journal que personne ne lit. Ailleurs, le journal suffit."""
    if os.name != 'nt':
        return
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, texte, 'Suivi FWD — le robot', 0x30 | 0x40000)   # ⚠, au premier plan
    except (AttributeError, OSError):
        pass


def lancer(auto=False):
    """auto : lancé par Windows (à l'heure du robot, 14 h par défaut ; à
    l'ouverture de session ou au retour devant l'écran s'il n'est pas encore
    passé). Une fois par jour : un passage réussi, et plus rien jusqu'au
    lendemain, quels que soient les redémarrages et les ouvertures de
    session. Avant l'heure, rien. Raté, il réessaie lui-même vingt minutes
    plus tard, trois passages au plus dans la journée, et ne dit rien avant
    le dernier. « Lancer maintenant » (sans auto) passe toujours, sauf si un
    passage est déjà en route."""
    if not auto:
        with verrou() as libre:
            return _passage(False)[0] if libre else 1
    if trop_tot() or fait_aujourd_hui() or essais_du_jour() >= ESSAIS_PAR_JOUR:
        return 0
    time.sleep(ATTENTE_AUTO)
    while not fait_aujourd_hui() and essais_du_jour() < ESSAIS_PAR_JOUR:
        with verrou(silencieux=True) as libre:
            if not libre or fait_aujourd_hui():     # un autre passage en route, ou fait entre-temps
                return 0
            code, raison = _passage(True)
        if code == 0:
            return 0
        if compter_essai() >= ESSAIS_PAR_JOUR:
            prevenir('Le robot n\'a pas pu mettre le tableau de bord à jour aujourd\'hui (%d essais).\n\n%s\n\n'
                     'Il réessaiera demain. Pour le faire maintenant : double-cliquez « Lancer maintenant ».\n'
                     'Pour le détail : « Etat du robot ».' % (ESSAIS_PAR_JOUR, raison[:400]))
            return 1
        noter('Nouvel essai dans %d minutes.' % (PAUSE_ESSAIS // 60))
        time.sleep(PAUSE_ESSAIS)
    return 0


def _passage(auto):
    """Un passage : le tableau de bord (ses contrats du jour, leur nom dans
    GATES), les exports, le dépôt, puis le compte rendu au tableau de bord.
    Rend (0, '') réussi, (1, la raison) sinon. Des exports ratés
    n'empêchent pas de déposer ceux qui sont sortis ; le passage compte
    alors comme raté (il sera refait) — sauf si ce qui a raté se corrige
    dans le tableau de bord (une erreur « de fiche » : nom GATES, colonne,
    PSN, export douteux) et que le tableau de bord l'a bien reçu : un nouvel
    essai n'y changerait rien, et le site le montre à côté du contrat."""
    cfg, liste = exports_choisis()
    etat = racine() / 'dernier-passage.txt'
    aujourd_hui = datetime.date.today().isoformat()
    if not liste or not cfg.get('tableau'):
        noter('Rien à faire : le robot n\'est pas encore préparé ou n\'a rien appris.')
        return 1, 'le robot n\'est pas encore préparé ou n\'a rien appris'
    dossier = racine() / 'deposes' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dossier.mkdir(parents=True, exist_ok=True)
    debut = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    noter('=== Passage du robot%s ===' % (' (automatique)' if auto else ''))
    try:
        with chrome(True, grand=not auto) as c:
            contrats = contrats_lus(attendre_tableau(c, cfg, ATTENTE_GOOGLE if auto else 120))
            sortis, rates, comptes = faire_les_exports(c, cfg, liste, dossier, contrats)
            # Une tranche que GATES ne montre pas, quand les autres sortent : c'est son nom, dans sa fiche.
            gates_ok = any(e.get('contrat') for e, _ in sortis)
            de_fiche = [r for r in rates if getattr(r, 'code', '') == 'gates-introuvable' and gates_ok]
            rates_tech = [r for r in rates if not any(r is f for f in de_fiche)]
            if sortis:
                res = deposer(c, cfg, sortis, comptes, debut, rates_tech)
            else:
                res = rendre_compte(c, cfg, comptes, debut, rates_tech)
            techniques = [str(r) for r in rates_tech] + res['techniques']
            fiche = [str(r) for r in de_fiche] + res['fiche']
            if techniques or (fiche and not res['rapport']):
                raise ErreurPilote('%s : %s' % ('pas tout' if sortis else 'rien', ' ; '.join(techniques + fiche)))
    except (ErreurPilote, OSError, ValueError) as err:
        noter('✗ Passage interrompu : %s' % err)
        etat.write_text('%s échec %s' % (aujourd_hui, err), encoding='utf-8')
        return 1, str(err).split('\n')[0]
    etat.write_text('%s ok %s' % (aujourd_hui, datetime.datetime.now().strftime('%H:%M')), encoding='utf-8')
    if fiche:
        noter('✓ Passage réussi — %d erreur(s) de fiche, visibles dans le tableau de bord : %s' % (len(fiche), ' ; '.join(fiche)))
    else:
        noter('✓ Passage réussi.')
    return 0, ''


# ---------------------------------------------------------------- navigateur
def choisir_navigateur():
    cfg = config()
    print('\n=== Le navigateur du robot ===\n')
    print('Aujourd\'hui : %s\n' % nom_navigateur())
    print('  1 = Chrome')
    print('  2 = Edge (il reconnaît de lui-même votre session Windows : à essayer si SEE reste blanc)')
    choix = input('> ').strip()
    if choix not in ('1', '2'):
        print('Rien n\'est changé.')
        return
    cfg['navigateur'] = 'edge' if choix == '2' else 'chrome'
    garder(cfg)
    noter('Navigateur du robot : %s.' % nom_navigateur())
    print('\nLe robot a son propre profil dans ce navigateur : il faut s\'y connecter une fois.')
    print('(Si un message dit que le navigateur « n\'a pas ouvert son canal », l\'entreprise le ferme')
    print(' au robot : revenez ici et reprenez l\'autre.)')
    if input('\nPréparer maintenant ? (o/n) ').strip().lower().startswith('o'):
        preparer()


# ---------------------------------------------------------------- planifier
def commande_robot(action):
    exe = pathlib.Path(sys.executable)
    sans_fenetre = exe.with_name('pythonw.exe')
    return '"%s" "%s" %s' % (sans_fenetre if sans_fenetre.exists() else exe, pathlib.Path(__file__).resolve(), action)


TACHE = 'Suivi FWD - robot'
ANCIENNES_TACHES = ('Suivi FWD - robot (matin)', 'Suivi FWD - robot (ouverture de session)')


def xml_tache(heure, commande, arguments, utilisateur, jour):
    """La tâche planifiée, en une : trois déclencheurs, une seule tâche.
    — l'heure du robot (14 h par défaut), chaque jour ;
    — l'ouverture de session (l'ordinateur éteint à 14 h, rallumé après) ;
    — le retour devant l'écran (déverrouillage : un portable refermé à
      14 h se rouvre sans nouvelle ouverture de session).
    Le robot ne passe qu'une fois par jour, et pas avant son heure (lancer) :
    une ouverture de session le matin, ou un déclenchement après le passage
    du jour, le trouvent trop tôt ou fait, et s'arrêtent aussitôt. Windows n'en lance
    jamais deux à la fois (IgnoreNew), rattrape l'heure manquée
    (StartWhenAvailable), et laisse faire sur batterie. Déclencheurs et
    compte : ceux de la personne connectée — c'est ce qu'un poste sans
    droits d'administrateur peut créer."""
    e = lambda t: (str(t).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))   # noqa: E731
    u = e(utilisateur)
    return ('<?xml version="1.0" encoding="UTF-16"?>\n'
            '<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">\n'
            '  <RegistrationInfo>\n'
            '    <Description>Suivi FWD : exports GATES et SEE, déposés dans le tableau de bord, une fois par jour.</Description>\n'
            '  </RegistrationInfo>\n'
            '  <Triggers>\n'
            '    <LogonTrigger>\n'
            '      <Enabled>true</Enabled>\n'
            '      <UserId>%(u)s</UserId>\n'
            '    </LogonTrigger>\n'
            '    <SessionStateChangeTrigger>\n'
            '      <Enabled>true</Enabled>\n'
            '      <StateChange>SessionUnlock</StateChange>\n'
            '      <UserId>%(u)s</UserId>\n'
            '    </SessionStateChangeTrigger>\n'
            '    <CalendarTrigger>\n'
            '      <StartBoundary>%(jour)sT%(heure)s:00</StartBoundary>\n'
            '      <Enabled>true</Enabled>\n'
            '      <ScheduleByDay>\n'
            '        <DaysInterval>1</DaysInterval>\n'
            '      </ScheduleByDay>\n'
            '    </CalendarTrigger>\n'
            '  </Triggers>\n'
            '  <Principals>\n'
            '    <Principal id="Author">\n'
            '      <UserId>%(u)s</UserId>\n'
            '      <LogonType>InteractiveToken</LogonType>\n'
            '      <RunLevel>LeastPrivilege</RunLevel>\n'
            '    </Principal>\n'
            '  </Principals>\n'
            '  <Settings>\n'
            '    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>\n'
            '    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>\n'
            '    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>\n'
            '    <AllowHardTerminate>true</AllowHardTerminate>\n'
            '    <StartWhenAvailable>true</StartWhenAvailable>\n'
            '    <RunOnlyIfNetworkAvailable>false</RunOnlyIfNetworkAvailable>\n'
            '    <IdleSettings>\n'
            '      <StopOnIdleEnd>false</StopOnIdleEnd>\n'
            '      <RestartOnIdle>false</RestartOnIdle>\n'
            '    </IdleSettings>\n'
            '    <AllowStartOnDemand>true</AllowStartOnDemand>\n'
            '    <Enabled>true</Enabled>\n'
            '    <Hidden>false</Hidden>\n'
            '    <RunOnlyIfIdle>false</RunOnlyIfIdle>\n'
            '    <WakeToRun>false</WakeToRun>\n'
            '    <ExecutionTimeLimit>PT6H</ExecutionTimeLimit>\n'
            '    <Priority>7</Priority>\n'
            '  </Settings>\n'
            '  <Actions Context="Author">\n'
            '    <Exec>\n'
            '      <Command>%(cmd)s</Command>\n'
            '      <Arguments>%(args)s</Arguments>\n'
            '    </Exec>\n'
            '  </Actions>\n'
            '</Task>\n') % {'u': u, 'jour': jour, 'heure': heure, 'cmd': e(commande), 'args': e(arguments)}


def activer():
    cfg = config()
    heure = input('À partir de quelle heure le robot passe-t-il ? (Entrée = %s) ' % heure_du_robot(cfg)).strip() or heure_du_robot(cfg)
    heure = heure.replace('h', ':').replace('H', ':')
    if re.match(r'^\d{1,2}:?$', heure):
        heure = '%02d:00' % int(heure.rstrip(':'))
    if not re.match(r'^([01]\d|2[0-3]):[0-5]\d$', heure):
        heure = HEURE_DEFAUT
    cfg['heure'] = heure
    garder(cfg)
    exe = pathlib.Path(sys.executable)
    sans_fenetre = exe.with_name('pythonw.exe')
    utilisateur = ('%s\\%s' % (os.environ.get('USERDOMAIN', ''), os.environ.get('USERNAME', ''))).lstrip('\\')
    f = racine() / 'tache.xml'
    f.write_text(xml_tache(heure, sans_fenetre if sans_fenetre.exists() else exe,
                           '"%s" auto' % pathlib.Path(__file__).resolve(), utilisateur,
                           datetime.date.today().isoformat()), encoding='utf-16')
    r = subprocess.run(['schtasks', '/create', '/tn', TACHE, '/xml', str(f), '/f'], capture_output=True, text=True)
    if r.returncode == 0:
        for nom in ANCIENNES_TACHES:               # celles d'avant (deux tâches) : remplacées
            subprocess.run(['schtasks', '/delete', '/tn', nom, '/f'], capture_output=True, text=True)
        noter('Lancement automatique activé : chaque jour à %s (sinon dès l\'ouverture de session ou le retour '
              'devant l\'écran qui suivent) — une seule fois par jour.' % heure)
        return
    # Repli : la tâche en une a été refusée — les deux tâches simples d'avant.
    noter('La tâche complète a été refusée (%s) : repli sur deux tâches simples.' % (r.stderr or r.stdout).strip()[:200])
    taches = [
        ['schtasks', '/create', '/tn', ANCIENNES_TACHES[0], '/tr', commande_robot('auto'),
         '/sc', 'daily', '/st', heure, '/f'],
        ['schtasks', '/create', '/tn', ANCIENNES_TACHES[1], '/tr', commande_robot('auto'),
         '/sc', 'onlogon', '/f'],
    ]
    for t in taches:
        r = subprocess.run(t, capture_output=True, text=True)
        print((r.stdout or r.stderr).strip())
    noter('Lancement automatique activé (repli) : chaque jour à %s, et à l\'ouverture de session qui suit '
          '(une seule fois par jour).' % heure)


def desactiver():
    for nom in (TACHE,) + ANCIENNES_TACHES:
        r = subprocess.run(['schtasks', '/delete', '/tn', nom, '/f'], capture_output=True, text=True)
        if r.returncode == 0:
            print((r.stdout or r.stderr).strip())
    noter('Lancement automatique désactivé.')


def montrer_etat():
    cfg = config()
    print('Tableau de bord : %s' % (cfg.get('tableau') or '(pas encore indiqué : lancez « preparer »)'))
    print('Navigateur      : %s' % nom_navigateur())
    print('Exports appris  : %s' % ('\n                  '.join(
        '%s → %s%s' % (e['nom'], 'tous les contrats du tableau' if e.get('modele') else 'case ' + str(e.get('case')),
                       ' (secours : %s)' % ', '.join(e['secours']) if e.get('secours') else '')
        for e in cfg.get('exports', [])) or 'aucun'))
    autres = {k: v for k, v in (cfg.get('noms_gates') or {}).items() if norm(k) != norm(v)}
    print('Noms dans GATES : réglés dans le tableau de bord (Administration → Contrats) ; à défaut : %s'
          % (', '.join('%s → « %s »' % kv for kv in sorted(autres.items())) if autres else 'le nom du contrat'))
    print('Heure du robot  : à partir de %s, une fois par jour' % heure_du_robot(cfg))
    etat = racine() / 'dernier-passage.txt'
    print('Dernier passage : %s' % (etat.read_text(encoding='utf-8') if etat.exists() else 'jamais'))
    n = essais_du_jour()
    if n and not fait_aujourd_hui():
        print('Aujourd\'hui     : %d passage(s) raté(s) sur %d permis' % (n, ESSAIS_PAR_JOUR))
    if os.name == 'nt':
        actif = any(subprocess.run(['schtasks', '/query', '/tn', t], capture_output=True, text=True).returncode == 0
                    for t in (TACHE,) + ANCIENNES_TACHES)
        print('Tout seul       : %s' % ('oui, une fois par jour' if actif else 'non (double-cliquez « 4 - Activer… »)'))
    print('Dossier         : %s' % racine())


def main(argv):
    action = argv[1] if len(argv) > 1 else 'etat'
    try:
        if action in ('preparer', 'apprendre', 'essayer'):
            with verrou() as libre:                # pas pendant un passage du robot
                if not libre:
                    return 1
                if action == 'preparer':
                    preparer()
                elif action == 'apprendre':
                    apprendre()
                else:
                    essayer(argv[2:] or None)
        elif action in ('lancer', 'auto'):
            return lancer(auto=(action == 'auto'))
        elif action == 'activer':
            activer()
        elif action == 'desactiver':
            desactiver()
        elif action == 'navigateur':
            choisir_navigateur()
        else:
            montrer_etat()
    except ErreurPilote as err:
        noter('✗ %s' % err)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
