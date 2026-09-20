#!/usr/bin/env python3
"""
Lit un plan ELEC au format PDF et en retire les composants.

**Ce que ce programme fait, et ce qu'il ne fait pas.** Un PDF sorti d'un outil
de dessin n'est pas une image : le texte y est écrit comme du texte, avec ses
coordonnées, et les boîtes comme des rectangles. Il n'y a donc rien à
reconnaître, rien à deviner — on lit ce qui est écrit, et on regarde ce qui
est dedans. C'est pour cela que le résultat est sûr, et surtout
**vérifiable** : le programme dit toujours combien de boîtes il a trouvées,
combien portent un repère unique, et lesquelles sont douteuses.

Un PDF **scanné** (une photo de papier), lui, ne contient aucun texte : ce
lecteur le dit franchement au lieu de rendre n'importe quoi, et renvoie vers
`lire_scan.py`, qui reconnaît les caractères. `lire_composants.py` fait ce
choix tout seul.

    python3 import/lire_plan.py plan.pdf
    python3 import/lire_plan.py plan.pdf --csv composants.csv
    python3 import/lire_plan.py plan.pdf --repere "^[0-9]{1,3}[A-Z]{1,3}[0-9]{0,3}$"

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import pathlib
import re
import sys
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from composants import (ErreurPlan, REPERE, COTE_MINI, DISTANCE_MAXI,      # noqa: E402,F401
                        composants, dedans, distance_au_bord, raconter,
                        lignes_csv, ecrire_csv)


# ---------------------------------------------------------------------------
#  Le fichier : objets, flux, décompression
# ---------------------------------------------------------------------------
def flux_du_pdf(donnees):
    """Tous les flux du fichier, décompressés quand on sait le faire."""
    if not donnees.startswith(b'%PDF'):
        raise ErreurPlan('Ce fichier ne commence pas par %PDF : ce n\'est pas un PDF.')
    flux = []
    for trouvaille in re.finditer(rb'stream\r?\n', donnees):
        debut = trouvaille.end()
        fin = donnees.find(b'endstream', debut)
        if fin == -1:
            continue
        brut = donnees[debut:fin].rstrip(b'\r\n')
        entete = donnees[max(0, trouvaille.start() - 400):trouvaille.start()]
        if b'/FlateDecode' in entete:
            try:
                brut = zlib.decompress(brut)
            except zlib.error:
                try:
                    brut = zlib.decompressobj().decompress(brut)
                except zlib.error:
                    continue
        elif b'/DCTDecode' in entete or b'/JPXDecode' in entete or b'/CCITTFaxDecode' in entete:
            continue                       # une image : rien à lire dedans
        flux.append(brut)
    return flux


def flux_de_dessin(flux):
    """Les flux qui décrivent un dessin : ceux qui portent du texte ou des traits."""
    gardes = []
    for f in flux:
        if b'BT' in f or b' re' in f or b' l\n' in f or b' l ' in f:
            gardes.append(f)
    return gardes


# ---------------------------------------------------------------------------
#  Les chaînes PDF
# ---------------------------------------------------------------------------
ECHAPPES = {b'n': b'\n', b'r': b'\r', b't': b'\t', b'b': b'\b', b'f': b'\f',
            b'(': b'(', b')': b')', b'\\': b'\\'}


def texte_litteral(brut):
    """« (Repère \\(1\\)) » devient « Repère (1) »."""
    sortie = bytearray()
    i = 0
    while i < len(brut):
        o = brut[i:i + 1]
        if o == b'\\' and i + 1 < len(brut):
            suivant = brut[i + 1:i + 2]
            if suivant in ECHAPPES:
                sortie += ECHAPPES[suivant]
                i += 2
                continue
            if suivant.isdigit():                       # \101 : un octet en octal
                chiffres = b''
                while len(chiffres) < 3 and i + 1 + len(chiffres) < len(brut) and \
                        brut[i + 1 + len(chiffres):i + 2 + len(chiffres)].isdigit():
                    chiffres += brut[i + 1 + len(chiffres):i + 2 + len(chiffres)]
                sortie.append(int(chiffres, 8) & 0xFF)
                i += 1 + len(chiffres)
                continue
            if suivant in (b'\n', b'\r'):               # coupure de ligne : ignorée
                i += 2
                continue
            sortie += suivant
            i += 2
            continue
        sortie += o
        i += 1
    return bytes(sortie)


def texte_hexa(brut):
    chiffres = re.sub(rb'[^0-9A-Fa-f]', b'', brut)
    if len(chiffres) % 2:
        chiffres += b'0'
    return bytes.fromhex(chiffres.decode('ascii'))


def en_caracteres(octets):
    """Du texte lisible : UTF-16 quand le PDF le marque, sinon l'encodage occidental."""
    if octets.startswith(b'\xfe\xff'):
        return octets[2:].decode('utf-16-be', 'replace')
    return octets.decode('cp1252', 'replace')


