#!/usr/bin/env python3
"""
Batterie du lecteur DXF : elle écrit de vrais DXF — polylignes fermées,
quatre traits qui se rejoignent, textes simples et mis en forme, blocs
insérés avec leurs attributs — puis vérifie que le lecteur retrouve les
composants attendus, et dit ce dont il n'est pas sûr.

    python3 import/tests_dxf.py

Aucune dépendance : bibliothèque standard uniquement.
"""

import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lire_dxf as ld                                              # noqa: E402

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
    except ld.ErreurPlan as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
#  Écrire un DXF à la main : des paires code / valeur
# ---------------------------------------------------------------------------
def p(code, valeur):
    return '%d\n%s\n' % (code, valeur)


def rect_poly(x, y, l, h):
    return (p(0, 'LWPOLYLINE') + p(8, '0') + p(90, 4) + p(70, 1) +
            p(10, x) + p(20, y) + p(10, x + l) + p(20, y) + p(10, x + l) + p(20, y + h) + p(10, x) + p(20, y + h))


def rect_traits(x, y, l, h):
    return (ligne(x, y, x + l, y) + ligne(x + l, y, x + l, y + h) + ligne(x + l, y + h, x, y + h) + ligne(x, y + h, x, y))


def ligne(x0, y0, x1, y1):
    return p(0, 'LINE') + p(8, '0') + p(10, x0) + p(20, y0) + p(11, x1) + p(21, y1)


def texte(x, y, t, hauteur=2.5):
    return p(0, 'TEXT') + p(8, '0') + p(10, x) + p(20, y) + p(40, hauteur) + p(1, t)


def mtext(x, y, t):
    return p(0, 'MTEXT') + p(8, '0') + p(10, x) + p(20, y) + p(40, 2.5) + p(1, t)


def insert(nom, x, y, attributs=(), echelle=1.0, angle=0):
    s = p(0, 'INSERT') + p(8, '0') + (p(66, 1) if attributs else '') + p(2, nom) + p(10, x) + p(20, y) + p(41, echelle) + p(42, echelle) + p(50, angle)
    for etiquette, valeur, ax, ay in attributs:
        s += p(0, 'ATTRIB') + p(8, '0') + p(10, ax) + p(20, ay) + p(40, 2.5) + p(1, valeur) + p(2, etiquette)
    if attributs:
        s += p(0, 'SEQEND')
    return s


def dxf(entites, blocs='', unites=4):
    return (p(0, 'SECTION') + p(2, 'HEADER') + p(9, '$INSUNITS') + p(70, unites) + p(0, 'ENDSEC') +
            p(0, 'SECTION') + p(2, 'BLOCKS') + blocs + p(0, 'ENDSEC') +
            p(0, 'SECTION') + p(2, 'ENTITIES') + entites + p(0, 'ENDSEC') + p(0, 'EOF'))


BLOC_CONN = (p(0, 'BLOCK') + p(2, 'CONN') + p(10, 0) + p(20, 0) + rect_poly(0, 0, 10, 6) +
             p(0, 'ATTDEF') + p(2, 'REP') + p(10, 1) + p(20, 1) + p(1, '') + p(0, 'ENDBLK'))
