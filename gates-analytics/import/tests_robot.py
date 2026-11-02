#!/usr/bin/env python3
"""
Batterie du robot, sans navigateur ni Windows : ce qui décide QUAND il passe.

    python3 import/tests_robot.py

— pas avant son heure (14 h par défaut) ;
— une fois par jour : un passage réussi, et plus rien jusqu'au lendemain,
  quels que soient les redémarrages et les ouvertures de session ;
— raté, il réessaie lui-même, trois passages au plus par jour, et ne le
  dit (une petite fenêtre) qu'après le dernier ;
— jamais deux robots à la fois (verrou du système), et un robot arrêté net
  (fenêtre noire fermée par sa croix, ordinateur éteint) ne bloque rien ;
— la tâche planifiée de Windows : un XML bien formé, trois déclencheurs
  (ouverture de session, déverrouillage, heure du matin), une seule
  instance, l'heure manquée rattrapée ;
— la case du tableau choisie dans la liste ;
— GATES appris sur un contrat, refait pour tous : le nom du contrat est
  retrouvé dans les gestes, remplacé partout, et exigé sur ce qu'on clique.

Aucune dépendance : bibliothèque standard uniquement.
"""

import builtins
import datetime
import os
import pathlib
import sys
import tempfile
import xml.etree.ElementTree as ET

DOSSIER = tempfile.mkdtemp(prefix='robot-')
os.environ['LOCALAPPDATA'] = DOSSIER
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import robot  # noqa: E402

echecs = []
faits = []


def verifier(nom, condition, detail=''):
    (faits if condition else echecs).append(nom)
    print(('  ✓ ' if condition else '  ✗ ') + nom + ('' if condition else ' — %s' % detail))


R = robot.racine()
AUJ = datetime.date.today().isoformat()
HIER = (datetime.date.today() - datetime.timedelta(days=1)).isoformat()


def remettre():
    for n in ('dernier-passage.txt', 'essais-du-jour.txt', 'en-cours.txt'):
        p = R / n
        if p.exists():
            p.unlink()


# Le passage lui-même est simulé : on compte les appels, il réussit ou rate.
appels = []
robot.ATTENTE_AUTO = 0
robot.PAUSE_ESSAIS = 0
robot.prevenir = lambda texte: appels.append(('prevenu', texte))
robot.garder(dict(robot.config(), heure='00:00'))     # l'heure du robot passée, sauf dans « Pas avant son heure »


def passage_reussi(auto):
    appels.append(('passage', auto))
    (R / 'dernier-passage.txt').write_text('%s ok 14:20' % AUJ, encoding='utf-8')
    return 0, ''


def passage_rate(auto):
    appels.append(('passage', auto))
    (R / 'dernier-passage.txt').write_text('%s échec SEE ne répond pas' % AUJ, encoding='utf-8')
    return 1, 'SEE ne répond pas'


def nb(sorte):
    return sum(1 for a in appels if a[0] == sorte)


print('\n— Pas avant son heure —')
verifier('par défaut, 14 h', robot.heure_du_robot({}) == '14:00')
verifier('une heure illisible : 14 h', robot.heure_du_robot({'heure': '25h'}) == '14:00')
verifier('avant l’heure : trop tôt ; après : non', robot.trop_tot({'heure': '23:59'}) == (datetime.datetime.now().strftime('%H:%M') < '23:59')
         and robot.trop_tot({'heure': '00:00'}) is False)
remettre(); appels.clear()
robot._passage = passage_reussi
robot.garder(dict(robot.config(), heure='23:59'))
if datetime.datetime.now().strftime('%H:%M') < '23:59':
    robot.lancer(auto=True)
    verifier('une ouverture de session avant l’heure (le matin) : rien', nb('passage') == 0, appels)
robot.lancer(auto=False)
verifier('« Lancer maintenant » passe à toute heure', nb('passage') == 1, appels)
robot.garder(dict(robot.config(), heure='00:00'))

print('\n— Une fois par jour —')
remettre(); appels.clear()
robot._passage = passage_reussi
for _ in range(5):                       # ouverture de session, déverrouillages, 8 h 15…
    robot.lancer(auto=True)
