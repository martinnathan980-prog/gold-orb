#!/usr/bin/env python3
"""
Batterie du paquet qui se déballe tout seul : elle le fabrique pour de vrai,
le lance comme le fera le poste de travail, et vérifie que chaque fichier
revient **octet pour octet** — accents compris. Puis elle lance un des outils
déballés, pour prouver que le dossier obtenu est utilisable tel quel.

    python3 import/tests_paquet.py

Aucune dépendance : bibliothèque standard uniquement.
"""

import pathlib
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import paquet                                                      # noqa: E402

echecs, faits = [], []


def verifier(nom, condition, detail=''):
    if condition:
        faits.append(nom)
        print('  ✓ ' + nom)
    else:
        echecs.append(nom)
        print('  ✗ ' + nom + (' — ' + str(detail) if detail else ''))


def section(titre):
    print('\n— ' + titre + ' —')


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-paquet-'))
    try:
        section('Ce que le paquet emporte, et ce qu\'il laisse')
        fichiers = paquet.a_emporter()
        noms = [nom for _, nom in fichiers]
        verifier('les outils du poste sont tous là',
                 all(('import/' + n) in noms for n in
                     ('diagnostic.py', 'essai.py', 'lire_composants.py', 'extraire.py',
                      'deposer.py', 'piloter_chrome.py', 'composants.py', 'lire_scan.py')),
                 [n for n in noms if n.startswith('import/')][:8])
        verifier('les recettes et le moteur Windows aussi',
                 'import/recettes/gates-par-contrat.json' in noms and
                 'import/ocr_windows.ps1' in noms)
        verifier('l\'installateur Apps Script, la marche à suivre et le mode d\'emploi voyagent avec',
                 'apps-script/Installateur.gs' in noms and 'AU-BUREAU.md' in noms and 'MODE-D-EMPLOI.md' in noms)
        verifier('les caches, le dossier d\'essai et le secret du dépôt restent ici',
                 not any('__pycache__' in n or '/essai/' in n or n.endswith('depot.json')
                         for n in noms), [n for n in noms if '__pycache__' in n])
        verifier('l\'interface emballée pour la messagerie ne part pas : elle ne sert pas là-bas',
                 not any('gz.b64' in n for n in noms))
        verifier('aucun doublon', len(noms) == len(set(noms)))

        section('Le paquet se fabrique, et deux fois de suite à l\'identique')
        sortie = atelier / 'outils.py.txt'
        paquet.main(['--sortie', str(sortie), '--silencieux'])
        verifier('il est écrit, et fait un poids plausible',
                 sortie.exists() and 100_000 < sortie.stat().st_size < 4_000_000,
                 sortie.stat().st_size if sortie.exists() else 'absent')
        premier = sortie.read_bytes()
        paquet.main(['--sortie', str(sortie), '--silencieux'])
        verifier('refabriqué sans rien changer, il est identique — on voit donc ce qui bouge',
                 sortie.read_bytes() == premier)
        texte = sortie.read_text(encoding='utf-8')
        verifier('c\'est un programme Python lisible, pas un tas d\'octets',
                 texte.startswith('#!/usr/bin/env python3') and 'def main(' in texte and
                 'base64.b64decode' in texte)
        lignes = texte.splitlines()
        debut = lignes.index('ARCHIVE = """\\') + 1
        fin = lignes.index('"""', debut)
        verifier('la base64 est en colonnes, comme un courriel — aucune ligne interminable',
                 fin - debut > 100 and all(len(l) <= paquet.LARGEUR for l in lignes[debut:fin]),
                 (fin - debut, max((len(l) for l in lignes[debut:fin]), default=0)))
        verifier('il dit lui-même comment s\'en servir, sans rien renommer',
                 'python suivi-fwd-outils.py.txt' in texte and 'se moque de' in texte)

        section('Il se déballe comme le fera le poste')
        dossier = atelier / 'chez-nathan'
        fini = subprocess.run([sys.executable, str(sortie), str(dossier)],
                              capture_output=True, timeout=180)
        dit = fini.stdout.decode('utf-8', 'replace')
        verifier('il se lance sans erreur, et dit ce qu\'il a fait',
                 fini.returncode == 0 and 'fichiers déballés' in dit,
                 fini.stderr.decode('utf-8', 'replace')[:300])
        verifier('il dit les trois commandes qui comptent, et le secours « py »',
                 'diagnostic.py' in dit and 'essai.py --jouer' in dit and 'py' in dit)
        differences = []
        for chemin, nom in fichiers:
            arrive = dossier / nom
            if not arrive.exists():
                differences.append(nom + ' (absent)')
            elif arrive.read_bytes() != chemin.read_bytes():
                differences.append(nom + ' (abîmé)')
        verifier('les %d fichiers reviennent octet pour octet, accents compris' % len(fichiers),
                 not differences, differences[:5])
        verifier('les sous-dossiers sont recréés', (dossier / 'import' / 'recettes').is_dir())
        verifier('sans argument, le dossier s\'appelle « suivi-fwd »',
                 _sans_argument(sortie, atelier))

        section('Le dossier déballé est utilisable tel quel')
        extrait = atelier / 'extrait.csv'
        fini = subprocess.run(
            [sys.executable, '-c',
             'import sys; sys.path.insert(0, %r); import essai, pathlib; '
             'pathlib.Path(%r).write_text(essai.csv_de("HDK"), encoding="utf-8-sig")'
             % (str(dossier / 'import'), str(extrait))],
            capture_output=True, timeout=120)
        verifier('un outil déballé s\'importe depuis son nouveau dossier',
                 fini.returncode == 0 and extrait.exists(),
                 fini.stderr.decode('utf-8', 'replace')[:300])
        fini = subprocess.run([sys.executable, str(dossier / 'import' / 'diagnostic.py'),
                               str(extrait), '--sans-fichier'], capture_output=True, timeout=120)
        dit = fini.stdout.decode('utf-8', 'replace')
        verifier('et la fiche d\'extract tourne, depuis le dossier déballé',
                 fini.returncode == 0 and 'FICHE D\'EXTRACT' in dit and
                 'l\'avancement suivi' in dit, fini.stderr.decode('utf-8', 'replace')[:300])
        fini = subprocess.run([sys.executable, str(dossier / 'import' / 'tests_plan.py')],
                              capture_output=True, timeout=300)
        verifier('la batterie des plans passe aussi, là-bas comme ici',
                 fini.returncode == 0 and '0 échec' in fini.stdout.decode('utf-8', 'replace'),
                 fini.stdout.decode('utf-8', 'replace')[-200:])
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


def _sans_argument(sortie, atelier):
    """Lancé sans rien, il déballe dans « suivi-fwd » à côté de là où on est."""
    ailleurs = atelier / 'ailleurs'
    ailleurs.mkdir()
    fini = subprocess.run([sys.executable, str(sortie)], capture_output=True,
                          cwd=str(ailleurs), timeout=180)
    return fini.returncode == 0 and (ailleurs / 'suivi-fwd' / 'import' / 'diagnostic.py').exists()


if __name__ == '__main__':
    sys.exit(main())
