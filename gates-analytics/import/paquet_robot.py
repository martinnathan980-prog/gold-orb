#!/usr/bin/env python3
"""
Fabrique `suivi-fwd-robot.py.txt` : le robot (robot.py + piloter_chrome.py)
dans un seul fichier, qui s'installe tout seul sur le poste.

    python3 import/paquet_robot.py

Sur le poste, une seule commande (l'extension .txt ne gêne pas Python) :

    python suivi-fwd-robot.py.txt

Il pose le robot dans %LOCALAPPDATA%\\SuiviFWD\\robot, met sur le Bureau un
dossier « Robot Suivi FWD » de raccourcis à double-cliquer, puis propose de
préparer le robot tout de suite.
"""

import base64
import pathlib
import zlib

ICI = pathlib.Path(__file__).resolve().parent
SORTIE = ICI.parent / 'suivi-fwd-robot.py.txt'
FICHIERS = ['robot.py', 'piloter_chrome.py']

INSTALLATEUR = r'''#!/usr/bin/env python3
# Robot Suivi FWD — installateur. Lancer : python suivi-fwd-robot.py.txt
import base64, ctypes, os, pathlib, subprocess, sys, zlib

FICHIERS = %(fichiers)s

RACCOURCIS = [
    ('1 - Preparer (une seule fois).bat', 'preparer'),
    ('2 - Apprendre un export.bat', 'apprendre'),
    ('3 - Essayer.bat', 'essayer'),
    ('4 - Activer chaque matin.bat', 'activer'),
    ('Lancer maintenant.bat', 'lancer'),
    ('Etat du robot.bat', 'etat'),
    ('Desactiver le lancement automatique.bat', 'desactiver'),
    ('Choisir le navigateur (Chrome ou Edge).bat', 'navigateur'),
]


def bureau():
    try:
        tampon = ctypes.create_unicode_buffer(260)
        ctypes.windll.shell32.SHGetFolderPathW(None, 0x10, None, 0, tampon)
        if tampon.value:
            return pathlib.Path(tampon.value)
    except Exception:
        pass
    return pathlib.Path.home() / 'Desktop'


def main():
    base = os.environ.get('LOCALAPPDATA')
    dossier = (pathlib.Path(base) / 'SuiviFWD' / 'robot') if base else (pathlib.Path.home() / '.suivi-fwd' / 'robot')
    dossier.mkdir(parents=True, exist_ok=True)
    for nom, donnees in FICHIERS.items():
        (dossier / nom).write_bytes(zlib.decompress(base64.b64decode(donnees)))
    raccourcis = bureau() / 'Robot Suivi FWD'
    raccourcis.mkdir(parents=True, exist_ok=True)
    for nom, action in RACCOURCIS:
        (raccourcis / nom).write_text(
            '@echo off\r\nchcp 65001 >nul\r\n"%%s" "%%s" %%s\r\npause\r\n' %% (sys.executable, dossier / 'robot.py', action),
            encoding='utf-8')
    print('Robot installé dans : %%s' %% dossier)
    print('Raccourcis posés sur le Bureau, dossier « Robot Suivi FWD ».')
    print()
    print('Prochaine étape : double-cliquez « 1 - Preparer (une seule fois) ».')
    if input('Le faire maintenant ? (o/n) ').strip().lower().startswith('o'):
        subprocess.call([sys.executable, str(dossier / 'robot.py'), 'preparer'])


main()
'''


def fabriquer():
    contenus = {}
    for nom in FICHIERS:
        donnees = (ICI / nom).read_bytes()
        contenus[nom] = base64.b64encode(zlib.compress(donnees, 9)).decode('ascii')
    lignes = '{\n' + ''.join('    %r: %r,\n' % (k, v) for k, v in contenus.items()) + '}'
    SORTIE.write_text(INSTALLATEUR % {'fichiers': lignes}, encoding='utf-8')
    return SORTIE


if __name__ == '__main__':
    print('Écrit : %s' % fabriquer())
