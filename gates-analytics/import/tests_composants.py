#!/usr/bin/env python3
"""
Batterie du socle commun : lire un mot comme un repère (tel quel, corrigé,
ou incertain), rattacher un repère à sa boîte, comparer à ce que la base
attend, raconter — et l'entrée unique, qui choisit le lecteur.

    python3 import/tests_composants.py

Aucune dépendance : bibliothèque standard uniquement.
"""

import pathlib
import re
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import composants as co                                            # noqa: E402
import lire_composants as lc                                       # noqa: E402
from tests_plan import pdf, boite, ecrire                          # noqa: E402

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
    except co.ErreurPlan as err:
        return bool(str(err).strip())
    except Exception:
        return False
    return False


def rect(x, y, l, h):
    return {'x': x, 'y': y, 'largeur': l, 'hauteur': h}


def mot(texte, x, y, **plus):
    m = {'texte': texte, 'x': x, 'y': y}
    m.update(plus)
    return m


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-composants-'))
    try:
        section('Lire un mot comme un repère')
        verifier('la ponctuation autour et les minuscules ne comptent pas',
                 co.nettoyer(' (18ab). ') == '18AB' and co.nettoyer('') == '', co.nettoyer(' (18ab). '))
        verifier('un repère lu tel quel est sûr', co.interpreter('18AB') == ('sur', '18AB'))
        verifier('une lettre confondue est corrigée quand une seule forme fait un repère',
                 co.interpreter('l8AB') == ('corrige', '18AB') and co.interpreter('O8AB') == ('corrige', '08AB'),
                 [co.interpreter('l8AB'), co.interpreter('O8AB')])
        verifier('un mot qui n\'est pas un repère le reste, corrigé ou non',
                 co.interpreter('Connecteur') == ('non', None) and co.interpreter('PN-1000') == ('non', None))
        verifier('une lecture brute qui fait déjà un repère n\'est pas changée sans raison',
                 co.interpreter('1BAB') == ('sur', '1BAB'))
        verifier('… mais la liste de la base tranche : 18AB attendu, 1BAB lu → corrigé',
                 co.interpreter('1BAB', connus={'18AB', '7XY'}) == ('corrige', '18AB'))
        verifier('la base connaît la lecture brute : elle l\'emporte sur toute correction',
                 co.interpreter('1BAB', connus={'18AB', '1BAB'}) == ('sur', '1BAB'),
                 co.interpreter('1BAB', connus={'18AB', '1BAB'}))
        verifier('deux formes attendues par la base, aussi proches l\'une que l\'autre : on ne tranche pas',
                 co.interpreter('1BAB', connus={'18AB', '1BA8'}) == ('incertain', ['18AB', '1BA8']),
                 co.interpreter('1BAB', connus={'18AB', '1BA8'}))
        verifier('on ne change jamais plus de lettres qu\'il n\'en faut : l8AB devient 18AB, pas 1BA8',
                 co.interpreter('l8AB') == ('corrige', '18AB') and co.variantes('l8AB')[0] == ('l8AB', 0),
                 co.variantes('L8AB')[:3])
        verifier('une lecture peu sûre est incertaine, sauf si la base la connaît',
                 co.interpreter('18AB', confiance=0.3) == ('incertain', ['18AB']) and
                 co.interpreter('18AB', confiance=0.3, connus={'18AB'}) == ('sur', '18AB'))
        verifier('trop de lettres confondables : on n\'essaie plus les variantes',
                 co.interpreter('0000000000') == ('non', None) and co.variantes('0000000000') == [('0000000000', 0)])
        verifier('un autre motif de repère s\'applique', co.interpreter('EQ-4512', re.compile(r'^EQ-\d{4}$')) == ('sur', 'EQ-4512'))
        textes = co.interpreter_mots([mot('l8AB', 1, 1), mot('1BAB', 2, 2), mot('Boîtier', 3, 3)],
                                     connus={'18AB', '1BA8'})
        verifier('les mots lus deviennent des textes prêts : corrigé garde sa lecture, incertain ses candidats',
                 textes[0]['texte'] == '18AB' and textes[0]['lu'] == 'l8AB' and
                 textes[1].get('candidats') == ['18AB', '1BA8'] and 'candidats' not in textes[2], textes)

        section('La règle commune : une boîte, un repère')
        r = co.composants([mot('18AB', 110, 420, lu='l8AB'), mot('Connecteur', 110, 408)], [rect(100, 400, 80, 40)])
        verifier('un repère corrigé dans sa boîte fait un composant, qui garde la lecture brute',
                 [c['repere'] for c in r['trouves']] == ['18AB'] and r['trouves'][0]['lu'] == 'l8AB', r)
        r = co.composants([mot('1BAB', 110, 420, candidats=['1BAB', '18AB'])], [rect(100, 400, 80, 40)])
        verifier('une boîte dont le repère est mal lu est douteuse, avec les candidats',
                 not r['trouves'] and r['douteux'][0]['pourquoi'] == 'repère mal lu' and
                 r['douteux'][0]['candidats'] == ['18AB', '1BAB'], r['douteux'])
        r = co.composants([mot('1BAB', 500, 500, candidats=['1BAB', '18AB'])], [rect(100, 400, 80, 40)])
        verifier('une lecture incertaine loin de toute boîte est rapportée à part',
                 [t['texte'] for t in r['incertains']] == ['1BAB'] and not r['orphelins'], r)
        cadre = rect(0, 0, 800, 600)
        r = co.composants([mot('18AB', 110, 420), mot('91AA', 700, 50)],
                          [rect(100, 400, 80, 40), rect(300, 400, 80, 40), cadre])
        verifier('le cadre du plan, qui contient les boîtes et couvre la page, n\'est pas une boîte',
                 r['cadres'] == 1 and r['boites'] == 2, (r['cadres'], r['boites']))
        verifier('un repère qui traîne dans le cadre est orphelin, pas un composant',
                 [t['texte'] for t in r['orphelins']] == ['91AA'] and [c['repere'] for c in r['trouves']] == ['18AB'], r)
        r = co.composants([mot('18AB', 110, 420)], [rect(100, 400, 80, 40)])
        verifier('une boîte seule sur le plan n\'est pas un cadre pour autant',
                 r['cadres'] == 0 and [c['repere'] for c in r['trouves']] == ['18AB'], r)
        r = co.composants([mot('18AB', 110, 420)], [rect(100, 400, 80, 40), rect(300, 0, 800, 600)])
        verifier('un grand rectangle qui ne contient aucune autre boîte n\'est pas un cadre : une boîte vide, signalée',
                 r['cadres'] == 0 and len(r['douteux']) == 1, (r['cadres'], r['douteux']))
        r = co.composants([mot('18AB', 110, 420), mot('19CD', 150, 420)], [rect(100, 400, 80, 40), rect(190, 400, 40, 40)])
        verifier('les repères d\'une boîte qui en a deux ne vont pas se rattacher à la boîte vide d\'à côté',
                 not r['trouves'] and not r['orphelins'] and len(r['douteux']) == 2, r)

        section('Ce que la base attend, et ce que le plan montre')
        r = {'trouves': [{'repere': '18AB'}, {'repere': '19CD'}, {'repere': '7XY'}]}
        c = co.correspondance(r, {'18AB', '19CD', '20EF'})
        verifier('communs, absents du plan, en plus sur le plan',
                 c == {'communs': ['18AB', '19CD'], 'absents': ['20EF'], 'en_plus': ['7XY']}, c)
        base = atelier / 'base.csv'
        base.write_text('Plan;Repère ELEC;PN\nTFE2130A600001A;18ab;PN-1\nTFE2130A600001A;19CD;PN-2\n'
                        'WLE4610A600003C;7XY;PN-3\n', encoding='utf-8-sig')
        connus = co.lire_connus(base)
        verifier('un CSV « plan ; repère » se lit, par plan, repères nettoyés',
                 connus == {'TFE2130A600001A': {'18AB', '19CD'}, 'WLE4610A600003C': {'7XY'}}, connus)
        liste = atelier / 'liste.txt'
        liste.write_text('18AB\n19CD\n\n7xy\n', encoding='utf-8')
        verifier('un simple fichier texte, un repère par ligne, vaut pour un seul plan',
                 co.lire_connus(liste) == {'': {'18AB', '19CD', '7XY'}}, co.lire_connus(liste))
        verifier('le plan se retrouve par son nom exact, par la référence dans le nom du fichier, ou seul',
                 co.attendus_pour(connus, 'TFE2130A600001A') == {'18AB', '19CD'} and
                 co.attendus_pour(connus, 'plan-WLE4610A600003C-indice-C') == {'7XY'} and
                 co.attendus_pour(co.lire_connus(liste), 'nimporte') == {'18AB', '19CD', '7XY'} and
                 co.attendus_pour(connus, 'inconnu') is None)
        sans = atelier / 'sans.csv'
        sans.write_text('Colonne A;Colonne B\n1;2\n', encoding='utf-8')
        try:
            co.lire_connus(sans)
            message = ''
        except co.ErreurPlan as err:
            message = str(err)
        verifier('un CSV sans colonne repère s\'arrête en montrant les en-têtes lus',
                 'Colonne A' in message and 'rep' in message, message)
        faux_xlsx = atelier / 'base.csv.xlsx'
        faux_xlsx.write_bytes(b'PK\x03\x04pas un csv')
        verifier('un classeur Excel est refusé, avec quoi faire', _leve(co.lire_connus, faux_xlsx))
        verifier('une liste introuvable le dit', _leve(co.lire_connus, atelier / 'nulle-part.csv'))

        section('Le compte rendu et le CSV')
        r = co.composants([mot('18AB', 110, 420, lu='l8AB'), mot('91AA', 700, 50),
                           mot('1BAB', 500, 500, candidats=['1BAB', '18AB'])],
                          [rect(100, 400, 80, 40), rect(300, 400, 80, 40), rect(0, 0, 800, 600)])
        r['resume'] = '3 texte(s)'
        corr = co.correspondance(r, {'18AB', '20EF'})
        texte = co.raconter(r, 'plan.pdf', corr)
        verifier('le compte rendu dit le résumé, les boîtes, le cadre, le composant et sa lecture brute',
                 'plan.pdf : 3 texte(s), 2 boîte(s) retenue(s), 1 cadre(s) ignoré(s)' in texte and
                 '18AB       (lu « l8AB »)' in texte and 'l8AB → 18AB' in texte, texte)
        verifier('… la boîte vide, l\'orphelin, l\'incertain, et la correspondance avec la base',
                 'aucun repère dans la boîte' in texte and 'sans boîte : 91AA' in texte and
                 'incertaine(s) hors boîte : 1BAB ?' in texte and
                 'la base attend 2 repère(s) : 1 retrouvé(s)' in texte and 'absent(s) du plan : 20EF' in texte, texte)
        lignes = co.lignes_csv(r, 'plan.pdf', corr)
        statuts = [l[3] for l in lignes]
        verifier('le CSV met une ligne par chose vue, avec son statut',
                 statuts == ['corrigé', 'douteux : aucun repère dans la boîte', 'orphelin', 'incertain',
                             'attendu, absent du plan'], statuts)
        sortie = atelier / 'sortie.csv'
        co.ecrire_csv(sortie, lignes)
        contenu = sortie.read_bytes()
        verifier('… écrit pour Excel : BOM, point-virgule, en-tête',
                 contenu.startswith(b'\xef\xbb\xbf' + 'Fichier;Page;Repère;Statut'.encode('utf-8')) and
                 contenu.count(b'\n') == 6, contenu[:80])

        section('L\'entrée unique choisit le lecteur')
        dessin = atelier / 'dessin.pdf'
        dessin.write_bytes(pdf(boite(100, 400, 80, 40) + ecrire(110, 420, '18AB')))
        resultat, lecteur = lc.lire_un(dessin)
        verifier('un PDF de dessin va au lecteur PDF', lecteur == 'dessin PDF' and [c['repere'] for c in resultat['trouves']] == ['18AB'])
        verifier('l\'extension décide, et sinon le contenu',
                 lc.lecteur_pour('x.vsdx') == 'visio' and lc.lecteur_pour('x.DXF') == 'dxf' and
                 lc.lecteur_pour('x.jpeg') == 'scan' and lc.lecteur_pour(dessin.with_suffix('')) is None)
        sans_ext = atelier / 'sans-extension'
        sans_ext.write_bytes(dessin.read_bytes())
        dxf = atelier / 'sans-ext-dxf'
        dxf.write_text('0\nSECTION\n2\nENTITIES\n0\nENDSEC\n0\nEOF\n')
        verifier('… un PDF ou un DXF sans extension sont reconnus à leur contenu',
                 lc.lecteur_pour(sans_ext) == 'pdf' and lc.lecteur_pour(dxf) == 'dxf')
        inconnu = atelier / 'plan.xyz'
        inconnu.write_text('rien')
        verifier('un format inconnu s\'arrête en disant lesquels sont lus', _leve(lc.lire_un, inconnu))
        vide = atelier / 'vide.pdf'
        vide.write_bytes(pdf('q 400 0 0 300 100 200 cm /Im0 Do Q\n'))
        try:
            lc.lire_un(vide)
            message = ''
        except co.ErreurPlan as err:
            message = str(err)
        verifier('un PDF sans texte ni image explique les deux lectures tentées',
                 'Comme scan' in message and 'aucune image' in message, message)
        (atelier / 'sous').mkdir()
        (atelier / 'sous' / 'autre.pdf').write_bytes(dessin.read_bytes())
        verifier('un dossier livre ses plans — pas le reste — sous-dossiers compris, dans l\'ordre',
                 [p.name for p in lc.plans_de(atelier)] == ['dessin.pdf', 'autre.pdf', 'vide.pdf'],
                 [p.name for p in lc.plans_de(atelier)])
        sortie = atelier / 'tout.csv'
        code = lc.main([str(dessin), '--csv', str(sortie), '--connus', str(liste)])
        verifier('la ligne de commande lit, compare et écrit le CSV', code == 0 and sortie.exists() and
                 'attendu, absent du plan' in sortie.read_text(encoding='utf-8-sig'))
        verifier('et rend 1 quand un plan n\'a pas pu être lu', lc.main([str(atelier)]) == 1)
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


if __name__ == '__main__':
    sys.exit(main())