verifier('cinq déclenchements le même jour : un seul passage', nb('passage') == 1, appels)
(R / 'dernier-passage.txt').write_text('%s ok 08:20' % HIER, encoding='utf-8')
appels.clear()
robot.lancer(auto=True)
verifier('passé hier : il repasse aujourd’hui', nb('passage') == 1, appels)
appels.clear()
robot.lancer(auto=False)
verifier('« Lancer maintenant » passe même si le passage du jour est fait', nb('passage') == 1, appels)

print('\n— Raté : il réessaie lui-même, trois passages au plus —')
remettre(); appels.clear()
robot._passage = passage_rate
robot.lancer(auto=True)
verifier('un déclenchement qui rate : trois passages (à vingt minutes), puis il s’arrête', nb('passage') == 3, appels)
verifier('une seule petite fenêtre, après le troisième, avec la raison et « Lancer maintenant »',
         nb('prevenu') == 1 and appels[-1][0] == 'prevenu' and 'SEE ne répond pas' in appels[-1][1] and 'Lancer maintenant' in appels[-1][1], appels)
for _ in range(4):
    robot.lancer(auto=True)
verifier('les déclenchements suivants du jour (ouvertures de session…) : plus rien', nb('passage') == 3, appels)
(R / 'essais-du-jour.txt').write_text('%s 3' % HIER, encoding='utf-8')
appels.clear()
robot.lancer(auto=True)
verifier('trois ratés hier : il réessaie aujourd’hui', nb('passage') == 3, appels)
remettre(); appels.clear()
suite = [passage_rate, passage_reussi]
robot._passage = lambda auto: suite.pop(0)(auto)
robot.lancer(auto=True)
robot._passage = passage_reussi
robot.lancer(auto=True)
verifier('un raté puis une réussite (vingt minutes après) : deux passages, aucune fenêtre, puis plus rien',
         nb('passage') == 2 and nb('prevenu') == 0, appels)

print('\n— Jamais deux robots à la fois —')
remettre(); appels.clear()
robot._passage = passage_reussi
with robot.verrou() as libre:
    verifier('le premier prend le verrou', libre is True)
    robot.lancer(auto=True)
    verifier('pendant un passage (ou « apprendre »), le passage automatique s’en va sans rien faire', nb('passage') == 0 and nb('prevenu') == 0, appels)
    verifier('… et « Lancer maintenant » le dit (code 1)', robot.lancer(auto=False) == 1)
    with robot.verrou(silencieux=True) as second:
        verifier('un second verrou est refusé', second is False)


def libre_maintenant():
    with robot.verrou(silencieux=True) as ok:
        return ok


verifier('le verrou est rendu à la fin', libre_maintenant() is True)
(R / 'en-cours.txt').write_text('1234 2026-11-02T09:12:00', encoding='utf-8')   # laissé par la version d'avant
verifier('un ancien fichier en-cours.txt (robot arrêté net avec la version d’avant) ne bloque rien', libre_maintenant() is True)

# Un robot arrêté net : un autre programme prend le verrou, puis il est tué (la croix de la fenêtre noire).
import signal  # noqa: E402
import subprocess  # noqa: E402
tenu = subprocess.Popen([sys.executable, '-c',
                         'import os,sys,time; os.environ["LOCALAPPDATA"]=%r; sys.path.insert(0,%r); import robot\n'
                         'with robot.verrou() as ok:\n    print("tenu" if ok else "refuse", flush=True); time.sleep(60)'
                         % (DOSSIER, str(pathlib.Path(__file__).resolve().parent))], stdout=subprocess.PIPE, text=True)
verifier('un autre robot en route tient le verrou', tenu.stdout.readline().strip() == 'tenu' and libre_maintenant() is False)
appels.clear()
robot.lancer(auto=True)
verifier('… et le passage automatique s’en va sans rien faire', nb('passage') == 0, appels)
tenu.send_signal(signal.SIGKILL if hasattr(signal, 'SIGKILL') else signal.SIGTERM)
tenu.wait(10)
verifier('ce robot tué net (fenêtre fermée par sa croix) : le verrou tombe aussitôt', libre_maintenant() is True)
robot.lancer(auto=True)
verifier('… et le robot repart', nb('passage') == 1, appels)


def boum(auto):
    raise RuntimeError('panne')


remettre()
robot._passage = boum
try:
    robot.lancer(auto=True)
except RuntimeError:
    pass
