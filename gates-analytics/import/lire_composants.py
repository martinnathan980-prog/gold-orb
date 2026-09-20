#!/usr/bin/env python3
"""
L'entrée unique : un plan, ou un dossier de plans, quel que soit le format —
et pour chacun, ses composants, comparés à ce que la base attend.

| Le fichier                       | Le lecteur       | Ce qu'il lit                       |
|----------------------------------|------------------|------------------------------------|
| PDF sorti d'un outil de dessin   | `lire_plan.py`   | le texte et les rectangles écrits  |
| PDF scanné, PNG, JPEG, TIFF      | `lire_scan.py`   | l'image : boîtes, puis caractères  |
| Visio `.vsdx` `.vsdm` `.vdx` `.vsd` | `lire_visio.py` | les formes et leur texte          |
| DXF                              | `lire_dxf.py`    | les entités et les blocs           |

Le choix se fait tout seul, sur l'extension puis sur le contenu : un PDF
qui n'a pas de texte est lu comme un scan.

    python3 import/lire_composants.py plan.pdf
    python3 import/lire_composants.py dossier-des-plans/ --connus base.csv --csv composants.csv
    python3 import/lire_composants.py scan.pdf --connus base.csv --controle controles/

`--connus` est la liste des repères que la base attend, par plan (un CSV
avec une colonne plan et une colonne repère, ou un repère par ligne pour un
seul plan) : le compte rendu dit alors ce qui est retrouvé, ce qui manque
sur le plan, et ce qui est en plus. Le CSV de sortie met tout sur une
ligne par chose vue — sûr, corrigé, douteux, orphelin, attendu absent —
pour trier dans un tableur.
"""

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from composants import (ErreurPlan, REPERE, raconter, lignes_csv, ecrire_csv,       # noqa: E402
                        lire_connus, attendus_pour, correspondance)
import lire_plan                                                                   # noqa: E402
import lire_visio                                                                  # noqa: E402
import lire_dxf                                                                    # noqa: E402

EXTENSIONS = {'.pdf': 'pdf', '.vsdx': 'visio', '.vsdm': 'visio', '.vdx': 'visio', '.vsd': 'visio',
              '.dxf': 'dxf', '.png': 'scan', '.jpg': 'scan', '.jpeg': 'scan', '.tif': 'scan',
              '.tiff': 'scan', '.bmp': 'scan'}


def lecteur_pour(chemin):
    """'pdf', 'visio', 'dxf', 'scan' — par l'extension, sinon par le contenu."""
    fichier = pathlib.Path(chemin)
    genre = EXTENSIONS.get(fichier.suffix.lower())
    if genre:
        return genre
    try:
        tete = fichier.read_bytes()[:4096]
    except OSError:
        return None
    if tete.startswith(b'%PDF'):
        return 'pdf'
    if tete.startswith(b'PK\x03\x04'):
        return 'visio'
    if tete.startswith((b'\x89PNG', b'\xff\xd8', b'II*\x00', b'MM\x00*', b'BM')):
        return 'scan'
    if re.search(rb'^\s*0\s*\r?\n\s*SECTION', tete):
        return 'dxf'
    return None


def lire_un(chemin, repere=REPERE, connus=None, options=None):
    """(résultat, nom du lecteur employé). Lève ErreurPlan."""
    options = options or {}
    genre = lecteur_pour(chemin)
    nom = pathlib.Path(chemin).name
    if genre is None:
        raise ErreurPlan('%s : format inconnu (PDF, Visio, DXF, ou une image PNG/JPEG/TIFF).' % nom)
    if genre == 'visio':
        return lire_visio.lire(chemin, repere), 'Visio'
    if genre == 'dxf':
        return lire_dxf.lire(chemin, repere), 'DXF'
    if genre == 'pdf':
        try:
            return lire_plan.lire(chemin, repere), 'dessin PDF'
        except ErreurPlan as err_dessin:
            import lire_scan
            try:
                return lire_scan.lire(chemin, repere, connus, **options), 'scan PDF'
            except ErreurPlan as err_scan:
                raise ErreurPlan('%s\n  Comme scan : %s' % (err_dessin, err_scan))
    import lire_scan
    return lire_scan.lire(chemin, repere, connus, **options), 'scan'


