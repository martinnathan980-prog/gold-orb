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
  par le robot, jusqu'au passage entier avec la configuration de Nathan ;
— débrief 31 : la fenêtre du robot garde le focus quand on clique ailleurs
  (un vrai Chrome à l'écran, sous Xvfb : sans la parade l'export rate, avec
  il sort) ; ce que le robot a lu du tableau de bord, dit (adresse,
  livraison, ce qu'il tapera pour chaque contrat), une ANCIENNE version
  dite en clair ; l'adresse /dev (qui ne change jamais), changée et vérifiée ;
  GATES appris en lisant les fiches, jamais « THS AA AA » ; « oublier » ;
  les attentes longues dites ; l'installateur et ses raccourcis.
— débrief 32 : le menu GATES (un dessin sans nom) qui ne s'ouvre pas au
  2e contrat — une page comme GATES servie en local (adresses en « #/… »,
  « Données MK2 » caché tant que le menu est fermé), HDK puis VRK dans le
  même onglet : menu branché tard, départ en « #… », menu au survol, clic
  perdu ; le robot rouvre le menu, recharge la page, le dit ; jamais deux
  « Submit », jamais deux téléchargements, jamais de clic à l'aveugle ;
  relecture : une liste qui défile, les menus cachés autrement (display:none,
  replié, hors de l'écran, dans un cadre), une requête en fond, jamais deux
  fois une case, « Page suivante », « Afficher », « Se connecter », le
  fichier, un clic qui change de page en retard ; « Quitter la page ? ».

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
    print(('  ✓ ' if condition else '  ✗ ') + nom + ('' if condition else ' — %s' % (detail,)))


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

# Débrief 30 (relu) : le plus récent des anciens exports ne se change pas en
# modèle ; un plus ancien, si — c'est lui qui devient l'export de tous.
scenario('gates-x2.json', 'GATES X', '2026-10-10T09:00:00', [{'faire': 'remplir', 'cible': {}, 'texte': 'Projet 7'}, {'faire': 'cliquer', 'cible': {'texte': 'XLSX'}}])
scenario('gates-hdk.json', 'GATES HDK', '2026-10-01T09:00:00', GESTES_HDK)
robot.garder({'tableau': 'x', 'exports': [{'nom': 'GATES X', 'scenario': 'gates-x2.json', 'case': 'GATES X'},
                                          {'nom': 'GATES HDK', 'scenario': 'gates-hdk.json', 'case': 'GATES HDK'}]})
cfg = robot.config()
robot.ranger_exports(cfg)
verifier('deux anciens GATES : le plus récent (« GATES X ») n’a pas le nom de son contrat dans ses gestes — le suivant (« GATES HDK ») devient le modèle de tous',
         cfg['exports'] == [{'nom': 'GATES', 'scenario': 'gates-hdk.json', 'modele': True}] and
         json.loads((EXP / 'gates-hdk.json').read_text(encoding='utf-8')).get('modele', {}).get('appris') == 'HDK', cfg['exports'])
scenario('gates-hdk.json', 'GATES HDK', '2026-10-01T09:00:00', GESTES_HDK)     # tel qu'avant la migration

print('\n— Débrief 30 (relu) : sans export GATES de tous les contrats, le site le sait —')
ANCIEN = [{'nom': 'GATES X', 'scenario': 'gates-x.json', 'case': 'GATES X'}, {'nom': 'GATES HDK', 'scenario': 'gates-hdk.json', 'case': 'GATES HDK'},
          {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]
DU_SITE = [{'contrat': 'X', 'case': 'GATES X', 'nom_gates': 'X T1', 'prevu': False}, {'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': '', 'prevu': False},
           {'contrat': 'VRK', 'case': 'GATES VRK', 'nom_gates': 'VRK-AA', 'prevu': True}]
manque = robot.sans_export(ANCIEN, DU_SITE)
verifier('un ancien « GATES X » qui ne tape pas « X T1 » (sa fiche), et VRK prévu sans export : dits ; HDK, que son ancien export fait, non',
         manque == [('X', 'Le robot refait l’export appris pour X seul, sans le nom GATES de sa fiche (« X T1 »). ' + robot.REAPPRENDRE),
                    ('VRK', robot.REAPPRENDRE)] and
         robot.REAPPRENDRE == 'Le robot n’a pas encore d’export GATES pour tous les contrats : sur le PC du robot, refaites « Apprendre » une fois pour GATES (sur n’importe quel contrat).', manque)
verifier('avec l’export GATES de tous les contrats : rien à dire', robot.sans_export([{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}], DU_SITE) == [])
vrai_rejouer_r, vraie_photo_r = robot.rejouer, robot.photo
robot.photo = lambda c: ''
robot.rejouer = lambda c, s, dossier: (lambda f: (f.write_text('x', encoding='utf-8'), f)[1])(pathlib.Path(tempfile.mkdtemp()) / (robot.nom_de_fichier(s['nom']) + '.xlsx'))
robot.garder({'tableau': 'x', 'exports': []})
sortis, rates, comptes = robot.faire_les_exports(None, robot.config(), ANCIEN, pathlib.Path(tempfile.mkdtemp()), DU_SITE)
verifier('les exports d’avant sortent toujours ; X et VRK ont leur erreur dans le compte rendu (« gates-export ») ; un seul raté, « reapprendre »',
         [e['nom'] for e, _ in sortis] == ['GATES X', 'GATES HDK', 'SEE'] and
         [k['contrat'] for k in comptes] == ['X', 'VRK'] and all(k['gates']['ok'] is False and k['gates']['code'] == 'gates-export' for k in comptes) and
         rates == [robot.REAPPRENDRE] and rates[0].code == 'reapprendre', (sortis, rates, comptes))
r_rea = robot.rapport_du_robot({}, '', comptes, [str(x) for x in rates], 0)
verifier('… le passage dit au site, en rouge, ce qu’il faut faire sur le PC', r_rea['passage']['ok'] is False and r_rea['passage']['message'] == robot.REAPPRENDRE, r_rea['passage'])
robot.rejouer, robot.photo = vrai_rejouer_r, vraie_photo_r

print('\n— Débrief 30 : un export par contrat, le nom GATES de la fiche —')
liste = [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}, {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]
travaux = robot.a_faire({'noms_gates': {'HDK': 'HDKX'}}, liste,
                        [{'contrat': 'HDK', 'nom_gates': '', 'case': 'GATES HDK', 'prevu': False},
                         {'contrat': 'VRK', 'nom_gates': 'VRK-AA', 'case': 'GATES VRK', 'prevu': True}])
# Débrief 31 : chaque export dit aussi d'où vient le nom tapé (« source » : fiche, retenu, deviné…),
# pour que le compte rendu dise quoi corriger quand GATES ne montre pas ce nom.
verifier('HDK tape « HDKX » (retenu par le robot), VRK tape « VRK-AA » (sa fiche), dans la case « GATES VRK », prévu',
         travaux[0][1]['etapes'][1]['texte'] == 'HDKX' and travaux[1][1]['etapes'][1]['texte'] == 'VRK-AA' and travaux[0][0]['source'] == 'retenu' and
         travaux[1][0] == {'nom': 'GATES VRK', 'case': 'GATES VRK', 'contrat': 'VRK', 'nom_gates': 'VRK-AA', 'prevu': True, 'source': 'fiche'}, [e for e, _ in travaux])
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
rea = robot.rate(robot.REAPPRENDRE, 'reapprendre')
simuler([GHDK], [rea], [{'contrat': 'VRK', 'gates': {'ok': False, 'code': 'gates-export', 'message': robot.REAPPRENDRE}}], {'rapport': True})
verifier('« refaites Apprendre » (relu) : envoyé au site avec le compte rendu (le passage en rouge), mais ni nouvel essai ni fenêtre — rien ne changera d’ici demain',
         PASSAGE(True) == (0, '') and outils['deposer'][2] == [rea], outils.get('deposer'))
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

# ---------------------------------------------------------------- Débrief 31
import contextlib  # noqa: E402
import io  # noqa: E402


def sortie_de(f, *a, **k):
    """Ce que f écrit dans la fenêtre noire, et ce qu'elle rend."""
    tampon = io.StringIO()
    with contextlib.redirect_stdout(tampon):
        r = f(*a, **k)
    return tampon.getvalue(), r


print('\n— Débrief 31 : ce que le robot tape dans GATES — la fiche d’abord, jamais deux fois —')
MODELE = {'appris': 'HDK AA', 'contrat': 'HDK'}
verifier('la fiche l’emporte toujours (sur ce que le robot avait retenu, et sur le modèle)',
         robot.nom_du_jour({'noms_gates': {'THS': 'THSX'}}, {'contrat': 'THS', 'nom_gates': 'THS AA'}, MODELE) == ('THS AA', 'fiche'))
verifier('… sans fiche : ce que le robot avait retenu', robot.nom_du_jour({'noms_gates': {'ths': 'THSX'}}, 'THS', MODELE) == ('THSX', 'retenu'))
verifier('… ni fiche ni mémoire : deviné sur le modèle (« HDK AA » appris sur HDK → « THS AA »)',
         robot.nom_du_jour({}, 'THS', MODELE) == ('THS AA', 'devine'))
verifier('… le contrat appris lui-même : ce qui a été tapé', robot.nom_du_jour({}, 'HDK', MODELE) == ('HDK AA', 'appris'))
verifier('… une tranche (« HDK Tranche 2 ») ne se devine pas : le nom du contrat, comme avant',
         robot.nom_du_jour({}, 'HDK Tranche 2', MODELE) == ('HDK Tranche 2', 'contrat') and robot.est_tranche('HDK - tranche 3') and not robot.est_tranche('THS'))
verifier('… un modèle appris sur le nom seul (« HDK ») ne devine rien : le nom du contrat',
         robot.nom_du_jour({}, 'THS', {'appris': 'HDK', 'contrat': 'HDK'}) == ('THS', 'contrat'))
verifier('… un modèle d’avant (sans « contrat ») : son contrat retrouvé dans ce que le robot avait retenu',
         robot.contrat_appris({'noms_gates': {'HDK': 'HDK AA'}}, {'appris': 'HDK AA'}) == 'HDK' and
         robot.nom_du_jour({'noms_gates': {'HDK': 'HDK AA'}}, 'NEO', {'appris': 'HDK AA'}) == ('NEO AA', 'devine'))
G31 = [{'faire': 'remplir', 'cible': {'balise': 'input', 'placeholder': 'Contrat'}, 'texte': 'HDK AA'},
       {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'HDK AA — 634 plans'}},
       {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'XLSX'}}]
s31 = robot.pour_le_contrat({'nom': 'GATES', 'etapes': G31}, 'HDK AA', 'THS', 'THS AA', 'HDK AA')['etapes']
verifier('appris « HDK AA », pour THS (« THS AA ») : tape « THS AA », clique « THS AA — 634 plans » — jamais « THS AA AA »',
         s31[0]['texte'] == 'THS AA' and s31[1]['cible']['texte'] == 'THS AA — 634 plans' and s31[1]['cible']['contient'] == 'THS AA', s31)
G31b = [dict(G31[0], texte='HDK'), G31[1], G31[2]]
s31 = robot.pour_le_contrat({'nom': 'GATES', 'etapes': G31b}, 'HDK', 'THS', 'THS AA', 'HDK AA')['etapes']
verifier('appris en tapant « HDK » puis en cliquant « HDK AA — 634 plans » : pour THS, « THS AA » et « THS AA — 634 plans »',
         s31[0]['texte'] == 'THS AA' and s31[1]['cible']['texte'] == 'THS AA — 634 plans' and s31[1]['cible']['contient'] == 'THS AA', s31)
s31 = robot.pour_le_contrat({'nom': 'GATES', 'etapes': G31b}, 'HDK', 'THS', 'THS AA', '')['etapes']
verifier('… même sans connaître le nom GATES de HDK (« HDK » suivi de ce que « THS AA » ajoute à THS)',
         s31[0]['texte'] == 'THS AA' and s31[1]['cible']['texte'] == 'THS AA — 634 plans', s31)
s31 = robot.pour_le_contrat({'nom': 'GATES', 'etapes': G31b}, 'HDK', 'HDK', 'HDK AA', 'HDK AA')['etapes']
verifier('… et pour HDK lui-même (sa fiche : « HDK AA ») : « HDK AA », « HDK AA — 634 plans » — pas « HDK AA AA »',
         s31[0]['texte'] == 'HDK AA' and s31[1]['cible']['texte'] == 'HDK AA — 634 plans' and s31[1]['cible']['contient'] == 'HDK AA', s31)
s31 = robot.pour_le_contrat({'nom': 'GATES', 'etapes': [dict(G31[0], texte='HDK'), {'faire': 'cliquer', 'cible': {'texte': 'HDKA — 600 plans'}}]},
                            'HDK', 'THS', 'THSA')['etapes']
verifier('« HDKA » (le nom GATES collé au contrat) : la ligne cliquée doit porter « THSA » — jamais celle de HDK pour THS',
         s31[1]['cible']['texte'] == 'THSA — 600 plans' and s31[1]['cible']['contient'] == 'THSA', s31)
(R / 'exports' / 'gates31.json').write_text(json.dumps({'nom': 'GATES', 'depart': 'x', 'etapes': G31b, 'modele': {'appris': 'HDK', 'contrat': 'HDK'}}), encoding='utf-8')
FICHES = [{'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': 'HDK AA', 'prevu': False},
          {'contrat': 'THS', 'case': 'GATES THS', 'nom_gates': 'THS AA', 'prevu': False},
          {'contrat': 'NEO', 'case': 'GATES NEO', 'nom_gates': 'NEO AA', 'prevu': True}]
travaux = robot.a_faire({}, [{'nom': 'GATES', 'scenario': 'gates31.json', 'modele': True}], FICHES)
verifier('chaque jour : HDK, THS et le prévu NEO tapent le nom de leur fiche, et cliquent la ligne qui le porte',
         [(e['contrat'], s['etapes'][0]['texte'], s['etapes'][1]['cible']['texte'], e['source']) for e, s in travaux] ==
         [('HDK', 'HDK AA', 'HDK AA — 634 plans', 'fiche'), ('THS', 'THS AA', 'THS AA — 634 plans', 'fiche'), ('NEO', 'NEO AA', 'NEO AA — 634 plans', 'fiche')],
         [(e['contrat'], s['etapes'][0]['texte'], s['etapes'][1]['cible']['texte']) for e, s in travaux])
verifier('une ligne par contrat : « THS → tape « THS AA » », « NEO … (prévu, nouvel onglet) », un nom deviné le dit',
         robot.lignes_des_contrats({}, FICHES + ['VRK', 'HDK Tranche 2'], {'modele': MODELE}) ==
         ['  HDK → tape « HDK AA »', '  THS → tape « THS AA »', '  NEO → tape « NEO AA » (prévu, nouvel onglet)',
          '  VRK → tape « VRK AA » (deviné : à écrire dans sa fiche pour être sûr)',
          '  HDK Tranche 2 → tape « HDK Tranche 2 » (la fiche n\'a pas de nom GATES : le nom du contrat)'],
         robot.lignes_des_contrats({}, FICHES + ['VRK', 'HDK Tranche 2'], {'modele': MODELE}))
robot.photo = lambda c: ''
robot.rejouer = rejouer_simule({'GATES VRK': panne('Je ne retrouve plus « VRK AA — 634 plans »', {'faire': 'cliquer', 'cible': {'contient': 'VRK AA'}})})
(R / 'exports' / 'gates31m.json').write_text(json.dumps({'nom': 'GATES', 'depart': 'x', 'etapes': G31, 'modele': MODELE}), encoding='utf-8')
_, rates31, comptes31 = robot.faire_les_exports(None, {}, [{'nom': 'GATES', 'scenario': 'gates31m.json', 'modele': True}], SORTIE, ['VRK'])
verifier('un nom deviné que GATES ne montre pas : le tableau de bord dit d’écrire le nom GATES dans la fiche',
         comptes31[0]['gates']['code'] == 'gates-introuvable' and comptes31[0]['gates']['tape'] == 'VRK AA' and
         'la fiche n’a pas de nom GATES : le robot l’a deviné' in comptes31[0]['gates']['message'], comptes31)
robot.rejouer, robot.photo = vrai_rejouer, vraie_photo

print('\n— Débrief 31 : apprendre GATES en lisant les fiches du tableau de bord —')


class ChromeApprendre:
    """La fenêtre du robot pendant « apprendre » : les gestes de la personne, puis le fichier arrivé."""
    def __init__(self, gestes):
        self.gestes, self.donnes, self.envoyes = list(gestes), False, []

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def envoyer(self, methode, **p):
        self.envoyes.append(methode)
        return {}

    def evaluer(self, js):
        return None

    def ouvrir(self, url):
        return url

    def fichiers_presents(self):
        return {'export-gates.xlsx'} if self.donnes else set()


def lire_evenements_appris(c, duree):
    if c.donnes:
        import time as _t
        _t.sleep(0.05)
        return []
    c.donnes = True
    return [{'method': 'Runtime.bindingCalled', 'params': {'name': '__suiviFwd', 'payload': json.dumps(g)}} for g in c.gestes]


def apprendre_avec(gestes, tableau, reponses_donnees):
    import time as _t
    vrais31 = {n: getattr(robot, n) for n in ('chrome', 'lire_evenements', 'lire_tableau')}
    vieil_input = builtins.input
    c31 = ChromeApprendre(gestes)
    robot.chrome = lambda *a, **k: c31
    robot.lire_evenements = lire_evenements_appris
    robot.lire_tableau = lambda c, cfg: tableau
    file_ = list(reponses_donnees)
    builtins.input = lambda invite='': (lambda r: (_t.sleep(r) or '') if isinstance(r, float) else r)(file_.pop(0))
    try:
        return sortie_de(robot.apprendre)[0], c31
    finally:
        builtins.input = vieil_input
        for n, v in vrais31.items():
            setattr(robot, n, v)


TABLEAU31 = {'cases': ['GATES HDK', 'GATES THS', 'GATES VRK', 'GATES NEO', 'SEE'], 'adresse': 'https://script.google.com/a/macros/airbus.com/s/AKfy/exec?page=import',
             'livraison': 'cd9cd8e', 'ancienne': False, 'erreur': '',
             'contrats': [{'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': 'HDK AA', 'prevu': False},
                          {'contrat': 'THS', 'case': 'GATES THS', 'nom_gates': 'THS AA', 'prevu': False},
                          {'contrat': 'VRK', 'case': 'GATES VRK', 'nom_gates': '', 'prevu': False},
                          {'contrat': 'NEO', 'case': 'GATES NEO', 'nom_gates': 'NEO AA', 'prevu': True}]}
GESTES31 = [{'faire': 'cliquer', 'cible': {'balise': 'a', 'texte': 'GATES'}},
            {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Ouvrir données MK2'}},
            {'faire': 'remplir', 'cible': {'balise': 'input', 'placeholder': 'Contrat'}, 'texte': 'HDK AA'},
            {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'HDK AA — 634 plans'}},
            {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'XLSX'}}]
