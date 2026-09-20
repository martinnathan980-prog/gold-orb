#!/usr/bin/env python3
"""
Lit un plan ELEC dessiné sous **Visio** et en retire les composants.

Un fichier `.vsdx` (ou `.vsdm`) est une archive ZIP de fichiers XML : chaque
page y décrit ses formes, avec leur position, leur taille, leur texte, et le
gabarit dont elles héritent. Il n'y a donc rien à reconnaître : on lit ce
qui est écrit, et on regarde quel texte est dans quelle forme — la même
règle que pour un PDF de dessin.

Le vieux format `.vdx` (Visio 2003-2010, du XML à plat) se lit aussi. Le
format binaire `.vsd`, lui, ne se lit pas sans Visio : si Visio est sur le
poste, le programme lui demande d'enregistrer une copie en `.vsdx` ; sinon
il dit quoi faire.

    python3 import/lire_visio.py plan.vsdx
    python3 import/lire_visio.py plan.vsdx --csv composants.csv

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import pathlib
import re
import sys
import zipfile
import xml.etree.ElementTree as ET

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from composants import (ErreurPlan, REPERE, COTE_MINI, DISTANCE_MAXI, composants,   # noqa: E402
                        raconter, lignes_csv, ecrire_csv)

ESPACE_2012 = 'http://schemas.microsoft.com/office/visio/2012/main'
ESPACE_2003 = 'http://schemas.microsoft.com/visio/2003/core'
ESPACE_RELS = 'http://schemas.openxmlformats.org/package/2006/relationships'
POINTS_PAR_POUCE = 72.0      # Visio compte en pouces ; le socle commun en points


# ---------------------------------------------------------------------------
#  Les formes d'une page : position absolue, taille, texte, nature
# ---------------------------------------------------------------------------
def _nom_local(element):
    return element.tag.split('}', 1)[-1]


def _enfants(element, nom):
    return [e for e in element if _nom_local(e) == nom]


def _enfant(element, nom):
    for e in element:
        if _nom_local(e) == nom:
            return e
    return None


def cellules(shape):
    """Les cellules d'une forme — `<Cell N='PinX' V='1.5'/>` (2012) ou
    `<XForm><PinX>1.5</PinX>…` (2003) — en nombres."""
    valeurs = {}
    for cell in _enfants(shape, 'Cell'):
        try:
            valeurs[cell.get('N')] = float(cell.get('V'))
        except (TypeError, ValueError):
            continue
    for bloc in ('XForm', 'XForm1D'):
        xform = _enfant(shape, bloc)
        if xform is not None:
            for e in xform:
                try:
                    valeurs[_nom_local(e)] = float(e.text)
                except (TypeError, ValueError):
                    continue
    return valeurs


def a_une_geometrie(shape):
    """Vrai si la forme trace quelque chose (elle-même ou ses sous-formes)."""
    for e in shape.iter():
        nom = _nom_local(e)
        if nom == 'Geom' or (nom == 'Section' and e.get('N') == 'Geometry'):
            return True
    return False


def texte_de(shape):
    texte = _enfant(shape, 'Text')
    if texte is None:
        return ''
    return ''.join(texte.itertext())


def formes(conteneur, gabarits, origine=(0.0, 0.0)):
    """Toutes les formes de `conteneur` (un `<Shapes>`), groupes ouverts,
    en pouces absolus : [{ x, y, largeur, hauteur, texte, boite, une_d }]."""
    sortie = []
    for shape in _enfants(conteneur, 'Shape'):
        c = cellules(shape)
        gabarit = gabarits.get(shape.get('Master'), {})
        herite = gabarit.get('cellules', {})

        def valeur(nom, defaut=0.0):
            if nom in c:
                return c[nom]
            return herite.get(nom, defaut)
        largeur, hauteur = valeur('Width'), valeur('Height')
        pin_x, pin_y = valeur('PinX'), valeur('PinY')
        loc_x, loc_y = valeur('LocPinX', largeur / 2.0), valeur('LocPinY', hauteur / 2.0)
        x0, y0 = origine[0] + pin_x - loc_x, origine[1] + pin_y - loc_y
        une_d = 'BeginX' in c or gabarit.get('une_d', False)
        geometrie = a_une_geometrie(shape) or gabarit.get('geometrie', False)
        sortie.append({'x': x0, 'y': y0, 'largeur': largeur, 'hauteur': hauteur,
                       'texte': texte_de(shape), 'boite': geometrie and not une_d, 'une_d': une_d})
        sous = _enfant(shape, 'Shapes')
        if sous is not None:
            sortie += formes(sous, gabarits, (x0, y0))
    return sortie


# ---------------------------------------------------------------------------
#  .vsdx : l'archive, ses pages, ses gabarits
# ---------------------------------------------------------------------------
def _relations(archive, chemin_rels):
    """{ rId: cible } d'un fichier .rels — vide s'il n'existe pas."""
    if chemin_rels not in archive.namelist():
        return {}
    racine = ET.fromstring(archive.read(chemin_rels))
    return {r.get('Id'): r.get('Target') for r in racine if _nom_local(r) == 'Relationship'}