def plans_de(chemin):
    """Le fichier, ou tous les plans du dossier, sous-dossiers compris."""
    racine = pathlib.Path(chemin)
    if racine.is_dir():
        return sorted(f for f in racine.rglob('*') if f.is_file() and f.suffix.lower() in EXTENSIONS)
    return [racine]


def main(argv=None):
    parseur = argparse.ArgumentParser(description='Les composants d\'un plan ELEC, ou d\'un dossier de plans.')
    parseur.add_argument('plan', help='un plan (PDF, Visio, DXF, image) ou un dossier')
    parseur.add_argument('--csv', help='écrire tout ce qui a été vu dans ce fichier')
    parseur.add_argument('--connus', help='les repères que la base attend, par plan')
    parseur.add_argument('--plan-nom', help='le nom du plan dans la liste des connus (un seul fichier)')
    parseur.add_argument('--repere', help='l\'expression qui reconnaît un repère électrique')
    parseur.add_argument('--moteur', default='auto', choices=['auto', 'rapidocr', 'windows'],
                         help='le moteur de lecture des scans')
    parseur.add_argument('--controle', help='pour les scans : un dossier où écrire une image de contrôle par page')
    parseur.add_argument('--sans-page-entiere', action='store_true', help='scans : ne lire que les boîtes')
    parseur.add_argument('--sans-rotation', action='store_true', help='scans : ne pas essayer la page tournée')
    args = parseur.parse_args(argv)
    try:
        motif = re.compile(args.repere) if args.repere else REPERE
        connus = lire_connus(args.connus) if args.connus else None
    except (ErreurPlan, re.error) as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1
    options = {'moteur': args.moteur, 'controle': args.controle, 'page_entiere': not args.sans_page_entiere}
    if args.sans_rotation:
        options['orientations'] = (0,)
    if args.controle:
        pathlib.Path(args.controle).mkdir(parents=True, exist_ok=True)
    plans = plans_de(args.plan)
    if not plans:
        print('Arrêt : aucun plan dans %s.' % args.plan, file=sys.stderr)
        return 1
    lignes, echecs, surs, a_regarder = [], 0, 0, 0
    for rang, plan in enumerate(plans):
        if rang:
            print('')
        attendus = attendus_pour(connus, args.plan_nom or plan.stem) if connus else None
        try:
            resultat, lecteur = lire_un(plan, motif, attendus, options)
        except ErreurPlan as err:
            echecs += 1
            print('%s : arrêt — %s' % (plan.name, err), file=sys.stderr)
            continue
        corr = correspondance(resultat, attendus) if attendus is not None else None
        print(raconter(resultat, '%s (%s)' % (plan.name, lecteur), corr))
        for c in resultat.get('controles', []):
            print('  → image de contrôle : %s' % c)
        if connus and attendus is None:
            print('  (aucune liste de repères attendus ne porte le nom de ce plan)')
        lignes += lignes_csv(resultat, plan.name, corr)
        surs += len(resultat['trouves'])
        a_regarder += len(resultat['douteux']) + len(resultat['orphelins']) + len(resultat.get('incertains', []))
    if len(plans) > 1:
        print('\n%d plan(s) lu(s), %d en échec — %d composant(s) sûr(s), %d chose(s) à regarder.'
              % (len(plans) - echecs, echecs, surs, a_regarder))
    if args.csv:
        ecrire_csv(args.csv, lignes)
        print('→ %s' % args.csv)
    return 1 if echecs else 0


if __name__ == '__main__':
    sys.exit(main())