verifier('une panne imprévue rend quand même le verrou', libre_maintenant() is True)

print('\n— La tâche planifiée de Windows —')
x = robot.xml_tache('08:15', r'C:\Program Files\Python312\pythonw.exe', r'"C:\Users\nathan\Suivi FWD & co\robot.py" auto',
                    r'AIRBUS\nathan', '2026-11-02')
f = R / 'tache.xml'
f.write_text(x, encoding='utf-16')
brut = f.read_bytes()
verifier('écrite en UTF-16 avec sa marque (ce que schtasks lit sans faute)', brut[:2] in (b'\xff\xfe', b'\xfe\xff'), brut[:4])
try:
    arbre = ET.fromstring(f.read_text(encoding='utf-16').split('?>', 1)[1])
    bien_forme = True
except ET.ParseError as err:
    arbre, bien_forme = None, False
    print('   ', err)
verifier('le XML est bien formé (une esperluette dans le chemin est échappée)', bien_forme)
ns = {'t': 'http://schemas.microsoft.com/windows/2004/02/mit/task'}
if arbre is not None:
    dec = arbre.find('t:Triggers', ns)
    verifier('trois déclencheurs : ouverture de session, déverrouillage, chaque jour',
             [c.tag.split('}')[1] for c in dec] == ['LogonTrigger', 'SessionStateChangeTrigger', 'CalendarTrigger'], [c.tag for c in dec])
    verifier('le déverrouillage (SessionUnlock), pour la personne connectée',
             dec.find('t:SessionStateChangeTrigger/t:StateChange', ns).text == 'SessionUnlock' and
             dec.find('t:SessionStateChangeTrigger/t:UserId', ns).text == r'AIRBUS\nathan')
    verifier('l’ouverture de session de la personne connectée (pas de tout le monde : sans droits d’administrateur)',
             dec.find('t:LogonTrigger/t:UserId', ns).text == r'AIRBUS\nathan')
    verifier('chaque jour à 08:15', dec.find('t:CalendarTrigger/t:StartBoundary', ns).text == '2026-11-02T08:15:00' and
             dec.find('t:CalendarTrigger/t:ScheduleByDay/t:DaysInterval', ns).text == '1')
    reg = {c.tag.split('}')[1]: c.text for c in arbre.find('t:Settings', ns)}
    verifier('jamais deux à la fois, l’heure manquée rattrapée, et sur batterie aussi',
             reg.get('MultipleInstancesPolicy') == 'IgnoreNew' and reg.get('StartWhenAvailable') == 'true' and
             reg.get('DisallowStartIfOnBatteries') == 'false' and reg.get('StopIfGoingOnBatteries') == 'false', reg)
    verifier('il tourne avec la session de la personne (sa connexion à GATES et SEE)',
             arbre.find('t:Principals/t:Principal/t:LogonType', ns).text == 'InteractiveToken' and
             arbre.find('t:Principals/t:Principal/t:RunLevel', ns).text == 'LeastPrivilege')
    verifier('la commande : pythonw (sans fenêtre noire), le robot, « auto »',
             arbre.find('t:Actions/t:Exec/t:Command', ns).text.endswith('pythonw.exe') and
             arbre.find('t:Actions/t:Exec/t:Arguments', ns).text == r'"C:\Users\nathan\Suivi FWD & co\robot.py" auto')

print('\n— La case du tableau, choisie dans la liste —')
reponses = []
builtins.input = lambda invite='': reponses.pop(0)
cases = ['GATES HDK', 'GATES HDK Tranche 2', 'GATES THS', 'SEE']
reponses[:] = ['']
verifier('Entrée : la case qui porte le nom de l’export', robot.choisir_case(cases, 'GATES HDK Tranche 2') == 'GATES HDK Tranche 2')
reponses[:] = ['9', 'abc', '3']
verifier('un numéro hors liste est redemandé, puis le bon est pris', robot.choisir_case(cases, 'GATES X') == 'GATES THS')
reponses[:] = ['GATES HDK']
verifier('sans liste (fenêtre d’import fermée) : le nom tapé, comme avant', robot.choisir_case([], 'GATES HDK') == 'GATES HDK')

