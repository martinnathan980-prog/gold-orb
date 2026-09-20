#!/usr/bin/env python3
"""
Lit un plan ELEC exporté en **DXF** — le format d'échange des outils de
dessin technique (AutoCAD, E3, DraftSight, LibreCAD…) — et en retire les
composants.

Un DXF est du texte : une suite de paires « code, valeur ». On y lit les
textes placés (TEXT, MTEXT, les attributs d'un bloc), les rectangles fermés
(une polyligne à quatre côtés, ou quatre traits qui se rejoignent), et les
**blocs insérés** — la façon dont un outil de dessin représente un
équipement, avec son repère dans un attribut. Puis la même règle que pour
les autres lecteurs : une boîte, un repère.

    python3 import/lire_dxf.py plan.dxf
    python3 import/lire_dxf.py plan.dxf --csv composants.csv

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from composants import (ErreurPlan, REPERE, composants, raconter,     # noqa: E402
                        lignes_csv, ecrire_csv)

# Les unités du dessin ($INSUNITS) ; ce qu'il faut pour convertir des millimètres.
MM_PAR_UNITE = {0: 1.0, 1: 25.4, 2: 304.8, 4: 1.0, 5: 10.0, 6: 1000.0}
COTE_MINI_MM = 3.0           # une boîte plus petite que 3 mm n'est pas un équipement
DISTANCE_MAXI_MM = 15.0      # un repère écrit à côté de sa boîte, pas à l'autre bout


# ---------------------------------------------------------------------------
#  Le fichier : des paires code / valeur, en sections et en entités
# ---------------------------------------------------------------------------
def paires(texte):
    lignes = texte.splitlines()
    for i in range(0, len(lignes) - 1, 2):
        try:
            yield int(lignes[i].strip()), lignes[i + 1].strip()
        except ValueError:
            continue


def sections(texte):
    """{ nom de section: [entités] } ; une entité est (type, { code: [valeurs] })."""
    resultat = {}
    courante, entites, entite = None, None, None
    for code, valeur in paires(texte):
        if code == 0:
            if valeur == 'SECTION':
                courante, entites, entite = None, [], None
            elif valeur == 'ENDSEC':
                if courante is not None:
                    resultat[courante] = entites
                courante, entites, entite = None, None, None
            elif valeur == 'EOF':
                break
            else:
                entite = (valeur, {})
                if entites is not None:
                    entites.append(entite)
            continue
        if code == 2 and courante is None and entites is not None and entite is None:
            courante = valeur
            continue
        if entite is not None:
            entite[1].setdefault(code, []).append(valeur)
    return resultat


def nombre(entite, code, defaut=0.0, rang=0):
    try:
        return float(entite[1][code][rang])
    except (KeyError, IndexError, ValueError):
        return defaut


def chaine(entite, code, defaut=''):
    valeurs = entite[1].get(code)
    return valeurs[0] if valeurs else defaut


def unites_du_texte(texte):
    m = re.search(r'\$INSUNITS\s*\n\s*70\s*\n\s*(\d+)', texte)
    return int(m.group(1)) if m else 4


# ---------------------------------------------------------------------------
#  Les textes
# ---------------------------------------------------------------------------
def nettoyer_mtext(brut):
    """Un MTEXT porte ses codes de mise en forme : on les retire."""
    texte = brut.replace('\\P', '\n').replace('\\~', ' ')
    texte = re.sub(r'\\[ACFHQTWfcpx][^;\\]*;', '', texte)
    texte = re.sub(r'\\[LlOoKk]', '', texte)
    texte = texte.replace('{', '').replace('}', '')
    texte = texte.replace('%%d', '°').replace('%%c', 'Ø').replace('%%p', '±')
    return texte


def position_texte(entite):
    """Le point d'un TEXT : le second point d'alignement quand il y en a un."""
    if entite[1].get(72) and chaine(entite, 72) != '0' and 11 in entite[1]:
        return nombre(entite, 11), nombre(entite, 21)
    if entite[1].get(73) and chaine(entite, 73) != '0' and 11 in entite[1]:
        return nombre(entite, 11), nombre(entite, 21)
    return nombre(entite, 10), nombre(entite, 20)


def textes_de(entites):
    textes = []
    for entite in entites:
        genre = entite[0]
        if genre == 'TEXT' or genre == 'ATTRIB' or genre == 'ATTDEF':
            x, y = position_texte(entite)
            valeur = chaine(entite, 1) if genre != 'ATTDEF' else chaine(entite, 2)
            for rang, ligne in enumerate(l.strip() for l in valeur.splitlines() if l.strip()):
                textes.append({'texte': ligne, 'x': x, 'y': y - rang * 1e-6})
        elif genre == 'MTEXT':
            x, y = nombre(entite, 10), nombre(entite, 20)
            valeur = nettoyer_mtext(''.join(entite[1].get(3, [])) + chaine(entite, 1))
            for rang, ligne in enumerate(l.strip() for l in valeur.splitlines() if l.strip()):
                textes.append({'texte': ligne, 'x': x, 'y': y - rang * 1e-6})
    return textes


# ---------------------------------------------------------------------------
#  Les rectangles : polylignes fermées, ou quatre traits qui se rejoignent
# ---------------------------------------------------------------------------
def rectangle_de_points(points, eps):
    if len(points) == 5 and abs(points[0][0] - points[4][0]) < eps and abs(points[0][1] - points[4][1]) < eps:
        points = points[:4]
    if len(points) != 4:
        return None
    xs, ys = sorted(p[0] for p in points), sorted(p[1] for p in points)
    if not (abs(xs[0] - xs[1]) < eps and abs(xs[2] - xs[3]) < eps and
            abs(ys[0] - ys[1]) < eps and abs(ys[2] - ys[3]) < eps):
        return None
    largeur, hauteur = xs[2] - xs[0], ys[2] - ys[0]
    if largeur < eps or hauteur < eps:
        return None
    return {'x': xs[0], 'y': ys[0], 'largeur': largeur, 'hauteur': hauteur}


def rectangles_de(entites, eps):
    rectangles = []
    horizontaux, verticaux = [], []
    sommets, polyligne_fermee = None, False
    for entite in entites:
        genre = entite[0]
        if genre == 'LWPOLYLINE':
            xs, ys = entite[1].get(10, []), entite[1].get(20, [])
            points = [(float(x), float(y)) for x, y in zip(xs, ys)]
            ferme = int(nombre(entite, 70)) & 1
            if ferme or (len(points) == 5):
                r = rectangle_de_points(points, eps)
                if r:
                    rectangles.append(r)
        elif genre == 'POLYLINE':
            sommets, polyligne_fermee = [], bool(int(nombre(entite, 70)) & 1)
        elif genre == 'VERTEX' and sommets is not None:
            sommets.append((nombre(entite, 10), nombre(entite, 20)))
        elif genre == 'SEQEND' and sommets is not None:
            if polyligne_fermee or len(sommets) == 5:
                r = rectangle_de_points(sommets, eps)
                if r:
                    rectangles.append(r)
            sommets = None
        elif genre == 'LINE':
            x0, y0 = nombre(entite, 10), nombre(entite, 20)
            x1, y1 = nombre(entite, 11), nombre(entite, 21)
            if abs(y0 - y1) < eps and abs(x0 - x1) >= eps:
                horizontaux.append((y0, min(x0, x1), max(x0, x1)))
            elif abs(x0 - x1) < eps and abs(y0 - y1) >= eps:
                verticaux.append((x0, min(y0, y1), max(y0, y1)))
    rectangles += rectangles_de_traits(horizontaux, verticaux, eps)
    return rectangles


def rectangles_de_traits(horizontaux, verticaux, eps):
    """Deux traits horizontaux de même étendue, et un trait vertical à
    chaque bout qui les relie : un rectangle."""
    par_x = {}
    for x, y0, y1 in verticaux:
        par_x.setdefault(round(x / eps), []).append((y0, y1))
    par_etendue = {}
    for y, x0, x1 in horizontaux:
        par_etendue.setdefault((round(x0 / eps), round(x1 / eps)), []).append((y, x0, x1))

    def relie(x, bas, haut):
        for cle in (round(x / eps) - 1, round(x / eps), round(x / eps) + 1):
            for y0, y1 in par_x.get(cle, []):
                if y0 <= bas + eps and y1 >= haut - eps:
                    return True
        return False
    rectangles = []
    for groupe in par_etendue.values():
        groupe.sort()
        for i, (y_bas, x0, x1) in enumerate(groupe):
            for y_haut, _, _ in groupe[i + 1:]:
                if y_haut - y_bas < eps:
                    continue
                if relie(x0, y_bas, y_haut) and relie(x1, y_bas, y_haut):
                    rectangles.append({'x': x0, 'y': y_bas, 'largeur': x1 - x0, 'hauteur': y_haut - y_bas})
                    break                      # le plus proche au-dessus ferme la boîte
    return rectangles


# ---------------------------------------------------------------------------
#  Les blocs : un équipement inséré, avec son repère en attribut
# ---------------------------------------------------------------------------
def blocs_de(entites_blocs, eps):
    """{ nom: { rectangles, textes, etendue } } — la définition de chaque bloc,
    dans son propre repère."""
    blocs, nom, courant = {}, None, None
    for entite in entites_blocs:
        if entite[0] == 'BLOCK':
            nom, courant = chaine(entite, 2), []
        elif entite[0] == 'ENDBLK':
            if nom is not None:
                blocs[nom] = _resume_bloc(courant, eps)
            nom, courant = None, None
        elif courant is not None:
            courant.append(entite)
    return blocs


def _resume_bloc(entites, eps):
    rectangles = rectangles_de(entites, eps)
    xs, ys = [], []
    for entite in entites:
        for code_x, code_y in ((10, 20), (11, 21)):
            for x, y in zip(entite[1].get(code_x, []), entite[1].get(code_y, [])):
                try:
                    xs.append(float(x))
                    ys.append(float(y))
                except ValueError:
                    continue
    etendue = (min(xs), min(ys), max(xs), max(ys)) if xs else None
    dessine = any(e[0] in ('LINE', 'LWPOLYLINE', 'POLYLINE', 'CIRCLE', 'ARC', 'SOLID', 'HATCH') for e in entites)
    return {'rectangles': rectangles, 'textes': textes_de([e for e in entites if e[0] != 'ATTDEF']),
            'etendue': etendue if dessine else None}


def insertions(entites, blocs, repere):
    """Chaque INSERT avec ses ATTRIB : rend (composants sûrs, boîtes restantes,
    textes restants) — sûr quand exactement un attribut est un repère."""
    surs, boites, textes = [], [], []
    i = 0
    while i < len(entites):
        entite = entites[i]
        i += 1
        if entite[0] != 'INSERT':
            continue
        attributs = []
        if chaine(entite, 66) == '1':
            while i < len(entites) and entites[i][0] != 'SEQEND':
                if entites[i][0] == 'ATTRIB':
                    attributs.append(entites[i])
                i += 1
            i += 1
        bloc = blocs.get(chaine(entite, 2))
        x, y = nombre(entite, 10), nombre(entite, 20)
        ex, ey = nombre(entite, 41, 1.0), nombre(entite, 42, 1.0)
        angle = nombre(entite, 50) % 360
        rect = None
        if bloc and bloc['etendue']:
            x0, y0, x1, y1 = bloc['etendue']
            coins = [(x0 * ex, y0 * ey), (x1 * ex, y1 * ey)]
            if angle in (90, 270):
                coins = [(-cy, cx) for cx, cy in coins]
            elif angle == 180:
                coins = [(-cx, -cy) for cx, cy in coins]
            xs, ys = sorted(c[0] for c in coins), sorted(c[1] for c in coins)
            rect = {'x': x + xs[0], 'y': y + ys[0], 'largeur': xs[1] - xs[0], 'hauteur': ys[1] - ys[0]}
        valeurs = textes_de(attributs)
        if bloc:
            for t in bloc['textes']:
                valeurs.append({'texte': t['texte'], 'x': x + t['x'] * ex, 'y': y + t['y'] * ey})
        reperes = [t for t in valeurs if repere.match(t['texte'])]
        if len(reperes) == 1:
            boite = rect or {'x': x - 0.5, 'y': y - 0.5, 'largeur': 1.0, 'hauteur': 1.0}
            surs.append(dict(boite, repere=reperes[0]['texte'], textes=[t['texte'] for t in valeurs], bloc=chaine(entite, 2)))
        else:
            if rect:
                boites.append(rect)
            textes += valeurs
    return surs, boites, textes


# ---------------------------------------------------------------------------
def lire(chemin, repere=REPERE, cote_mini=None, distance_maxi=None):
    """Le DXF, de bout en bout. Lève ErreurPlan s'il n'est pas lisible."""
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurPlan('Plan introuvable : %s' % fichier)
    brut = fichier.read_bytes()
    if brut[:4] == b'AC10' and b'\x00' in brut[:64]:
        raise ErreurPlan('%s est un DWG (le format fermé d\'AutoCAD), pas un DXF : dans l\'outil de '
                         'dessin, Enregistrer sous → DXF.' % fichier.name)
    for encodage in ('utf-8-sig', 'cp1252'):
        try:
            texte = brut.decode(encodage)
            break
        except UnicodeDecodeError:
            continue
    else:
        texte = brut.decode('latin-1')
    sect = sections(texte)
    if 'ENTITIES' not in sect:
        raise ErreurPlan('%s n\'a pas de section ENTITIES : ce n\'est pas un DXF.' % fichier.name)
    facteur = MM_PAR_UNITE.get(unites_du_texte(texte), 1.0)
    cote = cote_mini if cote_mini is not None else COTE_MINI_MM / facteur
    distance = distance_maxi if distance_maxi is not None else DISTANCE_MAXI_MM / facteur
    eps = cote / 4.0
    blocs = blocs_de(sect.get('BLOCKS', []), eps)
    entites = sect['ENTITIES']
    surs, boites_blocs, textes_blocs = insertions(entites, blocs, repere)
    textes = textes_de([e for e in entites if e[0] != 'ATTRIB']) + textes_blocs
    rectangles = rectangles_de(entites, eps) + boites_blocs
    resultat = composants(textes, rectangles, repere, cote, distance)
    resultat['trouves'] = surs + resultat['trouves']
    resultat['trouves'].sort(key=lambda c: (-c['y'], c['x']))
    resultat['boites'] += len(surs)
    resultat['entites'] = len(entites)
    resultat['resume'] = '%d entité(s), %d bloc(s) inséré(s)' % (len(entites), sum(1 for e in entites if e[0] == 'INSERT'))
    return resultat


def main(argv=None):
    parseur = argparse.ArgumentParser(description='Retire les composants d\'un plan ELEC exporté en DXF.')
    parseur.add_argument('plan', help='le fichier .dxf')
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
