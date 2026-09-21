#!/usr/bin/env python3
"""
Regarde un vrai extract — GATES, SEE, ou n'importe quel tableau — et en fait
une **fiche** : la forme du fichier, ses colonnes, et surtout ce qu'on ne peut
pas deviner de loin (les valeurs réelles de la colonne d'avancement, la forme
des références, le taux de remplissage).

C'est la pièce qui manque pour régler le tableau de bord sur les vraies
données. Elle se lance en une ligne et rend un texte à recopier.

    python diagnostic.py extract-HDK.xlsx
    python diagnostic.py extract-HDK.csv --anonyme
    python diagnostic.py extract.xlsx --onglet "Feuil2" --fiche fiche-HDK.txt

**Ce que la fiche contient** : les intitulés des colonnes, le nombre de lignes,
le taux de remplissage, et les valeurs distinctes des colonnes COURTES (moins
de 20 caractères — un avancement, un domaine, un ATA). **Ce qu'elle ne
contient pas** : aucun libellé, aucun commentaire, aucun texte libre, et
aucune ligne entière. Avec `--anonyme`, même les valeurs courtes sont
remplacées par leur forme (« AAA-999 »).

Lit les .csv (tous séparateurs, tous encodages) et les .xlsx, sans rien
installer : un .xlsx est une archive de fichiers XML, et la bibliothèque
standard sait ouvrir les deux.
"""

import argparse
import csv
import io
import os
import pathlib
import re
import sys
import unicodedata
import zipfile
import xml.etree.ElementTree as ET

LARGEUR_VALEUR = 20         # au-delà, c'est du texte libre : on ne le recopie pas
VALEURS_MONTREES = 12       # combien de valeurs distinctes on liste au plus
SEPARATEURS = ';,\t|'
# Une référence UD : code circuit, E, ATA et sous-ATA, A, séquence, solution, indice.
REFERENCE_UD = re.compile(r'^([A-Z]{2})E(\d{4})A(\d{3})(\d{3})([A-Z])$')


class ErreurDiagnostic(Exception):
    """Ce qui empêche de lire le fichier, dit en français."""


# ---------------------------------------------------------------------------
#  Lire un .xlsx sans rien installer : c'est une archive de XML
# ---------------------------------------------------------------------------
def _sans_espace_de_noms(balise):
    return balise.split('}', 1)[-1]


def _colonne_de(reference):
    """« BC12 » → 54 (l'index de la colonne, à partir de 0)."""
    lettres = ''.join(c for c in reference if c.isalpha())
    index = 0
    for lettre in lettres:
        index = index * 26 + (ord(lettre.upper()) - 64)
    return index - 1 if index else 0


def onglets_xlsx(chemin):
    """Les noms des onglets du classeur, dans l'ordre."""
    with zipfile.ZipFile(str(chemin)) as archive:
        return [f.get('name') for f in _feuilles(archive)]


def _feuilles(archive):
    classeur = ET.fromstring(archive.read('xl/workbook.xml'))
    for element in classeur.iter():
        if _sans_espace_de_noms(element.tag) == 'sheets':
            return [f for f in element if _sans_espace_de_noms(f.tag) == 'sheet']
    return []


def _chemin_feuille(archive, feuille):
    """Le fichier XML d'un onglet, retrouvé par sa relation — l'ordre des
    fichiers ne suit pas toujours l'ordre des onglets."""
    identifiant = None
    for cle, valeur in feuille.attrib.items():
        if cle.endswith('}id'):
            identifiant = valeur
    if identifiant and 'xl/_rels/workbook.xml.rels' in archive.namelist():
        relations = ET.fromstring(archive.read('xl/_rels/workbook.xml.rels'))
        for relation in relations:
            if relation.get('Id') == identifiant:
                cible = relation.get('Target', '')
                cible = cible[1:] if cible.startswith('/') else 'xl/' + cible.lstrip('./')
                if cible in archive.namelist():
                    return cible
    return None