print('\n— GATES : appris sur un contrat, refait pour tous —')
CONTRATS = robot.contrats_du_tableau(['GATES HDK', 'GATES HDK Tranche 2', 'GATES THS', 'SEE'])
verifier('les contrats du jour, lus dans les cases de la fenêtre d’import', CONTRATS == ['HDK', 'HDK Tranche 2', 'THS'], CONTRATS)
gestes = [
    {'faire': 'cliquer', 'cible': {'texte': 'Exports', 'chemin': 'nav > a:nth-of-type(2)'}},
    {'faire': 'remplir', 'cible': {'balise': 'input', 'placeholder': 'Contrat', 'texte': 'HDK'}, 'texte': 'HDK'},   # appris avec la version d'avant
    {'faire': 'cliquer', 'cible': {'texte': 'HDK — 634 plans', 'chemin': 'ul > li:nth-of-type(1)'}},
    {'faire': 'choisir', 'cible': {'label': 'Format'}, 'valeur': 'xlsx', 'option': 'Excel'},
    {'faire': 'cliquer', 'cible': {'texte': 'Exporter vers PATHS', 'titre': 'Exporter HDK'}},
]
reponses[:] = []
appris, contrat = robot.reperer_contrat(gestes, CONTRATS)
verifier('le nom tapé est celui d’un contrat du tableau : retrouvé seul, sans question', (appris, contrat) == ('HDK', 'HDK'), (appris, contrat))
ths = robot.pour_le_contrat({'nom': 'GATES', 'etapes': gestes, 'depart': 'x'}, 'HDK', 'THS', 'THS')['etapes']
verifier('pour THS : le champ reçoit « THS »', ths[1]['texte'] == 'THS', ths[1])
verifier('… et rien n’est exigé du champ lui-même (vide quand le robot arrive)', 'contient' not in ths[1]['cible'], ths[1])
verifier('… la ligne cliquée doit porter « THS » (exigé), sinon rien n’est cliqué',
         ths[2]['cible']['texte'] == 'THS — 634 plans' and ths[2]['cible']['contient'] == 'THS', ths[2])
verifier('… ce qui ne parlait pas du contrat ne change pas (Exports, Format)',
         ths[0] == gestes[0] and ths[3]['valeur'] == 'xlsx' and 'contient' not in ths[0]['cible'] and 'contient' not in ths[3]['cible'])
verifier('… en mot entier : « PATHS » ne devient pas « PATTHS », le titre « Exporter HDK » devient « Exporter THS »',
         ths[4]['cible']['texte'] == 'Exporter vers PATHS' and ths[4]['cible']['titre'] == 'Exporter THS' and 'contient' not in ths[4]['cible'], ths[4])
verifier('le scénario appris n’est pas touché', gestes[1]['texte'] == 'HDK' and 'contient' not in gestes[2]['cible'])
reponses[:] = ['1', '3']
autre = [{'faire': 'remplir', 'cible': {}, 'texte': 'THSA'}, {'faire': 'cliquer', 'cible': {'texte': 'Valider'}}]
verifier('un nom tapé qui n’est pas celui du tableau (« THSA ») : on demande lequel, et pour quel contrat',
         robot.reperer_contrat(autre, CONTRATS) == ('THSA', 'THS'))
reponses[:] = ['0']
verifier('« aucun » : rien n’est retenu', robot.reperer_contrat(autre, CONTRATS) == ('', ''))
(R / 'exports' / 'gates.json').write_text(__import__('json').dumps({'nom': 'GATES', 'depart': 'x', 'etapes': gestes, 'modele': {'appris': 'HDK'}}), encoding='utf-8')
(R / 'exports' / 'see.json').write_text(__import__('json').dumps({'nom': 'SEE', 'depart': 'y', 'etapes': []}), encoding='utf-8')
liste = [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}, {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]
travaux = robot.a_faire({'noms_gates': {'HDK Tranche 2': 'HDKB'}}, liste, CONTRATS)
verifier('chaque jour : un export GATES par contrat du tableau, chacun dans sa case, puis SEE',
         [e['case'] for e, _ in travaux] == ['GATES HDK', 'GATES HDK Tranche 2', 'GATES THS', 'SEE'], [e for e, _ in travaux])
verifier('un contrat qui s’écrit autrement dans GATES (« HDKB ») : c’est ce nom-là qui est tapé',
         travaux[1][1]['etapes'][1]['texte'] == 'HDKB' and travaux[2][1]['etapes'][1]['texte'] == 'THS')
