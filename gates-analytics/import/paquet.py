#!/usr/bin/env python3
"""
Fabrique **un seul fichier qui se déballe tout seul** : tout le dossier
d'automatisation, compressé dans un programme Python qui le recrée.

C'est la réponse au poste de travail : la messagerie mange les pièces jointes
de code, le Drive personnel est fermé, et GitHub n'est pas toujours joignable.
Un fichier `.txt` qui est aussi un programme Python passe partout — et Python
se moque de l'extension, donc il n'y a même pas à le renommer :

    python suivi-fwd-outils.py.txt

Pour fabriquer le paquet :

    python3 import/paquet.py
    python3 import/paquet.py --sortie /tmp/envoi/outils.py.txt

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import base64
import io
import pathlib
import sys
import zipfile

RACINE = pathlib.Path(__file__).resolve().parent.parent
SORTIE_DEFAUT = RACINE / 'suivi-fwd-outils.py.txt'
LARGEUR = 76                      # la base64 se lit en colonnes, comme un courriel
# Ce qui n'a rien à faire dans le paquet : les caches, le dossier fabriqué par
# l'essai, le secret du dépôt, et le transport par messagerie de l'interface.
EXCLUS = ('__pycache__', 'essai', 'donnees')
EXCLUS_NOMS = ('depot.json',)


def a_emporter(racine=RACINE):
    """[(chemin réel, nom dans le paquet)] — tout ce qui part sur le poste."""
    fichiers = []
    dossier = racine / 'import'
    for f in sorted(dossier.rglob('*')):
        if not f.is_file():
            continue
        if any(part in EXCLUS for part in f.parts) or f.name in EXCLUS_NOMS:
            continue
        if f.suffix == '.txt' and 'gz.b64' in f.name:
            continue              # l'interface emballée : elle ne sert pas ici
        fichiers.append((f, 'import/' + str(f.relative_to(dossier)).replace('\\', '/')))
    for extra in ('apps-script/Installateur.gs', 'AU-BUREAU.md', 'MODE-D-EMPLOI.md'):
        chemin = racine / extra
        if chemin.exists():
            fichiers.append((chemin, extra))
    return fichiers


def archive_de(fichiers):
    """Le ZIP, en mémoire. Les dates sont fixes : deux paquets du même code
    donnent le même fichier, donc on voit tout de suite s'il a changé."""
    tampon = io.BytesIO()
    with zipfile.ZipFile(tampon, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for chemin, nom in fichiers:
            info = zipfile.ZipInfo(nom, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, chemin.read_bytes())
    return tampon.getvalue()


TETE = '''#!/usr/bin/env python3
"""
LES OUTILS DU SUIVI FWD — un seul fichier, qui se déballe tout seul.

Tout le dossier d'automatisation tient ici, compressé : les lecteurs de plans,
le pilote Chrome, les recettes d'extraction, le dépôt dans le classeur, la
fiche d'extract, l'essai à blanc, et l'installateur Apps Script.

    python suivi-fwd-outils.py.txt

C'est tout. Inutile de renommer quoi que ce soit : Python se moque de
l'extension. Le dossier « suivi-fwd » apparaît à côté, et le programme dit
quoi taper ensuite.

Pour le déballer ailleurs :

    python suivi-fwd-outils.py.txt C:/chemin/de/mon/choix

Aucune dépendance : bibliothèque standard uniquement.
"""

import base64
import io
import pathlib
import sys
import zipfile

ARCHIVE = """\\
'''

PIED = '''"""


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    dossier = pathlib.Path(argv[0] if argv else 'suivi-fwd').resolve()
    donnees = base64.b64decode(''.join(ARCHIVE.split()))
    with zipfile.ZipFile(io.BytesIO(donnees)) as archive:
        noms = archive.namelist()
        archive.extractall(str(dossier))
    print('%d fichiers déballés dans %s' % (len(noms), dossier))
    print('')
    print('CE QU\\'IL Y A DEDANS')
    print('  import\\\\diagnostic.py        la fiche d\\'un vrai extract  (commencer par là)')
    print('  import\\\\essai.py             l\\'essai à blanc : un faux GATES sur ce PC')
    print('  import\\\\lire_composants.py   les composants d\\'un plan (PDF, Visio, DXF, scan)')
    print('  import\\\\extraire.py          rejoue une recette d\\'extraction dans Chrome')
    print('  import\\\\deposer.py           envoie un extract au classeur')
    print('  apps-script\\\\Installateur.gs  à coller dans Apps Script')
    print('  MODE-D-EMPLOI.md            ce qu\\'on fait dans le classeur, semaine après semaine')
    print('  AU-BUREAU.md                la marche à suivre, en entier')
    print('')
    print('LES TROIS COMMANDES QUI COMPTENT')
    print('  cd %s' % dossier)
    print('  python import\\\\diagnostic.py "C:\\\\chemin\\\\vers\\\\extract-HDK.xlsx"')
    print('  python import\\\\essai.py --jouer')
    print('  python import\\\\lire_composants.py "C:\\\\chemin\\\\vers\\\\plan.pdf"')
    print('')
    print('Si une commande dit « python n\\'est pas reconnu », essayer « py » à la place.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
'''


def fabriquer(racine=RACINE):
    """Le texte du paquet, prêt à écrire."""
    fichiers = a_emporter(racine)
    if not fichiers:
        raise SystemExit('Rien à emporter : le dossier import/ est introuvable depuis %s.' % racine)
    paquet = base64.b64encode(archive_de(fichiers)).decode('ascii')
    lignes = '\n'.join(paquet[i:i + LARGEUR] for i in range(0, len(paquet), LARGEUR))
    return TETE + lignes + '\n' + PIED, fichiers


def main(argv=None):
    parseur = argparse.ArgumentParser(
        description='Fabrique le fichier unique qui se déballe tout seul sur le poste.')
    parseur.add_argument('--sortie', default=str(SORTIE_DEFAUT), help='où écrire le paquet')
    parseur.add_argument('--racine', default=str(RACINE), help='le dossier gates-analytics')
    parseur.add_argument('--silencieux', action='store_true')
    args = parseur.parse_args(argv)
    texte, fichiers = fabriquer(pathlib.Path(args.racine))
    sortie = pathlib.Path(args.sortie)
    sortie.parent.mkdir(parents=True, exist_ok=True)
    sortie.write_text(texte, encoding='utf-8')
    if not args.silencieux:
        print('%d fichiers emportés, paquet de %d Ko : %s'
              % (len(fichiers), sortie.stat().st_size // 1024, sortie))
        for _, nom in fichiers:
            print('   ' + nom)
        print('\nSur le poste :  python %s' % sortie.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
