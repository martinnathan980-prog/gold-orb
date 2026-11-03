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
  retrouvé dans les gestes, remplacé partout, et exigé sur ce qu'on clique ;
— débrief 30 : les contrats et leur nom GATES lus dans la fenêtre d'import
  (le site l'emporte sur ce que le robot avait retenu), les prévus compris ;
  les exports d'avant rangés tout seuls (GATES HDK devient le modèle de tous,
  une seule exportation par case, les autres en secours) ; les erreurs de
  chaque contrat dites au tableau de bord par le pont de la fenêtre ; une
  erreur « de fiche » ne fait ni nouvel essai ni fenêtre d'alerte ; et, avec
  Node, la VRAIE fenêtre (vrai Code.gs, tests/fenetre-pour-robot.js) menée
  par le robot, jusqu'au passage entier avec la configuration de Nathan.

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
PASSAGE = robot._passage                  # le vrai, essayé plus bas avec ses outils simulés
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

# ---------------------------------------------------------------- Débrief 30
import json  # noqa: E402
import shutil  # noqa: E402

print('\n— Débrief 30 : les contrats lus dans la fenêtre d’import (nom GATES, prévus) —')
TABLEAU = {'cases': ['GATES HDK', 'GATES VRK', 'SEE'],
           'contrats': [{'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': '', 'prevu': False},
                        {'contrat': 'VRK', 'case': 'GATES VRK', 'nom_gates': 'VRK-AA', 'prevu': True}]}
lus = robot.contrats_lus(TABLEAU)
verifier('chaque case dit son contrat, son nom GATES (la fiche) et s’il est prévu',
         lus == TABLEAU['contrats'], lus)
avant = robot.contrats_lus({'cases': ['GATES HDK', 'GATES THS', 'SEE'], 'contrats': [{'contrat': '', 'case': 'GATES HDK'}, {'case': 'GATES THS'}]})
verifier('une fenêtre d’avant (sans data-contrat) : les contrats tirés des étiquettes, sans nom GATES ni prévu',
         avant == [robot.en_contrat('HDK'), robot.en_contrat('THS')] and avant[1] == {'contrat': 'THS', 'case': 'GATES THS', 'nom_gates': '', 'prevu': False}, avant)
cfg_noms = {'noms_gates': {'hdk': 'HDKX'}}
verifier('le nom tapé dans GATES : celui de la fiche (le site) l’emporte sur celui que le robot avait retenu',
         robot.nom_gates_de(cfg_noms, {'contrat': 'HDK', 'nom_gates': 'HDK T1'}) == 'HDK T1')
verifier('… sans fiche, celui que le robot avait retenu (casse indifférente), sinon le nom du contrat',
         robot.nom_gates_de(cfg_noms, {'contrat': 'HDK', 'nom_gates': ''}) == 'HDKX' and robot.nom_gates_de(cfg_noms, 'THS') == 'THS')

print('\n— Débrief 30 : les exports rangés tout seuls (rien à réapprendre) —')
EXP = R / 'exports'


def scenario(fichier, nom, appris, etapes, **plus):
    (EXP / fichier).write_text(json.dumps(dict({'nom': nom, 'depart': 'x', 'etapes': etapes, 'fichier': '*.xlsx', 'appris': appris}, **plus),
                                          ensure_ascii=False), encoding='utf-8')


def journal():
    f = R / 'journal.txt'
    return f.read_text(encoding='utf-8') if f.exists() else ''


GESTES_HDK = [{'faire': 'cliquer', 'cible': {'texte': 'Exports'}},
              {'faire': 'remplir', 'cible': {'balise': 'input', 'placeholder': 'Contrat'}, 'texte': 'HDK'},
              {'faire': 'cliquer', 'cible': {'texte': 'HDK — 634 plans'}},
              {'faire': 'cliquer', 'cible': {'texte': 'XLSX'}}]
