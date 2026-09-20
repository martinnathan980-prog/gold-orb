#!/usr/bin/env python3
"""
Pilote Chrome depuis Python, sans rien installer.

Le poste de travail n'autorise pas les exécutables : pas de pilote de
navigateur à télécharger, pas de bibliothèque externe. Or Chrome sait déjà
obéir à des ordres : lancé avec une option de débogage, il ouvre un canal
sur lequel on lui dit « va à cette adresse », « clique ce bouton », « lis ce
tableau ». C'est le protocole que les outils du métier utilisent — ici il est
parlé directement, en bibliothèque standard.

Ce n'est PAS un clic simulé à l'aveugle : on ne bouge pas la souris, on ne
tape pas au clavier de l'utilisateur. On désigne un élément de la page et on
lui demande de faire ce qu'il ferait sous le doigt. Travailler à côté pendant
ce temps ne dérange rien.

    Préparer Chrome (une seule fois, fenêtre fermée d'abord) :

        chrome.exe --remote-debugging-port=9222

    Puis, depuis Python :

        from piloter_chrome import Chrome

        with Chrome() as chrome:                  # s'attache à ce Chrome-là
            chrome.ouvrir('https://intranet/gates')
            chrome.remplir('#recherche', 'HDK')
            chrome.cliquer_texte('Tout extraire')
            fichier = chrome.attendre_telechargement()

La session reste celle de l'utilisateur : ses cookies, son authentification
Windows, ses droits. Aucun mot de passe n'est lu ni stocké nulle part.

Aucune dépendance : bibliothèque standard uniquement.
"""

import base64
import fnmatch
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.request

PORT_DEFAUT = 9222

DELAI_DEFAUT = 30          # secondes d'attente par défaut


class ErreurPilote(Exception):
    """Tout ce qui empêche de continuer, dit en français."""


# Sur un poste d'entreprise, le proxy est imposé à tout le trafic — y compris,
# selon la configuration, à 127.0.0.1. Le canal de Chrome est local : il ne
# doit jamais passer par le proxy, sans quoi rien ne répond.
SANS_PROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


