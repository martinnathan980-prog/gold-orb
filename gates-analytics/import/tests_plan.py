#!/usr/bin/env python3
"""
Batterie du lecteur de plans : elle fabrique de vrais PDF — avec des boîtes,
des repères dedans, des repères à côté, un cartouche, du texte compressé,
des coordonnées transformées — puis vérifie que le lecteur retrouve exactement
les composants attendus, et qu'il DIT ce dont il n'est pas sûr au lieu de
l'inventer.

    python3 import/tests_plan.py

Aucune dépendance : bibliothèque standard uniquement.
"""

import pathlib
import re
import shutil
import sys
import tempfile
import zlib

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lire_plan as lp                                            # noqa: E402

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
    except lp.ErreurPlan as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
#  Fabriquer un PDF à la main : c'est la seule façon de savoir ce qu'il contient
# ---------------------------------------------------------------------------
def pdf(contenu, comprimer=False):
    """Un PDF d'une page portant ce flux de dessin."""
    flux = contenu.encode('cp1252')
    if comprimer:
        flux = zlib.compress(flux)
        filtre = b'/Filter /FlateDecode '
    else:
        filtre = b''
    objets = [
        b'<< /Type /Catalog /Pages 2 0 R >>',
        b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] /Contents 4 0 R '
        b'/Resources << /Font << /F1 5 0 R >> >> >>',
        b'<< /Length ' + str(len(flux)).encode('ascii') + b' ' + filtre + b'>>\nstream\n' + flux + b'\nendstream',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
    ]
    sortie = bytearray(b'%PDF-1.4\n')
    positions = []
    for rang, corps in enumerate(objets, 1):
        positions.append(len(sortie))
        sortie += str(rang).encode('ascii') + b' 0 obj\n' + corps + b'\nendobj\n'
    debut_xref = len(sortie)
    sortie += b'xref\n0 ' + str(len(objets) + 1).encode('ascii') + b'\n0000000000 65535 f \n'
    for p in positions:
        sortie += ('%010d 00000 n \n' % p).encode('ascii')
    sortie += (b'trailer\n<< /Size ' + str(len(objets) + 1).encode('ascii') +
               b' /Root 1 0 R >>\nstartxref\n' + str(debut_xref).encode('ascii') + b'\n%%EOF\n')
    return bytes(sortie)


def boite(x, y, largeur, hauteur):
    return '%g %g %g %g re S\n' % (x, y, largeur, hauteur)