def _chaines_partagees(archive):
    if 'xl/sharedStrings.xml' not in archive.namelist():
        return []
    racine = ET.fromstring(archive.read('xl/sharedStrings.xml'))
    chaines = []
    for element in racine:
        if _sans_espace_de_noms(element.tag) != 'si':
            continue
        morceaux = []
        for sous in element.iter():
            if _sans_espace_de_noms(sous.tag) == 't':
                morceaux.append(sous.text or '')
        chaines.append(''.join(morceaux))
    return chaines


def lire_xlsx(chemin, onglet=None, lignes_maxi=200000):
    """Les lignes d'un onglet, en cellules de texte. Sans rien installer."""
    try:
        archive = zipfile.ZipFile(str(chemin))
    except zipfile.BadZipFile:
        raise ErreurDiagnostic(
            '%s n\'est pas un vrai .xlsx (ce n\'est même pas une archive). Un .xls ancien ou un '
            'fichier renommé ne compte pas : réenregistrez-le en « Classeur Excel (*.xlsx) » ou '
            'en CSV.' % pathlib.Path(chemin).name)
    with archive:
        feuilles = _feuilles(archive)
        if not feuilles:
            raise ErreurDiagnostic('%s ne contient aucun onglet.' % pathlib.Path(chemin).name)
        choisie = None
        if onglet:
            for f in feuilles:
                if (f.get('name') or '').strip().lower() == onglet.strip().lower():
                    choisie = f
            if choisie is None:
                raise ErreurDiagnostic(
                    'Aucun onglet « %s ». Ceux du classeur : %s'
                    % (onglet, ', '.join(f.get('name') or '?' for f in feuilles)))
        else:
            choisie = feuilles[0]
        fichier = _chemin_feuille(archive, choisie) or 'xl/worksheets/sheet1.xml'
        if fichier not in archive.namelist():
            raise ErreurDiagnostic('L\'onglet « %s » n\'a pas de contenu lisible.' % choisie.get('name'))
        chaines = _chaines_partagees(archive)
        lignes = []
        for _, element in ET.iterparse(io.BytesIO(archive.read(fichier)), events=('end',)):
            if _sans_espace_de_noms(element.tag) != 'row':
                continue
            cellules = []
            for cellule in element:
                if _sans_espace_de_noms(cellule.tag) != 'c':
                    continue
                index = _colonne_de(cellule.get('r') or '')
                while len(cellules) < index:
                    cellules.append('')
                cellules.append(_valeur_cellule(cellule, chaines))
            lignes.append(cellules)
            element.clear()
            if len(lignes) >= lignes_maxi:
                break
        return lignes, choisie.get('name') or '?', [f.get('name') or '?' for f in feuilles]


def _valeur_cellule(cellule, chaines):
    genre = cellule.get('t')
    if genre == 'inlineStr':
        return ''.join(s.text or '' for s in cellule.iter()
                       if _sans_espace_de_noms(s.tag) == 't')
    valeur = None
    for sous in cellule:
        if _sans_espace_de_noms(sous.tag) == 'v':
            valeur = sous.text
    if valeur is None:
        return ''
    if genre == 's':
        try:
            return chaines[int(valeur)]
        except (ValueError, IndexError):
            return ''
    if genre == 'b':
        return 'VRAI' if valeur == '1' else 'FAUX'
    return valeur


# ---------------------------------------------------------------------------
#  Lire un .csv, quel que soit ce que l'outil a choisi
# ---------------------------------------------------------------------------
def decoder(brut, nom):
    if brut[:2] in (b'\xff\xfe', b'\xfe\xff'):
        for encodage in ('utf-16', 'utf-32'):
            try:
                return brut.decode(encodage)
            except (UnicodeDecodeError, LookupError):
                continue
    if b'\x00' in brut[:4096]:
        for encodage in ('utf-16-le', 'utf-16-be'):
            try:
                return brut.decode(encodage)
            except UnicodeDecodeError:
                continue
        raise ErreurDiagnostic('%s contient des octets nuls : ce n\'est pas un fichier texte.' % nom)
    for encodage in ('utf-8-sig', 'cp1252'):
        try:
            return brut.decode(encodage)
        except UnicodeDecodeError:
            continue
    return brut.decode('latin-1')