# ---------------------------------------------------------------------------
#  Un client WebSocket minimal
#  Le canal de Chrome est un WebSocket. Il n'en faut qu'une petite part :
#  des messages texte, dans les deux sens, sur une connexion locale.
# ---------------------------------------------------------------------------
class _Canal:
    """Une connexion WebSocket vers 127.0.0.1, en texte."""

    def __init__(self, url, delai=DELAI_DEFAUT):
        if not url.startswith('ws://'):
            raise ErreurPilote('Adresse de canal inattendue : ' + url)
        reste = url[len('ws://'):]
        hote_port, _, chemin = reste.partition('/')
        hote, _, port = hote_port.partition(':')
        self.prise = socket.create_connection((hote, int(port or 80)), timeout=delai)
        self.prise.settimeout(delai)
        self._reste = b''
        self._poignee_de_main(hote_port, '/' + chemin)

    def _poignee_de_main(self, hote, chemin):
        cle = base64.b64encode(os.urandom(16)).decode('ascii')
        demande = (
            'GET %s HTTP/1.1\r\n'
            'Host: %s\r\n'
            'Upgrade: websocket\r\n'
            'Connection: Upgrade\r\n'
            'Sec-WebSocket-Key: %s\r\n'
            'Sec-WebSocket-Version: 13\r\n'
            '\r\n' % (chemin, hote, cle)
        )
        self.prise.sendall(demande.encode('ascii'))
        entete = b''
        while b'\r\n\r\n' not in entete:
            morceau = self.prise.recv(4096)
            if not morceau:
                raise ErreurPilote('Chrome a fermé la connexion pendant la poignée de main.')
            entete += morceau
        tete, _, suite = entete.partition(b'\r\n\r\n')
        self._reste = suite
        premiere = tete.split(b'\r\n')[0].decode('latin-1')
        if '101' not in premiere:
            raise ErreurPilote('Chrome refuse le canal : ' + premiere)
        attendue = base64.b64encode(
            hashlib.sha1((cle + '258EAFA5-E914-47DA-95CA-C5AB0DC85B11').encode('ascii')).digest()
        ).decode('ascii')
        for ligne in tete.decode('latin-1').split('\r\n')[1:]:
            nom, _, valeur = ligne.partition(':')
            if nom.strip().lower() == 'sec-websocket-accept' and valeur.strip() == attendue:
                return
        raise ErreurPilote('Réponse de Chrome non conforme : le canal n\'est pas sûr.')

    # -- lecture -----------------------------------------------------------
    def _lire(self, combien):
        while len(self._reste) < combien:
            try:
                morceau = self.prise.recv(65536)
            except socket.timeout:
                raise ErreurPilote(
                    'Chrome n\'a rien répondu pendant %d s. La page est peut-être figée, ou '
                    'l\'onglet mis en veille par Windows : ramenez la fenêtre au premier plan, '
                    'ou relancez Chrome avec son option de débogage.' % self.prise.gettimeout())
            except OSError as err:
                raise ErreurPilote('La liaison avec Chrome s\'est interrompue : %s' % err)
            if not morceau:
                raise ErreurPilote('Chrome a fermé la connexion.')
            self._reste += morceau
        tete, self._reste = self._reste[:combien], self._reste[combien:]
        return tete

    def recevoir(self):
        """Le prochain message texte, recomposé s'il arrive en morceaux."""
        morceaux = []
        while True:
            entete = self._lire(2)
            fin = bool(entete[0] & 0x80)
            code = entete[0] & 0x0F
            masque = bool(entete[1] & 0x80)
            taille = entete[1] & 0x7F
            if taille == 126:
                taille = struct.unpack('!H', self._lire(2))[0]
            elif taille == 127:
                taille = struct.unpack('!Q', self._lire(8))[0]
            cle = self._lire(4) if masque else b''
            charge = self._lire(taille)
            if masque:
                charge = bytes(o ^ cle[i % 4] for i, o in enumerate(charge))
            if code == 0x8:                       # fermeture
                raise ErreurPilote('Chrome a fermé le canal.')
            if code == 0x9:                       # ping : on répond
                self._envoyer_trame(0xA, charge)
                continue
            if code == 0xA:                       # pong
                continue
            morceaux.append(charge)
            if fin:
                return b''.join(morceaux).decode('utf-8', 'replace')

    # -- écriture ----------------------------------------------------------
    def _envoyer_trame(self, code, charge):
        entete = bytes([0x80 | code])
        taille = len(charge)
        if taille < 126:
            entete += bytes([0x80 | taille])
        elif taille < (1 << 16):
            entete += bytes([0x80 | 126]) + struct.pack('!H', taille)
        else:
            entete += bytes([0x80 | 127]) + struct.pack('!Q', taille)
        cle = os.urandom(4)
        masquee = bytes(o ^ cle[i % 4] for i, o in enumerate(charge))
        self.prise.sendall(entete + cle + masquee)

    def envoyer(self, texte):
        self._envoyer_trame(0x1, texte.encode('utf-8'))

    def fermer(self):
        try:
            self._envoyer_trame(0x8, b'')
        except OSError:
            pass
        try:
            self.prise.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
#  Trouver Chrome
# ---------------------------------------------------------------------------
def dossier_utilisable(chemin):
    """Un dossier donné par un humain : %USERPROFILE%, ~, antislash — tout est
    développé, et le dossier doit exister (on ne le crée pas à l'aveugle, sinon
    une faute de frappe fabriquerait un dossier où rien n'arriverait jamais)."""
    # %VARIABLE% est la forme Windows : os.path.expandvars ne la développe que
    # sous Windows, or une recette écrite là-bas doit se relire partout.
    def fenetre(trouvaille):
        return os.environ.get(trouvaille.group(1), trouvaille.group(0))
    brut = re.sub(r'%([A-Za-z_][A-Za-z0-9_]*)%', fenetre, str(chemin))
    brut = os.path.expanduser(os.path.expandvars(brut))
    dossier = pathlib.Path(brut).resolve()
    if not dossier.is_dir():
        raise ErreurPilote(
            'Le dossier de téléchargement « %s » n\'existe pas. Vérifiez « telechargements » '
            'dans la recette : c\'est là que Chrome dépose les fichiers.' % brut)
    return dossier