robot.garder({'tableau': 'https://script.google.com/a/macros/airbus.com/s/AKfy/exec', 'heure': '14:00', 'exports': []})
avant_j = journal()
dit, c31 = apprendre_avec(GESTES31, TABLEAU31, ['1', 1.0, 'n'])
appris_j = journal()[len(avant_j):]
cfg31 = robot.config()
s31 = json.loads((R / 'exports' / 'gates.json').read_text(encoding='utf-8'))
verifier('« HDK AA » tapé = le nom GATES de la fiche de HDK : reconnu sans question ; le modèle retient le mot ET le contrat',
         s31['modele'] == {'appris': 'HDK AA', 'contrat': 'HDK'} and cfg31['exports'] == [{'nom': 'GATES', 'modele': True, 'scenario': 'gates.json'}] and
         'Lequel de ces mots' not in dit, (s31.get('modele'), cfg31['exports'], dit[-600:]))
verifier('… ce qui a été lu (adresse, livraison) puis exactement ce qui sera tapé, contrat par contrat — dans la fenêtre noire et au journal',
         'Tableau de bord lu : https://script.google.com/a/macros/airbus.com/s/AKfy/exec?page=import — Livraison cd9cd8e' in appris_j and
         '  HDK → tape « HDK AA »\n' in dit and '  THS → tape « THS AA »\n' in dit and
         '  VRK → tape « VRK AA » (deviné : à écrire dans sa fiche pour être sûr)' in appris_j and
         '  NEO → tape « NEO AA » (prévu, nouvel onglet)' in appris_j, appris_j)
verifier('… la page du robot garde le focus pendant qu’on apprend (Chrome seul : pas de script dans la page)',
         'Emulation.setFocusEmulationEnabled' in c31.envoyes, c31.envoyes)
travaux = robot.a_faire(cfg31, cfg31['exports'], robot.contrats_lus(TABLEAU31))
verifier('… et le lendemain : THS tape « THS AA » et clique « THS AA — 634 plans » ; VRK (deviné) « VRK AA »',
         [(e['contrat'], s['etapes'][2]['texte'], s['etapes'][3]['cible']['texte']) for e, s in travaux] ==
         [('HDK', 'HDK AA', 'HDK AA — 634 plans'), ('THS', 'THS AA', 'THS AA — 634 plans'), ('VRK', 'VRK AA', 'VRK AA — 634 plans'),
          ('NEO', 'NEO AA', 'NEO AA — 634 plans')], [(e['contrat'], s['etapes'][2]['texte'], s['etapes'][3]['cible']['texte']) for e, s in travaux])
