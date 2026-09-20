#!/usr/bin/env python3
"""
Batterie du lecteur Visio : elle fabrique de vrais .vsdx (archive + XML) et
.vdx — formes avec texte, étiquettes à côté, groupes, gabarits, connecteurs
— puis vérifie que le lecteur retrouve les composants attendus, et dit ce
dont il n'est pas sûr.

    python3 import/tests_visio.py

Aucune dépendance : bibliothèque standard uniquement.
"""

import pathlib
import shutil
import sys
import tempfile
import zipfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import lire_visio as lv                                            # noqa: E402

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
    except lv.ErreurPlan as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
#  Fabriquer un .vsdx à la main
# ---------------------------------------------------------------------------
ESPACE = 'http://schemas.microsoft.com/office/visio/2012/main'
ESPACE_R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
ESPACE_RELS = 'http://schemas.openxmlformats.org/package/2006/relationships'
GEOMETRIE = ('<Section N="Geometry" IX="0"><Row T="RelMoveTo" IX="1"><Cell N="X" V="0"/><Cell N="Y" V="0"/></Row>'
             '<Row T="RelLineTo" IX="2"><Cell N="X" V="1"/><Cell N="Y" V="0"/></Row></Section>')

_id = [0]


def forme(pin_x, pin_y, largeur, hauteur, texte='', geometrie=True, master=None, une_d=False, sous=''):
    """Une forme Visio 2012, en pouces, ancrée en son centre."""
    _id[0] += 1
    texte_xml = '<Text><cp IX="0"/>%s</Text>' % texte.replace('&', '&amp;').replace('<', '&lt;').replace('\n', '&#xA;') if texte else ''
    cellules = ''
    if largeur is not None:
        cellules += '<Cell N="Width" V="%g"/><Cell N="Height" V="%g"/>' % (largeur, hauteur)
        cellules += '<Cell N="LocPinX" V="%g"/><Cell N="LocPinY" V="%g"/>' % (largeur / 2.0, hauteur / 2.0)
    if une_d:
        cellules += '<Cell N="BeginX" V="%g"/><Cell N="BeginY" V="%g"/><Cell N="EndX" V="%g"/><Cell N="EndY" V="%g"/>' % (
            pin_x - largeur / 2.0, pin_y, pin_x + largeur / 2.0, pin_y)
    return ('<Shape ID="%d" Type="%s"%s><Cell N="PinX" V="%g"/><Cell N="PinY" V="%g"/>%s%s%s%s</Shape>'
            % (_id[0], 'Group' if sous else 'Shape', ' Master="%s"' % master if master else '',
               pin_x, pin_y, cellules, GEOMETRIE if geometrie else '', texte_xml,
               '<Shapes>%s</Shapes>' % sous if sous else ''))