verifier('un contrat ajouté au tableau (VRK) est pris tout seul, sous son nom',
         [e['case'] for e, _ in robot.a_faire({}, liste, CONTRATS + ['VRK'])][3] == 'GATES VRK')
try:
    robot.a_faire({}, liste, [])
    vide = False
except robot.ErreurPilote:
    vide = True
verifier('aucun contrat lu dans le tableau : le passage s’arrête (il n’exporte rien au hasard)', vide)

print('\n— Dans un vrai navigateur : jamais un autre contrat —')
try:
    from piloter_chrome import Chrome, chemin_chrome
    exe = chemin_chrome()
except Exception:  # noqa: BLE001
    exe = None
if not exe:
    print('  (pas de Chrome sur ce poste : partie sautée)')
else:
    import json as _json
    import urllib.parse
    PAGE = ('<ul><li>HDK</li><li>HDK Tranche 2</li><li>THS — 180 plans</li></ul>'
            '<div class="case"><span class="etiquette">GATES HDK</span><div class="note"></div><button class="retirer">Retirer</button></div>'
            '<div class="case"><span class="etiquette">GATES THS</span><div class="note">seulement 3 plans sur 186 en commun avec « THS » : est-ce bien son export ?</div>'
            '<button class="retirer" onclick="this.dataset.clic=1">Retirer</button></div>'
            '<div class="case see"><span class="etiquette">SEE</span><div class="note" hidden>x</div></div>')
    profil = tempfile.mkdtemp(prefix='robot-chrome-')
    options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
    with Chrome(port=9455, lancer=True, profil=profil, sans_fenetre=True, delai=30, options=options) as c:
        c.ouvrir('data:text/html;charset=utf-8,' + urllib.parse.quote(PAGE))
        # La balise : le guetteur la note toujours (decrire), comme ici.
        prend = lambda cible: c.evaluer(robot.TROUVER % _json.dumps(cible)) and c.evaluer('window.__suiviCible.textContent')   # noqa: E731
        verifier('appris sur la première ligne, demandé pour THS : c’est la ligne de THS qui est prise',
                 prend({'balise': 'li', 'texte': 'THS — 180 plans', 'contient': 'THS', 'chemin': 'ul > li:nth-of-type(1)'}) == 'THS — 180 plans')
        verifier('demandé pour HDK : « HDK », pas « HDK Tranche 2 »',
                 prend({'balise': 'li', 'texte': 'HDK', 'contient': 'HDK', 'chemin': 'ul > li:nth-of-type(2)'}) == 'HDK')
        verifier('un contrat absent de la liste (VRK) : rien n’est pris, même à la place apprise',
                 c.evaluer(robot.TROUVER % _json.dumps({'balise': 'li', 'texte': 'VRK', 'contient': 'VRK', 'chemin': 'ul > li:nth-of-type(1)'})) is None)
        verifier('« HDK » n’est pas trouvé dans « HDKB » (mot entier)',
                 c.evaluer(robot.TROUVER % _json.dumps({'balise': 'li', 'texte': 'HDKB', 'contient': 'HDKB'})) is None)
        a = robot.deposer.__code__.co_consts
        js = [k for k in a if isinstance(k, str) and '.note' in k]
        douteux = c.evaluer(''.join(js)) if js else None
        verifier('fenêtre d’import : le fichier dont la fenêtre doute (GATES THS) est retiré, les autres restent',
                 douteux and len(douteux) == 1 and douteux[0].startswith('GATES THS — seulement 3 plans') and
                 c.evaluer('document.querySelectorAll(".retirer")[1].dataset.clic') == '1', douteux)