def separateur_de(texte):
    """Celui qui donne le plus souvent le même nombre de colonnes."""
    lignes = [l for l in texte.splitlines()[:60] if l.strip()]
    if not lignes:
        return ';'
    meilleur, note_max = ';', (-1, -1)
    for candidat in SEPARATEURS:
        comptes = {}
        for ligne in lignes:
            n = len(next(csv.reader([ligne], delimiter=candidat)))
            comptes[n] = comptes.get(n, 0) + 1
        dominant = max(comptes.items(), key=lambda x: (x[1], x[0]))
        if dominant[0] < 2:
            continue
        note = (dominant[1] / float(len(lignes)), dominant[0])
        if note > note_max:
            meilleur, note_max = candidat, note
    return meilleur


NOMS_ENCODAGES = {'utf-8-sig': 'UTF-8 avec BOM', 'cp1252': 'ANSI (Windows-1252)',
                  'utf-16': 'UTF-16', 'utf-16-le': 'UTF-16', 'utf-16-be': 'UTF-16',
                  'utf-32': 'UTF-32', 'latin-1': 'ISO-8859-1'}


def lire_csv(chemin):
    fichier = pathlib.Path(chemin)
    brut = fichier.read_bytes()
    if brut[:4] == b'PK\x03\x04':
        raise ErreurDiagnostic(
            '%s porte l\'extension .csv mais c\'est une archive — donc un .xlsx renommé. '
            'Relancez en donnant le vrai .xlsx, ou réenregistrez-le vraiment en CSV.' % fichier.name)
    texte = decoder(brut, fichier.name)
    separateur = separateur_de(texte)
    lignes = list(csv.reader(io.StringIO(texte), delimiter=separateur))
    return lignes, separateur


def lire(chemin, onglet=None):
    """Rend (lignes, description du format). Lève ErreurDiagnostic."""
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurDiagnostic('Fichier introuvable : %s' % fichier)
    tete = fichier.read_bytes()[:4]
    if tete == b'PK\x03\x04' or fichier.suffix.lower() in ('.xlsx', '.xlsm'):
        lignes, nom_onglet, tous = lire_xlsx(fichier, onglet)
        format_lu = 'classeur Excel (.xlsx), onglet « %s »' % nom_onglet
        if len(tous) > 1:
            format_lu += ' — le classeur en a %d : %s' % (len(tous), ', '.join(tous))
        return lignes, format_lu
    if tete == b'\xd0\xcf\x11\xe0':
        raise ErreurDiagnostic(
            '%s est un vieux classeur Excel (.xls). Ouvrez-le et faites « Enregistrer sous → '
            'Classeur Excel (*.xlsx) », ou « CSV (séparateur point-virgule) ».' % fichier.name)
    lignes, separateur = lire_csv(fichier)
    nom = {';': 'point-virgule', ',': 'virgule', '\t': 'tabulation', '|': 'barre verticale'}
    return lignes, 'CSV, séparateur %s' % nom.get(separateur, repr(separateur))


# ---------------------------------------------------------------------------
#  Comprendre la forme du tableau
# ---------------------------------------------------------------------------
def sans_accents(texte):
    return ''.join(c for c in unicodedata.normalize('NFD', texte or '')
                   if unicodedata.category(c) != 'Mn').lower()


def ligne_non_vide(ligne):
    return any(str(c).strip() for c in ligne)


def detecter_entete(lignes):
    """Rend (index de la ligne des intitulés, index de la ligne des groupes ou None).

    On cherche la première ligne qui a beaucoup d'intitulés distincts et non
    vides, et dont la suivante ressemble à des données. Une ligne de groupes
    fusionnés au-dessus est reconnue : elle est plus creuse que la suivante.
    """
    meilleur, note_max = 0, -1.0
    for rang in range(min(12, len(lignes))):
        ligne = lignes[rang]
        remplies = [str(c).strip() for c in ligne if str(c).strip()]
        if len(remplies) < 3:
            continue
        distincts = len(set(remplies))
        suivantes = [l for l in lignes[rang + 1:rang + 6] if ligne_non_vide(l)]
        if not suivantes:
            continue
        largeur = max(len(l) for l in lignes[:rang + 6]) or 1
        note = (distincts / float(largeur)) + (0.3 if len(suivantes) >= 3 else 0)
        if note > note_max:
            meilleur, note_max = rang, note
    groupes = None
    if meilleur > 0:
        au_dessus = [str(c).strip() for c in lignes[meilleur - 1] if str(c).strip()]
        ici = [str(c).strip() for c in lignes[meilleur] if str(c).strip()]
        # Une ligne de groupes a peu de mots différents : soit elle est fusionnée
        # (le nom une fois, puis des trous), soit l'export le répète sur chaque
        # colonne du groupe. Dans les deux cas, son vocabulaire est bien plus
        # petit que celui des intitulés.
        if au_dessus and len(set(au_dessus)) <= max(2, len(set(ici)) / 2.0):
            groupes = meilleur - 1
    return meilleur, groupes


