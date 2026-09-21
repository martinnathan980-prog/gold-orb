#!/usr/bin/env python3
"""
Batterie de la fiche d'extract : elle fabrique de vrais classeurs .xlsx —
chaînes partagées, cellules creuses, plusieurs onglets, ordre des feuilles
inversé — et de vrais CSV, puis vérifie que la fiche dit juste : la ligne
d'en-tête, les groupes, les rôles des colonnes, les valeurs d'avancement,
l'anatomie des références. Et qu'elle ne recopie jamais un texte libre.

    python3 import/tests_diagnostic.py

Aucune dépendance : bibliothèque standard uniquement.
"""

import pathlib
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import diagnostic as dg                                            # noqa: E402
import essai                                                       # noqa: E402

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


def _leve(fonction, *args, **params):
    try:
        fonction(*args, **params)
    except dg.ErreurDiagnostic as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
#  Fabriquer un vrai .xlsx : une archive de XML, comme Excel les écrit
# ---------------------------------------------------------------------------
PRINCIPAL = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
RELATIONS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


def _lettre(index):
    nom = ''
    index += 1
    while index:
        index, reste = divmod(index - 1, 26)
        nom = chr(65 + reste) + nom
    return nom


def xlsx(chemin, onglets, creuses=False, ordre_inverse=False):
    """onglets : [(nom, [[cellule, …], …])] — les nombres restent des nombres."""
    chaines, index_chaine = [], {}

    def numero(valeur):
        if valeur not in index_chaine:
            index_chaine[valeur] = len(chaines)
            chaines.append(valeur)
        return index_chaine[valeur]

    feuilles_xml = []
    for nom, lignes in onglets:
        morceaux = []
        for rang, ligne in enumerate(lignes, 1):
            cellules = []
            for colonne, valeur in enumerate(ligne):
                texte = '' if valeur is None else str(valeur)
                if creuses and not texte.strip():
                    continue                      # Excel n'écrit pas les cellules vides
                reference = '%s%d' % (_lettre(colonne), rang)
                try:
                    float(texte)
                    est_nombre = texte.strip() != ''
                except ValueError:
                    est_nombre = False
                if est_nombre:
                    cellules.append('<c r="%s"><v>%s</v></c>' % (reference, texte))
                else:
                    cellules.append('<c r="%s" t="s"><v>%d</v></c>' % (reference, numero(texte)))
            morceaux.append('<row r="%d">%s</row>' % (rang, ''.join(cellules)))
        feuilles_xml.append('<?xml version="1.0"?><worksheet xmlns="%s"><sheetData>%s</sheetData></worksheet>'
                            % (PRINCIPAL, ''.join(morceaux)))
    with zipfile.ZipFile(str(chemin), 'w') as archive:
        archive.writestr('[Content_Types].xml',
                         '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        # Les fichiers de feuille sont numérotés à l'envers des onglets : c'est
        # ce que fait Excel après un déplacement d'onglet, et c'est le piège.
        numeros = list(range(len(onglets), 0, -1)) if ordre_inverse else list(range(1, len(onglets) + 1))
        feuilles = ''.join('<sheet name="%s" sheetId="%d" r:id="rId%d"/>' % (nom, rang, rang)
                           for rang, (nom, _) in enumerate(onglets, 1))
        archive.writestr('xl/workbook.xml',
                         '<?xml version="1.0"?><workbook xmlns="%s" xmlns:r="%s"><sheets>%s</sheets></workbook>'
                         % (PRINCIPAL, RELATIONS, feuilles))
        relations = ''.join('<Relationship Id="rId%d" Type="x" Target="worksheets/sheet%d.xml"/>'
                            % (rang, numeros[rang - 1]) for rang in range(1, len(onglets) + 1))
        archive.writestr('xl/_rels/workbook.xml.rels',
                         '<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">%s</Relationships>'
                         % relations)
        for rang, contenu in enumerate(feuilles_xml, 1):
            archive.writestr('xl/worksheets/sheet%d.xml' % numeros[rang - 1], contenu)
        if chaines:
            items = ''.join('<si><t>%s</t></si>' % c.replace('&', '&amp;').replace('<', '&lt;') for c in chaines)
            archive.writestr('xl/sharedStrings.xml',
                             '<?xml version="1.0"?><sst xmlns="%s" count="%d" uniqueCount="%d">%s</sst>'
                             % (PRINCIPAL, len(chaines), len(chaines), items))


def tableau_gates(contrat='HDK'):
    """Un extract GATES, comme essai.py le fabrique : deux lignes d'en-tête."""
    return essai.lignes_de(contrat)


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-diag-'))
    try:
        section('Un classeur Excel se lit sans rien installer')
        lignes = tableau_gates('HDK')
        classeur = atelier / 'extract-HDK.xlsx'
        xlsx(classeur, [('Extract', lignes)])
        lues, format_lu = dg.lire(classeur)
        verifier('le .xlsx est reconnu et lu, onglet nommé',
                 'classeur Excel' in format_lu and 'Extract' in format_lu, format_lu)
        verifier('toutes les lignes et toutes les colonnes sont là',
                 len(lues) == len(lignes) and len(lues[1]) == 17, (len(lues), len(lues[1])))
        verifier('les textes et les nombres se lisent pareil',
                 lues[1][1] == 'Référence UD' and lues[2][1] == 'TFE2130A600001A' and
                 lues[2][16] in ('100', '100.0'), (lues[1][1], lues[2][1], lues[2][16]))
        creux = atelier / 'creux.xlsx'
        xlsx(creux, [('Extract', lignes)], creuses=True)
        lues_creuses, _ = dg.lire(creux)
        verifier('les cellules vides qu\'Excel n\'écrit pas ne décalent pas les colonnes',
                 lues_creuses[1][16] == 'Avancement' and lues_creuses[2][1] == 'TFE2130A600001A',
                 lues_creuses[1][:3])
        deux = atelier / 'deux-onglets.xlsx'
        xlsx(deux, [('GATES', lignes), ('SEE', [['NAME', 'SOL.'], ['TFE2130A600001A', 'X']])], ordre_inverse=True)
        verifier('le bon onglet est lu même si les fichiers sont numérotés à l\'envers',
                 dg.lire(deux)[0][1][1] == 'Référence UD', dg.lire(deux)[0][1][:3])
        verifier('… et l\'onglet se choisit par son nom',
                 dg.lire(deux, 'see')[0][0] == ['NAME', 'SOL.'], dg.lire(deux, 'see')[0][0])
        verifier('les onglets du classeur sont listés', dg.onglets_xlsx(deux) == ['GATES', 'SEE'])
        verifier('un onglet qui n\'existe pas est dit, avec la liste des vrais',
                 _leve(dg.lire, deux, 'Feuil9'))

        section('Un CSV aussi, quel que soit ce que l\'outil a choisi')
        for nom, octets, attendu in (
            ('point-virgule.csv', essai.csv_de('HDK').encode('utf-8-sig'), 'point-virgule'),
            ('tabulation.csv', essai.csv_de('HDK').replace(';', '\t').encode('cp1252'), 'tabulation'),
            ('utf16.csv', essai.csv_de('HDK').encode('utf-16'), 'point-virgule'),
        ):
            fichier = atelier / nom
            fichier.write_bytes(octets)
            lues, format_lu = dg.lire(fichier)
            verifier('%s : séparateur et encodage retrouvés tout seuls' % nom,
                     attendu in format_lu and lues[1][1] == 'Référence UD', (format_lu, lues[1][:2]))
        faux = atelier / 'renomme.csv'
        faux.write_bytes(classeur.read_bytes())
        lues, format_lu = dg.lire(faux)
        verifier('un .xlsx renommé en .csv est reconnu à son contenu, et lu quand même',
                 'classeur Excel' in format_lu and lues[1][1] == 'Référence UD', format_lu)
        vieux = atelier / 'vieux.xls'
        vieux.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\0' * 64)
        verifier('un vieux .xls est refusé en disant comment le convertir', _leve(dg.lire, vieux))
        verifier('un fichier introuvable le dit', _leve(dg.lire, atelier / 'nulle-part.xlsx'))
        pas_zip = atelier / 'pas-un-classeur.xlsx'
        pas_zip.write_bytes(b'bonjour')
        verifier('un .xlsx qui n\'est pas une archive le dit', _leve(dg.lire, pas_zip))

        section('La fiche dit juste')
        lues, format_lu = dg.lire(classeur)
        analyse = dg.analyser(lues)
        verifier('les intitulés sont trouvés ligne 2, les groupes ligne 1',
                 analyse['rang_titres'] == 2 and analyse['rang_groupes'] == 1,
                 (analyse['rang_titres'], analyse['rang_groupes']))
        verifier('les plans sont comptés sans les deux lignes d\'en-tête',
                 analyse['plans'] == len(essai.PLANS['HDK']), analyse['plans'])
        roles = {c['role']: c['index'] for c in analyse['colonnes'] if c['role']}
        verifier('la référence, l\'avancement, le domaine, l\'ATA, le CC, l\'ECP et la date sont désignés',
                 roles.get('la référence du plan') == 2 and roles.get('l\'avancement suivi') == 17 and
                 roles.get('le domaine') == 8 and roles.get('l\'ATA') == 13 and
                 roles.get('le code circuit') == 12 and roles.get('l\'ECP') == 15 and
                 roles.get('la date de création') == 10, roles)
        verifier('le groupe d\'une colonne fusionnée est reporté jusqu\'à la suivante',
                 analyse['colonnes'][16]['groupe'] == 'Réalisation FWD' and
                 analyse['colonnes'][12]['groupe'] == 'Définition du plan',
                 [c['groupe'] for c in analyse['colonnes'][11:17]])
        avancement = analyse['colonnes'][16]
        attendus = set(p[9] for p in essai.PLANS['HDK'] if p[9])
        verifier('toutes les valeurs d\'avancement sont relevées, et les vides comptées',
                 set(avancement['toutes']) == attendus and
                 avancement['remplies'] == analyse['plans'] - 1,
                 (avancement['toutes'], avancement['remplies']))
        libelle = analyse['colonnes'][6]
        verifier('une colonne de texte libre n\'est jamais recopiée en entier',
                 libelle['toutes'] is None and libelle['longueur_maxi'] > dg.LARGEUR_VALEUR,
                 (libelle['toutes'], libelle['longueur_maxi']))
        donnees = [l for l in lues if dg.ligne_non_vide(l)][analyse['rang_titres']:]
        refs = dg.references(analyse, donnees)
        verifier('l\'anatomie des références est reconnue, séquences et indices relevés',
                 refs['anatomie'] == refs['total'] and refs['sequences'] == ['600', '700', '800'] and
                 'A' in refs['indices'] and 'TF' in refs['circuits'], refs)
        fiche = dg.raconter(analyse, refs, 'extract-HDK.xlsx', format_lu, 1234)
        verifier('la fiche nomme le rôle de chaque colonne qui commande le tableau de bord',
                 'la référence du plan' in fiche and 'colonne 17' in fiche and
                 'LES VALEURS RÉELLES' in fiche, fiche[:200])
        verifier('… dit la ligne d\'en-tête, le nombre de plans et les colonnes vides',
                 'intitulés sont ligne 2' in fiche and 'groupes ligne 1' in fiche and
                 'sans intitulé ET vides : 1, 4, 5' in fiche, [l for l in fiche.splitlines()[:12]])
        verifier('… et se termine en disant ce qu\'elle ne contient pas',
                 'aucun libellé' in fiche and 'texte' in fiche.splitlines()[-4])
        longs = [p[5] for p in essai.PLANS['HDK'] if len(p[5]) > dg.LARGEUR_VALEUR]
        verifier('aucun texte long du fichier ne se retrouve dans la fiche, même en exemple',
                 longs and not any(t in fiche for t in longs),
                 [t for t in longs if t in fiche])
        verifier('un texte long apparaît seulement sous sa forme, lettres remplacées',
                 'Aa… a…' in fiche, [l for l in fiche.splitlines() if 'exemples' in l][:3])

        section('Le mode anonyme')
        anonyme = dg.analyser(lues, anonyme=True)
        fiche_anonyme = dg.raconter(anonyme, dg.references(anonyme, donnees), 'x.xlsx', format_lu, 1)
        verifier('les valeurs sont remplacées par leur forme',
                 'TFE2130A600001A' not in fiche_anonyme and 'AAA9999A999999A' in fiche_anonyme,
                 [l for l in fiche_anonyme.splitlines() if 'AAA' in l][:3])
        verifier('aucun code ECP réel ne subsiste',
                 'ECP-1201' not in fiche_anonyme and 'HDK-1001' not in fiche_anonyme)
        verifier('et aucun libellé, même court',
                 not any(p[5] in fiche_anonyme for p in essai.PLANS['HDK']),
                 [p[5] for p in essai.PLANS['HDK'] if p[5] in fiche_anonyme])
        verifier('la fiche dit qu\'elle est anonyme', 'remplacées par leur forme' in fiche_anonyme)

        section('Un tableau sans groupes, et un tableau bancal')
        simple = atelier / 'simple.csv'
        simple.write_text('Reference;Avancement\nTFE2130A600001A;100\nWLE4610A600003C;\n', encoding='utf-8')
        lues, _ = dg.lire(simple)
        a = dg.analyser(lues)
        verifier('sans ligne de groupes, l\'en-tête reste trouvé ligne 1',
                 a['rang_titres'] == 1 and a['rang_groupes'] is None and a['plans'] == 2,
                 (a['rang_titres'], a['rang_groupes'], a['plans']))
        titre = atelier / 'avec-titre.csv'
        titre.write_text('Extraction GATES du 21/09/2026;;\n;;\nReference;Domaine;Avancement\n'
                         'TFE2130A600001A;BASE;100\nWLE4610A600003C;PERSO;40\n', encoding='utf-8')
        lues, _ = dg.lire(titre)
        a = dg.analyser(lues)
        verifier('une ligne de titre au-dessus de l\'en-tête ne trompe pas la détection',
                 a['rang_titres'] == 2 and a['plans'] == 2, (a['rang_titres'], a['plans']))
        vide = atelier / 'vide.csv'
        vide.write_text('\n\n', encoding='utf-8')
        verifier('un fichier sans aucune ligne remplie le dit', _leve(dg.analyser, dg.lire(vide)[0]))

        section('La ligne de commande')
        code = dg.main([str(classeur), '--fiche', str(atelier / 'fiche.txt')])
        verifier('elle écrit la fiche et rend 0',
                 code == 0 and (atelier / 'fiche.txt').exists() and
                 'FICHE D\'EXTRACT' in (atelier / 'fiche.txt').read_text(encoding='utf-8'))
        verifier('sans --fiche, le nom est déduit de l\'extract',
                 dg.main([str(classeur), '--anonyme']) == 0 and (atelier / 'fiche-extract-HDK.txt').exists())
        verifier('--sans-fichier n\'écrit rien', dg.main([str(simple), '--sans-fichier']) == 0 and
                 not (atelier / 'fiche-simple.txt').exists())
        verifier('un fichier illisible rend 1', dg.main([str(vieux)]) == 1)
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


if __name__ == '__main__':
    sys.exit(main())