scenario('gates-hdk.json', 'GATES HDK', '2026-10-01T09:00:00', GESTES_HDK)
scenario('see-hdk.json', 'SEE HDK', '2026-10-05T09:00:00', [{'faire': 'cliquer', 'cible': {'texte': 'Submit'}}])
scenario('see.json', 'SEE', '2026-10-20T09:00:00', [{'faire': 'cliquer', 'cible': {'texte': 'Submit'}}])
NATHAN = {'tableau': 'https://script.google.com/a/macros/airbus.com/s/x/exec', 'heure': '14:00',
          'exports': [{'nom': 'GATES HDK', 'scenario': 'gates-hdk.json', 'case': 'GATES HDK'},
                      {'nom': 'SEE HDK', 'scenario': 'see-hdk.json', 'case': 'SEE'},
                      {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]}
COPIE = R / 'robot.avant-rangement.json'
if COPIE.exists():
    COPIE.unlink()
robot.garder(json.loads(json.dumps(NATHAN)))
dit_avant = journal().count('Exports rangés')
cfg = robot.config()
change = robot.ranger_exports(cfg)
verifier('chez Nathan : [GATES HDK, SEE HDK, SEE] devient [GATES pour tous les contrats, SEE avec SEE HDK en secours]',
         change and cfg['exports'] == [{'nom': 'GATES', 'scenario': 'gates-hdk.json', 'modele': True},
                                       {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE', 'secours': ['see-hdk.json']}], cfg['exports'])
migre = json.loads((EXP / 'gates-hdk.json').read_text(encoding='utf-8'))
verifier('… l’ancien GATES HDK est devenu le modèle, appris sur « HDK » (retrouvé dans ses gestes, sans question), ses gestes intacts',
         migre.get('modele') == {'appris': 'HDK', 'contrat': 'HDK', 'migre': True} and migre['etapes'] == GESTES_HDK, migre.get('modele'))
verifier('… robot.json réécrit, mais d’abord copié dans robot.avant-rangement.json (la configuration d’avant, intacte)',
         robot.config() == cfg and COPIE.exists() and json.loads(COPIE.read_text(encoding='utf-8')) == NATHAN)
verifier('… aucun fichier d’export effacé', all((EXP / f).exists() for f in ('gates-hdk.json', 'see-hdk.json', 'see.json')))
verifier('… dit une fois dans le journal', journal().count('Exports rangés') == dit_avant + 1, journal()[-400:])
cfg2 = robot.config()
verifier('un second rangement ne change rien (ni la configuration, ni le journal)',
         robot.ranger_exports(cfg2) is False and cfg2 == cfg and journal().count('Exports rangés') == dit_avant + 1)
travaux = robot.a_faire(cfg2, cfg2['exports'], robot.contrats_lus(TABLEAU))
verifier('les exports du jour, après rangement : GATES HDK, GATES VRK (prévu), puis SEE une seule fois — avec son secours chargé',
         [e['case'] for e, _ in travaux] == ['GATES HDK', 'GATES VRK', 'SEE'] and travaux[2][0]['fichier'] == 'see.json' and
         [f for f, _ in travaux[2][0]['secours']] == ['see-hdk.json'] and travaux[2][0]['secours'][0][1]['nom'] == 'SEE HDK',
         [(e['case'], e.get('fichier'), [f for f, _ in e.get('secours') or []]) for e, _ in travaux])
verifier('… GATES HDK tape toujours « HDK », comme avant',
         travaux[0][1]['etapes'][1]['texte'] == 'HDK' and travaux[0][1]['etapes'][2]['cible']['contient'] == 'HDK')

robot.garder(dict(json.loads(json.dumps(NATHAN)), reussis={'see': 'see-hdk.json'}))
scenario('gates-hdk.json', 'GATES HDK', '2026-10-01T09:00:00', GESTES_HDK)     # tel qu'avant la migration
copie_avant = COPIE.read_text(encoding='utf-8')
cfg = robot.config()
robot.ranger_exports(cfg)
verifier('SEE HDK a marché la dernière fois (reussis) : c’est lui qui passe en premier, SEE en secours',
         cfg['exports'][1] == {'nom': 'SEE HDK', 'scenario': 'see-hdk.json', 'case': 'SEE', 'secours': ['see.json']}, cfg['exports'])
verifier('… la copie de robot.json n’est faite qu’une fois (celle d’avant reste)', COPIE.read_text(encoding='utf-8') == copie_avant)

scenario('gates.json', 'GATES', '2026-10-25T09:00:00', GESTES_HDK, modele={'appris': 'HDK'})
scenario('gates-ths.json', 'GATES THS', '2026-10-02T09:00:00',
         [{'faire': 'remplir', 'cible': {'placeholder': 'Contrat'}, 'texte': 'THSA'}, {'faire': 'cliquer', 'cible': {'texte': 'XLSX'}}])
robot.garder({'tableau': 'x', 'noms_gates': {}, 'exports': [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True},
                                                             {'nom': 'GATES THS', 'scenario': 'gates-ths.json', 'case': 'GATES THS'}]})
cfg = robot.config()
robot.ranger_exports(cfg)
verifier('un ancien « GATES THS » appris sur « THSA », à côté du modèle : il s’efface, et « THSA » est retenu comme nom GATES de THS',
         cfg['exports'] == [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}] and cfg['noms_gates'] == {'THS': 'THSA'} and
         (EXP / 'gates-ths.json').exists(), cfg)

scenario('gates-x.json', 'GATES X', '2026-10-02T09:00:00', [{'faire': 'remplir', 'cible': {}, 'texte': 'Projet 7'}, {'faire': 'cliquer', 'cible': {'texte': 'XLSX'}}])
robot.garder({'tableau': 'x', 'exports': [{'nom': 'GATES X', 'scenario': 'gates-x.json', 'case': 'GATES X'}]})
cfg = robot.config()
avant_x = journal().count('il reste l’export de X seul')
robot.ranger_exports(cfg)
robot.ranger_exports(robot.config())
verifier('le mot d’un contrat dans ses gestes : exact, ou celui que le robot avait retenu ; un mot tapé tout proche (« THSA ») ; jamais un autre',
         robot.mot_du_contrat(GESTES_HDK, 'hdk', {}) == 'HDK' and robot.mot_du_contrat([{'faire': 'choisir', 'option': 'Hdk-B'}], 'HDK', {'HDK': 'HDK-B'}) == 'Hdk-B' and
         robot.mot_du_contrat([{'faire': 'remplir', 'texte': 'THSA'}], 'THS', {}) == 'THSA' and
         robot.mot_du_contrat([{'faire': 'remplir', 'texte': 'Projet 7'}], 'X', {}) == '' and
         robot.mot_du_contrat([{'faire': 'cliquer', 'cible': {'texte': 'THSA'}}], 'THS', {}) == '')
verifier('un « GATES X » dont le nom n’est pas dans ses gestes : laissé tel quel (l’export de X seul), dit une fois au journal',
         cfg['exports'] == [{'nom': 'GATES X', 'scenario': 'gates-x.json', 'case': 'GATES X'}] and 'modele' not in
         json.loads((EXP / 'gates-x.json').read_text(encoding='utf-8')) and journal().count('il reste l’export de X seul') == avant_x + 1)
(EXP / 'abime.json').write_text('{pas du json', encoding='utf-8')
robot.garder({'tableau': 'x', 'exports': [{'nom': 'Autre', 'scenario': 'abime.json', 'case': 'Autre'}, {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]})
cfg = robot.config()
verifier('un export au fichier illisible reste tel quel', robot.ranger_exports(cfg) is False and len(cfg['exports']) == 2)

print('\n— Débrief 30 : un export par contrat, le nom GATES de la fiche —')
liste = [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}, {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]
travaux = robot.a_faire({'noms_gates': {'HDK': 'HDKX'}}, liste,
                        [{'contrat': 'HDK', 'nom_gates': '', 'case': 'GATES HDK', 'prevu': False},
                         {'contrat': 'VRK', 'nom_gates': 'VRK-AA', 'case': 'GATES VRK', 'prevu': True}])
verifier('HDK tape « HDKX » (retenu par le robot), VRK tape « VRK-AA » (sa fiche), dans la case « GATES VRK », prévu',
         travaux[0][1]['etapes'][1]['texte'] == 'HDKX' and travaux[1][1]['etapes'][1]['texte'] == 'VRK-AA' and
         travaux[1][0] == {'nom': 'GATES VRK', 'case': 'GATES VRK', 'contrat': 'VRK', 'nom_gates': 'VRK-AA', 'prevu': True}, [e for e, _ in travaux])
verifier('des noms seuls (comme avant) : le même résultat',
         [(e['case'], s['etapes'][1]['texte']) for e, s in robot.a_faire({'noms_gates': {'HDK': 'HDKX'}}, liste, ['HDK', 'VRK'])[:2]] ==
         [('GATES HDK', 'HDKX'), ('GATES VRK', 'VRK')])

print('\n— Débrief 30 : les exports du jour, leurs erreurs dites au tableau de bord —')
vrai_rejouer, vraie_photo = robot.rejouer, robot.photo
robot.photo = lambda c: ''
SORTIE = pathlib.Path(tempfile.mkdtemp(prefix='robot-sorties-'))


def rejouer_simule(pannes):
    """pannes : nom du scénario → l'erreur levée (ErreurPilote, avec geste et introuvable au besoin)."""
    def rejouer(c, s, dossier):
        err = pannes.get(s['nom'])
        if err:
            raise err
        f = SORTIE / (robot.nom_de_fichier(s['nom']) + '.xlsx')
        f.write_text('x', encoding='utf-8')
        return f
    return rejouer


def panne(texte, geste=None, introuvable=None):
    e = robot.ErreurPilote(texte)
    e.geste = geste
    if introuvable is not None:
        e.introuvable = introuvable
    return e


robot.garder({'tableau': 'x', 'exports': []})
cfg = robot.config()
robot.rejouer = rejouer_simule({'GATES VRK': panne('Je ne retrouve plus « VRK-AA — 634 plans » sur la page x.\n  Boutons visibles…',
                                                   {'faire': 'cliquer', 'cible': {'texte': 'VRK-AA — 634 plans', 'contient': 'VRK-AA'}})})
sortis, rates, comptes = robot.faire_les_exports(None, cfg, liste, SORTIE, robot.contrats_lus(TABLEAU))
verifier('HDK et SEE sortent ; VRK rate (GATES ne montre pas son nom) — les ratés gardent leur forme « nom : raison »',
         [e['nom'] for e, _ in sortis] == ['GATES HDK', 'SEE'] and rates == ['GATES VRK : Je ne retrouve plus « VRK-AA — 634 plans » sur la page x.'] and
         rates[0].code == 'gates-introuvable' and rates[0].contrat == 'VRK', (sortis, rates))
verifier('le compte rendu : HDK dit seulement ce qu’il a tapé (sans « ok » : la fenêtre dira l’import) ; VRK « gates-introuvable », message exact',
         comptes == [{'contrat': 'HDK', 'gates': {'tape': 'HDK'}},
                     {'contrat': 'VRK', 'gates': {'ok': False, 'code': 'gates-introuvable', 'tape': 'VRK-AA',
                                                  'message': 'GATES ne montre pas « VRK-AA » : vérifiez le « Nom exact de la tranche dans GATES » de ce contrat '
                                                             '(tableau de bord → Administration → Contrats).'}}], comptes)
robot.rejouer = rejouer_simule({'GATES VRK': panne('Le choix « VRK-AA » n\'existe pas dans la liste « Contrat ».', {'faire': 'choisir', 'option': 'VRK-AA', 'cible': {}})})
_, _, comptes = robot.faire_les_exports(None, cfg, liste, SORTIE, robot.contrats_lus(TABLEAU))
verifier('un choix de liste qui portait le nom GATES, absent : « gates-introuvable » aussi', comptes[1]['gates']['code'] == 'gates-introuvable', comptes)
robot.rejouer = rejouer_simule({'GATES VRK': panne('Après « VRK-AA », « XLSX » n\'est jamais apparu.', {'faire': 'cliquer', 'cible': {'contient': 'VRK-AA'}}, False)})
_, rates, comptes = robot.faire_les_exports(None, cfg, liste, SORTIE, robot.contrats_lus(TABLEAU))
verifier('le contrat trouvé, mais la suite ne vient pas : « gates-export », avec la raison',
         comptes[1]['gates']['code'] == 'gates-export' and comptes[1]['gates']['message'] == 'L’export GATES de VRK n’a pas abouti : Après « VRK-AA », « XLSX » n\'est jamais apparu.'
         and rates[0].code == 'gates-export', comptes)

robot.garder({'tableau': 'x', 'exports': []})
cfg = robot.config()
avec_secours = [{'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE', 'secours': ['see-hdk.json']}]
robot.rejouer = rejouer_simule({'SEE': panne('SEE ne répond pas')})
sortis, rates, comptes = robot.faire_les_exports(None, cfg, avec_secours, SORTIE, [])
verifier('SEE (la principale) cale : son secours SEE HDK est essayé, il sort — et il est retenu pour la prochaine fois',
         [e['nom'] for e, _ in sortis] == ['SEE'] and sortis[0][1].name == 'see-hdk.xlsx' and not rates and
         cfg.get('reussis') == {'see': 'see-hdk.json'} and robot.config().get('reussis') == {'see': 'see-hdk.json'}, (sortis, rates, cfg))
verifier('… le lendemain, SEE HDK passe en premier, SEE en secours',
         [(e['fichier'], [f for f, _ in e['secours']]) for e, _ in robot.a_faire(cfg, avec_secours, [])] == [('see-hdk.json', ['see.json'])])
robot.rejouer = rejouer_simule({'SEE': panne('SEE ne répond pas'), 'SEE HDK': panne('SEE ne répond toujours pas')})
sortis, rates, comptes = robot.faire_les_exports(None, robot.config(), avec_secours, SORTIE, [])
verifier('tous ratés : un seul raté, avec la raison de la première essayée', not sortis and rates == ['SEE : SEE ne répond toujours pas'], rates)
robot.rejouer, robot.photo = vrai_rejouer, vraie_photo

print('\n— Débrief 30 : le compte rendu du robot —')
r = robot.rapport_du_robot({'heure': '14:00'}, '2026-11-03T14:01:00+01:00',
                           [{'contrat': 'VRK', 'gates': {'tape': 'VRK'}}, {'contrat': 'HDK', 'gates': {'tape': 'HDK'}},
                            {'contrat': 'vrk', 'gates': {'ok': False, 'code': 'colonne-elec', 'message': 'x' * 900}}],
                           ['SEE : SEE ne répond pas'], 1)
verifier('une entrée par contrat (ce qu’il a tapé et l’erreur de sa case réunis), messages coupés à 400 caractères',
         r['contrats'][0]['contrat'] == 'VRK' and r['contrats'][0]['gates']['tape'] == 'VRK' and r['contrats'][0]['gates']['code'] == 'colonne-elec' and
         len(r['contrats'][0]['gates']['message']) == 400 and len(r['contrats']) == 2, r)
verifier('le passage : raté (une erreur technique), dit en une phrase, l’heure du robot, son début, les erreurs de fiche',
         r['source'] == 'robot' and r['passage'] == {'ok': False, 'message': 'SEE : SEE ne répond pas', 'heure': '14:00',
                                                     'debut': '2026-11-03T14:01:00+01:00', 'erreursFiche': 1}, r['passage'])
verifier('résumé d’un passage : 200 caractères au plus', len(robot.rapport_du_robot({}, '', [], ['y' * 500], 0)['passage']['message']) == 200)

print('\n— Débrief 30 : un passage dont seule une fiche est à corriger —')
etat_passage = R / 'dernier-passage.txt'
outils = {}


class FauxChrome:
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def simuler(sortis, rates, comptes, depot):
    outils.clear()
    robot.exports_choisis = lambda noms=None: ({'tableau': 'x', 'heure': '00:00'}, [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}])
    robot.chrome = lambda *a, **k: FauxChrome()
    robot.attendre_tableau = lambda c, cfg, delai: TABLEAU
    robot.faire_les_exports = lambda c, cfg, liste, dossier, contrats: (sortis, rates, comptes)

    def deposer(c, cfg, s, k, debut, rt):
        outils['deposer'] = (s, k, rt)
        return dict({'douteux': [], 'techniques': [], 'fiche': [], 'rapport': True}, **depot)

    def rendre(c, cfg, k, debut, rt):
        outils['rendre'] = (k, rt)
        return dict({'douteux': [], 'techniques': [], 'fiche': [], 'rapport': True}, **depot)
    robot.deposer, robot.rendre_compte = deposer, rendre


vrais = {n: getattr(robot, n) for n in ('exports_choisis', 'chrome', 'attendre_tableau', 'faire_les_exports', 'deposer', 'rendre_compte')}
f_hdk = SORTIE / 'gates-hdk.xlsx'
GHDK = ({'nom': 'GATES HDK', 'case': 'GATES HDK', 'contrat': 'HDK'}, f_hdk)
remettre()
simuler([GHDK], [], [], {'fiche': ['GATES VRK : La colonne de la validation ELEC « … » n’est pas dans cet export.'], 'rapport': True})
dit_avant = journal().count('erreur(s) de fiche')
verifier('seulement une erreur de fiche, et le compte rendu est arrivé : le passage réussit (0, « ok ») — ni nouvel essai ni fenêtre',
         PASSAGE(True) == (0, '') and etat_passage.read_text(encoding='utf-8').startswith(AUJ + ' ok') and
         journal().count('✓ Passage réussi — 1 erreur(s) de fiche, visibles dans le tableau de bord') == dit_avant + 1)
simuler([GHDK], [], [], {'fiche': ['GATES VRK : colonne'], 'rapport': False})
code, raison = PASSAGE(True)
verifier('… la même, mais le compte rendu n’est pas arrivé (tableau de bord d’avant, sans pont) : raté, comme aujourd’hui',
         code == 1 and 'GATES VRK : colonne' in raison and etat_passage.read_text(encoding='utf-8').startswith(AUJ + ' échec'), raison)
simuler([GHDK], [], [], {'techniques': ['La fenêtre d\'import refuse les fichiers : x'], 'rapport': True})
verifier('une erreur technique (import refusé) : raté, même avec le compte rendu', PASSAGE(True)[0] == 1)
introuvable = robot.rate('GATES VRK : Je ne retrouve plus « VRK »', 'gates-introuvable', 'VRK')
simuler([GHDK], [introuvable], [{'contrat': 'VRK', 'gates': {'ok': False, 'code': 'gates-introuvable'}}], {'rapport': True})
verifier('GATES ne montre pas VRK, mais HDK est sorti : c’est sa fiche (le nom GATES) — réussi, sans nouvel essai',
         PASSAGE(True) == (0, '') and outils['deposer'][2] == [], outils.get('deposer'))
simuler([({'nom': 'SEE', 'case': 'SEE'}, SORTIE / 'see.xlsx')], [introuvable], [], {'rapport': True})
verifier('… aucun GATES sorti : GATES ou CHILDNéo a changé — erreur technique, nouvel essai',
         PASSAGE(True)[0] == 1 and outils['deposer'][2] == [introuvable])
simuler([], [robot.rate('SEE : SEE ne répond pas')], [], {'rapport': True})
code, raison = PASSAGE(True)
verifier('rien n’est sorti : la fenêtre d’import est ouverte quand même, pour envoyer le compte rendu ; le passage rate',
         'rendre' in outils and 'deposer' not in outils and outils['rendre'][1] == ['SEE : SEE ne répond pas'] and code == 1 and raison.startswith('rien : SEE'), (outils, raison))
remettre(); appels.clear()
robot.garder({'tableau': 'x', 'exports': [], 'heure': '00:00'})
simuler([GHDK], [], [], {'fiche': ['GATES VRK : colonne'], 'rapport': True})
robot._passage = lambda auto: (appels.append(('passage', auto)), PASSAGE(auto))[1]
robot.lancer(auto=True)
robot.lancer(auto=True)
verifier('en automatique : un seul passage dans la journée, aucune fenêtre d’alerte', nb('passage') == 1 and nb('prevenu') == 0, appels)
for n, v in vrais.items():
    setattr(robot, n, v)

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
        douteux = c.evaluer(robot.DOUTEUX_JS)
        verifier('fenêtre d’import : le fichier dont la fenêtre doute (GATES THS) est retiré, les autres restent',
                 douteux and len(douteux) == 1 and douteux[0]['etiquette'] == 'GATES THS' and douteux[0]['note'].startswith('seulement 3 plans') and
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

    robot.DELAI_TROUVER = 10           # un élément introuvable : dit en 10 s, pas en 5 min
    robot.DELAI_SUITE = 4              # la suite d'un clic : 4 s avant de réessayer autrement

    def rejouer_sur(html, pas):
        c.ouvrir(page_de(html))
        c.evaluer(robot.RESEAU_JS)
        try:
            for i, g in enumerate(pas):
                robot.faire_geste(c, g, pas[i + 1] if i + 1 < len(pas) else None)
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

        # « Export all » dont le menu ne s'ouvre pas au premier clic : le robot réessaie autrement.
        RETIF = ('<button id="exp" title="Export all">⇩</button><ul id="menu"></ul><div id="res"></div>'
                 '<script>var n=0,b=document.getElementById("exp"),m=document.getElementById("menu");'
                 'var ouvrir=function(){m.innerHTML="<li>CSV</li><li>XLSX</li>";};'
                 '%s'
                 'm.onclick=function(e){if(e.target.tagName==="LI")document.getElementById("res").textContent="export "+e.target.textContent;};</script>')
        menu = [{'faire': 'cliquer', 'cible': {'balise': 'button', 'titre': 'Export all', 'texte': '⇩'}},
                {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'XLSX'}}]
        verifier('le menu ne s’ouvre qu’au second clic : le robot réessaie, le menu s’ouvre, XLSX',
                 rejouer_sur(RETIF % 'b.onclick=function(){if(++n>=2)ouvrir();};', menu) == 'export XLSX')
        verifier('le menu ne s’ouvre qu’au clavier (Entrée) : le robot finit par appuyer sur Entrée, XLSX',
                 rejouer_sur(RETIF % 'b.onkeydown=function(e){if(e.key==="Enter")ouvrir();};', menu) == 'export XLSX')
        t0 = _time.time()
        dit = rejouer_sur(RETIF % '', menu)
        verifier('rien ne l’ouvre : il le dit vite et clairement, au lieu de rester figé',
                 dit.startswith('erreur : Après « Export all », « XLSX » n’est jamais apparu'.replace('’', "'")) and _time.time() - t0 < 200, dit[:160])
        verifier('le fichier attendu juste après le geste qui le fait venir : appris, ou deviné (« XLSX ») pour un export appris avant',
                 robot.indice_telechargement({'etapes': menu + [{'faire': 'cliquer', 'cible': {'texte': 'Log out'}}], 'telechargement_apres': 2}) == 2 and
                 robot.indice_telechargement({'etapes': menu + [{'faire': 'cliquer', 'cible': {'texte': 'Log out'}}]}) == 2 and
                 robot.indice_telechargement({'etapes': [{'faire': 'cliquer', 'cible': {'texte': 'OK'}}]}) == 1)

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

print('\n— Un gros fichier, puis « Log out » (vrai navigateur) —')
if exe:
    import json as _json
    import time as _time
    import urllib.parse as _up
    # XLSX : le fichier part 3 s plus tard (il se prépare) ; un « Log out » avant l'annule.
    PAGE_LOGOUT = ('<button id="x">XLSX</button><button id="o">Log out</button><div id="res"></div>'
                   '<script>var parti=false,dehors=false;document.getElementById("x").onclick=function(){setTimeout(function(){if(dehors)return;'
                   'var a=document.createElement("a");a.href="data:application/octet-stream;base64,UEsDBA==";a.download="see.xlsx";document.body.appendChild(a);a.click();parti=true;},3000);};'
                   'document.getElementById("o").onclick=function(){dehors=true;document.getElementById("res").textContent=parti?"déconnecté après le fichier":"déconnecté trop tôt";};</script>')
    scen = {'nom': 'SEE', 'depart': 'data:text/html;charset=utf-8,' + _up.quote('<!doctype html><meta charset="utf-8"><body>' + PAGE_LOGOUT),
            'fichier': '*.xlsx', 'telechargement_apres': 1,
            'etapes': [{'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'XLSX'}}, {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Log out'}}]}
    options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
    sortie = pathlib.Path(tempfile.mkdtemp(prefix='robot-sortie-'))
    with Chrome(port=9457, lancer=True, profil=tempfile.mkdtemp(prefix='robot-dl-'), sans_fenetre=True, delai=30, options=options,
                telechargements=str(R / 'telechargements')) as c:
        try:
            f = robot.rejouer(c, scen, sortie)
            res = c.evaluer('document.getElementById("res").textContent')
        except robot.ErreurPilote as err:
            f, res = None, 'erreur : %s' % err
        verifier('le fichier (3 s à se préparer) est arrivé AVANT le « Log out » : rien n’est coupé',
                 f is not None and f.exists() and res == 'déconnecté après le fichier', (f, res))

print('\n— Débrief 30 : la fenêtre d’import lue, et le compte rendu envoyé, depuis un monde isolé (vrai navigateur) —')
if exe:
    import json as _json
    import urllib.parse as _up
    page_de = lambda html: 'data:text/html;charset=utf-8,' + _up.quote('<!doctype html><meta charset="utf-8"><body>' + html)   # noqa: E731
    # Une fenêtre comme celle du tableau de bord : ses cases (data-contrat, data-nom-gates, data-prevu, data-code),
    # son pont, et un google.script.run qui garde ce qu'il reçoit — dans le monde de la page, que le robot ne voit pas.
    CASE = ('<li class="case gates%(classe)s" data-case="g:%(id)s" data-contrat="%(id)s" data-nom-gates="%(ng)s"%(plus)s data-etat="%(etat)s">'
            '<div class="tete"><span class="etiquette">GATES %(id)s</span>%(badge)s</div><div class="lu%(lu_classe)s">%(lu)s</div>'
            '<div class="note" hidden></div><button class="retirer" onclick="this.dataset.clic=1;this.parentNode.setAttribute(\'data-etat\',\'vide\')">Retirer</button>'
            '<input type="file" class="fichier" hidden></li>')
    ELEC = ('La colonne de la validation ELEC « VRK AA 011 › Avancement Definition Electrik » n’est pas dans cet export. Les plus proches : '
            '« VRK AA 011 › Avancement Définition Electrique ». Corrigez-la dans le tableau de bord → Administration → Contrats.')
    FENETRE = ('<ul id="cases-gates">' +
               CASE % {'classe': '', 'id': 'HDK', 'ng': '', 'plus': '', 'etat': 'lu', 'badge': '', 'lu_classe': '', 'lu': '634 plans'} +
               CASE % {'classe': ' prevue', 'id': 'VRK', 'ng': 'VRK-AA', 'plus': ' data-prevu="1" data-code="colonne-elec"', 'etat': 'erreur',
                       'badge': '<span class="prevu-badge">prévu</span>', 'lu_classe': ' erreur', 'lu': '✗ ' + ELEC} +
               '<li class="case gates nouvelle" data-case="n3" data-contrat=""><div class="tete"><span class="etiquette">Nouveau contrat</span></div></li></ul>'
               '<div id="case-see"><div class="case see" data-case="see" data-etat="vide"><div class="tete"><span class="etiquette">SEE</span></div>'
               '<input type="file" class="fichier" hidden></div></div><div class="etat" id="etat"></div>'
               '<div id="pont-robot" hidden data-etat=""><textarea id="pont-robot-rapport"></textarea><button type="button" id="pont-robot-envoyer">envoyer</button></div>'
               '<script>window.google = { script: { run: { importRapport: function (r) { window.__recu = r; } } } };'
               'document.getElementById("pont-robot-envoyer").addEventListener("click", function () { var p = document.getElementById("pont-robot"), r;'
               '  try { r = JSON.parse(document.getElementById("pont-robot-rapport").value); } catch (e) { p.setAttribute("data-etat", "erreur"); p.setAttribute("data-message", "rapport illisible"); return; }'
               '  p.setAttribute("data-etat", "envoi");'
               '  setTimeout(function () { if (window.__refuser) { p.setAttribute("data-etat", "erreur"); p.setAttribute("data-message", "Le classeur est occupé"); return; }'
               '    google.script.run.importRapport(r); p.setAttribute("data-etat", "ok"); }, 400); });</script>')

    def monde_isole(c):
        cadre = c.envoyer('Page.getFrameTree')['frameTree']['frame']['id']
        return c.envoyer('Page.createIsolatedWorld', frameId=cadre, worldName='robot')['executionContextId']

    options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
    with Chrome(port=9458, lancer=True, profil=tempfile.mkdtemp(prefix='robot-pont-'), sans_fenetre=True, delai=30, options=options) as c:
        c.ouvrir(page_de(FENETRE))
        ctx = monde_isole(c)
        lu = robot.dans_le_cadre(c, ctx, robot.TABLEAU_JS)
        verifier('lire_tableau (son JS, dans le monde isolé du robot) : les étiquettes, et chaque contrat avec son nom GATES et « prévu » — pas la case nouvelle',
                 lu == {'cases': ['GATES HDK', 'GATES VRK', 'SEE'],
                        'contrats': [{'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': '', 'prevu': False},
                                     {'contrat': 'VRK', 'case': 'GATES VRK', 'nom_gates': 'VRK-AA', 'prevu': True}]}, lu)
        verifier('… le robot ne voit pas google.script.run (monde isolé), la page si',
                 robot.dans_le_cadre(c, ctx, 'typeof google') == 'undefined' and c.evaluer('typeof google') == 'object')
        ou = lambda contrat, nom: robot.dans_le_cadre(c, ctx, '(function(i){return i ? i.closest(".case").getAttribute("data-case") : null;})(%s)'   # noqa: E731
                                                       % (robot.CASE_JS % (_json.dumps(contrat), _json.dumps(nom))).strip())
        verifier('le fichier d’un contrat va dans la case de son contrat (data-contrat), celui de SEE dans la case SEE',
                 ou('VRK', 'GATES VRK') == 'g:VRK' and ou('hdk', 'GATES HDK') == 'g:HDK' and ou('', 'SEE') == 'see' and ou('NEO', 'GATES NEO') is None)
        rapport = robot.rapport_du_robot({'heure': '14:00'}, '2026-11-03T14:01:00+01:00',
                                         [{'contrat': 'HDK', 'gates': {'tape': 'HDK'}}, {'contrat': 'VRK', 'gates': {'ok': False, 'code': 'colonne-elec', 'message': ELEC}}], [], 1)
        verifier('envoyer_rapport : écrit dans le pont, clique « envoyer », attend « ok » — le serveur reçoit le compte rendu tel quel',
                 robot.envoyer_rapport(c, ctx, rapport, delai=15) is True and c.evaluer('window.__recu') == rapport, c.evaluer('window.__recu'))
        c.evaluer('window.__refuser = true; window.__recu = null')
        verifier('… refusé par le serveur : False (le message va au journal)',
                 robot.envoyer_rapport(c, ctx, rapport, delai=15) is False and c.evaluer('window.__recu') is None and 'Le classeur est occupé' in journal()[-300:])
        erreurs = robot.dans_le_cadre(c, ctx, robot.ERREURS_JS)
        verifier('la case en erreur (VRK, colonne ELEC absente) : son code et son message lus, puis son fichier retiré',
                 erreurs == [{'see': False, 'contrat': 'VRK', 'etiquette': 'GATES VRK', 'code': 'colonne-elec', 'message': ELEC, 'porteurs': []}] and
                 c.evaluer('document.querySelector(\'[data-case="g:VRK"] .retirer\').dataset.clic') == '1' and
                 robot.dans_le_cadre(c, ctx, robot.LECTURES_FINIES_JS) is True, erreurs)
        c.ouvrir(page_de('<div class="case gates" data-case="g:HDK"><span class="etiquette">GATES HDK</span><input type="file" class="fichier"></div><div id="etat"></div>'))
        ctx = monde_isole(c)
        verifier('une fenêtre d’avant (sans pont) : False, sans erreur', robot.envoyer_rapport(c, ctx, rapport, delai=5) is False)
        verifier('… et sans data-contrat, la case se trouve par son étiquette, comme avant', ou('HDK', 'GATES HDK') == 'g:HDK')

print('\n— Débrief 30 : la vraie fenêtre d’import (vrai Code.gs) menée par le robot : un prévu créé, une fiche à corriger, le compte rendu —')
NODE = shutil.which('node')
SERVEUR = pathlib.Path(__file__).resolve().parent.parent / 'tests' / 'fenetre-pour-robot.js'
if not (exe and NODE and SERVEUR.exists()):
    print('  (pas de Chrome ou pas de Node sur ce poste : partie sautée)')
else:
    import json as _json
    import subprocess as _sp
    serveur = _sp.Popen([NODE, str(SERVEUR)], stdout=_sp.PIPE, text=True, cwd=str(SERVEUR.parent.parent))
    try:
        pret = serveur.stdout.readline().split(' ', 2)
        port, fichiers = int(pret[1]), _json.loads(pret[2])
        etat_du_serveur = lambda: _json.loads(robot.SANS_PROXY.open('http://127.0.0.1:%d/etat' % port, timeout=10).read().decode())   # noqa: E731
        robot.PORT = 9459
        options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
        with Chrome(port=robot.PORT, lancer=True, profil=tempfile.mkdtemp(prefix='robot-fenetre-'), sans_fenetre=True, delai=30, options=options) as c:
            cfg = {'tableau': 'http://127.0.0.1:%d/exec' % port, 'heure': '14:00'}
            tableau = robot.lire_tableau(c, cfg)
            contrats = robot.contrats_lus(tableau)
            verifier('le tableau lu dans la vraie fenêtre (cadre d’un autre site) : HDK, puis les prévus VRK et NEO avec leur nom GATES ; la case SEE',
                     tableau['cases'] == ['GATES HDK', 'GATES VRK', 'GATES NEO', 'SEE'] and
                     contrats == [{'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': '', 'prevu': False},
                                  {'contrat': 'VRK', 'case': 'GATES VRK', 'nom_gates': 'VRK', 'prevu': True},
                                  {'contrat': 'NEO', 'case': 'GATES NEO', 'nom_gates': 'NEO', 'prevu': True}], tableau)
            sortis = [({'nom': 'GATES ' + k['contrat'], 'case': k['case'], 'contrat': k['contrat'], 'nom_gates': k['nom_gates'] or k['contrat'], 'prevu': k['prevu']},
                       pathlib.Path(fichiers[k['contrat']])) for k in contrats] + [({'nom': 'SEE', 'case': 'SEE'}, pathlib.Path(fichiers['SEE']))]
            comptes = [{'contrat': k['contrat'], 'gates': {'tape': k['nom_gates'] or k['contrat']}} for k in contrats]
            res = robot.deposer(c, cfg, sortis, comptes, '2026-11-03T14:01:00+01:00', [])
            e = etat_du_serveur()
            rap = e['rapports']
            verifier('déposé, importé : l’onglet du prévu VRK créé tout seul (avec « SEE VRK », son PSN de la fiche), HDK remplacé',
                     'VRK' in e['onglets'] and 'SEE VRK' in e['onglets'] and e['prevus'] == ['NEO'] and 'importRapport' in e['appels'], e)
            verifier('NEO (sa colonne ELEC n’est pas dans son export) : retiré avant l’import, erreur de fiche — rien de technique, compte rendu arrivé',
                     res['techniques'] == [] and res['rapport'] is True and len(res['fiche']) == 1 and res['fiche'][0].startswith('GATES NEO : La colonne de la validation ELEC')
                     and 'NEO' not in e['onglets'], res)
            verifier('le tableau de bord sait tout : VRK et HDK importés (la fenêtre), ce que le robot a tapé, l’erreur de NEO et ses colonnes proches',
                     rap['contrats']['VRK']['gates']['ok'] is True and rap['contrats']['VRK']['gates']['plans'] == 25 and rap['contrats']['VRK']['gates']['tape'] == 'VRK' and
                     rap['contrats']['HDK']['gates']['ok'] is True and rap['contrats']['VRK']['see']['ok'] is True and rap['contrats']['VRK']['see']['lignes'] == 15 and
                     rap['contrats']['NEO']['gates']['ok'] is False and rap['contrats']['NEO']['gates']['code'] == 'colonne-elec' and
                     'Les plus proches : « NEO AA 011 › Avancement Définition Electrique »' in rap['contrats']['NEO']['gates']['message'], rap)
            verifier('… et le passage du robot : réussi, une erreur de fiche, à partir de 14 h 00',
                     rap['robot'] and rap['robot']['ok'] is True and rap['robot']['erreursFiche'] == 1 and rap['robot']['heure'] == '14:00', rap['robot'])
            r2 = robot.rendre_compte(c, cfg, [{'contrat': 'HDK', 'gates': {'ok': False, 'code': 'gates-introuvable', 'tape': 'HDKX',
                                                                         'message': 'GATES ne montre pas « HDKX » : vérifiez le « Nom exact de la tranche dans GATES » de ce contrat.'}}],
                                     '2026-11-03T14:30:00+01:00', [robot.rate('SEE : SEE ne répond pas')])
            rap = etat_du_serveur()['rapports']
            verifier('rien n’est sorti : la fenêtre ouverte juste pour le compte rendu — le passage raté et sa raison, l’erreur de HDK, le succès de la veille gardé',
                     r2['rapport'] is True and rap['robot']['ok'] is False and rap['robot']['message'] == 'SEE : SEE ne répond pas' and
                     rap['contrats']['HDK']['gates']['ok'] is False and rap['contrats']['HDK']['gates']['code'] == 'gates-introuvable' and
                     bool(rap['contrats']['HDK']['gates'].get('dernierOk')), rap)
    finally:
        serveur.terminate()
        serveur.wait(10)

print('\n— Débrief 30 : un passage entier chez Nathan — sa configuration d’avant, rangée toute seule ; la vraie fenêtre ; rien à réapprendre —')
if exe and NODE and SERVEUR.exists():
    import json as _json
    import subprocess as _sp
    serveur = _sp.Popen([NODE, str(SERVEUR)], stdout=_sp.PIPE, text=True, cwd=str(SERVEUR.parent.parent))
    try:
        pret = serveur.stdout.readline().split(' ', 2)
        port, fichiers = int(pret[1]), _json.loads(pret[2])
        etat_du_serveur = lambda: _json.loads(robot.SANS_PROXY.open('http://127.0.0.1:%d/etat' % port, timeout=10).read().decode())   # noqa: E731
        # Ses exports appris, tels qu'ils sont sur son PC : GATES HDK (un seul contrat), SEE HDK et SEE (la même case).
        scenario('gates-hdk.json', 'GATES HDK', '2026-10-01T09:00:00', GESTES_HDK)
        scenario('see-hdk.json', 'SEE HDK', '2026-10-05T09:00:00', [{'faire': 'cliquer', 'cible': {'texte': 'Submit'}}])
        scenario('see.json', 'SEE', '2026-10-20T09:00:00', [{'faire': 'cliquer', 'cible': {'texte': 'Submit'}}])
        if COPIE.exists():
            COPIE.unlink()
        robot.garder(dict(_json.loads(_json.dumps(NATHAN)), tableau='http://127.0.0.1:%d/exec' % port, heure='00:00'))
        # Les sites de GATES et de SEE ne sont pas là : chaque export rend le fichier du jour de son contrat.
        joues = []

        def rejouer_nathan(c, s, dossier):
            joues.append((s['nom'], [g.get('texte') for g in s['etapes'] if g.get('faire') == 'remplir']))
            source = pathlib.Path(fichiers['SEE' if s['nom'].startswith('SEE') else s['nom'][6:]])
            dest = pathlib.Path(dossier) / (robot.nom_de_fichier(s['nom']) + source.suffix)
            shutil.copy2(source, dest)
            return dest
        robot.rejouer = rejouer_nathan
        os.environ['SUIVI_FWD_OPTIONS_CHROME'] = _json.dumps(['--headless=new'] + (['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []))
        robot.PORT = 9460
        remettre()
        avant_j = journal()
        code = PASSAGE(False)
        nouveau_j = journal()[len(avant_j):]
        e = etat_du_serveur()
        rap = e['rapports']
        cfg = robot.config()
        verifier('le passage réussit (une seule erreur, de fiche : NEO) — « ok » pour aujourd’hui',
                 code == (0, '') and (R / 'dernier-passage.txt').read_text(encoding='utf-8').startswith(AUJ + ' ok') and
                 '✓ Passage réussi — 1 erreur(s) de fiche, visibles dans le tableau de bord : GATES NEO' in nouveau_j, (code, nouveau_j[-1500:]))
        verifier('ses exports rangés tout seuls : GATES (tous les contrats, appris sur « HDK »), SEE (SEE HDK en secours)',
                 cfg['exports'] == [{'nom': 'GATES', 'scenario': 'gates-hdk.json', 'modele': True},
                                    {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE', 'secours': ['see-hdk.json']}] and COPIE.exists(), cfg['exports'])
        verifier('chaque contrat du tableau exporté avec son nom (HDK comme avant, les prévus VRK et NEO), puis SEE une seule fois',
                 joues == [('GATES HDK', ['HDK']), ('GATES VRK', ['VRK']), ('GATES NEO', ['NEO']), ('SEE', [])], joues)
        verifier('le prévu VRK a son onglet et sa base SEE ; NEO reste prévu, son erreur dite au tableau de bord ; le passage aussi',
                 'VRK' in e['onglets'] and 'SEE VRK' in e['onglets'] and e['prevus'] == ['NEO'] and rap['contrats']['NEO']['gates']['code'] == 'colonne-elec' and
                 rap['contrats']['HDK']['gates']['ok'] is True and rap['contrats']['VRK']['gates']['ok'] is True and
                 rap['robot']['ok'] is True and rap['robot']['erreursFiche'] == 1, rap)
    finally:
        robot.rejouer = vrai_rejouer
        os.environ.pop('SUIVI_FWD_OPTIONS_CHROME', None)
        serveur.terminate()
        serveur.wait(10)

print('\n═══════════════════════════════════════')
print('%d vérification(s) réussie(s), %d échec(s)' % (len(faits), len(echecs)))
for e in echecs:
    print('  · ' + e)
sys.exit(1 if echecs else 0)