robot.garder({'tableau': 'x', 'exports': [{'nom': 'Gates', 'scenario': 'gates.json', 'case': 'GATES HDK'}, {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]})
verifier('un autre export dont le fichier s’appelle déjà « gates.json » : le nouveau n’écrase pas le sien (« gates-2.json »)',
         robot.fichier_libre('GATES', robot.config()['exports']) == 'gates-2.json' and robot.fichier_libre('SEE', robot.config()['exports']) == 'see.json')
reperes = robot.reperer_contrat([{'faire': 'cliquer', 'cible': {'texte': 'THS'}}, {'faire': 'remplir', 'texte': 'HDK AA'}], TABLEAU31['contrats'])
verifier('ce qu’on a TAPÉ passe avant ce qu’on a cliqué (un onglet « THS » cliqué en passant ne trompe pas)', reperes == ('HDK AA', 'HDK'), reperes)
robot.garder({'tableau': 'x', 'exports': []})
dit, _ = apprendre_avec([dict(g, texte='HDK') if g['faire'] == 'remplir' else g for g in GESTES31], TABLEAU31, ['1', 1.0, 'n'])
verifier('appris en tapant « HDK » alors que sa fiche dit « HDK AA » : dit en clair (c’est la fiche qui compte)',
         'Attention : la fiche de HDK dit « HDK AA ». Chaque jour, c\'est la fiche qui compte : le robot tapera « HDK AA ».' in dit and
         json.loads((R / 'exports' / 'gates.json').read_text(encoding='utf-8'))['modele'] == {'appris': 'HDK', 'contrat': 'HDK'}, dit[-900:])
robot.garder({'tableau': 'x', 'exports': [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}]})
avant_j = journal()
dit, _ = apprendre_avec([{'faire': 'remplir', 'cible': {'balise': 'input', 'etiquette': 'PSN'}, 'texte': '4530'},
                         {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Submit'}}], TABLEAU31, ['2', 1.0, 'n'])
verifier('apprendre SEE dit aussi ce qu’il a lu : l’adresse, la livraison, et ce que GATES tapera pour chaque contrat (au journal aussi)',
         'Tableau de bord lu : https://script.google.com/a/macros/airbus.com/s/AKfy/exec?page=import — Livraison cd9cd8e' in journal()[len(avant_j):] and
         '  THS → tape « THS AA »' in journal()[len(avant_j):] and robot.config()['exports'][-1]['case'] == 'SEE', dit[-900:])
robot.garder({'tableau': 'x', 'exports': []})
dit, _ = apprendre_avec(GESTES31, dict(TABLEAU31, cases=[], contrats=[], erreur='La fenêtre d\'import du tableau de bord ne s\'est pas ouverte'),
                        ['1', 1.0, '1', 'n'])
verifier('la fenêtre d’import illisible pendant « apprendre » : dit en clair (pas de repli muet), puis la question d’avant',
         '✗ Le robot n\'a pas pu lire la fenêtre d\'import du tableau de bord' in dit and 'ne s\'est pas ouverte' in dit and 'Lequel de ces mots' in dit and
         json.loads((R / 'exports' / 'gates.json').read_text(encoding='utf-8'))['modele'] == {'appris': 'HDK AA', 'contrat': ''}, dit[-900:])

print('\n— Débrief 31 : ce que le robot a lu, dit à chaque passage ; une ANCIENNE version du tableau de bord, dite en clair —')
ANCIENNE31 = {'cases': ['GATES HDK', 'GATES THS', 'SEE'], 'contrats': [{'contrat': '', 'case': 'GATES HDK'}, {'contrat': '', 'case': 'GATES THS'}],
              'adresse': 'https://script.google.com/a/macros/airbus.com/s/AKvieux/exec?page=import', 'livraison': '', 'ancienne': True, 'erreur': ''}
lignes31 = robot.entete_du_tableau({'tableau': 'x'}, ANCIENNE31)
# Débrief 31 (relu) : plus de « Gérer les déploiements → ✏️ → Nouvelle version » dans la fenêtre noire —
# Nathan fait un nouveau déploiement à chaque livraison (« les mises à jour de liens, ça déconne ») : un seul
# chemin, le lien /dev, une fois pour toutes (l'autre reste dans le README).
verifier('une ancienne version : l’adresse, « version inconnue », ce qu’il ne voit pas, et quoi faire (le lien /dev, « Changer l’adresse du tableau de bord » — un seul chemin)',
         lignes31[0] == 'Tableau de bord lu : https://script.google.com/a/macros/airbus.com/s/AKvieux/exec?page=import — version inconnue' and
         'ANCIENNE version du tableau de bord' in lignes31[1] and 'AKvieux/exec?page=import' in lignes31[1] and
         'Déployer → Tester les déploiements' in lignes31[1] and 'finit par /dev' in lignes31[1] and
         '« Changer l\'adresse du tableau de bord »' in lignes31[1] and
         'Gérer les déploiements' not in lignes31[1] and 'Nouvelle version' not in lignes31[1], lignes31)
dev31 = robot.entete_du_tableau({'tableau': 'https://script.google.com/a/macros/airbus.com/s/AKfy/dev'}, dict(ANCIENNE31, adresse=''))
verifier('… avec déjà le lien /dev : c’est le code du projet qui est ancien — recoller la dernière livraison et enregistrer',
         'AKfy/dev?page=import' in dev31[1] and 'collez la dernière livraison' in dev31[1] and 'Tester les déploiements' not in dev31[1], dev31)
verifier('… et sans data-contrat, les contrats tirés des étiquettes : chacun tape son nom (c’était « THS » au lieu de « THS AA »)',
         robot.lignes_des_contrats({}, robot.contrats_lus(ANCIENNE31), {'modele': {'appris': 'HDK', 'contrat': 'HDK'}}) ==
         ['  HDK → tape « HDK »', '  THS → tape « THS » (la fiche n\'a pas de nom GATES : le nom du contrat)'] and
         robot.lignes_des_contrats({}, robot.contrats_lus(ANCIENNE31), {'modele': {'appris': 'HDK', 'contrat': 'HDK'}}, True)[1] ==
         '  THS → tape « THS » (le nom du contrat : fiche non lue, ancienne version du tableau de bord)')
rate31 = robot.entete_du_tableau({'tableau': 'x'}, {'cases': [], 'contrats': [], 'adresse': 'x?page=import', 'erreur': 'connexion refusée'})
verifier('la fenêtre illisible : dit, avec l’adresse et la raison (jamais un repli muet sur les étiquettes)',
         rate31[0] == '✗ Le robot n\'a pas pu lire la fenêtre d\'import du tableau de bord (x?page=import) : connexion refusée.' and
         'ni les contrats du jour ni leur nom dans GATES' in rate31[1], rate31)
vrai_lire = robot.lire_tableau
robot.lire_tableau = lambda c, cfg: {'cases': [], 'contrats': [], 'adresse': 'x?page=import', 'erreur': 'connexion Google à refaire'}
try:
    robot.attendre_tableau(None, {'tableau': 'x'}, 0)
    dit = ''
except robot.ErreurPilote as err:
    dit = str(err)
robot.lire_tableau = vrai_lire
verifier('… et au passage, l’erreur dit l’adresse et la raison', 'Adresse : x?page=import — connexion Google à refaire.' in dit, dit)
remettre(); appels.clear()
for f31 in ('alerte-version.txt',):
    if (R / f31).exists():
        (R / f31).unlink()
robot.garder({'tableau': 'https://script.google.com/a/macros/airbus.com/s/AKvieux/exec', 'heure': '00:00', 'exports': []})
simuler([GHDK], [], [], {'rapport': False})
robot.attendre_tableau = lambda c, cfg, delai: ANCIENNE31
robot._passage = lambda auto: (appels.append(('passage', auto)), PASSAGE(auto))[1]
avant_j = journal()
robot.lancer(auto=True)
remettre()                                  # (comme si le passage du jour n'était pas fait : il repasse)
robot.lancer(auto=True)
dit_lancer31, code_lancer31 = sortie_de(robot.lancer, auto=False)
j31 = journal()[len(avant_j):]
prev31 = [a[1] for a in appels if a[0] == 'prevenu']
# Débrief 31 (relu) : la petite fenêtre ne propose plus « Nouvelle version » (voir plus haut) — le lien /dev seul.
verifier('en automatique : une petite fenêtre le dit à la fin des passages — une seule fois par jour (« Lancer maintenant » : la fenêtre noire suffit)',
         nb('passage') == 3 and len(prev31) == 1 and 'ANCIENNE version du tableau de bord' in prev31[0] and 'AKvieux/exec?page=import' in prev31[0] and
         'Tester les déploiements' in prev31[0] and '/dev' in prev31[0] and '« Changer l\'adresse du tableau de bord »' in prev31[0] and
         'Nouvelle version' not in prev31[0], (appels, prev31))
fin_lancer31 = dit_lancer31.rstrip().split('\n')
i_fin31 = max([i for i, l in enumerate(fin_lancer31) if l.startswith(('✓ Passage', '✗ Passage'))] or [-1])
verifier('« Lancer maintenant » (débrief 31, relu) : après la dernière ligne (✓ ou ✗), l’ANCIENNE version redite, avec quoi faire — pas seulement tout en haut',
         i_fin31 >= 0 and 'ANCIENNE version du tableau de bord' in '\n'.join(fin_lancer31[i_fin31 + 1:]) and
         '« Changer l\'adresse du tableau de bord »' in '\n'.join(fin_lancer31[i_fin31 + 1:]), dit_lancer31[-1500:])
verifier('… chaque passage écrit au journal ce qu’il a lu (l’adresse, la version, l’avertissement)',
         j31.count('Tableau de bord lu : https://script.google.com/a/macros/airbus.com/s/AKvieux/exec?page=import — version inconnue') == 3 and
         j31.count('ANCIENNE version du tableau de bord') >= 3, j31[-1500:])
(R / 'alerte-version.txt').write_text(HIER, encoding='utf-8')
remettre(); appels.clear()
robot.lancer(auto=True)
verifier('… le lendemain, elle le redit', sum(1 for a in appels if a[0] == 'prevenu') == 1, appels)
# Raté trois fois (le compte rendu n'arrive pas : une fenêtre d'avant n'a pas de pont) : la petite fenêtre
# vient à la fin, après le troisième passage — jamais entre deux, où elle retiendrait le nouvel essai.
(R / 'alerte-version.txt').write_text(HIER, encoding='utf-8')
remettre(); appels.clear()
simuler([GHDK], [], [], {'fiche': ['GATES VRK : colonne'], 'rapport': False})
robot.attendre_tableau = lambda c, cfg, delai: ANCIENNE31
robot.lancer(auto=True)
ordre31 = [a[0] for a in appels if a[0] in ('passage', 'prevenu')]
verifier('… raté trois fois : trois passages d’abord, puis la fenêtre « 3 essais », puis celle de l’ancienne version',
         ordre31 == ['passage', 'passage', 'passage', 'prevenu', 'prevenu'] and
         'ANCIENNE version' in [a[1] for a in appels if a[0] == 'prevenu'][1], appels)
robot._passage = PASSAGE
remettre()
lu31 = json.loads((R / 'dernier-tableau.json').read_text(encoding='utf-8'))
verifier('ce qui a été lu est gardé pour « Etat du robot » (dernier-tableau.json)',
         lu31['ancienne'] is True and lu31['adresse'].endswith('AKvieux/exec?page=import') and lu31['livraison'] == '', lu31)
for n, v in vrais.items():
    setattr(robot, n, v)

print('\n— Débrief 31 : tout oublier, pour tout recommencer (« 0 - Tout oublier (recommencer les exports) ») —')
for f31 in R.glob('exports/*.json'):
    f31.unlink()
scenario('gates.json', 'GATES', '2026-10-25T09:00:00', GESTES_HDK, modele={'appris': 'HDK AA', 'contrat': 'HDK'})
scenario('gates-ths.json', 'GATES THS', '2026-10-02T09:00:00', GESTES_HDK)
scenario('see.json', 'SEE', '2026-10-20T09:00:00', [{'faire': 'cliquer', 'cible': {'texte': 'Submit'}}])
scenario('see-hdk.json', 'SEE HDK', '2026-10-05T09:00:00', [{'faire': 'cliquer', 'cible': {'texte': 'Submit'}}])
(R / 'chrome' / 'Cookies').write_text('les connexions', encoding='utf-8')
CFG31 = {'tableau': 'https://script.google.com/a/macros/airbus.com/s/AKfy/exec', 'heure': '14:30', 'navigateur': 'edge',
         'noms_gates': {'HDK': 'HDK AA', 'THS': 'THSA'}, 'reussis': {'see': 'see-hdk.json'},
         'exports': [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}, {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE', 'secours': ['see-hdk.json']}]}
robot.garder(json.loads(json.dumps(CFG31)))
dit, _ = sortie_de(robot.montrer_etat)
verifier('« Etat du robot » : les exports appris, un par ligne, en clair (pour qui, appris quand, sur quoi, leurs secours)',
         'Exports appris  : 2' in dit and '  · GATES — pour tous les contrats du tableau de bord (appris le 25/10/2026 sur « HDK AA », contrat HDK)' in dit and
         '  · SEE — case « SEE » (appris le 20/10/2026) ; en secours : SEE HDK' in dit and '« 0 - Tout oublier (recommencer les exports) »' in dit and
         'Dernière lecture du tableau de bord' in dit, dit)
vieil_input = builtins.input
builtins.input = lambda invite='': 'n'
dit, _ = sortie_de(robot.oublier)
verifier('« oublier » demande d’abord, et dit ce qu’il garde ; « n » : rien ne change',
         'Tout oublier ? (o/n)' not in dit and 'Il garde : ses connexions (GATES, SEE, Google), l\'adresse du tableau de bord, le navigateur (Edge), son heure (14:30)' in dit and
         'Rien n\'est changé.' in dit and robot.config() == CFG31 and len(list(R.glob('exports/*.json'))) == 4, dit)
builtins.input = lambda invite='': 'o'
dit, code31 = sortie_de(robot.main, ['robot.py', 'oublier'])
builtins.input = vieil_input
cfg31 = robot.config()
piles = sorted((R / 'exports-oublies').iterdir())
verifier('« o » : la liste oubliée, les noms GATES retenus et les réussites aussi — gardés : l’adresse, le navigateur, l’heure',
         code31 == 0 and cfg31 == {'tableau': CFG31['tableau'], 'heure': '14:30', 'navigateur': 'edge', 'exports': []}, cfg31)
verifier('… rien n’est effacé : les exports appris et robot.json sont rangés dans un dossier daté (exports-oublies)',
         len(piles) == 1 and sorted(p.name for p in piles[0].iterdir()) == ['gates-ths.json', 'gates.json', 'robot.json', 'see-hdk.json', 'see.json'] and
         json.loads((piles[0] / 'robot.json').read_text(encoding='utf-8')) == CFG31 and not list(R.glob('exports/*.json')), [p.name for p in piles[0].iterdir()] if piles else piles)
verifier('… les connexions restent (le profil du navigateur n’est pas touché)', (R / 'chrome' / 'Cookies').read_text(encoding='utf-8') == 'les connexions')
(R / 'chrome' / 'Cookies').unlink()       # (un vrai navigateur reprend ce profil plus bas)
verifier('… et la suite est dite : 2 - Apprendre → 1 GATES sur un contrat, 2 - Apprendre → 2 SEE, 3 - Essayer',
         '« 2 - Apprendre un export », choisissez 1 (GATES)' in dit and '« 2 - Apprendre un export », choisissez 2 (SEE)' in dit and '« 3 - Essayer »' in dit and
         'Tout oublié : 4 export(s) appris mis de côté' in journal(), dit)
builtins.input = lambda invite='': 'o'
dit, _ = sortie_de(robot.oublier)
builtins.input = vieil_input
verifier('… redemandé : « rien à oublier », et la suite redite', 'rien à oublier' in dit and '« 3 - Essayer »' in dit and len(list((R / 'exports-oublies').iterdir())) == 1, dit)
dit, _ = sortie_de(robot.montrer_etat)
verifier('« Etat du robot » après : aucun export, et quoi faire', 'Exports appris  : aucun (double-cliquez « 2 - Apprendre un export »)' in dit, dit)
remettre(); appels.clear()
robot._passage = PASSAGE
code31 = robot._passage(False)
verifier('un passage sans rien d’appris : dit quoi faire', code31 == (1, 'le robot ne sait encore aucun export (double-cliquez « 2 - Apprendre un export »)'), code31)
with robot.verrou() as libre:
    builtins.input = lambda invite='': 'o'
    scenario('gates.json', 'GATES', '2026-10-25T09:00:00', GESTES_HDK, modele={'appris': 'HDK', 'contrat': 'HDK'})
    code31 = robot.main(['robot.py', 'oublier'])
    builtins.input = vieil_input
verifier('« oublier » pendant un passage du robot : refusé (le verrou), rien n’est rangé', code31 == 1 and (R / 'exports' / 'gates.json').exists())
(R / 'exports' / 'gates.json').unlink()

print('\n— Débrief 31 : l’adresse du tableau de bord — le lien /dev, qui ne change jamais ; la changer, la vérifier —')
DEV = 'https://script.google.com/a/macros/airbus.com/s/AKfyDEV/dev'
EXEC1 = 'https://script.google.com/a/macros/airbus.com/s/AKfyUN/exec'
verifier('la fenêtre d’import par le lien /dev comme par /exec : « ?page=import », ou « &page=import » après d’autres paramètres',
         robot.adresse_import({'tableau': DEV}) == DEV + '?page=import' and robot.adresse_import({'tableau': EXEC1}) == EXEC1 + '?page=import' and
         robot.adresse_import({'tableau': DEV + '?authuser=0'}) == DEV + '?authuser=0&page=import')
verifier('… une adresse collée depuis la fenêtre d’import (« ?page=import »), avec « # », une barre en trop, des guillemets : nettoyée, une seule fois « page=import »',
         robot.adresse_import({'tableau': DEV + '?page=import'}) == DEV + '?page=import' and
         robot.adresse_propre('  "' + DEV + '/?authuser=1&page=import#gid=3"  ') == DEV + '?authuser=1' and
         robot.adresse_propre('<' + EXEC1 + '/>') == EXEC1 and robot.adresse_propre('') == '')
verifier('… et reconnue : /dev (toujours la dernière version), /exec (un déploiement), ni l’un ni l’autre',
         [robot.sorte_d_adresse(a) for a in (DEV, DEV + '?page=import', EXEC1 + '/', 'https://exemple.fr/tableau', '')] == ['dev', 'dev', 'exec', '', ''])


class ChromeAdresse(ChromeApprendre):
    def __init__(self):
        ChromeApprendre.__init__(self, [])
        self.ouverts = []

    def ouvrir(self, url):
        self.ouverts.append(url)
        return url


def lu_a(cfg, **plus):
    """Ce que la fenêtre d'import montre à l'adresse du robot : la livraison d'aujourd'hui, sauf à une ancienne adresse."""
    vieille = 'AKfyUN' in cfg['tableau']
    return dict(TABLEAU31, adresse=robot.adresse_import(cfg), livraison='' if vieille else 'cd9cd8e', ancienne=vieille,
                contrats=ANCIENNE31['contrats'] if vieille else TABLEAU31['contrats'], **plus)


def adresse_avec(reponses, cfg, lecture=lu_a, action=None):
    vrais_a = {n: getattr(robot, n) for n in ('chrome', 'lire_tableau', 'nouvel_onglet')}
    vieil_input = builtins.input
    c_a, file_, lus_a = ChromeAdresse(), list(reponses), []
    robot.chrome = lambda *a, **k: c_a
    robot.lire_tableau = lambda c, cfg_: (lus_a.append(cfg_['tableau']), lecture(cfg_))[1]
    robot.nouvel_onglet = lambda url: c_a.ouverts.append(url)
    builtins.input = lambda invite='': (print(invite, end=''), file_.pop(0))[1]
    robot.garder(cfg)
    try:
        dit, r = sortie_de(action or robot.changer_adresse)
        return dit, r, c_a, lus_a, file_
    finally:
        builtins.input = vieil_input
        for n, v in vrais_a.items():
            setattr(robot, n, v)


avant_j = journal()
dit, _, c_a, lus_a, _ = adresse_avec([''], {'tableau': EXEC1, 'heure': '14:00', 'exports': []})
verifier('« Changer l’adresse » : l’adresse d’aujourd’hui montrée (un /exec : « le lien /dev est plus sûr »), comment trouver le lien /dev ; Entrée la garde',
         'L\'adresse du tableau de bord que le robot utilise aujourd\'hui :\n    ' + EXEC1 in dit and 'reste sur UN déploiement' in dit and
         'Déployer → Tester les déploiements → « Application Web »' in dit and 'Gardée : ' + EXEC1 in dit and
         robot.config()['tableau'] == EXEC1 and lus_a == [EXEC1], dit)
verifier('… puis il vérifie aussitôt : l’ancienne version vue à cette adresse, dite, avec quoi faire',
         'Tableau de bord lu : %s?page=import — version inconnue' % EXEC1 in dit and 'ANCIENNE version du tableau de bord' in dit and
         '  THS → fiche non lue (ancienne version du tableau de bord) ; pas encore d\'export GATES « tous les contrats » appris' in dit, dit[-1500:])
dit, _, c_a, lus_a, _ = adresse_avec(['pas une adresse', DEV + '?page=import'], {'tableau': EXEC1, 'heure': '14:00', 'exports': [], 'navigateur': 'edge'})
cfg_a = robot.config()
verifier('… on colle le lien /dev (copié depuis la fenêtre d’import) : refusé d’abord ce qui n’est pas une adresse, puis gardé, propre ; le reste de la configuration intact',
         'Ce n\'est pas une adresse internet' in dit and 'C\'est le lien /dev : le robot verra toujours la dernière version' in dit and
         cfg_a == {'tableau': DEV, 'heure': '14:00', 'exports': [], 'navigateur': 'edge'} and lus_a == [DEV], (cfg_a, dit))
verifier('… et vérifié tout de suite : la livraison qu’il voit, puis, pour chaque contrat, le nom GATES de sa fiche (pas encore d’export GATES appris)',
         'Tableau de bord lu : %s?page=import — Livraison cd9cd8e' % DEV in dit and
         '  HDK → sa fiche : « HDK AA » ; pas encore d\'export GATES « tous les contrats » appris' in dit and
         '  NEO (prévu, nouvel onglet) → sa fiche : « NEO AA » ; pas encore d\'export GATES « tous les contrats » appris' in dit and
         '  VRK → sa fiche n\'a pas de nom GATES ; pas encore d\'export GATES « tous les contrats » appris' in dit and
         '✓ Le robot voit le tableau de bord (Livraison cd9cd8e). En bas du tableau de bord, la « Livraison » doit être la même.' in dit, dit[-1500:])
verifier('… le changement est écrit au journal, avec l’adresse d’avant',
         'Adresse du tableau de bord changée : %s (avant : %s).' % (DEV, EXEC1) in journal()[len(avant_j):], journal()[-600:])
scenario('gates.json', 'GATES', '2026-11-03T09:00:00', GESTES31, modele={'appris': 'HDK AA', 'contrat': 'HDK'})
dit, _, _, _, _ = adresse_avec([''], {'tableau': DEV, 'heure': '14:00', 'exports': [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}]})
verifier('avec l’export GATES appris : la même vérification dit ce qu’il tapera (« THS → tape « THS AA » ») ; le lien /dev : « c’est le bon »',
         '(le lien /dev : il montre toujours la dernière version — c\'est le bon)' in dit and '  THS → tape « THS AA »' in dit and
         '  VRK → tape « VRK AA » (deviné : à écrire dans sa fiche pour être sûr)' in dit, dit[-1200:])
(R / 'exports' / 'gates.json').unlink()
dit, _, _, _, _ = adresse_avec([EXEC1.replace('AKfyUN', 'AKfyDEUX')], {'tableau': DEV, 'heure': '14:00', 'exports': []})
verifier('une adresse /exec collée : acceptée, mais avec un avertissement clair (chaque « Nouveau déploiement » en a une autre ; le lien /dev évite cela)',
         '⚠ Cette adresse finit par /exec : elle reste sur UN déploiement. Chaque « Nouveau déploiement » a une autre' in dit and
         robot.config()['tableau'] == EXEC1.replace('AKfyUN', 'AKfyDEUX'), dit)
lectures = iter([dict(TABLEAU31, cases=[], contrats=[], erreur='La fenêtre d\'import ne s\'est pas ouverte'), None])
dit, _, _, lus_a, reste = adresse_avec(['', ''], {'tableau': DEV, 'heure': '14:00', 'exports': []},
                                       lecture=lambda cfg_: next(lectures) or lu_a(cfg_))
verifier('la fenêtre ne se lit pas (connexion Google à refaire) : dit, on se connecte dans la fenêtre du robot, Entrée — il relit',
         '✗ Je n\'arrive pas à la lire : La fenêtre d\'import ne s\'est pas ouverte.' in dit and 'connectez-vous' in dit and
         len(lus_a) == 2 and reste == [] and 'Livraison cd9cd8e' in dit, dit[-1200:])
dit, _, _, lus_a, _ = adresse_avec([''], {'heure': '14:00', 'exports': []})
verifier('sans adresse du tout, Entrée : rien n’est ouvert, et il dit quoi faire', lus_a == [] and 'Sans adresse, le robot ne peut rien déposer' in dit, dit)
dit, _, c_a, lus_a, reste = adresse_avec(['', ''], {'tableau': DEV, 'heure': '14:00', 'exports': []}, action=robot.preparer)
verifier('« 1 - Preparer » montre aussi l’adresse (Entrée : la garder), ouvre les trois onglets, puis vérifie ce qu’il voit à cette adresse',
         'L\'adresse du tableau de bord que le robot utilise aujourd\'hui :\n    ' + DEV in dit and robot.config()['tableau'] == DEV and
         c_a.ouverts[0] == DEV and len(c_a.ouverts) == 3 and lus_a == [DEV] and 'Livraison cd9cd8e' in dit and reste == [], (c_a.ouverts, dit[-900:]))
dit, _, c_a, lus_a, reste = adresse_avec([EXEC1 + '#x', ''], {'tableau': DEV, 'heure': '14:00', 'exports': []}, action=robot.preparer)
verifier('… et la remplace si l’on en colle une autre (ici un /exec : l’avertissement ; la vérification dit l’ancienne version)',
         robot.config()['tableau'] == EXEC1 and '⚠ Cette adresse finit par /exec' in dit and c_a.ouverts[0] == EXEC1 and
         'ANCIENNE version du tableau de bord' in dit and reste == [], dit[-900:])
robot.garder({'tableau': EXEC1, 'exports': []})
dit, _ = sortie_de(robot.montrer_etat)
verifier('« Etat du robot » : une adresse /exec, dite — le lien /dev est plus sûr (« Changer l’adresse du tableau de bord »)',
         'un lien /exec, qui reste sur UN déploiement : le lien qui finit par /dev est plus sûr — « Changer l\'adresse du tableau de bord »' in dit, dit)
robot.garder({'tableau': DEV, 'exports': []})
verifier('… le lien /dev : rien à en dire', 'plus sûr' not in sortie_de(robot.montrer_etat)[0])
with robot.verrou() as libre:
    code_a = robot.main(['robot.py', 'adresse'])
verifier('« Changer l’adresse » pendant un passage du robot : refusé (le verrou)', code_a == 1 and robot.config()['tableau'] == DEV)

print('\n— Débrief 31 : d’autres chemins qui tapaient « THS » au lieu de « THS AA », ou sautaient un contrat —')
verifier('un nom retenu égal au nom du contrat (« THS » → « THS », la question d’avant le débrief 30) ne cache pas le nom deviné',
         robot.nom_du_jour({'noms_gates': {'THS': 'THS'}}, 'THS', MODELE) == ('THS AA', 'devine') and
         robot.nom_du_jour({'noms_gates': {'THS': 'THS'}}, {'contrat': 'THS', 'nom_gates': 'THS AA'}, MODELE) == ('THS AA', 'fiche'))
verifier('… pour le contrat appris lui-même, ce qu’on vient de montrer passe avant ce que le robot avait retenu',
         robot.nom_du_jour({'noms_gates': {'HDK': 'HDKX'}}, 'HDK', MODELE) == ('HDK AA', 'appris') and
         robot.nom_gates_de({'noms_gates': {'HDK': 'HDKX'}}, 'HDK') == 'HDKX')
robot.garder({'tableau': 'x', 'noms_gates': {'HDK': 'HDK AA', 'THS': 'THSX'}, 'exports': []})
dit, _ = apprendre_avec([dict(g, texte='HDK') if g['faire'] == 'remplir' else g for g in GESTES31],
                        dict(TABLEAU31, contrats=[dict(k, nom_gates='') for k in TABLEAU31['contrats']]), ['1', 1.0, 'n'])
verifier('réappris en tapant « HDK » seul : l’ancien « HDK AA » retenu s’efface (sinon il l’emportait), les autres restent',
         robot.config()['noms_gates'] == {'THS': 'THSX'}, robot.config().get('noms_gates'))
robot.garder({'tableau': 'x', 'exports': []})
dit, _ = apprendre_avec(GESTES31, dict(ANCIENNE31, contrats=[]), ['1', 1.0, 'n'])
verifier('une fenêtre d’avant (sans fiches) : « HDK AA » tapé, qui commence par le nom du seul contrat HDK — reconnu sans question',
         'Lequel de ces mots' not in dit and json.loads((R / 'exports' / 'gates.json').read_text(encoding='utf-8'))['modele'] == {'appris': 'HDK AA', 'contrat': 'HDK'} and
         'ANCIENNE version du tableau de bord' in dit and '  THS → tape « THS AA » (deviné : fiche non lue, ancienne version du tableau de bord)' in dit, dit[-1500:])
vieil_input = builtins.input
builtins.input = lambda invite='': '0'
tranche31 = robot.reperer_contrat([{'faire': 'remplir', 'texte': 'HDK AA'}], ['HDK', 'HDK Tranche 2'])
deux31 = sortie_de(robot.reperer_contrat, [{'faire': 'remplir', 'texte': 'HDK-B AA'}], ['HDK', 'HDK-B'])
builtins.input = vieil_input
verifier('… jamais pour une tranche (« HDK Tranche 2 » commence aussi par « HDK ») ; deux contrats qui conviennent : la question d’avant',
         tranche31 == ('HDK AA', 'HDK') and deux31[1] == ('', '') and 'Lequel de ces mots' in deux31[0], (tranche31, deux31))
(R / 'exports' / 'gates-ths-vieux.json').write_text('{abîmé', encoding='utf-8')
scenario('gates.json', 'GATES', '2026-11-03T09:00:00', GESTES31, modele={'appris': 'HDK AA', 'contrat': 'HDK'})
LISTE31 = [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True}, {'nom': 'GATES THS', 'scenario': 'gates-ths-vieux.json', 'case': 'GATES THS'}]
travaux31 = robot.a_faire({}, LISTE31, FICHES)
verifier('un ancien « GATES THS » resté à côté du modèle (son fichier illisible au rangement) : jamais fait — rien ne passe par-dessus THS AA, rien ne cale',
         [(e['case'], s['etapes'][2]['texte']) for e, s in travaux31] == [('GATES HDK', 'HDK AA'), ('GATES THS', 'THS AA'), ('GATES NEO', 'NEO AA')] and
         '« GATES THS » n’est pas fait : l’export GATES de tous les contrats le remplace.' in journal(), [(e['case'], e['nom']) for e, _ in travaux31])
(R / 'exports' / 'gates-ths-vieux.json').unlink()

print('\n— Débrief 31 (relu) : essayer SEE seul, un début tapé, ce que GATES montrait, une fenêtre plus ancienne que le robot, le compte rendu dit son lien —')
# Essayer SEE juste après l'avoir appris (« Le robot essaie tout de suite ? o ») : un faux « refaites Apprendre ».
for f31 in R.glob('exports/*.json'):
    f31.unlink()
scenario('gates.json', 'GATES', '2026-11-03T09:00:00', GESTES31, modele={'appris': 'HDK AA', 'contrat': 'HDK'})
scenario('see.json', 'SEE', '2026-11-03T09:10:00', [{'faire': 'cliquer', 'cible': {'texte': 'Submit'}}])
robot.garder({'tableau': DEV, 'heure': '14:00', 'exports': [{'nom': 'GATES', 'scenario': 'gates.json', 'modele': True},
                                                            {'nom': 'SEE', 'scenario': 'see.json', 'case': 'SEE'}]})
vrais_e = {n: getattr(robot, n) for n in ('chrome', 'attendre_tableau', 'rejouer', 'photo')}
joues_e = []


def rejouer_essai(c, s_, dossier):
    joues_e.append(s_['nom'])
    p_ = pathlib.Path(dossier) / (robot.nom_de_fichier(s_['nom']) + '.xlsx')
    p_.write_text('x', encoding='utf-8')
    return p_


robot.chrome = lambda *a, **k: FauxChrome()
robot.attendre_tableau = lambda c, cfg, delai: dict(TABLEAU31, adresse=robot.adresse_import(cfg))
robot.rejouer, robot.photo = rejouer_essai, (lambda c: '')
vieil_input = builtins.input
builtins.input = lambda invite='': ''
try:
    avant_j = journal()
    dit_e, _ = sortie_de(robot.essayer, ['SEE'])
    j_e = journal()[len(avant_j):]
    joues_see = list(joues_e)
    del joues_e[:]
    dit_g, _ = sortie_de(robot.essayer, ['GATES'])
finally:
    builtins.input = vieil_input
    for n, v in vrais_e.items():
        setattr(robot, n, v)
verifier('essayer SEE seul (l’export GATES de tous les contrats déjà appris) : SEE refait, « Tout est bon » — pas de faux « refaites Apprendre » pour GATES',
         joues_see == ['SEE'] and 'Tout est bon : le robot sait refaire SEE.' in dit_e and 'refaites « Apprendre »' not in dit_e and '✗' not in dit_e, dit_e[-1500:])
verifier('… et ce qu’il dit des contrats vient du modèle appris (« THS → tape « THS AA » »), pas « pas encore d’export GATES » — au journal aussi',
         '  THS → tape « THS AA »' in j_e and 'pas encore d\'export GATES' not in j_e, j_e[-1200:])
verifier('… essayer GATES fait toujours chaque contrat du tableau de bord', joues_e == ['GATES HDK', 'GATES THS', 'GATES VRK', 'GATES NEO'] and
         'Tout est bon' in dit_g, (joues_e, dit_g[-800:]))

# Un début tapé (« HDK A »), puis la suggestion « HDK AA » cliquée.
G_DEBUT = [{'faire': 'remplir', 'cible': {'balise': 'input', 'placeholder': 'Contrat'}, 'texte': 'HDK A'},
           {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'HDK AA'}},
           {'faire': 'remplir', 'cible': {'balise': 'input', 'placeholder': 'Contrat'}, 'texte': 'HDK AA'},
           {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'XLSX'}}]
s_ths = robot.pour_le_contrat({'nom': 'GATES', 'etapes': G_DEBUT}, 'HDK AA', 'THS', 'THS AA', 'HDK AA')['etapes']
s_hdk = robot.pour_le_contrat({'nom': 'GATES', 'etapes': G_DEBUT}, 'HDK AA', 'HDK', 'HDK AA', 'HDK AA')['etapes']
verifier('appris en tapant « HDK A » puis en cliquant « HDK AA » : pour THS, le robot tape « THS AA » en entier (retapé « HDK A », GATES ne proposait que HDK) et clique « THS AA »',
         [g.get('texte') or g['cible'].get('texte') for g in s_ths] == ['THS AA', 'THS AA', 'THS AA', 'XLSX'] and s_ths[1]['cible']['contient'] == 'THS AA', s_ths)
verifier('… pour HDK lui-même : exactement les gestes montrés (« HDK A », puis « HDK AA »)',
         [g.get('texte') or g['cible'].get('texte') for g in s_hdk] == ['HDK A', 'HDK AA', 'HDK AA', 'XLSX'], s_hdk)
G_DEBUT2 = [dict(G_DEBUT[0]), {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'HDK AA — 634 plans'}}, G_DEBUT[3]]
builtins.input = lambda invite='': (_ for _ in ()).throw(AssertionError('le robot pose une question : %s' % invite))
try:
    vu_debut = robot.reperer_contrat(G_DEBUT2, TABLEAU31['contrats'])