ROLES = [
    ('la référence du plan', ('reference ud', 'reference', 'ref ud', 'name', 'ud')),
    ('l\'avancement suivi', ('avancement',)),
    ('le domaine', ('domaine', 'propa', 'perimetre')),
    ('l\'ATA', ('ata', 'chapitre')),
    ('le code circuit', ('cc', 'code circuit')),
    ('l\'ECP', ('ecp',)),
    ('la date de création', ('date creation', 'date de creation', 'creation')),
    ('la validation', ('validation',)),
]


def role_de(titre, groupe):
    entier = sans_accents((groupe + ' ' + titre).strip())
    titre_seul = sans_accents(titre)
    for role, mots in ROLES:
        for mot in mots:
            if titre_seul == mot or titre_seul.startswith(mot + ' ') or (' ' + mot + ' ') in (' ' + entier + ' '):
                return role
    return ''


def forme_de(valeur):
    """« TFE2130A600001A » → « AAA9999A999999A » : la forme, pas la valeur."""
    forme = re.sub(r'[0-9]', '9', str(valeur))
    forme = re.sub(r'[A-ZÀ-Ý]', 'A', forme)
    forme = re.sub(r'[a-zà-ÿ]', 'a', forme)
    if len(forme) <= 24:
        return forme                    # une référence se lit en entier
    return re.sub(r'(.)\1{3,}', lambda m: m.group(1) + '…', forme)


def analyser(lignes, anonyme=False):
    """La fiche, en données : format du tableau, colonnes, rôles, valeurs."""
    lignes = [l for l in lignes if ligne_non_vide(l)]
    if not lignes:
        raise ErreurDiagnostic('Le fichier ne contient aucune ligne remplie.')
    rang_titres, rang_groupes = detecter_entete(lignes)
    titres = [str(c).strip() for c in lignes[rang_titres]]
    largeur = max(len(l) for l in lignes)
    while len(titres) < largeur:
        titres.append('')
    groupes = ['' for _ in titres]
    if rang_groupes is not None:
        courant = ''
        for i in range(largeur):
            cellule = str(lignes[rang_groupes][i]).strip() if i < len(lignes[rang_groupes]) else ''
            courant = cellule or courant
            groupes[i] = courant
    donnees = lignes[rang_titres + 1:]
    colonnes = []
    for i in range(largeur):
        valeurs = [str(l[i]).strip() for l in donnees if i < len(l) and str(l[i]).strip()]
        distinctes = []
        for v in valeurs:
            if v not in distinctes:
                distinctes.append(v)
            if len(distinctes) > 400:
                break
        courtes = [v for v in distinctes if len(v) <= LARGEUR_VALEUR]
        montrables = len(courtes) == len(distinctes) and len(distinctes) <= 400
        colonnes.append({
            'index': i + 1,
            'titre': titres[i],
            'groupe': groupes[i],
            'role': role_de(titres[i], groupes[i]),
            'remplies': len(valeurs),
            'distinctes': len(distinctes),
            'exemples': [forme_de(v) if anonyme or len(v) > LARGEUR_VALEUR else v
                         for v in distinctes[:4]],
            'toutes': ([forme_de(v) for v in distinctes] if anonyme else distinctes) if montrables else None,
            'longueur_maxi': max([len(v) for v in valeurs] or [0]),
        })
    return {
        'lignes_totales': len(lignes),
        'rang_titres': rang_titres + 1,
        'rang_groupes': (rang_groupes + 1) if rang_groupes is not None else None,
        'plans': len(donnees),
        'largeur': largeur,
        'colonnes': colonnes,
        'anonyme': anonyme,
    }