def _cible(rel, dossier):
    if rel is None:
        return None
    return dossier + '/' + rel if not rel.startswith('/') else rel.lstrip('/')


def _id_relation(element):
    for e in element:
        if _nom_local(e) == 'Rel':
            for attribut, valeur in e.attrib.items():
                if attribut.endswith('}id') or attribut == 'id':
                    return valeur
    return None


def gabarits_vsdx(archive):
    """{ ID du gabarit: { cellules, geometrie, une_d } }, pour ce que les
    formes n'écrivent pas elles-mêmes."""
    if 'visio/masters/masters.xml' not in archive.namelist():
        return {}
    racine = ET.fromstring(archive.read('visio/masters/masters.xml'))
    rels = _relations(archive, 'visio/masters/_rels/masters.xml.rels')
    gabarits = {}
    for master in _enfants(racine, 'Master'):
        fichier = _cible(rels.get(_id_relation(master)), 'visio/masters')
        if not fichier or fichier not in archive.namelist():
            continue
        contenu = ET.fromstring(archive.read(fichier))
        shapes = _enfant(contenu, 'Shapes')
        premiere = _enfants(shapes, 'Shape')[0] if shapes is not None and _enfants(shapes, 'Shape') else None
        if premiere is None:
            continue
        gabarits[master.get('ID')] = {'cellules': cellules(premiere),
                                      'geometrie': a_une_geometrie(premiere),
                                      'une_d': 'BeginX' in cellules(premiere)}
    return gabarits


def pages_vsdx(archive):
    """[(nom de la page, élément <Shapes>)] dans l'ordre du document."""
    if 'visio/pages/pages.xml' not in archive.namelist():
        raise ErreurPlan('Cette archive n\'est pas un dessin Visio : pas de visio/pages/pages.xml.')
    racine = ET.fromstring(archive.read('visio/pages/pages.xml'))
    rels = _relations(archive, 'visio/pages/_rels/pages.xml.rels')
    pages = []
    for page in _enfants(racine, 'Page'):
        fichier = _cible(rels.get(_id_relation(page)), 'visio/pages')
        if not fichier or fichier not in archive.namelist():
            continue
        contenu = ET.fromstring(archive.read(fichier))
        shapes = _enfant(contenu, 'Shapes')
        pages.append((page.get('Name') or fichier, shapes if shapes is not None else ET.Element('Shapes')))
    if not pages:
        raise ErreurPlan('Ce dessin Visio n\'a aucune page lisible.')
    return pages


def lire_vsdx(chemin):
    try:
        archive = zipfile.ZipFile(str(chemin))
    except zipfile.BadZipFile:
        raise ErreurPlan('%s n\'est pas une archive Visio (.vsdx). Un .vsd renommé ne le devient pas : '
                         'enregistrer sous… → Dessin Visio (*.vsdx).' % pathlib.Path(chemin).name)
    with archive:
        gabarits = gabarits_vsdx(archive)
        return [(nom, formes(shapes, gabarits)) for nom, shapes in pages_vsdx(archive)]


# ---------------------------------------------------------------------------
#  .vdx : le XML à plat de Visio 2003-2010
# ---------------------------------------------------------------------------
def lire_vdx(chemin):
    try:
        racine = ET.parse(str(chemin)).getroot()
    except ET.ParseError as err:
        raise ErreurPlan('%s n\'est pas un XML Visio lisible : %s' % (pathlib.Path(chemin).name, err))
    gabarits = {}
    masters = _enfant(racine, 'Masters')
    if masters is not None:
        for master in _enfants(masters, 'Master'):
            shapes = _enfant(master, 'Shapes')
            premiere = _enfants(shapes, 'Shape')[0] if shapes is not None and _enfants(shapes, 'Shape') else None
            if premiere is not None:
                gabarits[master.get('ID')] = {'cellules': cellules(premiere),
                                              'geometrie': a_une_geometrie(premiere),
                                              'une_d': 'BeginX' in cellules(premiere)}
    pages = []
    conteneur = _enfant(racine, 'Pages')
    for page in (_enfants(conteneur, 'Page') if conteneur is not None else []):
        shapes = _enfant(page, 'Shapes')
        pages.append((page.get('Name') or 'Page', formes(shapes if shapes is not None else ET.Element('Shapes'), gabarits)))
    if not pages:
        raise ErreurPlan('Ce dessin Visio n\'a aucune page.')
    return pages