finally:
    builtins.input = vieil_input
verifier('« HDK A » tapé, puis « HDK AA — 634 plans » cliqué : reconnu sans question — le nom de la fiche, tel que GATES le montre (« HDK AA »), sur HDK',
         vu_debut == ('HDK AA', 'HDK'), vu_debut)
robot.garder({'tableau': 'x', 'exports': []})
dit, _ = apprendre_avec(G_DEBUT2, TABLEAU31, ['1', 1.0, 'n'])
cfg_d = robot.config()
travaux_d = robot.a_faire(cfg_d, cfg_d['exports'], robot.contrats_lus(TABLEAU31))
verifier('… appris ainsi : ce qu’il annonce (« THS → tape « THS AA » ») est ce qu’il tape le lendemain, pour chaque contrat',
         'Lequel de ces mots' not in dit and '  THS → tape « THS AA »' in dit and
         [(e['contrat'], s_['etapes'][0]['texte'], s_['etapes'][1]['cible']['texte'], s_['etapes'][1]['cible'].get('contient')) for e, s_ in travaux_d] ==
         [('HDK', 'HDK A', 'HDK AA — 634 plans', 'HDK AA'), ('THS', 'THS AA', 'THS AA — 634 plans', 'THS AA'),
          ('VRK', 'VRK AA', 'VRK AA — 634 plans', 'VRK AA'), ('NEO', 'NEO AA', 'NEO AA — 634 plans', 'NEO AA')],
         [(e['contrat'], s_['etapes'][0]['texte'], s_['etapes'][1]['cible']['texte'], s_['etapes'][1]['cible'].get('contient')) for e, s_ in travaux_d])

# La fiche de HDK n'a pas de nom GATES ; appris en tapant « HDK », en cliquant « HDK AA — 634 plans » : jamais « THS AB AA — … ».
s_t2 = robot.pour_le_contrat({'nom': 'GATES', 'etapes': G31b}, 'HDK', 'THS Tranche 2', 'THS AB', '')['etapes']
verifier('« HDK » tapé, « HDK AA — 634 plans » cliqué, sans nom GATES dans la fiche de HDK : pour « THS Tranche 2 » (« THS AB »), « THS AB — 634 plans » — jamais « THS AB AA — … »',
         s_t2[0]['texte'] == 'THS AB' and s_t2[1]['cible']['texte'] == 'THS AB — 634 plans' and s_t2[1]['cible']['contient'] == 'THS AB', s_t2)
(R / 'exports' / 'gates-t2.json').write_text(json.dumps({'nom': 'GATES', 'depart': 'x', 'etapes': G31b, 'modele': {'appris': 'HDK', 'contrat': 'HDK'}}), encoding='utf-8')
travaux_t2 = robot.a_faire({}, [{'nom': 'GATES', 'scenario': 'gates-t2.json', 'modele': True}],
                           [{'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': '', 'prevu': False},
                            {'contrat': 'THS', 'case': 'GATES THS', 'nom_gates': 'THS AA', 'prevu': False},
                            {'contrat': 'THS Tranche 2', 'case': 'GATES THS Tranche 2', 'nom_gates': 'THS AB', 'prevu': True}])
verifier('… chaque jour : HDK comme appris, THS « THS AA — 634 plans », la tranche « THS AB — 634 plans »',
         [(e['contrat'], s_['etapes'][0]['texte'], s_['etapes'][1]['cible']['texte']) for e, s_ in travaux_t2] ==
         [('HDK', 'HDK', 'HDK AA — 634 plans'), ('THS', 'THS AA', 'THS AA — 634 plans'), ('THS Tranche 2', 'THS AB', 'THS AB — 634 plans')],
         [(e['contrat'], s_['etapes'][0]['texte'], s_['etapes'][1]['cible']['texte']) for e, s_ in travaux_t2])
verifier('… « forme_vue » ne prend qu’un ou deux mots courts avant le séparateur (rien dans « HDK AA 011 > Avancement… », ni dans « HDKA — … »)',
         robot.forme_vue([{'faire': 'cliquer', 'cible': {'texte': 'HDK AA 011 > Avancement'}}], 'HDK') == '' and
         robot.forme_vue([{'faire': 'cliquer', 'cible': {'texte': 'HDKA — 600 plans'}}], 'HDK') == '' and
         robot.forme_vue([{'faire': 'remplir', 'texte': 'HDK AA — x'}], 'HDK') == '' and
         robot.forme_vue([{'faire': 'choisir', 'option': 'HDK AB (tranche)'}], 'HDK') == 'HDK AB')

# Une fenêtre du débrief 30 : le pont et les fiches, mais pas de livraison — plus ancienne que ce robot.
D30 = dict(TABLEAU31, livraison='', ancienne=False, perimee=True, adresse=EXEC1 + '?page=import')
lignes_d30 = robot.entete_du_tableau({'tableau': EXEC1}, D30)
verifier('une fenêtre avec pont mais sans « Livraison » (un déploiement du débrief 30) : dite plus ANCIENNE que le robot, avec l’adresse et le lien /dev à donner',
         lignes_d30[0] == 'Tableau de bord lu : %s?page=import — version inconnue' % EXEC1 and 'plus ANCIENNE que lui' in lignes_d30[1] and
         EXEC1 + '?page=import' in lignes_d30[1] and '« Changer l\'adresse du tableau de bord »' in lignes_d30[1] and
         'Il lit les fiches des contrats' in lignes_d30[1], lignes_d30)
verifier('… ses fiches sont lues : les lignes des contrats ne disent pas « fiche non lue »',
         robot.lignes_des_contrats({}, robot.contrats_lus(D30), {'modele': MODELE}, D30['ancienne']) ==
         ['  HDK → tape « HDK AA »', '  THS → tape « THS AA »', '  VRK → tape « VRK AA » (deviné : à écrire dans sa fiche pour être sûr)',
          '  NEO → tape « NEO AA » (prévu, nouvel onglet)'])
dit, _, _, _, _ = adresse_avec([''], {'tableau': EXEC1, 'heure': '14:00', 'exports': []}, lecture=lambda cfg_: dict(D30, adresse=robot.adresse_import(cfg_)))
verifier('« Changer l’adresse » sur cette fenêtre : jamais « ✓ Le robot voit le tableau de bord » — l’avertissement à la place',
         '✓ Le robot voit le tableau de bord' not in dit and 'plus ANCIENNE que lui' in dit, dit[-1200:])
if (R / 'alerte-version.txt').exists():
    (R / 'alerte-version.txt').unlink()
appels.clear()
robot.prevenir_ancienne({'tableau': EXEC1}, D30, True)
robot.prevenir_ancienne({'tableau': EXEC1}, D30, False)
prev_d30 = [a[1] for a in appels if a[0] == 'prevenu']
verifier('… en automatique, la petite fenêtre de la fin le dit aussi (une fois ; « Lancer maintenant » : la fenêtre noire)',
         len(prev_d30) == 1 and 'plus ANCIENNE que lui' in prev_d30[0] and 'Changer l\'adresse du tableau de bord' in prev_d30[0] and 'Nouvelle version' not in prev_d30[0], prev_d30)
dit, _ = sortie_de(robot.rappeler_ancienne, {'tableau': DEV}, D30)
verifier('… sur le lien /dev, c’est le code du projet qui est d’avant : recoller la dernière livraison',
         'plus ANCIENNE que lui' in dit and 'collez la dernière livraison' in dit and 'Tester les déploiements' not in dit, dit)

# Le compte rendu dit la sorte de lien du robot : sur /dev, le site ne lui demande pas d'en changer après chaque livraison.
verifier('le compte rendu dit son lien : « adresse » = « dev » ou « exec » ; rien pour une adresse ni /dev ni /exec',
         robot.rapport_du_robot({'tableau': DEV}, '', [], [], 0).get('adresse') == 'dev' and
         robot.rapport_du_robot({'tableau': EXEC1}, '', [], [], 0).get('adresse') == 'exec' and
         'adresse' not in robot.rapport_du_robot({'tableau': 'https://exemple.fr/x'}, '', [], [], 0))

print('\n— Débrief 31 : une attente longue dit son maximum, puis où elle en est —')
robot.Patience.PAS = 1


class ChromeSansFichier:
    def attendre_telechargement(self, avant=None, delai=0, motif=None):
        import time as _t
        _t.sleep(delai)
        raise robot.ErreurPilote('rien')


err31 = ''
tampon = io.StringIO()
try:
    with contextlib.redirect_stdout(tampon):
        robot.attendre_fichier(ChromeSansFichier(), set(), '*.xlsx', 3)
except robot.ErreurPilote as err:
    err31 = str(err)
dit = tampon.getvalue()
verifier('le fichier : « j’attends jusqu’à … », puis « … pas encore arrivé (1 s) », puis l’erreur avec le maximum',
         '(le fichier se prépare, le robot attend qu\'il soit arrivé — j\'attends jusqu\'à 3 s)' in dit and '… pas encore arrivé (1 s)' in dit and
         err31 == 'Aucun fichier « *.xlsx » n\'est arrivé en 3 s.', (dit, err31))
verifier('les durées dites en clair : « 5 min », « 30 min », « 45 s »',
         (robot.duree_dite(300), robot.duree_dite(1800), robot.duree_dite(45), robot.duree_dite(150)) == ('5 min', '30 min', '45 s', '2 min'))
robot.Patience.PAS = 60

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
        # Débrief 31 : « (attente : … grisé) » faisait croire le robot figé.
        robot.Patience.PAS = 1
        tampon = io.StringIO()
        with contextlib.redirect_stdout(tampon):
            fait31 = rejouer_sur(grise.replace('},3000);', '},6000);'), pas)
        robot.Patience.PAS = 60
        dit = tampon.getvalue()
        verifier('… et l’attente le dit : son maximum d’abord, puis où elle en est (« … toujours grisé (2 s) »)',
                 fait31 == 'export XLSX pour 4530' and '(attente : « Export all » grisé — j\'attends jusqu\'à 10 s)' in dit and
                 dit.count('(attente : « Export all » grisé') == 1 and '    … toujours grisé (2 s)\n' in dit, dit)
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
                 dit.startswith('erreur : Le menu « Export all » ne s’est pas ouvert (« XLSX » ne s’est pas montré), même après plusieurs essais'.replace('’', "'")) and
                 'relancez « 3 - Essayer »' in dit and _time.time() - t0 < 200, dit[:400])
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

        # Débrief 31 : le guetteur est posé dans CHAQUE page du rejeu (comme quand l'export a été appris) :
        # un lien « nouvel onglet » sur une page suivante reste dans l'onglet du robot.
        import http.server as _hs
        import threading as _th
        PAGES = {'/p1': '<a href="/p2">Suite</a>', '/p2': '<a href="/p3" target="_blank">Exporter</a>',
                 '/p3': '<button onclick="var a=document.createElement(\'a\');a.href=\'data:application/octet-stream;base64,UEsDBA==\';'
                        'a.download=\'liens.xlsx\';document.body.appendChild(a);a.click();">XLSX</button>'}

        class Pages(_hs.BaseHTTPRequestHandler):
            def do_GET(self):
                corps = ('<!doctype html><meta charset="utf-8"><body>' + PAGES.get(self.path, 'introuvable')).encode('utf-8')
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.end_headers()
                self.wfile.write(corps)

            def log_message(self, *a):
                pass
        site = _hs.ThreadingHTTPServer(('127.0.0.1', 0), Pages)
        _th.Thread(target=site.serve_forever, daemon=True).start()
        scen = {'nom': 'Liens', 'depart': 'http://127.0.0.1:%d/p1' % site.server_port, 'fichier': '*.xlsx', 'telechargement_apres': 3,
                'etapes': [{'faire': 'cliquer', 'cible': {'balise': 'a', 'texte': 'Suite'}}, {'faire': 'cliquer', 'cible': {'balise': 'a', 'texte': 'Exporter'}},
                           {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'XLSX'}}]}
        try:
            f, res = robot.rejouer(c, scen, sortie), ''
        except robot.ErreurPilote as err:
            f, res = None, str(err)
        site.shutdown()
        verifier('une page suivante (une autre adresse) avec un lien « nouvel onglet » : le robot reste dans son onglet, le fichier arrive',
                 f is not None and f.exists() and c.evaluer('location.pathname') == '/p3', (f, res))

# ---- début débrief 32 (bloc autonome : il se rejoue tel quel contre un ancien robot.py, pour voir l'avant/après)
print('\n— Débrief 32 : le menu GATES qui ne s’ouvre pas au 2e contrat —')
# Nathan, livraison 3d35dfb : HDK sort, puis pour VRK « 1/6 cliquer (un élément sans nom) », le menu GATES
# (un simple dessin, sans texte) ne s'ouvre pas ; « Données MK2 » reste posé dans la page mais caché
# (« couvert ») et le robot attend 5 minutes, jusqu'à ce que Nathan ouvre le menu à la main.
# Ici, une page comme GATES (application d'une seule page, adresses en « #/… ») servie en local :
# le menu « GATES » sans aucun nom ; « Données MK2 » caché (opacity 0, pointer-events none) tant que le
# menu est fermé ; « Choisir une tranche » et ses suggestions ; « Exporter » ; « Exporter (.xls) » → un fichier.
# Comme un vrai menu, la ligne d'un menu fermé ne répond à rien (pas même à un clic envoyé par script).
# Variantes (?v=) : a — l'application branche le menu 3 s après s'être dessinée (et le redessine) ;
# b — départ avec un « #/accueil » (Chrome ne recharge pas : l'application garde l'état du 1er export,
# son menu se croit ouvert) ; c — le menu s'ouvre au survol, et un clic le referme ; d — au 2e export,
# le premier clic sur le menu se perd (le cas de Nathan). Puis la sécurité (une autre page) : « Submit »
# suivi d'un voile de chargement, un voile sur toute la page, le geste du fichier — jamais recliqués.
if not exe:
    print('  (pas de Chrome sur ce poste : partie sautée)')