def references(analyse, donnees):
    """Ce que valent les références : anatomie reconnue, séquences, indices."""
    col = None
    for c in analyse['colonnes']:
        if c['role'] == 'la référence du plan':
            col = c['index'] - 1
            break
    if col is None:
        return None
    brut = [str(l[col]).strip() for l in donnees if col < len(l) and str(l[col]).strip()]
    reconnues = [REFERENCE_UD.match(r.upper()) for r in brut]
    bonnes = [m for m in reconnues if m]
    formes = {}
    for r, m in zip(brut, reconnues):
        if not m:
            formes[forme_de(r)] = formes.get(forme_de(r), 0) + 1
    return {
        'total': len(brut),
        'distinctes': len(set(brut)),
        'anatomie': len(bonnes),
        'sequences': sorted(set(m.group(3) for m in bonnes)),
        'indices': sorted(set(m.group(5) for m in bonnes)),
        'circuits': sorted(set(m.group(1) for m in bonnes))[:20],
        'autres_formes': sorted(formes.items(), key=lambda x: -x[1])[:6],
        'exemple': ('' if analyse['anonyme'] else (bonnes[0].group(0) if bonnes else (brut[0] if brut else ''))),
    }


# ---------------------------------------------------------------------------
#  La fiche
# ---------------------------------------------------------------------------
def raconter(analyse, refs, nom, format_lu, taille):
    l = []
    l.append('FICHE D\'EXTRACT — %s' % nom)
    l.append('=' * 66)
    l.append('')
    l.append('Format lu    : %s' % format_lu)
    l.append('Taille       : %s' % _taille(taille))
    l.append('Lignes       : %d au total, dont %d plans' % (analyse['lignes_totales'], analyse['plans']))
    l.append('Colonnes     : %d' % analyse['largeur'])
    l.append('En-tête      : les intitulés sont ligne %d%s' % (
        analyse['rang_titres'],
        (', les groupes ligne %d' % analyse['rang_groupes']) if analyse['rang_groupes'] else
        ' (aucune ligne de groupes au-dessus)'))
    vides = [c['index'] for c in analyse['colonnes'] if not c['titre'] and not c['remplies']]
    if vides:
        l.append('Colonnes sans intitulé ET vides : %s' % ', '.join(str(v) for v in vides))
    l.append('')
    l.append('LES COLONNES QUI COMMANDENT LE TABLEAU DE BORD')
    l.append('-' * 66)
    trouves = set()
    for role, _ in ROLES:
        c = next((c for c in analyse['colonnes'] if c['role'] == role), None)
        if c:
            trouves.add(role)
            l.append('  %-24s colonne %-4d « %s »%s'
                     % (role, c['index'], c['titre'],
                        (' (groupe « %s »)' % c['groupe']) if c['groupe'] else ''))
        else:
            l.append('  %-24s INTROUVABLE — à désigner à la main' % role)
    l.append('')
    avancement = next((c for c in analyse['colonnes'] if c['role'] == 'l\'avancement suivi'), None)
    if avancement:
        l.append('LES VALEURS RÉELLES DE LA COLONNE D\'AVANCEMENT   (la question nº 1)')
        l.append('-' * 66)
        l.append('  %d plans renseignés sur %d — %d cellule(s) vide(s)'
                 % (avancement['remplies'], analyse['plans'], analyse['plans'] - avancement['remplies']))
        if avancement['toutes'] is not None:
            l.append('  %d valeur(s) distincte(s) :' % avancement['distinctes'])
            for v in avancement['toutes'][:60]:
                l.append('      %s' % v)
            if avancement['distinctes'] > 60:
                l.append('      … et %d autre(s)' % (avancement['distinctes'] - 60))
        else:
            l.append('  %d valeurs distinctes, trop longues pour être recopiées ici.'
                     % avancement['distinctes'])
        l.append('')
    if refs:
        l.append('LES RÉFÉRENCES')
        l.append('-' * 66)
        l.append('  %d références, %d distinctes' % (refs['total'], refs['distinctes']))
        l.append('  %d suivent l\'anatomie attendue (CC + E + ATA + A + séquence + solution + indice)'
                 % refs['anatomie'])
        if refs['exemple']:
            l.append('  exemple : %s' % refs['exemple'])
        if refs['sequences']:
            l.append('  séquences rencontrées : %s' % ', '.join(refs['sequences']))
        if refs['indices']:
            l.append('  indices rencontrés    : %s' % ', '.join(refs['indices']))
        if refs['circuits']:
            l.append('  codes circuit         : %s' % ', '.join(refs['circuits']))
        if refs['autres_formes']:
            l.append('  formes NON reconnues  : %s'
                     % ', '.join('%s (×%d)' % (f, n) for f, n in refs['autres_formes']))
        l.append('')
    l.append('TOUTES LES COLONNES')
    l.append('-' * 66)
    l.append('  nº  remplies  distinctes  groupe / intitulé')
    for c in analyse['colonnes']:
        taux = (100.0 * c['remplies'] / analyse['plans']) if analyse['plans'] else 0
        titre = c['titre'] or '(sans intitulé)'
        if c['groupe']:
            titre = c['groupe'] + ' / ' + titre
        l.append('  %-3d %5.0f%%     %6d      %s' % (c['index'], taux, c['distinctes'], titre))
        if c['toutes'] is not None and 1 <= c['distinctes'] <= VALEURS_MONTREES and c['remplies']:
            l.append('        valeurs : %s' % ' · '.join(c['toutes']))
        elif c['exemples'] and c['remplies']:
            l.append('        exemples : %s%s' % (' · '.join(c['exemples']),
                                                  ' …' if c['distinctes'] > 4 else ''))
    l.append('')
    l.append('-' * 66)
    l.append('Cette fiche ne contient aucun libellé, aucun commentaire, aucun texte')
    l.append('libre et aucune ligne entière : seulement des intitulés, des comptes,')
    l.append('et les valeurs courtes (20 caractères au plus) des colonnes à petit')
    l.append('vocabulaire.%s' % (' Les valeurs sont remplacées par leur forme.'
                                 if analyse['anonyme'] else
                                 ' Relisez-la avant de l\'envoyer ; --anonyme masque les valeurs.'))
    return '\n'.join(l)