# ---------------------------------------------------------------------------
#  .vsd : le format binaire, que seul Visio sait ouvrir
# ---------------------------------------------------------------------------
def convertir_vsd(chemin):
    """Demande à Visio, s'il est sur le poste, d'enregistrer une copie .vsdx
    à côté du fichier — et la rend. Sinon dit quoi faire."""
    source = pathlib.Path(chemin)
    cible = source.with_suffix('.vsdx')
    if cible.exists():
        return cible
    try:
        import win32com.client                                   # noqa: F401
    except ImportError:
        raise ErreurPlan(
            '%s est au vieux format binaire de Visio, que seul Visio sait ouvrir. Deux façons : '
            'dans Visio, Fichier → Enregistrer sous → Dessin Visio (*.vsdx) ; ou installer le '
            'paquet Python pywin32 (pip install pywin32 — pas d\'exécutable) et relancer : le '
            'programme demandera lui-même la conversion à Visio.' % source.name)
    try:
        visio = win32com.client.Dispatch('Visio.InvisibleApp')
    except Exception as err:
        raise ErreurPlan('Visio ne répond pas sur ce poste (%s) : convertir %s en .vsdx à la main.'
                         % (err, source.name))
    try:
        document = visio.Documents.Open(str(source.resolve()))
        document.SaveAs(str(cible.resolve()))
        document.Close()
    finally:
        visio.Quit()
    return cible


# ---------------------------------------------------------------------------
def lire(chemin, repere=REPERE, cote_mini=COTE_MINI, distance_maxi=DISTANCE_MAXI):
    """Le dessin Visio, de bout en bout, page après page. Lève ErreurPlan."""
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurPlan('Plan introuvable : %s' % fichier)
    suffixe = fichier.suffix.lower()
    if suffixe == '.vsd':
        fichier = convertir_vsd(fichier)
        suffixe = '.vsdx'
    if suffixe == '.vdx':
        pages = lire_vdx(fichier)
    else:
        pages = lire_vsdx(fichier)
    resultat = {'trouves': [], 'douteux': [], 'orphelins': [], 'incertains': [],
                'boites': 0, 'cadres': 0, 'formes': 0, 'pages': len(pages)}
    for numero, (nom, liste) in enumerate(pages, 1):
        textes, rectangles = [], []
        for f in liste:
            x, y = f['x'] * POINTS_PAR_POUCE, f['y'] * POINTS_PAR_POUCE
            largeur, hauteur = f['largeur'] * POINTS_PAR_POUCE, f['hauteur'] * POINTS_PAR_POUCE
            if f['boite']:
                rectangles.append({'x': round(x, 2), 'y': round(y, 2),
                                   'largeur': round(largeur, 2), 'hauteur': round(hauteur, 2)})
            lignes = [l.strip() for l in f['texte'].splitlines() if l.strip()]
            for rang, ligne in enumerate(lignes):
                # Chaque ligne de texte au centre de sa forme, la première un
                # peu plus haut : l'ordre de lecture est conservé.
                textes.append({'texte': ligne, 'x': round(x + largeur / 2.0, 2),
                               'y': round(y + hauteur / 2.0 - rang * 0.01, 2)})
        r = composants(textes, rectangles, repere, cote_mini, distance_maxi)
        for cle in ('trouves', 'douteux', 'orphelins', 'incertains'):
            for element in r[cle]:
                element['page'] = numero
            resultat[cle] += r[cle]
        resultat['boites'] += r['boites']
        resultat['cadres'] += r['cadres']
        resultat['formes'] += len(liste)
    resultat['resume'] = '%d forme(s)' % resultat['formes']
    return resultat


def main(argv=None):
    parseur = argparse.ArgumentParser(description='Retire les composants d\'un plan ELEC dessiné sous Visio.')
    parseur.add_argument('plan', help='le fichier .vsdx, .vsdm, .vdx ou .vsd')
    parseur.add_argument('--csv', help='écrire ce qui a été vu dans ce fichier')
    parseur.add_argument('--repere', help='l\'expression qui reconnaît un repère électrique')
    args = parseur.parse_args(argv)
    try:
        motif = re.compile(args.repere) if args.repere else REPERE
        resultat = lire(args.plan, motif)
        nom = pathlib.Path(args.plan).name
        print(raconter(resultat, nom))
        if args.csv:
            ecrire_csv(args.csv, lignes_csv(resultat, nom))
            print('  → %s' % args.csv)
        return 0
    except ErreurPlan as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