def chemin_chrome():
    """Le Chrome de ce poste, ou None. SUIVI_FWD_CHROME a le dernier mot."""
    impose = os.environ.get('SUIVI_FWD_CHROME')
    if impose:
        return impose
    candidats = []
    if platform.system() == 'Windows':
        dossiers = [os.environ.get(var) for var in ('PROGRAMFILES', 'PROGRAMFILES(X86)', 'LOCALAPPDATA')]
        # Chrome d'abord, partout, AVANT le premier Edge : le poste travaille
        # sur Chrome, et un Edge trouvé plus tôt lui serait passé devant.
        for marque in (('Google', 'Chrome', 'Application', 'chrome.exe'),
                       ('Microsoft', 'Edge', 'Application', 'msedge.exe')):
            for base in dossiers:
                if base:
                    candidats.append(os.path.join(base, *marque))
    else:
        candidats += ['/usr/bin/google-chrome', '/usr/bin/chromium', '/usr/bin/chromium-browser',
                      '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome']
    for c in candidats:
        if c and os.path.exists(c):
            return c
    for nom in ('google-chrome', 'chromium', 'chrome'):
        trouve = shutil.which(nom)
        if trouve:
            return trouve
    return None


# ---------------------------------------------------------------------------
#  Le pilote
# ---------------------------------------------------------------------------
class Chrome:
    """Un Chrome qui obéit : s'attache au vôtre, ou en lance un pour les essais.

    port           : le port de débogage (celui de --remote-debugging-port).
    telechargements: le dossier où les fichiers doivent tomber.
    lancer         : True pour démarrer un Chrome à part (essais, poste sans
                     session à préserver) ; par défaut on s'attache à celui
                     qui tourne déjà, pour garder l'authentification.
    profil         : dossier de profil du Chrome lancé (avec lancer=True).
    sans_fenetre   : Chrome lancé sans interface (essais uniquement).
    options        : options supplémentaires passées à Chrome au lancement
                     (la batterie s'en sert pour tourner dans un conteneur).
    """

    def __init__(self, port=PORT_DEFAUT, telechargements=None, lancer=False,
                 profil=None, sans_fenetre=False, delai=DELAI_DEFAUT, options=None):
        self.port = int(port)
        self.delai = delai
        self.telechargements = dossier_utilisable(telechargements) if telechargements else None
        self._lancer = lancer
        self._profil = profil
        self._sans_fenetre = sans_fenetre
        self._options = list(options or [])
        self._processus = None
        self._canal = None
        self._numero = 0
        self._onglet_cree = None

    # -- cycle de vie ------------------------------------------------------
    def __enter__(self):
        self.demarrer()
        return self

    def __exit__(self, *_):
        self.fermer()
        return False

    def demarrer(self):
        if self._lancer:
            self._lancer_chrome()
        cible = self._onglet_a_part() or self._premier_onglet()
        self._canal = _Canal(cible['webSocketDebuggerUrl'], self.delai)
        self.envoyer('Page.enable')
        self.envoyer('Runtime.enable')
        if self.telechargements:
            # Selon les versions, l'ordre s'appelle Browser… ou Page… : on tente les deux.
            for methode in ('Browser.setDownloadBehavior', 'Page.setDownloadBehavior'):
                try:
                    self.envoyer(methode, behavior='allow', downloadPath=str(self.telechargements))
                    break
                except ErreurPilote:
                    continue
        return self

    def _lancer_chrome(self):
        exe = chemin_chrome()
        if not exe:
            raise ErreurPilote(
                'Chrome est introuvable sur ce poste. Indiquez son chemin dans la variable '
                'SUIVI_FWD_CHROME.')
        profil = self._profil or os.path.join(os.path.expanduser('~'), '.suivi-fwd-chrome')
        options = [exe, '--remote-debugging-port=%d' % self.port, '--user-data-dir=%s' % profil,
                   '--no-first-run', '--no-default-browser-check']
        if self._sans_fenetre:
            options += ['--headless=new', '--disable-gpu']
        options += self._options + ['about:blank']
        self._processus = subprocess.Popen(options, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        fin = time.time() + self.delai
        while time.time() < fin:
            try:
                self._version()
                return
            except (urllib.error.URLError, OSError, ValueError):
                time.sleep(0.2)
        raise ErreurPilote('Chrome n\'a pas ouvert son canal sur le port %d.' % self.port)

    def fermer(self):
        if self._canal:
            self._canal.fermer()
            self._canal = None
        self._fermer_onglet_a_part()
        if self._processus:
            self._processus.terminate()
            try:
                self._processus.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self._processus.kill()
            self._processus = None

    # -- le canal ----------------------------------------------------------
    def _http(self, chemin):
        """Une demande au canal local, sans passer par le proxy de l'entreprise."""
        with SANS_PROXY.open('http://127.0.0.1:%d%s' % (self.port, chemin), timeout=self.delai) as r:
            return json.loads(r.read().decode('utf-8'))

    def _version(self):
        return self._http('/json/version')

    def _onglet_a_part(self):
        """Un onglet neuf, rien qu'à nous : celui de la lectrice n'est pas détourné.

        Chrome le crée sur demande ; certaines versions n'acceptent plus cette
        demande, et l'on retombe alors sur l'onglet courant.
        """
        for methode in ('PUT', 'GET'):
            try:
                demande = urllib.request.Request(
                    'http://127.0.0.1:%d/json/new?about:blank' % self.port, method=methode)
                with SANS_PROXY.open(demande, timeout=self.delai) as r:
                    cible = json.loads(r.read().decode('utf-8'))
                if cible.get('webSocketDebuggerUrl'):
                    self._onglet_cree = cible.get('id')
                    return cible
            except (urllib.error.URLError, OSError, ValueError):
                continue
        return None

    def _fermer_onglet_a_part(self):
        if not self._onglet_cree:
            return
        try:
            with SANS_PROXY.open('http://127.0.0.1:%d/json/close/%s' % (self.port, self._onglet_cree),
                                 timeout=5):
                pass
        except (urllib.error.URLError, OSError):
            pass
        self._onglet_cree = None

    def _premier_onglet(self):
        try:
            cibles = self._http('/json/list')
        except (urllib.error.URLError, OSError) as err:
            raise ErreurPilote(
                'Aucun Chrome ne répond sur le port %d. Fermez Chrome, puis relancez-le une fois '
                'avec  chrome.exe --remote-debugging-port=%d  (détail : %s).' % (self.port, self.port, err))
        pages = [c for c in cibles if c.get('type') == 'page' and c.get('webSocketDebuggerUrl')]
        if not pages:
            raise ErreurPilote('Chrome répond, mais n\'a aucun onglet ouvert à piloter.')
        return pages[0]

    def envoyer(self, methode, delai=None, **params):
        """Un ordre à Chrome ; rend son résultat, lève ErreurPilote s'il refuse."""
        if not self._canal:
            raise ErreurPilote('Le canal n\'est pas ouvert : appelez demarrer().')
        attente = delai or self.delai
        self._numero += 1
        numero = self._numero
        self._canal.envoyer(json.dumps({'id': numero, 'method': methode, 'params': params}))
        fin = time.time() + attente
        while time.time() < fin:
            message = json.loads(self._canal.recevoir())
            if message.get('id') != numero:
                continue                                  # un événement : on passe
            if 'error' in message:
                raise ErreurPilote('%s a échoué : %s' % (methode, message['error'].get('message', message['error'])))
            return message.get('result', {})
        raise ErreurPilote('%s : Chrome n\'a pas répondu en %d s.' % (methode, attente))

    # -- les gestes --------------------------------------------------------
    def evaluer(self, js, delai=None):
        """Évalue une expression JavaScript dans la page et rend sa valeur."""
        resultat = self.envoyer('Runtime.evaluate', delai=delai, expression=js, returnByValue=True,
                                awaitPromise=True, userGesture=True)
        details = resultat.get('exceptionDetails')
        if details:
            texte = (details.get('exception') or {}).get('description') or details.get('text')
            raise ErreurPilote('La page a répondu par une erreur : ' + str(texte))
        return resultat.get('result', {}).get('value')

    def ouvrir(self, url, delai=None):
        """Va à cette adresse et attend que la page soit posée."""
        self.envoyer('Page.navigate', url=url)
        self.attendre('document.readyState === "complete"', delai=delai)
        return self.url()

    def url(self):
        return self.evaluer('location.href')

    def titre(self):
        return self.evaluer('document.title')

    def attendre(self, condition_js, delai=None, pas=0.25):
        """Attend qu'une condition JavaScript devienne vraie."""
        fin = time.time() + (delai or self.delai)
        derniere = None
        while time.time() < fin:
            try:
                if self.evaluer('!!(' + condition_js + ')'):
                    return True
            except ErreurPilote as err:
                derniere = err
            time.sleep(pas)
        raise ErreurPilote('Toujours faux après %d s : %s%s' % (
            delai or self.delai, condition_js, ' (%s)' % derniere if derniere else ''))

    def attendre_selecteur(self, selecteur, delai=None):
        self.attendre('document.querySelector(%s)' % json.dumps(selecteur), delai=delai)
        return True

    def cliquer(self, selecteur, delai=None):
        """Clique l'élément désigné — un vrai clic sur l'élément, pas sur des coordonnées."""
        self.attendre_selecteur(selecteur, delai=delai)
        ok = self.evaluer(
            '(function (s) { var e = document.querySelector(s); if (!e) return false;'
            ' e.scrollIntoView({block:"center"}); e.click(); return true; })(%s)' % json.dumps(selecteur),
            delai=delai)
        if not ok:
            raise ErreurPilote('Rien à cliquer pour « %s ».' % selecteur)
        return True

    def cliquer_texte(self, texte, balises='button, a, input[type=submit], input[type=button], [role=button]', delai=None):
        """Clique le bouton ou le lien qui porte ce texte — pratique quand on ne
        connaît pas le sélecteur, seulement ce qui est écrit dessus."""
        js = (
            '(function (mot, sel) {'
            '  var m = mot.trim().toLowerCase();'
            '  var lus = [].slice.call(document.querySelectorAll(sel));'
            '  var mot = function (x) { return (x.value || x.textContent || "").trim().toLowerCase(); };'
            '  var e = lus.filter(function (x) { return mot(x) === m; })[0]'
            '       || lus.filter(function (x) { return mot(x).indexOf(m) !== -1; })[0];'
            '  if (!e) return false;'
            '  e.scrollIntoView({block:"center"}); e.click(); return true;'
            '})(%s, %s)' % (json.dumps(texte), json.dumps(balises))
        )
        fin = time.time() + (delai or self.delai)
        while time.time() < fin:
            if self.evaluer(js):
                return True
            time.sleep(0.25)
        raise ErreurPilote('Aucun bouton ni lien nommé « %s » dans cette page.' % texte)

    def remplir(self, selecteur, texte, delai=None):
        """Écrit dans un champ et prévient la page, comme une frappe au clavier."""
        self.attendre_selecteur(selecteur, delai=delai)
        ok = self.evaluer(
            '(function (s, v) { var e = document.querySelector(s); if (!e) return false;'
            ' e.focus(); e.value = v;'
            ' e.dispatchEvent(new Event("input", {bubbles:true}));'
            ' e.dispatchEvent(new Event("change", {bubbles:true}));'
            ' return true; })(%s, %s)' % (json.dumps(selecteur), json.dumps(texte)), delai=delai)
        if not ok:
            raise ErreurPilote('Aucun champ « %s » à remplir.' % selecteur)
        return True

    def texte(self, selecteur='body'):
        return self.evaluer(
            '(function (s) { var e = document.querySelector(s); return e ? e.innerText : null; })(%s)'
            % json.dumps(selecteur))

    def tableau(self, selecteur='table'):
        """Le contenu d'un tableau HTML, ligne par ligne, cellule par cellule."""
        return self.evaluer(
            '(function (s) { var t = document.querySelector(s); if (!t) return null;'
            ' return [].slice.call(t.rows).map(function (r) {'
            '   return [].slice.call(r.cells).map(function (c) { return c.innerText.trim(); }); }); })(%s)'
            % json.dumps(selecteur))

    # -- téléchargements ---------------------------------------------------
    def fichiers_presents(self):
        if not self.telechargements:
            raise ErreurPilote('Aucun dossier de téléchargement n\'a été indiqué au pilote.')
        return {p.name for p in self.telechargements.iterdir() if p.is_file()}

    def attendre_telechargement(self, avant=None, delai=180, pas=0.5, motif=None):
        """Attend qu'un fichier nouveau ait fini d'arriver, et rend son chemin.

        `avant` : la liste des fichiers déjà là (fichiers_presents()) avant le
        clic. Sans elle, on prend une photo maintenant — à n'utiliser que si
        le téléchargement n'a pas encore commencé.
        `motif` : un filtre (« *.csv », « gates-*.csv ») pour ne pas confondre
        avec un fichier que la lectrice télécharge en même temps. Sans motif,
        c'est le plus récent des nouveaux qui est retenu.
        """
        if not self.telechargements:
            raise ErreurPilote('Aucun dossier de téléchargement n\'a été indiqué au pilote.')
        avant = set(avant if avant is not None else self.fichiers_presents())
        fin = time.time() + delai
        while time.time() < fin:
            nouveaux = [n for n in self.fichiers_presents() - avant
                        if not n.endswith(('.crdownload', '.tmp', '.part'))]
            if motif:
                nouveaux = [n for n in nouveaux if fnmatch.fnmatch(n, motif)]
            if nouveaux:
                # Le plus récent : si la lectrice télécharge autre chose pendant
                # ce temps, c'est le nôtre qui vient d'arriver.
                nouveaux.sort(key=lambda n: (self.telechargements / n).stat().st_mtime, reverse=True)
                chemin = self.telechargements / nouveaux[0]
                taille = -1
                # Un fichier encore en cours d'écriture grandit : on attend qu'il se pose.
                while time.time() < fin:
                    actuelle = chemin.stat().st_size
                    if actuelle == taille and actuelle > 0:
                        return chemin
                    taille = actuelle
                    time.sleep(pas)
            time.sleep(pas)
        raise ErreurPilote('Aucun fichier%s n\'est arrivé dans %s en %d s.'
                           % (' « ' + motif + ' »' if motif else '', self.telechargements, delai))


def etat_du_poste():
    """Ce que le poste sait faire, en clair — à lancer en premier pour voir."""
    lignes = ['Python  : ' + platform.python_version() + ' (' + platform.system() + ')']
    exe = chemin_chrome()
    lignes.append('Chrome  : ' + (exe if exe else 'introuvable — indiquez SUIVI_FWD_CHROME'))
    try:
        # SANS_PROXY, comme le pilote lui-même : sur un poste d'entreprise, une
        # demande à 127.0.0.1 partie dans le proxy échoue, et le diagnostic
        # annoncerait « fermé » un canal parfaitement ouvert.
        with SANS_PROXY.open('http://127.0.0.1:%d/json/version' % PORT_DEFAUT, timeout=2) as r:
            version = json.loads(r.read().decode('utf-8'))
        lignes.append('Canal   : ouvert sur le port %d — %s' % (PORT_DEFAUT, version.get('Browser', '?')))
    except Exception:
        lignes.append('Canal   : fermé. Fermez Chrome, puis relancez-le une fois avec '
                      '--remote-debugging-port=%d' % PORT_DEFAUT)
    return '\n'.join(lignes)


if __name__ == '__main__':
    print(etat_du_poste())