# ---------------------------------------------------------------------------
#  Le contenu : texte placé, rectangles
# ---------------------------------------------------------------------------
def multiplier(a, b):
    """Deux matrices [a b c d e f] l'une après l'autre."""
    return [a[0] * b[0] + a[1] * b[2], a[0] * b[1] + a[1] * b[3],
            a[2] * b[0] + a[3] * b[2], a[2] * b[1] + a[3] * b[3],
            a[4] * b[0] + a[5] * b[2] + b[4], a[4] * b[1] + a[5] * b[3] + b[5]]


def applique(m, x, y):
    return (m[0] * x + m[2] * y + m[4], m[1] * x + m[3] * y + m[5])


# Les jetons d'un flux de dessin, dans cet ordre : une chaîne littérale entre
# parenthèses, une chaîne hexadécimale, l'ouverture et la fermeture d'un
# tableau, un nombre, un nom (/F1), un opérateur (Tj, re, cm…).
JETON = re.compile(rb"\((?:\\.|[^\\()])*\)|<[0-9A-Fa-f\s]*>|\[|\]|[-+]?[0-9]*\.?[0-9]+|/[^\s/\[\]()<>]+|[A-Za-z'\"*]+")


def lire_contenu(flux):
    """Rend (textes, rectangles) : le texte placé et les boîtes du dessin.

    textes     : [{ texte, x, y }] — le point d'ancrage de chaque écriture ;
    rectangles : [{ x, y, largeur, hauteur }] — coin bas gauche et taille.
    """
    textes, rectangles = [], []
    pile, ctm = [], [1, 0, 0, 1, 0, 0]
    tm = tlm = [1, 0, 0, 1, 0, 0]
    operandes = []
    dans_tableau = False
    morceaux_tableau = []

    for jeton in JETON.finditer(flux):
        brut = jeton.group(0)
        premier = brut[:1]
        if premier == b'(':
            valeur = texte_litteral(brut[1:-1])
            (morceaux_tableau if dans_tableau else operandes).append(valeur)
            continue
        if premier == b'<':
            valeur = texte_hexa(brut[1:-1])
            (morceaux_tableau if dans_tableau else operandes).append(valeur)
            continue
        if brut == b'[':
            dans_tableau, morceaux_tableau = True, []
            continue
        if brut == b']':
            dans_tableau = False
            operandes.append(b''.join(m for m in morceaux_tableau if isinstance(m, bytes)))
            continue
        if premier == b'/':
            (morceaux_tableau if dans_tableau else operandes).append(brut)
            continue
        if premier in b'-+0123456789.':
            try:
                nombre = float(brut)
            except ValueError:
                continue
            if dans_tableau:
                morceaux_tableau.append(nombre)
            else:
                operandes.append(nombre)
            continue

        operateur = brut
        nombres = [o for o in operandes if isinstance(o, float)]
        chaines = [o for o in operandes if isinstance(o, bytes) and not o.startswith(b'/')]

        if operateur == b'q':
            pile.append(list(ctm))
        elif operateur == b'Q':
            if pile:
                ctm = pile.pop()
        elif operateur == b'cm' and len(nombres) >= 6:
            ctm = multiplier(nombres[-6:], ctm)
        elif operateur == b'BT':
            tm = tlm = [1, 0, 0, 1, 0, 0]
        elif operateur == b'Tm' and len(nombres) >= 6:
            tm = tlm = list(nombres[-6:])
        elif operateur in (b'Td', b'TD') and len(nombres) >= 2:
            tlm = multiplier([1, 0, 0, 1, nombres[-2], nombres[-1]], tlm)
            tm = list(tlm)
        elif operateur == b'T*':
            tlm = multiplier([1, 0, 0, 1, 0, -12], tlm)
            tm = list(tlm)
        elif operateur in (b'Tj', b'TJ', b"'", b'"'):
            if operateur in (b"'", b'"'):
                tlm = multiplier([1, 0, 0, 1, 0, -12], tlm)
                tm = list(tlm)
            if chaines:
                mot = en_caracteres(chaines[-1]).strip()
                if mot:
                    x, y = applique(multiplier(tm, ctm), 0, 0)
                    textes.append({'texte': mot, 'x': round(x, 2), 'y': round(y, 2)})
        elif operateur == b're' and len(nombres) >= 4:
            x, y, largeur, hauteur = nombres[-4:]
            coins = [applique(ctm, x, y), applique(ctm, x + largeur, y + hauteur)]
            x0, x1 = sorted([coins[0][0], coins[1][0]])
            y0, y1 = sorted([coins[0][1], coins[1][1]])
            rectangles.append({'x': round(x0, 2), 'y': round(y0, 2),
                               'largeur': round(x1 - x0, 2), 'hauteur': round(y1 - y0, 2)})
        operandes = []
    return textes, rectangles