BLOC_ETIQUETTE = (p(0, 'BLOCK') + p(2, 'ETIQ') + p(10, 0) + p(20, 0) +
                  p(0, 'ATTDEF') + p(2, 'REP') + p(10, 0) + p(20, 0) + p(1, '') + p(0, 'ENDBLK'))


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-dxf-'))
    try:
        section('Un plan simple : polyligne, quatre traits, texte mis en forme')
        simple = atelier / 'simple.dxf'
        simple.write_text(dxf(
            rect_poly(100, 100, 20, 10) + texte(102, 105, '18AB') + texte(102, 101, 'Connecteur') +
            rect_traits(200, 100, 20, 10) + texte(202, 105, '120PA3') +
            rect_poly(300, 100, 20, 10) + mtext(302, 108, '{\\fArial|b0|i0;7XY}\\PBoîtier') +
            rect_traits(0, 0, 420, 297) + texte(10, 280, 'TFE2130A600001A')), encoding='cp1252')
        r = ld.lire(simple)
        reperes = sorted(c['repere'] for c in r['trouves'])
        verifier('les trois repères sont retrouvés, chacun dans sa boîte', reperes == ['120PA3', '18AB', '7XY'], reperes)
        verifier('une polyligne fermée et quatre traits qui se rejoignent font tous deux une boîte',
                 r['boites'] == 3 and r['cadres'] == 1, (r['boites'], r['cadres']))
        verifier('les codes de mise en forme d\'un MTEXT sont retirés, ses lignes séparées',
                 [c['textes'] for c in r['trouves'] if c['repere'] == '7XY'] == [['7XY', 'Boîtier']],
                 [c['textes'] for c in r['trouves']])
        verifier('le texte qui accompagne le repère reste attaché, et l\'accent passe',
                 [c['textes'] for c in r['trouves'] if c['repere'] == '18AB'] == [['18AB', 'Connecteur']])
        verifier('le cartouche n\'est pas un composant, et rien n\'est orphelin',
                 not r['orphelins'] and not r['douteux'], (r['orphelins'], r['douteux']))
        verifier('le compte rendu dit les entités et les blocs', '3 composant(s) sûr(s)' in ld.raconter(r) and 'entité(s)' in ld.raconter(r))

        section('Les blocs insérés : un équipement, son repère en attribut')
        blocs = atelier / 'blocs.dxf'
        blocs.write_text(dxf(
            insert('CONN', 100, 100, [('REP', '31AB2', 101, 101), ('PN', 'PN-1000', 101, 103)]) +
            insert('CONN', 200, 100, [('REP', '32AB', 201, 101)], echelle=2.0) +
            insert('CONN', 300, 100, [('REP', '33AB', 301, 101), ('REP2', '34AB', 301, 103)]) +
            insert('CONN', 400, 100) + texte(402, 108, '35AB') +
            insert('ETIQ', 500, 100, [('REP', '36AB', 500, 100)]) +
            insert('CONN', 600, 100, [('REP', '37AB', 601, 101)], angle=90), blocs=BLOC_CONN + BLOC_ETIQUETTE),
            encoding='utf-8')
        r = ld.lire(blocs)
        par = {c['repere']: c for c in r['trouves']}
        verifier('un bloc dont un attribut est un repère est un composant sûr, avec ses autres attributs',
                 '31AB2' in par and par['31AB2']['textes'] == ['31AB2', 'PN-1000'] and par['31AB2'].get('bloc') == 'CONN', par.get('31AB2'))
        verifier('sa boîte est l\'étendue du bloc, à l\'échelle de l\'insertion',
                 abs(par['31AB2']['largeur'] - 10) < 1e-6 and abs(par['32AB']['largeur'] - 20) < 1e-6 and
                 abs(par['32AB']['x'] - 200) < 1e-6, (par.get('31AB2'), par.get('32AB')))
        verifier('deux attributs qui font repère : rien d\'inventé, la boîte est signalée',
                 '33AB' not in par and '34AB' not in par and
                 any(d['pourquoi'] == 'plusieurs repères dans la même boîte' and sorted(d['reperes']) == ['33AB', '34AB'] for d in r['douteux']),
                 r['douteux'])
        verifier('un bloc sans attribut prend le repère écrit juste à côté', par.get('35AB', {}).get('x') == 400, par.get('35AB'))
        verifier('un bloc étiquette, sans tracé, vaut par son attribut (une boîte d\'un point)',
                 '36AB' in par and par['36AB']['largeur'] == 1.0, par.get('36AB'))
        verifier('un bloc inséré tourné d\'un quart de tour garde une boîte à sa place',
                 '37AB' in par and abs(par['37AB']['hauteur'] - 10) < 1e-6 and abs(par['37AB']['largeur'] - 6) < 1e-6, par.get('37AB'))

        section('Ce dont le lecteur n\'est pas sûr, il le dit')
        doute = atelier / 'doute.dxf'
        doute.write_text(dxf(rect_poly(100, 100, 30, 10) + texte(102, 105, '18AB') + texte(118, 105, '19CD') +
                             rect_poly(200, 100, 20, 10) + texte(202, 105, 'Zone A') +
                             texte(300, 300, '91AA') +
                             rect_poly(400, 100, 20, 10) + rect_poly(430, 100, 20, 10) + texte(424, 96, '92AB')), encoding='utf-8')
        r = ld.lire(doute)
        verifier('deux repères dans une boîte, une boîte sans repère : signalés, pas inventés',
                 not r['trouves'] and sorted(d['pourquoi'] for d in r['douteux']) ==
                 ['aucun repère dans la boîte', 'aucun repère dans la boîte', 'aucun repère dans la boîte', 'plusieurs repères dans la même boîte'],
                 [d['pourquoi'] for d in r['douteux']])
        verifier('un repère loin de tout, et un repère entre deux boîtes : orphelins tous les deux',
                 sorted(t['texte'] for t in r['orphelins']) == ['91AA', '92AB'], r['orphelins'])

        section('Les unités du dessin, les vieilles polylignes, l\'alignement des textes')
        pouces = atelier / 'pouces.dxf'
        pouces.write_text(dxf(rect_poly(4, 4, 0.8, 0.4) + texte(4.1, 4.2, '18AB') +
                              rect_poly(8, 4, 0.05, 0.05) + texte(8.01, 4.01, '19CD'), unites=1), encoding='utf-8')
        r = ld.lire(pouces)
        verifier('en pouces, une boîte de 0,8" est un équipement et une de 0,05" (1,3 mm) n\'en est pas une',
                 [c['repere'] for c in r['trouves']] == ['18AB'] and [t['texte'] for t in r['orphelins']] == ['19CD'], r)
        vieux = atelier / 'vieux.dxf'
        vieux.write_text(dxf(p(0, 'POLYLINE') + p(8, '0') + p(70, 1) +
                             ''.join(p(0, 'VERTEX') + p(8, '0') + p(10, x) + p(20, y) for x, y in ((100, 100), (120, 100), (120, 110), (100, 110))) +
                             p(0, 'SEQEND') +
                             p(0, 'TEXT') + p(8, '0') + p(10, 0) + p(20, 0) + p(11, 102) + p(21, 105) + p(72, 1) + p(1, '18AB')),
                         encoding='utf-8')
        r = ld.lire(vieux)
        verifier('une POLYLINE à sommets fait une boîte, et un TEXT aligné se lit à son second point',
                 [c['repere'] for c in r['trouves']] == ['18AB'], r)

        section('Ce que le lecteur refuse franchement')
        verifier('un fichier introuvable le dit', _leve(ld.lire, atelier / 'nulle-part.dxf'))
        dwg = atelier / 'plan.dwg'
        dwg.write_bytes(b'AC1027\x00\x00\x00' + b'\x00' * 100)
        verifier('un DWG est refusé, en disant d\'enregistrer en DXF', _leve(ld.lire, dwg))
        texte_quelconque = atelier / 'texte.dxf'
        texte_quelconque.write_text('Bonjour', encoding='utf-8')
        verifier('un fichier sans section ENTITIES le dit', _leve(ld.lire, texte_quelconque))

        section('Le motif du repère se règle, et la ligne de commande')
        autre = atelier / 'autre.dxf'
        autre.write_text(dxf(rect_poly(100, 100, 20, 10) + texte(102, 105, 'EQ-4512')), encoding='utf-8')
        verifier('un autre motif reconnaît un autre genre de repère',
                 [c['repere'] for c in ld.lire(autre, re.compile(r'^EQ-\d{4}$'))['trouves']] == ['EQ-4512'] and not ld.lire(autre)['trouves'])
        sortie = atelier / 'sortie.csv'
        verifier('la ligne de commande lit et écrit le CSV',
                 ld.main([str(simple), '--csv', str(sortie)]) == 0 and '18AB;sûr' in sortie.read_text(encoding='utf-8-sig'))
        verifier('et rend 1 sur un fichier illisible', ld.main([str(dwg)]) == 1)
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


if __name__ == '__main__':
    sys.exit(main())