def ecrire(x, y, texte):
    echappe = texte.replace('\\', r'\\').replace('(', r'\(').replace(')', r'\)')
    return 'BT /F1 8 Tf 1 0 0 1 %g %g Tm (%s) Tj ET\n' % (x, y, echappe)


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-plan-'))
    try:
        section('Un plan simple : trois équipements dans leurs boîtes')
        contenu = (
            boite(100, 400, 80, 40) + ecrire(110, 420, '18AB') + ecrire(110, 408, 'Connecteur') +
            boite(300, 400, 80, 40) + ecrire(310, 420, '120PA3') + ecrire(310, 408, 'Boîtier') +
            boite(500, 400, 80, 40) + ecrire(510, 420, '7XY') +
            boite(20, 20, 800, 555)                       # le cadre du plan : pas un équipement
        )
        simple = atelier / 'simple.pdf'
        simple.write_bytes(pdf(contenu))
        r = lp.lire(simple)
        reperes = [c['repere'] for c in r['trouves']]
        verifier('les trois repères sont retrouvés, chacun dans sa boîte',
                 sorted(reperes) == ['120PA3', '18AB', '7XY'], reperes)
        verifier('le texte qui accompagne le repère reste attaché à son composant',
                 sorted(c['textes'] for c in r['trouves'] if c['repere'] == '18AB')[0] == ['18AB', 'Connecteur'],
                 [c['textes'] for c in r['trouves']])
        verifier('le cadre du plan, qui contient tout, n\'est pas pris pour un équipement',
                 all(c['largeur'] < 200 for c in r['trouves']), [c['largeur'] for c in r['trouves']])
        verifier('les positions sont rendues, pour pouvoir retrouver le composant sur le plan',
                 all(isinstance(c['x'], float) and isinstance(c['y'], float) for c in r['trouves']))
        verifier('rien n\'est douteux, rien n\'est orphelin sur un plan propre',
                 not r['orphelins'] and all(d['pourquoi'] != 'plusieurs repères dans la même boîte' for d in r['douteux']),
                 [d['pourquoi'] for d in r['douteux']])

        section('Le flux compressé, la casse, les caractères échappés')
        comprime = atelier / 'comprime.pdf'
        comprime.write_bytes(pdf(contenu, comprimer=True))
        verifier('un plan dont le dessin est compressé se lit pareil',
                 sorted(c['repere'] for c in lp.lire(comprime)['trouves']) == ['120PA3', '18AB', '7XY'])
        accents = atelier / 'accents.pdf'
        accents.write_bytes(pdf(boite(100, 400, 90, 40) + ecrire(110, 420, '18AB') +
                                ecrire(110, 408, 'Câble blindé (arrière)')))
        r = lp.lire(accents)
        verifier('les accents et les parenthèses échappées se lisent tels quels',
                 r['trouves'][0]['textes'] == ['18AB', 'Câble blindé (arrière)'], r['trouves'][0]['textes'])

        section('Le repère écrit à côté de sa boîte')
        cote = atelier / 'cote.pdf'
        cote.write_bytes(pdf(boite(100, 400, 60, 30) + ecrire(105, 385, '18AB') +
                             boite(400, 400, 60, 30) + ecrire(405, 385, '19CD')))
        r = lp.lire(cote)
        verifier('un repère écrit juste sous sa boîte lui est rattaché',
                 sorted(c['repere'] for c in r['trouves']) == ['18AB', '19CD'],
                 [c['repere'] for c in r['trouves']])
        loin = atelier / 'loin.pdf'
        loin.write_bytes(pdf(boite(100, 400, 60, 30) + ecrire(105, 100, '18AB')))
        r = lp.lire(loin)
        verifier('un repère écrit à l\'autre bout du plan n\'est rattaché à rien : il est signalé',
                 not r['trouves'] and [t['texte'] for t in r['orphelins']] == ['18AB'],
                 [r['trouves'], r['orphelins']])
        ambigu = atelier / 'ambigu.pdf'
        ambigu.write_bytes(pdf(boite(100, 400, 40, 20) + boite(160, 400, 40, 20) + ecrire(150, 395, '18AB')))
        r = lp.lire(ambigu)
        verifier('un repère entre deux boîtes possibles n\'est attribué à aucune : on ne tranche pas',
                 not r['trouves'] and len(r['orphelins']) == 1, [r['trouves'], r['orphelins']])

        section('Ce dont le lecteur n\'est pas sûr, il le dit')
        deux = atelier / 'deux.pdf'
        deux.write_bytes(pdf(boite(100, 400, 120, 40) + ecrire(110, 420, '18AB') + ecrire(170, 420, '19CD')))
        r = lp.lire(deux)
        verifier('deux repères dans la même boîte : aucun composant inventé, la boîte est signalée',
                 not r['trouves'] and any(d['pourquoi'] == 'plusieurs repères dans la même boîte' for d in r['douteux']),
                 [r['trouves'], r['douteux']])
        vide = atelier / 'vide.pdf'
        vide.write_bytes(pdf(boite(100, 400, 60, 30) + ecrire(110, 415, 'Zone A') + ecrire(300, 300, 'Cartouche')))
        r = lp.lire(vide)
        verifier('une boîte sans repère est signalée, avec ce qu\'elle contient',
                 not r['trouves'] and any(d['pourquoi'] == 'aucun repère dans la boîte' and d['textes'] == ['Zone A']
                                          for d in r['douteux']), r['douteux'])

        section('Les coordonnées transformées, comme dans un vrai plan')
        transforme = atelier / 'transforme.pdf'
        transforme.write_bytes(pdf(
            'q 1 0 0 1 200 100 cm\n' + boite(0, 300, 60, 30) + ecrire(5, 315, '18AB') + 'Q\n' +
            'q 2 0 0 2 0 0 cm\n' + boite(50, 150, 40, 20) + ecrire(55, 158, '19CD') + 'Q\n'))
        r = lp.lire(transforme)
        parRepere = {c['repere']: c for c in r['trouves']}
        verifier('un dessin déplacé par une transformation est lu à sa vraie place',
                 '18AB' in parRepere and abs(parRepere['18AB']['x'] - 200) < 1 and abs(parRepere['18AB']['y'] - 400) < 1,
                 parRepere.get('18AB'))
        verifier('un dessin agrandi aussi : la boîte grandit avec lui',
                 '19CD' in parRepere and abs(parRepere['19CD']['x'] - 100) < 1 and
                 abs(parRepere['19CD']['largeur'] - 80) < 1, parRepere.get('19CD'))

        section('Ce que le lecteur refuse franchement')
        verifier('un fichier introuvable le dit', _leve(lp.lire, atelier / 'nulle-part.pdf'))
        pas_pdf = atelier / 'pas-un-pdf.txt'
        pas_pdf.write_bytes(b'Bonjour, je ne suis pas un PDF.')
        verifier('un fichier qui n\'est pas un PDF le dit', _leve(lp.lire, pas_pdf))
        scan = atelier / 'scan.pdf'
        scan.write_bytes(pdf('q 400 0 0 300 100 200 cm /Im0 Do Q\n'))
        verifier('un plan scanné — des traits ou une image, aucun texte — est refusé en expliquant pourquoi, '
                 'et en disant quoi demander à la place',
                 _leve(lp.lire, scan), 'doit lever')
        try:
            lp.lire(scan)
            message = ''
        except lp.ErreurPlan as err:
            message = str(err)
        verifier('et le message parle de scan, de reconnaissance de caractères et du PDF d\'origine',
                 'scan' in message and 'reconnaissance de caract' in message and 'origine' in message, message)

        section('Le motif du repère se règle')
        autre = atelier / 'autre.pdf'
        autre.write_bytes(pdf(boite(100, 400, 60, 30) + ecrire(110, 415, 'EQ-4512')))
        r = lp.lire(autre, re.compile(r'^EQ-\d{4}$'))
        verifier('avec un autre motif, un autre genre de repère est reconnu',
                 [c['repere'] for c in r['trouves']] == ['EQ-4512'], r['trouves'])
        verifier('et avec le motif par défaut, celui-là n\'en est pas un',
                 not lp.lire(autre)['trouves'])

        section('Un plan chargé : cinquante équipements')
        morceaux = []
        attendus = []
        for i in range(50):
            x, y = 40 + (i % 10) * 78, 500 - (i // 10) * 95
            repere = '%d%s' % (10 + i, 'ABCDE'[i % 5])
            attendus.append(repere)
            morceaux.append(boite(x, y, 60, 40) + ecrire(x + 4, y + 26, repere) +
                            ecrire(x + 4, y + 12, 'PN-%04d' % (1000 + i)))
        charge = atelier / 'charge.pdf'
        charge.write_bytes(pdf(''.join(morceaux) + boite(10, 10, 822, 575), comprimer=True))
        r = lp.lire(charge)
        verifier('les cinquante équipements sont retrouvés, sans doublon ni manque',
                 sorted(c['repere'] for c in r['trouves']) == sorted(attendus),
                 '%d trouvés' % len(r['trouves']))
        verifier('chacun garde son part number',
                 all(any(t.startswith('PN-') for t in c['textes']) for c in r['trouves']))
        verifier('le compte rendu dit combien, et ce qui reste à regarder',
                 '50 composant(s) sûr(s)' in lp.raconter(r), lp.raconter(r).splitlines()[1])
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


if __name__ == '__main__':
    sys.exit(main())
