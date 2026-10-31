#!/usr/bin/env python3
"""
Batterie du robot, sans navigateur ni Windows : ce qui décide QUAND il passe.

    python3 import/tests_robot.py

— pas avant son heure (14 h par défaut) ;
— une fois par jour : un passage réussi, et plus rien jusqu'au lendemain,
  quels que soient les redémarrages et les ouvertures de session ;
— raté, il réessaie lui-même, trois passages au plus par jour, et ne le
  dit (une petite fenêtre) qu'après le dernier ;
— jamais deux robots à la fois (verrou), et un verrou laissé par un
  ordinateur éteint en plein passage ne bloque pas le lendemain ;
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
    verifier('le verrou est posé (en-cours.txt)', (R / 'en-cours.txt').exists())
    robot.lancer(auto=True)
    verifier('pendant un passage (ou « apprendre »), le passage automatique s’en va sans rien faire', nb('passage') == 0 and nb('prevenu') == 0, appels)
    verifier('… et « Lancer maintenant » le dit (code 1)', robot.lancer(auto=False) == 1)
    with robot.verrou(silencieux=True) as second:
        verifier('un second verrou est refusé', second is False)
verifier('le verrou est rendu à la fin', not (R / 'en-cours.txt').exists())
(R / 'en-cours.txt').write_text('1234 hier', encoding='utf-8')
vieux = datetime.datetime.now().timestamp() - 3 * 3600
os.utime(R / 'en-cours.txt', (vieux, vieux))
robot.lancer(auto=True)
verifier('un verrou de plus de deux heures (ordinateur éteint en plein passage) ne bloque plus', nb('passage') == 1, appels)


def boum(auto):
    raise RuntimeError('panne')


remettre()
robot._passage = boum
try:
    robot.lancer(auto=True)
except RuntimeError:
    pass
verifier('une panne imprévue rend quand même le verrou', not (R / 'en-cours.txt').exists())

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
    {'faire': 'remplir', 'cible': {'placeholder': 'Contrat', 'texte': ''}, 'texte': 'HDK'},
    {'faire': 'cliquer', 'cible': {'texte': 'HDK — 634 plans', 'chemin': 'ul > li:nth-of-type(1)'}},
    {'faire': 'choisir', 'cible': {'label': 'Format'}, 'valeur': 'xlsx', 'option': 'Excel'},
    {'faire': 'cliquer', 'cible': {'texte': 'Exporter vers PATHS', 'titre': 'Exporter HDK'}},
]
reponses[:] = []
appris, contrat = robot.reperer_contrat(gestes, CONTRATS)
verifier('le nom tapé est celui d’un contrat du tableau : retrouvé seul, sans question', (appris, contrat) == ('HDK', 'HDK'), (appris, contrat))
ths = robot.pour_le_contrat({'nom': 'GATES', 'etapes': gestes, 'depart': 'x'}, 'HDK', 'THS', 'THS')['etapes']
verifier('pour THS : le champ reçoit « THS »', ths[1]['texte'] == 'THS', ths[1])
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

print('\n═══════════════════════════════════════')
print('%d vérification(s) réussie(s), %d échec(s)' % (len(faits), len(echecs)))
for e in echecs:
    print('  · ' + e)
sys.exit(1 if echecs else 0)