def lire(chemin, repere=REPERE):
    """Le plan, de bout en bout. Lève ErreurPlan si le fichier n'est pas lisible."""
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurPlan('Plan introuvable : %s' % fichier)
    donnees = fichier.read_bytes()
    dessins = flux_de_dessin(flux_du_pdf(donnees))
    if not dessins:
        raise ErreurPlan(
            '%s ne contient aucun dessin lisible. S\'il s\'agit d\'un scan ou d\'une photo, '
            'il n\'y a pas de texte dedans : il faut de la reconnaissance de caractères — '
            'c\'est le travail de lire_scan.py, que lire_composants.py appelle tout seul. '
            'Le PDF d\'origine, celui qui sort de l\'outil de dessin, reste la meilleure source.'
            % fichier.name)
    textes, rectangles = [], []
    for flux in dessins:
        t, r = lire_contenu(flux)
        textes += t
        rectangles += r
    if not textes:
        raise ErreurPlan(
            '%s porte des traits mais aucun texte : soit une image (lire_scan.py la lira), '
            'soit un dessin dont le texte a été converti en traits — alors demandez le PDF '
            'd\'origine.' % fichier.name)
    resultat = composants(textes, rectangles, repere)
    resultat['textes'] = len(textes)
    resultat['rectangles'] = len(rectangles)
    resultat['resume'] = '%d texte(s), %d rectangle(s)' % (len(textes), len(rectangles))
    return resultat


def main(argv=None):
    parseur = argparse.ArgumentParser(description='Retire les composants d\'un plan ELEC en PDF.')
    parseur.add_argument('plan', help='le fichier PDF')
    parseur.add_argument('--csv', help='écrire les composants sûrs dans ce fichier')
    parseur.add_argument('--repere', help='l\'expression qui reconnaît un repère électrique')
    args = parseur.parse_args(argv)
    try:
        motif = re.compile(args.repere) if args.repere else REPERE
        resultat = lire(args.plan, motif)
        print(raconter(resultat, pathlib.Path(args.plan).name))
        if args.csv:
            ecrire_csv(args.csv, lignes_csv(resultat, pathlib.Path(args.plan).name))
            print('  → %s' % args.csv)
        return 0
    except ErreurPlan as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
