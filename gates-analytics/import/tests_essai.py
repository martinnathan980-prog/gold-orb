#!/usr/bin/env python3
"""
Batterie de l'essai à blanc : elle vérifie que le dossier d'essai est complet
et juste — la page, la recette, les plans, la base — puis, s'il y a un Chrome
sur le poste, elle JOUE la recette d'essai comme le fera la lectrice, et
vérifie que le CSV arrive et qu'il ressemble à un extract GATES.

    python3 import/tests_essai.py

Sans Chrome, la partie navigateur est sautée en le disant : le reste de la
batterie tourne quand même.

Aucune dépendance : bibliothèque standard uniquement.
"""

import csv
import io
import os
import pathlib
import shutil
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import essai                                                       # noqa: E402
import extraire                                                    # noqa: E402
import lire_composants                                             # noqa: E402
from composants import lire_connus, correspondance                 # noqa: E402
from piloter_chrome import Chrome                                  # noqa: E402
from tests_pilote import chrome_pour_la_batterie                   # noqa: E402

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


def main():
    atelier = pathlib.Path(tempfile.mkdtemp(prefix='suivi-fwd-essai-'))
    try:
        section('Le dossier d\'essai est complet')
        dossier, faits_prepa = essai.preparer(atelier / 'essai')
        noms = sorted(f.name for f, _ in faits_prepa)
        attendus = ['composants-base.csv', 'gates-essai.html', 'plan-essai.dxf', 'plan-essai.pdf',
                    'recette-essai.json']
        verifier('la page, la recette, les plans et la base sont écrits',
                 all(n in noms for n in attendus) and all(f.exists() for f, _ in faits_prepa), noms)
        verifier('le dossier de téléchargement existe — sinon Chrome n\'y déposerait rien',
                 (dossier / 'telechargements').is_dir())
        verifier('chaque fichier est décrit en français, pour qu\'on sache quoi en faire',
                 all(len(quoi) > 20 for _, quoi in faits_prepa))
        essai.preparer(dossier)
        verifier('préparer deux fois ne casse rien', (dossier / 'gates-essai.html').exists())

        section('La page d\'essai ressemble à l\'intranet')
        page = (dossier / 'gates-essai.html').read_text(encoding='utf-8')
        verifier('elle porte le champ, le bouton et le lien que la recette vise',
                 'id="recherche"' in page and '>Rechercher<' in page and 'id="telecharger"' in page)
        verifier('les trois contrats y sont, avec leurs lignes',
                 all(('"%s"' % c) in page for c in ('HDK', 'THS', 'VRK')) and 'TFE2130A600001A' in page)
        verifier('elle répond avec un délai : la recette doit savoir attendre',
                 'setTimeout' in page and '900' in page)
        verifier('elle dit qu\'elle n\'est pas réelle', 'essai' in page.lower() and 'rien de tout ceci' in page)

        section('L\'extract d\'essai a la forme d\'un extract GATES')
        lignes = list(csv.reader(io.StringIO(essai.csv_de('HDK')), delimiter=';'))
        lignes = [l for l in lignes if any(c.strip() for c in l)]
        verifier('deux lignes d\'en-tête — les groupes, puis les intitulés',
                 lignes[0][1] == 'Informations principales' and lignes[1][1] == 'Référence UD' and
                 lignes[1][16] == 'Avancement', (lignes[0][:2], lignes[1][:2]))
        verifier('toutes les lignes ont le même nombre de colonnes',
                 len(set(len(l) for l in lignes)) == 1 and len(lignes[0]) == 17,
                 sorted(set(len(l) for l in lignes)))
        verifier('la première colonne est sans intitulé et vide — celle qu\'Excel ajoute',
                 lignes[1][0] == '' and all(l[0] == '' for l in lignes[2:]))
        verifier('les colonnes 4 et 5 sont sans intitulé et vides, mais présentes',
                 lignes[1][3] == '' and lignes[1][4] == '' and all(l[3] == '' and l[4] == '' for l in lignes[2:]))
        references = [l[1] for l in lignes[2:]]
        verifier('les références suivent l\'anatomie réelle : CC, E, ATA, A, séquence, solution, indice',
                 all(len(r) == 15 and r[2] == 'E' and r[7] == 'A' and r[8:11] in ('600', '700', '800')
                     for r in references), references[:3])
        verifier('les colonnes analysées sont renseignées : CC, ATA, séquence, ECP, domaine',
                 all(l[11] and l[12] and l[13] and l[14] and l[7] in ('BASE', 'OPTION', 'PERSO') for l in lignes[2:]))
        avancements = [l[16] for l in lignes[2:]]
        verifier('les quatre états sont représentés, cellule vide comprise',
                 '100' in avancements and '' in avancements and '0' in avancements and
                 any(a not in ('', '0', '100') for a in avancements), avancements)
        verifier('un libellé qui contient un point-virgule serait protégé',
                 essai.csv_de('HDK').count('"') % 2 == 0)
        verifier('les trois contrats ne portent pas le même jeu de plans',
                 len({len(essai.PLANS[c]) for c in essai.PLANS}) > 1 and
                 essai.csv_de('HDK') != essai.csv_de('THS'))

        section('La recette d\'essai tient debout toute seule')
        recette = extraire.lire_recette(dossier / 'recette-essai.json')
        verifier('elle est valide au sens du vérificateur', recette['etapes'][0]['faire'] == 'ouvrir')
        verifier('elle vise la page du dossier, par son adresse de fichier',
                 recette['etapes'][0]['url'].startswith('file://') and 'gates-essai.html' in recette['etapes'][0]['url'])
        verifier('elle télécharge vers le dossier préparé',
                 pathlib.Path(recette['telechargements']).resolve() == (dossier / 'telechargements').resolve())
        verifier('elle joue les trois contrats, par une variable',
                 recette['variable'] == 'contrat' and sorted(recette['valeurs']) == ['HDK', 'THS', 'VRK'])
        verifier('elle dit, dans le fichier même, ce qui changera au bureau',
                 any('bureau' in l for l in recette['_ceci_est_un_essai']))
        verifier('les gestes sont ceux du vrai geste : ouvrir, attendre, remplir, cliquer, télécharger',
                 [e['faire'] for e in recette['etapes']] ==
                 ['ouvrir', 'attendre', 'remplir', 'cliquer_texte', 'attendre', 'cliquer', 'telecharger'],
                 [e['faire'] for e in recette['etapes']])

        section('Les plans d\'essai disent ce qu\'il faut voir')
        connus = lire_connus(dossier / 'composants-base.csv')
        attendus = connus['TFE2130A600001A']
        verifier('la base attend huit repères pour ce plan, dont un qui n\'est pas dessiné',
                 len(attendus) == 8 and '66ZZ' in attendus, sorted(attendus))
        for nom, lecteur in (('plan-essai.pdf', 'dessin PDF'), ('plan-essai.dxf', 'DXF')):
            r, quel = lire_composants.lire_un(dossier / nom, connus=attendus)
            reperes = sorted(c['repere'] for c in r['trouves'])
            verifier('%s : les cinq composants nets sont lus, et le cadre du plan est ignoré' % nom,
                     reperes == ['120PA3', '18AB', '19CD', '31AB2', '7XY'] and r['cadres'] == 1 and quel == lecteur,
                     (reperes, r['cadres']))
            c = correspondance(r, attendus)
            verifier('%s : 66ZZ est signalé absent du plan, et rien n\'est inventé' % nom,
                     '66ZZ' in c['absents'] and not c['en_plus'], c)
        r, _ = lire_composants.lire_un(dossier / 'plan-essai.pdf', connus=attendus)
        verifier('le PDF montre la boîte à deux repères et le repère sans boîte : la leçon du dossier',
                 any(d['pourquoi'] == 'plusieurs repères dans la même boîte' and
                     sorted(d['reperes']) == ['44XY', '45XZ'] for d in r['douteux']) and
                 [t['texte'] for t in r['orphelins']] == ['91AA'], (r['douteux'], r['orphelins']))
        verifier('chaque composant garde son part number', all(any(t.startswith('PN-') for t in c['textes'])
                                                               for c in r['trouves']))

        section('La marche à suivre dit tout ce qu\'il faut faire')
        texte = essai.marche_a_suivre(dossier)
        verifier('elle donne la commande qui ouvre le canal de Chrome',
                 '--remote-debugging-port=9222' in texte and 'Fermer Chrome' in texte)
        verifier('elle donne les commandes de vérification puis de jeu de la recette',
                 '--verifier' in texte and 'extraire.py' in texte and 'lire_composants.py' in texte)
        verifier('elle nomme les trois choses à changer au bureau',
                 'telechargements' in texte and 'url' in texte and 'Inspecter' in texte)
        verifier('tous les chemins qu\'elle cite existent vraiment',
                 all((dossier / n).exists() for n in ('gates-essai.html', 'recette-essai.json',
                                                      'plan-essai.pdf', 'composants-base.csv')))

        section('La chaîne entière, dans un vrai Chrome')
        exe = chrome_pour_la_batterie()
        if not exe:
            print('  Chrome est introuvable : cette partie n\'est pas jouée (ce n\'est pas un échec).')
        else:
            os.environ['SUIVI_FWD_CHROME'] = exe
            options = ['--no-sandbox'] if hasattr(os, 'geteuid') and os.geteuid() == 0 else []
            fichiers = essai.jouer(dossier, port=9336, contrats=['THS'], sans_fenetre=True,
                                   options=options, journal=lambda *_: None, lire_les_plans=False)
            verifier('la recette joue et le fichier arrive, sous le nom voulu',
                     len(fichiers) == 1 and fichiers[0].name == 'gates-THS.csv' and fichiers[0].exists(),
                     [str(f) for f in fichiers])
            contenu = fichiers[0].read_text(encoding='utf-8-sig')
            recu = [l for l in csv.reader(io.StringIO(contenu), delimiter=';') if any(c.strip() for c in l)]
            verifier('le CSV reçu est exactement l\'extract du contrat demandé',
                     recu == [l for l in csv.reader(io.StringIO(essai.csv_de('THS')), delimiter=';')
                              if any(c.strip() for c in l)],
                     recu[:2])
            verifier('il est lisible par le dépôt : séparateur et encodage retrouvés tout seuls',
                     _relisible(fichiers[0]), 'deposer.lire_tableur doit le relire')
            verifier('rejouer ne redonne pas deux fois le même fichier',
                     len(essai.jouer(dossier, port=9336, contrats=['VRK'], sans_fenetre=True,
                                     options=options, journal=lambda *_: None,
                                     lire_les_plans=False)) == 1)
    finally:
        shutil.rmtree(atelier, ignore_errors=True)

    print('\n%d vérifications, %d échec(s).' % (len(faits) + len(echecs), len(echecs)))
    return 1 if echecs else 0


def _relisible(fichier):
    import deposer
    lignes = deposer.lire_tableur(fichier)
    return len(lignes) > 2 and lignes[1][1] == 'Référence UD' and len(lignes[0]) == 17


if __name__ == '__main__':
    sys.exit(main())