def vsdx(chemin, pages, gabarits=None):
    """pages : [(nom, xml des formes)] ; gabarits : { ID: (largeur, hauteur, geometrie, une_d) }."""
    with zipfile.ZipFile(str(chemin), 'w') as archive:
        archive.writestr('[Content_Types].xml', '<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"/>')
        liste, rels = [], []
        for rang, (nom, formes_xml) in enumerate(pages, 1):
            liste.append('<Page ID="%d" Name="%s"><Rel r:id="rId%d"/></Page>' % (rang, nom, rang))
            rels.append('<Relationship Id="rId%d" Type="x" Target="page%d.xml"/>' % (rang, rang))
            archive.writestr('visio/pages/page%d.xml' % rang,
                             '<?xml version="1.0"?><PageContents xmlns="%s"><Shapes>%s</Shapes></PageContents>' % (ESPACE, formes_xml))
        archive.writestr('visio/pages/pages.xml',
                         '<?xml version="1.0"?><Pages xmlns="%s" xmlns:r="%s">%s</Pages>' % (ESPACE, ESPACE_R, ''.join(liste)))
        archive.writestr('visio/pages/_rels/pages.xml.rels',
                         '<?xml version="1.0"?><Relationships xmlns="%s">%s</Relationships>' % (ESPACE_RELS, ''.join(rels)))
        if gabarits:
            liste, rels = [], []
            for rang, (ident, (largeur, hauteur, geometrie, une_d)) in enumerate(gabarits.items(), 1):
                liste.append('<Master ID="%s" Name="Gabarit %s"><Rel r:id="rId%d"/></Master>' % (ident, ident, rang))
                rels.append('<Relationship Id="rId%d" Type="x" Target="master%d.xml"/>' % (rang, rang))
                archive.writestr('visio/masters/master%d.xml' % rang,
                                 '<?xml version="1.0"?><MasterContents xmlns="%s"><Shapes>%s</Shapes></MasterContents>'
                                 % (ESPACE, forme(0, 0, largeur, hauteur, geometrie=geometrie, une_d=une_d)))
            archive.writestr('visio/masters/masters.xml',
                             '<?xml version="1.0"?><Masters xmlns="%s" xmlns:r="%s">%s</Masters>' % (ESPACE, ESPACE_R, ''.join(liste)))
            archive.writestr('visio/masters/_rels/masters.xml.rels',
                             '<?xml version="1.0"?><Relationships xmlns="%s">%s</Relationships>' % (ESPACE_RELS, ''.join(rels)))


def vdx(chemin, formes_2003):
    chemin.write_text('<?xml version="1.0"?><VisioDocument xmlns="http://schemas.microsoft.com/visio/2003/core">'
                      '<Pages><Page ID="0" Name="Page-1"><Shapes>%s</Shapes></Page></Pages></VisioDocument>' % formes_2003,
                      encoding='utf-8')


