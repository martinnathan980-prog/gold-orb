#!/usr/bin/env python3
"""
Rejoue une « recette » d'extraction dans Chrome : la suite de gestes qu'on
fait à la main sur l'intranet — aller à la page, chercher un contrat, cliquer
« Tout extraire », récupérer le fichier — écrite une fois dans un fichier,
puis rejouée à l'identique, contrat après contrat, plan après plan.

    python3 import/extraire.py recettes/gates.json
    python3 import/extraire.py recettes/see.json --valeurs HDK THS VRK
    python3 import/extraire.py recettes/composants.json --valeurs-fichier refs.txt

Une recette est un fichier JSON :

    {
      "nom": "GATES — un extract par contrat",
      "telechargements": "C:/Users/moi/Downloads",
      "variable": "contrat",
      "valeurs": ["HDK", "THS", "VRK"],
      "etapes": [
        { "faire": "ouvrir",        "url": "https://intranet/gates" },
        { "faire": "remplir",       "ou": "#recherche", "texte": "{contrat}" },
        { "faire": "cliquer_texte", "texte": "Tout extraire" },
        { "faire": "telecharger",   "vers": "gates-{contrat}.csv" }
      ]
    }

Les gestes disponibles : ouvrir, attendre, cliquer, cliquer_texte, remplir,
telecharger, lire_tableau, patienter. « {contrat} » — ou le nom de n'importe
quelle variable — est remplacé par la valeur du tour en cours.

Rien n'est deviné : tant que la recette ne dit pas ce qu'il faut cliquer, le
script ne clique rien. C'est la recette qu'on écrit une fois, devant l'écran,
en relevant les sélecteurs dans F12 ou simplement le texte des boutons.

Aucune dépendance : bibliothèque standard uniquement.
"""

import argparse
import json
import pathlib
import re
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from piloter_chrome import Chrome, ErreurPilote, PORT_DEFAUT   # noqa: E402

GESTES = ('ouvrir', 'attendre', 'cliquer', 'cliquer_texte', 'remplir',
          'telecharger', 'lire_tableau', 'patienter')


class ErreurRecette(Exception):
    """Une recette qui ne tient pas debout, dite en français."""


# ---------------------------------------------------------------------------
#  Lire et vérifier une recette — sans navigateur : ça se teste seul
# ---------------------------------------------------------------------------
def lire_recette(chemin):
    fichier = pathlib.Path(chemin)
    if not fichier.exists():
        raise ErreurRecette('Recette introuvable : %s' % fichier)
    try:
        recette = json.loads(fichier.read_text(encoding='utf-8'))
    except ValueError as err:
        raise ErreurRecette('Recette illisible (%s) : %s' % (fichier.name, err))
    return verifier_recette(recette)


def verifier_recette(recette):
    """Rend la recette telle quelle si elle tient debout, sinon dit pourquoi."""
    if not isinstance(recette, dict):
        raise ErreurRecette('Une recette est un objet JSON, pas %s.' % type(recette).__name__)
    etapes = recette.get('etapes')
    if not isinstance(etapes, list) or not etapes:
        raise ErreurRecette('Une recette a besoin d\'au moins une étape dans « etapes ».')
    for rang, etape in enumerate(etapes, 1):
        if not isinstance(etape, dict):
            raise ErreurRecette('Étape %d : un objet est attendu.' % rang)
        geste = etape.get('faire')
        if geste not in GESTES:
            raise ErreurRecette('Étape %d : geste « %s » inconnu. Au choix : %s.'
                                % (rang, geste, ', '.join(GESTES)))
        manque = {
            'ouvrir': ['url'], 'attendre': ['ou'], 'cliquer': ['ou'],
            'cliquer_texte': ['texte'], 'remplir': ['ou', 'texte'],
            'lire_tableau': ['ou'], 'patienter': ['secondes'],
        }.get(geste, [])
        for cle in manque:
            if cle not in etape:
                raise ErreurRecette('Étape %d (%s) : il manque « %s ».' % (rang, geste, cle))
    if 'valeurs' in recette and not isinstance(recette['valeurs'], list):
        raise ErreurRecette('« valeurs » doit être une liste.')
    if recette.get('valeurs') and not recette.get('variable'):
        raise ErreurRecette('Des valeurs sans « variable » : le script ne saurait pas quoi remplacer.')
    if any(e['faire'] == 'telecharger' for e in etapes) and not recette.get('telechargements'):
        raise ErreurRecette(
            'Une étape « telecharger » sans « telechargements » : il faut dire dans quel dossier '
            'Chrome dépose les fichiers.')
    return recette


def remplacer(texte, variables):
    """« gates-{contrat}.csv » avec contrat=HDK donne « gates-HDK.csv »."""
    if not isinstance(texte, str):
        return texte

    def une(trouvaille):
        nom = trouvaille.group(1)
        if nom not in variables:
            raise ErreurRecette('« {%s} » n\'est pas une variable de cette recette.' % nom)
        return str(variables[nom])

    return re.sub(r'\{([A-Za-z_][A-Za-z0-9_]*)\}', une, texte)


def valeurs_de(recette, imposees=None, fichier=None):
    """Les tours à jouer : ceux de la ligne de commande, d'un fichier, ou de la recette."""
    if imposees:
        return list(imposees)
    if fichier:
        lignes = pathlib.Path(fichier).read_text(encoding='utf-8').splitlines()
        valeurs = [l.strip() for l in lignes if l.strip() and not l.strip().startswith('#')]
        if not valeurs:
            raise ErreurRecette('%s ne contient aucune valeur à jouer.' % fichier)
        return valeurs
    if recette.get('variable') and not recette.get('valeurs'):
        raise ErreurRecette(
            'Cette recette attend des valeurs pour « %s » : donnez-les avec --valeurs, '
            'avec --valeurs-fichier, ou dans la recette.' % recette['variable'])
    return list(recette.get('valeurs') or [None])