else:
    import contextlib as _cl32
    import http.server as _hs32
    import io as _io32
    import json as _json32
    import threading as _th32
    import time as _t32
    GATES32 = r'''<!doctype html><html><head><meta charset="utf-8"><title>CHILDNéo</title><style>
body{margin:0;font:14px sans-serif}
#app-header{height:48px;background:#0b3d6e;display:flex;align-items:center;gap:12px;padding:0 8px}
.menu-gates{position:relative}
.gates-trigger{width:40px;height:40px;cursor:pointer;background:#2a6db0 url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 24 24'%3E%3Cpath fill='white' d='M3 6h18v2H3zm0 5h18v2H3zm0 5h18v2H3z'/%3E%3C/svg%3E") center/24px no-repeat}
.sous-menu{position:absolute;top:44px;left:0;width:220px;background:#fff;box-shadow:0 2px 8px #0005;opacity:0;pointer-events:none;transition:opacity .12s;z-index:5}
.sous-menu.ouvert{opacity:1;pointer-events:auto}
.sous-menu a{display:block;padding:10px;cursor:pointer;color:#036}
.titre{color:#fff}
main{padding:24px;min-height:600px}
#sugg li{cursor:pointer;padding:4px}
#dlg{position:fixed;left:30%;top:30%;background:#fff;border:1px solid #888;padding:16px;z-index:9}
.voile{position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.25);z-index:20}
</style></head><body><header id="app-header"></header><main id="vue"></main>
<script>
var V = new URLSearchParams(location.search).get('v') || '';
/* (relecture) h — le menu fermé en display:none (Bootstrap) ; q — une petite requête toutes les 3 s (session, notifications) */
if (V.indexOf('h') >= 0) document.head.insertAdjacentHTML('beforeend', '<style>.sous-menu{display:none}.sous-menu.ouvert{display:block}</style>');
if (V.indexOf('q') >= 0) setInterval(function () { fetch('/lent?' + Math.random()); }, 3000);
var n = +(sessionStorage.getItem('exports') || 0), ouvert = false, avale = V.indexOf('d') >= 0 && n === 1;
var T = ['HDK AA (SUPER PUMA)', 'VRK AA (SUPER PUMA)', 'THS AA (TIGRE)'];
var note = function (t) { sessionStorage.setItem('journal', (sessionStorage.getItem('journal') || '') + t + ';'); };
function menu(o) { ouvert = o; var m = document.querySelector('.sous-menu'); if (m) m.classList.toggle('ouvert', o); }
function brancher() {
  var t = document.querySelector('.gates-trigger'), w = document.querySelector('.menu-gates');
  t.addEventListener('click', function () { note('clic menu'); if (avale) { avale = false; note('perdu'); return; } menu(!ouvert); });
  if (V.indexOf('c') >= 0) { w.addEventListener('mouseenter', function () { menu(true); }); w.addEventListener('mouseleave', function () { menu(false); }); }
  [].forEach.call(document.querySelectorAll('.sous-menu a'), function (a) {
    a.addEventListener('click', function () {
      var m = document.querySelector('.sous-menu');
      if (!m.classList.contains('ouvert')) { note('ligne d’un menu fermé'); return; }   /* un menu fermé ne répond pas */
      if (V.indexOf('b') < 0) ouvert = false; m.classList.remove('ouvert'); location.hash = a.getAttribute('data-vers'); });
  });
}
function entete(branche) {
  document.getElementById('app-header').innerHTML = '<div class="menu-gates"><div class="gates-trigger"></div><div class="sous-menu">' +
    '<a data-vers="#/mk1">Données MK1</a><a data-vers="#/mk2">Données MK2</a><a data-vers="#/aide">Aide</a></div></div><span class="titre">CHILDNéo — GATES</span>';
  if (branche) brancher();
}
function route() {
  var h = location.hash || '#/accueil', vue = document.getElementById('vue');
  if (V.indexOf('a') >= 0) { entete(false); clearTimeout(window.__t); window.__t = setTimeout(function () { entete(true); }, 3000); }
  if (h !== '#/mk2') { vue.innerHTML = '<h2>Bienvenue dans GATES</h2><p>Choisissez un menu.</p>'; return; }
  vue.innerHTML = '<h2>Données MK2</h2><div class="ligne"><span>Choisir une tranche</span><div><input id="tranche" autocomplete="off"></div></div>' +
    '<ul id="sugg"></ul><button id="exporter">Exporter</button><div id="res"></div>';
  var i = document.getElementById('tranche'), u = document.getElementById('sugg'), choisie = '';
  i.addEventListener('input', function () { var v = i.value.toLowerCase(); u.innerHTML = v ? T.filter(function (t) { return t.toLowerCase().indexOf(v) === 0; })
    .map(function (t) { return '<li>' + t + '</li>'; }).join('') : ''; });
  u.addEventListener('click', function (e) { if (e.target.tagName === 'LI') { choisie = e.target.textContent; i.value = choisie; u.innerHTML = ''; } });
  document.getElementById('exporter').addEventListener('click', function () {
    if (!choisie || document.getElementById('dlg')) return;
    var d = document.createElement('div'); d.id = 'dlg'; d.innerHTML = '<p>Exporter « ' + choisie + ' »</p><button id="xls">Exporter (.xls)</button>';
    document.body.appendChild(d);
    document.getElementById('xls').addEventListener('click', function () {
      var a = document.createElement('a'); a.href = 'data:application/octet-stream;base64,UEsDBA=='; a.download = 'export.xlsx';
      document.body.appendChild(a); a.click(); d.remove(); n++; sessionStorage.setItem('exports', n); note('export ' + choisie);
      document.getElementById('res').textContent = 'export ' + choisie;
    });
  });
}
window.addEventListener('hashchange', route);
if (V.indexOf('a') < 0) entete(true);
route();
</script>'''
    # Sécurité : « Submit » (un voile de chargement ~20 s ensuite), « Afficher » (un voile sur toute la page),
    # puis « Export all » et son menu ; « Exporter (.xls) » suivi d'un « Fermer » qui tarde.
    SURE32 = r'''<!doctype html><html><head><meta charset="utf-8"><style>
.voile{position:fixed;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.25);z-index:20}
#menu li{cursor:pointer}</style></head><body>
<button id="submit">Submit</button> <button id="aff">Afficher</button>
<button id="exp" title="Export all">⇩</button><ul id="menu"></ul><button id="fermer">Fermer</button>
<script>
var compte = {submit: 0, aff: 0, exp: 0, xls: 0, fermer: 0};
var voile = function (ms) { var v = document.createElement('div'); v.className = 'voile'; document.body.appendChild(v); setTimeout(function () { v.remove(); }, ms); };
var V = new URLSearchParams(location.search).get('v') || '';
document.getElementById('submit').onclick = function () { compte.submit++; voile(+(V || 20000)); };
document.getElementById('aff').onclick = function () { compte.aff++; voile(8000); };
document.getElementById('exp').onclick = function () { compte.exp++; document.getElementById('menu').innerHTML = '<li id="xls">Exporter (.xls)</li>'; };
document.getElementById('menu').onclick = function (e) { if (e.target.id !== 'xls') return; compte.xls++;
  var a = document.createElement('a'); a.href = 'data:application/octet-stream;base64,UEsDBA=='; a.download = 'see.xlsx'; document.body.appendChild(a); a.click(); voile(6000); };
document.getElementById('fermer').onclick = function () { compte.fermer++; };
</script>'''

    class Pages32(_hs32.BaseHTTPRequestHandler):
        def do_GET(self):
            corps = (SURE32 if self.path.startswith('/sur') else GATES32).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(corps)

        def log_message(self, *a):
            pass
    site32 = _hs32.ThreadingHTTPServer(('127.0.0.1', 0), Pages32)
    _th32.Thread(target=site32.serve_forever, daemon=True).start()
    BASE32 = 'http://127.0.0.1:%d/gates/childneo' % site32.server_port
    NOMS32 = ('DELAI_TROUVER', 'DELAI_SUITE', 'DELAI_CACHE', 'DELAI_ROUVRIR', 'DELAI_REOUVERTURE', 'DELAI_PAGE_NEUVE')
    avant32 = {k: getattr(robot, k, None) for k in NOMS32}
    # Des délais courts pour la batterie (chez Nathan : 5 min, 45 s…) : l'ancien robot, lui, attend
    # DELAI_TROUVER avec « Données MK2 » caché, puis clique à l'aveugle.
    robot.DELAI_TROUVER, robot.DELAI_SUITE, robot.DELAI_CACHE = 20, 4, 3
    robot.DELAI_ROUVRIR, robot.DELAI_REOUVERTURE, robot.DELAI_PAGE_NEUVE = 4, 6, 30
    options32 = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
    sortie32 = pathlib.Path(tempfile.mkdtemp(prefix='robot-d32-'))

    def centre32(c, sel):
        return c.evaluer('(function(){var e=%s;var r=e.getBoundingClientRect();return {x:r.left+r.width/2,y:r.top+r.height/2};})()' % sel)

    def apprendre32(c):
        """« Apprendre » sur HDK : le vrai guetteur dans la page, de vrais clics, une vraie frappe."""
        c.ouvrir('about:blank')
        c.ouvrir(BASE32)
        c.evaluer('sessionStorage.clear()')
        c.ouvrir('about:blank')
        c.ouvrir(BASE32)
        c.evaluer('window.__vus=[];window.__suiviFwd=function(s){window.__vus.push(s);}')
        c.evaluer(robot.GUETTEUR)
        for sel, pause in (('document.querySelector(".gates-trigger")', 0.6), ('document.querySelectorAll(".sous-menu a")[1]', 0.8),
                           ('document.getElementById("tranche")', 0.3)):
            p = centre32(c, sel)
            robot.souris(c, p['x'], p['y'])
            _t32.sleep(pause)
        c.envoyer('Input.insertText', text='HDK AA')
        _t32.sleep(1.2)
        for sel in ('document.querySelector("#sugg li")', 'document.getElementById("exporter")', 'document.getElementById("xls")'):
            p = centre32(c, sel)
            robot.souris(c, p['x'], p['y'])
            _t32.sleep(0.8)
        pas = []
        for brut in c.evaluer('window.__vus'):
            robot.ajouter_geste(pas, _json32.loads(brut))
        return {'nom': 'GATES', 'depart': BASE32, 'etapes': pas, 'fichier': '*.xlsx', 'telechargement_apres': len(pas),
                'modele': {'appris': 'HDK AA', 'contrat': 'HDK'}}

    def deux_contrats32(c, scen, v='', diese=''):
        """Comme « 3 - Essayer » : GATES HDK puis GATES VRK, dans le MÊME onglet (rejouer, pour_le_contrat)."""
        c.ouvrir('about:blank')
        c.ouvrir(BASE32 + '?v=' + v)
        c.evaluer('sessionStorage.clear()')
        c.ouvrir('about:blank')
        depart = BASE32 + ('?v=' + v if v else '') + diese
        sortis, dit, err = [], _io32.StringIO(), ''
        t0 = _t32.time()
        try:
            with _cl32.redirect_stdout(dit):
                for contrat in ('HDK', 'VRK'):
                    s = robot.pour_le_contrat(dict(scen, depart=depart), 'HDK AA', contrat, contrat + ' AA')
                    print('Export « %s »…' % s['nom'])
                    sortis.append(robot.rejouer(c, s, sortie32).name)
        except robot.ErreurPilote as e:
            err = str(e).split('\n')[0]
        except Exception as e:  # noqa: BLE001 — un ancien robot.py peut manquer d'une fonction
            err = '%s: %s' % (type(e).__name__, e)
        try:
            journal_page = c.evaluer('sessionStorage.getItem("journal")') or ''
        except robot.ErreurPilote:
            journal_page = ''
        return {'sortis': sortis, 'err': err, 'dit': dit.getvalue(), 'page': journal_page, 'duree': round(_t32.time() - t0)}

    # Ce que Nathan a vu : le robot planté devant « Données MK2 » caché, jusqu'à 5 minutes (ici DELAI_TROUVER).
    SANS_ATTENTE32 = '(attente : « Données MK2 » couvert'
    # (relecture : « couvert » se dit désormais « caché derrière autre chose » ou « pas encore affiché »)
    ATTENTES32 = (SANS_ATTENTE32, '(attente : « Données MK2 » caché derrière', '(attente : « Données MK2 » pas encore affiché')

    def planté32(dit):
        return any(a in dit for a in ATTENTES32)

    def resume32(r):
        return {k: r[k] for k in ('sortis', 'err', 'page', 'duree')}, r['dit'][-1500:]

    try:
        with Chrome(port=9481, lancer=True, profil=tempfile.mkdtemp(prefix='robot-d32-'), sans_fenetre=True, delai=30, options=options32,
                    telechargements=str(R / 'telechargements')) as c:
            scen32 = apprendre32(c)
            pas32 = scen32['etapes']
            dits32 = [robot.dire_geste(g) for g in pas32]
            verifier('appris sur HDK par le vrai guetteur : les six gestes de Nathan (le menu sans nom, « Données MK2 », la tranche, sa suggestion, Exporter, Exporter (.xls))',
                     [g['faire'] for g in pas32] == ['cliquer', 'cliquer', 'remplir', 'cliquer', 'cliquer', 'cliquer'] and
                     dits32[1:] == ['« Données MK2 »', '« HDK AA » dans le champ « Choisir une tranche »', '« HDK AA (SUPER PUMA) »', '« Exporter »', '« Exporter (.xls) »'] and
                     not robot.nom_de_cible(pas32[0]['cible']), dits32)
            menu32 = pas32[0]['cible']
            verifier('le menu « GATES » : ni texte, ni aria, ni titre, ni bulle, ni icône — mais un indice de plus, sa classe à lui (« gates-trigger »)',
                     not any(menu32.get(k) for k in ('texte', 'label', 'titre', 'bulle', 'icone', 'testid', 'id')) and
                     menu32.get('classe') == 'gates-trigger' and menu32.get('chemin', '').endswith('div:nth-of-type(1) > div:nth-of-type(1)'), menu32)

            r = deux_contrats32(c, scen32)
            verifier('témoin : la page GATES simple, HDK puis VRK dans le même onglet — les deux fichiers',
                     r['sortis'] == ['gates-hdk.xlsx', 'gates-vrk.xlsx'] and not r['err'] and 'export HDK AA (SUPER PUMA);' in r['page'] and
                     'export VRK AA (SUPER PUMA);' in r['page'], resume32(r))
            verifier('… et le menu sans nom se dit par ce qu’il ouvre : « 1/6 cliquer (le menu qui ouvre « Données MK2 ») »',
                     '  1/6 cliquer (le menu qui ouvre « Données MK2 »)\n' in r['dit'] and '(un élément sans nom)' not in r['dit'], r['dit'][:600])

            r = deux_contrats32(c, scen32, 'd')
            verifier('d — le cas de Nathan : au 2e export (VRK), le premier clic sur le menu se perd ; « Données MK2 » reste caché — '
                     'le robot reclique sur le menu, tout seul, et VRK sort',
                     r['sortis'] == ['gates-hdk.xlsx', 'gates-vrk.xlsx'] and not r['err'] and 'perdu;clic menu;' in r['page'] and
                     'export VRK AA (SUPER PUMA);' in r['page'], resume32(r))
            verifier('… dit en clair, sans attendre 5 minutes, SOUS la ligne « 1/6 » : « (« Données MK2 » ne s’est pas montré : le menu ne s’est pas ouvert, '
                     'le robot essaie de le rouvrir) », les essais numérotés, et au journal « … ne s’était pas ouvert du premier coup ; rouvert par : … »',
                     '(« Données MK2 » ne s\'est pas montré : le menu ne s\'est pas ouvert, le robot essaie de le rouvrir)' in r['dit'] and
                     '      … essai 1 : la souris posée sur le menu\n' in r['dit'] and
                     r['dit'].rindex('  1/6 cliquer (le menu qui ouvre « Données MK2 »)') < r['dit'].rindex('(« Données MK2 » ne s\'est pas montré') and
                     'ne s\'était pas ouvert du premier coup ; rouvert par : ' in journal() and not planté32(r['dit']) and
                     r['duree'] < 90, resume32(r))

            r = deux_contrats32(c, scen32, 'b', '#/accueil')
            verifier('b — départ « …#/accueil » : Chrome ne rechargeait pas (même document), l’application gardait l’état du 1er export — '
                     'le robot recharge la page, VRK sort',
                     r['sortis'] == ['gates-hdk.xlsx', 'gates-vrk.xlsx'] and not r['err'] and 'export VRK AA (SUPER PUMA);' in r['page'] and
                     'essaie de le rouvrir' not in r['dit'] and 'il a fallu recliquer' not in r['dit'] and not planté32(r['dit']), resume32(r))

            r = deux_contrats32(c, scen32, 'a')
            verifier('a — l’application branche son menu 3 s après s’être dessinée (et le redessine) : le robot attend la page calme, '
                     'puis reclique sur le menu redessiné — HDK et VRK sortent, sans attendre devant « Données MK2 » caché',
                     r['sortis'] == ['gates-hdk.xlsx', 'gates-vrk.xlsx'] and not r['err'] and 'export VRK AA (SUPER PUMA);' in r['page'] and
                     not planté32(r['dit']), resume32(r))

            r = deux_contrats32(c, scen32, 'c')
            verifier('c — un menu qui s’ouvre au survol, et qu’un clic referme : le robot le survole à nouveau — HDK et VRK sortent, '
                     'sans attendre devant « Données MK2 » caché',
                     r['sortis'] == ['gates-hdk.xlsx', 'gates-vrk.xlsx'] and not r['err'] and 'export VRK AA (SUPER PUMA);' in r['page'] and
                     ('essai : le survol' in r['dit'] or 'essai 1 : la souris posée sur le menu' in r['dit']) and not planté32(r['dit']), resume32(r))

            # Un export appris AVANT ce débrief (le menu décrit par son seul chemin) : retrouvé exactement comme avant.
            ancien32 = dict(scen32, etapes=[dict(g, cible={k: v for k, v in g['cible'].items() if k not in ('contenu', 'alt', 'svgtitre', 'classe')})
                                            for g in pas32])
            r = deux_contrats32(c, ancien32, 'd')
            verifier('un export appris avant (le menu sans nom, décrit par son seul chemin) : rien à réapprendre — HDK et VRK sortent, même au clic perdu',
                     r['sortis'] == ['gates-hdk.xlsx', 'gates-vrk.xlsx'] and not r['err'], resume32(r))
            # Sa place a changé (un bandeau du jour avant lui) : retrouvé par sa classe à lui ; un export d'avant, sans elle, pas pris ailleurs.
            c.ouvrir(BASE32)
            c.evaluer('var b=document.createElement("div");b.textContent="Bandeau";document.querySelector(".menu-gates").prepend(b);')
            deplace = dict(menu32, chemin='header#app-header > div:nth-of-type(1) > div:nth-of-type(1)')
            pris = c.evaluer(robot.TROUVER % _json32.dumps(deplace)) and c.evaluer('window.__suiviCible.className')
            sans = c.evaluer(robot.TROUVER % _json32.dumps({k: v for k, v in deplace.items() if k != 'classe'})) and c.evaluer('window.__suiviCible.className')
            verifier('… et un menu déplacé (un bandeau avant lui) : retrouvé par sa classe ; sans elle (export d’avant), c’est l’ancienne place, comme avant',
                     pris == 'gates-trigger' and sans != 'gates-trigger', (pris, sans))

            # Sécurité : jamais deux « Submit », jamais deux téléchargements.
            def sur32(etapes, v='', telechargement=None):
                c.ouvrir('about:blank')
                dit = _io32.StringIO()
                try:
                    with _cl32.redirect_stdout(dit):
                        f = robot.rejouer(c, {'nom': 'SEE', 'depart': BASE32.replace('/gates/childneo', '/sur') + ('?v=' + v if v else ''),
                                              'etapes': etapes, 'fichier': '*.xlsx', 'telechargement_apres': telechargement or len(etapes)}, sortie32)
                    err = ''
                except robot.ErreurPilote as e:
                    f, err = None, str(e).split('\n')[0]
                return {'f': f and f.name, 'err': err, 'compte': c.evaluer('compte'), 'dit': dit.getvalue()[-800:]}
            SUBMIT = {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Submit', 'id': 'submit'}}
            EXPALL = {'faire': 'cliquer', 'cible': {'balise': 'button', 'titre': 'Export all', 'texte': '⇩', 'id': 'exp'}}
            XLS = {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'Exporter (.xls)'}}
            robot.DELAI_TROUVER = 40
            t0 = _t32.time()
            r = sur32([SUBMIT, EXPALL, XLS])
            verifier('« Submit » puis un voile de chargement ~20 s sur « Export all » : Submit cliqué UNE fois, le robot attend le voile, le fichier sort',
                     r['f'] == 'see.xlsx' and r['compte']['submit'] == 1 and r['compte']['exp'] == 1 and _t32.time() - t0 >= 18, (r, round(_t32.time() - t0)))
            r = sur32([{'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Afficher', 'id': 'aff'}}, EXPALL, XLS])
            verifier('« Afficher » (rien d’interdit dans son nom) puis un voile sur TOUTE la page 8 s : pas recliqué (lui aussi sous le voile), le fichier sort',
                     r['f'] == 'see.xlsx' and r['compte']['aff'] == 1, r)
            r = sur32([EXPALL, XLS, {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Fermer', 'id': 'fermer'}}], telechargement=2)
            verifier('le geste qui fait venir le fichier n’est jamais refait, même si la suite (« Fermer ») reste couverte 6 s',
                     r['f'] == 'see.xlsx' and r['compte']['xls'] == 1 and r['compte']['fermer'] == 1, r)
            robot.DELAI_TROUVER = 20

            # trouver : ce qu'on va cliquer reste caché — jamais un clic à l'aveugle ; le menu rouvert (une fois) ; sinon une erreur claire.
            c.ouvrir(BASE32.replace('/gates/childneo', '/sur'))
            c.evaluer('var v=document.createElement("div");v.className="voile";v.id="cache";document.body.appendChild(v);')
            AFF = {'balise': 'button', 'texte': 'Afficher', 'dessus': True}
            try:
                r_ = robot.trouver(c, AFF, delai=3)
                e_ = None
            except robot.ErreurPilote as e:
                r_, e_ = None, e
            verifier('toujours couvert au bout du délai : une erreur claire (« … est resté caché … »), plus de clic sur ce qui le cache',
                     r_ is None and e_ is not None and 'caché' in str(e_) and ('aveugle' in str(e_) or 'jamais au hasard' in str(e_)) and
                     getattr(e_, 'introuvable', True) is False, (r_, e_))
            appels = []

            def leve32():
                appels.append(1)
                c.evaluer('document.getElementById("cache").remove();document.getElementById("aff").style.cssText=""')
                return True
            leve32.menu = 'le menu qui ouvre « Afficher »'
            # Relecture : « Afficher » caché LUI-MÊME (la ligne d'un menu fermé : transparente, sans clic), plus sous un voile.
            c.evaluer('document.getElementById("cache").remove();document.getElementById("aff").style.cssText="opacity:0;pointer-events:none";'
                      'var v=document.createElement("div");v.id="cache";document.body.appendChild(v);')
            try:
                r_ = robot.trouver(c, AFF, delai=20, rouvrir=leve32)
            except Exception as e:  # noqa: BLE001
                r_ = 'erreur : %s' % e
            verifier('caché, geste d’avant recliquable : au bout de DELAI_ROUVRIR (pas 5 min) le menu est rouvert, une fois, puis le clic',
                     isinstance(r_, dict) and not r_.get('attendre') and appels == [1], (r_, appels))
            c.evaluer('document.getElementById("aff").style.cssText="opacity:0;pointer-events:none"')
            rate32 = lambda: False   # noqa: E731
            rate32.menu = 'le menu qui ouvre « Afficher »'
            try:
                robot.trouver(c, AFF, delai=30, rouvrir=rate32)
                e_ = None
            except Exception as e:  # noqa: BLE001
                e_ = e
            verifier('… rien n’y fait : il le dit tout de suite, en nommant l’étape du menu',
                     e_ is not None and 'le menu qui ouvre « afficher » ne s\'est pas ouvert' in str(e_).lower(), e_)
            c.evaluer('document.getElementById("aff").style.cssText=""')

            # Une page vraiment neuve à chaque export, même quand l'adresse ne change que par son « #… ».
            c.ouvrir(BASE32 + '#/mk2')
            c.evaluer('window.__ici = 1')
            robot.preparer_rejeu(c)
            neuve1 = neuve2 = None
            with _cl32.suppress(AttributeError):              # (un robot d'avant le débrief 32 n'a pas page_neuve)
                robot.page_neuve(c, BASE32 + '#/accueil')
                neuve1 = c.evaluer('[window.__ici === undefined, location.hash, !!window.__suiviFwdGuette, !!window.__suiviReseau, !!window.__suiviFocus]')
                c.evaluer('window.__ici = 1')
                robot.page_neuve(c, BASE32 + '#/accueil')
                neuve2 = c.evaluer('[window.__ici === undefined, location.hash]')
            verifier('page_neuve : « #/mk2 » → « #/accueil » puis la même adresse : rechargée les deux fois, scripts du robot posés (guetteur, requêtes, focus)',
                     neuve1 == [True, '#/accueil', True, True, True] and neuve2 == [True, '#/accueil'], (neuve1, neuve2))
            recliquable32 = getattr(robot, 'recliquable', lambda g: None)
            verifier('les clics jamais refaits : Submit, Valider, OK, Rechercher, Enregistrer, Supprimer, Log out, un bouton type=submit ; '
                     'refaits : le menu sans nom, « Données MK2 », « Export all », « Exporter »',
                     getattr(robot, 'recliquable', None) is not None and not any(recliquable32({'faire': 'cliquer', 'cible': c_}) for c_ in (
                         {'texte': 'Submit'}, {'texte': 'Valider'}, {'texte': 'OK'}, {'label': 'Rechercher'}, {'texte': 'Enregistrer le document'},
                         {'titre': 'Supprimer'}, {'texte': 'Log out'}, {'texte': 'Déconnexion'}, {'type': 'submit', 'texte': 'Afficher'})) and
                     all(recliquable32({'faire': 'cliquer', 'cible': c_}) for c_ in (
                         menu32, {'texte': 'Données MK2'}, {'bulle': 'Export all'}, {'texte': 'Exporter'}, {'texte': 'HDK AA (SUPER PUMA)'})))
    finally:
        site32.shutdown()
        for k, v in avant32.items():
            if v is not None:
                setattr(robot, k, v)
# ---- fin débrief 32

print('\n— Débrief 32, relecture : listes qui défilent, menus cachés autrement, clics jamais refaits, messages —')
# Ce que les trois relecteurs ont trouvé, refait ici en vrai Chrome : une ligne au bas d'une liste qui a sa
# propre barre de défilement ; la ligne d'un menu fermé autrement que transparente (display:none, groupe
# replié, rangée hors de l'écran, dans un cadre) ; « Exporter (.xls) » pris pour « Exporter » ; un menu sans
# nom dans un cadre ; jamais deux fois une case à cocher, « Page suivante », « Afficher », « Se connecter »,
# une loupe, ce qui fait venir le fichier, ni un clic qui charge sa page en retard ; une page qui demande
# « Quitter la page ? » ; GATES avec son menu en display:none, ou une requête en fond toutes les 3 s.
rq = robot.recliquable
verifier('jamais recliqués : une connexion, « Page suivante », une flèche, ce qui fait venir le fichier, une case, une poubelle',
         not any(rq({'faire': 'cliquer', 'cible': c_}) for c_ in (
             {'texte': 'Se connecter'}, {'texte': 'Sign in', 'role': 'button'}, {'label': 'Log in'}, {'texte': 'Connexion'}, {'texte': 'Sign On'},
             {'texte': 'Page suivante'}, {'texte': 'Next'}, {'texte': '›'}, {'texte': 'XLSX'}, {'texte': 'Exporter (.xls)'}, {'texte': 'Télécharger'},
             {'icone': 'fa-trash'}, {'icone': 'fa-sign-out'}, {'balise': 'input', 'type': 'checkbox'}, {'role': 'switch'}, {'classe': 'btn-save'})) and
         all(rq({'faire': 'cliquer', 'cible': c_}) for c_ in (
             {'texte': 'Export all'}, {'texte': 'Exporter'}, {'texte': 'Données MK2'},
             {'chemin': 'header > div', 'contenu': 'Données MK1 Données MK2 Import Aide'})))
mm = robot.message_menu('le menu qui ouvre « Données MK2 »', '« Données MK2 »')
verifier('l’erreur finale dit quoi faire : ouvrir le menu soi-même, relancer « 3 - Essayer » s’il s’ouvre, réapprendre sinon',
         mm.startswith('Le menu qui ouvre « Données MK2 » ne s\'est pas ouvert, même après plusieurs essais') and
         'relancez « 3 - Essayer »' in mm and 'Sinon, refaites « 2 - Apprendre un export »' in mm and 'aveugle' not in mm, mm)
verifier('un bouton qui n’a pas l’air d’un menu se dit « le bouton « Afficher » », un champ par son nom — jamais « le menu le champ »',
         robot.nom_du_menu({'texte': 'Afficher'}, {'texte': 'Export all'}, False)[0] == 'le bouton « Afficher »' and
         robot.nom_du_menu({'balise': 'input', 'etiquette': 'PSN'}, {'texte': 'Submit'}, True) == ('le champ « PSN »', 'le champ « PSN »', False) and
         robot.nom_du_menu({'chemin': 'header > div'}, {'texte': 'Données MK2'}, True)[0] == 'le menu qui ouvre « Données MK2 »')
verifier('« (le menu qui ouvre … ) » seulement suivi d’un clic ; avant un champ : « (ce qui fait paraître …) »',
         robot.dire_geste({'faire': 'cliquer', 'cible': {'chemin': 'div'}}, {'faire': 'cliquer', 'cible': {'texte': 'Données MK2'}}) ==
         '(le menu qui ouvre « Données MK2 »)' and
         robot.dire_geste({'faire': 'cliquer', 'cible': {'chemin': 'div'}}, {'faire': 'remplir', 'cible': {'balise': 'input', 'etiquette': 'PSN'}}) ==
         '(ce qui fait paraître le champ « PSN »)')
verifier('l’attente dit « caché derrière autre chose » ou « pas encore affiché », plus « couvert »',
         robot.DIT_ATTENTE.get('couvert') == 'caché derrière autre chose' and robot.DIT_ATTENTE.get('caché') == 'pas encore affiché')
if exe:
    import contextlib as _cl32r
    import http.server as _hs32r
    import io as _io32r
    import json as _json32r
    import threading as _th32r
    import time as _t32r
    LIGNES32R = ''.join('<div class="t" style="height:30px">Tranche %d</div>' % k for k in range(1, 21))
    SONDE32R = ('<!doctype html><meta charset="utf-8"><body style="margin:0;font:14px sans-serif">'
                '<div id="liste" style="height:100px;overflow:auto;width:200px;border:1px solid #888">' + LIGNES32R + '</div>'
                '<nav style="width:200px;background:#eee;padding:4px"><div><b>Groupe</b><div style="height:0;overflow:hidden">'
                '<a href="#" onclick="return false">Ligne accordéon</a></div></div><div><b>Autre groupe</b></div></nav>'
                '<div style="position:absolute;left:-9999px;top:300px"><a>Ligne hors écran</a></div>'
                '<div style="display:none"><a>Ligne non affichée</a></div>'
                '<a id="ouverte">Ligne ouverte</a> <button type="button" id="exporter">Exporter</button><br>'
                '<iframe id="cadre" src="/cadre" style="width:300px;height:120px;border:0"></iframe>')
    CADRE32R = ('<!doctype html><meta charset="utf-8"><body style="margin:0"><header id="h"><div>'
                '<div class="x" style="width:30px;height:30px;background:#36c"></div></div></header>'
                '<div style="opacity:0;pointer-events:none"><a>Ligne du cadre</a></div>')
    # Un voile qui ne couvre que le BAS de la page (sans requête comptée) après chaque bouton du haut.
    SURE32R = r'''<!doctype html><meta charset="utf-8"><style>#bas{position:relative;margin-top:30px;padding:8px}
.voile{position:absolute;left:0;top:0;right:0;bottom:0;background:rgba(0,0,0,.25);z-index:20}#menu li{cursor:pointer}</style>
<div id="haut"><input type="checkbox" id="case"> <button id="suivant">Page suivante</button> <button id="aff">Afficher</button>
<button type="button" id="cnx">Se connecter</button> <button id="loupe"><i class="fa fa-search"></i></button><ul id="menu"></ul></div>
<div id="bas"><button id="exp" title="Export all">⇩</button> <button id="fermer">Fermer</button></div>
<script>
var compte = {case: 0, suivant: 0, aff: 0, cnx: 0, loupe: 0, exp: 0, xls: 0, fermer: 0};
var voile = function (ms) { var v = document.createElement('div'); v.className = 'voile'; document.getElementById('bas').appendChild(v); setTimeout(function () { v.remove(); }, ms); };
['case', 'suivant', 'aff', 'cnx', 'loupe'].forEach(function (k) { document.getElementById(k).addEventListener('click', function () { compte[k]++; voile(12000); }); });
document.getElementById('exp').onclick = function () { compte.exp++; document.getElementById('menu').innerHTML = '<li id="xls">XLSX</li>'; };
document.getElementById('menu').onclick = function (e) { if (e.target.id !== 'xls') return; compte.xls++;
  var a = document.createElement('a'); a.href = 'data:application/octet-stream;base64,UEsDBA=='; a.download = 'see.xlsx'; document.body.appendChild(a); a.click(); voile(12000); };
document.getElementById('fermer').onclick = function () { compte.fermer++; };
</script>'''
    # « Rapports » charge sa page 6 s après le clic (par script) ; la nouvelle page porte le même lien.
    NAV32R = ('<!doctype html><meta charset="utf-8"><a id="rap" href="#" onclick="setTimeout(function(){location.href=\'/nav?\'+Date.now();},6000);'
              'return false;">Rapports</a>')
    BU32R = ('<!doctype html><meta charset="utf-8"><button id="b">x</button><script>'
             'addEventListener("beforeunload",function(e){e.preventDefault();e.returnValue="";});</script>')
    vus32r = {'nav': 0}

    class Pages32r(_hs32r.BaseHTTPRequestHandler):
        def do_GET(self):
            p = self.path.split('?')[0]
            if p == '/lent':
                _t32r.sleep(float((self.path.split('s=') + ['1'])[1].split('&')[0]) if 's=' in self.path else 1.0)
                corps = 'ok'
            elif p == '/nav':
                vus32r['nav'] += 1
                corps = NAV32R
            else:
                corps = {'/sonde': SONDE32R, '/cadre': CADRE32R, '/sur2': SURE32R, '/bu': BU32R}.get(p, GATES32)
            corps = corps.encode('utf-8')
            with _cl32r.suppress(OSError):            # une requête que Chrome abandonne (la page quittée)
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                self.wfile.write(corps)

        def log_message(self, *a):
            pass
    site32r = _hs32r.ThreadingHTTPServer(('127.0.0.1', 0), Pages32r)
    _th32r.Thread(target=site32r.serve_forever, daemon=True).start()
    ICI32R = 'http://127.0.0.1:%d' % site32r.server_port
    BASE32 = ICI32R + '/gates/childneo'            # apprendre32 et deux_contrats32 (plus haut) servent cette page-ci
    avant32r = {k: getattr(robot, k, None) for k in NOMS32}
    robot.DELAI_TROUVER, robot.DELAI_SUITE, robot.DELAI_CACHE = 20, 4, 3
    robot.DELAI_ROUVRIR, robot.DELAI_REOUVERTURE, robot.DELAI_PAGE_NEUVE = 4, 6, 30

    def etat32r(c, texte):
        return robot.etat_cible(c, {'balise': 'a', 'texte': texte, 'dessus': True})

    try:
        with Chrome(port=9482, lancer=True, profil=tempfile.mkdtemp(prefix='robot-d32r-'), sans_fenetre=True, delai=30, options=options32,
                    telechargements=str(R / 'telechargements')) as c:
            c.ouvrir(ICI32R + '/sonde')
            _t32r.sleep(0.5)
            t18 = c.evaluer(robot.TROUVER % _json32r.dumps({'texte': 'Tranche 18', 'dessus': True}))
            sous = t18 and c.evaluer('(function(){var h=document.elementFromPoint(%s,%s);return [h&&h.textContent, document.getElementById("liste").scrollTop, scrollY];})()'
                                     % (t18['x'], t18['y']))
            verifier('une ligne au bas d’une liste qui a sa propre barre de défilement : la liste défile (pas la page), le clic tombe sur la ligne',
                     bool(t18) and not t18.get('attendre') and sous[0] == 'Tranche 18' and sous[1] > 0 and sous[2] == 0, (t18, sous))
            etats = {t: etat32r(c, t) for t in ('Ligne ouverte', 'Ligne accordéon', 'Ligne hors écran', 'Ligne non affichée', 'Ligne du cadre')}
            verifier('la ligne d’un menu fermé est « cachée », quelle que soit la façon : groupe replié, rangée hors de l’écran, non affichée, '
                     'transparente dans un cadre ; une ligne ouverte est « là »',
                     etats == {'Ligne ouverte': 'là', 'Ligne accordéon': 'caché', 'Ligne hors écran': 'caché', 'Ligne non affichée': 'caché',
                               'Ligne du cadre': 'caché'}, etats)
            pris = c.evaluer(robot.TROUVER % _json32r.dumps({'balise': 'button', 'texte': 'Exporter (.xls)', 'type': 'button', 'dessus': True}))
            verifier('« Exporter (.xls) » (pas encore là) n’est pas pris pour le bouton « Exporter » : le début du texte ne suffit pas', pris is None, pris)
            dans = c.evaluer(robot.TROUVER % _json32r.dumps({'balise': 'div', 'chemin': 'header#h > div:nth-of-type(1) > div:nth-of-type(1)', 'dessus': True}))
            verifier('un élément sans nom dans un cadre, décrit par son seul chemin : retrouvé (au bon endroit de la page)',
                     bool(dans) and not dans.get('attendre') and dans['y'] > 100, dans)
            c.evaluer(robot.RESEAU_JS)
            c.evaluer('fetch("/lent?s=5"), 1')            # (sans attendre la réponse)
            dit = _io32r.StringIO()
            with _cl32r.redirect_stdout(dit):
                robot.attendre_calme(c, 8, 'la page se charge')
            verifier('au départ d’un export, l’attente dit « la page se charge », pas « la page calcule »',
                     '(la page se charge' in dit.getvalue() and 'calcule' not in dit.getvalue(), dit.getvalue())

            # trouver : la ligne d'un menu refermé en display:none, ou retiré de la page — rouvert au bout de DELAI_ROUVRIR.
            appels = []

            def remet32r():
                appels.append(1)
                c.evaluer('document.querySelector("#ligne").parentNode.style.display=""')
                return True
            remet32r.menu, remet32r.court = 'le menu qui ouvre « Ligne cachée »', 'le menu'
            c.evaluer('document.body.insertAdjacentHTML("beforeend","<div style=\\"display:none\\"><a id=\\"ligne\\">Ligne cachée</a></div>")')
            dit = _io32r.StringIO()
            t0 = _t32r.time()
            with _cl32r.redirect_stdout(dit):
                r_ = robot.trouver(c, {'balise': 'a', 'texte': 'Ligne cachée', 'dessus': True}, delai=20, rouvrir=remet32r)
            verifier('menu refermé en display:none entre la vérification et le clic : rouvert au bout de DELAI_ROUVRIR, et dit '
                     '« (… est caché : le menu s’est refermé, le robot le rouvre dans 4 s) »',
                     isinstance(r_, dict) and not r_.get('attendre') and appels == [1] and _t32r.time() - t0 < 10 and
                     'le robot le rouvre dans 4 s' in dit.getvalue(), (r_, appels, dit.getvalue()))
            appels.clear()

            def reajoute32r():
                appels.append(1)
                c.evaluer('document.body.insertAdjacentHTML("beforeend","<a id=\\"ligne2\\">Ligne retirée</a>")')
                return True
            reajoute32r.menu, reajoute32r.court, reajoute32r.absent = 'le menu qui ouvre « Ligne retirée »', 'le menu', True
            with _cl32r.redirect_stdout(_io32r.StringIO()):
                r_ = robot.trouver(c, {'balise': 'a', 'texte': 'Ligne retirée', 'dessus': True}, delai=20, rouvrir=reajoute32r)
            verifier('… un menu retiré de la page quand il se ferme (Material) : rouvert aussi, une fois',
                     isinstance(r_, dict) and appels == [1], (r_, appels))

            # Jamais deux fois : une case, « Page suivante », « Afficher », « Se connecter », une loupe — le bas de la page sous un voile 12 s.
            robot.DELAI_TROUVER = 40

            def sur32r(etapes, telechargement=None):
                c.ouvrir('about:blank')
                dit = _io32r.StringIO()
                try:
                    with _cl32r.redirect_stdout(dit):
                        f = robot.rejouer(c, {'nom': 'SEE', 'depart': ICI32R + '/sur2', 'etapes': etapes, 'fichier': '*.xlsx',
                                              'telechargement_apres': telechargement or len(etapes)}, sortie32)
                    err = ''
                except robot.ErreurPilote as e:
                    f, err = None, str(e).split('\n')[0]
                return {'f': f and f.name, 'err': err, 'compte': c.evaluer('compte'), 'coche': c.evaluer('document.getElementById("case").checked'),
                        'dit': dit.getvalue()[-600:]}
            EXP32R = {'faire': 'cliquer', 'cible': {'balise': 'button', 'titre': 'Export all', 'texte': '⇩', 'id': 'exp'}}
            XLS32R = {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'XLSX', 'id': 'xls'}}
            for k, cible_, quoi in (('case', {'balise': 'input', 'type': 'checkbox', 'id': 'case'}, 'une case à cocher (l’export sortirait décoché)'),
                                    ('suivant', {'balise': 'button', 'texte': 'Page suivante', 'id': 'suivant'}, '« Page suivante » (la mauvaise page)'),
                                    ('aff', {'balise': 'button', 'texte': 'Afficher', 'id': 'aff'}, '« Afficher » (un calcul relancé)'),
                                    ('cnx', {'balise': 'button', 'type': 'button', 'texte': 'Se connecter', 'id': 'cnx'}, '« Se connecter » (le compte verrouillé)'),
                                    ('loupe', {'balise': 'button', 'icone': 'fa-search', 'id': 'loupe'}, 'une loupe sans nom')):
                r = sur32r([{'faire': 'cliquer', 'cible': cible_}, EXP32R, XLS32R])
                verifier('voile sur le bas de la page 12 s après %s : cliqué UNE fois, le robot attend, le fichier sort' % quoi,
                         r['f'] == 'see.xlsx' and r['compte'][k] == 1 and r['compte']['exp'] == 1 and (k != 'case' or r['coche'] is True), r)
            r = sur32r([EXP32R, XLS32R, {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Fermer', 'id': 'fermer'}}], telechargement=3)
            verifier('le fichier noté après « Fermer » (appris ainsi) : « XLSX » n’est jamais refait, même si « Fermer » reste sous un voile 12 s',
                     r['f'] == 'see.xlsx' and r['compte']['xls'] == 1 and r['compte']['fermer'] == 1, r)
            robot.DELAI_TROUVER = 20
            c.ouvrir('about:blank')
            vus32r['nav'] = 0
            try:
                with _cl32r.redirect_stdout(_io32r.StringIO()):
                    robot.rejouer(c, {'nom': 'X', 'depart': ICI32R + '/nav', 'etapes': [
                        {'faire': 'cliquer', 'cible': {'balise': 'a', 'texte': 'Rapports', 'id': 'rap'}},
                        {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'Rapport mensuel'}}], 'fichier': '*.xlsx', 'telechargement_apres': 2}, sortie32)
            except robot.ErreurPilote:
                pass
            verifier('un clic qui charge sa page 6 s plus tard (par script) : pas recliqué sur la nouvelle page (la page servie 2 fois, pas plus)',
                     vus32r['nav'] == 2, vus32r)

            # GATES : le menu fermé en display:none ; une requête toutes les 3 s — le 1er clic sur le menu perdu au 2e contrat.
            scen32r = apprendre32(c)
            for v, quoi in (('hd', 'menu fermé en display:none'), ('qd', 'une petite requête toutes les 3 s (la page jamais tout à fait calme)')):
                r = deux_contrats32(c, scen32r, v)
                verifier('GATES, %s, le 1er clic sur le menu perdu au 2e contrat : le robot rouvre le menu vite, le dit sous la ligne « 1/6 », VRK sort' % quoi,
                         r['sortis'] == ['gates-hdk.xlsx', 'gates-vrk.xlsx'] and not r['err'] and 'perdu;clic menu;' in r['page'] and
                         r['dit'].rindex('  1/6 cliquer (le menu qui ouvre « Données MK2 »)') < r['dit'].rindex('(« Données MK2 » ne s\'est pas montré') and
                         not planté32(r['dit']) and r['duree'] < 90, resume32(r))

            # « Quitter la page ? » : le départ ne diffère que par son « #… » (détour par une page blanche) — l'onglet ne se fige pas.
            c.ouvrir(ICI32R + '/bu#/mk2')
            p = centre32(c, 'document.getElementById("b")')
            robot.souris(c, p['x'], p['y'])
            c.evaluer('window.__ici = 1')
            try:
                robot.page_neuve(c, ICI32R + '/bu#/accueil')
                neuve = c.evaluer('[window.__ici === undefined, location.hash]', delai=5)
            except robot.ErreurPilote as e:
                neuve = 'erreur : %s' % e
            verifier('une page qui demande « Quitter la page ? » : rechargée quand même, l’onglet du robot répond toujours',
                     neuve == [True, '#/accueil'], neuve)
    finally:
        site32r.shutdown()
        for k, v in avant32r.items():
            if v is not None:
                setattr(robot, k, v)
# ---- fin débrief 32, relecture

print('\n— Débrief 31 : la fenêtre du robot garde le focus quand on clique ailleurs (vrai Chrome à l’écran, sous Xvfb) —')
XVFB = shutil.which('Xvfb')
if not exe:
    print('  (pas de Chrome sur ce poste : partie sautée)')
elif not XVFB:
    print('  (pas d’écran virtuel Xvfb sur ce poste : partie sautée — installez le paquet xvfb pour la jouer)')
else:
    import json as _json
    import subprocess as _sp
    import time as _time
    import urllib.parse as _up
    from piloter_chrome import Chrome as _Chrome, _Canal as _CanalF

    def ecran_virtuel():
        """Un écran X virtuel, rien qu'à cette batterie : (processus, ':N'), ou (None, '')."""
        for n in range(91, 140):
            if os.path.exists('/tmp/.X11-unix/X%d' % n) or os.path.exists('/tmp/.X%d-lock' % n):
                continue
            p = _sp.Popen([XVFB, ':%d' % n, '-screen', '0', '1280x1024x24', '-nolisten', 'tcp'], stdout=_sp.DEVNULL, stderr=_sp.DEVNULL)
            for _ in range(60):
                if os.path.exists('/tmp/.X11-unix/X%d' % n):
                    return p, ':%d' % n
                if p.poll() is not None:
                    break
                _time.sleep(0.1)
            if p.poll() is None:
                p.terminate()
                p.wait(5)
        return None, ''

    xvfb, ecran = ecran_virtuel()
    if not xvfb:
        print('  (l’écran virtuel Xvfb ne démarre pas : partie sautée)')
    else:
        page_de = lambda html: 'data:text/html;charset=utf-8,' + _up.quote('<!doctype html><meta charset="utf-8"><body>' + html)   # noqa: E731
        TELE = ('var a=document.createElement("a");a.href="data:application/octet-stream;base64,UEsDBA==";a.download="export.xlsx";'
                'document.body.appendChild(a);a.click();')
        # GATES (CHILDNéo) : « Ouvrir données MK2 » ignore un clic sans le focus ; son panneau se ferme quand la fenêtre perd le focus.
        PAGE_GATES = ('<button id="mk2">Ouvrir données MK2</button><div id="panneau" hidden><button id="xlsx">XLSX</button></div><div id="res"></div>'
                      '<script>var p=document.getElementById("panneau"),log=[];'
                      'window.addEventListener("blur",function(){p.hidden=true;log.push("blur");});'
                      'document.getElementById("mk2").onclick=function(){if(!document.hasFocus()){log.push("clic ignoré");return;}p.hidden=false;};'
                      'document.getElementById("xlsx").onclick=function(){document.getElementById("res").textContent="export XLSX";' + TELE + '};</script>')
        GESTES_GATES = [{'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Ouvrir données MK2', 'id': 'mk2'}},
                        {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'XLSX', 'id': 'xlsx'}}]
        # SEE : le champ PSN et sa liste de suggestions (fermée quand le champ perd le focus), « Submit » (ignoré sans le focus),
        # le calcul, puis « Export all » (une icône) et son menu (fermé quand la fenêtre perd le focus ou se cache).
        PAGE_SEE = ('<div class="ligne"><span>PSN</span><input id="psn"></div><ul id="sugg"></ul><button id="submit">Submit</button><div id="zone"></div><div id="res"></div>'
                    '<script>var log=[],psn=document.getElementById("psn"),sugg=document.getElementById("sugg"),puce="";'
                    'psn.addEventListener("input",function(){sugg.innerHTML=psn.value?"<li>"+psn.value+"</li>":"";});'
                    'psn.addEventListener("blur",function(){log.push("blur champ");sugg.innerHTML="";});'
                    'sugg.addEventListener("mousedown",function(e){e.preventDefault();});'
                    'sugg.addEventListener("click",function(e){if(e.target.tagName==="LI"){puce=e.target.textContent;sugg.innerHTML="";}});'
                    'var fermer=function(){var m=document.getElementById("liste");if(m)m.hidden=true;};'
                    'window.addEventListener("blur",function(){log.push("blur");fermer();});'
                    'document.addEventListener("visibilitychange",function(){log.push("cachée");if(document.hidden)fermer();});'
                    'document.getElementById("submit").onclick=function(){if(!document.hasFocus()){log.push("submit ignoré");return;}'
                    ' setTimeout(function(){var z=document.getElementById("zone");'
                    '  z.innerHTML=\'<button class="exp" mattooltip="Export all"><svg data-icon="file-export" width="16" height="16"><path d="M0 0h16v16H0z"/></svg></button>'
                    '<ul id="liste" hidden><li>CSV</li><li>XLSX</li></ul>\';'
                    '  var m=document.getElementById("liste");z.querySelector(".exp").onclick=function(){m.hidden=false;};'
                    '  m.onclick=function(e){if(e.target.tagName==="LI"){document.getElementById("res").textContent="export "+e.target.textContent+" pour "+puce;' + TELE + '}};'
                    ' },1500);};</script>')
        GESTES_SEE = [{'faire': 'remplir', 'cible': {'balise': 'input', 'etiquette': 'PSN'}, 'texte': '4530'},
                      {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': '4530'}},
                      {'faire': 'cliquer', 'cible': {'balise': 'button', 'texte': 'Submit'}},
                      {'faire': 'cliquer', 'cible': {'balise': 'button', 'bulle': 'Export all', 'icone': 'file-export'}},
                      {'faire': 'cliquer', 'cible': {'balise': 'li', 'texte': 'XLSX'}}]
        avant_focus = {n: getattr(robot, n) for n in ('PORT', 'FOCUS_EMULE', 'FOCUS_SCRIPT', 'DELAI_TROUVER', 'DELAI_SUITE', 'faire_geste')}
        vieil_ecran, vieilles_options = os.environ.get('DISPLAY'), os.environ.get('SUIVI_FWD_OPTIONS_CHROME')
        os.environ['DISPLAY'] = ecran
        os.environ['SUIVI_FWD_OPTIONS_CHROME'] = _json.dumps(['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else [])
        robot.PORT, robot.DELAI_TROUVER, robot.DELAI_SUITE = 9471, 10, 4
        options_autre = (['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []) + ['--window-size=1280,1024', '--window-position=0,0']
        try:
            # La fenêtre du robot, à l'écran (ses options d'aujourd'hui), et « une autre application » : un autre navigateur, un autre client X.
            with robot.chrome(True, grand=False) as fenetre_robot, \
                    _Chrome(port=9472, lancer=True, profil=tempfile.mkdtemp(prefix='robot-autre-'), delai=30, options=options_autre) as autre:
                autre.ouvrir('data:text/html;charset=utf-8,<h1>Une autre application</h1>')
                navig = _CanalF(_json.loads(robot.SANS_PROXY.open('http://127.0.0.1:%d/json/version' % robot.PORT, timeout=10).read())['webSocketDebuggerUrl'], 20)
                numero = [0]

                def cdp(methode, **p):
                    numero[0] += 1
                    navig.envoyer(_json.dumps({'id': numero[0], 'method': methode, 'params': p}))
                    while True:
                        m = _json.loads(navig.recevoir())
                        if m.get('id') == numero[0]:
                            return m.get('result') or {}

                def par_l_autre_application():
                    autre.envoyer('Page.bringToFront')
                    _time.sleep(1.0)
                    return autre.evaluer('document.hasFocus()') is True        # c'est elle qui a le focus, pour de vrai

                fenetres = []

                def par_une_autre_fenetre():
                    fenetres.append(cdp('Target.createTarget', url='about:blank', newWindow=True)['targetId'])
                    cdp('Target.activateTarget', targetId=fenetres[-1])
                    _time.sleep(1.0)
                    return True

                def essai(page, gestes, voler_apres, voleur, mode, nom, voler_avant=lambda g: False):
                    """Le robot refait l'export ; on lui vole le focus juste après (ou juste avant) les gestes choisis."""
                    robot.FOCUS_EMULE, robot.FOCUS_SCRIPT = mode in ('tout', 'chrome'), mode in ('tout', 'script')
                    t = _Chrome(port=robot.PORT, telechargements=str(R / 'telechargements'), delai=30)
                    t.demarrer()
                    voles, vu_page = [], []

                    def geste(c, g, suivant=None, **plus):
                        if voler_avant(g):
                            voles.append(voleur())
                            # Ce que la page croit, juste après qu'on a cliqué ailleurs (avant le clic du robot).
                            vu_page.append(c.evaluer('[document.hasFocus(), document.visibilityState, document.hidden]'))
                        r = avant_focus['faire_geste'](c, g, suivant, **plus)
                        if voler_apres(g):
                            voles.append(voleur())
                        return r
                    try:
                        t.envoyer('Page.bringToFront')
                        _time.sleep(0.8)
                        depart = t.evaluer('document.hasFocus()')                # le robot a le focus au départ
                        robot.faire_geste = geste
                        try:
                            f, res = robot.rejouer(t, {'nom': nom, 'depart': page_de(page), 'etapes': gestes, 'fichier': '*.xlsx',
                                                       'telechargement_apres': len(gestes)}, tempfile.mkdtemp(prefix='robot-focus-')), 'ok'
                        except robot.ErreurPilote as err:
                            f, res = None, 'erreur : %s' % str(err).split('\n')[0]
                        return {'depart': depart, 'voles': voles, 'vu': vu_page, 'res': res, 'f': f, 'log': t.evaluer('log.join(",")'),
                                'page': t.evaluer('document.getElementById("res").textContent')}
                    finally:
                        robot.faire_geste = avant_focus['faire_geste']
                        t.fermer()
                        while fenetres:
                            with contextlib.suppress(Exception):
                                cdp('Target.closeTarget', targetId=fenetres.pop())

                apres_mk2 = lambda g: (g.get('cible') or {}).get('texte') == 'Ouvrir données MK2'   # noqa: E731
                apres_psn = lambda g: g['faire'] == 'remplir' or (g.get('cible') or {}).get('bulle') == 'Export all'   # noqa: E731
                r0 = essai(PAGE_GATES, GESTES_GATES, apres_mk2, par_l_autre_application, 'rien', 'GATES HDK')
                # (débrief 32, relecture : la ligne du menu fermé, non affichée, se dit désormais « cachée »)
                rate0 = ('erreur : Je ne retrouve plus « XLSX »', 'erreur : « XLSX » est resté caché')
                verifier('GATES, sans la parade : on clique dans une autre application entre « Ouvrir données MK2 » et « XLSX » — le menu se ferme, l’export rate',
                         r0['depart'] is True and r0['voles'] == [True] and r0['res'].startswith(rate0) and 'blur' in r0['log'], r0)
                r1 = essai(PAGE_GATES, GESTES_GATES, apres_mk2, par_l_autre_application, 'tout', 'GATES HDK')
                verifier('… avec la parade (le robot d’aujourd’hui) : le menu reste ouvert, « XLSX », le fichier arrive — la page n’a rien vu',
                         r1['depart'] is True and r1['voles'] == [True] and r1['res'] == 'ok' and r1['f'] and r1['f'].exists() and
                         r1['page'] == 'export XLSX' and r1['log'] == '', r1)
                r2 = essai(PAGE_GATES, GESTES_GATES, apres_mk2, par_l_autre_application, 'chrome', 'GATES HDK')
                r3 = essai(PAGE_GATES, GESTES_GATES, apres_mk2, par_l_autre_application, 'script', 'GATES HDK')
                verifier('… chacune des deux défenses suffit seule : Chrome qui garde le focus de la page, puis le script posé dans la page',
                         r2['res'] == 'ok' and r2['page'] == 'export XLSX' and r3['res'] == 'ok' and r3['page'] == 'export XLSX' and r2['voles'] == r3['voles'] == [True],
                         (r2, r3))
                # « Ouvrir données MK2, des fois ça marche, des fois non » : on a cliqué ailleurs AVANT son clic.
                # Ce que voit alors un bouton qui ne répond qu'avec le focus (document.hasFocus()), avant que le
                # robot clique : sans la parade, « pas le focus, page cachée ? » ; avec, toujours le focus.
                # (Sous Xvfb, sans gestionnaire de fenêtres, le clic du robot rend lui-même le focus à sa fenêtre :
                # c'est donc ce que croit la page juste avant le clic qui est vérifié ici.)
                jamais = lambda g: False   # noqa: E731
                r8 = essai(PAGE_GATES, GESTES_GATES, jamais, par_l_autre_application, 'rien', 'GATES HDK', voler_avant=apres_mk2)
                r9 = essai(PAGE_GATES, GESTES_GATES, jamais, par_l_autre_application, 'tout', 'GATES HDK', voler_avant=apres_mk2)
                verifier('GATES, on clique ailleurs juste AVANT « Ouvrir données MK2 » : sans la parade, la page n’a plus le focus (document.hasFocus() faux, « blur ») ; '
                         'avec, elle l’a toujours, rien ne lui est dit, et l’export sort',
                         r8['voles'] == [True] and r8['vu'][0][0] is False and 'blur' in r8['log'] and
                         r9['voles'] == [True] and r9['vu'] == [[True, 'visible', False]] and r9['res'] == 'ok' and r9['page'] == 'export XLSX' and
                         r9['log'] == '', (r8, r9))
                r4 = essai(PAGE_SEE, GESTES_SEE, apres_psn, par_l_autre_application, 'rien', 'SEE')
                verifier('SEE, sans la parade : on clique ailleurs après avoir tapé le PSN — sa liste se ferme, l’export rate',
                         r4['depart'] is True and r4['voles'][:1] == [True] and r4['res'].startswith('erreur : Je ne retrouve plus « 4530 »') and
                         'blur champ,blur' in r4['log'], r4)
                r5 = essai(PAGE_SEE, GESTES_SEE, apres_psn, par_l_autre_application, 'tout', 'SEE')
                verifier('… avec la parade : PSN, Submit (qui exige le focus), Export all, puis ailleurs encore — « export XLSX pour 4530 »',
                         r5['depart'] is True and r5['voles'] == [True, True] and r5['res'] == 'ok' and r5['page'] == 'export XLSX pour 4530', r5)
                verifier('… et le « blur » que le robot provoque lui-même (son clic sur Submit quitte le champ PSN) passe toujours, lui seul',
                         r5['log'] == 'blur champ', r5['log'])
                r6 = essai(PAGE_SEE, GESTES_SEE, apres_psn, par_une_autre_fenetre, 'rien', 'SEE')
                r7 = essai(PAGE_SEE, GESTES_SEE, apres_psn, par_une_autre_fenetre, 'tout', 'SEE')
                verifier('une autre fenêtre du navigateur du robot passe devant (Target.createTarget + activateTarget) : sans la parade l’export rate, avec il sort',
                         r6['res'].startswith('erreur : Je ne retrouve plus « 4530 »') and 'blur' in r6['log'] and
                         r7['res'] == 'ok' and r7['page'] == 'export XLSX pour 4530' and r7['log'] == 'blur champ', (r6, r7))
                navig.fermer()
        finally:
            for n, v in avant_focus.items():
                setattr(robot, n, v)
            for var, v in (('DISPLAY', vieil_ecran), ('SUIVI_FWD_OPTIONS_CHROME', vieilles_options)):
                if v is None:
                    os.environ.pop(var, None)
                else:
                    os.environ[var] = v
            xvfb.terminate()
            xvfb.wait(10)

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
        # Débrief 31 : le compte rendu dit la livraison de la fenêtre que le robot a vue (data-livraison du pont).
        c.evaluer('document.getElementById("pont-robot").setAttribute("data-livraison", "cd9cd8e"); window.__recu = null')
        verifier('… une fenêtre qui dit sa livraison (data-livraison) : le compte rendu la porte (« livraison »), le reste tel quel',
                 robot.envoyer_rapport(c, ctx, rapport, delai=15) is True and c.evaluer('window.__recu') == dict(rapport, livraison='cd9cd8e') and
                 'livraison' not in rapport, c.evaluer('window.__recu'))
        c.evaluer('document.getElementById("pont-robot").removeAttribute("data-livraison")')
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
            # Débrief 31 : ce que le robot dit avoir lu — l'adresse, la version de la fenêtre (data-livraison du pont).
            CODE = pathlib.Path(os.environ.get('SUIVI_FWD_CODE_GS') or SERVEUR.parent.parent / 'Code.gs').read_text(encoding='utf-8')
            edition = __import__('re').search(r"const EDITION = '([^']*)'", CODE).group(1)
            attendue = edition if 'data-livraison' in CODE else ''
            verifier('la vraie fenêtre : pas une ancienne version ; l’adresse lue ; sa livraison (« %s »)' % (attendue or 'version inconnue'),
                     tableau['ancienne'] is False and tableau['erreur'] == '' and tableau['adresse'] == cfg['tableau'] + '?page=import' and
                     tableau['livraison'] == attendue and tableau['perimee'] is (not attendue) and
                     robot.entete_du_tableau(cfg, tableau)[0] == 'Tableau de bord lu : %s?page=import — %s' % (cfg['tableau'], 'Livraison ' + attendue if attendue else 'version inconnue') and
                     # Débrief 31 (relu) : un Code.gs d'avant data-livraison (SUIVI_FWD_CODE_GS) est dit plus ancien que le robot.
                     len(robot.entete_du_tableau(cfg, tableau)) == (1 if attendue else 2),
                     (tableau, attendue))
            vieux = {'tableau': 'http://127.0.0.1:%d/exec?ancienne=1' % port}
            tableau_vieux = robot.lire_tableau(c, vieux)
            verifier('une fenêtre d’avant les fiches (le déploiement /exec d’avant) : reconnue — « ANCIENNE version », l’adresse, quoi faire',
                     tableau_vieux['ancienne'] is True and tableau_vieux['cases'] == ['GATES HDK', 'SEE'] and tableau_vieux['livraison'] == '' and
                     robot.contrats_lus(tableau_vieux) == [{'contrat': 'HDK', 'case': 'GATES HDK', 'nom_gates': '', 'prevu': False}] and
                     'ANCIENNE version du tableau de bord' in robot.entete_du_tableau(vieux, tableau_vieux)[1] and
                     vieux['tableau'] + '&page=import' in robot.entete_du_tableau(vieux, tableau_vieux)[1], tableau_vieux)
            # Débrief 31 (relu) : la fenêtre d'un déploiement du débrief 30 — le pont et les fiches, sans data-livraison.
            d30 = {'tableau': 'http://127.0.0.1:%d/exec?d30=1' % port}
            tableau_d30 = robot.lire_tableau(c, d30)
            verifier('une fenêtre du débrief 30 (pont et fiches, sans « Livraison ») : plus ancienne que le robot — dite, jamais « ✓ » ; ses fiches lues quand même',
                     (not attendue) or (tableau_d30['perimee'] is True and tableau_d30['ancienne'] is False and tableau_d30['livraison'] == '' and
                                        robot.contrats_lus(tableau_d30) == contrats and
                                        'plus ANCIENNE que lui' in '\n'.join(robot.entete_du_tableau(d30, tableau_d30))), tableau_d30)
            # Un autre onglet du navigateur du robot montre l'ancienne fenêtre : le robot lit toujours la sienne.
            with Chrome(port=robot.PORT, delai=30) as onglet:
                onglet.ouvrir(vieux['tableau'] + '&page=import')
                time_ = __import__('time')
                time_.sleep(2)
                lu_mien = robot.lire_tableau(c, cfg)
                lu_vieux = robot.lire_tableau(c, vieux)
            verifier('… et un autre onglet ouvert sur une autre fenêtre d’import ne trompe pas le robot : il lit celle de son onglet',
                     lu_mien['ancienne'] is False and len(lu_mien['contrats']) == 3 and lu_vieux['ancienne'] is True, (lu_mien, lu_vieux))
            # Débrief 31 : le lien de test /dev (celui que le robot garde désormais) — la même fenêtre, lue de même.
            dev = {'tableau': 'http://127.0.0.1:%d/dev' % port}
            tableau_dev = robot.lire_tableau(c, dev)
            verifier('par le lien /dev (Tester les déploiements) : la même fenêtre d’import (…/dev?page=import), les mêmes contrats, la même livraison',
                     tableau_dev['adresse'] == dev['tableau'] + '?page=import' and tableau_dev['ancienne'] is False and
                     tableau_dev['cases'] == tableau['cases'] and robot.contrats_lus(tableau_dev) == contrats and tableau_dev['livraison'] == attendue,
                     tableau_dev)
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
            du_robot = [r for r in e['recus'] if isinstance(r, dict) and r.get('source') == 'robot' and 'passage' in r]   # (la fenêtre, menée par le robot, dit aussi « robot »)
            verifier('… son compte rendu porte la livraison de la fenêtre (« %s ») — %s' % (attendue or 'aucune', 'le champ « livraison »' if attendue
                     else 'sans data-livraison, pas de champ « livraison »'),
                     len(du_robot) == 1 and (du_robot[0].get('livraison') == attendue if attendue else 'livraison' not in du_robot[0]), e['recus'])
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
        # Débrief 31 : par le lien /dev, celui que le robot garde désormais (« Changer l'adresse du tableau de bord »).
        robot.garder(dict(_json.loads(_json.dumps(NATHAN)), tableau='http://127.0.0.1:%d/dev' % port, heure='00:00'))
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
        verifier('… tout cela par le lien /dev : lu, déposé, compte rendu arrivé ; le journal dit l’adresse et la livraison lues',
                 'Tableau de bord lu : http://127.0.0.1:%d/dev?page=import — ' % port in nouveau_j and
                 len([r for r in e['recus'] if r.get('source') == 'robot' and 'passage' in r]) == 1, (nouveau_j[:600], e['recus']))
        # Débrief 31 (relu) : le compte rendu dit « adresse » = « dev », gardé par le vrai Code.gs avec la ligne du robot.
        CODE_N = pathlib.Path(os.environ.get('SUIVI_FWD_CODE_GS') or SERVEUR.parent.parent / 'Code.gs').read_text(encoding='utf-8')
        verifier('… son compte rendu dit son lien (« adresse » : « dev ») — et le tableau de bord le garde avec la ligne du robot',
                 [r.get('adresse') for r in e['recus'] if r.get('source') == 'robot' and 'passage' in r] == ['dev'] and
                 (rap['robot'].get('adresse') == 'dev' or "r.adresse === 'dev'" not in CODE_N), (e['recus'], rap['robot']))
    finally:
        robot.rejouer = vrai_rejouer
        os.environ.pop('SUIVI_FWD_OPTIONS_CHROME', None)
        serveur.terminate()
        serveur.wait(10)

print('\n— Débrief 31 : l’installateur (suivi-fwd-robot.py.txt) — à jour, avec « 0 - Tout oublier » et « Changer l’adresse du tableau de bord » —')
import base64 as _b64  # noqa: E402
import re as _re  # noqa: E402
import zlib as _zlib  # noqa: E402
PAQUET = pathlib.Path(__file__).resolve().parent.parent / 'suivi-fwd-robot.py.txt'
texte_paquet = PAQUET.read_text(encoding='utf-8') if PAQUET.exists() else ''
dans_le_paquet = {m.group(1): _zlib.decompress(_b64.b64decode(m.group(2))) for m in _re.finditer(r"    '([^']+)': '([A-Za-z0-9+/=]+)',", texte_paquet)}
verifier('le robot et son pilote, dans l’installateur, sont ceux d’aujourd’hui (python3 import/paquet_robot.py)',
         dans_le_paquet.get('robot.py') == (pathlib.Path(__file__).resolve().parent / 'robot.py').read_bytes() and
         dans_le_paquet.get('piloter_chrome.py') == (pathlib.Path(__file__).resolve().parent / 'piloter_chrome.py').read_bytes(), sorted(dans_le_paquet))
maison = pathlib.Path(tempfile.mkdtemp(prefix='robot-installe-'))
env = dict(os.environ, HOME=str(maison), USERPROFILE=str(maison), LOCALAPPDATA=str(maison / 'AppData'))
installe = subprocess.run([sys.executable, str(PAQUET)], input='n\n', capture_output=True, text=True, env=env, cwd=str(maison), timeout=60)
raccourcis = maison / 'Desktop' / 'Robot Suivi FWD'
oubli = raccourcis / '0 - Tout oublier (recommencer les exports).bat'
verifier('installé : le raccourci « 0 - Tout oublier (recommencer les exports) » est posé avec les autres, et lance « oublier »',
         installe.returncode == 0 and oubli.exists() and oubli.read_text(encoding='utf-8').splitlines()[2].endswith(' oublier') and
         sorted(p.name for p in raccourcis.iterdir())[:3] == ['0 - Tout oublier (recommencer les exports).bat', '1 - Preparer (une seule fois).bat',
                                                            '2 - Apprendre un export.bat'] and
         (maison / 'AppData' / 'SuiviFWD' / 'robot' / 'robot.py').read_bytes() == (pathlib.Path(__file__).resolve().parent / 'robot.py').read_bytes(),
         (installe.returncode, installe.stdout[-300:], installe.stderr[-300:], sorted(p.name for p in raccourcis.iterdir()) if raccourcis.exists() else None))
adresse_bat = raccourcis / "Changer l'adresse du tableau de bord.bat"
verifier('… et « Changer l’adresse du tableau de bord », qui lance « adresse » ; dix raccourcis en tout',
         adresse_bat.exists() and adresse_bat.read_text(encoding='utf-8').splitlines()[2].endswith(' adresse') and
         len(list(raccourcis.iterdir())) == 10, sorted(p.name for p in raccourcis.iterdir()) if raccourcis.exists() else None)

print('\n═══════════════════════════════════════')
print('%d vérification(s) réussie(s), %d échec(s)' % (len(faits), len(echecs)))
for e in echecs:
    print('  · ' + e)
sys.exit(1 if echecs else 0)