print('\n— SEE : le champ PSN, appris puis refait (vrai navigateur) —')
if exe:
    import json as _json
    import time as _time
    import urllib.parse as _up
    # Trois pages comme SEE peut les faire. La boîte de création s'ouvre, le PSN se tape, « Submit ».
    DIALOGUE = ('<button id="creer" onclick="document.getElementById(\'dlg\').hidden=false">Create document</button>%s'
                '<div id="dlg" hidden><div class="ligne"><span class="t">PSN</span><div><input class="x"></div></div>'
                '<button onclick="document.getElementById(\'res\').textContent=\'créé pour \'+document.querySelector(\'#dlg input\').value">Submit</button></div>'
                '<div id="res"></div>')
    SUGGESTIONS = ('<div><span>PSN</span><input class="x"></div><ul id="sugg"></ul><div id="puce"></div>'
                   '<button onclick="document.getElementById(\'res\').textContent=\'créé pour \'+document.getElementById(\'puce\').textContent">Submit</button><div id="res"></div>'
                   '<script>var i=document.querySelector("input"),u=document.getElementById("sugg");'
                   'i.addEventListener("input",function(){u.innerHTML=i.value?"<li>"+i.value+"</li>":"";});'
                   'u.addEventListener("mousedown",function(e){e.preventDefault();});'
                   'u.addEventListener("click",function(e){if(e.target.tagName==="LI"){document.getElementById("puce").textContent=e.target.textContent;i.value="";u.innerHTML="";}});</script>')
    FANTOME = ('<champ-psn></champ-psn><button onclick="document.getElementById(\'res\').textContent=\'créé pour \'+document.querySelector(\'champ-psn\').shadowRoot.querySelector(\'input\').value">Submit</button><div id="res"></div>'
               '<script>customElements.define("champ-psn",class extends HTMLElement{constructor(){super();'
               'this.attachShadow({mode:"open"}).innerHTML="<div><span>PSN</span><input></div>";}});</script>')
    page_de = lambda html: 'data:text/html;charset=utf-8,' + _up.quote('<!doctype html><meta charset="utf-8"><body>' + html)   # noqa: E731
    centre = lambda sel: c.evaluer('(function(){var e=%s;var r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()' % sel)   # noqa: E731

    def apprendre_sur(html, gestes_personne):
        """Ce que fait « Apprendre » : le guetteur dans la page, la personne agit (vrais clics, vraie frappe)."""
        c.ouvrir(page_de(html))
        c.evaluer('window.__vus=[];window.__suiviFwd=function(s){window.__vus.push(s);}')
        c.evaluer(robot.GUETTEUR)
        for g in gestes_personne:
            g()
            _time.sleep(0.3)
        _time.sleep(1.0)                                           # la frappe regroupée part (0,8 s)
        pas = []
        for brut in c.evaluer('window.__vus'):
            robot.ajouter_geste(pas, _json.loads(brut))
        return pas

    def clic(sel):
        return lambda: robot.souris(c, centre(sel)['x'], centre(sel)['y'])

    def taper(texte):
        return lambda: c.envoyer('Input.insertText', text=texte)

    robot.DELAI_TROUVER = 10           # un élément introuvable : dit en 10 s, pas en 2 min

    def rejouer_sur(html, pas):
        c.ouvrir(page_de(html))
        c.evaluer(robot.RESEAU_JS)
        try:
            for g in pas:
                robot.faire_geste(c, g)
                _time.sleep(0.4)
        except robot.ErreurPilote as err:
            return 'erreur : %s' % err
        return c.evaluer('document.getElementById("res").textContent')

    options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
    with Chrome(port=9456, lancer=True, profil=tempfile.mkdtemp(prefix='robot-see-'), sans_fenetre=True, delai=30, options=options) as c:
        pas = apprendre_sur(DIALOGUE % '', [clic('document.getElementById("creer")'), clic('document.querySelector("#dlg input")'),
                                            taper('4530'), clic('document.querySelector("#dlg button")')])
        rempli = [g for g in pas if g['faire'] == 'remplir']
        verifier('appris : le champ est retenu par son nom « PSN », pas par ce qu’on y a tapé',
                 len(rempli) == 1 and rempli[0]['cible'].get('etiquette') == 'PSN' and rempli[0]['cible'].get('texte') == '' and rempli[0]['texte'] == '4530',
                 [(g['faire'], g['cible'].get('etiquette'), g['cible'].get('texte'), g.get('texte')) for g in pas])
        verifier('appris : trois gestes, dans l’ordre (Create document, PSN 4530, Submit)',
                 [g['faire'] for g in pas] == ['cliquer', 'remplir', 'cliquer'], [g['faire'] for g in pas])
        verifier('refait le lendemain (champ vide) : « créé pour 4530 »', rejouer_sur(DIALOGUE % '', pas) == 'créé pour 4530')
        verifier('… même si la boîte s’ouvre ailleurs dans la page (son chemin a changé)',
                 rejouer_sur(DIALOGUE % '<div><p>Bandeau du jour</p><div></div></div>', pas) == 'créé pour 4530')
        ancien = [dict(g) for g in pas]
        ancien[1] = dict(ancien[1], cible=dict(ancien[1]['cible'], texte='4530', etiquette=''))   # comme l'enregistrait la version d'avant
        verifier('un SEE appris avec la version d’avant (le champ décrit par « 4530 ») : refait quand même',
                 rejouer_sur(DIALOGUE % '', ancien) == 'créé pour 4530')
        perdu = [dict(g) for g in pas]
        perdu[1] = dict(perdu[1], cible=dict(perdu[1]['cible'], etiquette='Machine', chemin='div#nulle-part > input'))
        dit = rejouer_sur(DIALOGUE % '', perdu)
        verifier('un champ vraiment introuvable : l’erreur dit son nom et les champs visibles (« PSN »)',
                 dit.startswith('erreur : Je ne retrouve plus le champ « Machine »') and '« PSN »' in dit, dit)

        pas = apprendre_sur(SUGGESTIONS, [clic('document.querySelector("input")'), taper('4530'),
                                          clic('document.querySelector("#sugg li")'), clic('document.querySelector("button")')])
        verifier('liste de suggestions : la frappe « 4530 » est apprise AVANT le clic sur la suggestion « 4530 »',
                 [(g['faire'], g.get('texte') or g['cible'].get('texte')) for g in pas] == [('remplir', '4530'), ('cliquer', '4530'), ('cliquer', 'Submit')],
                 [(g['faire'], g.get('texte') or g['cible'].get('texte')) for g in pas])
        verifier('… et refaite : « créé pour 4530 »', rejouer_sur(SUGGESTIONS, pas) == 'créé pour 4530')

        pas = apprendre_sur(FANTOME, [clic('document.querySelector("champ-psn").shadowRoot.querySelector("input")'), taper('4530'),
                                      clic('document.querySelector("button")')])
        rempli = [g for g in pas if g['faire'] == 'remplir']
        verifier('champ dans un composant à racine fantôme : appris, avec son nom « PSN »',
                 len(rempli) == 1 and rempli[0]['cible'].get('etiquette') == 'PSN', [(g['faire'], g['cible']) for g in pas])
        verifier('… et refait : « créé pour 4530 »', rejouer_sur(FANTOME, pas) == 'créé pour 4530')

        # SEE après « Submit » : la page calcule, le bouton « Export all » (une icône) est grisé puis couvert, puis le menu XLSX.
        CALCUL = ('<div class="ligne"><span>PSN</span><input></div><button id="submit">Submit</button><div id="zone"></div>'
                  '<script>document.getElementById("submit").onclick=function(){var z=document.getElementById("zone");'
                  'z.innerHTML=\'<div class="%(voile)s" style="position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.2)"></div>\'+'
                  '\'<button class="exp" %(gris)s mattooltip="Export all"><svg data-icon="file-export" width="16" height="16"><path d="M0 0h16v16H0z"/></svg></button>\'+'
                  '\'<ul id="menu"></ul><div id="res"></div>\';'
                  'setTimeout(function(){z.firstChild.remove();z.querySelector(".exp").disabled=false;},3000);'
                  'z.querySelector(".exp").onclick=function(){document.getElementById("menu").innerHTML="<li>CSV</li><li>XLSX</li>";};'
                  'document.getElementById("menu").onclick=function(e){if(e.target.tagName==="LI")document.getElementById("res").textContent='
                  '"export "+e.target.textContent+" pour "+document.querySelector("input").value;};};</script>')
        attente = lambda s: lambda: _time.sleep(s)   # noqa: E731
        lent = CALCUL % {'voile': 'loading-overlay', 'gris': 'disabled'}
        pas = apprendre_sur(lent, [clic('document.querySelector("input")'), taper('4530'), clic('document.getElementById("submit")'),
                                   attente(3.5), clic('document.querySelector(".exp svg path")'), clic('document.querySelectorAll("#menu li")[1]')])
        verifier('appris : le bouton icône est retenu par sa bulle « Export all » et son icône — plus un simple « cliquer »',
                 [robot.dire_geste(g) for g in pas] == ['« 4530 » dans le champ « PSN »', '« Submit »', '« Export all »', '« XLSX »'],
                 [robot.dire_geste(g) for g in pas])
        verifier('… c’est le bouton qui est appris, pas le trait du dessin',
                 pas[2]['cible'].get('balise') == 'button' and pas[2]['cible'].get('icone') == 'file-export', pas[2]['cible'])
        verifier('refait : il attend la fin du calcul (roue de chargement), puis « Export all », puis XLSX',
                 rejouer_sur(lent, pas) == 'export XLSX pour 4530')
        couvert = CALCUL % {'voile': 'voile', 'gris': ''}
        verifier('… même sans roue : bouton couvert par un voile 3 s, il attend qu’il se lève avant de cliquer',
                 rejouer_sur(couvert, pas) == 'export XLSX pour 4530')
        grise = CALCUL % {'voile': 'rien" hidden data-x="', 'gris': 'disabled'}
        verifier('… et bouton grisé 3 s : il attend qu’il s’allume',
                 rejouer_sur(grise, pas) == 'export XLSX pour 4530')
        sans = [dict(g) for g in pas]
        sans[2] = dict(sans[2], cible=dict(sans[2]['cible'], bulle='Exporter tout', icone='autre', chemin='nulle > part'))
        dit = rejouer_sur(lent, sans)
        verifier('un bouton vraiment introuvable : l’erreur dit son nom et les boutons visibles', 
                 dit.startswith('erreur : Je ne retrouve plus « Exporter tout »') and 'Boutons visibles' in dit and '« Export all »' in dit, dit)

        # GATES de bout en bout : appris sur HDK, refait pour THS, et pour un contrat absent.
        GATES = ('<input placeholder="Contrat"><ul id="l"></ul><div id="res"></div>'
                 '<script>var C=["HDK — 634 plans","HDK Tranche 2 — 120 plans","THS — 180 plans"],i=document.querySelector("input"),l=document.getElementById("l");'
                 'i.addEventListener("input",function(){var v=i.value.toLowerCase();l.innerHTML=v?C.filter(function(c){return c.toLowerCase().indexOf(v)===0;})'
                 '.map(function(c){return "<li>"+c+"</li>";}).join(""):"";});'
                 'l.addEventListener("click",function(e){if(e.target.tagName==="LI")document.getElementById("res").textContent="export "+e.target.textContent;});</script>')
        pas = apprendre_sur(GATES, [clic('document.querySelector("input")'), taper('HDK'), clic('document.querySelector("#l li")')])
        appris, contrat = robot.reperer_contrat(pas, ['HDK', 'HDK Tranche 2', 'THS'])
        scen = {'nom': 'GATES', 'depart': 'x', 'etapes': pas}
        verifier('GATES appris sur HDK : le nom du contrat est retrouvé seul', (appris, contrat) == ('HDK', 'HDK'), (appris, contrat, pas))
        verifier('… refait pour THS : c’est THS qui est exporté',
                 rejouer_sur(GATES, robot.pour_le_contrat(scen, 'HDK', 'THS', 'THS')['etapes']) == 'export THS — 180 plans')
        verifier('… refait pour HDK Tranche 2 : la bonne tranche',
                 rejouer_sur(GATES, robot.pour_le_contrat(scen, 'HDK', 'HDK Tranche 2', 'HDK Tranche 2')['etapes']) == 'export HDK Tranche 2 — 120 plans')
        verifier('… refait pour HDK : HDK, pas sa tranche 2',
                 rejouer_sur(GATES, robot.pour_le_contrat(scen, 'HDK', 'HDK', 'HDK')['etapes']) == 'export HDK — 634 plans')
        dit = rejouer_sur(GATES, robot.pour_le_contrat(scen, 'HDK', 'VRK', 'VRK')['etapes'])
        verifier('… pour un contrat que GATES ne montre pas (VRK) : il s’arrête, rien n’est exporté à sa place',
                 dit.startswith('erreur : Je ne retrouve plus « VRK — 634 plans »'), dit)

print('\n═══════════════════════════════════════')
print('%d vérification(s) réussie(s), %d échec(s)' % (len(faits), len(echecs)))
for e in echecs:
    print('  · ' + e)
sys.exit(1 if echecs else 0)
