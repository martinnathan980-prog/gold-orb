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

Un PDF **scanné** (une photo de papier), lui, ne contient aucun texte : il
faudrait de la reconnaissance de caractères, qui demande un programme à
installer. Ce cas-là n'est pas traité, et le programme le dit franchement au
lieu de rendre n'importe quoi.

    python3 import/lire_plan.py plan.pdf
    python3 import/lire_plan.py plan.pdf --csv composants.csv
    python3 import/lire_plan.py plan.pdf --repere "^[0-9]{1,3}[A-Z]{1,3}[0-9]{0,3}$"

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import csv
import pathlib
import re
import sys
import zlib

# Un repère électrique, par défaut : quelques chiffres, quelques lettres, et
# éventuellement des chiffres — « 18AB », « 120PA3 ». Se remplace en ligne de
# commande le jour où la convention diffère.
REPERE = re.compile(r'^[0-9]{1,3}[A-Z]{1,4}[0-9]{0,3}$')
COTE_MINI = 8.0          # une boîte plus petite que cela n'est pas un équipement
DISTANCE_MAXI = 40.0     # un repère écrit à côté de sa boîte, pas à l'autre bout


class ErreurPlan(Exception):
    """Ce qui empêche de lire le plan, dit en français."""


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


# ---------------------------------------------------------------------------
#  Les composants : une boîte, et le repère qui est dedans ou juste à côté
# ---------------------------------------------------------------------------
def dedans(rect, t):
    return (rect['x'] <= t['x'] <= rect['x'] + rect['largeur'] and
            rect['y'] <= t['y'] <= rect['y'] + rect['hauteur'])


def distance_au_bord(rect, t):
    dx = max(rect['x'] - t['x'], 0, t['x'] - (rect['x'] + rect['largeur']))
    dy = max(rect['y'] - t['y'], 0, t['y'] - (rect['y'] + rect['hauteur']))
    return (dx * dx + dy * dy) ** 0.5


def composants(textes, rectangles, repere=REPERE, cote_mini=COTE_MINI,
               distance_maxi=DISTANCE_MAXI):
    """Rend { trouves, douteux, orphelins, boites } — et jamais une invention.

    trouves   : [{ repere, x, y, largeur, hauteur, textes }] — une boîte, un repère ;
    douteux   : les boîtes à plusieurs repères, ou sans aucun ;
    orphelins : les repères écrits loin de toute boîte.
    """
    boites = [r for r in rectangles
              if r['largeur'] >= cote_mini and r['hauteur'] >= cote_mini]
    # Une boîte dans une autre (un cadre autour du plan) : on garde la plus petite
    # qui contient le repère, donc on trie du plus petit au plus grand.
    boites.sort(key=lambda r: r['largeur'] * r['hauteur'])
    pris = set()
    trouves, douteux = [], []
    for rang, rect in enumerate(boites):
        interieur = [t for i, t in enumerate(textes) if i not in pris and dedans(rect, t)]
        reperes = [t for t in interieur if repere.match(t['texte'])]
        if len(reperes) == 1:
            for i, t in enumerate(textes):
                if t in interieur:
                    pris.add(i)
            trouves.append({'repere': reperes[0]['texte'], 'x': rect['x'], 'y': rect['y'],
                            'largeur': rect['largeur'], 'hauteur': rect['hauteur'],
                            'textes': [t['texte'] for t in interieur]})
        elif len(reperes) > 1:
            douteux.append({'pourquoi': 'plusieurs repères dans la même boîte',
                            'reperes': [t['texte'] for t in reperes], 'rect': rect})
        else:
            douteux.append({'pourquoi': 'aucun repère dans la boîte',
                            'textes': [t['texte'] for t in interieur], 'rect': rect})
    # Les repères écrits à côté d'une boîte sans repère : on les rattache, mais
    # seulement si une seule boîte est assez proche — sinon on ne tranche pas.
    orphelins = []
    libres = [t for i, t in enumerate(textes) if i not in pris and repere.match(t['texte'])]
    for t in libres:
        proches = [d for d in douteux
                   if d['pourquoi'] == 'aucun repère dans la boîte' and
                   distance_au_bord(d['rect'], t) <= distance_maxi]
        if len(proches) == 1:
            d = proches[0]
            douteux.remove(d)
            trouves.append({'repere': t['texte'], 'x': d['rect']['x'], 'y': d['rect']['y'],
                            'largeur': d['rect']['largeur'], 'hauteur': d['rect']['hauteur'],
                            'textes': d.get('textes', []) + [t['texte']]})
        else:
            orphelins.append(t)
    trouves.sort(key=lambda c: (-c['y'], c['x']))
    return {'trouves': trouves, 'douteux': douteux, 'orphelins': orphelins,
            'boites': len(boites)}


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
            'il n\'y a pas de texte dedans : il faudrait de la reconnaissance de caractères, '
            'qui demande un programme à installer. Demandez le PDF d\'origine, celui qui sort '
            'de l\'outil de dessin.' % fichier.name)
    textes, rectangles = [], []
    for flux in dessins:
        t, r = lire_contenu(flux)
        textes += t
        rectangles += r
    if not textes:
        raise ErreurPlan(
            '%s porte des traits mais aucun texte : c\'est probablement une image. '
            'Demandez le PDF d\'origine.' % fichier.name)
    resultat = composants(textes, rectangles, repere)
    resultat['textes'] = len(textes)
    resultat['rectangles'] = len(rectangles)
    return resultat


def raconter(resultat, nom=''):
    lignes = ['%s : %d texte(s), %d rectangle(s), %d boîte(s) retenue(s)'
              % (nom or 'Plan', resultat['textes'], resultat['rectangles'], resultat['boites'])]
    lignes.append('  %d composant(s) sûr(s)' % len(resultat['trouves']))
    for c in resultat['trouves'][:20]:
        autres = [t for t in c['textes'] if t != c['repere']]
        lignes.append('    %-10s %s' % (c['repere'], ' · '.join(autres[:4])))
    if len(resultat['trouves']) > 20:
        lignes.append('    … et %d autre(s)' % (len(resultat['trouves']) - 20))
    if resultat['douteux']:
        lignes.append('  %d boîte(s) à regarder :' % len(resultat['douteux']))
        for d in resultat['douteux'][:10]:
            lignes.append('    %s — %s' % (d['pourquoi'],
                                           ', '.join(d.get('reperes') or d.get('textes') or ['(vide)'])[:60]))
    if resultat['orphelins']:
        lignes.append('  %d repère(s) sans boîte : %s'
                      % (len(resultat['orphelins']),
                         ', '.join(t['texte'] for t in resultat['orphelins'][:10])))
    return '\n'.join(lignes)


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
            with open(args.csv, 'w', encoding='utf-8-sig', newline='') as sortie:
                plume = csv.writer(sortie, delimiter=';')
                plume.writerow(['Repère', 'X', 'Y', 'Largeur', 'Hauteur', 'Textes de la boîte'])
                for c in resultat['trouves']:
                    plume.writerow([c['repere'], c['x'], c['y'], c['largeur'], c['hauteur'],
                                    ' | '.join(c['textes'])])
            print('  → %s' % args.csv)
        return 0
    except ErreurPlan as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
