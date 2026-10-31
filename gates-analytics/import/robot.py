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

Tout tient dans la bibliothèque standard de Python, plus piloter_chrome.py (à
côté). Le robot a son propre Chrome et son propre profil : vos onglets ne
sont jamais touchés, et il ne voit ni ne garde aucun mot de passe (un champ
« mot de passe » n'est jamais enregistré).

Ses fichiers vivent dans %LOCALAPPDATA%\\SuiviFWD (ailleurs : ~/.suivi-fwd) :
    robot.json          la configuration (adresse du tableau, exports appris)
    exports/*.json      un export appris = la suite des gestes
    chrome/             le profil du Chrome du robot (connexions gardées)
    telechargements/    où ses fichiers arrivent
    journal.txt         ce qu'il a fait, jour par jour
    dernier-passage.txt le passage du jour (« ok » : plus rien jusqu'à demain)
    essais-du-jour.txt  combien de passages ratés aujourd'hui (trois au plus, à 20 min)
    en-cours.txt        un passage est en route : un second attend son tour
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
    """Un seul robot à la fois : un passage du matin qui part pendant qu'on
    apprend un export, ou l'ouverture de session et le retour devant l'écran
    presque ensemble, se marcheraient dessus (même fenêtre, même profil).
    Le second voit le passage en route et s'en va. Un verrou de plus de deux
    heures est celui d'un passage coupé net (ordinateur éteint) : il ne
    bloque plus rien."""
    f = racine() / 'en-cours.txt'
    for _ in range(2):
        try:
            fd = os.open(str(f), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            try:
                age = time.time() - f.stat().st_mtime
            except OSError:
                continue
            if age > 2 * 3600:
                with contextlib.suppress(OSError):
                    f.unlink()
                continue
            if not silencieux:
                print('Le robot travaille déjà (depuis %d min). Réessayez quand il a fini.' % (age // 60 + 1))
            yield False
            return
        os.write(fd, ('%d %s' % (os.getpid(), datetime.datetime.now().isoformat(timespec='seconds'))).encode())
        os.close(fd)
        try:
            yield True
        finally:
            with contextlib.suppress(OSError):
                f.unlink()
        return
    yield False


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
  var dire = function (o) { try { window.__suiviFwd(JSON.stringify(o)); } catch (e) {} };
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
    return { balise: e.tagName.toLowerCase(), id: stable(e.id) ? e.id : '', nom: a('name'), role: a('role'), type: a('type'),
             label: a('aria-label'), titre: a('title'), texte: texte(e), placeholder: a('placeholder'), href: a('href'),
             chemin: chemin(e), page: location.host + location.pathname };
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
    return (t.closest && t.closest(FAIBLE)) || t;
  };
  var CONNEXION = /keycloak|login|signin|sso|\/auth\b|oauth|adfs|openid-connect|saml|authorize/i;
  var libre = function (u) { return window.top === window && !CONNEXION.test(location.href) && !CONNEXION.test(String(u || '')); };
  var champ = function (e) { return e.matches && e.matches('input:not([type]),input[type=text],input[type=search],input[type=email],input[type=number],input[type=date],textarea'); };
  document.addEventListener('click', function (ev) {
    if (!ev.isTrusted) return;            // un clic de la page elle-même (lien de téléchargement…)
    var e = cliquable(ev.target);
    var a = ev.target.closest && ev.target.closest('a[target]');
    if (a && a.target !== '_self' && libre(a.href)) a.target = '_self';
    if (champ(e) || (e.matches && e.matches('select,input[type=password]'))) return;
    dire({ faire: 'cliquer', cible: decrire(e) });
  }, true);
  document.addEventListener('change', function (ev) {
    var e = ev.target; if (!e.matches || e.matches('input[type=password]')) return;
    if (e.matches('select')) dire({ faire: 'choisir', cible: decrire(e), valeur: e.value, option: (e.options[e.selectedIndex] || {}).text || '' });
    else if (champ(e)) dire({ faire: 'remplir', cible: decrire(e), texte: e.value });
  }, true);
  document.addEventListener('keydown', function (ev) {
    var e = ev.target;
    if (ev.key === 'Enter' && champ(e)) { dire({ faire: 'remplir', cible: decrire(e), texte: e.value }); dire({ faire: 'entree', cible: decrire(e) }); }
  }, true);
  var ouvrir = window.open;
  window.open = function (u) {
    if (!libre(u)) return ouvrir.apply(window, arguments);
    if (u) location.href = u; return window;
  };
})();
"""

# Retrouver un élément décrit, dans la page et ses cadres de même origine ;
# rend ses coordonnées à l'écran (pour un vrai clic de souris).
TROUVER = r"""
(function (d) {
  var norm = function (s) { return String(s || '').replace(/\s+/g, ' ').trim().toLowerCase(); };
  var premiere = function (s) { return String(s || '').split('\n').map(function (x) { return x.trim(); }).filter(Boolean)[0] || ''; };
  var vus = [];
  var visible = function (e) { var r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  var parcourir = function (doc, dx, dy) {
    var liste = [].slice.call(doc.querySelectorAll(d.balise || '*'));
    liste.forEach(function (e) { vus.push({ e: e, dx: dx, dy: dy }); });
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
    if (d.titre && a('title') === d.titre) n += 3;
    if (d.placeholder && a('placeholder') === d.placeholder) n += 3;
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
  return { x: meilleur.dx + r.left + r.width / 2, y: meilleur.dy + r.top + r.height / 2, note: note };
})(%s)
"""


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
        recus = set()
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
                        if pas and geste.get('faire') == 'remplir' and pas[-1].get('faire') == 'remplir' and \
                                pas[-1]['cible'].get('chemin') == geste['cible'].get('chemin'):
                            pas[-1] = geste
                        else:
                            pas.append(geste)
                        print('  ✓ %s %s' % (geste['faire'], (geste.get('cible') or {}).get('texte') or geste.get('texte') or ''))
            except ErreurPilote:
                print('La fenêtre du robot s\'est fermée.')
                break
            nouveaux = fichiers(c) - avant - recus
            for n in sorted(nouveaux):
                recus.add(n)
                print('  ✓ fichier reçu : %s' % n)
        if not recus:
            print('\nAucun fichier n\'est arrivé : l\'export n\'a pas été enregistré. Recommencez quand vous voulez.')
            return
        print('\nJe regarde les cases de la fenêtre d\'import du tableau de bord…')
        cases = cases_du_tableau(c, cfg)
    fichier = sorted(recus)[-1]
    extension = pathlib.Path(fichier).suffix or '.xlsx'
    scenario = {'nom': nom, 'depart': depart, 'etapes': pas, 'fichier': '*' + extension,
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
        for autre in contrats:
            if autre != contrat and norm(appris) != norm(contrat or appris):
                vu = noms.get(autre, autre)
                r = input('Dans GATES, le contrat « %s » s\'écrit comment ? (Entrée = %s)\n> ' % (autre, vu)).strip()
                if r:
                    noms[autre] = r
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
    f = racine() / 'exports' / (nom_de_fichier(nom) + '.json')
    f.write_text(json.dumps(scenario, ensure_ascii=False, indent=2), encoding='utf-8')
    entree['scenario'] = f.name
    cfg['exports'] = [e for e in anciens if e.get('nom') != nom] + [entree]
    garder(cfg)
    noter('Appris : %s (%d gestes, fichier %s%s).' % (nom, len(pas), fichier,
          ', tous les contrats, appris sur « %s »' % scenario['modele']['appris'] if entree.get('modele') else ', case %s' % entree['case']))
    if input('\nLe robot essaie tout de suite, devant vous ? (o/n) ').strip().lower().startswith('o'):
        essayer([nom])


def norm(t):
    return re.sub(r'\s+', ' ', str(t or '')).strip().lower()


def contrats_du_tableau(cases):
    """« GATES HDK », « GATES THS »… → HDK, THS : les contrats que la fenêtre
    d'import du tableau de bord connaît aujourd'hui."""
    return [n[6:].strip() for n in cases if n.upper().startswith('GATES ') and n[6:].strip()]


def reperer_contrat(pas, contrats):
    """Dans les gestes appris, le mot qui désigne le contrat : tapé dans un
    champ, choisi dans une liste, ou cliqué. Il est retrouvé seul quand il est
    le nom d'un contrat du tableau ; sinon on demande. Rend (le mot appris,
    le contrat du tableau qu'il désigne — ou '' si le tableau n'a rien dit)."""
    candidats = []
    for g in pas:
        for t in ((g.get('texte'),) if g['faire'] == 'remplir' else (g.get('option'), g.get('valeur')) if g['faire'] == 'choisir'
                  else ((g.get('cible') or {}).get('texte'),) if g['faire'] == 'cliquer' else ()):
            t = str(t or '').strip()
            if t and len(t) <= 60 and t not in candidats:
                candidats.append(t)
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
        if motif.search(str(cible.get('texte') or '')):
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


def cases_du_tableau(c, cfg):
    """Les cases de la fenêtre d'import du tableau de bord, comme elles s'y
    lisent (« GATES HDK », « GATES HDK Tranche 2 »…, et celle de SEE) : le
    fichier appris ira dans l'une d'elles, choisie dans la liste plutôt que
    tapée (une lettre de travers, et le dépôt ne la trouvait pas). Vide si
    la fenêtre ne s'ouvre pas : on demande alors le nom, comme avant."""
    if not cfg.get('tableau'):
        return []
    try:
        c.ouvrir(cfg['tableau'] + ('&' if '?' in cfg['tableau'] else '?') + 'page=import')
        cadre, ctx = cadre_import(c, delai=60)
        try:
            time.sleep(2)
            noms = dans_le_cadre(cadre, ctx, '[].map.call(document.querySelectorAll(".case:not(.nouvelle) .etiquette"), '
                                             'function (e) { return e.textContent.replace(/\\s+/g, " ").trim(); })')
        finally:
            cadre._canal.fermer()
        return [n for n in (noms or []) if n]
    except (ErreurPilote, OSError, ValueError):
        return []


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
    for t in ('mouseMoved', 'mousePressed', 'mouseReleased'):
        extra = {'button': 'left', 'clickCount': 1} if t != 'mouseMoved' else {}
        c.envoyer('Input.dispatchMouseEvent', type=t, x=x, y=y, **extra)
        time.sleep(0.05)


def trouver(c, cible, delai=60):
    fin = time.time() + delai
    while time.time() < fin:
        try:
            r = c.evaluer(TROUVER % json.dumps(cible))
            if r:
                return r
        except ErreurPilote:
            pass
        time.sleep(0.5)
    raise ErreurPilote('Je ne retrouve plus « %s » sur la page %s. La page a peut-être changé : refaites '
                       '« Apprendre » pour cet export.' % (cible.get('texte') or cible.get('label') or cible.get('chemin'),
                                                          cible.get('page')))


def vider_telechargements():
    """Le dossier de téléchargement du robot, vidé avant chaque export : un
    fichier du même nom qu'hier serait sinon écrasé sans se voir arriver."""
    for f in (racine() / 'telechargements').iterdir():
        try:
            f.unlink() if f.is_file() else shutil.rmtree(f)
        except OSError:
            pass


def rejouer(c, scenario, dossier_sortie):
    vider_telechargements()
    avant = set()
    c.ouvrir(scenario['depart'])
    try:
        c.evaluer(GUETTEUR)    # même onglet pour les liens « nouvel onglet »
    except ErreurPilote:
        pass
    for i, g in enumerate(scenario['etapes'], 1):
        cible = g.get('cible') or {}
        facultatif = bool(CONNEXION.search(cible.get('page', '')))
        try:
            r = trouver(c, cible, delai=12 if facultatif else 60)
        except ErreurPilote:
            if facultatif and not CONNEXION.search(page_actuelle(c)):
                print('  %d/%d (page de connexion inutile ce matin : sautée)' % (i, len(scenario['etapes'])))
                continue
            raise
        if g['faire'] == 'cliquer':
            souris(c, r['x'], r['y'])
        elif g['faire'] == 'remplir':
            c.evaluer('(function(e){e.focus(); if (e.select) e.select();})(window.__suiviCible)')
            c.envoyer('Input.insertText', text=g.get('texte', ''))
            c.evaluer('window.__suiviCible.dispatchEvent(new Event("change",{bubbles:true}))')
        elif g['faire'] == 'choisir':
            pris = c.evaluer('(function(e,v,t){var o=[].slice.call(e.options).filter(function(x){return x.value===v;})[0]'
                             '||[].slice.call(e.options).filter(function(x){return x.text===t;})[0]; if(!o) return false; e.value=o.value;'
                             'e.dispatchEvent(new Event("input",{bubbles:true}));e.dispatchEvent(new Event("change",{bubbles:true}));return true;})'
                             '(window.__suiviCible,%s,%s)' % (json.dumps(g.get('valeur', '')), json.dumps(g.get('option', ''))))
            if pris is False:      # rien de choisi : la page garderait le choix d'avant (un autre contrat ?)
                raise ErreurPilote('Le choix « %s » n\'existe pas dans la liste « %s ».'
                                   % (g.get('option') or g.get('valeur'), cible.get('label') or cible.get('texte') or cible.get('nom') or '?'))
        elif g['faire'] == 'entree':
            c.evaluer('window.__suiviCible.focus()')
            for t in ('keyDown', 'keyUp'):
                c.envoyer('Input.dispatchKeyEvent', type=t, key='Enter', code='Enter', windowsVirtualKeyCode=13,
                          nativeVirtualKeyCode=13, **({'text': '\r'} if t == 'keyDown' else {}))
        print('  %d/%d %s %s' % (i, len(scenario['etapes']), g['faire'], cible.get('texte') or g.get('texte') or ''))
        time.sleep(1.2)
        attendre_page(c)
    chemin = c.attendre_telechargement(avant=avant, delai=600, motif=scenario.get('fichier'))
    dest = pathlib.Path(dossier_sortie) / (nom_de_fichier(scenario['nom']) + chemin.suffix)
    shutil.copy2(chemin, dest)
    return dest


def exports_choisis(noms=None):
    cfg = config()
    liste = cfg.get('exports', [])
    if noms:
        liste = [e for e in liste if e['nom'] in noms]
    return cfg, liste


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
    d'aujourd'hui, un contrat ajouté hier compris —, chacun dans sa case
    « GATES <contrat> ». Rend [(entrée, scénario)]."""
    travaux = []
    for e in liste:
        scenario = json.loads((racine() / 'exports' / e['scenario']).read_text(encoding='utf-8'))
        if not (e.get('modele') and scenario.get('modele')):
            travaux.append((e, scenario))
            continue
        if not contrats:
            raise ErreurPilote('Je ne connais aucun contrat : la fenêtre d\'import du tableau de bord n\'en montre aucun.')
        appris = scenario['modele']['appris']
        for k in contrats:
            nom_gates = (cfg.get('noms_gates') or {}).get(k, k)
            travaux.append(({'nom': 'GATES ' + k, 'case': 'GATES ' + k}, pour_le_contrat(scenario, appris, k, nom_gates)))
    return travaux


def faire_les_exports(c, cfg, liste, dossier, contrats):
    """Chaque export, l'un après l'autre. Un contrat qui cale n'arrête pas
    les autres : ce qui est sorti est rendu, et les ratés avec leur raison."""
    sortis, rates = [], []
    for e, scenario in a_faire(cfg, liste, contrats):
        noter('Export « %s »…' % e['nom'])
        try:
            sortis.append((e, rejouer(c, scenario, dossier)))
        except ErreurPilote as err:
            vue = photo(c)
            noter('  ✗ %s%s' % (err, '\n  Photo de la fenêtre du robot : ' + vue if vue else ''))
            rates.append('%s : %s' % (e['nom'], str(err).split('\n')[0]))
            continue
        noter('  ✓ %s' % sortis[-1][1].name)
    return sortis, rates


def attendre_tableau(c, cfg, delai):
    """Le tableau de bord d'abord : ses cases disent les contrats du jour.
    Au retour devant l'écran, Google met parfois longtemps à répondre (le
    réseau de l'entreprise se remet en place) : le robot attend, sans
    compter d'essai raté, jusqu'à « delai » secondes."""
    if not cfg.get('tableau'):
        raise ErreurPilote('Le robot ne connaît pas encore l\'adresse du tableau de bord : double-cliquez « 1 - Preparer ».')
    fin = time.time() + delai
    while True:
        cases = cases_du_tableau(c, cfg)
        if cases:
            return cases
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
            contrats = contrats_du_tableau(attendre_tableau(c, cfg, 120)) if any(e.get('modele') for e in liste) else []
            sortis, rates = faire_les_exports(c, cfg, liste, dossier, contrats)
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


def deposer(c, cfg, sortis):
    adresse = cfg['tableau'] + ('&' if '?' in cfg['tableau'] else '?') + 'page=import'
    c.ouvrir(adresse)
    cadre, ctx = cadre_import(c)
    try:
        time.sleep(3)
        cadre.envoyer('DOM.enable')
        for e, chemin in sortis:
            case = e.get('case') or e['nom']
            js = ('(function(nom){var norm=function(s){return String(s||"").replace(/\\s+/g," ").trim().toLowerCase();};'
                  'if(norm(nom)==="see"){var s=document.querySelector("#case-see input.fichier"); if(s) return s;}'
                  'var c=[].slice.call(document.querySelectorAll(".case")).filter(function(k){'
                  'var t=k.querySelector(".etiquette"); return t && norm(t.textContent)===norm(nom);})[0];'
                  'return c ? c.querySelector("input.fichier") : null;})(%s)' % json.dumps(case))
            obj = dans_le_cadre(cadre, ctx, js, objet=True)
            if not obj.get('objectId'):
                raise ErreurPilote('Pas de case « %s » dans la fenêtre d\'import du tableau de bord.' % case)
            cadre.envoyer('DOM.setFileInputFiles', files=[str(chemin)], objectId=obj['objectId'])
            noter('  ↑ %s → case « %s »' % (chemin.name, case))
        fin = time.time() + 600
        while time.time() < fin and dans_le_cadre(cadre, ctx, 'document.getElementById("importer").disabled'):
            time.sleep(1)
        if dans_le_cadre(cadre, ctx, 'document.getElementById("importer").disabled'):
            raise ErreurPilote('La fenêtre d\'import refuse les fichiers : %s'
                               % dans_le_cadre(cadre, ctx, 'document.getElementById("blocage").innerText'))
        # Le doute de la fenêtre d'import (« seulement 3 plans sur 186 en commun avec « HDK » : est-ce
        # bien son export ? ») : à la main, on regarde ; le robot, lui, n'importe pas ce fichier-là.
        douteux = dans_le_cadre(cadre, ctx, '[].slice.call(document.querySelectorAll(".case")).filter(function (k) {'
                                            'var n = k.querySelector(".note"); return n && !n.hidden && n.textContent.trim(); }).map(function (k) {'
                                            'var r = k.querySelector("button.retirer"); if (r && !r.hidden) r.click();'
                                            'return k.querySelector(".etiquette").textContent + " — " + k.querySelector(".note").textContent.trim(); })') or []
        for d in douteux:
            noter('  ✗ Pas importé, par prudence : %s' % d)
        if douteux:
            time.sleep(2)
            if dans_le_cadre(cadre, ctx, 'document.getElementById("importer").disabled'):
                raise ErreurPilote('Rien d\'importé, par prudence : %s' % ' ; '.join(douteux))
        dans_le_cadre(cadre, ctx, 'document.getElementById("importer").click()')
        fin = time.time() + 1800
        while time.time() < fin:
            time.sleep(3)
            if dans_le_cadre(cadre, ctx, 'document.getElementById("fermer").classList.contains("principal") && '
                                         'document.getElementById("consigne").hidden'):
                break
        bilan = dans_le_cadre(cadre, ctx, 'document.getElementById("etat").innerText') or ''
        rate = dans_le_cadre(cadre, ctx, '!!document.querySelector("#etat.erreur, #etat .erreur")')
        noter(('✗ ' if rate else '✓ ') + 'Dépôt : ' + bilan.replace('\n', ' · ')[:600])
        if rate:
            raise ErreurPilote('Le dépôt a signalé une erreur (voir le journal).')
        return douteux
    finally:
        cadre._canal.fermer()


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
    """Un passage : le tableau de bord (ses contrats du jour), les exports,
    le dépôt. Rend (0, '') réussi, (1, la raison) sinon. Des exports ratés
    n'empêchent pas de déposer ceux qui sont sortis ; le passage compte
    alors comme raté (il sera refait)."""
    cfg, liste = exports_choisis()
    etat = racine() / 'dernier-passage.txt'
    aujourd_hui = datetime.date.today().isoformat()
    if not liste or not cfg.get('tableau'):
        noter('Rien à faire : le robot n\'est pas encore préparé ou n\'a rien appris.')
        return 1, 'le robot n\'est pas encore préparé ou n\'a rien appris'
    dossier = racine() / 'deposes' / datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    dossier.mkdir(parents=True, exist_ok=True)
    noter('=== Passage du robot%s ===' % (' (automatique)' if auto else ''))
    try:
        with chrome(True, grand=not auto) as c:
            contrats = contrats_du_tableau(attendre_tableau(c, cfg, ATTENTE_GOOGLE if auto else 120))
            sortis, rates = faire_les_exports(c, cfg, liste, dossier, contrats)
            if sortis:
                rates += deposer(c, cfg, sortis)
            if rates:
                raise ErreurPilote('%s : %s' % ('pas tout' if sortis else 'rien', ' ; '.join(rates)))
    except (ErreurPilote, OSError, ValueError) as err:
        noter('✗ Passage interrompu : %s' % err)
        etat.write_text('%s échec %s' % (aujourd_hui, err), encoding='utf-8')
        return 1, str(err).split('\n')[0]
    etat.write_text('%s ok %s' % (aujourd_hui, datetime.datetime.now().strftime('%H:%M')), encoding='utf-8')
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
    print('Exports appris  : %s' % (', '.join('%s → %s' % (e['nom'], 'tous les contrats du tableau' if e.get('modele') else e.get('case'))
                                              for e in cfg.get('exports', [])) or 'aucun'))
    autres = {k: v for k, v in (cfg.get('noms_gates') or {}).items() if norm(k) != norm(v)}
    if autres:
        print('Noms dans GATES : %s' % ', '.join('%s → « %s »' % kv for kv in sorted(autres.items())))
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