def forme_2003(pin_x, pin_y, largeur, hauteur, texte='', geometrie=True):
    _id[0] += 1
    return ('<Shape ID="%d" Type="Shape"><XForm><PinX>%g</PinX><PinY>%g</PinY><Width>%g</Width><Height>%g</Height>'
            '<LocPinX>%g</LocPinX><LocPinY>%g</LocPinY></XForm>%s%s</Shape>'
            % (_id[0], pin_x, pin_y, largeur, hauteur, largeur / 2.0, hauteur / 2.0,
               '<Geom IX="0"><MoveTo IX="1"><X>0</X><Y>0</Y></MoveTo></Geom>' if geometrie else '',
               '<Text><cp IX="0"/>%s</Text>' % texte if texte else ''))


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-visio-'))
    try:
        section('Un dessin simple : trois équipements, leur texte dedans')
        simple = atelier / 'simple.vsdx'
        vsdx(simple, [('Page-1',
                       forme(2, 5, 1, 0.5, '18AB\nConnecteur') + forme(4, 5, 1, 0.5, '120PA3\nBoîtier') +
                       forme(6, 5, 1, 0.5, '7XY') + forme(5.5, 4.25, 11, 8.5))])       # le cadre de la page
        r = lv.lire(simple)
        reperes = sorted(c['repere'] for c in r['trouves'])
        verifier('les trois repères sont retrouvés, chacun dans sa forme', reperes == ['120PA3', '18AB', '7XY'], reperes)
        verifier('le texte de la forme reste attaché au composant, ligne par ligne',
                 [c['textes'] for c in r['trouves'] if c['repere'] == '18AB'] == [['18AB', 'Connecteur']],
                 [c['textes'] for c in r['trouves']])
        premier = [c for c in r['trouves'] if c['repere'] == '18AB'][0]
        verifier('les positions sont en points, depuis le coin bas gauche de la forme',
                 abs(premier['x'] - 1.5 * 72) < 0.01 and abs(premier['y'] - 4.75 * 72) < 0.01 and
                 abs(premier['largeur'] - 72) < 0.01, premier)
        verifier('le cadre de la page est ignoré, et compté comme tel', r['cadres'] == 1 and r['boites'] == 3, (r['cadres'], r['boites']))
        verifier('rien de douteux, rien d\'orphelin, et le compte rendu le dit',
                 not r['douteux'] and not r['orphelins'] and '3 composant(s) sûr(s)' in lv.raconter(r, 'simple.vsdx') and
                 '4 forme(s)' in lv.raconter(r, 'simple.vsdx'), lv.raconter(r))

        section('L\'étiquette à côté de sa forme, et celle qui ne l\'est pas')
        cote = atelier / 'cote.vsdx'
        vsdx(cote, [('Page-1', forme(2, 5, 1, 0.5) + forme(2, 4.6, 0.6, 0.2, '18AB', geometrie=False) +
                     forme(6, 5, 1, 0.5) + forme(6, 1, 0.6, 0.2, '19CD', geometrie=False))])
        r = lv.lire(cote)
        verifier('un texte sans trait juste sous une forme vide lui est rattaché',
                 [c['repere'] for c in r['trouves']] == ['18AB'], r['trouves'])
        verifier('un texte loin de toute forme est orphelin, et la forme vide est signalée',
                 [t['texte'] for t in r['orphelins']] == ['19CD'] and
                 any(d['pourquoi'] == 'aucun repère dans la boîte' for d in r['douteux']), (r['orphelins'], r['douteux']))

        section('Les groupes, les gabarits, les connecteurs')
        groupe = atelier / 'groupe.vsdx'
        vsdx(groupe, [('Page-1', forme(4, 4, 4, 2, sous=forme(1, 1, 1, 0.5, '18AB') + forme(3, 1, 1, 0.5, '19CD')))])
        r = lv.lire(groupe)
        par = {c['repere']: c for c in r['trouves']}
        verifier('les formes d\'un groupe sont lues à leur place absolue (l\'origine du groupe s\'ajoute)',
                 sorted(par) == ['18AB', '19CD'] and abs(par['18AB']['x'] - 2.5 * 72) < 0.01 and
                 abs(par['18AB']['y'] - 3.75 * 72) < 0.01, par)
        gabarit = atelier / 'gabarit.vsdx'
        vsdx(gabarit, [('Page-1', forme(2, 5, None, None, '18AB', geometrie=False, master='7') +
                        forme(5, 5, 1, 0.5, 'W12', geometrie=True, master='9'))],
             gabarits={'7': (1.2, 0.6, True, False), '9': (1, 0.5, True, True)})
        r = lv.lire(gabarit)
        verifier('une forme qui hérite tout de son gabarit — taille et tracé — est une boîte quand même',
                 [c['repere'] for c in r['trouves']] == ['18AB'] and abs(r['trouves'][0]['largeur'] - 1.2 * 72) < 0.01,
                 r['trouves'])
        verifier('un connecteur (forme 1D) n\'est pas une boîte, même s\'il trace un trait',
                 r['boites'] == 1, r['boites'])
        connecteur = atelier / 'connecteur.vsdx'
        vsdx(connecteur, [('Page-1', forme(2, 5, 1, 0.5, '18AB') + forme(4, 5, 2, 0.02, '19CD', une_d=True))])
        r = lv.lire(connecteur)
        verifier('un repère écrit sur un connecteur reste orphelin : il n\'a pas de boîte',
                 [c['repere'] for c in r['trouves']] == ['18AB'] and [t['texte'] for t in r['orphelins']] == ['19CD'], r)

        section('Ce dont le lecteur n\'est pas sûr, il le dit')
        deux = atelier / 'deux.vsdx'
        vsdx(deux, [('Page-1', forme(2, 5, 2, 0.5, '18AB 19CD'))])
        r = lv.lire(deux)
        verifier('deux repères sur une ligne : ce n\'est pas un repère, la forme est signalée',
                 not r['trouves'] and r['douteux'], r)
        vsdx(deux, [('Page-1', forme(2, 5, 2, 0.5, '18AB\n19CD'))])
        r = lv.lire(deux)
        verifier('deux repères sur deux lignes de la même forme : rien d\'inventé, signalé',
                 not r['trouves'] and r['douteux'][0]['pourquoi'] == 'plusieurs repères dans la même boîte', r['douteux'])

        section('Plusieurs pages')
        pages = atelier / 'pages.vsdx'
        vsdx(pages, [('Cabine', forme(2, 5, 1, 0.5, '18AB')),
                     ('Soute', forme(2, 5, 1, 0.5) + forme(2, 4.6, 0.6, 0.2, '19CD', geometrie=False) + forme(6, 5, 1, 0.5, '20EF'))])
        r = lv.lire(pages)
        verifier('chaque page est lue pour elle-même, et chaque composant sait sa page',
                 sorted((c['repere'], c['page']) for c in r['trouves']) == [('18AB', 1), ('19CD', 2), ('20EF', 2)] and
                 r['pages'] == 2 and 'sur 2 pages' in lv.raconter(r), r['trouves'])

        section('Le vieux XML Visio 2003 (.vdx)')
        vieux = atelier / 'vieux.vdx'
        vdx(vieux, forme_2003(2, 5, 1, 0.5, '18AB') + forme_2003(4, 5, 1, 0.5) + forme_2003(4, 4.6, 0.6, 0.2, '19CD', geometrie=False))
        r = lv.lire(vieux)
        verifier('les formes en XForm se lisent pareil', sorted(c['repere'] for c in r['trouves']) == ['18AB', '19CD'], r['trouves'])

        section('Ce que le lecteur refuse franchement')
        verifier('un fichier introuvable le dit', _leve(lv.lire, atelier / 'nulle-part.vsdx'))
        faux = atelier / 'faux.vsdx'
        faux.write_bytes(b'ceci n\'est pas une archive')
        verifier('un fichier qui n\'est pas une archive le dit, en parlant d\'Enregistrer sous', _leve(lv.lire, faux))
        sans_page = atelier / 'sans-page.vsdx'
        with zipfile.ZipFile(str(sans_page), 'w') as archive:
            archive.writestr('rien.txt', 'rien')
        verifier('une archive sans page Visio le dit', _leve(lv.lire, sans_page))
        binaire = atelier / 'binaire.vsd'
        binaire.write_bytes(b'\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1' + b'\0' * 64)
        try:
            lv.lire(binaire)
            message = ''
        except lv.ErreurPlan as err:
            message = str(err)
        verifier('le format binaire .vsd, sans Visio ni pywin32, dit les deux façons de faire',
                 ('vsdx' in message and 'pywin32' in message) or 'Visio' in message, message)
        casse = atelier / 'casse.vdx'
        casse.write_text('<VisioDocument><Pages><Page>', encoding='utf-8')
        verifier('un .vdx mal formé le dit', _leve(lv.lire, casse))

        section('Le motif du repère se règle, et la ligne de commande')
        import re
        autre = atelier / 'autre.vsdx'
        vsdx(autre, [('Page-1', forme(2, 5, 1, 0.5, 'EQ-4512'))])
        verifier('un autre motif reconnaît un autre genre de repère',
                 [c['repere'] for c in lv.lire(autre, re.compile(r'^EQ-\d{4}$'))['trouves']] == ['EQ-4512'] and
                 not lv.lire(autre)['trouves'])
        sortie = atelier / 'sortie.csv'
        verifier('la ligne de commande lit et écrit le CSV',
                 lv.main([str(simple), '--csv', str(sortie)]) == 0 and '18AB;sûr' in sortie.read_text(encoding='utf-8-sig'))
        verifier('et rend 1 sur un fichier illisible', lv.main([str(faux)]) == 1)
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


if __name__ == '__main__':
    sys.exit(main())