# ---------------------------------------------------------------------------
#  Jouer une recette dans Chrome
# ---------------------------------------------------------------------------
def jouer(chrome, recette, variables, journal=print):
    """Joue les étapes une fois, avec ces variables. Rend ce qui a été récolté."""
    recolte = {'fichiers': [], 'tableaux': []}
    for rang, etape in enumerate(recette['etapes'], 1):
        geste = etape['faire']
        delai = etape.get('delai')
        if geste == 'ouvrir':
            url = remplacer(etape['url'], variables)
            journal('    %d. ouvrir %s' % (rang, url))
            chrome.ouvrir(url, delai=delai)
        elif geste == 'attendre':
            cible = remplacer(etape['ou'], variables)
            journal('    %d. attendre %s' % (rang, cible))
            chrome.attendre_selecteur(cible, delai=delai)
        elif geste == 'cliquer':
            cible = remplacer(etape['ou'], variables)
            journal('    %d. cliquer %s' % (rang, cible))
            avant = chrome.fichiers_presents() if chrome.telechargements else None
            chrome.cliquer(cible, delai=delai)
            variables['_avant'] = avant
        elif geste == 'cliquer_texte':
            mot = remplacer(etape['texte'], variables)
            journal('    %d. cliquer « %s »' % (rang, mot))
            avant = chrome.fichiers_presents() if chrome.telechargements else None
            chrome.cliquer_texte(mot, delai=delai)
            variables['_avant'] = avant
        elif geste == 'remplir':
            cible = remplacer(etape['ou'], variables)
            valeur = remplacer(etape['texte'], variables)
            journal('    %d. remplir %s avec « %s »' % (rang, cible, valeur))
            chrome.remplir(cible, valeur, delai=delai)
        elif geste == 'patienter':
            import time
            journal('    %d. patienter %s s' % (rang, etape['secondes']))
            time.sleep(float(etape['secondes']))
        elif geste == 'lire_tableau':
            cible = remplacer(etape['ou'], variables)
            lignes = chrome.tableau(cible)
            if lignes is None:
                raise ErreurRecette('Étape %d : aucun tableau « %s » dans cette page.' % (rang, cible))
            journal('    %d. lire le tableau %s — %d lignes' % (rang, cible, len(lignes)))
            recolte['tableaux'].append(lignes)
        elif geste == 'telecharger':
            fichier = chrome.attendre_telechargement(variables.get('_avant'),
                                                     delai=etape.get('delai', 180),
                                                     motif=etape.get('motif'))
            # Le fichier est pris : le prochain « telecharger » attend le suivant,
            # il ne rend pas deux fois le même.
            variables['_avant'] = chrome.fichiers_presents()
            if etape.get('vers'):
                voulu = fichier.parent / remplacer(etape['vers'], variables)
                fichier.replace(voulu)
                fichier = voulu
            journal('    %d. fichier reçu : %s' % (rang, fichier.name))
            recolte['fichiers'].append(fichier)
    return recolte


def extraire(chemin_recette, valeurs=None, fichier_valeurs=None, port=PORT_DEFAUT,
             lancer=False, journal=print):
    """Joue la recette pour chaque valeur, et rend la récolte de tous les tours."""
    recette = lire_recette(chemin_recette)
    tours = valeurs_de(recette, valeurs, fichier_valeurs)
    dossier = recette.get('telechargements')
    journal('%s — %d tour(s)' % (recette.get('nom', pathlib.Path(chemin_recette).stem), len(tours)))
    tout = {'fichiers': [], 'tableaux': []}
    with Chrome(port=port, telechargements=dossier, lancer=lancer) as chrome:
        for valeur in tours:
            variables = dict(recette.get('variables') or {})
            if recette.get('variable'):
                variables[recette['variable']] = valeur
            journal('  · %s' % (valeur if valeur is not None else 'tour unique'))
            recolte = jouer(chrome, recette, variables, journal)
            tout['fichiers'] += recolte['fichiers']
            tout['tableaux'] += recolte['tableaux']
    return tout


def main(argv=None):
    parseur = argparse.ArgumentParser(description='Rejoue une recette d\'extraction dans Chrome.')
    parseur.add_argument('recette', help='le fichier JSON de la recette')
    parseur.add_argument('--valeurs', nargs='*', help='les valeurs à jouer (sinon celles de la recette)')
    parseur.add_argument('--valeurs-fichier', help='un fichier, une valeur par ligne')
    parseur.add_argument('--port', type=int, default=PORT_DEFAUT, help='le port de débogage de Chrome')
    parseur.add_argument('--lancer', action='store_true',
                         help='démarrer un Chrome à part au lieu de s\'attacher au vôtre')
    parseur.add_argument('--verifier', action='store_true',
                         help='lire la recette et s\'arrêter là, sans toucher à Chrome')
    args = parseur.parse_args(argv)
    try:
        if args.verifier:
            recette = lire_recette(args.recette)
            tours = valeurs_de(recette, args.valeurs, args.valeurs_fichier)
            print('Recette lisible : %d étape(s), %d tour(s).' % (len(recette['etapes']), len(tours)))
            return 0
        recolte = extraire(args.recette, args.valeurs, args.valeurs_fichier, args.port, args.lancer)
        print('%d fichier(s), %d tableau(x).' % (len(recolte['fichiers']), len(recolte['tableaux'])))
        for f in recolte['fichiers']:
            print('  ' + str(f))
        return 0
    except (ErreurRecette, ErreurPilote) as err:
        print('Arrêt : %s' % err, file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