def _taille(octets):
    for unite in ('octets', 'Ko', 'Mo'):
        if octets < 1024 or unite == 'Mo':
            return '%.0f %s' % (octets, unite) if unite == 'octets' else '%.1f %s' % (octets, unite)
        octets /= 1024.0


def main(argv=None):
    parseur = argparse.ArgumentParser(
        description='Fait la fiche d\'un extract réel : colonnes, valeurs, références.')
    parseur.add_argument('fichier', help='l\'extract (.xlsx ou .csv)')
    parseur.add_argument('--onglet', help='l\'onglet du classeur (sinon : le premier)')
    parseur.add_argument('--fiche', help='écrire la fiche dans ce fichier (sinon : à côté de l\'extract)')
    parseur.add_argument('--anonyme', action='store_true',
                         help='remplacer chaque valeur par sa forme (AAA-999)')
    parseur.add_argument('--sans-fichier', action='store_true', help='afficher seulement, n\'écrire rien')
    args = parseur.parse_args(argv)
    try:
        chemin = pathlib.Path(args.fichier)
        lignes, format_lu = lire(chemin, args.onglet)
        analyse = analyser(lignes, args.anonyme)
        donnees = [l for l in lignes if ligne_non_vide(l)][analyse['rang_titres']:]
        fiche = raconter(analyse, references(analyse, donnees), chemin.name, format_lu,
                         chemin.stat().st_size)
        print(fiche)
        if not args.sans_fichier:
            sortie = pathlib.Path(args.fiche) if args.fiche else chemin.with_name('fiche-' + chemin.stem + '.txt')
            sortie.write_text(fiche + '\n', encoding='utf-8')
            print('\n→ Fiche écrite dans %s' % sortie)
            print('  (c\'est ce fichier qu\'il faut renvoyer — relisez-le d\'abord.)')
        return 0
    except ErreurDiagnostic as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
